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
