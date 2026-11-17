"""Kwaliteit van een aanbieding voor een gezin van vier personen.

Twee criteria, beide uit de opgeslagen gegevens (er wordt niets geschat):

- *populair*: de titel bevat een van de producten die het gezin graag eet (``POPULAR``);
- *genoeg voor vier*: gewicht per pak maal voorraad is minimaal ``FOUR_PERSON_GRAMS``
  (500 g, 125 g per persoon). Twee of meer pakken van hetzelfde product tellen dus samen.

Een *topaanbieding* is populair én genoeg voor vier personen.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

FOUR_PERSON_GRAMS = 500.0

_MULTI = re.compile(r"(\d+)\s*[x×]\s*(\d+(?:[.,]\d+)?)\s*(kg|g)\b")
_SINGLE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(kg|g)\b")

# Naam in de rapporten en het patroon dat in de (kleine letter) titel moet voorkomen.
POPULAR = [
    ("kipkluifjes", r"kluif"),
    ("gehakt", r"gehakt|hamburger"),
    ("kipfilet", r"kipfilet"),
    ("worst", r"worst"),
    ("biefstuk", r"biefstuk"),
    ("entrecote", r"entrec[oô]te"),
    ("drumsticks", r"drumstick"),
    ("speklappen", r"speklap"),
]


def grams_of(size: str | None) -> float | None:
    """Gewicht per pak in gram uit tekst als '500 g', 'ca. 1,2 kg' of '2 x 125 g'; anders None."""
    text = (size or "").lower()
    if multi := _MULTI.search(text):
        count, amount, unit = int(multi[1]), float(multi[2].replace(",", ".")), multi[3]
        return count * amount * (1000 if unit == "kg" else 1)
    if single := _SINGLE.search(text):
        return float(single[1].replace(",", ".")) * (1000 if single[2] == "kg" else 1)
    return None


def popular_kind(title: str | None) -> str:
    """Naam van het populaire product dat in de titel zit, of '' als het er geen is."""
    lowered = (title or "").lower()
    for name, pattern in POPULAR:
        if re.search(pattern, lowered):
            return name
    return ""


@dataclass(frozen=True)
class Quality:
    popular: str  # populaire soort, '' als niet populair
    pack_grams: float | None
    stock: float
    total_grams: float | None
    enough_for_four: bool | None  # None: gewicht onbekend

    @property
    def top(self) -> bool:
        return bool(self.popular) and self.enough_for_four is True

    @property
    def needs_several_packs(self) -> bool:
        """Eén pak is te weinig, maar de voorraad bij elkaar is genoeg voor vier."""
        pack = self.pack_grams
        return bool(pack is not None and pack < FOUR_PERSON_GRAMS and self.enough_for_four)


def assess(title: str | None, size: str | None, stock: object) -> Quality:
    try:
        count = float(stock)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        count = 0.0
    pack = grams_of(size)
    total = None if pack is None else pack * count
    return Quality(
        popular_kind(title),
        pack,
        count,
        total,
        None if total is None else total >= FOUR_PERSON_GRAMS,
    )
