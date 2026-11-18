import unittest

from fpt_scope import classify_public_service_scope


class FPTScopeTests(unittest.TestCase):
    def test_territorial_scope_is_eligible(self):
        result = classify_public_service_scope({
            "title": "Décret relatif aux agents de la fonction publique territoriale",
            "full_text": "Les collectivités territoriales et leurs établissements publics."
        })
        self.assertEqual(result["scope"], "FPT")
        self.assertTrue(result["analysis_eligible"])

    def test_hospital_scope_is_excluded(self):
        result = classify_public_service_scope({
            "title": "Dispositions relatives à la fonction publique hospitalière",
            "full_text": "Les établissements publics de santé."
        })
        self.assertEqual(result["scope"], "FPH")
        self.assertFalse(result["analysis_eligible"])

    def test_state_scope_is_excluded(self):
        result = classify_public_service_scope({
            "title": "Agents de la fonction publique de l'État",
            "full_text": "Les fonctionnaires de l'État."
        })
        self.assertEqual(result["scope"], "FPE")
        self.assertFalse(result["analysis_eligible"])

    def test_cross_public_service_text_can_be_eligible(self):
        result = classify_public_service_scope({
            "title": "Droits et obligations des fonctionnaires",
            "full_text": "Le code général de la fonction publique prévoit les garanties des agents publics."
        })
        self.assertEqual(result["scope"], "GENERAL_PUBLIC_SERVICE")
        self.assertTrue(result["analysis_eligible"])

    def test_ihts_reference_decree_is_eligible_with_local_checks_required(self):
        result = classify_public_service_scope({
            "title": "Décret n° 2002-60 relatif aux indemnités horaires pour travaux supplémentaires",
            "full_text": "Indemnités horaires pour travaux supplémentaires (IHTS)."
        })
        self.assertEqual(result["scope"], "FPT_REFERENCE")
        self.assertTrue(result["analysis_eligible"])
        self.assertIn("deliberation locale", result["evidence"][0])

    def test_ambiguous_scope_fails_closed(self):
        result = classify_public_service_scope({
            "title": "Modalités d'application d'une mesure",
            "full_text": "Dispositions diverses."
        })
        self.assertEqual(result["scope"], "SCOPE_TO_VERIFY")
        self.assertFalse(result["analysis_eligible"])


if __name__ == "__main__":
    unittest.main()
