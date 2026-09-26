# Oasis Amsterdam resale scanner

Live browser scanner in this public repository, separate from all AH/vacancy/Oro workflows.

**Run order:** GitHub Action `.github/workflows/oasis-monitor.yml` runs around 19:15 Europe/Amsterdam (two UTC cron entries, local-time gate); the existing ChatGPT report runs at 21:00. A manual `workflow_dispatch` is also available. The workflow uses GitHub's standard public-repository Ubuntu runner, no paid runner or third-party scraping service.

**Events:** separately 2027-07-16 and 2027-07-17, Johan Cruijff ArenA. **Registry:** `sources.json`, exactly ten fixed platforms per date. `scanner.py` uses regular public Playwright Chromium browsing, a small concurrency cap and event-specific page validation. `bootstrap.py` verifies SHA-256 checksums of initial compressed sources, then creates readable `scanner.py` and `test_scanner.py` on the initial run; readable sources are committed alongside the first successfully validated snapshot. Existing readable files are never replaced by bootstrap.

**Coverage is not one number:** for each concert, record (A) dated event page validated, (B) actual categorized listing(s) or explicitly verified zero, (C) verified all-in price. Report all as X/10 separately. "All 20 source/date checks classified" is not the same as verified listing coverage. Blocked/empty/unlisted pages are never treated as zero stock. Aggregator partner quotes remain separate and do not count as actual reseller listing inventory. Prices are asking prices only; no guessed fees, sales or realized profit.

**Persistence:** `data/YYYY-MM-DD.json` and `data/latest.json`, with per-source timestamp/status/link/reason, listings and forum checks/signals. Both are written only after schema/coverage QA, read back locally, committed and checked against the published GitHub file. Only verified comparable category/fee-basis series appear in trends. `status=classified_with_gaps` means complete source classification, *not* 100% listing verification. If the scan fails before publication, `latest.json` remains stale and the reporter must flag that.

**Quality controls:** `python -m unittest discover -s oasis-monitor -p 'test_*.py' -v`; then live browser scan; then 20 unique source/date checks, coverage consistency and byte-for-byte day/latest readback. Logs appear under GitHub Actions. The scanner respects access restrictions, does not bypass CAPTCHAs, use private APIs or place transactions. Client-side listings may be blocked or require login; this is an honestly reported limitation, not a 90% coverage guarantee.

**Forums:** public Reddit feeds and the listed public forum URLs. Individual links and original publication times are required for Reddit signals; thread index/undated page text is not an evidence-backed new signal. Fan reports are not official ticket policy.

**Official rules:** https://help.ticketmaster.nl/hc/nl/articles/50379069472529-Oasis-Live-27 ; check transfer/Face Value Exchange every day. Do not treat external asking prices as guaranteed or authorized resale.
