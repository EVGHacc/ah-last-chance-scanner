import {
  EXPORT_CRON,
  REPORT_CRON,
  isExportMoment,
  isReportMoment,
  isScanSlot,
  scheduledAt,
} from "./slots.js";

const RETRY_DELAYS_MS = [0, 1000, 3000];
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function log(level, message, fields = {}) {
  console.log(JSON.stringify({ level, message, ...fields }));
}

/**
 * Start een workflow via workflow_dispatch. Herhaalt alleen bij tijdelijke fouten (429, 5xx,
 * netwerk); andere fouten (bijv. 401/403/404/422) stoppen direct. Het token wordt nooit gelogd.
 */
export async function dispatchWorkflow(env, workflowFile, inputs, fetchFn = fetch, wait = sleep) {
  const url = `https://api.github.com/repos/${env.GITHUB_REPO}/actions/workflows/${workflowFile}/dispatches`;
  const payload = { ref: env.GITHUB_REF };
  if (inputs) payload.inputs = inputs;
  const body = JSON.stringify(payload);
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

/** Start de scan-workflow voor een scanmoment. */
export function dispatch(env, scheduled, fetchFn = fetch, wait = sleep) {
  return dispatchWorkflow(env, env.WORKFLOW_FILE, { scheduled_at: scheduled }, fetchFn, wait);
}

async function report(result, what, fields) {
  log(result.ok ? "info" : "error", result.ok ? `${what} dispatched` : `${what} dispatch failed`, {
    ...fields,
    status: result.status,
  });
  if (!result.ok) throw new Error(`${what} dispatch failed (HTTP ${result.status})`);
}

export default {
  async scheduled(controller, env) {
    if (controller.cron === EXPORT_CRON) {
      // De cron vuurt in twee UTC-uren; alleen 22:45 Amsterdam start de export.
      if (!isExportMoment(controller.scheduledTime)) {
        log("info", "skip: geen exportmoment", { scheduledTime: controller.scheduledTime });
        return;
      }
      const result = await dispatchWorkflow(env, env.EXPORT_WORKFLOW_FILE, null);
      await report(result, "export", { scheduled_at: scheduledAt(controller.scheduledTime) });
      return;
    }
    if (controller.cron === REPORT_CRON) {
      // De cron vuurt in twee UTC-uren; alleen zondag 23:15 Amsterdam start het weekrapport.
      if (!isReportMoment(controller.scheduledTime)) {
        log("info", "skip: geen rapportmoment", { scheduledTime: controller.scheduledTime });
        return;
      }
      const result = await dispatchWorkflow(env, env.REPORT_WORKFLOW_FILE, null);
      await report(result, "report", { scheduled_at: scheduledAt(controller.scheduledTime) });
      return;
    }
    if (!isScanSlot(controller.scheduledTime)) {
      log("info", "skip: geen scanmoment", { scheduledTime: controller.scheduledTime });
      return;
    }
    const scheduled = scheduledAt(controller.scheduledTime);
    await report(await dispatch(env, scheduled), "scan", { scheduled_at: scheduled });
  },
};
