from dataclasses import dataclass
from enum import Enum

class Coverage(str, Enum):
    UNPROVEN = "unproven"
    VERIFIED_COMPLETE = "verified_complete"

@dataclass(frozen=True)
class Source:
    kind: str
    name: str
    official_domain: str
    seed_urls: tuple[str, ...]
    allowed_domains: tuple[str, ...] = ()

@dataclass(frozen=True)
class InventoryProof:
    source: Source
    coverage: Coverage
    unique_jobs: int = 0
    authoritative_total: int | None = None
    exhausted: bool = False
    evidence_kind: str | None = None

    def validate(self) -> None:
        if self.coverage is Coverage.VERIFIED_COMPLETE:
            if not self.exhausted:
                raise ValueError("verified_complete requires exhausted inventory")
            if self.authoritative_total is not None and self.unique_jobs != self.authoritative_total:
                raise ValueError("verified_complete count mismatch")
            if self.authoritative_total is None and self.evidence_kind not in {"pagination_exhausted","official_complete_payload"}:
                raise ValueError("verified_complete requires total or exhaustive official payload proof")
