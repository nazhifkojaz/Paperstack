FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app/packages/backend

COPY packages/backend/pyproject.toml packages/backend/uv.lock ./
RUN uv sync --frozen --no-dev

COPY packages/backend/alembic.ini ./
COPY packages/backend/alembic ./alembic
COPY packages/backend/app ./app

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
