FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/backend

WORKDIR /app

COPY *.zip /tmp/kit.zip
COPY secure_main.py /tmp/secure_main.py

RUN python -c "import zipfile; zipfile.ZipFile('/tmp/kit.zip').extractall('/tmp/kit')" \
 && cp -r /tmp/kit/Dikevia_Chatbot_V1_Kit_Developpeur/. /app/ \
 && cp /tmp/secure_main.py /app/backend/secure_main.py \
 && rm -rf /tmp/kit /tmp/kit.zip /tmp/secure_main.py

RUN pip install --no-cache-dir -r backend/requirements.txt \
 && useradd --create-home app \
 && chown -R app:app /app

USER app

EXPOSE 8000

CMD ["sh", "-c", "uvicorn secure_main:app --app-dir backend --host 0.0.0.0 --port ${PORT:-8000}"]
