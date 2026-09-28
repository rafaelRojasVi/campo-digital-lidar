.PHONY: setup lint format format-check typecheck test test-api docs-check architecture-check secret-check dependency-audit check db-test-up db-test-reset db-test-down migration-check persistence-check lidar-dev lidar-status lidar-stop transelec-dev transelec-status transelec-stop campo-demo campo-status campo-stop ensure-platform-db platform-local platform-worker platform-worker-concurrency

N ?= 2

setup:
	uv sync --all-extras --dev

lint:
	uv run ruff check .

format:
	uv run ruff format .

format-check:
	uv run ruff format --check .

typecheck:
	uv run mypy .

test:
	uv run pytest

test-api:
	uv run pytest apps/api/tests

docs-check:
	uv run python scripts/check_doc_links.py

architecture-check:
	uv run python scripts/check_architecture_boundaries.py

secret-check:
	./scripts/check_secrets.sh

dependency-audit:
	./scripts/check_dependency_vulnerabilities.sh

check: format-check lint typecheck architecture-check test docs-check

db-test-up:
	docker compose up -d --wait postgres-test

db-test-reset:
	docker compose rm -sf postgres-test
	docker compose up -d --wait postgres-test

db-test-down:
	docker compose rm -sf postgres-test

migration-check: db-test-reset
	APP_ENV=test \
	POSTGRES_DB=campo_digital_test \
	POSTGRES_USER=campo_digital_test \
	POSTGRES_PASSWORD=campo_digital_test \
	POSTGRES_HOST=127.0.0.1 \
	POSTGRES_PORT=5433 \
	PYTHONPATH=apps/api \
	uv run python scripts/migration_check.py

persistence-check: migration-check
	APP_ENV=test \
	POSTGRES_DB=campo_digital_test \
	POSTGRES_USER=campo_digital_test \
	POSTGRES_PASSWORD=campo_digital_test \
	POSTGRES_HOST=127.0.0.1 \
	POSTGRES_PORT=5433 \
	PYTHONPATH=apps/api \
	uv run pytest -q apps/api/integration_tests

lidar-dev:
	uv run --extra api python scripts/lidar_dev.py up

lidar-status:
	uv run python scripts/lidar_dev.py status

lidar-stop:
	uv run python scripts/lidar_dev.py stop

transelec-dev:
	uv run --extra api python scripts/transelec_dev.py up

transelec-status:
	uv run python scripts/transelec_dev.py status

transelec-stop:
	uv run python scripts/transelec_dev.py stop

campo-demo:
	uv run --extra api python scripts/campo_demo.py up

campo-status:
	uv run python scripts/campo_demo.py status

campo-stop:
	uv run python scripts/campo_demo.py stop

# Local platform ingestion/access foundation. See docs/superpowers/plans/
# 2026-09-01-platform-ingestion-access-foundation.md. Requires a local .env
# (copy .env.example) with POSTGRES_PASSWORD set for the dev database.
#
# ensure-platform-db is the one shared readiness step (bring up `postgres`,
# apply migrations to head) used by every local entry point that touches the
# shared platform schema — this target, lidar-dev/campo-demo (via
# scripts/lidar_dev.py), and the worker targets below. See
# scripts/_platform_db.py for why this gives migrations a single,
# predictable owner without requiring only one process be allowed to run
# them.
ensure-platform-db:
	uv run python scripts/ensure_platform_db.py

# Foreground, --reload dev server for the shared app.main:app process — the
# SAME process lidar-dev/campo-demo start in the background on a
# free-chosen port. scripts/platform_local.py refuses to start (rather than
# collide on port 8000) if lidar-dev/campo-demo already owns a running
# instance; use that instance instead, or `make lidar-stop` first.
platform-local:
	uv run python scripts/platform_local.py

platform-worker: ensure-platform-db
	APP_ENV=development PYTHONPATH=apps/api uv run python -m app.worker

# Run N concurrent local workers claiming from the same PostgreSQL queue via
# SELECT ... FOR UPDATE SKIP LOCKED. Override with `make platform-worker-concurrency N=4`.
platform-worker-concurrency: ensure-platform-db
	@for i in $$(seq 1 $(N)); do \
		APP_ENV=development PYTHONPATH=apps/api uv run python -m app.worker & \
	done; \
	wait

