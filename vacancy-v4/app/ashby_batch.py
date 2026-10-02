import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from .model import Coverage
from .registry import load_sources
from .runner import ashby_endpoint, ashby_run_with_metadata

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
    for row in rows:
        if set(row) != {"name","board","first_party_evidence_url"}:
            raise ValueError("unexpected Ashby config fields")
        if not all(isinstance(row[k],str) and row[k].strip() for k in row):
            raise ValueError("invalid Ashby config value")
        if row["name"] in seen:
            raise ValueError("duplicate Ashby source")
        seen.add(row["name"])
    return rows


def _jobs_hash(jobs):
    canonical="\n".join(sorted(f"{j.title}\t{j.job_url}\t{j.apply_url}" for j in jobs))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def run_batch(fetcher=None, config_path=DEFAULT_CONFIG):
    source_by_name={s.name:s for s in load_sources()}
    configured=load_config(config_path)
    unknown=[r["name"] for r in configured if r["name"] not in source_by_name]
    if unknown:
        raise ValueError(f"Ashby config references non-target sources: {unknown}")
    results=[]
    for row in configured:
        source=source_by_name[row["name"]]
        checked_at=datetime.now(timezone.utc).isoformat()
        try:
            proof,meta=ashby_run_with_metadata(source,row["board"],fetcher)
            results.append({
                "name":source.name,
                "board":row["board"],
                "coverage":proof.coverage.value,
                "raw_jobs":meta.raw_count,
                "unlisted_jobs":meta.unlisted_count,
                "unique_jobs":proof.unique_jobs,
                "exhausted":proof.exhausted,
                "evidence_kind":proof.evidence_kind,
                "endpoint":ashby_endpoint(row["board"]),
                "first_party_evidence_url":row["first_party_evidence_url"],
                "jobs_sha256":_jobs_hash(meta.jobs),
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
