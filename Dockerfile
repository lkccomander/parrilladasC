FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
COPY backend/requirements.lock /app/requirements.lock
RUN pip install -r requirements.lock
COPY backend /app/backend
RUN pip install --no-deps --no-build-isolation /app/backend \
    && useradd --create-home --uid 10001 appuser
USER appuser
WORKDIR /app/backend
EXPOSE 8000
CMD ["sh", "-c", "exec uvicorn \"${APP_MODULE:-parrilladas.main:create_app}\" --factory --host 0.0.0.0 --port \"${PORT:-8000}\""]
