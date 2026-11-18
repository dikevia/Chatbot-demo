import asyncio
import json
import sys
import unittest
from datetime import date
from urllib.parse import parse_qs

import httpx

sys.path.insert(0, "/app/backend")
from app.config import settings
from app.legifrance import LegifranceConnector
from app.jurisprudence import AdministrativeCaseLawConnector


class ExistingLegifranceConnectorTests(unittest.TestCase):
    def test_code_search_is_scoped_to_cgfp_and_requested_version(self):
        connector = LegifranceConnector()
        payload = connector._search_payload("sanction disciplinaire", date(2025, 4, 12))
        self.assertEqual(payload["fond"], "CODE_DATE")
        filters = payload["recherche"]["filtres"]
        self.assertEqual(filters[0]["facette"], "NOM_CODE")
        self.assertEqual(filters[0]["valeurs"], ["Code général de la fonction publique"])
        self.assertEqual(filters[1]["facette"], "DATE_VERSION")
        self.assertEqual(filters[1]["singleDate"], connector._date_epoch_ms(date(2025, 4, 12)))

    def test_cetat_search_is_administrative_and_date_limited(self):
        payload = AdministrativeCaseLawConnector.search_payload(
            "protection fonctionnelle", date(2025, 4, 12)
        )
        self.assertEqual(payload["fond"], "CETAT")
        self.assertEqual(payload["recherche"]["filtres"][0]["facette"], "DATE_DECISION")
        self.assertEqual(payload["recherche"]["filtres"][0]["dates"]["end"], "2025-04-12")

    def test_piste_oauth_search_and_full_text_consultation(self):
        article_text = (
            "Le présent décret précise les règles applicables aux agents de la fonction "
            "publique territoriale et aux collectivités territoriales. " * 4
        )
        seen = []

        def handler(request):
            seen.append(request)
            if request.url.host == "sandbox-oauth.piste.gouv.fr":
                form = parse_qs(request.content.decode())
                self.assertEqual(form["grant_type"], ["client_credentials"])
                self.assertEqual(form["scope"], ["openid"])
                self.assertEqual(form["client_id"], ["sandbox-client"])
                self.assertEqual(form["client_secret"], ["sandbox-secret"])
                return httpx.Response(200, json={"access_token": "mock-token", "expires_in": 3600})
            self.assertEqual(request.headers.get("Authorization"), "Bearer mock-token")
            if request.url.path.endswith("/search"):
                body = json.loads(request.content)
                self.assertEqual(body["fond"], "LODA_DATE")
                return httpx.Response(200, json={"results": [{
                    "id": "LEGITEXT000000000001",
                    "titre": "Décret relatif à la fonction publique territoriale",
                    "etat": "VIGUEUR",
                    "nor": "TEST0000001",
                }]})
            if request.url.path.endswith("/consult/legiPart"):
                body = json.loads(request.content)
                self.assertEqual(body["textId"], "LEGITEXT000000000001")
                return httpx.Response(200, json={"text": {
                    "id": "LEGITEXT000000000001", "texte": article_text
                }})
            raise AssertionError(f"Unexpected PISTE endpoint: {request.url.path}")

        async def exercise():
            with unittest.mock.patch.object(settings, "legifrance_client_id", "sandbox-client"), \
                 unittest.mock.patch.object(settings, "legifrance_client_secret", "sandbox-secret"), \
                 unittest.mock.patch.object(settings, "legifrance_environment", "sandbox"):
                transport = httpx.MockTransport(handler)
                connector = LegifranceConnector(transport=transport)
                results = await connector.search_regulatory_texts(
                    "fonction publique territoriale", date(2025, 4, 12), limit=3
                )
                self.assertEqual(len(results), 1)
                self.assertEqual(results[0]["source_id"], "LEGITEXT000000000001")
                self.assertGreaterEqual(len(results[0]["full_text"]), 80)
                self.assertEqual(results[0]["version_key"], "LEGITEXT000000000001:2025-04-12")

        asyncio.run(exercise())
        self.assertEqual(seen[0].url.host, "sandbox-oauth.piste.gouv.fr")
        self.assertTrue(any(request.url.path.endswith("/search") for request in seen))
        self.assertTrue(any(request.url.path.endswith("/consult/legiPart") for request in seen))


if __name__ == "__main__":
    unittest.main()
