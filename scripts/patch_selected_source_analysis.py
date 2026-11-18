from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
import tempfile, shutil, re, sys

ROOT = Path(__file__).resolve().parent.parent
archives = [p for p in ROOT.glob("*.zip") if p.is_file()]
if len(archives) != 1:
    raise SystemExit(f"Expected one root ZIP archive, found {len(archives)}")
archive = archives[0]
prefix = "Dikevia_Chatbot_V1_Kit_Developpeur/"
paths = {
    "orchestrator": prefix + "backend/app/orchestrator.py",
    "main": prefix + "backend/dev_main.py",
    "ai": prefix + "backend/app/ai_provider.py",
    "appjs": prefix + "frontend/app.js",
    "css": prefix + "frontend/app.css",
}

with tempfile.TemporaryDirectory() as td:
    temp = Path(td) / archive.name
    with ZipFile(archive, "r") as src, ZipFile(temp, "w", ZIP_DEFLATED) as dst:
        names = set(src.namelist())
        for key, path in paths.items():
            if path not in names:
                raise SystemExit(f"Missing expected file in ZIP: {path}")
        for info in src.infolist():
            data = src.read(info.filename)
            if info.filename in paths.values():
                key = next(k for k, v in paths.items() if v == info.filename)
                text = data.decode("utf-8")

                if key == "orchestrator":
                    old = "class LegalOrchestrator:\n    async def ask(self, request: AskRequest, organization_id: str, conn=None, conversation_history: list[dict] | None = None) -> AskResponse:"
                    new = '''def source_selection_key(source: dict) -> str:
    identity = source.get("article") or source.get("official_number") or source.get("case_number") or source.get("source_id") or source.get("title") or ""
    return f"{source.get('source_type') or 'SOURCE'}|{identity}"


class LegalOrchestrator:
    async def ask(self, request: AskRequest, organization_id: str, conn=None,
                  conversation_history: list[dict] | None = None,
                  selected_source_keys: list[str] | None = None) -> AskResponse:'''
                    if old not in text: raise SystemExit("orchestrator signature anchor not found")
                    text = text.replace(old, new, 1)

                    old = '''        if not any(s.get("source_type") in {"LEGIFRANCE_API", "LEGIFRANCE_LODA"} for s in sources) and not usable_permanent and not usable_local:'''
                    new = '''        selected_key_set = set(selected_source_keys or [])
        selected_sources: list[dict] = []
        if selected_key_set:
            for source in sources:
                integrity = source.get("citation_integrity") or {}
                if (source_selection_key(source) in selected_key_set
                        and source.get("content_kind") != "METADATA"
                        and source.get("source_type") != "LEGIFRANCE_CETAT_SEARCH"
                        and integrity.get("valid") is True):
                    if source.get("source_type") == "CGFP_SNAPSHOT":
                        selected_sources.append({
                            **source,
                            "reference_role": "BASELINE_CONTEXT_ONLY",
                            "temporal_status": "SNAPSHOT_ONLY_NOT_TEMPORALLY_VERIFIED",
                        })
                    else:
                        selected_sources.append(source)
            if not selected_sources:
                return AskResponse(
                    request_id=request_id,
                    verification_status="NON_VERIFIE",
                    answer="Aucun des textes sélectionnés ne peut être analysé : leur contenu ou leur intégrité documentaire n'est pas suffisamment vérifié.",
                    sources=sources,
                    missing_information=["Sélectionnez des textes dont le contenu intégral ou l'extrait vérifié est disponible."],
                )

        if not selected_sources and not any(s.get("source_type") in {"LEGIFRANCE_API", "LEGIFRANCE_LODA"} for s in sources) and not usable_permanent and not usable_local:'''
                    if old not in text: raise SystemExit("orchestrator source guard anchor not found")
                    text = text.replace(old, new, 1)

                    old = '''        if parsed_date is None:
            ai_answer = None
            missing.insert(0, "Analyse juridique contextualisée suspendue : préciser la date des faits pour vérifier la version applicable. La date du jour n'est utilisée que pour le repérage documentaire.")
        else:'''
                    new = '''        if parsed_date is None and not selected_sources:
            ai_answer = None
            missing.insert(0, "Analyse juridique contextualisée suspendue : préciser la date des faits pour vérifier la version applicable. La date du jour n'est utilisée que pour le repérage documentaire.")
        else:'''
                    if old not in text: raise SystemExit("orchestrator missing-date anchor not found")
                    text = text.replace(old, new, 1)

                    old = '''                ai_sources = cgfp_context_sources + verified_sources if verified_sources else []'''
                    new = '''                ai_sources = selected_sources if selected_sources else (cgfp_context_sources + verified_sources if verified_sources else [])
                if selected_sources and parsed_date is None:
                    missing.insert(0, "Date des faits absente : l'IA explique uniquement les textes sélectionnés et ne peut pas confirmer leur applicabilité à la date de la situation.")'''
                    if old not in text: raise SystemExit("orchestrator ai-source anchor not found")
                    text = text.replace(old, new, 1)

                elif key == "main":
                    old = '''class ChatQuestion(BaseModel):
    question: str = Field(min_length=8, max_length=5000)
    facts_date: str | None = None
    history: list[dict[str, Any]] = Field(default_factory=list, max_length=12)'''
                    new = '''class ChatQuestion(BaseModel):
    question: str = Field(min_length=8, max_length=5000)
    facts_date: str | None = None
    history: list[dict[str, Any]] = Field(default_factory=list, max_length=12)
    selected_source_keys: list[str] | None = Field(default=None, max_length=12)'''
                    if old not in text: raise SystemExit("dev_main request model anchor not found")
                    text = text.replace(old, new, 1)
                    old = 'request, organization_id="CHATBOT_V1_LOCAL_ONLY", conn=None, conversation_history=history,'
                    new = old + "\n                selected_source_keys=payload.selected_source_keys,"
                    if old not in text: raise SystemExit("dev_main orchestrator call anchor not found")
                    text = text.replace(old, new, 1)

                elif key == "ai":
                    old = '''- Si la date des faits ou une information déterminante manque, indique-le clairement et demande une seule précision utile au maximum.'''
                    new = '''- Si la date des faits ou une information déterminante manque, indique-le clairement et demande une seule précision utile au maximum.
- Sans date des faits, tu peux expliquer le contenu des textes sélectionnés, mais tu ne dois jamais affirmer qu'ils étaient applicables à la situation à une date donnée.
- Lorsque des textes sont explicitement sélectionnés, analyse uniquement ces textes ; distingue leur contenu, leur portée et les limites de vérification.'''
                    if old not in text: raise SystemExit("AI prompt anchor not found")
                    text = text.replace(old, new, 1)
                    old = '''"extrait": s.get("excerpt") or s.get("text", "")[:1800],'''
                    new = '''"extrait": (s.get("text") or s.get("excerpt") or "")[:7000],'''
                    if old not in text: raise SystemExit("AI full-text anchor not found")
                    text = text.replace(old, new, 1)

                elif key == "appjs":
                    old = '''  function renderSources(sources) {
    const d = el("details"); d.append(el("summary", null, "Sources juridiques (" + sources.length + ")"));
    const box = el("div");
    sources.forEach(s => {
      const w = el("div", "src");
      w.append(el("b", null, (s.title || s.source_id || "Source") + (s.article && !(s.title || "").includes(s.article) ? " — " + s.article : "")));
      const t = L.temporalInfo(s.temporal_status);
      w.append(el("span", "kind", L.sourceKind(s) + " · " + t.label + (s.page_start ? " · pages " + s.page_start + "–" + s.page_end : "")));
      if (s.excerpt) w.append(el("p", null, s.excerpt));
      const url = safeUrl(s.official_url);
      if (url) { const a = el("a", null, "Consulter sur Légifrance"); a.href = url; a.target = "_blank"; a.rel = "noopener noreferrer"; w.append(a); }
      box.append(w);
    });
    d.append(box); return d;
  }'''
                    new = '''  function sourceSelectionKey(s) {
    const identity = s.article || s.official_number || s.case_number || s.source_id || s.title || "";
    return (s.source_type || "SOURCE") + "|" + identity;
  }

  async function analyzeSelected(message, selectedKeys) {
    if (busy || !selectedKeys.length) return;
    const conv = store.current();
    const history = L.buildHistory(conv ? conv.messages : [], 12);
    busy = true; $("btnSend").disabled = true;
    const typing = el("div", "typing", "Analyse des textes sélectionnés avec l'IA…");
    $("messages").append(typing); $("chat").scrollTop = $("chat").scrollHeight;
    let reply;
    try {
      const r = await api("/api/v1/chat/ask", { method: "POST", body: JSON.stringify({
        question: message.question, facts_date: message.factsDate || null, history,
        selected_source_keys: selectedKeys
      }) });
      if (r.ok && r.data) reply = {
        role: "assistant", content: r.data.answer || "Aucune réponse exploitable.",
        status: r.data.verification_status, sources: L.trimSources(r.data.sources),
        missing: (r.data.missing_information || []).slice(0, 20),
        question: message.question, factsDate: message.factsDate, selectionDone: true
      };
      else reply = { role: "assistant", content: L.friendlyNetworkError(null, r.status, r.data && r.data.detail),
        status: "NON_VERIFIE", sources: [], missing: [], selectionDone: true };
    } catch (e) {
      reply = { role: "assistant", content: L.friendlyNetworkError(e, 0),
        status: "NON_VERIFIE", sources: [], missing: [], selectionDone: true };
    }
    store.addMessage(reply); busy = false; $("btnSend").disabled = false; renderAll();
  }

  function renderSources(sources, message) {
    const d = el("details"); d.append(el("summary", null, "Sources juridiques (" + sources.length + ")"));
    const box = el("div"), selectable = [];
    sources.forEach(s => {
      const w = el("div", "src");
      const title = (s.title || s.source_id || "Source") + (s.article && !(s.title || "").includes(s.article) ? " — " + s.article : "");
      const canSelect = !message.selectionDone && s.content_kind !== "METADATA"
        && s.source_type !== "LEGIFRANCE_CETAT_SEARCH"
        && s.citation_integrity && s.citation_integrity.valid === true;
      if (canSelect) {
        const label = el("label", "sourcepick");
        const check = el("input"); check.type = "checkbox"; check.value = sourceSelectionKey(s);
        label.append(check, document.createTextNode(" Analyser ce texte"));
        w.append(label); selectable.push(check);
      }
      w.append(el("b", null, title));
      const t = L.temporalInfo(s.temporal_status);
      w.append(el("span", "kind", L.sourceKind(s) + " · " + t.label + (s.page_start ? " · pages " + s.page_start + "–" + s.page_end : "")));
      if (s.excerpt) w.append(el("p", null, s.excerpt));
      const url = safeUrl(s.official_url);
      if (url) { const a = el("a", null, "Consulter sur Légifrance"); a.href = url; a.target = "_blank"; a.rel = "noopener noreferrer"; w.append(a); }
      box.append(w);
    });
    if (selectable.length) {
      const action = el("button", "selectbtn", "Analyser les textes sélectionnés");
      action.type = "button"; action.disabled = true;
      selectable.forEach(c => c.addEventListener("change", () => {
        action.disabled = !selectable.some(item => item.checked);
      }));
      action.onclick = () => analyzeSelected(message, selectable.filter(c => c.checked).map(c => c.value));
      box.append(action);
      const note = el("p", "small", "La sélection est vérifiée côté serveur. Sans date des faits, l'IA explique le texte sans certifier son applicabilité à votre situation.");
      box.append(note);
    }
    d.append(box); return d;
  }'''
                    if old not in text: raise SystemExit("frontend renderSources anchor not found")
                    text = text.replace(old, new, 1)
                    old = '''      if (m.sources && m.sources.length) extra.append(renderSources(m.sources));'''
                    new = '''      if (m.sources && m.sources.length) extra.append(renderSources(m.sources, m));'''
                    if old not in text: raise SystemExit("frontend renderMessage source anchor not found")
                    text = text.replace(old, new, 1)
                    old = '''if (r.ok && r.data) reply = { role: "assistant", content: r.data.answer || "Aucune réponse exploitable.", status: r.data.verification_status,
        sources: L.trimSources(r.data.sources), missing: (r.data.missing_information || []).slice(0, 20) };'''
                    new = '''if (r.ok && r.data) reply = { role: "assistant", content: r.data.answer || "Aucune réponse exploitable.", status: r.data.verification_status,
        sources: L.trimSources(r.data.sources), missing: (r.data.missing_information || []).slice(0, 20),
        question: q.value, factsDate: d.value, selectionDone: false };'''
                    if old not in text: raise SystemExit("frontend initial reply anchor not found")
                    text = text.replace(old, new, 1)

                elif key == "css":
                    text += '''
.sourcepick{display:flex;align-items:center;gap:7px;font-size:12px;color:var(--g);margin-bottom:6px}
.sourcepick input{width:18px;height:18px;flex:none;accent-color:var(--g)}
.selectbtn{display:block;width:100%;margin:10px 0 4px;padding:12px;border:0;border-radius:10px;background:var(--g);color:#fff;font-weight:700;min-height:44px}
.selectbtn:disabled{opacity:.45;cursor:not-allowed}
'''
                data = text.encode("utf-8")
            dst.writestr(info, data)

    shutil.copy2(temp, archive)

print(f"Patched {archive.name}")
