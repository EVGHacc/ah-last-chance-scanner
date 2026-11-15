import assert from "node:assert/strict";
import test from "node:test";
import { amsterdamMinutes, isScanSlot, scheduledAt } from "../src/slots.js";

const utc = (iso) => Date.parse(iso);

// Alle UTC-momenten van een dag (per 5 min) die als scanmoment tellen.
function slotsOn(day) {
  const out = [];
  for (let ms = utc(`${day}T00:00:00Z`); ms < utc(`${day}T00:00:00Z`) + 86400000; ms += 300000) {
    if (isScanSlot(ms)) out.push(ms);
  }
  return out;
}

test("winter: 17:30 Amsterdam = 16:30 UTC", () => {
  assert.equal(isScanSlot(utc("2026-11-15T16:30:00Z")), true);
  assert.equal(isScanSlot(utc("2026-11-15T15:30:00Z")), false);
});

test("zomer: 17:30 Amsterdam = 15:30 UTC", () => {
  assert.equal(isScanSlot(utc("2026-07-15T15:30:00Z")), true);
  assert.equal(isScanSlot(utc("2026-07-15T16:30:00Z")), true); // 18:30 lokaal, ook een slot
  assert.equal(isScanSlot(utc("2026-07-15T15:25:00Z")), false); // 17:25 lokaal
});

test("grenzen: 22:30 wel, 22:35 niet", () => {
  assert.equal(isScanSlot(utc("2026-11-15T21:30:00Z")), true);
  assert.equal(isScanSlot(utc("2026-11-15T21:35:00Z")), false);
});

for (const day of ["2026-11-15", "2026-07-15", "2026-10-25", "2027-03-28"]) {
  test(`61 slots op ${day} (ook rond DST)`, () => {
    assert.equal(slotsOn(day).length, 61);
  });
}

test("slots vallen binnen de cron-uren 15-21 UTC", () => {
  for (const day of ["2026-11-15", "2026-07-15", "2026-10-25", "2027-03-28"]) {
    for (const ms of slotsOn(day)) {
      const hour = new Date(ms).getUTCHours();
      assert.ok(hour >= 15 && hour <= 21, `${new Date(ms).toISOString()} buiten cron-venster`);
    }
  }
});

test("seconden en milliseconden worden genegeerd", () => {
  assert.equal(isScanSlot(utc("2026-11-15T16:30:42Z") + 123), true);
  assert.equal(scheduledAt(utc("2026-11-15T16:30:42Z") + 123), "2026-11-15T16:30:00.000Z");
});

test("amsterdamMinutes", () => {
  assert.equal(amsterdamMinutes(utc("2026-07-15T15:30:00Z")), 17 * 60 + 30);
});
