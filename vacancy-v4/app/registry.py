import json
from pathlib import Path
from .model import Source
DEFAULT_MANIFEST = Path(__file__).resolve().parents[1] / "config" / "sources.json"
def load_sources(path: Path = DEFAULT_MANIFEST) -> tuple[Source, ...]:
    data=json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version")!=1: raise ValueError("unsupported source manifest schema")
    rows=data.get("sources")
    if not isinstance(rows,list) or data.get("target_count")!=105 or len(rows)!=105: raise ValueError("v4 target manifest must contain exactly 105 sources")
    out=[];seen=set()
    for row in rows:
        if set(row)!={"kind","name","official_domain","seed_urls","allowed_domains"}: raise ValueError("manifest contains non-identity fields")
        key=(row["kind"],row["name"])
        if key in seen: raise ValueError(f"duplicate source: {key}")
        seen.add(key)
        if row["kind"] not in {"employer","recruiter","job_board"} or not row["name"] or not row["official_domain"]: raise ValueError(f"invalid source identity: {key}")
        seeds=tuple(row["seed_urls"])
        if not seeds or not all(isinstance(u,str) and u.startswith(("https://","http://")) for u in seeds): raise ValueError(f"invalid seed URLs: {key}")
        out.append(Source(row["kind"],row["name"],row["official_domain"],seeds,tuple(row["allowed_domains"])))
    return tuple(out)
