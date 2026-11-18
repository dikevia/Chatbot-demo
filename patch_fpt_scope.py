"""Apply the FPT-scope safety guard to the packaged chatbot after extraction."""
from pathlib import Path

ROOT = Path("/app")
orchestrator_path = ROOT / "backend/app/orchestrator.py"
source = orchestrator_path.read_text(encoding="utf-8")

import_anchor = "from .cgfp_relevance import search_cgfp"
import_replacement = import_anchor + "\nfrom .fpt_scope import classify_public_service_scope"
if import_anchor not in source:
    raise RuntimeError("Import du moteur CGFP introuvable pour le filtre FPT.")
if "from .fpt_scope import classify_public_service_scope" not in source:
    source = source.replace(import_anchor, import_replacement, 1)

regulatory_anchor = '''        for item in regulatory_sources:
            full_text = item.get("full_text") or ""
            sources.append({
                **item,
'''
regulatory_replacement = '''        for item in regulatory_sources:
            full_text = item.get("full_text") or ""
            scope = classify_public_service_scope({**item, "full_text": full_text})
            sources.append({
                **item,
                "public_service_scope": scope["scope"],
                "public_service_scope_evidence": scope["evidence"],
                "analysis_eligible": scope["analysis_eligible"],
'''
if regulatory_anchor in source:
    source = source.replace(regulatory_anchor, regulatory_replacement, 1)
elif '"public_service_scope": scope["scope"]' not in source:
    raise RuntimeError("Boucle de transformation des textes Légifrance introuvable.")

selected_anchor = '''                if (source_selection_key(source) in selected_key_set
                        and source.get("content_kind") != "METADATA"
'''
selected_replacement = '''                if (source_selection_key(source) in selected_key_set
                        and source.get("analysis_eligible") is not False
                        and source.get("content_kind") != "METADATA"
'''
if selected_anchor in source:
    source = source.replace(selected_anchor, selected_replacement, 1)
elif 'source.get("analysis_eligible") is not False' not in source:
    raise RuntimeError("Filtre des textes sélectionnés introuvable.")

verified_anchor = '''                    and (s.get("citation_integrity") or {}).get("valid") is True
                    and s.get("temporal_status") in eligible_temporal_statuses
'''
verified_replacement = '''                    and (s.get("citation_integrity") or {}).get("valid") is True
                    and s.get("temporal_status") in eligible_temporal_statuses
                    and (s.get("source_type") != "LEGIFRANCE_LODA" or s.get("analysis_eligible") is True)
'''
if verified_anchor in source:
    source = source.replace(verified_anchor, verified_replacement, 1)
elif 's.get("source_type") != "LEGIFRANCE_LODA" or s.get("analysis_eligible") is True' not in source:
    raise RuntimeError("Filtre des sources transmises à Gemini introuvable.")

case_law_anchor = '''        if case_law_sources:
            missing.insert(0, "Les résultats CETAT sont des métadonnées/extraits de recherche ; le texte intégral des décisions n'a pas été récupéré ni contrôlé.")
'''
scope_warning = case_law_anchor + '''        if any(s.get("source_type") == "LEGIFRANCE_LODA" and s.get("analysis_eligible") is not True for s in sources):
            missing.insert(0, "Certains textes réglementaires repérés ne sont pas clairement applicables à la fonction publique territoriale ; ils restent affichés comme pistes et sont exclus de l'analyse IA.")
'''
if case_law_anchor in source:
    source = source.replace(case_law_anchor, scope_warning, 1)
elif "Certains textes réglementaires repérés ne sont pas clairement applicables" not in source:
    raise RuntimeError("Emplacement du message de prudence FPT introuvable.")

orchestrator_path.write_text(source, encoding="utf-8")
compile(source, str(orchestrator_path), "exec")

ai_path = ROOT / "backend/app/ai_provider.py"
ai_source = ai_path.read_text(encoding="utf-8")
prompt_anchor = "- Respecte strictement leur provenance, leur statut et leur temporalité ; ne déduis jamais leur applicabilité de leur seule présence."
prompt_replacement = prompt_anchor + "\n- Pour les textes réglementaires hors CGFP, vérifie le champ de la fonction publique : un texte FPE ou FPH n'est pas une règle FPT. Les textes de périmètre incertain sont des pistes à vérifier et ne doivent pas fonder une conclusion."
if prompt_anchor in ai_source:
    ai_source = ai_source.replace(prompt_anchor, prompt_replacement, 1)
elif "un texte FPE ou FPH n'est pas une règle FPT" not in ai_source:
    raise RuntimeError("Règle de périmètre FPT du prompt IA introuvable.")

serialization_anchor = '''                    "statut_source": s.get("source_status"), "type_contenu": s.get("content_kind"),
'''
serialization_replacement = serialization_anchor + '''                    "perimetre_fonction_publique": s.get("public_service_scope"),
                    "eligibilite_analyse": s.get("analysis_eligible"),
'''
if serialization_anchor in ai_source:
    ai_source = ai_source.replace(serialization_anchor, serialization_replacement, 1)
elif '"perimetre_fonction_publique": s.get("public_service_scope")' not in ai_source:
    raise RuntimeError("Emplacement des métadonnées de périmètre dans le prompt IA introuvable.")

ai_path.write_text(ai_source, encoding="utf-8")
compile(ai_source, str(ai_path), "exec")

chat_logic_path = ROOT / "frontend/chat-logic.js"
if chat_logic_path.exists():
    chat_logic = chat_logic_path.read_text(encoding="utf-8")
    integrity_line = '      citation_integrity: s.citation_integrity ? { valid: s.citation_integrity.valid === true } : null,\n'
    eligibility_line = integrity_line + '      analysis_eligible: s.analysis_eligible !== false,\n'
    if integrity_line in chat_logic:
        chat_logic = chat_logic.replace(integrity_line, eligibility_line, 1)
    elif 'analysis_eligible: s.analysis_eligible !== false' not in chat_logic:
        raise RuntimeError("Métadonnée d'éligibilité FPT introuvable dans chat-logic.js.")
    chat_logic_path.write_text(chat_logic, encoding="utf-8")

frontend_app_path = ROOT / "frontend/app.js"
if frontend_app_path.exists():
    frontend_app = frontend_app_path.read_text(encoding="utf-8")
    old_selectable = '&& s.citation_integrity && s.citation_integrity.valid === true;'
    new_selectable = '&& s.analysis_eligible !== false && s.citation_integrity && s.citation_integrity.valid === true;'
    if old_selectable in frontend_app:
        frontend_app = frontend_app.replace(old_selectable, new_selectable, 1)
    elif new_selectable not in frontend_app:
        raise RuntimeError("Garde de sélection des sources introuvable dans app.js.")
    frontend_app_path.write_text(frontend_app, encoding="utf-8")

print("FPT scope filter applied: FPE/FPH and ambiguous regulatory texts remain visible but are excluded from Gemini.")
