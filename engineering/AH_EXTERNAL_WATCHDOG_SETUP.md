# External AH watchdog setup (cron-job.org, free tier)

This is a **manual activation checklist**. No cron job or credential is created by merging this PR.

1. Merge only after all engineering checks and independent review pass.
2. In GitHub, create a fine-grained personal access token limited to repository
   `EVGHacc/ah-last-chance-scanner`, with **Actions: read/write** and
   **Contents: read**. Set a short expiry and rotate before expiry.
3. In cron-job.org, create an HTTPS job with the URL:
   `https://api.github.com/repos/EVGHacc/ah-last-chance-scanner/actions/workflows/external-recovery.yml/dispatches`
   Method: `POST`; schedule: every 2 minutes during 17:35–22:10
   **Europe/Amsterdam** (ensure DST-aware timezone selection).
4. Request headers: `Authorization: Bearer <TOKEN>`,
   `Accept: application/vnd.github+json`,
   `X-GitHub-Api-Version: 2022-11-28`,
   `Content-Type: application/json`.
   Body: `{"ref":"main"}`. Store the token in a protected header/secret field,
   **never in the URL or repository**. Confirm cron-job.org does not expose
   authorization headers in its logs or UI.
5. GitHub returns HTTP 204 for accepted dispatch. This only means the
   watchdog workflow was requested, **not** that the scanner recovered.
   Verify the resulting `AH external recovery entrypoint` run and
   `AH supervised evening session` runs in Actions.
6. Perform a controlled failure drill outside the critical production window
   (or using a mocked heartbeat), and independently verify that a missing
   heartbeat triggers at most one recovery, healthy scans do not trigger
   duplicate sessions, and no historical measurements are invented.
7. Monitor cron-job.org execution failures and token expiry. A failed
   external job must be surfaced separately from GitHub Actions health.

**Important:** This is an external *dispatch clock* but the recovery decision
still executes on GitHub Actions. It does not protect against a complete
GitHub Actions service outage. Avoid treating HTTP 204 as end-to-end proof.
