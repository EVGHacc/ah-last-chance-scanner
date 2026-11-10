"""Regression tests for bounded AH refresh recovery and scan integration."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import scanner
import session
from auth_recovery import AuthRefreshError, refresh_access_token


class AuthRefreshRecoveryTests(unittest.TestCase):
    def test_retries_transient_failure_with_bounded_backoff(self):
        calls = []
        responses = [(503, {"error": "temporary"}), (200, {"access_token": "fresh"})]

        def request(token):
            calls.append(token)
            return responses.pop(0)

        payload, used = refresh_access_token(
            "refresh-a", request, lambda: "", sleep=lambda _: None, delays=(0, 2)
        )

        self.assertEqual(payload["access_token"], "fresh")
        self.assertEqual(used, "refresh-a")
        self.assertEqual(calls, ["refresh-a", "refresh-a"])

    def test_uses_newer_encrypted_refresh_token_after_rejection(self):
        calls = []
        responses = [(401, {"error": "rejected"}), (200, {"access_token": "fresh"})]

        def request(token):
            calls.append(token)
            return responses.pop(0)

        payload, used = refresh_access_token(
            "stale-token",
            request,
            lambda: "newer-sealed-token",
            sleep=lambda _: None,
            delays=(0, 2),
        )

        self.assertEqual(payload["access_token"], "fresh")
        self.assertEqual(used, "newer-sealed-token")
        self.assertEqual(calls, ["stale-token", "newer-sealed-token"])

    def test_rejected_token_without_newer_sealed_state_requires_interactive_login(self):
        secret = "do-not-print-this-token"
        with self.assertRaises(AuthRefreshError) as raised:
            refresh_access_token(
                secret,
                lambda _: (401, {"error": "invalid_grant"}),
                lambda: secret,
                sleep=lambda _: None,
                delays=(0, 2),
            )

        self.assertEqual(raised.exception.code, "AUTH_REAUTH_REQUIRED")
        self.assertNotIn(secret, str(raised.exception))

    def test_transient_retries_stop_at_configured_limit(self):
        calls = []
        with self.assertRaises(AuthRefreshError) as raised:
            refresh_access_token(
                "refresh-a",
                lambda token: (calls.append(token) or (429, {})),
                lambda: "",
                sleep=lambda _: None,
                delays=(0, 0, 0),
            )

        self.assertEqual(raised.exception.code, "AUTH_REFRESH_RETRY_EXHAUSTED")
        self.assertEqual(len(calls), 3)

    def test_non_retryable_response_fails_without_repeating(self):
        calls = []
        with self.assertRaises(AuthRefreshError) as raised:
            refresh_access_token(
                "refresh-a",
                lambda token: (calls.append(token) or (403, {})),
                lambda: "",
                sleep=lambda _: None,
                delays=(0, 2, 5),
            )

        self.assertEqual(raised.exception.code, "AUTH_REFRESH_FAILED")
        self.assertEqual(len(calls), 1)


class ScannerAuthIntegrationTests(unittest.TestCase):
    def test_force_refresh_bypasses_unexpired_access_token_cache(self):
        cached = {
            "accessToken": "cached-access",
            "accessExpiresAt": 9999999999,
            "refreshToken": "refresh-a",
        }
        with patch.object(scanner, "_load_state", return_value=cached), \
             patch.dict("os.environ", {"AH_REFRESH_TOKEN": "root-secret"}), \
             patch.object(scanner, "post", return_value=(200, {"access_token": "fresh-access", "expires_in": 600})) as post, \
             patch.object(scanner, "_save_state") as save:
            access, mode = scanner.token(force_refresh=True)

        self.assertEqual(access, "fresh-access")
        self.assertEqual(mode, "user-refresh")
        post.assert_called_once()
        self.assertEqual(post.call_args.kwargs["attempts"], 1)
        save.assert_called_once()

    def test_graphql_401_rebuilds_session_once_and_updates_shared_access(self):
        context = {"access": "expired-access"}
        with patch.object(scanner, "post", side_effect=[
            (401, {"error": "unauthorized"}),
            (200, {"data": {"bargainItems": []}}),
        ]), patch.object(scanner, "token", return_value=("refreshed-access", "user-refresh")) as refresh:
            result = scanner.fetch_store(1463, "AH Blekersvaartweg", "expired-access", context)

        self.assertTrue(result["fetched"])
        refresh.assert_called_once_with(force_refresh=True)
        self.assertEqual(context["access"], "refreshed-access")
        self.assertEqual(post.call_args_list[0].args[2], "expired-access")
        self.assertEqual(post.call_args_list[1].args[2], "refreshed-access")

    def test_failed_auth_rebuild_is_shared_and_not_retried_per_store(self):
        context = {"access": "expired-access"}
        with patch.object(scanner, "post", return_value=(401, {"error": "unauthorized"})), \
             patch.object(scanner, "token", side_effect=RuntimeError("AUTH_REAUTH_REQUIRED: login needed")) as refresh:
            first = scanner.fetch_store(1463, "AH Blekersvaartweg", "expired-access", context)
            second = scanner.fetch_store(1348, "AH Zandvoortselaan", "expired-access", context)

        self.assertFalse(first["fetched"])
        self.assertFalse(second["fetched"])
        self.assertIn("AUTH_REAUTH_REQUIRED", first["error"])
        self.assertIn("AUTH_REAUTH_REQUIRED", second["error"])
        refresh.assert_called_once_with(force_refresh=True)


    def test_rejected_refreshed_access_stops_fanout_and_requests_reauthentication(self):
        context = {"access": "expired-access"}
        with patch.object(scanner, "post", side_effect=[
            (401, {"error": "unauthorized"}),
            (401, {"error": "unauthorized"}),
        ]) as post, patch.object(scanner, "token", return_value=("fresh-access", "user-refresh")) as refresh:
            first = scanner.fetch_store(1463, "AH Blekersvaartweg", "expired-access", context)
            second = scanner.fetch_store(1348, "AH Zandvoortselaan", "expired-access", context)

        self.assertFalse(first["fetched"])
        self.assertFalse(second["fetched"])
        self.assertIn("AUTH_REAUTH_REQUIRED", first["error"])
        self.assertIn("AUTH_REAUTH_REQUIRED", second["error"])
        refresh.assert_called_once_with(force_refresh=True)
        self.assertEqual(post.call_count, 2)


class SessionRetryPolicyTests(unittest.TestCase):
    def test_interactive_reauthentication_failure_stops_outer_scan_retries(self):
        obs = {
            "authMode": "user-refresh-failed",
            "stores": [{"error": "AUTH_REAUTH_REQUIRED: login needed"}],
        }
        self.assertTrue(session.requires_interactive_reauth(obs))

    def test_transient_auth_failure_keeps_bounded_outer_retry_available(self):
        obs = {
            "authMode": "user-refresh-failed",
            "stores": [{"error": "AUTH_REFRESH_RETRY_EXHAUSTED: temporary failure"}],
        }
        self.assertFalse(session.requires_interactive_reauth(obs))


if __name__ == "__main__":
    unittest.main()
