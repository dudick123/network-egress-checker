FROM python:3.14-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src/ src/
RUN uv sync --frozen --no-dev

FROM python:3.14-slim

RUN groupadd --gid 1000 egress-checker \
    && useradd --uid 1000 --gid 1000 --shell /bin/bash egress-checker

COPY --from=builder /app/.venv /app/.venv

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8080 9090

USER egress-checker

ENTRYPOINT ["python", "-m", "egress_checker"]
