import csv
from pathlib import Path

from .models import Source


def _split_optional(value: str | None) -> tuple[str, ...]:
    return tuple(x.strip() for x in (value or "").split(";") if x.strip())


def load_registry(path: str | Path) -> list[Source]:
    with Path(path).open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh, delimiter="\t"))
    sources = [
        Source(
            kind=(row["kind"] or "").strip(),
            name=(row["name"] or "").strip(),
            official_domain=(row["official_domain"] or "").strip(),
            seed_urls=_split_optional(row["seed_urls"]),
            no_public_hint=(row["no_public_hint"] or "").strip() == "1",
            allowed_domains=_split_optional(row["allowed_domains"]),
        )
        for row in rows
    ]
    names=[(s.kind,s.name) for s in sources]
    if len(names) != len(set(names)):
        raise ValueError("duplicate registry identity")
    if any(not s.name or not s.official_domain or not s.seed_urls for s in sources):
        raise ValueError("registry source missing required identity/evidence seed")
    return sources
