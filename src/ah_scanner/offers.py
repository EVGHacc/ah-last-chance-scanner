"""Momentopname van alle geldende 70%-aanbiedingen en het verschil met de vorige mail.

Zuivere logica, geen I/O. Een aanbieding is uniek per winkel, product en einddatum van de korting.
Een winkel die in deze scan niet gelezen is, telt niet als "aanbieding eraf": de vorige bekende
aanbiedingen van die winkel blijven staan (``stale``).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from ah_scanner.models import Item, ScanResult

Snapshot = dict[str, dict]  # sleutel -> {"store_id", "store", "item": {...}}


@dataclass(frozen=True)
class Offer:
    store_id: int
    store: str
    item: Item
    key: str
    is_new: bool = False
    stale: bool = False  # winkel in deze scan niet gelezen; laatst bekende stand


def key_for(store_id: int, item: Item) -> str:
    return f"{store_id}|{item.product_id}|{item.expires}"


def to_entry(offer: Offer) -> dict:
    return {"store_id": offer.store_id, "store": offer.store, "item": asdict(offer.item)}


def from_entry(key: str, entry: dict, *, stale: bool = False) -> Offer:
    return Offer(entry["store_id"], entry["store"], Item(**entry["item"]), key, stale=stale)


def snapshot_of(offers: list[Offer]) -> Snapshot:
    return {o.key: to_entry(o) for o in offers}


def build_current(scan: ScanResult, previous: Snapshot) -> tuple[list[Offer], list[str]]:
    """(alle geldende aanbiedingen op winkelvolgorde en titel, namen van niet-gelezen winkels)."""
    offers: list[Offer] = []
    unread: list[str] = []
    for store in scan.stores:
        if store.fetched:
            for item in store.meat70:
                offers.append(
                    Offer(store.store_id, store.store, item, key_for(store.store_id, item))
                )
            continue
        unread.append(store.store)
        offers += [
            from_entry(key, entry, stale=True)
            for key, entry in previous.items()
            if entry["store_id"] == store.store_id
        ]
    order = {s.store_id: n for n, s in enumerate(scan.stores)}
    offers.sort(key=lambda o: (order.get(o.store_id, 99), o.item.title.casefold(), o.key))
    return offers, unread


def diff(offers: list[Offer], previous: Snapshot) -> tuple[list[Offer], list[Offer]]:
    """(nieuwe aanbiedingen gemarkeerd als nieuw, verdwenen aanbiedingen uit de vorige mail)."""
    added = [
        Offer(o.store_id, o.store, o.item, o.key, is_new=True, stale=o.stale)
        for o in offers
        if o.key not in previous
    ]
    current_keys = {o.key for o in offers}
    removed = [from_entry(k, e) for k, e in previous.items() if k not in current_keys]
    return added, removed


def mark_new(offers: list[Offer], added: list[Offer]) -> list[Offer]:
    new_keys = {o.key for o in added}
    return [
        Offer(o.store_id, o.store, o.item, o.key, is_new=o.key in new_keys, stale=o.stale)
        for o in offers
    ]
