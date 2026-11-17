from pathlib import Path

ROOT = Path("/app")
orchestrator = ROOT / "backend/app/orchestrator.py"
source = orchestrator.read_text(encoding="utf-8")
source = source.replace(
    "from .cgfp import search_cgfp, get_cgfp_article",
    "from .cgfp import get_cgfp_article\nfrom .cgfp_relevance import search_cgfp",
    1,
)
if "from .cgfp_relevance import search_cgfp" not in source:
    raise RuntimeError("Le moteur de pertinence CGFP n'a pas pu être raccordé.")


old_context = '''        contextual_question = current_question[:500]
        # A short follow-up may depend on the immediately preceding question,
        # but older exchanges must never displace the current request.
        if prior_user_questions and len(current_question) < 220:
            contextual_question = current_question[:350] + "\\n" + prior_user_questions[-1][:150]
'''
new_context = '''        # A new question is always searched independently. History remains
        # available to the assistant, but must never contaminate retrieval.
        contextual_question = current_question[:500]
'''
old_search = "                found = search_cgfp(contextual_question, limit=8)" + chr(10)
new_search = "                found = search_cgfp(current_question, limit=8)" + chr(10)
if old_context in source:
    source = source.replace(old_context, new_context, 1)
elif new_context not in source:
    raise RuntimeError("Bloc de contexte de recherche introuvable ou déjà modifié.")
if old_search in source:
    source = source.replace(old_search, new_search, 1)
elif new_search.strip() not in source:
    raise RuntimeError("Appel de recherche CGFP introuvable ou déjà modifié.")

old_gate = '''        if not any(s.get("source_type") in {"LEGIFRANCE_API", "LEGIFRANCE_LODA"} for s in sources) and not usable_permanent and not usable_local:
'''
new_gate = '''        # A validated local CGFP snapshot is useful documentary material even
        # when live PISTE is unavailable. Display it, but never treat it as
        # date-verified authority or sufficient evidence for an AI conclusion.
        has_cgfp_snapshot = any(
            s.get("source_type") == "CGFP_SNAPSHOT"
            and (s.get("citation_integrity") or {}).get("valid") is True
            for s in sources
        )
        has_usable_legal_source = (
            any(s.get("source_type") in {"LEGIFRANCE_API", "LEGIFRANCE_LODA"} for s in sources)
            or bool(usable_permanent)
            or bool(usable_local)
            or has_cgfp_snapshot
        )
        if not has_usable_legal_source:
'''
if old_gate in source:
    source = source.replace(old_gate, new_gate, 1)
elif "has_cgfp_snapshot = any(" not in source:
    raise RuntimeError("Condition de refus sans source introuvable ou déjà modifiée de façon inattendue.")

source = source.replace(
    "\"title\": f\"Code général de la fonction publique — article {hit['article']}\",",
    "\"title\": f\"Code général de la fonction publique — article {hit['article']}\" + (f\" — {hit.get('relevance_label')}\" if hit.get(\"relevance_label\") else \"\"),",
    1,
)

source = source.replace(
    "JURIS ne formule donc pas de conclusion juridique.",
    "Dikévia ne formule donc pas de conclusion juridique.",
    1,
)

warning = '''        if has_cgfp_snapshot and not any(
            s.get("source_type") in {"LEGIFRANCE_API", "LEGIFRANCE_LODA"} for s in sources
        ):
            missing.insert(0, "Les articles affichés proviennent de l'index documentaire local du CGFP (snapshot daté du 31 octobre 2026). Ils servent au repérage et ne remplacent pas la vérification de la version officielle sur Légifrance à la date des faits.")

'''
warning_anchor = '''            "Vérifier les actes locaux, délibérations et accords applicables à l'employeur concerné."]
'''
if warning_anchor in source and warning not in source:
    source = source.replace(warning_anchor, warning_anchor + warning, 1)
elif warning not in source and "Les articles affichés proviennent de l'index documentaire local du CGFP" not in source:
    raise RuntimeError("Emplacement du message de prudence CGFP introuvable.")

orchestrator.write_text(source, encoding="utf-8")

for relative in ("frontend/index.html", "frontend/manifest.webmanifest"):
    path = ROOT / relative
    if path.exists():
        content = path.read_text(encoding="utf-8").replace("Dikevia", "Dikévia")
        path.write_text(content, encoding="utf-8")

compile(source, str(orchestrator), "exec")
print("Dikévia runtime patch applied.")
