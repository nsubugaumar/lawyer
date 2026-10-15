# LexDesk API, background worker and scheduler: one image, three commands.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# Tesseract and poppler let document search read scanned papers (OCR).
RUN apt-get update \
 && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng poppler-utils curl \
 && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --uid 1000 lexdesk
WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY --chown=lexdesk:lexdesk . .
RUN mkdir -p /vault /app/staticfiles && chown -R lexdesk:lexdesk /vault /app/staticfiles

USER lexdesk
# Static files for the office admin site. Keys are not needed to collect them.
RUN LEXDESK_DEBUG=1 python manage.py collectstatic --noinput

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD curl -fsS http://127.0.0.1:8000/api/v1/health/ || exit 1

# Migrations run once, from the api container, before it starts serving.
CMD ["sh", "-c", "python manage.py migrate --noinput && exec gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers ${GUNICORN_WORKERS:-3} --timeout 120 --access-logfile -"]
