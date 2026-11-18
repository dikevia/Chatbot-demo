import json
import os
import unittest
from unittest.mock import patch

from backend.app.piste_legifrance import LegifranceClient, LegifranceError


class FakeResponse:
    def __init__(self, payload, status=200):
        self.data = json.dumps(payload).encode()
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self.data


class PisteClientTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {
            "LEGIFRANCE_ENVIRONMENT": "sandbox",
            "LEGIFRANCE_CLIENT_ID": "test-client",
            "LEGIFRANCE_CLIENT_SECRET": "test-secret",
        })
        self.env.start()

    def tearDown(self):
        self.env.stop()

    def test_uses_sandbox_and_caches_oauth_token(self):
        calls = []
        def opener(request, timeout):
            calls.append(request)
            if request.full_url.endswith("/api/oauth/token"):
                return FakeResponse({"access_token": "temporary-token", "expires_in": 3600})
            return FakeResponse({"status": "ok"})
        client = LegifranceClient(opener=opener)
        self.assertTrue(client.ping())
        self.assertTrue(client.ping())
        self.assertEqual(sum(c.full_url.endswith("/api/oauth/token") for c in calls), 1)
        self.assertTrue(all("sandbox-" in c.full_url for c in calls))
        self.assertNotIn("test-secret", repr(calls))

    def test_cetat_is_administrative_case_law_fund(self):
        payload = LegifranceClient._search_payload("harcèlement", "CETAT",
                                                   start="2020-01-01", end="2025-01-01")
        self.assertEqual(payload["fond"], "CETAT")
        self.assertEqual(payload["recherche"]["filtres"][0]["facette"], "DATE_DECISION")

    def test_invalid_period_is_rejected(self):
        with self.assertRaises(LegifranceError):
            LegifranceClient._search_payload("discipline", "LODA_DATE",
                                              start="2025-02-01", end="2025-01-01")

    def test_production_has_separate_hosts(self):
        with patch.dict(os.environ, {"LEGIFRANCE_ENVIRONMENT": "production"}):
            client = LegifranceClient(opener=lambda *a, **k: FakeResponse({}))
        self.assertEqual(client.oauth_url, "https://oauth.piste.gouv.fr/api/oauth/token")
        self.assertTrue(client.api_base.startswith("https://api.piste.gouv.fr/"))

    def test_missing_credentials_fails_closed(self):
        with patch.dict(os.environ, {"LEGIFRANCE_CLIENT_ID": "", "LEGIFRANCE_CLIENT_SECRET": ""}):
            with self.assertRaises(LegifranceError):
                LegifranceClient()


if __name__ == "__main__":
    unittest.main()
