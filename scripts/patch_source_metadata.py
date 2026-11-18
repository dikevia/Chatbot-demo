from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
import tempfile, shutil

ROOT = Path(__file__).resolve().parent.parent
archives = list(ROOT.glob("*.zip"))
if len(archives) != 1:
    raise SystemExit(f"Expected one root ZIP archive, found {len(archives)}")
archive = archives[0]
target = "Dikevia_Chatbot_V1_Kit_Developpeur/frontend/chat-logic.js"
old = '''      source_type: s.source_type, title: s.title, article: s.article, official_number: s.official_number,
      excerpt: (s.excerpt || "").slice(0, MAX_EXCERPT), temporal_status: s.temporal_status,
      source_status: s.source_status, page_start: s.page_start, page_end: s.page_end,
      official_url: s.official_url || s.source_url || null,
'''
new = '''      source_type: s.source_type, source_id: s.source_id, title: s.title,
      article: s.article, official_number: s.official_number, case_number: s.case_number,
      content_kind: s.content_kind,
      citation_integrity: s.citation_integrity ? { valid: s.citation_integrity.valid === true } : null,
      excerpt: (s.excerpt || "").slice(0, MAX_EXCERPT), temporal_status: s.temporal_status,
      source_status: s.source_status, page_start: s.page_start, page_end: s.page_end,
      official_url: s.official_url || s.source_url || null,
'''
with tempfile.TemporaryDirectory() as td:
    temp = Path(td) / archive.name
    changed = False
    with ZipFile(archive, "r") as src, ZipFile(temp, "w", ZIP_DEFLATED) as dst:
        names = set(src.namelist())
        if target not in names:
            raise SystemExit(f"Missing expected file in ZIP: {target}")
        for info in src.infolist():
            data = src.read(info.filename)
            if info.filename == target:
                text = data.decode("utf-8")
                if old in text:
                    text = text.replace(old, new, 1)
                    changed = True
                elif new not in text:
                    raise SystemExit("trimSources source metadata block not found")
                data = text.encode("utf-8")
            dst.writestr(info, data)
    if changed:
        shutil.copy2(temp, archive)
        print(f"Updated source metadata in {archive.name}")
    else:
        print("Source metadata already preserved")
