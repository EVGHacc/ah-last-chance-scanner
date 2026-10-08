"""Pinned Breezy batch; no zero-inventory certification and no guessed boards."""
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from .providers.breezy import _board_host, parse_inventory
from .registry import load_sources
from .transport import fetch_json, fetch_text

CONFIG = Path(__file__).resolve().parents[1] / "config/breezy_sources.json"


def run_batch(fetcher=None, detail_fetcher=None, config_path=CONFIG):
    data = json.loads(Path(config_path).read_text(encoding="utf-8"))
    if data.get("schema_version") != 1 or data.get("provider") != "breezy":
        raise ValueError("invalid Breezy provider configuration")
    rows = data.get("sources")
    if not isinstance(rows, list) or not rows:
        raise ValueError("no Breezy sources configured")
    known = {s.name for s in load_sources()}
    names = set()
    results = []
    for row in rows:
        name, board, feed = row["name"], row["board_url"], row["feed_url"]
        host = _board_host(board)
        parsed = urlparse(feed)
        if (name not in known or name in names or parsed.scheme != "https"
                or parsed.netloc != host or parsed.path != "/json"
                or parsed.query or parsed.fragment):
            raise ValueError("untrusted Breezy source identity or route")
        names.add(name)
        checked_at = datetime.now(timezone.utc).isoformat()
        try:
            payload = (fetcher or fetch_json)(feed)
            jobs = parse_inventory(payload, board, detail_fetcher or fetch_text)
            results.append(dict(name=name, coverage="verified_complete", unique_jobs=len(jobs),
                                authoritative_total=len(payload), jobs=jobs, checked_at=checked_at, error=None))
        except Exception as exc:
            results.append(dict(name=name, coverage="unproven", unique_jobs=0,
                                authoritative_total=None, jobs=[], checked_at=checked_at,
                                error=f"{type(exc).__name__}: {exc}"))
    verified = sum(s["coverage"] == "verified_complete" for s in results)
    return dict(schema_version=1, provider="breezy", configured_sources=len(results),
                verified_complete=verified, failed=len(results)-verified, sources=results)
