FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/backend

WORKDIR /app

COPY *.zip /tmp/kit.zip
COPY secure_main.py /tmp/secure_main.py
COPY patch_runtime.py /tmp/patch_runtime.py
COPY pwa /tmp/pwa

RUN python -c "import zipfile; zipfile.ZipFile('/tmp/kit.zip').extractall('/tmp/kit')" \
 && cp -r /tmp/kit/Dikevia_Chatbot_V1_Kit_Developpeur/. /app/ \
 && cp /tmp/secure_main.py /app/backend/secure_main.py \
 && cp /tmp/pwa/* /app/frontend/ \
 && python -c 'from pathlib import Path; p=Path("/app/frontend/index.html"); s=p.read_text(); s=s.replace("</head>", """<link rel="manifest" href="/manifest.webmanifest"><link rel="stylesheet" href="/voice.css"><meta name="theme-color" content="#173b63"><meta name="mobile-web-app-capable" content="yes"><meta name="apple-mobile-web-app-capable" content="yes"><meta name="apple-mobile-web-app-title" content="Dikevia"></head>""", 1); s=s.replace("""<script src="app.js"></script>""", """<script src="app.js"></script><script src="voice.js"></script>""", 1); s=s.replace("</body>", """<script>if ("serviceWorker" in navigator) { window.addEventListener("load", () => navigator.serviceWorker.register("/sw.js").catch(() => {})); }</script></body>""", 1); p.write_text(s)' \
 && python /tmp/patch_runtime.py \
 && rm -rf /tmp/kit /tmp/kit.zip /tmp/secure_main.py /tmp/patch_runtime.py /tmp/pwa

RUN pip install --no-cache-dir -r backend/requirements.txt \
 && useradd --create-home app \
 && chown -R app:app /app

USER app

EXPOSE 8000

CMD ["sh", "-c", "uvicorn secure_main:app --app-dir backend --host 0.0.0.0 --port ${PORT:-8000}"]
