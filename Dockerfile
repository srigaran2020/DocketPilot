FROM python:3.11.9-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DEFAULT_TIMEOUT=180 \
    PIP_RETRIES=15

WORKDIR /app
COPY requirements.txt constraints.txt ./
RUN pip install --no-cache-dir -r requirements.txt -c constraints.txt

COPY alembic.ini ./
COPY migrations ./migrations
COPY docketpilot ./docketpilot

RUN useradd --create-home appuser
USER appuser

EXPOSE 8000
# Apply database migrations, then serve the API.
CMD ["sh", "-c", "alembic upgrade head && uvicorn docketpilot.api.main:app --host 0.0.0.0 --port 8000"]
