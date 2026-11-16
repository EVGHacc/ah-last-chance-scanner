"""Verrijking van nieuwe 70%-producten: productfoto en bewaartekst ('Bewaren').

Het AH-schema is niet te inspecteren (introspectie staat uit) en het type van
``storage.instructions`` is onbekend. Daarom: foto en bewaartekst in aparte queries,
fouten zichtbaar in de log (alleen de eerste foutmelding, ingekort), en een mislukte
verrijking mag nooit een scan of mail blokkeren.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

from ah_scanner.models import Item

CACHE_FILE = "product_info.json"
MAX_PER_RUN = 40

IMAGE_QUERY = (
    "query ProductImage($productId: Int!) { product(id: $productId) { id "
    "imagePack { medium { url width height } } } }"
)
STORAGE_QUERY = (
    "query ProductStorage($productId: Int!) { product(id: $productId) { id "
    "tradeItem { storage { instructions lifeSpan } } } }"
)

QueryFn = Callable[[str, dict], tuple[int, dict]]  # (query, variables) -> (status, json)

JA, NEE, ONBEKEND = "ja", "nee", "onbekend"


@dataclass(frozen=True)
class Enrichment:
    image_url: str = ""
    storage: str = ""
    lifespan: str = ""

    @property
    def freeze(self) -> str:
        return classify_freeze(self.storage)


_FREEZE = re.compile(r"in\s?vries|in te vriezen|vriezen|vries\s.*\sin\b", re.I)
_NEGATION = re.compile(r"\bniet\b|\bgeen\b|\bnooit\b", re.I)
_REFREEZE = re.compile(r"ontdooid|opnieuw|weer\b|nogmaals|na het ontdooien", re.I)


def classify_freeze(text: str) -> str:
    """Ja/Nee/Onbekend op basis van de bewaartekst, per zin.

    Zinnen over opnieuw invriezen van ontdooid product ("niet opnieuw invriezen") zeggen niets
    over invriesbaarheid op de dag van aankoop en worden genegeerd. Een ontkenning wint van
    een bevestiging. De ruwe tekst blijft altijd zichtbaar in de mail.
    """
    verdict = ONBEKEND
    for sentence in re.split(r"(?<=[.!?])\s+|\n", text or ""):
        if not _FREEZE.search(sentence) or _REFREEZE.search(sentence):
            continue
        if _NEGATION.search(sentence):
            return NEE
        verdict = JA
    return verdict


def _text(value: object) -> str:
    """Tekst uit een string of lijst van strings; alles anders telt als leeg."""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        return " ".join(v.strip() for v in value if isinstance(v, str) and v.strip())
    return ""


def _error(data: dict) -> str:
    errors = data.get("errors")
    if not errors:
        return ""
    first = errors[0] if isinstance(errors, list) and errors else errors
    message = first.get("message") if isinstance(first, dict) else str(first)
    return re.sub(r"\s+", " ", str(message))[:160] or "onbekend"


def _product(data: dict) -> dict:
    return ((data.get("data") or {}).get("product")) or {}


def fetch_image(product_id: int, query: QueryFn) -> str | None:
    """URL van de foto, '' als er geen is, None bij een fout."""
    status, data = query(IMAGE_QUERY, {"productId": product_id})
    if status != 200 or _error(data):
        print(f"ENRICH_ERROR product={product_id} part=image http={status} msg={_error(data)}")
        return None
    packs = _product(data).get("imagePack") or []
    for pack in packs if isinstance(packs, list) else []:
        url = ((pack or {}).get("medium") or {}).get("url")
        if isinstance(url, str) and url.startswith("https://"):
            return url
    return ""


def fetch_storage(product_id: int, query: QueryFn) -> tuple[str, str] | None:
    """(bewaartekst, houdbaarheid), None bij een fout."""
    status, data = query(STORAGE_QUERY, {"productId": product_id})
    if status != 200 or _error(data):
        print(f"ENRICH_ERROR product={product_id} part=storage http={status} msg={_error(data)}")
        return None
    storage = ((_product(data).get("tradeItem")) or {}).get("storage") or {}
    return _text(storage.get("instructions")), _text(storage.get("lifeSpan"))


def load_cache(root: Path) -> dict[str, dict]:
    try:
        data = json.loads((root / CACHE_FILE).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_cache(root: Path, cache: dict[str, dict]) -> None:
    (root / CACHE_FILE).write_text(
        json.dumps(cache, ensure_ascii=False, sort_keys=True, indent=1) + "\n", encoding="utf-8"
    )


def enrich_items(
    items: Iterable[Item], query: QueryFn, root: Path, cap: int = MAX_PER_RUN
) -> dict[int, Enrichment]:
    """Verrijk unieke producten. Succesvolle delen worden gecachet (ook leeg); fouten niet."""
    cache = load_cache(root)
    ids = list(dict.fromkeys(i.product_id for i in items if isinstance(i.product_id, int)))
    result: dict[int, Enrichment] = {}
    changed = False
    for product_id in ids[:cap]:
        entry = cache.setdefault(str(product_id), {})
        if "image" not in entry and (image := fetch_image(product_id, query)) is not None:
            entry["image"], changed = image, True
        if "storage" not in entry and (found := fetch_storage(product_id, query)) is not None:
            entry["storage"], entry["lifespan"], changed = found[0], found[1], True
        result[product_id] = Enrichment(
            entry.get("image", ""), entry.get("storage", ""), entry.get("lifespan", "")
        )
    cache = {k: v for k, v in cache.items() if v}
    if changed:
        save_cache(root, cache)
    return result
