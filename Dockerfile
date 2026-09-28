# Campo Digital API — Transelec production container.
#
# One container serves both the JSON API (/transelec, /api/transelec) and
# the built React dashboard from the same origin (see
# apps/api/app/dashboard_static.py) — no separate frontend origin, no CORS
# surface. See docs/platform/production-platform-v1.md for the target
# production architecture (Cloud Run) and
# docs/platform/environments-and-costs.md for cost context.
#
# This packages the SAME shared FastAPI modular monolith (apps/api/app/
# main.py) LiDAR and the platform ingestion API already run — it adds no
# Transelec-specific backend behavior beyond mounting the built dashboard
# and the /api/* routing alias every browser bundle on this platform already
# expects (see app.main). Auth is the platform's real session/CSRF/RBAC
# stack; dev-only auth stays gated to APP_ENV=development exactly as it is
# everywhere else this app runs (see app.main._resolve_app_env and
# apps/api/tests/test_main_dev_auth_gate.py).
#
# Adapted from the SHAPE of feat/transelec-hosted-pilot-v1's Dockerfile
# (superseded prior art — "PR #47" in
# docs/superpowers/specs/2026-09-02-transelec-hosted-pilot-v2-design.md),
# not copied: that draft predates this branch's real session/CSRF/RBAC work
# and its own CAMPO_TRANSELEC_ADMIN_TOKEN model, both superseded here. This
# image also does not bundle a Cloud Storage SDK layer — this codebase's
# app.object_store has no GCS backend yet, so that would be speculative
# runtime weight with no code path to use it.

# ---- Stage 1: build the Transelec dashboard's static assets -----------------
FROM node:24.19.0-slim AS dashboard-build

WORKDIR /dashboard

COPY products/transelect/dashboard/package.json products/transelect/dashboard/package-lock.json ./
RUN npm ci

COPY products/transelect/dashboard/ ./
RUN npm run build

# ---- Stage 2: Python runtime -------------------------------------------------
FROM python:3.12-slim AS runtime

# Pinned to match [tool.uv].required-version in pyproject.toml.
COPY --from=ghcr.io/astral-sh/uv:0.12.5 /uv /uvx /bin/

WORKDIR /app

# Only what hatchling needs to build/install this project's local packages
# (see [tool.hatch.build.targets.wheel] in pyproject.toml), so this layer
# stays cached across pure application-code edits below.
COPY pyproject.toml uv.lock README.md ./
COPY products/lidar/src ./products/lidar/src
COPY products/transelect/src ./products/transelect/src

# --no-dev excludes lint/test/notebook tooling. "api" and "transelec" are the
# only extras this service needs at runtime (matches render.yaml's own
# buildCommand for the shared platform API service).
RUN uv sync --frozen --no-dev --extra api --extra transelec

COPY apps/api ./apps/api
COPY migrations ./migrations
COPY alembic.ini ./alembic.ini
COPY --from=dashboard-build /dashboard/dist ./products/transelect/dashboard/dist
COPY scripts/container/entrypoint.sh /usr/local/bin/campo-entrypoint

RUN chmod 0755 /usr/local/bin/campo-entrypoint && \
    groupadd --system campo && \
    useradd --system --gid campo --home-dir /app --no-create-home campo && \
    chown -R campo:campo /app

USER campo

ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    PORT=8080

EXPOSE 8080

# Cloud Run (and any other host) injects $PORT at runtime; always bind
# 0.0.0.0. --no-sync skips uv's dependency-resolution check so startup never
# touches the network. No migration runs here — see
# docs/platform/production-platform-v1.md: "no implicit destructive
# migration on app startup"; apply `alembic upgrade head` as a separate
# release step against this same image.
# See scripts/container/entrypoint.sh: a no-op under the default non-root
# user; when a host starts the container as root to mount a root-owned
# volume, it hands CAMPO_OBJECT_STORE_ROOT to `campo` and drops privileges.
ENTRYPOINT ["/usr/local/bin/campo-entrypoint"]
CMD ["sh", "-c", "exec uv run --frozen --no-sync uvicorn app.main:app --app-dir apps/api --host 0.0.0.0 --port ${PORT}"]
