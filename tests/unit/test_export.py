import csv
import json

from ah_scanner import cli, export


def v2_record(slot="17:30", day="2026-11-16", items=None, fetched=True, late=False):
    items = items if items is not None else [
        {"product_id": 1, "title": "Kip", "brand": "AH", "size": "300 g", "category": "Vlees",
         "discount_pct": 70.0, "stock": 2.0, "price_was": "5.00", "price_now": "1.50",
         "expires": day},
        {"product_id": 2, "title": "Worst", "brand": "AH", "size": "250 g", "category": "Vlees",
         "discount_pct": 40.0, "stock": 1.0, "price_was": "3.00", "price_now": "1.80",
         "expires": day},
    ]  # fmt: skip
    store = {
        "store_id": 1463, "store": "AH Test", "fetched": fetched, "total_items": 99,
        "meat_items": items, "meat70": [
            i for i in items
            if isinstance(i["discount_pct"], int | float) and i["discount_pct"] >= 70
        ],
        "error": "" if fetched else "UPSTREAM_HTTP_500",
    }  # fmt: skip
    stamp = f"{day}T{slot}:00+01:00"
    return {
        "scheduled_at": stamp, "started_at": stamp, "completed_at": stamp, "delay_seconds": 50,
        "late": late, "status": "OK", "valid": True, "stores": [store],
    }  # fmt: skip


def v1_record(slot="17:42", day="2026-10-06", with_items=True, delay=100):
    store = {"storeId": 1348, "store": "AH Zandvoortselaan", "fetched": True}
    if with_items:
        store |= {
            "totalBargainItems": 120, "meatItems": 1, "meat70Items": 1,
            "items": [{
                "productId": 9, "title": "Gehakt", "brand": "AH", "size": "500 g",
                "category": "Vlees", "discountPct": 70, "stock": 3, "priceWas": "4.00",
                "priceNow": "1.20", "markdownExpirationDate": day,
            }],
        }  # fmt: skip
    return {
        "schemaVersion": 5, "date": day, "scheduledSlot": slot,
        "scheduledAt": f"{day}T{slot}:00+02:00", "startedAt": f"{day}T{slot}:30+02:00",
        "status": "OK", "valid": True, "delaySeconds": delay, "stores": [store],
    }  # fmt: skip


def write_jsonl(path, records, extra_lines=()):
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(r) for r in records] + list(extra_lines)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def test_canonical_5min_raster_en_slot():
    assert export.slot_of("2026-11-16T17:35:00+01:00") == "17:35"
    assert export.canonical_5min("17:30") and export.canonical_5min("22:30")
    assert not export.canonical_5min("17:42") and not export.canonical_5min("22:35")
    assert not export.canonical_5min("") and not export.canonical_5min("xx:yy")


def test_v2_rijen_per_scan_winkel_en_item():
    scans, items = export.rows_for(v2_record())
    assert len(scans) == 1 and len(items) == 2
    assert scans[0]["meat_items"] == 2 and scans[0]["meat70_items"] == 1
    assert scans[0]["canonical_5min"] is True and scans[0]["source"] == "v2"
    assert [i["is_70"] for i in items] == [True, False] and items[0]["discount_pct"] == 70.0


def test_v1_rijen_met_andere_veldnamen_en_niet_canonical_slot():
    scans, items = export.rows_for(v1_record())
    assert scans[0]["source"] == "v1" and scans[0]["canonical_5min"] is False
    assert scans[0]["late"] is False and scans[0]["total_items"] == 120
    assert items[0]["product_id"] == 9 and items[0]["is_70"] is True
    assert items[0]["expires"] == "2026-10-06" and items[0]["price_now"] == "1.20"


def test_v1_late_en_vroege_record_zonder_items():
    assert export.rows_for(v1_record(delay=241))[0][0]["late"] is True
    scans, items = export.rows_for(v1_record(with_items=False))
    assert len(scans) == 1 and items == [] and scans[0]["meat_items"] == 0


def test_onbekend_formaat_en_onleesbare_waarde():
    assert export.rows_for({"iets": 1}) is None
    scans, items = export.rows_for(v2_record(items=[{"product_id": 3, "discount_pct": "n.v.t."}]))
    assert items[0]["discount_pct"] is None and items[0]["is_70"] is False


def test_uitgevallen_winkel_geeft_scanrij_met_fout_en_geen_items():
    scans, items = export.rows_for(v2_record(items=[], fetched=False))
    assert scans[0]["fetched"] is False and scans[0]["error"] == "UPSTREAM_HTTP_500" and items == []


def test_export_all_schrijft_csv_per_dag_voor_v1_en_v2_en_slaat_rommel_over(tmp_path):
    root, out = tmp_path / "data", tmp_path / "out"
    write_jsonl(
        root / "scans" / "2026-11-16.jsonl",
        [v2_record(), v2_record("17:35")],
        extra_lines=["{kapot", "[1, 2]"],
    )
    write_jsonl(root / "legacy" / "2026-10-06.jsonl", [v1_record(), {"onbekend": True}])
    stats = export.export_all(root, out)
    assert stats == {"days": 2, "scan_rows": 3, "item_rows": 5, "skipped": 3}
    assert len(read_csv(out / "items" / "2026-11-16.csv")) == 4
    assert read_csv(out / "scans" / "2026-10-06.csv")[0]["source"] == "v1"
    header = (out / "items" / "2026-11-16.csv").read_text(encoding="utf-8-sig").splitlines()[0]
    assert header.split(",") == export.ITEM_COLUMNS
    assert not (out / "scans_all.csv").exists()


def test_export_is_idempotent_en_combined_bevat_alles(tmp_path):
    root, out = tmp_path / "data", tmp_path / "out"
    write_jsonl(root / "scans" / "2026-11-16.jsonl", [v2_record()])
    write_jsonl(root / "legacy" / "2026-10-06.jsonl", [v1_record()])
    export.export_all(root, out, combined=True)
    first = (out / "items_all.csv").read_bytes()
    export.export_all(root, out, combined=True)
    assert (out / "items_all.csv").read_bytes() == first
    assert [r["date"] for r in read_csv(out / "items_all.csv")] == [
        "2026-10-06", "2026-11-16", "2026-11-16"
    ]  # fmt: skip


def test_dag_zonder_items_geeft_wel_lege_itemsbestand_met_header(tmp_path):
    root, out = tmp_path / "data", tmp_path / "out"
    write_jsonl(
        root / "legacy" / "2026-09-12.jsonl", [v1_record(day="2026-09-12", with_items=False)]
    )
    export.export_all(root, out)
    assert read_csv(out / "items" / "2026-09-12.csv") == []
    assert len(read_csv(out / "scans" / "2026-09-12.csv")) == 1


def test_cli_export_commando(tmp_path, capsys):
    root, out = tmp_path / "data", tmp_path / "out"
    write_jsonl(root / "scans" / "2026-11-16.jsonl", [v2_record()])
    assert cli.main(["export", "--data-root", str(root), "--out", str(out), "--combined"]) == 0
    assert "EXPORT days=1 scan_rows=1 item_rows=2 skipped=0" in capsys.readouterr().out
    assert (out / "scans_all.csv").exists()


def test_item_rijen_hebben_kwaliteitskolommen():
    _, items = export.rows_for(v2_record())
    for row in items:
        assert {"popular", "total_grams", "enough_for_four"} <= set(row)
    assert set(export.ITEM_COLUMNS) >= {"popular", "total_grams", "enough_for_four"}
