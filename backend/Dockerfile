# Build from the repo root so the contract is included:
#   docker build -f backend/Dockerfile -t pinni-backend .
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /usr/local/bin/uv

WORKDIR /app/backend
COPY agent /app/agent
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY contract /app/contract
COPY admin /app/admin
COPY backend/pinni ./pinni

ENV PINNI_DB_PATH=/data/pinni.db \
    PINNI_CONTRACT_DIR=/app/contract \
    PINNI_ADMIN_DIR=/app/admin
VOLUME /data
EXPOSE 8000
CMD ["uv", "run", "--no-sync", "uvicorn", "pinni.main:app", "--host", "0.0.0.0", "--port", "8000"]
