import { isScanSlot, scheduledAt } from "./slots.js";

const RETRY_DELAYS_MS = [0, 1000, 3000];
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function log(level, message, fields = {}) {
  console.log(JSON.stringify({ level, message, ...fields }));
}

/**
 * Start de scan-workflow. Herhaalt alleen bij tijdelijke fouten (429, 5xx, netwerk);
 * andere fouten (bijv. 401/403/404/422) stoppen direct. Het token wordt nooit gelogd.
 */
export async function dispatch(env, scheduled, fetchFn = fetch, wait = sleep) {
  const url = `https://api.github.com/repos/${env.GITHUB_REPO}/actions/workflows/${env.WORKFLOW_FILE}/dispatches`;
  const body = JSON.stringify({ ref: env.GITHUB_REF, inputs: { scheduled_at: scheduled } });
  let lastStatus = 0;
  for (const delay of RETRY_DELAYS_MS) {
    if (delay) await wait(delay);
    try {
      const response = await fetchFn(url, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${env.GITHUB_TOKEN}`,
          Accept: "application/vnd.github+json",
          "X-GitHub-Api-Version": "2022-11-28",
          "User-Agent": "ah-scan-trigger",
          "Content-Type": "application/json",
        },
        body,
      });
      lastStatus = response.status;
      if (response.status === 204) return { ok: true, status: 204 };
      if (response.status !== 429 && response.status < 500) break;
    } catch {
      lastStatus = 0;
    }
  }
  return { ok: false, status: lastStatus };
}

export default {
  async scheduled(controller, env) {
    if (!isScanSlot(controller.scheduledTime)) {
      log("info", "skip: geen scanmoment", { scheduledTime: controller.scheduledTime });
      return;
    }
    const scheduled = scheduledAt(controller.scheduledTime);
    const result = await dispatch(env, scheduled);
    log(result.ok ? "info" : "error", result.ok ? "dispatched" : "dispatch failed", {
      scheduled_at: scheduled,
      status: result.status,
    });
    if (!result.ok) throw new Error(`dispatch failed (HTTP ${result.status})`);
  },
};
