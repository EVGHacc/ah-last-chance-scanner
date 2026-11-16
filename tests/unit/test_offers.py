from ah_scanner import offers
from ah_scanner.models import OK, STORES, Item, ScanResult, StoreResult


def item(pid, title="Gehakt", expires="2026-11-16", stock=2):
    return Item(pid, title, "AH", "500 g", "Vlees", 70.0, stock, "5.00", "1.50", expires)


def store(store_id, items=(), fetched=True):
    name = dict(STORES)[store_id]
    return StoreResult(store_id, name, fetched, len(items), tuple(items), tuple(items))


def scan(*stores):
    return ScanResult("s", "t", "c", 0, False, OK, tuple(stores))


def five(**by_store):
    return [store(sid, by_store.get(str(sid), ())) for sid, _ in STORES]


def test_build_current_sorteert_per_winkel_op_hoogste_voorraad_dan_titel():
    s = scan(
        *five(
            **{
                "1348": [
                    item(2, "Zeta", stock=2),
                    item(3, "Alfa", stock=2),
                    item(4, "Mid", stock=9),
                ],
                "1463": [item(1, "Beta", stock=1), item(5, "Gamma", stock=30)],
            }
        )
    )
    current, _ = offers.build_current(s, {})
    # winkelvolgorde blijft leidend (1463 vóór 1348); daarbinnen hoogste voorraad eerst
    assert [o.item.title for o in current] == ["Gamma", "Beta", "Mid", "Alfa", "Zeta"]


def test_sortering_is_stabiel_bij_gelijke_voorraad_en_met_ontbrekende_voorraad():
    s = scan(
        *five(**{"1463": [item(2, "b", stock=None), item(1, "a", stock=0), item(3, "c", stock=0)]})
    )
    current, _ = offers.build_current(s, {})
    assert [o.item.title for o in current] == ["a", "b", "c"]


def test_laatst_bekende_winkel_wordt_ook_op_voorraad_gesorteerd():
    first, _ = offers.build_current(
        scan(*five(**{"1348": [item(1, "Laag", stock=1), item(2, "Hoog", stock=8)]})), {}
    )
    prev = offers.snapshot_of(first)
    stores = [store(sid, fetched=sid != 1348) for sid, _ in STORES]
    now, _ = offers.build_current(scan(*stores), prev)
    assert [o.item.title for o in now] == ["Hoog", "Laag"] and all(o.stale for o in now)


def test_build_current_sorteert_op_winkelvolgorde_en_titel():
    s = scan(*five(**{"1348": [item(2, "Zeta"), item(3, "Alfa")], "1463": [item(1, "Beta")]}))
    current, unread = offers.build_current(s, {})
    assert [o.item.title for o in current] == ["Beta", "Alfa", "Zeta"]  # gelijke voorraad: titel
    assert unread == []


def test_key_is_per_winkel_product_en_einddatum():
    a, b = item(1), item(1, expires="2026-11-17")
    assert offers.key_for(1463, a) != offers.key_for(1348, a)
    assert offers.key_for(1463, a) != offers.key_for(1463, b)


def test_diff_nieuw_en_verdwenen():
    first, _ = offers.build_current(scan(*five(**{"1463": [item(1), item(2)]})), {})
    prev = offers.snapshot_of(first)
    now, _ = offers.build_current(scan(*five(**{"1463": [item(2), item(3)]})), prev)
    added, removed = offers.diff(now, prev)
    assert [o.item.product_id for o in added] == [3] and all(o.is_new for o in added)
    assert [o.item.product_id for o in removed] == [1]


def test_ongewijzigd_geeft_geen_verschil():
    first, _ = offers.build_current(scan(*five(**{"1463": [item(1)]})), {})
    prev = offers.snapshot_of(first)
    now, _ = offers.build_current(scan(*five(**{"1463": [item(1)]})), prev)
    assert offers.diff(now, prev) == ([], [])


def test_niet_gelezen_winkel_houdt_laatst_bekende_aanbod_en_telt_niet_als_eraf():
    first, _ = offers.build_current(scan(*five(**{"1348": [item(7)]})), {})
    prev = offers.snapshot_of(first)
    stores = [store(sid, fetched=sid != 1348) for sid, _ in STORES]
    now, unread = offers.build_current(scan(*stores), prev)
    assert unread == ["AH Zandvoortselaan"]
    assert [o.item.product_id for o in now] == [7] and now[0].stale
    assert offers.diff(now, prev) == ([], [])


def test_roundtrip_snapshot_bewaart_alle_itemvelden():
    first, _ = offers.build_current(scan(*five(**{"1135": [item(5, "Kip")]})), {})
    restored = offers.from_entry(first[0].key, offers.to_entry(first[0]))
    assert restored.item == first[0].item and restored.store_id == 1135


def test_mark_new():
    now, _ = offers.build_current(scan(*five(**{"1463": [item(1), item(2)]})), {})
    marked = offers.mark_new(now, [now[1]])
    assert [o.is_new for o in marked] == [False, True]
