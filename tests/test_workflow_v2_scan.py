import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ScanWorkflowContractTests(unittest.TestCase):
    def setUp(self):
        self.source = (ROOT / ".github/workflows/scan.yml").read_text(encoding="utf-8")

    def test_only_workflow_dispatch_with_required_scheduled_at(self):
        self.assertIn("workflow_dispatch:", self.source)
        self.assertIn("scheduled_at:", self.source)
        self.assertIn("required: true", self.source)
        for forbidden in ("schedule:", "pull_request", "push:"):
            self.assertNotIn(forbidden, self.source)

    def test_serialized_with_auth_state_and_never_cancelled(self):
        self.assertIn("group: ah-state", self.source)
        self.assertIn("cancel-in-progress: false", self.source)

    def test_writes_only_to_data_branch(self):
        self.assertIn("HEAD:data", self.source)
        self.assertNotIn("HEAD:main", self.source)

    def test_data_is_persisted_even_when_scan_fails(self):
        persist = self.source.split("Persist data", 1)[1]
        self.assertIn("if: always()", persist.split("run:", 1)[0])

    def test_secret_only_via_secrets_context(self):
        self.assertIn("${{ secrets.AH_REFRESH_TOKEN }}", self.source)
        self.assertNotIn("echo $AH_REFRESH_TOKEN", self.source)

    def test_mail_settings_only_via_secrets(self):
        for name in ("RESEND_API_KEY", "AH_MAIL_FROM", "AH_MAIL_TO"):
            self.assertIn("${{ secrets.%s }}" % name, self.source)


class WorkerConfigContractTests(unittest.TestCase):
    def setUp(self):
        self.config = (ROOT / "worker/wrangler.jsonc").read_text(encoding="utf-8")
        self.code = (ROOT / "worker/src/index.js").read_text(encoding="utf-8")

    def test_cron_covers_dst_window_in_utc(self):
        self.assertIn('"*/5 15-21 * * *"', self.config)

    def test_export_cron_matches_the_constant_in_the_code(self):
        import re

        slots = (ROOT / "worker/src/slots.js").read_text(encoding="utf-8")
        match = re.search(r'EXPORT_CRON = "([^"]+)"', slots)
        self.assertIsNotNone(match)
        self.assertIn(f'"{match.group(1)}"', self.config)
        self.assertEqual(match.group(1), "45 20,21 * * *")  # 22:45 Amsterdam, zomer en winter

    def test_report_cron_matches_the_constant_in_the_code(self):
        import re

        slots = (ROOT / "worker/src/slots.js").read_text(encoding="utf-8")
        match = re.search(r'REPORT_CRON = "([^"]+)"', slots)
        self.assertIsNotNone(match)
        self.assertIn(f'"{match.group(1)}"', self.config)
        self.assertEqual(match.group(1), "15 21,22 * * sun")  # zondag 23:15 Amsterdam

    def test_report_workflow_is_dispatched_via_config_variable(self):
        self.assertIn('"REPORT_WORKFLOW_FILE": "report.yml"', self.config)
        self.assertIn("env.REPORT_WORKFLOW_FILE", self.code)

    def test_crons_use_cloudflare_weekday_syntax(self):
        """Cloudflare weigert weekdag 0 ("invalid cron string"); gebruik namen of 1-7 (zondag = 1)."""
        import re

        crons = re.search(r'"crons": \[([^\]]*)\]', self.config).group(1)
        for cron in re.findall(r'"([^"]+)"', crons):
            fields = cron.split()
            self.assertEqual(len(fields), 5, cron)
            self.assertNotIn("0", re.split(r"[,\-/]", fields[4]), cron)
            self.assertRegex(fields[4], r"^(\*|(\*/\d+)|([1-7]|sun|mon|tue|wed|thu|fri|sat)([,\-]([1-7]|sun|mon|tue|wed|thu|fri|sat))*)$", cron)

    def test_stays_within_five_cron_triggers_of_the_free_plan(self):
        import re

        crons = re.search(r'"crons": \[([^\]]*)\]', self.config).group(1)
        self.assertLessEqual(len(re.findall(r'"[^"]+"', crons)), 5)

    def test_export_workflow_is_dispatched_on_main_without_secrets_in_config(self):
        self.assertIn('"EXPORT_WORKFLOW_FILE": "export.yml"', self.config)
        self.assertIn("env.EXPORT_WORKFLOW_FILE", self.code)

    def test_dispatches_scan_workflow_on_main_with_scheduled_at(self):
        self.assertIn('"WORKFLOW_FILE": "scan.yml"', self.config)
        self.assertIn('"GITHUB_REF": "main"', self.config)
        self.assertIn("scheduled_at", self.code)

    def test_token_is_a_secret_never_in_config(self):
        self.assertNotIn("ghp_", self.config)
        self.assertNotIn("github_pat_", self.config)
        self.assertIn("env.GITHUB_TOKEN", self.code)

    def test_observability_with_traces_enabled(self):
        self.assertIn('"observability": { "enabled": true, "traces": { "enabled": true } }', self.config)


if __name__ == "__main__":
    unittest.main()
