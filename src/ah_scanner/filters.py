"""Filterregels: categorie exact 'Vlees' en korting >= 70%."""

from __future__ import annotations

from collections.abc import Iterable

from ah_scanner.models import Item

CATEGORY = "Vlees"
MIN_DISCOUNT = 70.0


def _num(value: object) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0


def to_item(row: dict) -> Item:
    markdown = row.get("markdown") or {}
    product = row.get("product") or {}
    price = row.get("bargainPrice") or {}
    return Item(
        product_id=product.get("id"),
        title=str(product.get("title") or ""),
        brand=str(product.get("brand") or ""),
        size=str(product.get("salesUnitSize") or ""),
        category=str(row.get("categoryTitle") or ""),
        discount_pct=_num(markdown.get("markdownPercentage")),
        stock=_num(row.get("stock")),
        price_was=price.get("priceWas"),
        price_now=price.get("priceNow"),
        expires=markdown.get("markdownExpirationDate"),
    )


def is_meat(row: dict) -> bool:
    """Exacte categorie 'Vlees' (hoofdletterongevoelig); 'Vleeswaren' valt er dus buiten."""
    return str(row.get("categoryTitle") or "").strip().casefold() == CATEGORY.casefold()


def meat_items(rows: Iterable[dict]) -> list[Item]:
    return [to_item(r) for r in rows if is_meat(r)]


def meat70(items: Iterable[Item]) -> list[Item]:
    return [i for i in items if i.discount_pct >= MIN_DISCOUNT]
