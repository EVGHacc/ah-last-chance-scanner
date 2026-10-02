import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from .model import Coverage, InventoryProof
from .registry import load_sources
from .runner import ashby_endpoint, ashby_run_with_metadata
from .transport import fetch_text

DEFAULT_CONFIG = Path(__file__).resolve().parents[1] / "config" / "ashby_sources.json"
DEFAULT_OUTPUT = Path(__file__).resolve().parents[1] / "data" / "ashby-proof.json"


def load_config(path=DEFAULT_CONFIG):
    data=json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("schema_version") != 1 or data.get("provider") != "ashby":
        raise ValueError("invalid Ashby config")
    rows=data.get("sources")
    if not isinstance(rows,list) or not rows:
        raise ValueError("Ashby config has no sources")
    seen=set()
    allowed={
        "name","board","first_party_evidence_url",
        "first_party_job_id_pattern","first_party_detail_url_template",
    }
    required={"name","board","first_party_evidence_url"}
    for row in rows:
        if not set(row).issubset(allowed) or not required.issubset(row):
            raise ValueError("unexpected Ashby config fields")
        if not all(isinstance(row[k],str) and row[k].strip() for k in row):
            raise ValueError("invalid Ashby config value")
        if row["name"] in seen:
            raise ValueError("duplicate Ashby source")
        has_pattern="first_party_job_id_pattern" in row
        has_template="first_party_detail_url_template" in row
        if has_pattern != has_template:
            raise ValueError("first-party reconciliation requires pattern and detail template")
        if has_pattern:
            re.compile(row["first_party_job_id_pattern"])
            if "{id}" not in row["first_party_detail_url_template"]:
                raise ValueError("first-party detail template missing {id}")
        seen.add(row["name"])
    return rows


def _jobs_hash(jobs, reconciled_ids=()):
    canonical=[f"{j.title}\t{j.job_url}\t{j.apply_url}" for j in jobs]
    canonical.extend(f"FIRST_PARTY_RECONCILED\t{x}" for x in reconciled_ids)
    return hashlib.sha256("\n".join(sorted(canonical)).encode("utf-8")).hexdigest()


def _job_ids(jobs):
    return {urlparse(j.job_url).path.strip("/").split("/")[1].lower() for j in jobs}


def _first_party_ids(row, html_fetcher):
    pattern=row.get("first_party_job_id_pattern")
    if not pattern:
        return None
    html=html_fetcher(row["first_party_evidence_url"])
    ids={x.lower() for x in re.findall(pattern,html,re.I)}
    if not ids:
        raise ValueError("first-party inventory ids absent")
    return ids


def _reconcile_first_party_only(row, ids, html_fetcher):
    reconciled=[]
    template=row.get("first_party_detail_url_template")
    for ident in sorted(ids):
        detail_url=template.format(id=ident)
        html=html_fetcher(detail_url)
        lower=html.lower()
        ashby_job=f"jobs.ashbyhq.com/{row['board'].lower()}/{ident}"
        ashby_apply=ashby_job+"/application"
        if ident not in lower or ashby_job not in lower or ashby_apply not in lower:
            raise ValueError(f"first-party-only job not live/apply-linked: {ident}")
        reconciled.append(ident)
    return tuple(reconciled)


def run_batch(fetcher=None, html_fetcher=None, config_path=DEFAULT_CONFIG):
    source_by_name={s.name:s for s in load_sources()}
    configured=load_config(config_path)
    unknown=[r["name"] for r in configured if r["name"] not in source_by_name]
    if unknown:
        raise ValueError(f"Ashby config references non-target sources: {unknown}")
    page_fetcher=html_fetcher or fetch_text
    results=[]
    for row in configured:
        source=source_by_name[row["name"]]
        checked_at=datetime.now(timezone.utc).isoformat()
        try:
            provider_proof,meta=ashby_run_with_metadata(source,row["board"],fetcher)
            ashby_ids=_job_ids(meta.jobs)
            first_party_ids=_first_party_ids(row,page_fetcher)
            first_party_only=set()
            provider_only=set()
            reconciled=()
            proof=provider_proof
            inventory_count=len(ashby_ids)
            evidence_kind=provider_proof.evidence_kind

            if first_party_ids is not None:
                first_party_only=first_party_ids-ashby_ids
                provider_only=ashby_ids-first_party_ids
                if provider_only:
                    raise ValueError(
                        f"Ashby jobs missing from first-party inventory "
                        f"count={len(provider_only)} sample={sorted(provider_only)[:3]}"
                    )
                if first_party_only:
                    reconciled=_reconcile_first_party_only(row,first_party_only,page_fetcher)
                    inventory_count=len(first_party_ids)
                    proof=InventoryProof(
                        source=source,
                        coverage=Coverage.VERIFIED_COMPLETE,
                        unique_jobs=inventory_count,
                        authoritative_total=None,
                        exhausted=True,
                        evidence_kind="official_complete_payload_plus_first_party_reconciled",
                    )
                    proof.validate()
                    evidence_kind=proof.evidence_kind

            results.append({
                "name":source.name,
                "board":row["board"],
                "coverage":proof.coverage.value,
                "raw_jobs":meta.raw_count,
                "unlisted_jobs":meta.unlisted_count,
                "provider_unique_jobs":len(ashby_ids),
                "first_party_unique_jobs":None if first_party_ids is None else len(first_party_ids),
                "first_party_only_jobs":len(first_party_only),
                "reconciled_first_party_only_ids":list(reconciled),
                "unique_jobs":inventory_count,
                "exhausted":proof.exhausted,
                "evidence_kind":evidence_kind,
                "endpoint":ashby_endpoint(row["board"]),
                "first_party_evidence_url":row["first_party_evidence_url"],
                "jobs_sha256":_jobs_hash(meta.jobs,reconciled),
                "checked_at":checked_at,
                "error":None,
            })
        except Exception as exc:
            results.append({
                "name":source.name,
                "board":row["board"],
                "coverage":Coverage.UNPROVEN.value,
                "raw_jobs":None,
                "unlisted_jobs":None,
                "provider_unique_jobs":None,
                "first_party_unique_jobs":None,
                "first_party_only_jobs":None,
                "reconciled_first_party_only_ids":[],
                "unique_jobs":0,
                "exhausted":False,
                "evidence_kind":None,
                "endpoint":ashby_endpoint(row["board"]),
                "first_party_evidence_url":row["first_party_evidence_url"],
                "jobs_sha256":None,
                "checked_at":checked_at,
                "error":f"{type(exc).__name__}: {exc}",
            })
    verified=sum(r["coverage"]==Coverage.VERIFIED_COMPLETE.value for r in results)
    return {
        "schema_version":1,
        "provider":"ashby",
        "generated_at":datetime.now(timezone.utc).isoformat(),
        "configured_sources":len(results),
        "verified_complete":verified,
        "failed":len(results)-verified,
        "sources":results,
    }


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--output",type=Path,default=DEFAULT_OUTPUT)
    args=parser.parse_args()
    payload=run_batch()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({
        "provider":payload["provider"],
        "configured_sources":payload["configured_sources"],
        "verified_complete":payload["verified_complete"],
        "failed":payload["failed"],
        "output":str(args.output),
    }))


if __name__=="__main__":
    main()
