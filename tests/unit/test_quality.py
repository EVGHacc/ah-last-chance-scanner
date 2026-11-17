import pytest

from ah_scanner import quality
from ah_scanner.quality import assess, grams_of, popular_kind


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("AH Kipkluifjes", "kipkluifjes"),
        ("AH Rundergehakt", "gehakt"),
        ("AH Runder hamburger 4 stuks", "gehakt"),
        ("AH Scharrel kipfilet", "kipfilet"),
        ("Gelderse rookworst", "worst"),
        ("AH Biefstuk", "biefstuk"),
        ("Entrecôte", "entrecote"),
        ("Kip drumsticks", "drumsticks"),
        ("Speklappen naturel", "speklappen"),
        ("Varkenshaas", ""),
        ("", ""),
        (None, ""),
    ],
)
def test_popular_kind(title, expected):
    assert popular_kind(title) == expected


def test_een_pak_is_genoeg_voor_vier_vanaf_500_gram():
    assert assess("Gehakt", "500 g", 1).enough_for_four is True
    assert assess("Gehakt", "499 g", 1).enough_for_four is False


def test_twee_pakken_samen_tellen_en_dat_wordt_gemeld():
    two = assess("Kipfilet", "250 g", 2)
    assert two.total_grams == 500 and two.enough_for_four is True
    assert two.needs_several_packs is True and two.top is True
    one = assess("Kipfilet", "250 g", 1)
    assert one.enough_for_four is False and one.needs_several_packs is False and not one.top
    assert assess("Kipfilet", "600 g", 1).needs_several_packs is False


def test_topaanbieding_vereist_populair_en_genoeg_voor_vier():
    assert assess("Varkenshaas", "1 kg", 1).top is False  # genoeg, niet populair
    assert assess("Kipkluifjes", "300 g", 1).top is False  # populair, te weinig
    assert assess("Kipkluifjes", "1 kg", 1).top is True


def test_onbekend_gewicht_en_ongeldige_voorraad():
    q = assess("Gehakt", "per stuk", 3)
    assert q.total_grams is None and q.enough_for_four is None and not q.top
    assert assess("Gehakt", "500 g", "x").total_grams == 0
    assert grams_of("2 x 125 g") == 250 and quality.FOUR_PERSON_GRAMS == 500
