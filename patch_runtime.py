from pathlib import Path

ROOT = Path("/app")
orchestrator = ROOT / "backend/app/orchestrator.py"
source = orchestrator.read_text(encoding="utf-8")

old_context = '''        contextual_question = current_question[:500]
        # A short follow-up may depend on the immediately preceding question,
        # but older exchanges must never displace the current request.
        if prior_user_questions and len(current_question) < 220:
            contextual_question = current_question[:350] + "\\n" + prior_user_questions[-1][:150]
'''
new_context = '''        # Never contaminate a new legal search with the previous question.
        # Conversation context is used only for explicit short follow-ups, and
        # then only as a fallback if the current wording returns no CGFP hit.
        contextual_question = current_question[:500]
        lower_question = current_question.lower().lstrip()
        is_explicit_follow_up = lower_question.startswith((
            "et pour ", "et si ", "et dans ce cas", "qu en est-il", "qu'en est-il",
            "et concernant ", "et pour les ", "et pour un ", "et pour une ",
            "dans cette situation", "dans ce cas", "pour ces agents",
        ))
'''
old_search = "                found = search_cgfp(contextual_question, limit=8)\\n"
new_search = '''                found = search_cgfp(current_question, limit=8)
                if not found.get("results") and is_explicit_follow_up and prior_user_questions:
                    found = search_cgfp(
                        current_question[:350] + "\\n" + prior_user_questions[-1][:150], limit=8
                    )
'''
if old_context in source:
    source = source.replace(old_context, new_context, 1)
elif new_context not in source:
    raise RuntimeError("Bloc de contexte de recherche introuvable ou déjà modifié de façon inattendue.")

if old_search in source:
    source = source.replace(old_search, new_search, 1)
elif "found = search_cgfp(current_question, limit=8)" not in source:
    raise RuntimeError("Appel de recherche CGFP introuvable ou déjà modifié de façon inattendue.")

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
    "JURIS ne formule donc pas de conclusion juridique.",
    "Dikévia ne formule donc pas de conclusion juridique.",
    1,
)

warning_anchor = '''        missing = ["Vérifier les dates d'effet et la rédaction exacte applicable à la date des faits.",
'''
warning = '''        if has_cgfp_snapshot and not any(
            s.get("source_type") in {"LEGIFRANCE_API", "LEGIFRANCE_LODA"} for s in sources
        ):
            missing.insert(0, "Les articles affichés proviennent de l'index documentaire local du CGFP (snapshot daté du 31 octobre 2026). Ils servent au repérage et ne remplacent pas la vérification de la version officielle sur Légifrance à la date des faits.")

'''
if warning_anchor in source and warning not in source:
    source = source.replace(warning_anchor, warning + warning_anchor, 1)
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
