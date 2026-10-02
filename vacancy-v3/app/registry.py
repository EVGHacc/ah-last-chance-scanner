import csv
from pathlib import Path

from .models import Source


def load_registry(path: str | Path) -> list[Source]:
    with Path(path).open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh, delimiter="\t"))
    sources = [
        Source(
            kind=row["kind"].strip(),
            name=row["name"].strip(),
            official_domain=row["official_domain"].strip(),
            seed_urls=tuple(x for x in row["seed_urls"].split(";") if x),
            no_public_hint=row["no_public_hint"].strip() == "1",
            allowed_domains=tuple(x for x in row["allowed_domains"].split(";") if x),
        )
        for row in rows
    ]
    names=[(s.kind,s.name) for s in sources]
    if len(names) != len(set(names)):
        raise ValueError("duplicate registry identity")
    if any(not s.name or not s.official_domain or not s.seed_urls for s in sources):
        raise ValueError("registry source missing required identity/evidence seed")
    return sources
