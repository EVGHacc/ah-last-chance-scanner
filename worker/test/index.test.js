import assert from "node:assert/strict";
import test from "node:test";
import worker, { dispatch } from "../src/index.js";

const env = {
  GITHUB_REPO: "o/r",
  WORKFLOW_FILE: "scan.yml",
  GITHUB_REF: "main",
  GITHUB_TOKEN: "secret-token",
};
const noWait = async () => {};
const respond = (...statuses) => {
  const calls = [];
  const fn = async (url, init) => {
    calls.push({ url, init });
    return { status: statuses[Math.min(calls.length - 1, statuses.length - 1)] };
  };
  fn.calls = calls;
  return fn;
};

test("dispatch stuurt ref en scheduled_at", async () => {
  const f = respond(204);
  const result = await dispatch(env, "2026-11-15T16:30:00.000Z", f, noWait);
  assert.deepEqual(result, { ok: true, status: 204 });
  assert.equal(f.calls[0].url, "https://api.github.com/repos/o/r/actions/workflows/scan.yml/dispatches");
  assert.deepEqual(JSON.parse(f.calls[0].init.body), {
    ref: "main",
    inputs: { scheduled_at: "2026-11-15T16:30:00.000Z" },
  });
  assert.equal(f.calls[0].init.headers.Authorization, "Bearer secret-token");
});

test("tijdelijke fout wordt herhaald, daarna succes", async () => {
  const f = respond(503, 502, 204);
  assert.equal((await dispatch(env, "x", f, noWait)).ok, true);
  assert.equal(f.calls.length, 3);
});

test("permanente fout (401) wordt niet herhaald", async () => {
  const f = respond(401);
  assert.deepEqual(await dispatch(env, "x", f, noWait), { ok: false, status: 401 });
  assert.equal(f.calls.length, 1);
});

test("netwerkfout is begrensd tot 3 pogingen", async () => {
  let n = 0;
  const f = async () => {
    n += 1;
    throw new Error("netwerk");
  };
  assert.deepEqual(await dispatch(env, "x", f, noWait), { ok: false, status: 0 });
  assert.equal(n, 3);
});

test("scheduled: buiten een slot gebeurt er niets", async () => {
  const original = globalThis.fetch;
  globalThis.fetch = async () => assert.fail("mag niet dispatchen");
  try {
    await worker.scheduled({ scheduledTime: Date.parse("2026-11-15T12:00:00Z") }, env);
  } finally {
    globalThis.fetch = original;
  }
});

test("scheduled: mislukte dispatch gooit een fout en lekt geen token", async () => {
  const original = globalThis.fetch;
  const logs = [];
  const log = console.log;
  console.log = (line) => logs.push(line);
  globalThis.fetch = async () => ({ status: 403 });
  try {
    await assert.rejects(
      worker.scheduled({ scheduledTime: Date.parse("2026-11-15T16:30:00Z") }, env),
      /HTTP 403/,
    );
  } finally {
    globalThis.fetch = original;
    console.log = log;
  }
  assert.ok(logs.every((l) => !l.includes("secret-token")));
});

// ---- dagelijkse export (tweede cron) ----

import { EXPORT_CRON } from "../src/slots.js";

const exportEnv = { ...env, EXPORT_WORKFLOW_FILE: "export.yml" };

async function runCron(cron, iso, fetchImpl, environment = exportEnv) {
  const original = globalThis.fetch;
  const calls = [];
  globalThis.fetch = async (url, init) => {
    calls.push({ url, init });
    return fetchImpl ? fetchImpl(url, init) : { status: 204 };
  };
  const log = console.log;
  console.log = () => {};
  try {
    await worker.scheduled({ cron, scheduledTime: Date.parse(iso) }, environment);
  } finally {
    globalThis.fetch = original;
    console.log = log;
  }
  return calls;
}

test("export-cron: 22:45 Amsterdam in wintertijd (21:45Z) start export.yml zonder inputs", async () => {
  const calls = await runCron(EXPORT_CRON, "2026-11-16T21:45:00Z");
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, "https://api.github.com/repos/o/r/actions/workflows/export.yml/dispatches");
  assert.deepEqual(JSON.parse(calls[0].init.body), { ref: "main" });
});

test("export-cron: 22:45 Amsterdam in zomertijd (20:45Z) start export.yml", async () => {
  const calls = await runCron(EXPORT_CRON, "2026-07-15T20:45:00Z");
  assert.equal(calls.length, 1);
});

test("export-cron: het andere UTC-uur is geen exportmoment", async () => {
  assert.equal((await runCron(EXPORT_CRON, "2026-11-16T20:45:00Z")).length, 0); // 21:45 lokaal
  assert.equal((await runCron(EXPORT_CRON, "2026-07-15T21:45:00Z")).length, 0); // 23:45 lokaal
});

test("export-cron: precies een export per dag, ook rond DST-wissels", async () => {
  for (const day of ["2026-10-24", "2026-10-25", "2026-10-26", "2027-03-27", "2027-03-28", "2027-03-29"]) {
    let hits = 0;
    for (const hour of [20, 21]) {
      hits += (await runCron(EXPORT_CRON, `${day}T${String(hour).padStart(2, "0")}:45:00Z`)).length;
    }
    assert.equal(hits, 1, `${day}: ${hits} exports`);
  }
});

test("scan-cron start nooit de export en export-cron nooit een scan", async () => {
  // 21:45Z is in de winter 22:45 lokaal: geen scanmoment voor de scan-cron
  assert.equal((await runCron("*/5 15-21 * * *", "2026-11-16T21:45:00Z")).length, 0);
  const scan = await runCron("*/5 15-21 * * *", "2026-11-16T16:30:00Z");
  assert.equal(scan.length, 1);
  assert.match(scan[0].url, /scan\.yml\/dispatches$/);
  assert.deepEqual(JSON.parse(scan[0].init.body).inputs, { scheduled_at: "2026-11-16T16:30:00.000Z" });
});

test("export-cron: mislukte dispatch gooit een fout en lekt geen token", async () => {
  const logs = [];
  const log = console.log;
  const original = globalThis.fetch;
  console.log = (line) => logs.push(line);
  globalThis.fetch = async () => ({ status: 403 });
  try {
    await assert.rejects(
      worker.scheduled({ cron: EXPORT_CRON, scheduledTime: Date.parse("2026-11-16T21:45:00Z") }, exportEnv),
      /export dispatch failed \(HTTP 403\)/,
    );
  } finally {
    globalThis.fetch = original;
    console.log = log;
  }
  assert.ok(logs.every((l) => !l.includes("secret-token")));
});
