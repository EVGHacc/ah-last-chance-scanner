from dataclasses import dataclass
from enum import StrEnum


class Coverage(StrEnum):
    VERIFIED_COMPLETE = "verified_complete"
    VERIFIED_NO_PUBLIC_BOARD = "verified_no_public_board"
    PARTIAL = "partial"
    UNPROVEN = "unproven"
    TECHNICAL_FAILURE = "technical_failure"


@dataclass(frozen=True)
class Source:
    kind: str
    name: str
    official_domain: str
    seed_urls: tuple[str, ...]
    no_public_hint: bool
    allowed_domains: tuple[str, ...]


@dataclass(frozen=True)
class InventoryProof:
    source_name: str
    provider: str
    discovered: int
    unique: int
    authoritative_total: int | None
    exhausted: bool
    duplicate_count: int
    error: str | None = None

    @property
    def verified_complete(self) -> bool:
        if self.error or self.duplicate_count or self.discovered != self.unique:
            return False
        if self.authoritative_total is not None:
            return self.exhausted and self.unique == self.authoritative_total
        return self.exhausted
