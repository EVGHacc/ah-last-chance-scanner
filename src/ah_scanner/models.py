"""Datamodellen voor een scan. Geen I/O."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

STORES: tuple[tuple[int, str], ...] = (
    (1463, "AH Blekersvaartweg"),
    (1348, "AH Zandvoortselaan"),
    (1135, "AH Casablancastraat"),
    (4046, "AH Clothildestraat"),
    (8728, "AH Westergracht"),
)

# Scanstatussen. Alleen OK en OK_ZERO_ROWS tellen als geslaagd.
OK, OK_ZERO_ROWS, INCOMPLETE, FAILED = "OK", "OK_ZERO_ROWS", "INCOMPLETE", "FAILED"


@dataclass(frozen=True)
class Item:
    product_id: int | None
    title: str
    brand: str
    size: str
    category: str
    discount_pct: float
    stock: float
    price_was: str | None
    price_now: str | None
    expires: str | None


@dataclass(frozen=True)
class StoreResult:
    store_id: int
    store: str
    fetched: bool
    total_items: int = 0
    meat_items: tuple[Item, ...] = ()  # alle Vlees-items
    meat70: tuple[Item, ...] = ()  # Vlees met korting >= 70%
    error: str = ""  # stabiele code, nooit een response-body


@dataclass(frozen=True)
class ScanResult:
    scheduled_at: str
    started_at: str
    completed_at: str
    delay_seconds: int
    late: bool
    status: str
    stores: tuple[StoreResult, ...] = field(default_factory=tuple)

    @property
    def valid(self) -> bool:
        return self.status in (OK, OK_ZERO_ROWS)

    def to_dict(self) -> dict:
        data = asdict(self)
        data["valid"] = self.valid
        return data
