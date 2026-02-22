# backend/Dockerfile
# Multi-stage Docker image for wxcode-adm backend.
#
# Base: python:3.11-slim (not alpine — asyncpg requires gcc for building)
# Production CMD: uvicorn wxcode_adm.main:app --host 0.0.0.0 --port 8060
# Dev override in docker-compose.yml: adds --reload and runs alembic upgrade head first.

FROM python:3.11-slim

WORKDIR /app

# Copy pyproject.toml first for Docker layer caching.
# Only re-installs dependencies when pyproject.toml changes.
COPY pyproject.toml .

# Install all project dependencies (including the package itself as editable-like).
# Using --no-cache-dir reduces image size.
RUN pip install --no-cache-dir -e "."

# Copy source code and alembic migration files.
COPY src/ ./src/
COPY alembic/ ./alembic/
COPY alembic.ini .

EXPOSE 8060

# Production default CMD.
# docker-compose.yml overrides this for development with --reload + alembic.
CMD ["uvicorn", "wxcode_adm.main:app", "--host", "0.0.0.0", "--port", "8060"]
