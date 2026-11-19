FROM python:3.11-slim-bookworm AS base

FROM base AS build
COPY --from=ghcr.io/astral-sh/uv:0.12.16 /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY src/ ./src/
RUN uv sync --locked --no-default-groups --group api --no-editable --no-python-downloads

FROM build AS postgres-driver
RUN uv pip install --python /app/.venv/bin/python --target /opt/geolife-postgres \
    --only-binary :all: --no-deps "psycopg==3.3.0" "psycopg-binary==3.3.0" "typing-extensions==4.16.0"

FROM base AS runtime
WORKDIR /app
COPY --from=build /app/.venv /app/.venv
COPY openapi.yaml ./
ENV PYTHONDONTWRITEBYTECODE=1
USER 10001:10001
EXPOSE 8000
STOPSIGNAL SIGINT
CMD ["/app/.venv/bin/python", "-m", "geolife_inference.api", "--host", "0.0.0.0"]

FROM runtime AS sqlite-demo
COPY --from=demo_snapshot --chmod=0444 geolife.sqlite3 /app/geolife.sqlite3
ENV GEOLIFE_SQLITE_PATH=/app/geolife.sqlite3

FROM runtime AS postgres
COPY --from=postgres-driver /opt/geolife-postgres /opt/geolife-postgres
ENV PYTHONPATH=/opt/geolife-postgres

FROM runtime AS api
