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
elif "selected_sources" in source and "if not selected_sources and not has_cgfp_snapshot" not in source:
    selected_gate = '''        if not selected_sources and not any(s.get("source_type") in {"LEGIFRANCE_API", "LEGIFRANCE_LODA"} for s in sources) and not usable_permanent and not usable_local:
'''
    selected_new_gate = '''        has_cgfp_snapshot = any(
            s.get("source_type") == "CGFP_SNAPSHOT"
            and (s.get("citation_integrity") or {}).get("valid") is True
            for s in sources
        )
        if not selected_sources and not has_cgfp_snapshot and not any(s.get("source_type") in {"LEGIFRANCE_API", "LEGIFRANCE_LODA"} for s in sources) and not usable_permanent and not usable_local:
'''
    if selected_gate in source:
        source = source.replace(selected_gate, selected_new_gate, 1)
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



# Gemini OpenAI-compatible endpoint support and safe general-purpose orientation.
config_path = ROOT / "backend/app/config.py"
config_source = config_path.read_text(encoding="utf-8")
old_ai_path = 'ai_url.path not in ("", "/v1")'
new_ai_path = 'ai_url.path not in ("", "/v1", "/v1beta/openai", "/v1beta/openai/")'
if old_ai_path in config_source:
    config_source = config_source.replace(old_ai_path, new_ai_path, 1)
elif new_ai_path not in config_source:
    raise RuntimeError("Validation AI_API_BASE_URL introuvable.")
config_source = config_source.replace(
    "AI_API_BASE_URL doit être une origine ou une base /v1 sans paramètres.",
    "AI_API_BASE_URL doit être une origine, une base /v1 ou le chemin Gemini /v1beta/openai, sans paramètres.",
    1,
)
config_path.write_text(config_source, encoding="utf-8")
compile(config_source, str(config_path), "exec")

ai_provider_path = ROOT / "backend/app/ai_provider.py"
ai_source = ai_provider_path.read_text(encoding="utf-8")
prompt_anchor = "\n\n@dataclass(frozen=True)"
triage_prompt = '''

SYSTEM_PROMPT += """
MODE ORIENTATION GÉNÉRALE SANS SOURCE :
- Si aucun extrait documentaire validé ne t'est fourni, tu ne fais PAS d'analyse juridique et tu ne cites aucun article, loi, décret, jurisprudence, délai ou règle présentée comme certaine.
- Tu peux néanmoins aider concrètement : comprendre la situation décrite, signaler les risques pratiques immédiats, proposer des démarches prudentes et expliquer quelles informations ou sources officielles seraient nécessaires.
- Présente explicitement cette réponse comme une orientation générale non juridique, non vérifiée et non comme un avis de droit.
- Ne prétends jamais avoir consulté une source qui n'a pas été transmise.
- Si un risque immédiat pour une personne ou la sécurité existe, donne la priorité à la mise en sécurité et aux procédures d'urgence adaptées.
- Pose au maximum une question de clarification, uniquement si elle change réellement les premières démarches.
"""
'''
if "MODE ORIENTATION GÉNÉRALE SANS SOURCE" not in ai_source:
    if prompt_anchor not in ai_source:
        raise RuntimeError("Point d'insertion du mode d'orientation IA introuvable.")
    ai_source = ai_source.replace(prompt_anchor, triage_prompt + prompt_anchor, 1)
ai_provider_path.write_text(ai_source, encoding="utf-8")
compile(ai_source, str(ai_provider_path), "exec")

helper_anchor = 'logger = logging.getLogger(__name__)\n\n\nclass LegalOrchestrator:'
helper = '''logger = logging.getLogger(__name__)


async def _dikevia_general_ai_orientation(
    question: str, employer: str, facts_date: str | None, history: list[dict] | None
) -> str | None:
    """General practical orientation only; no legal sources means no legal claims."""
    if not all((settings.ai_api_base_url, settings.ai_api_key, settings.ai_model)):
        return None
    try:
        result = await analyze_question(
            question=question,
            employer=employer,
            facts_date=facts_date,
            sources=[],
            conversation_history=history,
        )
    except AIProviderUnavailable as exc:
        # Keep the secret out of logs: expose only the sanitized provider error
        # so authentication, model and endpoint failures can be distinguished.
        detail = str(exc).replace(settings.ai_api_key or "", "[secret]")[:500]
        logger.warning(
            "Fournisseur IA indisponible pendant l'orientation générale (%s): %s",
            type(exc).__name__, detail or "aucun détail transmis par le fournisseur",
        )
        return None
    content = result.content if isinstance(result, AIAnalysisResult) else result
    if not isinstance(content, str) or not content.strip():
        return None
    # With no documentary sources, every generated legal reference is rejected.
    if not answer_references_are_grounded(content, set(), set()):
        logger.warning("Orientation IA écartée : référence juridique sans source.")
        return None
    return content.strip()


class LegalOrchestrator:'''
if helper_anchor in source:
    source = source.replace(helper_anchor, helper, 1)
elif "def source_selection_key(source: dict) -> str:" in source and "_dikevia_general_ai_orientation" not in source:
    helper_prefix = helper.split("class LegalOrchestrator:")[0]
    source = source.replace(
        "logger = logging.getLogger(__name__)\\n\\n\\ndef source_selection_key(source: dict) -> str:",
        helper_prefix + "def source_selection_key(source: dict) -> str:",
        1,
    )
elif "_dikevia_general_ai_orientation" not in source:
    raise RuntimeError("Point d'insertion de l'orientation IA introuvable.")

old_no_sources = '''            return AskResponse(request_id=request_id, verification_status="NON_VERIFIE",
                answer="Aucune source exploitable n'a été récupérée et contrôlée pour cette question. Dikévia ne formule donc pas de conclusion juridique.",
                sources=sources, missing_information=missing)'''
new_no_sources = '''            triage_answer = await _dikevia_general_ai_orientation(
                current_question, request.employer, request.facts_date, history
            )
            if triage_answer:
                answer = (
                    "Orientation générale et pratique — non juridique, non vérifiée. "
                    "Aucune source juridique exploitable n'a été contrôlée pour cette question.\\\\n\\\\n"
                    + triage_answer
                    + "\\\\n\\\\nCette orientation ne constitue pas une analyse juridique. "
                    "Une vérification sur des sources officielles reste nécessaire avant toute décision."
                )
            else:
                answer = "Aucune source exploitable n'a été récupérée et contrôlée pour cette question. Dikévia ne formule donc pas de conclusion juridique."
            return AskResponse(request_id=request_id, verification_status="NON_VERIFIE",
                answer=answer, sources=sources, missing_information=missing)'''
if old_no_sources in source:
    source = source.replace(old_no_sources, new_no_sources, 1)
elif "triage_answer = await _dikevia_general_ai_orientation(" not in source:
    raise RuntimeError("Retour sans source introuvable.")

old_no_date = '''        if parsed_date is None:
            ai_answer = None
            missing.insert(0, "Analyse juridique contextualisée suspendue : préciser la date des faits pour vérifier la version applicable. La date du jour n'est utilisée que pour le repérage documentaire.")
        else:'''
new_no_date = '''        ai_triage_mode = parsed_date is None
        if parsed_date is None:
            ai_answer = await _dikevia_general_ai_orientation(
                current_question, request.employer, None, history
            )
            if not ai_answer:
                missing.insert(0, "Analyse juridique contextualisée suspendue : préciser la date des faits. Sans date, Dikévia peut seulement fournir une orientation générale non juridique si le fournisseur IA est configuré.")
        else:'''
if old_no_date in source:
    source = source.replace(old_no_date, new_no_date, 1)
elif "if parsed_date is None and not selected_sources:" in source:
    selected_no_date = '''        ai_triage_mode = parsed_date is None and not selected_sources
        if ai_triage_mode:
            ai_answer = await _dikevia_general_ai_orientation(
                current_question, request.employer, None, history
            )
            if not ai_answer:
                missing.insert(0, "Analyse juridique contextualisée suspendue : préciser la date des faits. Sans date, Dikévia peut seulement fournir une orientation générale non juridique si le fournisseur IA est configuré.")
        else:'''
    selected_old = '''        if parsed_date is None and not selected_sources:
            ai_answer = None
            missing.insert(0, "Analyse juridique contextualisée suspendue : préciser la date des faits pour vérifier la version applicable. La date du jour n'est utilisée que pour le repérage documentaire.")
        else:'''
    source = source.replace(selected_old, selected_no_date, 1)
elif "ai_triage_mode = parsed_date is None" not in source:
    raise RuntimeError("Bloc IA sans date des faits introuvable.")

old_no_verified = '''                else:
                    ai_answer = None
                    missing.insert(
                        0,
                        "Analyse IA suspendue : aucune source officielle datée et exploitable n'est disponible. Le snapshot CGFP seul reste une piste documentaire.",
                    )'''
new_no_verified = '''                else:
                    ai_triage_mode = True
                    ai_answer = await _dikevia_general_ai_orientation(
                        current_question, request.employer, request.facts_date, history
                    )
                    if not ai_answer:
                        missing.insert(
                            0,
                            "Aucune source officielle datée et exploitable n'est disponible. Le snapshot CGFP reste une piste documentaire ; l'orientation IA est indisponible ou non configurée.",
                        )'''
if old_no_verified in source:
    source = source.replace(old_no_verified, new_no_verified, 1)
elif "ai_answer = await _dikevia_general_ai_orientation(" not in source:
    raise RuntimeError("Branche sans source IA vérifiée introuvable.")

answer_start = source.find("        if ai_answer:")
answer_end = source.find("        else:", answer_start)
if answer_start < 0 or answer_end < 0:
    if "if ai_answer and ai_triage_mode:" not in source:
        raise RuntimeError("Assemblage de la réponse IA introuvable.")
else:
    answer_block = '''        if ai_answer and ai_triage_mode:
            answer = (
                "Orientation générale et pratique — non juridique, non vérifiée. "
                "Aucune source juridique officielle datée et exploitable n'a été transmise à l'IA.\\n\\n"
                + ai_answer
                + "\\n\\nCette orientation ne constitue pas une analyse juridique. "
                "Vérifier les faits et les sources officielles avant toute décision."
            )
        elif ai_answer:
            answer = (ai_answer + "\\n\\n---\\nStatut : analyse assistée à partir des sources affichées. "
                "Les extraits du snapshot PDF ne certifient pas l'authenticité officielle. Les versions du corpus dont les dates d'effet sont incomplètes ne sont pas utilisées pour les conclusions IA. Les actes locaux restent à vérifier. Une validation juridique humaine reste nécessaire.")
'''
    source = source[:answer_start] + answer_block + source[answer_end:]

orchestrator.write_text(source, encoding="utf-8")
compile(source, str(orchestrator), "exec")
print("Gemini endpoint and safe no-source orientation patches applied.")

compile(source, str(orchestrator), "exec")
print("Dikévia runtime patch applied.")
