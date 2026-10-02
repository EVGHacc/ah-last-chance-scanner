import argparse
import hashlib
from html import unescape
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from .model import Coverage, InventoryProof
from .providers.ashby import short_summary
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


def _job_record(job):
    return {
        "job_id":job.job_id,
        "title":job.title,
        "location":job.location,
        "summary":job.summary,
        "job_url":job.job_url,
        "apply_url":job.apply_url,
        "department":job.department,
        "team":job.team,
        "published_at":job.published_at,
        "record_source":"ashby_public_api",
    }


def _jobs_hash(records):
    canonical=[
        "\t".join([
            str(j.get("job_id") or ""),
            str(j.get("title") or ""),
            str(j.get("location") or ""),
            str(j.get("summary") or ""),
            str(j.get("job_url") or ""),
            str(j.get("apply_url") or ""),
        ])
        for j in records
    ]
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


def _json_ld_objects(html):
    for body in re.findall(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html,
        re.I|re.S,
    ):
        try:
            data=json.loads(unescape(body).strip())
        except Exception:
            continue
        stack=[data]
        while stack:
            item=stack.pop()
            if isinstance(item,list):
                stack.extend(item)
            elif isinstance(item,dict):
                if str(item.get("@type","")).casefold()=="jobposting":
                    yield item
                stack.extend(v for v in item.values() if isinstance(v,(dict,list)))


def _location_from_jobposting(job):
    loc=job.get("jobLocation")
    if isinstance(loc,list):
        loc=loc[0] if loc else None
    if not isinstance(loc,dict):
        return ""
    address=loc.get("address")
    if not isinstance(address,dict):
        return ""
    parts=[address.get("addressLocality"),address.get("addressRegion"),address.get("addressCountry")]
    return ", ".join(str(x).strip() for x in parts if isinstance(x,str) and x.strip())


def _meta_content(html, key):
    patterns=[
        rf'<meta[^>]+(?:name|property)=["\']{re.escape(key)}["\'][^>]+content=["\']([^"\']+)["\']',
        rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:name|property)=["\']{re.escape(key)}["\']',
    ]
    for pattern in patterns:
        match=re.search(pattern,html,re.I)
        if match:
            return unescape(match.group(1)).strip()
    return ""


def _first_party_job_record(row, ident, html):
    lower=html.lower()
    ashby_job=f"https://jobs.ashbyhq.com/{row['board']}/{ident}"
    ashby_apply=ashby_job+"/application"
    if ident not in lower or ashby_job.lower() not in lower or ashby_apply.lower() not in lower:
        raise ValueError(f"first-party-only job not live/apply-linked: {ident}")
    posting=next(_json_ld_objects(html),None)
    if posting:
        title=posting.get("title") if isinstance(posting.get("title"),str) else ""
        raw={
            "descriptionPlain":posting.get("description") if isinstance(posting.get("description"),str) else "",
            "location":_location_from_jobposting(posting),
        }
        location=raw["location"]
    else:
        title=_meta_content(html,"og:title") or _meta_content(html,"twitter:title")
        raw={"descriptionPlain":_meta_content(html,"description") or _meta_content(html,"og:description")}
        location=""
    title=title.strip()
    if not title:
        match=re.search(r"<title[^>]*>(.*?)</title>",html,re.I|re.S)
        title=re.sub(r"\s+"," ",unescape(match.group(1))).strip() if match else ""
    if not title:
        raise ValueError(f"first-party-only job title absent: {ident}")
    return {
        "job_id":ident,
        "title":title,
        "location":location,
        "summary":short_summary(raw),
        "job_url":row["first_party_detail_url_template"].format(id=ident),
        "apply_url":ashby_apply,
        "department":"",
        "team":"",
        "published_at":None,
        "record_source":"first_party_reconciled",
    }


def _reconcile_first_party_only(row, ids, html_fetcher):
    records=[]
    template=row.get("first_party_detail_url_template")
    for ident in sorted(ids):
        detail_url=template.format(id=ident)
        html=html_fetcher(detail_url)
        records.append(_first_party_job_record(row,ident,html))
    return tuple(records)


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
            reconciled_records=()
            proof=provider_proof
            inventory_count=len(ashby_ids)
            evidence_kind=provider_proof.evidence_kind
            job_records=[_job_record(j) for j in meta.jobs]

            if first_party_ids is not None:
                # Authority contract: Ashby's complete provider payload is authoritative.
                # First-party HTML is sampled asynchronously and is diagnostic only;
                # never merge it into, or subtract it from, the authoritative snapshot.
                first_party_only=first_party_ids-ashby_ids
                provider_only=ashby_ids-first_party_ids

            if len(job_records)!=inventory_count:
                raise ValueError(f"persisted job record count mismatch: {len(job_records)} != {inventory_count}")
            if any(not j["title"].strip() or not j["summary"].strip() for j in job_records):
                raise ValueError("persisted job record missing title or summary")
            if len({j["job_id"] for j in job_records})!=len(job_records):
                raise ValueError("persisted job record ids are not unique")

            job_records.sort(key=lambda j:(j["title"].casefold(),j["job_id"]))
            results.append({
                "name":source.name,
                "board":row["board"],
                "coverage":proof.coverage.value,
                "raw_jobs":meta.raw_count,
                "unlisted_jobs":meta.unlisted_count,
                "provider_unique_jobs":len(ashby_ids),
                "first_party_unique_jobs":None if first_party_ids is None else len(first_party_ids),
                "first_party_only_jobs":len(first_party_only),
                "reconciled_first_party_only_ids":[],
                "first_party_drift_detected":bool(first_party_only or provider_only),
                "provider_only_jobs":len(provider_only),
                "unique_jobs":inventory_count,
                "exhausted":proof.exhausted,
                "evidence_kind":evidence_kind,
                "endpoint":ashby_endpoint(row["board"]),
                "first_party_evidence_url":row["first_party_evidence_url"],
                "jobs_sha256":_jobs_hash(job_records),
                "jobs":job_records,
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
                "jobs":[],
                "checked_at":checked_at,
                "error":f"{type(exc).__name__}: {exc}",
            })
    verified=sum(r["coverage"]==Coverage.VERIFIED_COMPLETE.value for r in results)
    return {
        "schema_version":2,
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
    target=args.output if payload["failed"]==0 else args.output.with_suffix(args.output.suffix+".attempt")
    target.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    if payload["failed"]:
        raise SystemExit("attempt rejected; authoritative proof preserved")
    print(json.dumps({
        "provider":payload["provider"],
        "configured_sources":payload["configured_sources"],
        "verified_complete":payload["verified_complete"],
        "failed":payload["failed"],
        "persisted_jobs":sum(len(x["jobs"]) for x in payload["sources"]),
        "output":str(args.output),
    }))


if __name__=="__main__":
    main()
