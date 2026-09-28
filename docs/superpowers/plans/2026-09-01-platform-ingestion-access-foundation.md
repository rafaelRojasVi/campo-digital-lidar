# Platform Ingestion + Access Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task (executed inline, same session, by the same agent that wrote it). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prove, locally, that Campo Digital can operate as a multi-user
platform: authenticated dev users, product-scoped RBAC, a controlled file
intake boundary, immutable content-addressed object storage, durable
PostgreSQL-backed async job processing safe under concurrent workers, minimal
per-product inspection adapters, and an auditable end-to-end demo through the
existing portal — without inventing business workflow status, without cloud
provisioning, and without duplicating the existing provenance model.

**Architecture:** Extend the existing `platform.source_snapshot` /
`source_observation` provenance chain (do not duplicate it) with two new
migrations: `0005` (access — `app_user`, `product_grant`, `audit_event`) and
`0006` (ingestion — `upload_session`, `ingestion_run`, `processing_job`,
`processing_attempt`, `generated_artifact`, plus an `object_storage_key`
column added to `source_snapshot`). All new persistence follows the
established raw-SQL-via-`sqlalchemy.text()` style (no ORM) with the
`ON CONFLICT ... DO NOTHING` + re-select idempotency pattern already used in
`app/source_provenance.py`. A filesystem-backed `LocalObjectStore` implements
a small provider-neutral `ObjectStore` protocol. A dev-only `DevAuth` adapter
issues an in-process session cookie mapped to a seeded `app_user`, hard-gated
against `APP_ENV == "production"`. RBAC is a pure function over
`(role, action)` plus a per-product grant lookup — never conflated with
authentication. Three lightweight, read-only "inspection" adapters (LiDAR
header via the existing `lidar_io.inspect.inspect_las`, Transelec workbook via
the existing `transelec_ingestion.xlsx_contract`, and a new
zip-slip-hardened Forestry shapefile-family ZIP inspector) run synchronously
at upload time; a `processing_job` row is queued for the same inspection to
run again asynchronously via a `SELECT ... FOR UPDATE SKIP LOCKED` worker,
demonstrating the durable job model without a message broker. A new
`/ingesta` page in the existing `apps/portal` React app drives the flow
against a standalone FastAPI process started by a new `make platform-local`
target, kept decoupled from the existing `make campo-demo` orchestration.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy Core (no ORM), Alembic,
psycopg3, pytest, `uv`; React 19 + TypeScript + Vite (`apps/portal`, plain
`fetch`, no added dependencies).

**Spec:** PARTS 2–12 of the task brief given in this session (see
conversation). Ground truth: `docs/platform/source-ingestion.md`,
`docs/platform/security-model.md`, `docs/adr/ADR-002-source-provenance-identity.md`,
`apps/api/app/source_provenance.py`, `apps/api/app/source_discovery.py`,
`config/source-catalog.yaml` (product keys: `lidar`, `forestry`, `transelect`),
`products/lidar/src/lidar_io/inspect.py`, `products/transelect/src/transelec_ingestion/xlsx_contract.py`.

## Global Constraints

- Product keys are exactly `lidar`, `forestry`, `transelect` (matches
  `config/source-catalog.yaml`; note the repository spelling `transelect`,
  stakeholder spelling `Transelec` per `CLAUDE.md`).
- Do not create a new content-snapshot concept — extend
  `platform.source_snapshot` (add `object_storage_key`), reuse
  `source_asset`/`source_observation`/`source_system` as-is.
- No Redis/Celery/Kafka/RabbitMQ/Kubernetes. Job durability lives in
  PostgreSQL only, via `SELECT ... FOR UPDATE SKIP LOCKED`.
- No cloud SDK imports anywhere in domain code. `ObjectStore` is the only
  storage abstraction domain code depends on.
- Dev auth must be structurally incapable of running when
  `APP_ENV == "production"` — enforced by a guard function called at
  construction time, with a dedicated test.
- Do not invent product-specific roles or business workflow statuses. Roles
  are exactly `admin`, `operator`, `viewer` per product grant. Job states are
  exactly `queued`, `running`, `succeeded`, `failed`.
- Never commit real client files. Tests use small synthetic fixtures only.
- Never log secrets or full source contents in audit events.
- All new raw SQL follows the existing constraint-naming convention
  (`ck_<table>_<name>`, `fk_<table>_<col>`, `pk_<table>`, `uq_<table>_<cols>`).
- `make check` (format, lint, mypy, architecture boundaries, full pytest,
  doc links) and `make persistence-check` (migration lifecycle +
  integration tests) must pass before the final commit.

## File Structure

New backend files:
- `migrations/versions/0005_establish_platform_access_foundation.py`
- `migrations/versions/0006_establish_platform_ingestion_foundation.py`
- `apps/api/app/object_store.py` — `ObjectStore` protocol + `LocalObjectStore`
- `apps/api/app/access.py` — `Role`, `ROLE_RANK`, `can()`, `ProductGrant` dataclass, `AuthorizationError`
- `apps/api/app/access_repository.py` — `app_user`/`product_grant` persistence
- `apps/api/app/dev_auth.py` — seeded identities, session issuance/lookup, production guard
- `apps/api/app/audit.py` — `record_audit_event()` persistence helper
- `apps/api/app/inspection/__init__.py`
- `apps/api/app/inspection/lidar_inspector.py` — wraps `lidar_io.inspect.inspect_las`
- `apps/api/app/inspection/transelec_inspector.py` — wraps `transelec_ingestion.xlsx_contract`
- `apps/api/app/inspection/forestry_inspector.py` — new zip-slip-hardened ZIP inspector
- `apps/api/app/jobs.py` — `enqueue_processing_job`, `claim_next_job`, `complete_job`, `fail_job`, `reap_stale_leases`
- `apps/api/app/worker.py` — worker loop CLI entrypoint (`uv run python -m app.worker`)
- `apps/api/app/routers/dev_auth.py` — `/auth/dev-login`, `/auth/me`, `/auth/logout`
- `apps/api/app/routers/ingestion.py` — `/ingesta/upload`, `/ingesta/jobs`, `/ingesta/jobs/{id}/retry`, `/ingesta/audit`
- Test files mirrored under `apps/api/tests/` (unit) and `apps/api/integration_tests/` (real DB), named per task below.

New frontend files:
- `apps/portal/src/pages/Ingesta.tsx` + `apps/portal/src/pages/Ingesta.test.tsx`
- `apps/portal/src/lib/platformApi.ts` — typed `fetch` wrapper for the platform API base URL

Modified files:
- `apps/api/app/main.py` — mount new routers
- `apps/portal/src/App.tsx` — route `/ingesta`
- `apps/portal/vite.config.ts` — dev proxy for `/api` (if not already present)
- `Makefile` — `platform-local`, `platform-worker`, `platform-worker-concurrency`

---

### Task 1: Migration `0005` — access foundation (`app_user`, `product_grant`, `audit_event`)

**Files:**
- Create: `migrations/versions/0005_establish_platform_access_foundation.py`
- Test: `apps/api/integration_tests/test_access_schema.py`

**Interfaces:**
- Produces: `platform.app_user(id, identity_kind, identity_key, display_name, email, created_at)`,
  `platform.product_grant(id, app_user_id, product_key, role, created_at)`,
  `platform.audit_event(id, occurred_at, actor_app_user_id, event_type, product_key, subject_kind, subject_id, metadata)`.

- [ ] **Step 1: Write the migration**

```python
"""Establish platform access foundation.

Revision ID: 0005
Revises: 0004
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PRODUCT_KEYS = ("lidar", "forestry", "transelect")
ROLE_KEYS = ("admin", "operator", "viewer")


def upgrade() -> None:
    op.create_table(
        "app_user",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("identity_kind", sa.Text(), nullable=False),
        sa.Column("identity_key", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("email", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint("btrim(identity_kind) <> ''", name="ck_app_user_identity_kind_nonempty"),
        sa.CheckConstraint("btrim(identity_key) <> ''", name="ck_app_user_identity_key_nonempty"),
        sa.CheckConstraint("btrim(display_name) <> ''", name="ck_app_user_display_name_nonempty"),
        sa.CheckConstraint(
            "email IS NULL OR btrim(email) <> ''", name="ck_app_user_email_nonempty"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_app_user"),
        sa.UniqueConstraint("identity_kind", "identity_key", name="uq_app_user_identity"),
        schema="platform",
    )

    op.create_table(
        "product_grant",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("app_user_id", sa.BigInteger(), nullable=False),
        sa.Column("product_key", sa.Text(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            f"product_key IN {PRODUCT_KEYS!r}",
            name="ck_product_grant_product_key_known",
        ),
        sa.CheckConstraint(f"role IN {ROLE_KEYS!r}", name="ck_product_grant_role_known"),
        sa.ForeignKeyConstraint(
            ["app_user_id"],
            ["platform.app_user.id"],
            name="fk_product_grant_app_user_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_product_grant"),
        sa.UniqueConstraint("app_user_id", "product_key", name="uq_product_grant_user_product"),
        schema="platform",
    )

    op.create_table(
        "audit_event",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("actor_app_user_id", sa.BigInteger(), nullable=True),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("product_key", sa.Text(), nullable=True),
        sa.Column("subject_kind", sa.Text(), nullable=True),
        sa.Column("subject_id", sa.Text(), nullable=True),
        sa.Column(
            "metadata",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.CheckConstraint("btrim(event_type) <> ''", name="ck_audit_event_event_type_nonempty"),
        sa.CheckConstraint(
            "product_key IS NULL OR btrim(product_key) <> ''",
            name="ck_audit_event_product_key_nonempty",
        ),
        sa.CheckConstraint(
            "subject_kind IS NULL OR btrim(subject_kind) <> ''",
            name="ck_audit_event_subject_kind_nonempty",
        ),
        sa.CheckConstraint(
            "subject_id IS NULL OR btrim(subject_id) <> ''",
            name="ck_audit_event_subject_id_nonempty",
        ),
        sa.ForeignKeyConstraint(
            ["actor_app_user_id"],
            ["platform.app_user.id"],
            name="fk_audit_event_actor_app_user_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_audit_event"),
        schema="platform",
    )
    op.create_index(
        "ix_audit_event_occurred_at",
        "audit_event",
        ["occurred_at"],
        unique=False,
        schema="platform",
    )


def downgrade() -> None:
    op.drop_index("ix_audit_event_occurred_at", table_name="audit_event", schema="platform")
    op.drop_table("audit_event", schema="platform")
    op.drop_table("product_grant", schema="platform")
    op.drop_table("app_user", schema="platform")
```

- [ ] **Step 2: Write the failing integration test**

```python
"""Schema-level checks for the platform access foundation."""

from __future__ import annotations

import pytest
from sqlalchemy import Connection, text
from sqlalchemy.exc import IntegrityError


def test_product_grant_rejects_unknown_role(integration_connection: Connection) -> None:
    user_id = integration_connection.execute(
        text(
            "INSERT INTO platform.app_user (identity_kind, identity_key, display_name) "
            "VALUES ('dev-local', 'alice', 'Alice') RETURNING id"
        )
    ).scalar_one()

    with pytest.raises(IntegrityError):
        integration_connection.execute(
            text(
                "INSERT INTO platform.product_grant (app_user_id, product_key, role) "
                "VALUES (:user_id, 'lidar', 'superadmin')"
            ),
            {"user_id": user_id},
        )


def test_product_grant_unique_per_user_and_product(integration_connection: Connection) -> None:
    user_id = integration_connection.execute(
        text(
            "INSERT INTO platform.app_user (identity_kind, identity_key, display_name) "
            "VALUES ('dev-local', 'bob', 'Bob') RETURNING id"
        )
    ).scalar_one()

    integration_connection.execute(
        text(
            "INSERT INTO platform.product_grant (app_user_id, product_key, role) "
            "VALUES (:user_id, 'forestry', 'operator')"
        ),
        {"user_id": user_id},
    )

    with pytest.raises(IntegrityError):
        integration_connection.execute(
            text(
                "INSERT INTO platform.product_grant (app_user_id, product_key, role) "
                "VALUES (:user_id, 'forestry', 'viewer')"
            ),
            {"user_id": user_id},
        )
```

- [ ] **Step 3: Run `make migration-check` and the new integration test**

```bash
export POSTGRES_PASSWORD=local-dev-only-not-secret
make migration-check
APP_ENV=test POSTGRES_DB=campo_digital_test POSTGRES_USER=campo_digital_test \
POSTGRES_PASSWORD=campo_digital_test POSTGRES_HOST=127.0.0.1 POSTGRES_PORT=5433 \
PYTHONPATH=apps/api uv run pytest apps/api/integration_tests/test_access_schema.py -v
```

Expected: migration-check head is now `0005`; both new tests pass.

---

### Task 2: Migration `0006` — ingestion/job foundation

**Files:**
- Create: `migrations/versions/0006_establish_platform_ingestion_foundation.py`
- Test: `apps/api/integration_tests/test_ingestion_schema.py`

**Interfaces:**
- Produces: `ALTER TABLE platform.source_snapshot ADD COLUMN object_storage_key text NULL` (unique when present, via partial index), `platform.upload_session`, `platform.ingestion_run`, `platform.processing_job`, `platform.processing_attempt`, `platform.generated_artifact`.
- Consumes: `platform.source_snapshot.id`, `platform.app_user.id` (from `0005`).

- [ ] **Step 1: Write the migration**

```python
"""Establish platform ingestion foundation.

Revision ID: 0006
Revises: 0005
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PRODUCT_KEYS = ("lidar", "forestry", "transelect")


def upgrade() -> None:
    op.add_column(
        "source_snapshot",
        sa.Column("object_storage_key", sa.Text(), nullable=True),
        schema="platform",
    )
    op.create_check_constraint(
        "ck_source_snapshot_object_storage_key_nonempty",
        "source_snapshot",
        "object_storage_key IS NULL OR btrim(object_storage_key) <> ''",
        schema="platform",
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_source_snapshot_object_storage_key "
        "ON platform.source_snapshot (object_storage_key) "
        "WHERE object_storage_key IS NOT NULL"
    )

    op.create_table(
        "upload_session",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("app_user_id", sa.BigInteger(), nullable=False),
        sa.Column("product_key", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
        sa.Column("original_filename", sa.Text(), nullable=False),
        sa.Column("declared_media_type", sa.Text(), nullable=True),
        sa.Column("source_snapshot_id", sa.BigInteger(), nullable=True),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            f"product_key IN {PRODUCT_KEYS!r}", name="ck_upload_session_product_key_known"
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'completed', 'failed')", name="ck_upload_session_status_known"
        ),
        sa.CheckConstraint(
            "btrim(original_filename) <> ''", name="ck_upload_session_original_filename_nonempty"
        ),
        sa.ForeignKeyConstraint(
            ["app_user_id"],
            ["platform.app_user.id"],
            name="fk_upload_session_app_user_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_snapshot_id"],
            ["platform.source_snapshot.id"],
            name="fk_upload_session_source_snapshot_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_upload_session"),
        schema="platform",
    )

    op.create_table(
        "ingestion_run",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("source_snapshot_id", sa.BigInteger(), nullable=False),
        sa.Column("product_key", sa.Text(), nullable=False),
        sa.Column("requested_by_app_user_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            f"product_key IN {PRODUCT_KEYS!r}", name="ck_ingestion_run_product_key_known"
        ),
        sa.ForeignKeyConstraint(
            ["source_snapshot_id"],
            ["platform.source_snapshot.id"],
            name="fk_ingestion_run_source_snapshot_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["requested_by_app_user_id"],
            ["platform.app_user.id"],
            name="fk_ingestion_run_requested_by",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_ingestion_run"),
        schema="platform",
    )

    op.create_table(
        "processing_job",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("ingestion_run_id", sa.BigInteger(), nullable=False),
        sa.Column("product_key", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="queued"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("requested_by_app_user_id", sa.BigInteger(), nullable=True),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_owner", sa.Text(), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            f"product_key IN {PRODUCT_KEYS!r}", name="ck_processing_job_product_key_known"
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed')",
            name="ck_processing_job_status_known",
        ),
        sa.CheckConstraint(
            "attempt_count >= 0", name="ck_processing_job_attempt_count_nonnegative"
        ),
        sa.CheckConstraint("max_attempts >= 1", name="ck_processing_job_max_attempts_positive"),
        sa.ForeignKeyConstraint(
            ["ingestion_run_id"],
            ["platform.ingestion_run.id"],
            name="fk_processing_job_ingestion_run_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["requested_by_app_user_id"],
            ["platform.app_user.id"],
            name="fk_processing_job_requested_by",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_processing_job"),
        schema="platform",
    )
    op.create_index(
        "ix_processing_job_status_created_at",
        "processing_job",
        ["status", "created_at"],
        unique=False,
        schema="platform",
    )

    op.create_table(
        "processing_attempt",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("processing_job_id", sa.BigInteger(), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("worker_id", sa.Text(), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "attempt_number >= 1", name="ck_processing_attempt_attempt_number_positive"
        ),
        sa.CheckConstraint(
            "btrim(worker_id) <> ''", name="ck_processing_attempt_worker_id_nonempty"
        ),
        sa.CheckConstraint(
            "status IN ('running', 'succeeded', 'failed')",
            name="ck_processing_attempt_status_known",
        ),
        sa.ForeignKeyConstraint(
            ["processing_job_id"],
            ["platform.processing_job.id"],
            name="fk_processing_attempt_processing_job_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_processing_attempt"),
        sa.UniqueConstraint(
            "processing_job_id", "attempt_number", name="uq_processing_attempt_job_attempt"
        ),
        schema="platform",
    )

    op.create_table(
        "generated_artifact",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("processing_job_id", sa.BigInteger(), nullable=False),
        sa.Column("artifact_kind", sa.Text(), nullable=False),
        sa.Column("storage_key", sa.Text(), nullable=False),
        sa.Column("byte_size", sa.BigInteger(), nullable=False),
        sa.Column("media_type", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "btrim(artifact_kind) <> ''", name="ck_generated_artifact_artifact_kind_nonempty"
        ),
        sa.CheckConstraint(
            "btrim(storage_key) <> ''", name="ck_generated_artifact_storage_key_nonempty"
        ),
        sa.CheckConstraint("byte_size >= 0", name="ck_generated_artifact_byte_size_nonnegative"),
        sa.ForeignKeyConstraint(
            ["processing_job_id"],
            ["platform.processing_job.id"],
            name="fk_generated_artifact_processing_job_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_generated_artifact"),
        schema="platform",
    )


def downgrade() -> None:
    op.drop_table("generated_artifact", schema="platform")
    op.drop_table("processing_attempt", schema="platform")
    op.drop_index(
        "ix_processing_job_status_created_at", table_name="processing_job", schema="platform"
    )
    op.drop_table("processing_job", schema="platform")
    op.drop_table("ingestion_run", schema="platform")
    op.drop_table("upload_session", schema="platform")
    op.execute("DROP INDEX platform.uq_source_snapshot_object_storage_key")
    op.drop_constraint(
        "ck_source_snapshot_object_storage_key_nonempty", "source_snapshot", schema="platform"
    )
    op.drop_column("source_snapshot", "object_storage_key", schema="platform")
```

- [ ] **Step 2: Write a failing integration test covering the lease/status constraints and the FK chain**

```python
"""Schema-level checks for the platform ingestion foundation."""

from __future__ import annotations

import pytest
from sqlalchemy import Connection, text
from sqlalchemy.exc import IntegrityError


def _make_snapshot(connection: Connection) -> int:
    system_id = connection.execute(
        text("INSERT INTO platform.source_system (system_key) VALUES ('test_system') RETURNING id")
    ).scalar_one()
    asset_id = connection.execute(
        text(
            "INSERT INTO platform.source_asset (source_system_id, identity_kind, identity_key) "
            "VALUES (:sid, 'relative_path', 'a.xlsx') RETURNING id"
        ),
        {"sid": system_id},
    ).scalar_one()
    return connection.execute(
        text(
            "INSERT INTO platform.source_snapshot (source_asset_id, content_sha256, byte_size) "
            "VALUES (:aid, repeat('a', 64), 10) RETURNING id"
        ),
        {"aid": asset_id},
    ).scalar_one()


def test_processing_job_rejects_unknown_status(integration_connection: Connection) -> None:
    snapshot_id = _make_snapshot(integration_connection)
    run_id = integration_connection.execute(
        text(
            "INSERT INTO platform.ingestion_run (source_snapshot_id, product_key) "
            "VALUES (:sid, 'transelect') RETURNING id"
        ),
        {"sid": snapshot_id},
    ).scalar_one()

    with pytest.raises(IntegrityError):
        integration_connection.execute(
            text(
                "INSERT INTO platform.processing_job (ingestion_run_id, product_key, status) "
                "VALUES (:rid, 'transelect', 'paused')"
            ),
            {"rid": run_id},
        )


def test_source_snapshot_object_storage_key_unique_when_present(
    integration_connection: Connection,
) -> None:
    snapshot_a = _make_snapshot(integration_connection)
    integration_connection.execute(
        text(
            "UPDATE platform.source_snapshot SET object_storage_key = 'sha256/dup' WHERE id = :id"
        ),
        {"id": snapshot_a},
    )

    system_id = integration_connection.execute(
        text(
            "INSERT INTO platform.source_system (system_key) VALUES ('test_system_2') RETURNING id"
        )
    ).scalar_one()
    asset_id = integration_connection.execute(
        text(
            "INSERT INTO platform.source_asset (source_system_id, identity_kind, identity_key) "
            "VALUES (:sid, 'relative_path', 'b.xlsx') RETURNING id"
        ),
        {"sid": system_id},
    ).scalar_one()
    snapshot_b = integration_connection.execute(
        text(
            "INSERT INTO platform.source_snapshot (source_asset_id, content_sha256, byte_size) "
            "VALUES (:aid, repeat('b', 64), 20) RETURNING id"
        ),
        {"aid": asset_id},
    ).scalar_one()

    with pytest.raises(IntegrityError):
        integration_connection.execute(
            text(
                "UPDATE platform.source_snapshot SET object_storage_key = 'sha256/dup' WHERE id = :id"
            ),
            {"id": snapshot_b},
        )
```

- [ ] **Step 3: Run migration-check and the new tests; verify full downgrade/upgrade cycle**

```bash
export POSTGRES_PASSWORD=local-dev-only-not-secret
make migration-check
make persistence-check
```

Expected: head is `0006`; all integration tests (old and new) pass.

---

### Task 3: `ObjectStore` protocol + `LocalObjectStore`

**Files:**
- Create: `apps/api/app/object_store.py`
- Test: `apps/api/tests/test_object_store.py`

**Interfaces:**
- Produces:
  ```python
  class ObjectStoreError(RuntimeError): ...


  class ObjectAlreadyExistsWithDifferentContentError(ObjectStoreError): ...


  @dataclass(frozen=True, slots=True)
  class StoredObject:
      key: str
      sha256: str
      byte_size: int
      media_type: str | None


  class ObjectStore(Protocol):
      def put(self, data: BinaryIO, *, media_type: str | None) -> StoredObject: ...
      def open(self, key: str) -> BinaryIO: ...
      def stat(self, key: str) -> StoredObject: ...
      def exists(self, key: str) -> bool: ...


  class LocalObjectStore:
      def __init__(self, root: Path) -> None: ...

      # implements ObjectStore
  ```
  Key scheme: `sha256/<first 2 hex chars>/<remaining 62 hex chars>` (git-style
  sharding to avoid huge flat directories). `media_type` is recorded in a
  sidecar `<key>.meta.json` (`{"media_type": ..., "byte_size": ...}`), never in
  the content file itself, so the stored bytes are exactly the original
  content — this is what `content_sha256` in `platform.source_snapshot` must
  match.
- Consumes: nothing beyond `pathlib`/`hashlib`/`os`.

- [ ] **Step 1: Write failing tests**

```python
"""Unit tests for the local filesystem-backed object store."""

from __future__ import annotations

import hashlib
import io
import os
from pathlib import Path

import pytest

from app.object_store import (
    LocalObjectStore,
    ObjectAlreadyExistsWithDifferentContentError,
)


@pytest.fixture
def store(tmp_path: Path) -> LocalObjectStore:
    return LocalObjectStore(tmp_path / "object-store")


def test_put_returns_sha256_identity_and_size(store: LocalObjectStore) -> None:
    content = b"hello campo digital"
    result = store.put(io.BytesIO(content), media_type="text/plain")

    assert result.sha256 == hashlib.sha256(content).hexdigest()
    assert result.byte_size == len(content)
    assert result.media_type == "text/plain"


def test_put_is_idempotent_for_identical_content(store: LocalObjectStore) -> None:
    content = b"same bytes"
    first = store.put(io.BytesIO(content), media_type="text/plain")
    second = store.put(io.BytesIO(content), media_type="text/plain")

    assert first.key == second.key


def test_open_returns_original_bytes(store: LocalObjectStore) -> None:
    content = b"round trip content"
    stored = store.put(io.BytesIO(content), media_type=None)

    with store.open(stored.key) as handle:
        assert handle.read() == content


def test_stat_matches_put_result(store: LocalObjectStore) -> None:
    content = b"stat me"
    stored = store.put(io.BytesIO(content), media_type="application/zip")

    stat_result = store.stat(stored.key)
    assert stat_result == stored


def test_exists_false_for_unknown_key(store: LocalObjectStore) -> None:
    assert store.exists("sha256/aa/" + "0" * 62) is False


def test_write_is_atomic_no_partial_file_on_crash(
    store: LocalObjectStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failure mid-write must never leave a corrupt object at the final key."""

    original_replace = os.replace

    def failing_replace(*args: object, **kwargs: object) -> None:
        raise OSError("simulated crash before atomic rename")

    monkeypatch.setattr(os, "replace", failing_replace)

    with pytest.raises(OSError):
        store.put(io.BytesIO(b"partial"), media_type=None)

    monkeypatch.setattr(os, "replace", original_replace)
    stored = store.put(io.BytesIO(b"partial"), media_type=None)
    assert store.exists(stored.key)


def test_key_rejects_path_traversal(store: LocalObjectStore) -> None:
    with pytest.raises(Exception):
        store.open("../../etc/passwd")


def test_key_rejects_absolute_path(store: LocalObjectStore) -> None:
    with pytest.raises(Exception):
        store.open("/etc/passwd")


def test_symlink_escape_is_rejected(store: LocalObjectStore, tmp_path: Path) -> None:
    outside = tmp_path / "outside.txt"
    outside.write_text("secret")

    stored = store.put(io.BytesIO(b"placeholder"), media_type=None)
    real_path = store.root / stored.key
    real_path.unlink()
    real_path.symlink_to(outside)

    with pytest.raises(Exception):
        store.open(stored.key)
```

- [ ] **Step 2: Run to verify failure**

```bash
uv run pytest apps/api/tests/test_object_store.py -v
```

Expected: `ModuleNotFoundError: No module named 'app.object_store'`.

- [ ] **Step 3: Implement `LocalObjectStore`**

Key requirements to implement precisely:
- `put()`: stream input to a temp file inside the store root
  (`root / "_tmp" / uuid4().hex`) while hashing with `hashlib.sha256`, then
  `os.replace()` the temp file into its final content-addressed path
  (atomic on the same filesystem). Write the sidecar metadata JSON only after
  the content rename succeeds. If the final path already exists, compare
  size; content-addressing by SHA-256 makes a same-key/different-content
  situation cryptographically implausible, but if the existing file's size
  disagrees with the new size, raise `ObjectAlreadyExistsWithDifferentContentError`
  instead of silently trusting the cache.
- `_key_to_path(key)`: parse `key` as `sha256/xx/yyyy...` with a strict regex
  (`^sha256/[0-9a-f]{2}/[0-9a-f]{62}$`); anything else raises `ObjectStoreError`.
  Build the path component-by-component and, after resolving, verify
  `resolved_path.relative_to(self.root.resolve())` and that no path
  component along the way `is_symlink()` — mirror
  `app.source_discovery._resolve_source_file`'s approach exactly.
- `open()`/`stat()`/`exists()` all route through `_key_to_path` first, so an
  unsafe key is rejected before any filesystem call.
- Store the sidecar as `<content_path>.meta.json` next to the content, not
  world-writable beyond default permissions.

- [ ] **Step 4: Run to verify pass**

```bash
uv run pytest apps/api/tests/test_object_store.py -v
```

Expected: all tests pass.

---

### Task 4: RBAC — `Role`, `can()`, product grant isolation

**Files:**
- Create: `apps/api/app/access.py`
- Test: `apps/api/tests/test_access.py`

**Interfaces:**
- Produces:
  ```python
  class Role(str, Enum):
      ADMIN = "admin"
      OPERATOR = "operator"
      VIEWER = "viewer"


  class Action(str, Enum):
      VIEW = "view"
      UPLOAD = "upload"
      PROCESS = "process"
      RETRY = "retry"
      MANAGE_ACCESS = "manage_access"


  def can(role: Role | None, action: Action) -> bool: ...
  ```
  `role=None` (no grant) must return `False` for every action — "no grant =
  deny" is a hard rule tested explicitly, not an emergent property.

- [ ] **Step 1: Write failing tests — the full RBAC matrix**

```python
"""RBAC matrix: every (role, action) pair, plus the no-grant-denies rule."""

from __future__ import annotations

import pytest

from app.access import Action, Role, can

MATRIX: dict[tuple[Role, Action], bool] = {
    (Role.ADMIN, Action.VIEW): True,
    (Role.ADMIN, Action.UPLOAD): True,
    (Role.ADMIN, Action.PROCESS): True,
    (Role.ADMIN, Action.RETRY): True,
    (Role.ADMIN, Action.MANAGE_ACCESS): True,
    (Role.OPERATOR, Action.VIEW): True,
    (Role.OPERATOR, Action.UPLOAD): True,
    (Role.OPERATOR, Action.PROCESS): True,
    (Role.OPERATOR, Action.RETRY): True,
    (Role.OPERATOR, Action.MANAGE_ACCESS): False,
    (Role.VIEWER, Action.VIEW): True,
    (Role.VIEWER, Action.UPLOAD): False,
    (Role.VIEWER, Action.PROCESS): False,
    (Role.VIEWER, Action.RETRY): False,
    (Role.VIEWER, Action.MANAGE_ACCESS): False,
}


@pytest.mark.parametrize(("role", "action"), list(MATRIX))
def test_rbac_matrix(role: Role, action: Action) -> None:
    assert can(role, action) is MATRIX[(role, action)]


@pytest.mark.parametrize("action", list(Action))
def test_no_grant_denies_every_action(action: Action) -> None:
    assert can(None, action) is False
```

- [ ] **Step 2: Run to verify failure, then implement `access.py`**

`can()` is a pure lookup over a module-level `frozenset[tuple[Role, Action]]`
or an equivalent explicit table — no cleverness, no rank-comparison
shortcuts that could silently grant an unintended action when `Action` grows.

- [ ] **Step 3: Run to verify pass**

```bash
uv run pytest apps/api/tests/test_access.py -v
```

---

### Task 5: Access repository — `app_user` / `product_grant` persistence

**Files:**
- Create: `apps/api/app/access_repository.py`
- Test: `apps/api/integration_tests/test_access_repository.py`

**Interfaces:**
- Produces:
  ```python
  @dataclass(frozen=True, slots=True)
  class AppUser:
      id: int
      identity_kind: str
      identity_key: str
      display_name: str
      email: str | None


  def resolve_or_create_app_user(
      connection: Connection, *, identity_kind: str, identity_key: str, display_name: str
  ) -> AppUser: ...


  def grant_product_role(
      connection: Connection, *, app_user_id: int, product_key: str, role: Role
  ) -> None: ...


  def get_product_role(
      connection: Connection, *, app_user_id: int, product_key: str
  ) -> Role | None: ...


  def list_grants_for_user(
      connection: Connection, *, app_user_id: int
  ) -> tuple[ProductGrant, ...]: ...
  ```
- Consumes: `app.access.Role`, follows the `ON CONFLICT ... DO NOTHING` +
  re-select idempotency pattern from `app/source_provenance.py`.

- [ ] **Step 1: Write failing integration tests**

```python
"""Integration tests for access repository persistence."""

from __future__ import annotations

from sqlalchemy import Connection

from app.access import Role
from app.access_repository import (
    get_product_role,
    grant_product_role,
    list_grants_for_user,
    resolve_or_create_app_user,
)


def test_resolve_or_create_is_idempotent(integration_connection: Connection) -> None:
    first = resolve_or_create_app_user(
        integration_connection,
        identity_kind="dev-local",
        identity_key="alice",
        display_name="Alice",
    )
    second = resolve_or_create_app_user(
        integration_connection,
        identity_kind="dev-local",
        identity_key="alice",
        display_name="Alice",
    )
    assert first.id == second.id


def test_grant_and_get_product_role_round_trip(integration_connection: Connection) -> None:
    user = resolve_or_create_app_user(
        integration_connection, identity_kind="dev-local", identity_key="bob", display_name="Bob"
    )
    grant_product_role(
        integration_connection, app_user_id=user.id, product_key="forestry", role=Role.OPERATOR
    )

    assert (
        get_product_role(integration_connection, app_user_id=user.id, product_key="forestry")
        is Role.OPERATOR
    )
    assert (
        get_product_role(integration_connection, app_user_id=user.id, product_key="lidar") is None
    )


def test_product_isolation_grant_on_one_product_does_not_leak(
    integration_connection: Connection,
) -> None:
    user = resolve_or_create_app_user(
        integration_connection,
        identity_kind="dev-local",
        identity_key="carol",
        display_name="Carol",
    )
    grant_product_role(
        integration_connection, app_user_id=user.id, product_key="lidar", role=Role.VIEWER
    )

    assert (
        get_product_role(integration_connection, app_user_id=user.id, product_key="transelect")
        is None
    )
    grants = list_grants_for_user(integration_connection, app_user_id=user.id)
    assert {g.product_key for g in grants} == {"lidar"}
```

- [ ] **Step 2: Implement `access_repository.py`**, then run:

```bash
export POSTGRES_PASSWORD=local-dev-only-not-secret
APP_ENV=test POSTGRES_DB=campo_digital_test POSTGRES_USER=campo_digital_test \
POSTGRES_PASSWORD=campo_digital_test POSTGRES_HOST=127.0.0.1 POSTGRES_PORT=5433 \
PYTHONPATH=apps/api uv run pytest apps/api/integration_tests/test_access_repository.py -v
```

---

### Task 6: Dev-only authentication adapter, hard-gated against production

**Files:**
- Create: `apps/api/app/dev_auth.py`
- Test: `apps/api/tests/test_dev_auth.py`

**Interfaces:**
- Produces:
  ```python
  class DevAuthDisabledInProductionError(RuntimeError): ...


  @dataclass(frozen=True, slots=True)
  class DevIdentity:
      identity_key: str
      display_name: str


  SEEDED_DEV_IDENTITIES: tuple[DevIdentity, ...]  # e.g. admin/operator/viewer seed users


  def assert_dev_auth_allowed(settings: Settings) -> None:
      """Raise unless settings.app_env != 'production'."""


  class DevSessionStore:
      def create_session(self, identity_key: str) -> str: ...  # returns opaque token
      def resolve_session(self, token: str) -> str | None: ...  # returns identity_key or None
      def clear_session(self, token: str) -> None: ...
  ```
  `DevSessionStore` is an in-process dict keyed by a `secrets.token_urlsafe(32)`
  opaque token — acceptable for local dev only, explicitly not durable across
  process restarts, and never used if `assert_dev_auth_allowed` has not been
  called first by the router at startup.

- [ ] **Step 1: Write failing tests**

```python
"""Dev-only auth adapter: production gate and session lifecycle."""

from __future__ import annotations

import pytest

from app.config import Settings
from app.dev_auth import (
    DevAuthDisabledInProductionError,
    DevSessionStore,
    assert_dev_auth_allowed,
)


def _settings(app_env: str) -> Settings:
    return Settings(app_env=app_env, postgres_password="x")  # type: ignore[call-arg]


def test_dev_auth_allowed_in_development() -> None:
    assert_dev_auth_allowed(_settings("development"))


def test_dev_auth_allowed_in_test() -> None:
    assert_dev_auth_allowed(_settings("test"))


def test_dev_auth_rejected_in_production() -> None:
    with pytest.raises(DevAuthDisabledInProductionError):
        assert_dev_auth_allowed(_settings("production"))


def test_session_round_trip() -> None:
    store = DevSessionStore()
    token = store.create_session("alice")
    assert store.resolve_session(token) == "alice"


def test_unknown_session_resolves_to_none() -> None:
    store = DevSessionStore()
    assert store.resolve_session("not-a-real-token") is None


def test_cleared_session_no_longer_resolves() -> None:
    store = DevSessionStore()
    token = store.create_session("bob")
    store.clear_session(token)
    assert store.resolve_session(token) is None


def test_sessions_are_unguessable_tokens() -> None:
    store = DevSessionStore()
    token_a = store.create_session("alice")
    token_b = store.create_session("alice")
    assert token_a != token_b
    assert len(token_a) >= 32
```

- [ ] **Step 2: Implement, then run**

```bash
uv run pytest apps/api/tests/test_dev_auth.py -v
```

---

### Task 7: Audit event repository

**Files:**
- Create: `apps/api/app/audit.py`
- Test: `apps/api/integration_tests/test_audit.py`

**Interfaces:**
- Produces:
  ```python
  def record_audit_event(
      connection: Connection,
      *,
      actor_app_user_id: int | None,
      event_type: str,
      product_key: str | None = None,
      subject_kind: str | None = None,
      subject_id: str | None = None,
      metadata: dict[str, object] | None = None,
  ) -> int: ...
  ```
  `metadata` is serialized as JSONB; callers are responsible for never
  passing secrets or raw file contents — enforce this at call sites (Tasks
  9–11), not inside this generic helper.

- [ ] **Step 1: Write failing integration test**

```python
"""Integration tests for the audit event ledger."""

from __future__ import annotations

from sqlalchemy import Connection, text

from app.access_repository import resolve_or_create_app_user
from app.audit import record_audit_event


def test_record_audit_event_persists_row(integration_connection: Connection) -> None:
    user = resolve_or_create_app_user(
        integration_connection, identity_kind="dev-local", identity_key="dana", display_name="Dana"
    )

    event_id = record_audit_event(
        integration_connection,
        actor_app_user_id=user.id,
        event_type="session.created",
        metadata={"identity_kind": "dev-local"},
    )

    row = integration_connection.execute(
        text("SELECT event_type, actor_app_user_id FROM platform.audit_event WHERE id = :id"),
        {"id": event_id},
    ).one()
    assert row.event_type == "session.created"
    assert row.actor_app_user_id == user.id


def test_record_audit_event_allows_null_actor_for_system_events(
    integration_connection: Connection,
) -> None:
    event_id = record_audit_event(
        integration_connection, actor_app_user_id=None, event_type="worker.started"
    )
    assert event_id > 0
```

- [ ] **Step 2: Implement, then run**

```bash
export POSTGRES_PASSWORD=local-dev-only-not-secret
APP_ENV=test POSTGRES_DB=campo_digital_test POSTGRES_USER=campo_digital_test \
POSTGRES_PASSWORD=campo_digital_test POSTGRES_HOST=127.0.0.1 POSTGRES_PORT=5433 \
PYTHONPATH=apps/api uv run pytest apps/api/integration_tests/test_audit.py -v
```

---

### Task 8: Forestry ZIP inspector — zip-slip and archive-bomb hardened

**Files:**
- Create: `apps/api/app/inspection/__init__.py`, `apps/api/app/inspection/forestry_inspector.py`
- Test: `apps/api/tests/inspection/test_forestry_inspector.py`

**Interfaces:**
- Produces:
  ```python
  class ForestryInspectionError(RuntimeError): ...


  @dataclass(frozen=True, slots=True)
  class ForestryInspectionResult:
      member_names: tuple[str, ...]
      has_shp: bool
      has_shx: bool
      has_dbf: bool
      has_prj: bool
      total_uncompressed_bytes: int


  MAX_ARCHIVE_MEMBERS = 2_000
  MAX_UNCOMPRESSED_BYTES = 500 * 1024 * 1024  # 500 MiB
  MAX_COMPRESSION_RATIO = 100


  def inspect_forestry_zip(path: Path) -> ForestryInspectionResult: ...
  ```
  Safety rules enforced *before* trusting any member: reject any
  `ZipInfo.filename` that is absolute, contains `..`, or normalizes outside
  the archive root (zip-slip); reject if `len(namelist()) > MAX_ARCHIVE_MEMBERS`;
  sum `file_size` (uncompressed) across all entries and reject if it exceeds
  `MAX_UNCOMPRESSED_BYTES` or if the ratio of any single entry's
  `file_size / max(compress_size, 1)` exceeds `MAX_COMPRESSION_RATIO` (zip
  bomb heuristic) — all computed from `ZipInfo` metadata only, never by
  extracting.

- [ ] **Step 1: Write failing tests using small synthetic ZIPs built in-test**

```python
"""Forestry ZIP inspector: safety and expected-member detection."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from app.inspection.forestry_inspector import (
    ForestryInspectionError,
    inspect_forestry_zip,
)


def _make_zip(path: Path, members: dict[str, bytes]) -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        for name, content in members.items():
            archive.writestr(name, content)
    return path


def test_detects_shapefile_family_members(tmp_path: Path) -> None:
    archive = _make_zip(
        tmp_path / "predio.zip",
        {"predio.shp": b"x", "predio.shx": b"y", "predio.dbf": b"z", "predio.prj": b"w"},
    )
    result = inspect_forestry_zip(archive)
    assert result.has_shp and result.has_shx and result.has_dbf and result.has_prj


def test_missing_members_reported_false(tmp_path: Path) -> None:
    archive = _make_zip(tmp_path / "incomplete.zip", {"predio.shp": b"x"})
    result = inspect_forestry_zip(archive)
    assert result.has_shp is True
    assert result.has_dbf is False


def test_rejects_zip_slip_parent_traversal(tmp_path: Path) -> None:
    archive_path = tmp_path / "evil.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        info = zipfile.ZipInfo("../../etc/passwd")
        archive.writestr(info, b"pwned")

    with pytest.raises(ForestryInspectionError):
        inspect_forestry_zip(archive_path)


def test_rejects_absolute_member_path(tmp_path: Path) -> None:
    archive_path = tmp_path / "evil_abs.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        info = zipfile.ZipInfo("/etc/passwd")
        archive.writestr(info, b"pwned")

    with pytest.raises(ForestryInspectionError):
        inspect_forestry_zip(archive_path)


def test_rejects_too_many_members(tmp_path: Path) -> None:
    archive_path = tmp_path / "many.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        for i in range(2_001):
            archive.writestr(f"file_{i}.txt", b"x")

    with pytest.raises(ForestryInspectionError):
        inspect_forestry_zip(archive_path)


def test_rejects_pathological_compression_ratio(tmp_path: Path) -> None:
    archive_path = tmp_path / "bomb.zip"
    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("bomb.txt", b"0" * (50 * 1024 * 1024))

    with pytest.raises(ForestryInspectionError):
        inspect_forestry_zip(archive_path)


def test_rejects_non_zip_file(tmp_path: Path) -> None:
    fake = tmp_path / "not_a_zip.zip"
    fake.write_bytes(b"not actually a zip file")

    with pytest.raises(ForestryInspectionError):
        inspect_forestry_zip(fake)
```

- [ ] **Step 2: Implement, then run**

```bash
uv run pytest apps/api/tests/inspection/test_forestry_inspector.py -v
```

Note: `test_rejects_pathological_compression_ratio` uses a highly
compressible 50 MiB payload compressed with `ZIP_DEFLATED`; verify locally
that its on-disk compressed size is small enough to trip
`MAX_COMPRESSION_RATIO` without approaching `MAX_UNCOMPRESSED_BYTES` — if the
ratio does not trip, lower `MAX_COMPRESSION_RATIO` or raise the synthetic
payload's compressibility (e.g. repeat a longer pattern) until it does,
documenting the chosen threshold's rationale as a code comment.

---

### Task 9: Transelec and LiDAR inspectors (thin wrappers over existing code)

**Files:**
- Create: `apps/api/app/inspection/transelec_inspector.py`, `apps/api/app/inspection/lidar_inspector.py`
- Test: `apps/api/tests/inspection/test_transelec_inspector.py`, `apps/api/tests/inspection/test_lidar_inspector.py`

**Interfaces:**
- Produces:
  ```python
  # transelec_inspector.py
  @dataclass(frozen=True, slots=True)
  class TranselecInspectionResult:
      sheet_names: tuple[str, ...]
      resumen_row_count: int | None
      contract_error: str | None  # populated, not raised, when contract validation fails


  def inspect_transelec_workbook(path: Path) -> TranselecInspectionResult: ...


  # lidar_inspector.py
  @dataclass(frozen=True, slots=True)
  class LidarInspectionResult:
      point_count: int
      las_version: str
      point_format_id: int
      bounds: tuple[float, float, float, float, float, float]
      crs_is_explicit: bool


  def inspect_lidar_file(path: Path) -> LidarInspectionResult: ...
  ```
  `inspect_transelec_workbook` calls
  `transelec_ingestion.xlsx_contract` functions to read sheet names and
  attempt the existing Resumen contract validation, catching
  `TranselecWorkbookError` into `contract_error` rather than raising — intake
  inspection reports evidence, it does not gate upload on business-schema
  perfection.
  `inspect_lidar_file` calls `lidar_io.inspect.inspect_las(path,
  compute_checksum=False)` (checksum disabled — SHA-256 identity is already
  established by the object store) and maps the returned `LasMetadata` onto
  the smaller `LidarInspectionResult`. Document in a module docstring that
  this streams through every point to recompute observed bounds (matching
  the product's own ADR-001 not-stale-header-bounds decision) and is
  therefore proportional to file size, not true O(1) header-only inspection —
  an explicit, honest LIMITATION for very large future LiDAR files.

- [ ] **Step 1: Write failing tests**

```python
# test_transelec_inspector.py
from __future__ import annotations

from pathlib import Path

from python_calamine import CalamineWorkbook  # only used to build the fixture, not by the inspector
import openpyxl  # if unavailable, build via a minimal xlsx writer instead — see note below

from app.inspection.transelec_inspector import inspect_transelec_workbook


def _make_minimal_workbook(path: Path) -> Path:
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "Resumen"
    sheet.append(["not", "the", "real", "contract", "headers"])
    workbook.create_sheet("Pendientes")
    workbook.save(path)
    return path


def test_reports_sheet_names(tmp_path: Path) -> None:
    workbook_path = _make_minimal_workbook(tmp_path / "wb.xlsx")
    result = inspect_transelec_workbook(workbook_path)
    assert "Resumen" in result.sheet_names
    assert "Pendientes" in result.sheet_names


def test_contract_mismatch_is_reported_not_raised(tmp_path: Path) -> None:
    workbook_path = _make_minimal_workbook(tmp_path / "wb2.xlsx")
    result = inspect_transelec_workbook(workbook_path)
    assert result.contract_error is not None
```

```python
# test_lidar_inspector.py
from __future__ import annotations

from pathlib import Path

import laspy
import numpy as np

from app.inspection.lidar_inspector import inspect_lidar_file


def _make_minimal_las(path: Path) -> Path:
    header = laspy.LasHeader(point_format=3, version="1.2")
    las = laspy.LasData(header)
    las.x = np.array([0.0, 1.0, 2.0])
    las.y = np.array([0.0, 1.0, 2.0])
    las.z = np.array([0.0, 1.0, 2.0])
    las.write(path)
    return path


def test_reports_point_count_and_bounds(tmp_path: Path) -> None:
    las_path = _make_minimal_las(tmp_path / "sample.las")
    result = inspect_lidar_file(las_path)
    assert result.point_count == 3
    assert result.las_version == "1.2"
```

Check whether `openpyxl` is already a dependency before writing the Transelec
fixture (the corpus-measurement research found it absent). If absent, either
add it as a `dev`-only extra in `pyproject.toml` for test-fixture generation
only (never imported by application code, which uses `python_calamine`
exclusively, matching the existing `xlsx_contract` module), or build the
minimal `.xlsx` fixture by hand via `zipfile` + the minimal OOXML parts
instead of adding a new dependency — prefer the dependency-free approach if
it is not significantly more code, since `pyproject.toml` changes should be
minimal for this slice.

- [ ] **Step 2: Implement both inspectors, then run**

```bash
uv run pytest apps/api/tests/inspection/ -v
```

---

### Task 10: Durable job queue — enqueue, `SKIP LOCKED` claim, complete/fail, stale-lease reap

**Files:**
- Create: `apps/api/app/jobs.py`
- Test: `apps/api/integration_tests/test_jobs.py`

**Interfaces:**
- Produces:
  ```python
  @dataclass(frozen=True, slots=True)
  class ClaimedJob:
      id: int
      ingestion_run_id: int
      product_key: str
      attempt_count: int
      source_snapshot_id: int
      object_storage_key: str | None


  def enqueue_processing_job(
      connection: Connection,
      *,
      ingestion_run_id: int,
      product_key: str,
      requested_by_app_user_id: int | None,
  ) -> int: ...


  def claim_next_job(
      connection: Connection, *, worker_id: str, lease_seconds: int = 120
  ) -> ClaimedJob | None: ...
  def complete_job(connection: Connection, *, job_id: int, worker_id: str) -> None: ...
  def fail_job(
      connection: Connection, *, job_id: int, worker_id: str, error_summary: str
  ) -> None: ...
  def reap_stale_leases(connection: Connection) -> int: ...  # returns count reset to queued
  ```
  `claim_next_job` runs, in one statement, roughly:
  ```sql
  UPDATE platform.processing_job
  SET status = 'running',
      lease_owner = :worker_id,
      lease_expires_at = now() + make_interval(secs => :lease_seconds),
      started_at = COALESCE(started_at, now()),
      attempt_count = attempt_count + 1
  WHERE id = (
      SELECT id FROM platform.processing_job
      WHERE status = 'queued'
         OR (status = 'running' AND lease_expires_at < now())
      ORDER BY created_at
      FOR UPDATE SKIP LOCKED
      LIMIT 1
  )
  RETURNING id, ingestion_run_id, product_key, attempt_count
  ```
  then a follow-up `SELECT` joins `ingestion_run`/`source_snapshot` for
  `source_snapshot_id`/`object_storage_key`. This single
  `UPDATE ... WHERE id = (SELECT ... FOR UPDATE SKIP LOCKED)` is what makes
  two concurrent workers never claim the same row: the losing worker's
  subquery simply skips the locked row and finds nothing (or the next row).
  A `processing_attempt` row is inserted by the caller (the worker loop in
  Task 11) with `attempt_number = attempt_count` from the claim result, using
  `INSERT ... ON CONFLICT (processing_job_id, attempt_number) DO NOTHING` to
  stay idempotent if a lease-timeout retry ever double-claims after a reap
  race — `fail_job` sets `status='failed'` only when `attempt_count >=
  max_attempts`, otherwise resets to `queued` for a bounded retry.

- [ ] **Step 1: Write failing tests, including the two-worker concurrency test**

The concurrency test must NOT use the `integration_connection` fixture (it
wraps everything in one rolled-back transaction, so two "workers" sharing it
would just be one transaction seeing its own uncommitted lock — not a real
test). Use `integration_engine` directly with two separate connections that
each commit, and clean up the rows the test created at the end.

```python
"""Job durability: enqueue, SKIP LOCKED claim exclusivity, retry, stale lease reap."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import Connection, Engine, text

from app.access_repository import resolve_or_create_app_user
from app.jobs import (
    claim_next_job,
    complete_job,
    enqueue_processing_job,
    fail_job,
    reap_stale_leases,
)


def _make_ingestion_run(connection: Connection, *, product_key: str = "transelect") -> int:
    system_id = connection.execute(
        text("INSERT INTO platform.source_system (system_key) VALUES ('jobs_test') RETURNING id")
    ).scalar_one()
    asset_id = connection.execute(
        text(
            "INSERT INTO platform.source_asset (source_system_id, identity_kind, identity_key) "
            "VALUES (:sid, 'relative_path', 'jobs_test.xlsx') RETURNING id"
        ),
        {"sid": system_id},
    ).scalar_one()
    snapshot_id = connection.execute(
        text(
            "INSERT INTO platform.source_snapshot (source_asset_id, content_sha256, byte_size) "
            "VALUES (:aid, repeat('c', 64), 5) RETURNING id"
        ),
        {"aid": asset_id},
    ).scalar_one()
    return connection.execute(
        text(
            "INSERT INTO platform.ingestion_run (source_snapshot_id, product_key) "
            "VALUES (:snid, :pk) RETURNING id"
        ),
        {"snid": snapshot_id, "pk": product_key},
    ).scalar_one()


def test_two_workers_never_claim_the_same_job(integration_engine: Engine) -> None:
    with integration_engine.connect() as setup_conn:
        run_id = _make_ingestion_run(setup_conn)
        job_id = enqueue_processing_job(
            setup_conn,
            ingestion_run_id=run_id,
            product_key="transelect",
            requested_by_app_user_id=None,
        )
        setup_conn.commit()

    try:
        with integration_engine.connect() as conn_a, integration_engine.connect() as conn_b:
            claimed_a = claim_next_job(conn_a, worker_id="worker-a")
            conn_a.commit()
            claimed_b = claim_next_job(conn_b, worker_id="worker-b")
            conn_b.commit()

        assert claimed_a is not None
        assert claimed_a.id == job_id
        assert claimed_b is None
    finally:
        with integration_engine.connect() as cleanup_conn:
            cleanup_conn.execute(
                text("DELETE FROM platform.processing_job WHERE id = :id"), {"id": job_id}
            )
            cleanup_conn.execute(
                text("DELETE FROM platform.ingestion_run WHERE id = :id"), {"id": run_id}
            )
            cleanup_conn.commit()


def test_stale_lease_is_reclaimed(integration_engine: Engine) -> None:
    with integration_engine.connect() as setup_conn:
        run_id = _make_ingestion_run(setup_conn)
        job_id = enqueue_processing_job(
            setup_conn,
            ingestion_run_id=run_id,
            product_key="transelect",
            requested_by_app_user_id=None,
        )
        claim_next_job(setup_conn, worker_id="worker-crashed", lease_seconds=0)
        setup_conn.commit()

    try:
        with integration_engine.connect() as reap_conn:
            reset_count = reap_stale_leases(reap_conn)
            reap_conn.commit()
        assert reset_count >= 1

        with integration_engine.connect() as retry_conn:
            claimed = claim_next_job(retry_conn, worker_id="worker-b")
            retry_conn.commit()
        assert claimed is not None
        assert claimed.id == job_id
    finally:
        with integration_engine.connect() as cleanup_conn:
            cleanup_conn.execute(
                text("DELETE FROM platform.processing_job WHERE id = :id"), {"id": job_id}
            )
            cleanup_conn.execute(
                text("DELETE FROM platform.ingestion_run WHERE id = :id"), {"id": run_id}
            )
            cleanup_conn.commit()


def test_fail_job_retries_until_max_attempts_then_fails(integration_engine: Engine) -> None:
    with integration_engine.connect() as setup_conn:
        run_id = _make_ingestion_run(setup_conn)
        job_id = enqueue_processing_job(
            setup_conn,
            ingestion_run_id=run_id,
            product_key="transelect",
            requested_by_app_user_id=None,
        )
        setup_conn.commit()

    try:
        with integration_engine.connect() as conn:
            for _ in range(3):
                claimed = claim_next_job(conn, worker_id="retry-worker")
                assert claimed is not None
                fail_job(conn, job_id=job_id, worker_id="retry-worker", error_summary="boom")
                conn.commit()

            status = conn.execute(
                text("SELECT status, attempt_count FROM platform.processing_job WHERE id = :id"),
                {"id": job_id},
            ).one()
        assert status.status == "failed"
        assert status.attempt_count == 3
    finally:
        with integration_engine.connect() as cleanup_conn:
            cleanup_conn.execute(
                text("DELETE FROM platform.processing_job WHERE id = :id"), {"id": job_id}
            )
            cleanup_conn.execute(
                text("DELETE FROM platform.ingestion_run WHERE id = :id"), {"id": run_id}
            )
            cleanup_conn.commit()
```

- [ ] **Step 2: Implement `jobs.py`**, then run

```bash
export POSTGRES_PASSWORD=local-dev-only-not-secret
APP_ENV=test POSTGRES_DB=campo_digital_test POSTGRES_USER=campo_digital_test \
POSTGRES_PASSWORD=campo_digital_test POSTGRES_HOST=127.0.0.1 POSTGRES_PORT=5433 \
PYTHONPATH=apps/api uv run pytest apps/api/integration_tests/test_jobs.py -v
```

Expected: `claimed_b is None` in the first test is the load-bearing
assertion proving `SKIP LOCKED` exclusivity — if this ever becomes flaky or
passes for the wrong reason (e.g. because job B silently failed to find any
row due to a query bug rather than genuine exclusivity), add a third
assertion that a job existed and was claimable at all (already covered by
`claimed_a is not None`).

---

### Task 11: Worker loop CLI entrypoint

**Files:**
- Create: `apps/api/app/worker.py`
- Test: `apps/api/tests/test_worker.py` (unit-level: dispatch-to-inspector routing only, not a live DB loop)

**Interfaces:**
- Produces:
  ```python
  def run_one_job(connection: Connection, store: ObjectStore, *, worker_id: str) -> bool:
      """Claim, run one inspection, record outcome. Returns False if nothing was queued."""


  def dispatch_inspection(product_key: str, local_path: Path) -> dict[str, object]:
      """Route to the product's inspector; returns a JSON-serializable evidence dict."""


  def main() -> None:
      """CLI loop: repeatedly call run_one_job with a short sleep when idle."""
  ```
  `run_one_job`: `claim_next_job` → if `None`, return `False`. Otherwise:
  write a `processing_attempt` row (`status='running'`), fetch the object
  from `store.open(object_storage_key)` into a `NamedTemporaryFile` (product
  inspectors take a `Path`, not a stream, since `laspy`/`python_calamine`/
  `zipfile` all want random-access file access), call
  `dispatch_inspection`, on success insert a `generated_artifact` row
  (`artifact_kind="inspection_report"`, JSON evidence written via
  `store.put()` and its returned key), call `complete_job`, update the
  `processing_attempt` to `status='succeeded'`, and call
  `record_audit_event(event_type="artifact.produced", ...)`. On any
  exception from `dispatch_inspection`, call `fail_job` with a truncated
  `str(exc)`, mark the `processing_attempt` `status='failed'`, and audit
  `event_type="processing.failed"`. Always delete the temp file in a
  `finally` block.

- [ ] **Step 1: Write failing unit test for `dispatch_inspection` routing only**

```python
"""Worker dispatch routing — unit-level, no live job claim/DB loop here."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.worker import dispatch_inspection


def test_dispatch_rejects_unknown_product_key(tmp_path: Path) -> None:
    dummy = tmp_path / "file.bin"
    dummy.write_bytes(b"x")
    with pytest.raises(ValueError):
        dispatch_inspection("unknown_product", dummy)
```

- [ ] **Step 2: Implement `worker.py`**, then run

```bash
uv run pytest apps/api/tests/test_worker.py -v
```

- [ ] **Step 3: Write one full end-to-end integration test: enqueue → `run_one_job` → artifact recorded**

**Test:** `apps/api/integration_tests/test_worker_end_to_end.py` — build a
tiny synthetic Transelec-shaped `.xlsx` fixture (same helper as Task 9), put
it in a `LocalObjectStore` under a `tmp_path`, insert the full
`source_snapshot`/`ingestion_run`/`processing_job` chain with
`object_storage_key` set to the stored key, call `run_one_job`, then assert:
`processing_job.status == 'succeeded'`, exactly one `processing_attempt` row
with `status='succeeded'`, and exactly one `generated_artifact` row exists
whose stored JSON (read back via `store.open`) contains the expected sheet
names. Use `integration_engine` with manual commit/cleanup, not
`integration_connection`, since the worker's own internal commits must be
real for this to be a meaningful test.

```bash
export POSTGRES_PASSWORD=local-dev-only-not-secret
APP_ENV=test POSTGRES_DB=campo_digital_test POSTGRES_USER=campo_digital_test \
POSTGRES_PASSWORD=campo_digital_test POSTGRES_HOST=127.0.0.1 POSTGRES_PORT=5433 \
PYTHONPATH=apps/api uv run pytest apps/api/integration_tests/test_worker_end_to_end.py -v
```

---

### Task 12: FastAPI routers — dev auth, upload/intake, jobs, audit

**Files:**
- Create: `apps/api/app/routers/dev_auth.py`, `apps/api/app/routers/ingestion.py`
- Modify: `apps/api/app/main.py` (mount both routers; construct the
  process-level `LocalObjectStore` and `DevSessionStore` singletons)
- Test: `apps/api/tests/test_dev_auth_router.py`, `apps/api/tests/test_ingestion_router.py` (unit, via `TestClient` with a real test-DB connection — follow the pattern in `apps/api/tests/test_lidar_api.py`)

**Interfaces:**
- Produces:
  - `POST /auth/dev-login {identity_key} -> 200 {display_name, product_grants: [...]}`, sets an
    httponly session cookie. `GET /auth/me -> 200 {...}` or `401` if no valid
    session. `POST /auth/logout -> 204`.
  - `POST /ingesta/upload` — multipart form: `product_key` (required, one of
    the three literals — reject any other value with `422`, INDEPENDENT of
    the uploaded filename/extension, per the spec's "do not infer product
    from extension" rule) + `file`. Requires `Action.UPLOAD` for that
    product via the current session's grant, else `403`. Streams to
    `LocalObjectStore`, runs the matching inspector synchronously (bounded —
    see Task 9's note on LiDAR cost), persists
    `source_system`/`source_asset`/`source_snapshot` (reusing
    `persist_filesystem_source_provenance`'s sibling functions — add a
    non-filesystem variant `persist_uploaded_source_provenance` to
    `app/source_provenance.py` if the existing one is too filesystem-specific;
    if it already accommodates an arbitrary `identity_key`/`system_key` pair,
    reuse it directly rather than adding a new function), sets
    `object_storage_key`, creates an `ingestion_run` +
    `processing_job` (`enqueue_processing_job`), records
    `upload.completed` and `processing.requested` audit events, and returns
    `{source_snapshot_id, sha256, byte_size, validation_evidence, job_id}`.
  - `GET /ingesta/jobs` — lists jobs visible to the caller's granted
    products only (never other products' jobs, even for an admin of a
    different product — this is the IDOR-prevention surface).
  - `POST /ingesta/jobs/{id}/retry` — requires `Action.RETRY` for that job's
    product; `404` (not `403`) if the job's product isn't one the caller has
    any grant on, to avoid leaking job existence across product boundaries;
    resets a `failed` job back to `queued` with `attempt_count` unchanged
    (bounded by `max_attempts` still).
  - `GET /ingesta/audit` — requires `Action.MANAGE_ACCESS` (admin only, per
    spec's "audit trail visible to admin/operator" — operators get a
    narrower per-product view via `/ingesta/jobs`; full cross-audit is
    admin-only since it may span products the caller isn't granted on).

- [ ] **Step 1: Write failing router tests** covering: `401` with no
  session; `403` for a viewer attempting `POST /ingesta/upload`; `422` for a
  `product_key` not in the three literals; `404` (not `403`) for
  `/ingesta/jobs/{id}/retry` on a job belonging to an ungranted product; a
  full happy-path upload as an operator returning `200` with a non-null
  `job_id`.

- [ ] **Step 2: Implement both routers and wire them into `main.py`**, then run

```bash
uv run pytest apps/api/tests/test_dev_auth_router.py apps/api/tests/test_ingestion_router.py -v
```

---

### Task 13: Security test sweep

**Files:**
- Test: `apps/api/tests/test_intake_security.py`

Cover, each as an explicit test against the live router (`TestClient`):
- Oversized upload rejected before fully buffering in memory (set a small
  `MAX_UPLOAD_BYTES` for the test via dependency override or settings, upload
  one byte over it, assert `413`).
- Malicious `Content-Type` header does not change which product/inspector
  runs — only the explicit `product_key` field does.
- Path-traversal in the original filename (`"../../evil.xlsx"`) is not used
  to construct any real filesystem path (`LocalObjectStore` already prevents
  this structurally — assert the returned evidence contains the raw
  filename string only as *metadata*, never as a path component in any
  server-side log line the test can inspect, and that
  `store.stat(result.key)` resolves correctly).
- Requesting `GET /ingesta/jobs?product_key=lidar` as a user with only a
  `forestry` grant returns an empty list (or omits `lidar` jobs), not an
  error revealing whether `lidar` jobs exist.
- `assert_dev_auth_allowed` is actually invoked at API startup (import
  `app.main` under `APP_ENV=production` in a subprocess or via monkeypatched
  settings and assert the app fails fast rather than serving the dev-login
  route) — this directly tests the "dev-auth accidentally enabled in
  production" threat from the spec.

- [ ] **Step 1: Write failing tests for each bullet above**
- [ ] **Step 2: Fix whichever bullet(s) are not yet satisfied by Tasks 3–12's implementations**
- [ ] **Step 3: Run the full suite**

```bash
uv run pytest apps/api/tests/test_intake_security.py -v
```

---

### Task 14: Portal `/ingesta` page

**Files:**
- Create: `apps/portal/src/lib/platformApi.ts`, `apps/portal/src/pages/Ingesta.tsx`, `apps/portal/src/pages/Ingesta.test.tsx`
- Modify: `apps/portal/src/App.tsx` (route `/ingesta` before the `startsWith('/modulo/')` check), `apps/portal/vite.config.ts` (add a dev proxy: `server.proxy['/api'] = { target: 'http://127.0.0.1:8000', changeOrigin: true }`)

**Interfaces:**
- `platformApi.ts` exports `devLogin(identityKey)`, `getMe()`,
  `uploadFile(productKey, file)`, `listJobs()`, `retryJob(jobId)`,
  `getAuditLog()` — all thin `fetch('/api/...', { credentials: 'include' })`
  wrappers returning typed results, each catching network errors into a
  `{ ok: false, error }` shape (mirroring `runtimeConfig.ts`'s
  never-throw-to-the-UI convention).
- `Ingesta.tsx`: identity picker (buttons for each seeded dev identity) when
  logged out; once logged in, shows the current role per product, a product
  selector + file input + upload button (disabled unless the selected
  product's role permits `upload`), a polling (2s interval, cleared on
  unmount) table of the caller's visible jobs with a retry button gated by
  role, and — only when the current role is `admin` — an audit log table.

- [ ] **Step 1: Write failing component tests** (following the existing
  `Estado.test.tsx` / `Home.test.tsx` patterns — mock `fetch`, assert
  role-gated controls render/hide correctly for each of the three roles, and
  that a `viewer` never renders an enabled upload/retry control).
- [ ] **Step 2: Implement `platformApi.ts` and `Ingesta.tsx`, wire the route and dev proxy**
- [ ] **Step 3: Run**

```bash
cd apps/portal && npm test
```

---

### Task 15: `Makefile` targets and browser QA

**Files:**
- Modify: `Makefile` — add:
  ```makefile
  platform-local:
  	APP_ENV=development PYTHONPATH=apps/api uv run uvicorn app.main:app --reload --port 8000

  platform-worker:
  	APP_ENV=development PYTHONPATH=apps/api uv run python -m app.worker

  platform-worker-concurrency:
  	for i in $$(seq 1 $(N)); do \
  		APP_ENV=development PYTHONPATH=apps/api uv run python -m app.worker & \
  	done; \
  	wait
  ```
  (`N` defaults via `N ?= 2` near the top of the file if not already set.)
  Do not modify `campo-demo`/`campo-status`/`campo-stop` — these targets stay
  fully decoupled from `platform-local`, per the constraint not to break the
  existing three-product demo composition.

- [ ] **Step 1: Add the Makefile targets**
- [ ] **Step 2: Manually run the full local loop and record the transcript**

```bash
export POSTGRES_PASSWORD=local-dev-only-not-secret
make db-test-up   # or a separate dev-mode compose profile if `postgres` (non-test) is used instead
# apply migrations to the dev DB (not the test DB) before starting the API
make platform-local &        # note the PID
make platform-worker &       # note the PID
cd apps/portal && npm run dev &
```

Then in a browser: dev-login as the seeded ADMIN identity, upload a small
synthetic fixture file for each product, confirm SHA-256/size/validation
evidence appear, confirm the job transitions `queued → running → succeeded`
via polling, confirm a generated artifact reference appears, confirm the
audit log shows the sequence of events. Log out, log back in as OPERATOR:
confirm upload/retry works but `/ingesta/audit` is hidden. Log in as VIEWER:
confirm upload/retry controls are absent and attempting the API call
directly (e.g. via browser devtools) returns `403`. Confirm a VIEWER or
OPERATOR granted only on `forestry` cannot see `lidar` or `transelect` jobs.

- [ ] **Step 3: Stop the manually started processes**

```bash
kill %1 %2 %3  # or the recorded PIDs
```

Record the manual QA transcript's key observations in the final report — do
not claim success without having actually driven the browser flow.

---

### Task 16: Full gate, `docs/superpowers/plans` update, and commit

**Files:** none new.

- [ ] **Step 1: Run the full local gate**

```bash
export POSTGRES_PASSWORD=local-dev-only-not-secret
make check
make persistence-check
```

- [ ] **Step 2: Update `docs/platform/roadmap.md`'s Phase 1 section** to
  record the newly implemented FACTS (access/RBAC, object store, intake,
  jobs) and move the relevant LIMITATION bullets forward or resolve them —
  per `docs/DOCUMENTATION_POLICY.md`, do not duplicate facts already stated
  elsewhere; add only what changed.

- [ ] **Step 3: Run doc automation**

```bash
uv run python scripts/update_doc_nav.py
uv run python scripts/check_doc_links.py
```

- [ ] **Step 4: Commit**

```bash
git add migrations/versions/0005_establish_platform_access_foundation.py \
        migrations/versions/0006_establish_platform_ingestion_foundation.py \
        apps/api/app/object_store.py apps/api/app/access.py \
        apps/api/app/access_repository.py apps/api/app/dev_auth.py \
        apps/api/app/audit.py apps/api/app/jobs.py apps/api/app/worker.py \
        apps/api/app/inspection/ apps/api/app/routers/dev_auth.py \
        apps/api/app/routers/ingestion.py apps/api/app/main.py \
        apps/api/tests/ apps/api/integration_tests/ \
        apps/portal/src/lib/platformApi.ts apps/portal/src/pages/Ingesta.tsx \
        apps/portal/src/pages/Ingesta.test.tsx apps/portal/src/App.tsx \
        apps/portal/vite.config.ts Makefile \
        docs/platform/roadmap.md \
        docs/superpowers/plans/2026-09-01-platform-ingestion-access-foundation.md
git commit -m "$(cat <<'EOF'
feat: establish local platform ingestion and access foundation

Adds dev-only authentication, product-scoped RBAC, a content-addressed
local object store, a controlled multi-product upload/intake boundary,
lightweight per-product inspection adapters, and a durable PostgreSQL-backed
job queue safe under concurrent workers (SELECT ... FOR UPDATE SKIP LOCKED).
Extends the existing source-provenance schema rather than duplicating it,
and demonstrates the full flow end-to-end through a new /ingesta portal page.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01PkrV6oQZWRidRfQP5wqWBz
EOF
)"
git log -1 --stat
```
