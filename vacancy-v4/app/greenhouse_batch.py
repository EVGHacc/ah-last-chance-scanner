import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from .model import Coverage, InventoryProof
from .providers.greenhouse import inventory
from .registry import load_sources
from .transport import fetch_json

DEFAULT_CONFIG=Path(__file__).resolve().parents[1]/"config"/"greenhouse_sources.json"
DEFAULT_OUTPUT=Path(__file__).resolve().parents[1]/"data"/"greenhouse-proof.json"
GREENHOUSE_MAX_BYTES=64_000_000


def endpoint(board_token: str) -> str:
    return f"https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true"


def load_config(path=DEFAULT_CONFIG):
    data=json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("schema_version")!=1 or data.get("provider")!="greenhouse":
        raise ValueError("invalid Greenhouse config")
    rows=data.get("sources")
    if not isinstance(rows,list) or not rows:
        raise ValueError("Greenhouse config has no sources")
    seen=set()
    for row in rows:
        if set(row)!={"name","board","first_party_evidence_url"}:
            raise ValueError("unexpected Greenhouse config fields")
        if not all(isinstance(v,str) and v.strip() for v in row.values()):
            raise ValueError("invalid Greenhouse config value")
        if row["name"] in seen:
            raise ValueError("duplicate Greenhouse source")
        seen.add(row["name"])
    return rows


def _record(job):
    return {
        "job_id":job.job_id,
        "title":job.title,
        "location":job.location,
        "summary":job.summary,
        "job_url":job.job_url,
        "apply_url":job.apply_url,
        "department":job.department,
        "office":job.office,
        "published_at":job.published_at,
        "updated_at":job.updated_at,
        "record_source":"greenhouse_job_board_api",
    }


def _hash(records):
    canonical=[
        "\t".join([
            j["job_id"],j["title"],j["location"],j["summary"],
            j["job_url"],j["apply_url"],j["department"],j["office"],
            j["published_at"] or "",j["updated_at"] or "",
        ])
        for j in records
    ]
    return hashlib.sha256("\n".join(sorted(canonical)).encode("utf-8")).hexdigest()


def run_batch(fetcher=None,config_path=DEFAULT_CONFIG):
    source_by_name={s.name:s for s in load_sources()}
    configured=load_config(config_path)
    unknown=[r["name"] for r in configured if r["name"] not in source_by_name]
    if unknown:
        raise ValueError(f"Greenhouse config references non-target sources: {unknown}")
    transport=fetcher or (lambda url: fetch_json(url,max_bytes=GREENHOUSE_MAX_BYTES))
    results=[]
    for row in configured:
        source=source_by_name[row["name"]]
        checked_at=datetime.now(timezone.utc).isoformat()
        try:
            inv=inventory(source,row["board"],lambda _:transport(endpoint(row["board"])))
            records=sorted((_record(j) for j in inv.jobs),key=lambda j:(j["title"].casefold(),j["job_id"]))
            proof=InventoryProof(
                source=source,
                coverage=Coverage.VERIFIED_COMPLETE,
                unique_jobs=len(records),
                authoritative_total=inv.authoritative_total,
                exhausted=True,
                evidence_kind="official_complete_payload",
            )
            proof.validate()
            if len(records)!=inv.authoritative_total:
                raise ValueError("persisted job record count mismatch")
            if len({j["job_id"] for j in records})!=len(records):
                raise ValueError("persisted job ids are not unique")
            if any(not j["title"].strip() or not j["summary"].strip() for j in records):
                raise ValueError("persisted job record missing title or summary")
            results.append({
                "name":source.name,
                "board":row["board"],
                "coverage":proof.coverage.value,
                "unique_jobs":proof.unique_jobs,
                "authoritative_total":proof.authoritative_total,
                "exhausted":proof.exhausted,
                "evidence_kind":"greenhouse_meta_total_reconciled",
                "endpoint":endpoint(row["board"]),
                "first_party_evidence_url":row["first_party_evidence_url"],
                "jobs_sha256":_hash(records),
                "jobs":records,
                "checked_at":checked_at,
                "error":None,
            })
        except Exception as exc:
            results.append({
                "name":source.name,
                "board":row["board"],
                "coverage":Coverage.UNPROVEN.value,
                "unique_jobs":0,
                "authoritative_total":None,
                "exhausted":False,
                "evidence_kind":None,
                "endpoint":endpoint(row["board"]),
                "first_party_evidence_url":row["first_party_evidence_url"],
                "jobs_sha256":None,
                "jobs":[],
                "checked_at":checked_at,
                "error":f"{type(exc).__name__}: {exc}",
            })
    verified=sum(x["coverage"]==Coverage.VERIFIED_COMPLETE.value for x in results)
    return {
        "schema_version":1,
        "provider":"greenhouse",
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
        failures=[
            {"name":row["name"],"board":row["board"],"error":row["error"]}
            for row in payload["sources"] if row["coverage"]!=Coverage.VERIFIED_COMPLETE.value
        ]
        print(json.dumps({"greenhouse_failed_sources":failures},ensure_ascii=False),file=sys.stderr)
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
