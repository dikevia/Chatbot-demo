import unittest

from fpt_scope import classify_public_service_scope, is_ihts_relevant_source


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

    def test_ihts_question_rejects_unrelated_service_hours_and_cpf_results(self):
        question = "On me paie pas mes heures supolementaires"
        unrelated = [
            {"title": "CGFP L711-2", "full_text": "Il n'y a pas service fait lorsque l'agent s'abstient d'effectuer ses heures de service."},
            {"title": "CGFP L542-3", "full_text": "Modification du nombre d'heures de service hebdomadaire d'un emploi à temps non complet."},
            {"title": "CGFP R214-33", "full_text": "Crédits d'heures syndicales et compensation financière entre établissements."},
            {"title": "CGFP R422-85", "full_text": "Alimentation du compte personnel de formation à hauteur de 50 heures."},
        ]
        for source in unrelated:
            with self.subTest(source=source["title"]):
                self.assertFalse(is_ihts_relevant_source(question, source))

    def test_ihts_question_keeps_relevant_decrees_and_compensation(self):
        question = "On ne me paie pas mes heures supplémentaires"
        relevant = [
            {"title": "Décret n° 2002-60", "full_text": "Indemnités horaires pour travaux supplémentaires (IHTS)."},
            {"title": "Décret n° 91-875", "full_text": "Indemnités horaires pour travaux supplémentaires."},
            {"title": "Décret n° 2001-623", "full_text": "Organisation des cycles de travail."},
            {"title": "Repos compensateur", "full_text": "Les heures supplémentaires ouvrent droit à repos compensateur."},
        ]
        for source in relevant:
            with self.subTest(source=source["title"]):
                self.assertTrue(is_ihts_relevant_source(question, source))

    def test_topic_filter_does_not_change_other_legal_questions(self):
        source = {"title": "CGFP L134-5", "full_text": "Protection fonctionnelle."}
        self.assertTrue(is_ihts_relevant_source("Mon chef me menace", source))

    def test_ambiguous_scope_fails_closed(self):
        result = classify_public_service_scope({
            "title": "Modalités d'application d'une mesure",
            "full_text": "Dispositions diverses."
        })
        self.assertEqual(result["scope"], "SCOPE_TO_VERIFY")
        self.assertFalse(result["analysis_eligible"])


if __name__ == "__main__":
    unittest.main()
