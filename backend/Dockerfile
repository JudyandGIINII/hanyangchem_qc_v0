FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY backend/pyproject.toml backend/uv.lock /app/backend/
RUN pip install --no-cache-dir uv==0.11.14 && uv sync --project /app/backend --no-dev
COPY backend /app/backend
ENV PYTHONPATH=/app/backend/src
CMD ["uv", "run", "--project", "/app/backend", "uvicorn", "hyc_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
