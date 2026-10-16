FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    FLASK_APP=app.py

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN useradd --create-home --uid 1001 appuser \
    && mkdir -p /tmp/uploads \
    && chown -R appuser:appuser /app /tmp/uploads

USER appuser

EXPOSE 5000

# gunicorn (production WSGI server) instead of the Werkzeug dev server.
# Set SECRET_KEY (and ideally WEB_CONCURRENCY) in the environment.
CMD ["sh", "-c", "gunicorn --bind 0.0.0.0:5000 --workers ${WEB_CONCURRENCY:-2} --threads 4 --timeout 120 app:app"]
