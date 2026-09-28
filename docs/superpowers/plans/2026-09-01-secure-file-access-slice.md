# Secure File Access Slice Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Task 6 cannot start until the external gate after Task 5 is closed by a human with Campo Digital tenant-admin rights — do not attempt to script around this.**

**Goal:** Turn the Render staging demo into a usable private platform: real
Entra ID sign-in, a hashed-cookie Postgres-backed session store, a
discoverable `Archivos` area, metadata-only real OneDrive browsing feeding
the existing ingestion pipeline (byte import still flagged off), an
admin grants panel, and a staging-only in-process execution adapter — without
provisioning paid infrastructure, without guessing the Microsoft Graph
scope, and without importing real client binaries into Render's ephemeral
storage.

**Architecture:** One new migration (`0007`, keeping a single Alembic head)
adds `platform.session` (hashed-secret cookie sessions) and
`platform.ms_graph_grant` (Fernet-encrypted Graph tokens), both following the
existing raw-SQL-via-`sqlalchemy.text()` + `ON CONFLICT` idempotency style
used throughout `app/access_repository.py` and `app/source_provenance.py`.
`app.dev_auth` is untouched in shape but newly gated to
`APP_ENV == "development"` only. A new `app/session_store.py` provides the
Postgres-backed store for real (Entra) identities; `app/deps.py` tries it
first and falls back to `DevSessionStore` only where dev-auth is allowed,
so both coexist without one router depending on the other. `msal` drives the
authorization-code + PKCE flow in a new `app/entra_auth.py` +
`app/routers/entra_auth.py`. The Microsoft Graph scope is never assumed —
`config/source-catalog.yaml` only gains `drive_id`/`site_id`/`root_item_id`
fields after a throwaway discovery script is run against a real sign-in
through a real Entra app registration, and that RESULT is what Task 12's
Graph client and `config/source-catalog.yaml` values are built from. An
`ExecutionBackend` protocol (`app/execution.py`) gives Render staging a way
to actually finish queued jobs without pretending it is a production worker.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy Core (no ORM), Alembic,
psycopg3, `msal` (new), `cryptography` (new, Fernet), pytest; React 19 +
TypeScript + Vite (`apps/portal`), plain `fetch`, no new frontend
dependencies.

**Spec:** `docs/superpowers/specs/2026-09-01-secure-file-access-slice-design.md`
(approved 2026-09-01, with the sequencing correction folded into this plan:
the Entra app-registration handoff and the tenant-admin registration must
both happen **before** the Graph discovery spike, because discovery needs a
real app registration to sign in through). Ground truth for existing
conventions: `apps/api/app/access_repository.py`, `apps/api/app/dev_auth.py`,
`apps/api/app/deps.py`, `apps/api/app/source_discovery.py`,
`config/source-catalog.yaml`, `docs/source-systems/onedrive.md`,
`docs/platform/security-model.md`, `docs/adr/ADR-005-render-staging-experiment.md`.

## Global Constraints

- Do not implement application code for anything gated on the Graph scope
  before Task 7's RESULT is recorded. No default/guessed scope.
- Entra app registration in Campo Digital's own dedicated Entra tenant
  (created via Azure free-account signup, not an unrelated existing
  tenant), supporting **any organizational directory + personal
  Microsoft accounts** (not single-tenant, not personal-accounts-only —
  see the 2026-09-01 revision in the spec, section 1). Confidential
  client (authorization-code + PKCE via `msal`), MSAL authority
  `https://login.microsoftonline.com/common`. Never a public client,
  never client-credentials/app-only tokens for Graph calls.
- `identity_kind = "entra"`, `identity_key = f"{tenant_id}:{oid}"`. Never
  email/UPN as an identity key.
- Sign-in requests only `openid profile` scope. The Graph scope is a
  separate, incremental consent triggered only for users who already hold an
  `UPLOAD`-capable grant on at least one product.
- `platform.session` stores `sha256(raw_secret)`, never the raw secret.
- `platform.ms_graph_grant` stores Fernet-encrypted tokens under
  `PLATFORM_TOKEN_ENCRYPTION_KEY`; access/refresh tokens are never sent to
  the browser.
- `app.dev_auth.assert_dev_auth_allowed` must reject everything except
  `APP_ENV == "development"` (this closes ADR-005's staging exposure — the
  three `staging`-allows-dev-auth tests it added must be replaced, not left
  passing).
- Bootstrap admin grant is config-driven
  (`PLATFORM_BOOTSTRAP_ADMIN_TENANT_ID`/`_OBJECT_ID`), one-time, and only
  fires when the resolved identity currently holds zero grants. Never
  domain/email-based, never "first login ever".
- Every Graph call server-side uses the signing-in user's own delegated
  token. No app-only fallback, ever.
- Server proves product ownership of a browsed OneDrive item via Graph's own
  `parentReference` ancestry chain against the configured root `item_id` —
  never trusts a client-asserted product.
- `ENABLE_ONEDRIVE_IMPORT` stays `false`; only metadata-only Graph calls
  (`children`, `search`, item properties) are exercised end-to-end in this
  slice.
- `InProcessStagingExecutionBackend` runs only under `APP_ENV == "staging"`,
  runs blocking work via `asyncio.to_thread`, caps bytes at
  `STAGING_EXECUTION_MAX_BYTES` (default 25 MB), and explicitly refuses
  `lidar` product jobs.
- Preserve one Alembic head: this slice adds exactly one new migration,
  `0007`, with `down_revision = "0006"`.
- No paid Render resources. No Render Disk. No background worker service.
- Never commit real client binaries, tenant secrets, or a real
  `client_secret`/`PLATFORM_TOKEN_ENCRYPTION_KEY` value.
- `make check` (format, lint, mypy, architecture boundaries, full pytest,
  doc links) and `make persistence-check` must pass before each commit that
  touches `apps/api` or `migrations/`.

## File Structure

New backend files:
- `migrations/versions/0007_establish_platform_session_and_graph_grant.py`
- `apps/api/app/session_store.py` — `PlatformSessionStore` (Postgres-backed, hashed secret)
- `apps/api/app/entra_auth.py` — `msal` confidential-client wrapper, ID-token validation, bootstrap-admin check
- `apps/api/app/token_crypto.py` — Fernet encrypt/decrypt helpers for `ms_graph_grant`
- `apps/api/app/routers/entra_auth.py` — `/auth/entra/login`, `/auth/entra/callback`, `/auth/entra/graph-consent/start`, `/auth/entra/graph-consent/callback`
- `apps/api/app/routers/access_admin.py` — `/access/users`, `/access/users/{id}/grants` (admin-only)
- `apps/api/app/graph_client.py` — thin Microsoft Graph HTTP wrapper (`list_children`, `search`, `get_item`, `resolve_parent_chain`)
- `apps/api/app/execution.py` — `ExecutionBackend` protocol, `InProcessStagingExecutionBackend`
- `scripts/graph_discovery_spike.py` — throwaway, not imported by the app; deleted or archived after Task 7
- Test files mirrored under `apps/api/tests/` (unit) and `apps/api/integration_tests/` (real DB), named per task below.

Modified backend files:
- `apps/api/app/config.py` — new `Settings` fields (Entra, token encryption, bootstrap, feature flags)
- `apps/api/app/dev_auth.py` — `assert_dev_auth_allowed` restricted to `development`
- `apps/api/app/main.py` — dev-auth router mount restricted to `development`; mount `entra_auth` and `access_admin` routers
- `apps/api/app/deps.py` — `get_current_identity_key`/`get_current_app_user` try `PlatformSessionStore` first, fall back to `DevSessionStore` only where allowed
- `apps/api/app/routers/ingestion.py` — mount `/archivos` alias, add `Desde OneDrive` metadata endpoints
- `apps/api/app/worker.py` — ephemeral-object-missing handling in `run_one_job`
- `config/source-catalog.yaml` — `drive_id`/`site_id`/`root_item_id` per project, filled in from Task 7's RESULT
- `docs/source-systems/onedrive.md` — RESULT entry from Task 7
- `pyproject.toml` — add `msal` and `cryptography` to the `api` extra
- `render.yaml` — new env vars for staging

New frontend files:
- `apps/portal/src/pages/Archivos.tsx` (renamed/reorganized from `Ingesta.tsx`) + `Archivos.test.tsx`
- `apps/portal/src/pages/Grants.tsx` (admin-only) + `Grants.test.tsx`
- `apps/portal/src/components/OneDrivePanel.tsx` + test

Modified frontend files:
- `apps/portal/src/App.tsx` — route `/archivos`, 301-equivalent redirect from `/ingesta`, route `/archivos/grants`
- `apps/portal/src/pages/Home.tsx` — add the `Archivos` nav link (currently missing entirely)
- `apps/portal/src/lib/platformApi.ts` — Entra login/consent redirects, grants endpoints, OneDrive browse endpoints

Docs:
- `docs/platform/entra-app-registration-handoff.md` (new, Task 1)

---

### Task 1: Entra app-registration handoff document

**Status: done** (`docs: add Entra app-registration handoff for tenant
admin`), but **revised 2026-09-01** — the embedded Step 1 markdown below
is the original, now-superseded text kept for history. The actual
committed file, `docs/platform/entra-app-registration-handoff.md`, has
since been corrected in place for the account-type/tenant-ownership
evidence described in the spec's 2026-09-01 revision note (section 1):
supported account types are "any organizational directory + personal
Microsoft accounts" (not single-tenant), a "Prerequisite: create the
tenant" section was added (Azure free-account signup — no personal
Microsoft account can create an Entra tenant directly), and "What
happens after this" now reflects the confirmed personal-OneDrive source
instead of an assumed SharePoint library. Treat the live file as
authoritative, not the block below.

**Files:**
- Create: `docs/platform/entra-app-registration-handoff.md`

**Interfaces:**
- Produces: a document a Campo Digital tenant admin can follow with no
  platform-engineering context. Later tasks (8, 12) reference the exact
  env var names this document tells the admin to hand back:
  `ENTRA_TENANT_ID`, `ENTRA_CLIENT_ID`, `ENTRA_CLIENT_SECRET`.

- [ ] **Step 1: Write the handoff document**

```markdown
# Entra ID app registration — handoff for Campo Digital tenant admin

## Status

Action required from someone with Global Administrator or Application
Administrator rights in the Campo Digital Microsoft 365 tenant. Platform
engineering cannot perform this step.

## What this is for

The Campo Digital platform (staging, at
`https://campo-digital-portal-staging.onrender.com`, and local development)
needs to let real Campo Digital users sign in with their Microsoft account,
and — only for users who administer file uploads — browse the shared
OneDrive/SharePoint source material described in
`docs/source-systems/onedrive.md`.

## What to create

1. Azure Portal → **Microsoft Entra ID** → **App registrations** → **New
   registration**.
2. Name: `Campo Digital Platform (staging)`.
3. Supported account types: **Accounts in this organizational directory
   only (Campo Digital tenant only — Single tenant)**. Do not choose
   "multitenant" or "personal Microsoft accounts".
4. Redirect URI (platform — Web):
   - `http://localhost:8000/auth/entra/callback` (local development)
   - `https://campo-digital-api-staging.onrender.com/auth/entra/callback`
     (Render staging — confirm this is the API service's actual
     `.onrender.com` hostname per `render.yaml`'s existing caveat before
     entering it)
5. After creation, go to **Certificates & secrets** → **New client
   secret**. Copy the secret **value** immediately (it is shown once).
6. Go to **API permissions** → confirm `Microsoft Graph` →
   `User.Read` (delegated) is present (added by default). Do not add any
   other Graph permission yet — the exact scope is decided later, in
   `docs/source-systems/onedrive.md`, once a discovery step (which needs
   this registration to exist) has run and recorded which OneDrive/SharePoint
   location actually holds Campo Digital's source material.
7. Note down, and return to platform engineering over a secure channel (not
   plain email/chat if avoidable — this is a credential):
   - **Directory (tenant) ID** → becomes `ENTRA_TENANT_ID`
   - **Application (client) ID** → becomes `ENTRA_CLIENT_ID`
   - **Client secret value** from step 5 → becomes `ENTRA_CLIENT_SECRET`

## What happens after this

Platform engineering runs a short, read-only discovery script against a
real sign-in using this registration (no client data is touched — only
Graph metadata calls like "list my drives"). That determines whether a
second permission grant is needed:

- If the source material turns out to live in a SharePoint/Teams document
  library (the most likely case, per `docs/source-systems/onedrive.md`),
  the tenant admin will be asked to run one more one-time action:
  `Sites.Selected` permission grant scoped to exactly one site (not every
  site in the tenant). Platform engineering will provide the exact
  `POST /sites/{site-id}/permissions` request body at that point — do not
  pre-grant broader Graph permissions in anticipation of this.

## What this registration will never be used for

- It is never used to sign in as the app itself (no client-credentials
  flow). Every Graph call uses the signing-in Campo Digital user's own
  delegated permissions.
- It does not grant access to anyone's email, calendar, or Teams data —
  only `openid profile` (sign-in) and, for a small set of upload-capable
  users, read access to the specific OneDrive/SharePoint location
  configured in `config/source-catalog.yaml`.
```

- [ ] **Step 2: Commit**

```bash
git add docs/platform/entra-app-registration-handoff.md
git commit -m "docs: add Entra app-registration handoff for tenant admin"
```

---

### EXTERNAL GATE — stop and wait

Nothing in Task 6 onward (any code touching `ENTRA_TENANT_ID`/
`ENTRA_CLIENT_ID`/`ENTRA_CLIENT_SECRET`, or the discovery script) can run
until:

1. A Campo Digital tenant admin has completed Task 1's document end to end.
2. Platform engineering has received `ENTRA_TENANT_ID`, `ENTRA_CLIENT_ID`,
   `ENTRA_CLIENT_SECRET` over a secure channel and stored them in the local
   ignored env file (never committed).

Tasks 2–5 below do not depend on this gate and can proceed in parallel
while waiting for tenant-admin action.

---

### Task 2: Settings, dependencies, and feature flags (no behavior yet)

**Files:**
- Modify: `apps/api/app/config.py`
- Modify: `pyproject.toml`
- Test: `apps/api/tests/test_config.py`

**Interfaces:**
- Produces: `Settings.app_env` unchanged; new optional fields
  `entra_tenant_id: str | None`, `entra_client_id: str | None`,
  `entra_client_secret: SecretStr | None`, `entra_redirect_base_url: str`,
  `platform_token_encryption_key: SecretStr | None`,
  `platform_bootstrap_admin_tenant_id: str | None`,
  `platform_bootstrap_admin_object_id: str | None`,
  `enable_onedrive_import: bool = False`,
  `staging_execution_max_bytes: int = 25 * 1024 * 1024`. All Entra/token
  fields are optional at the `Settings` level (not every environment needs
  them yet) — routers that need them raise a clear error if unset, rather
  than `Settings` construction failing everywhere.

- [ ] **Step 1: Write the failing test**

```python
# apps/api/tests/test_config.py (add to existing file)


def test_new_settings_default_safely() -> None:
    settings = Settings(postgres_password="x")
    assert settings.enable_onedrive_import is False
    assert settings.staging_execution_max_bytes == 25 * 1024 * 1024
    assert settings.entra_tenant_id is None
    assert settings.platform_bootstrap_admin_tenant_id is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest apps/api/tests/test_config.py -v`
Expected: FAIL with `AttributeError` or a `pydantic` validation error — the
fields do not exist yet.

- [ ] **Step 3: Add the fields**

```python
# apps/api/app/config.py — add inside class Settings, after postgres_port

    entra_tenant_id: str | None = Field(default=None, validation_alias="ENTRA_TENANT_ID")
    entra_client_id: str | None = Field(default=None, validation_alias="ENTRA_CLIENT_ID")
    entra_client_secret: SecretStr | None = Field(
        default=None, validation_alias="ENTRA_CLIENT_SECRET"
    )
    entra_redirect_base_url: str = Field(
        default="http://localhost:8000",
        validation_alias="ENTRA_REDIRECT_BASE_URL",
    )

    platform_token_encryption_key: SecretStr | None = Field(
        default=None, validation_alias="PLATFORM_TOKEN_ENCRYPTION_KEY"
    )

    platform_bootstrap_admin_tenant_id: str | None = Field(
        default=None, validation_alias="PLATFORM_BOOTSTRAP_ADMIN_TENANT_ID"
    )
    platform_bootstrap_admin_object_id: str | None = Field(
        default=None, validation_alias="PLATFORM_BOOTSTRAP_ADMIN_OBJECT_ID"
    )

    enable_onedrive_import: bool = Field(
        default=False, validation_alias="ENABLE_ONEDRIVE_IMPORT"
    )
    staging_execution_max_bytes: int = Field(
        default=25 * 1024 * 1024,
        validation_alias="STAGING_EXECUTION_MAX_BYTES",
        gt=0,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest apps/api/tests/test_config.py -v`
Expected: PASS

- [ ] **Step 5: Add new dependencies**

```toml
# pyproject.toml — inside [project.optional-dependencies] api = [...]
  "msal>=1.28,<2",
  "cryptography>=43.0,<44",
```

Run: `uv lock && uv sync --extra api --extra transelec --group dev`

- [ ] **Step 6: Commit**

```bash
git add apps/api/app/config.py apps/api/tests/test_config.py pyproject.toml uv.lock
git commit -m "feat: add Entra/token-encryption/feature-flag settings"
```

---

### Task 3: Migration `0007` — `platform.session`, `platform.ms_graph_grant`

**Files:**
- Create: `migrations/versions/0007_establish_platform_session_and_graph_grant.py`
- Test: `apps/api/integration_tests/test_session_schema.py`

**Interfaces:**
- Produces: `platform.session(id, session_secret_hash, app_user_id, created_at, last_seen_at, expires_at)`,
  `platform.ms_graph_grant(id, app_user_id, access_token_encrypted, refresh_token_encrypted, scope, expires_at, granted_at)`.
  Task 4 depends on `platform.session`'s exact column names above.

- [ ] **Step 1: Write the migration**

```python
"""Establish platform session and Microsoft Graph grant storage.

Revision ID: 0007
Revises: 0006
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the session and Microsoft Graph grant tables."""

    op.create_table(
        "session",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("session_secret_hash", sa.Text(), nullable=False),
        sa.Column("app_user_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "btrim(session_secret_hash) <> ''",
            name="ck_session_session_secret_hash_nonempty",
        ),
        sa.ForeignKeyConstraint(
            ["app_user_id"],
            ["platform.app_user.id"],
            name="fk_session_app_user_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_session"),
        sa.UniqueConstraint("session_secret_hash", name="uq_session_session_secret_hash"),
        schema="platform",
    )
    op.create_index(
        "ix_session_app_user_id",
        "session",
        ["app_user_id"],
        unique=False,
        schema="platform",
    )

    op.create_table(
        "ms_graph_grant",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("app_user_id", sa.BigInteger(), nullable=False),
        sa.Column("access_token_encrypted", sa.LargeBinary(), nullable=False),
        sa.Column("refresh_token_encrypted", sa.LargeBinary(), nullable=False),
        sa.Column("scope", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "granted_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "btrim(scope) <> ''",
            name="ck_ms_graph_grant_scope_nonempty",
        ),
        sa.ForeignKeyConstraint(
            ["app_user_id"],
            ["platform.app_user.id"],
            name="fk_ms_graph_grant_app_user_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_ms_graph_grant"),
        sa.UniqueConstraint("app_user_id", name="uq_ms_graph_grant_app_user_id"),
        schema="platform",
    )


def downgrade() -> None:
    """Remove the session and Microsoft Graph grant tables."""

    op.drop_table("ms_graph_grant", schema="platform")
    op.drop_index("ix_session_app_user_id", table_name="session", schema="platform")
    op.drop_table("session", schema="platform")
```

- [ ] **Step 2: Run the migration against the local dev DB**

Run: `make ensure-platform-db && uv run alembic upgrade head`
Expected: migration `0007` applies cleanly; `alembic current` reports `0007`.

- [ ] **Step 3: Write the schema integration test**

```python
# apps/api/integration_tests/test_session_schema.py

"""platform.session and platform.ms_graph_grant must exist with the shape
Task 4 (session_store.py) and Task 8 (entra_auth.py) depend on.
"""

from __future__ import annotations

from sqlalchemy import Connection, text


def test_session_table_has_expected_columns(connection: Connection) -> None:
    rows = (
        connection.execute(
            text(
                """
            SELECT column_name FROM information_schema.columns
            WHERE table_schema = 'platform' AND table_name = 'session'
            """
            )
        )
        .scalars()
        .all()
    )
    assert set(rows) == {
        "id",
        "session_secret_hash",
        "app_user_id",
        "created_at",
        "last_seen_at",
        "expires_at",
    }


def test_ms_graph_grant_is_one_per_user(connection: Connection) -> None:
    result = connection.execute(
        text(
            """
            SELECT conname FROM pg_constraint
            WHERE conname = 'uq_ms_graph_grant_app_user_id'
            """
        )
    ).scalar_one_or_none()
    assert result == "uq_ms_graph_grant_app_user_id"
```

- [ ] **Step 4: Run the integration test**

Run: `uv run pytest apps/api/integration_tests/test_session_schema.py -v`
Expected: PASS (uses the existing `connection` fixture from
`apps/api/integration_tests/conftest.py`).

- [ ] **Step 5: Run the migration lifecycle check**

Run: `python scripts/migration_check.py`
Expected: PASS — confirms a single head and clean upgrade/downgrade/upgrade
cycle for `0007`.

- [ ] **Step 6: Commit**

```bash
git add migrations/versions/0007_establish_platform_session_and_graph_grant.py \
        apps/api/integration_tests/test_session_schema.py
git commit -m "feat: add platform.session and platform.ms_graph_grant (migration 0007)"
```

---

### Task 4: Postgres-backed hashed-cookie session store + dev-auth restricted to development

**Files:**
- Create: `apps/api/app/session_store.py`
- Test: `apps/api/integration_tests/test_session_store.py`
- Modify: `apps/api/app/dev_auth.py`
- Modify: `apps/api/app/deps.py`
- Modify: `apps/api/app/main.py`
- Modify: `apps/api/tests/test_dev_auth.py`
- Modify: `apps/api/tests/test_main_dev_auth_gate.py`

**Interfaces:**
- Consumes: `platform.session` (Task 3).
- Produces: `app.session_store.PlatformSessionStore` with
  `create_session(connection, *, app_user_id: int, ttl: timedelta) -> str`
  (returns the raw secret to set as the cookie) and
  `resolve_session(connection, raw_secret: str) -> int | None` (returns
  `app_user_id` or `None` if unknown/expired). Task 8 calls
  `create_session` after a successful Entra callback.

- [ ] **Step 1: Write the failing test**

```python
# apps/api/integration_tests/test_session_store.py

"""PlatformSessionStore: hashed-secret sessions backed by platform.session."""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import Connection

from app.access_repository import resolve_or_create_app_user
from app.session_store import PlatformSessionStore


def _make_user(connection: Connection) -> int:
    user = resolve_or_create_app_user(
        connection,
        identity_kind="entra",
        identity_key="tenant-x:oid-y",
        display_name="Test User",
    )
    return user.id


def test_create_and_resolve_round_trip(connection: Connection) -> None:
    store = PlatformSessionStore()
    app_user_id = _make_user(connection)

    raw_secret = store.create_session(connection, app_user_id=app_user_id, ttl=timedelta(hours=8))
    connection.commit()

    resolved = store.resolve_session(connection, raw_secret)
    assert resolved == app_user_id


def test_unknown_secret_resolves_to_none(connection: Connection) -> None:
    store = PlatformSessionStore()
    assert store.resolve_session(connection, "not-a-real-secret") is None


def test_expired_session_resolves_to_none(connection: Connection) -> None:
    store = PlatformSessionStore()
    app_user_id = _make_user(connection)

    raw_secret = store.create_session(
        connection, app_user_id=app_user_id, ttl=timedelta(seconds=-1)
    )
    connection.commit()

    assert store.resolve_session(connection, raw_secret) is None


def test_raw_secret_is_never_stored(connection: Connection) -> None:
    from sqlalchemy import text

    store = PlatformSessionStore()
    app_user_id = _make_user(connection)
    raw_secret = store.create_session(connection, app_user_id=app_user_id, ttl=timedelta(hours=8))

    stored_hashes = (
        connection.execute(text("SELECT session_secret_hash FROM platform.session")).scalars().all()
    )
    assert raw_secret not in stored_hashes
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest apps/api/integration_tests/test_session_store.py -v`
Expected: FAIL — `app.session_store` does not exist yet.

- [ ] **Step 3: Implement `PlatformSessionStore`**

```python
# apps/api/app/session_store.py
"""Postgres-backed, hashed-secret session store for real (Entra) identities.

The raw secret is generated the same way app.dev_auth.DevSessionStore
generates its token (secrets.token_urlsafe), but only its SHA-256 hash is
persisted — a database read alone can never mint a session.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import Connection, text


def _hash_secret(raw_secret: str) -> str:
    return hashlib.sha256(raw_secret.encode("utf-8")).hexdigest()


class PlatformSessionStore:
    """Issues and resolves durable, hashed-secret sessions in `platform.session`."""

    def create_session(self, connection: Connection, *, app_user_id: int, ttl: timedelta) -> str:
        """Issue a new session for `app_user_id`, returning the raw cookie secret."""

        raw_secret = secrets.token_urlsafe(32)
        expires_at = datetime.now(UTC) + ttl

        connection.execute(
            text(
                """
                INSERT INTO platform.session (session_secret_hash, app_user_id, expires_at)
                VALUES (:session_secret_hash, :app_user_id, :expires_at)
                """
            ),
            {
                "session_secret_hash": _hash_secret(raw_secret),
                "app_user_id": app_user_id,
                "expires_at": expires_at,
            },
        )
        return raw_secret

    def resolve_session(self, connection: Connection, raw_secret: str) -> int | None:
        """Return the session's `app_user_id`, or None if unknown/expired."""

        row = connection.execute(
            text(
                """
                UPDATE platform.session
                SET last_seen_at = now()
                WHERE session_secret_hash = :session_secret_hash
                  AND expires_at > now()
                RETURNING app_user_id
                """
            ),
            {"session_secret_hash": _hash_secret(raw_secret)},
        ).one_or_none()

        return row.app_user_id if row is not None else None

    def clear_session(self, connection: Connection, raw_secret: str) -> None:
        """Invalidate a session, if present."""

        connection.execute(
            text("DELETE FROM platform.session WHERE session_secret_hash = :session_secret_hash"),
            {"session_secret_hash": _hash_secret(raw_secret)},
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest apps/api/integration_tests/test_session_store.py -v`
Expected: PASS

- [ ] **Step 5: Restrict dev-auth to development only**

```python
# apps/api/app/dev_auth.py — replace assert_dev_auth_allowed


def assert_dev_auth_allowed(settings: Settings) -> None:
    """Raise unless the configured environment permits dev-only auth."""

    if settings.app_env != "development":
        raise DevAuthDisabledInProductionError(
            "Dev-only authentication must never run outside APP_ENV=development."
        )
```

```python
# apps/api/app/main.py — replace the dev-auth mounting condition

if os.environ.get("APP_ENV", "development") == "development":
    from app.routers.dev_auth import router as dev_auth_router

    app.include_router(dev_auth_router)
```

- [ ] **Step 6: Update dev-auth tests for the tightened gate**

```python
# apps/api/tests/test_dev_auth.py — replace test_dev_auth_allowed_in_staging


def test_dev_auth_rejected_in_staging() -> None:
    # ADR-005 originally allowed dev-auth in staging; the secure-file-access
    # slice closes that exposure now that real Entra sign-in exists.
    with pytest.raises(DevAuthDisabledInProductionError):
        assert_dev_auth_allowed(_settings("staging"))


def test_dev_auth_rejected_in_test() -> None:
    with pytest.raises(DevAuthDisabledInProductionError):
        assert_dev_auth_allowed(_settings("test"))
```

Note: this removes the seam pytest fixtures previously relied on
(`APP_ENV=test` no longer gets dev-auth). Check
`apps/api/integration_tests/conftest.py` and
`apps/api/integration_tests/test_dev_auth_router.py` for any fixture that
called `assert_dev_auth_allowed` under `test` — route those fixtures to call
`resolve_or_create_app_user` / `PlatformSessionStore` directly instead of
going through the dev-login HTTP endpoint.

```python
# apps/api/tests/test_main_dev_auth_gate.py — replace the staging test


def test_dev_auth_routes_not_mounted_in_staging() -> None:
    output = _run_with_env("staging")
    assert "AUTH_MOUNTED=False" in output


def test_dev_auth_routes_not_mounted_in_test() -> None:
    output = _run_with_env("test")
    assert "AUTH_MOUNTED=False" in output
```

- [ ] **Step 7: Wire `deps.py` to try the real session store first**

```python
# apps/api/app/deps.py — replace get_current_identity_key / get_current_app_user

from app.config import Settings, get_settings
from app.dev_auth import DevAuthDisabledInProductionError, assert_dev_auth_allowed
from app.session_store import PlatformSessionStore

_platform_session_store = PlatformSessionStore()


def get_platform_session_store() -> PlatformSessionStore:
    return _platform_session_store


def get_current_app_user(
    settings: Annotated[Settings, Depends(get_settings)],
    connection: Annotated[Connection, Depends(get_db_connection)],
    platform_sessions: Annotated[PlatformSessionStore, Depends(get_platform_session_store)],
    dev_sessions: Annotated[DevSessionStore, Depends(get_session_store)],
    session_token: Annotated[str | None, Cookie(alias=SESSION_COOKIE_NAME)] = None,
) -> AppUser:
    """Resolve the caller's app_user row: real session first, dev-auth fallback."""

    if session_token is None:
        raise HTTPException(status_code=401, detail="Not authenticated.")

    app_user_id = platform_sessions.resolve_session(connection, session_token)
    if app_user_id is not None:
        return _load_app_user(connection, app_user_id)

    try:
        assert_dev_auth_allowed(settings)
    except DevAuthDisabledInProductionError as exc:
        raise HTTPException(status_code=401, detail="Not authenticated.") from exc

    identity_key = dev_sessions.resolve_session(session_token)
    if identity_key is None:
        raise HTTPException(status_code=401, detail="Not authenticated.")

    display_name = next(
        (i.display_name for i in SEEDED_DEV_IDENTITIES if i.identity_key == identity_key),
        identity_key,
    )
    return resolve_or_create_app_user(
        connection,
        identity_kind=DEV_IDENTITY_KIND,
        identity_key=identity_key,
        display_name=display_name,
    )


def _load_app_user(connection: Connection, app_user_id: int) -> AppUser:
    row = connection.execute(
        text(
            "SELECT id, identity_kind, identity_key, display_name, email "
            "FROM platform.app_user WHERE id = :id"
        ),
        {"id": app_user_id},
    ).one()
    return AppUser(
        id=row.id,
        identity_kind=row.identity_kind,
        identity_key=row.identity_key,
        display_name=row.display_name,
        email=row.email,
    )
```

Remove the now-unused standalone `get_current_identity_key` dependency, or
keep it delegating to `get_current_app_user().identity_key` if
`routers/dev_auth.py`'s `logout` still needs a lightweight identity check —
either is fine; do not duplicate session-resolution logic in two places.

- [ ] **Step 8: Run the full API test suite**

Run: `uv run pytest apps/api/tests apps/api/integration_tests -v`
Expected: PASS, including the updated staging/test dev-auth-rejection tests.

- [ ] **Step 9: Commit**

```bash
git add apps/api/app/session_store.py apps/api/app/dev_auth.py apps/api/app/deps.py \
        apps/api/app/main.py apps/api/tests/test_dev_auth.py \
        apps/api/tests/test_main_dev_auth_gate.py \
        apps/api/integration_tests/test_session_store.py
git commit -m "feat: add hashed-cookie session store, restrict dev-auth to development"
```

---

### Task 5: Bootstrap-admin grant helper (unit-testable, no HTTP yet)

**Files:**
- Modify: `apps/api/app/access_repository.py`
- Test: `apps/api/integration_tests/test_access_repository.py`

**Interfaces:**
- Produces: `maybe_grant_bootstrap_admin(connection, *, settings: Settings, tenant_id: str, object_id: str, app_user_id: int) -> bool`
  — returns whether it granted anything. Task 8's Entra callback calls this
  once, right after resolving the app_user, before issuing a session.

- [ ] **Step 1: Write the failing test**

```python
# apps/api/integration_tests/test_access_repository.py (append)

from app.access_repository import list_grants_for_user, maybe_grant_bootstrap_admin
from app.config import Settings


def _bootstrap_settings() -> Settings:
    return Settings(
        postgres_password="x",
        platform_bootstrap_admin_tenant_id="tenant-x",
        platform_bootstrap_admin_object_id="oid-y",
    )


def test_bootstrap_grants_admin_on_all_products_for_matching_identity(connection) -> None:
    user = resolve_or_create_app_user(
        connection,
        identity_kind="entra",
        identity_key="tenant-x:oid-y",
        display_name="Bootstrap Admin",
    )

    granted = maybe_grant_bootstrap_admin(
        connection,
        settings=_bootstrap_settings(),
        tenant_id="tenant-x",
        object_id="oid-y",
        app_user_id=user.id,
    )

    assert granted is True
    grants = {
        g.product_key: g.role.value for g in list_grants_for_user(connection, app_user_id=user.id)
    }
    assert grants == {"lidar": "admin", "forestry": "admin", "transelect": "admin"}


def test_bootstrap_does_not_fire_for_non_matching_identity(connection) -> None:
    user = resolve_or_create_app_user(
        connection,
        identity_kind="entra",
        identity_key="tenant-x:someone-else",
        display_name="Regular User",
    )

    granted = maybe_grant_bootstrap_admin(
        connection,
        settings=_bootstrap_settings(),
        tenant_id="tenant-x",
        object_id="someone-else",
        app_user_id=user.id,
    )

    assert granted is False
    assert list_grants_for_user(connection, app_user_id=user.id) == ()


def test_bootstrap_does_not_fire_if_user_already_has_a_grant(connection) -> None:
    user = resolve_or_create_app_user(
        connection,
        identity_kind="entra",
        identity_key="tenant-x:oid-y",
        display_name="Bootstrap Admin",
    )
    grant_product_role(connection, app_user_id=user.id, product_key="forestry", role=Role.VIEWER)

    granted = maybe_grant_bootstrap_admin(
        connection,
        settings=_bootstrap_settings(),
        tenant_id="tenant-x",
        object_id="oid-y",
        app_user_id=user.id,
    )

    assert granted is False
    grants = {
        g.product_key: g.role.value for g in list_grants_for_user(connection, app_user_id=user.id)
    }
    assert grants == {"forestry": "viewer"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest apps/api/integration_tests/test_access_repository.py -k bootstrap -v`
Expected: FAIL — `maybe_grant_bootstrap_admin` does not exist.

- [ ] **Step 3: Implement it**

```python
# apps/api/app/access_repository.py (append)

from app.config import Settings

_BOOTSTRAP_PRODUCT_KEYS = ("lidar", "forestry", "transelect")


def maybe_grant_bootstrap_admin(
    connection: Connection,
    *,
    settings: Settings,
    tenant_id: str,
    object_id: str,
    app_user_id: int,
) -> bool:
    """Grant one-time bootstrap ADMIN if this identity matches config and holds no grants."""

    configured_tenant = settings.platform_bootstrap_admin_tenant_id
    configured_object = settings.platform_bootstrap_admin_object_id
    if not configured_tenant or not configured_object:
        return False
    if configured_tenant != tenant_id or configured_object != object_id:
        return False
    if list_grants_for_user(connection, app_user_id=app_user_id):
        return False

    for product_key in _BOOTSTRAP_PRODUCT_KEYS:
        grant_product_role(
            connection, app_user_id=app_user_id, product_key=product_key, role=Role.ADMIN
        )
    return True
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest apps/api/integration_tests/test_access_repository.py -k bootstrap -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/access_repository.py apps/api/integration_tests/test_access_repository.py
git commit -m "feat: add one-time config-driven bootstrap-admin grant"
```

---

### Task 6: Graph discovery spike (throwaway script)

**Blocked on:** the EXTERNAL GATE after Task 1 — do not start until
`ENTRA_TENANT_ID`/`ENTRA_CLIENT_ID`/`ENTRA_CLIENT_SECRET` are in the local
ignored env file.

**Files:**
- Create: `scripts/graph_discovery_spike.py` (not imported by `app.*`; not
  covered by `make check`'s architecture-boundary or coverage gates —
  add it to any exclude list that scripts already use, e.g. alongside
  `scripts/campo_demo.py` if that is excluded from coverage)

**Interfaces:**
- Produces: printed JSON a human reads to make the Task 7 decision. No
  return value consumed by other code — this script is deleted or moved to
  `docs/` as a recorded artifact once Task 7 is done, per the spec's
  "short, throwaway discovery script" framing.

- [ ] **Step 1: Write the script**

**Revised 2026-09-01:** the source is now confirmed personal OneDrive
(spec section 2 revision), not an unknown drive/site type — so this
script no longer searches broadly (`/sites?search=`) or requests
`Sites.Read.All`. It requests only delegated `Files.Read`, and follows
the confirmed shape directly: list the signing-in user's own OneDrive
root, find the `remoteItem`-faceted child for the shared Campo Digital
folder, and resolve it via `remoteItem.parentReference.driveId` +
`remoteItem.id`. It does not use `GET /me/drive/sharedWithMe` — that
endpoint is deprecated and documented to stop returning data after
November 2026. It also uses the `common` authority so a personal
Microsoft account sign-in works, matching the app registration's
account-type change in Task 1.

```python
# scripts/graph_discovery_spike.py
"""Throwaway Microsoft Graph discovery spike.

Run manually, once, against a real Campo Digital sign-in (a personal
Microsoft account), to confirm the shared `00 Hub Digital CampoDigital`
folder's remoteItem shape and record its stable driveId/itemId. Never
touches client file content — only metadata calls (own drive root,
children). Deliberately does NOT call the deprecated
`GET /me/drive/sharedWithMe` (stops returning data after November 2026)
and does NOT request `Sites.Read.All` — the source is confirmed personal
OneDrive, not SharePoint, so only delegated `Files.Read` is requested,
per the least-privilege decision in the spec's section 2 revision.

Usage:
    uv run python scripts/graph_discovery_spike.py

Requires ENTRA_CLIENT_ID in the environment (see
docs/platform/entra-app-registration-handoff.md; ENTRA_TENANT_ID is not
used here — the authority is `common` so this also works for a personal
Microsoft account sign-in). Opens a device-code sign-in prompt in the
terminal — sign in as the real Campo Digital user (personal Microsoft
account) who already has the shared folder in their own OneDrive.
"""

from __future__ import annotations

import json
import os
import sys

import msal
import requests

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
SHARED_FOLDER_NAME = "00 Hub Digital CampoDigital"


def _acquire_token() -> str:
    client_id = os.environ["ENTRA_CLIENT_ID"]

    app = msal.PublicClientApplication(
        client_id, authority="https://login.microsoftonline.com/common"
    )
    flow = app.initiate_device_flow(scopes=["Files.Read"])
    if "user_code" not in flow:
        raise RuntimeError(f"Failed to create device flow: {flow}")
    print(flow["message"])
    result = app.acquire_token_by_device_flow(flow)
    if "access_token" not in result:
        raise RuntimeError(f"Sign-in failed: {result}")
    return result["access_token"]


def _get(token: str, path: str) -> dict:
    response = requests.get(
        f"{GRAPH_BASE}{path}", headers={"Authorization": f"Bearer {token}"}, timeout=30
    )
    response.raise_for_status()
    return response.json()


def main() -> None:
    token = _acquire_token()

    print("\n=== id_token claims (tid/oid) ===")
    # msal doesn't expose claims from the device-flow result directly by
    # path here; if needed, decode the ID token from `result` in
    # _acquire_token and print `tid`/`oid` to confirm the identity-key
    # shape documented in the spec's section 1 revision before Task 8
    # relies on it.

    print("\n=== /me/drive/root/children ===")
    own_root = _get(token, "/me/drive/root/children")
    print(json.dumps(own_root, indent=2))

    shared_folder = next(
        (
            item
            for item in own_root.get("value", [])
            if item.get("name") == SHARED_FOLDER_NAME and "remoteItem" in item
        ),
        None,
    )
    if shared_folder is None:
        raise RuntimeError(
            f"No remoteItem-faceted child named {SHARED_FOLDER_NAME!r} found in "
            "/me/drive/root/children. Do not fall back to the deprecated "
            "/me/drive/sharedWithMe endpoint — investigate the exact folder "
            "name/placement in the signing-in user's own OneDrive instead."
        )

    remote = shared_folder["remoteItem"]
    remote_drive_id = remote["parentReference"]["driveId"]
    remote_item_id = remote["id"]
    print(f"\nremoteItem driveId={remote_drive_id} itemId={remote_item_id}")

    print(f"\n=== /drives/{remote_drive_id}/items/{remote_item_id}/children ===")
    children = _get(token, f"/drives/{remote_drive_id}/items/{remote_item_id}/children")
    for item in children.get("value", []):
        print(f"  {item['name']}  (id={item['id']})")


if __name__ == "__main__":
    sys.exit(main() or 0)
```

- [ ] **Step 2: Add a throwaway-script dependency note**

`requests` is not currently a dependency; add it as a `dev`-group-only
addition scoped to running this one script (do not add it to the `api`
extra — the running application never needs a synchronous HTTP client
outside `app.graph_client`, built in Task 12 on `httpx`, which IS an `api`
dependency already transitively via `fastapi`/`starlette` test client —
confirm before adding `requests` at all; prefer reusing `httpx` if already
available: `httpx.Client(...).get(...)` with the same call shape).

- [ ] **Step 3: Run it manually and capture raw output**

Run: `uv run python scripts/graph_discovery_spike.py`

This step has no pass/fail assertion — its output is the input to Task 7.
Save the full terminal output to a local (not committed) scratch file for
reference while writing Task 7's RESULT entry.

- [ ] **Step 4: Commit the script (not its output)**

```bash
git add scripts/graph_discovery_spike.py
git commit -m "chore: add throwaway Microsoft Graph discovery spike script"
```

---

### Task 7: Record discovery RESULT, finalize Graph scope and stable IDs

**Blocked on:** Task 6's manual run producing real output.

**Files:**
- Modify: `docs/source-systems/onedrive.md`
- Modify: `config/source-catalog.yaml`

**Interfaces:**
- Produces: `config/source-catalog.yaml` entries with `drive_id`,
  `site_id` (nullable), and `root_item_id` per project, and a documented
  `graph_scope` value. Task 12's `graph_client.py` and the intersection
  authorization check read these exact keys — do not invent different key
  names when this task is executed; keep them in sync with whatever Task 12
  ends up reading.

- [ ] **Step 1: Add the RESULT entry to `docs/source-systems/onedrive.md`**

Append a section shaped like this, filled in with Task 6's actual output
(this is illustrative structure, not a value to copy — the real drive/site
type and IDs come only from the real discovery run):

```markdown
## RESULT (fill in real date) — Graph discovery

Discovery run via `scripts/graph_discovery_spike.py` against a real Campo
Digital sign-in (personal Microsoft account). Confirmed pre-discovery
(browser URL inspection, 2026-09-01): `00 Hub Digital CampoDigital` is a
personal OneDrive owned by a different personal Microsoft account,
appearing as a `remoteItem` in the signing-in user's own OneDrive — this
run exists to record the exact stable IDs and confirm `Files.Read`
against a real token, not to re-decide the drive type.

- `remoteItem.parentReference.driveId = <value>`,
  `remoteItem.id = <value>` for `00 Hub Digital CampoDigital`, resolved
  from `/me/drive/root/children`.
- Chosen least-privileged Graph scope: `Files.Read`, confirmed sufficient
  to enumerate `/drives/{driveId}/items/{itemId}/children` for the
  resolved remote item. [If insufficient: record the exact Graph error
  under `Files.Read` and the justification for escalating to
  `Files.Read.All` — never straight to a Sites/tenant-admin permission,
  which does not apply to this personal-OneDrive source.]
- `tid`/`oid` observed on the real ID token (confirms or corrects the
  spec section 1 revision's documented-but-unverified expectation that
  `tid` is the constant personal-account placeholder
  `9188040d-6c67-4c5b-b112-36a304b66dad`): `tid = <value>`, `oid = <value>`.
```

- [ ] **Step 2: Add stable IDs to `config/source-catalog.yaml`**

```yaml
# config/source-catalog.yaml — add to each relevant project entry, e.g.:

  forestry:
    display_name: "Gestión Predial Forestal / QGIS"
    bounded_context: forestry
    repository_root: "products/forestry"
    source_paths:
      - "01_Gestion_Predial_Forestal"
    graph:
      drive_id: "<value from discovery RESULT>"
      site_id: null  # or the site id, if SharePoint-backed
      root_item_id: "<value from discovery RESULT>"
    expected_extensions: [...]
```

Apply the same `graph:` block shape to `lidar` and `transelect`. Leave
`shared_sources`/`archive` entries without a `graph:` block unless a later
task needs them — this slice only needs per-product roots.

- [ ] **Step 3: Run the doc-link and nav checks**

Run: `python scripts/check_doc_links.py`
Expected: PASS (no broken links introduced).

- [ ] **Step 4: Commit**

```bash
git add docs/source-systems/onedrive.md config/source-catalog.yaml
git commit -m "docs: record Microsoft Graph discovery RESULT and finalize scope"
```

---

### Task 8: Entra sign-in flow (msal, PKCE, bootstrap, two-step consent scaffolding)

**Files:**
- Create: `apps/api/app/entra_auth.py`
- Create: `apps/api/app/routers/entra_auth.py`
- Test: `apps/api/tests/test_entra_auth.py`
- Test: `apps/api/integration_tests/test_entra_auth_router.py`
- Modify: `apps/api/app/main.py`

**Interfaces:**
- Consumes: `Settings.entra_*` (Task 2), `PlatformSessionStore` (Task 4),
  `maybe_grant_bootstrap_admin` (Task 5).
- Produces: `app.entra_auth.build_msal_app(settings) -> msal.ConfidentialClientApplication`,
  `app.entra_auth.resolve_identity_from_claims(claims: dict) -> tuple[str, str, str]`
  (returns `(tenant_id, object_id, identity_key)`). Router exposes
  `GET /auth/entra/login`, `GET /auth/entra/callback`,
  `GET /auth/entra/graph-consent/start`, `GET /auth/entra/graph-consent/callback`.
  Task 12's Graph client reads the resulting `platform.ms_graph_grant` row.

- [ ] **Step 1: Write the failing unit test for identity resolution**

```python
# apps/api/tests/test_entra_auth.py

from app.entra_auth import resolve_identity_from_claims


def test_resolve_identity_from_claims_uses_tid_and_oid_never_email() -> None:
    claims = {
        "tid": "tenant-x",
        "oid": "oid-y",
        "preferred_username": "someone@campodigital.cl",
        "name": "Someone",
    }
    tenant_id, object_id, identity_key = resolve_identity_from_claims(claims)
    assert tenant_id == "tenant-x"
    assert object_id == "oid-y"
    assert identity_key == "tenant-x:oid-y"


def test_resolve_identity_from_claims_handles_personal_microsoft_account() -> None:
    # Revised 2026-09-01: the app registration now supports personal
    # Microsoft accounts (spec section 1 revision). Public documentation
    # says personal-account sign-ins carry a constant placeholder `tid`
    # (the well-known "consumers" tenant ID) rather than a real
    # organizational tenant ID — confirm this against Task 6/7's real
    # discovery output before trusting it further; this test only checks
    # that resolve_identity_from_claims does not special-case or reject
    # that placeholder value.
    claims = {
        "tid": "9188040d-6c67-4c5b-b112-36a304b66dad",
        "oid": "oid-personal",
        "name": "Someone",
    }
    tenant_id, object_id, identity_key = resolve_identity_from_claims(claims)
    assert tenant_id == "9188040d-6c67-4c5b-b112-36a304b66dad"
    assert object_id == "oid-personal"
    assert identity_key == "9188040d-6c67-4c5b-b112-36a304b66dad:oid-personal"


def test_resolve_identity_from_claims_requires_tid_and_oid() -> None:
    import pytest

    with pytest.raises(KeyError):
        resolve_identity_from_claims({"preferred_username": "x@campodigital.cl"})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest apps/api/tests/test_entra_auth.py -v`
Expected: FAIL — module does not exist.

- [ ] **Step 3: Implement `app/entra_auth.py`**

```python
# apps/api/app/entra_auth.py
"""msal-backed Entra ID confidential-client auth code + PKCE flow.

Every function here is pure/stateless except `build_msal_app`, which
constructs msal's own in-memory token cache per call — Graph tokens that
must persist are written to platform.ms_graph_grant by the router, not kept
in this cache across requests.
"""

from __future__ import annotations

import msal

from app.config import Settings

SIGN_IN_SCOPES: tuple[str, ...] = ("openid", "profile")

# Revised 2026-09-01: the app registration supports "any organizational
# directory + personal Microsoft accounts" (spec section 1 revision), so
# the authority must be the multi-tenant `common` endpoint, never an
# authority pinned to the app registration's home tenant — pinning to
# ENTRA_TENANT_ID would silently reject personal-account sign-ins.
_AUTHORITY = "https://login.microsoftonline.com/common"


class EntraNotConfiguredError(RuntimeError):
    """Raised when Entra settings are required but unset."""


def build_msal_app(settings: Settings) -> msal.ConfidentialClientApplication:
    """Construct the confidential-client app for one request's token exchange."""

    if not (settings.entra_client_id and settings.entra_client_secret):
        raise EntraNotConfiguredError("ENTRA_CLIENT_ID/ENTRA_CLIENT_SECRET must both be set.")

    return msal.ConfidentialClientApplication(
        settings.entra_client_id,
        authority=_AUTHORITY,
        client_credential=settings.entra_client_secret.get_secret_value(),
    )


def resolve_identity_from_claims(claims: dict[str, object]) -> tuple[str, str, str]:
    """Extract (tenant_id, object_id, identity_key) from a validated ID token's claims."""

    tenant_id = str(claims["tid"])
    object_id = str(claims["oid"])
    return tenant_id, object_id, f"{tenant_id}:{object_id}"


def redirect_uri(settings: Settings, *, path: str) -> str:
    """Build a redirect URI under the configured base URL."""

    return f"{settings.entra_redirect_base_url.rstrip('/')}{path}"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest apps/api/tests/test_entra_auth.py -v`
Expected: PASS

- [ ] **Step 5: Implement the router**

```python
# apps/api/app/routers/entra_auth.py
"""Real Entra ID sign-in and incremental Graph consent."""

from __future__ import annotations

from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy import Connection

from app.access import Action, can
from app.access_repository import (
    get_product_role,
    list_grants_for_user,
    maybe_grant_bootstrap_admin,
    resolve_or_create_app_user,
)
from app.audit import record_audit_event
from app.config import Settings, get_settings
from app.deps import (
    SESSION_COOKIE_NAME,
    get_current_app_user,
    get_db_connection,
    get_platform_session_store,
)
from app.entra_auth import (
    SIGN_IN_SCOPES,
    build_msal_app,
    redirect_uri,
    resolve_identity_from_claims,
)
from app.session_store import PlatformSessionStore

router = APIRouter(prefix="/auth/entra", tags=["auth"])

_SESSION_TTL = timedelta(hours=12)
_STATE_COOKIE_NAME = "campo_entra_state"


@router.get("/login")
def login(settings: Annotated[Settings, Depends(get_settings)]) -> RedirectResponse:
    """Redirect to Microsoft's sign-in page, requesting only openid+profile."""

    msal_app = build_msal_app(settings)
    auth_url = msal_app.get_authorization_request_url(
        list(SIGN_IN_SCOPES),
        redirect_uri=redirect_uri(settings, path="/auth/entra/callback"),
    )
    return RedirectResponse(auth_url)


@router.get("/callback")
def callback(
    request: Request,
    response: Response,
    settings: Annotated[Settings, Depends(get_settings)],
    connection: Annotated[Connection, Depends(get_db_connection)],
    session_store: Annotated[PlatformSessionStore, Depends(get_platform_session_store)],
) -> RedirectResponse:
    """Exchange the authorization code, resolve identity, issue a session."""

    code = request.query_params.get("code")
    if not code:
        raise HTTPException(status_code=400, detail="Missing authorization code.")

    msal_app = build_msal_app(settings)
    result = msal_app.acquire_token_by_authorization_code(
        code,
        scopes=list(SIGN_IN_SCOPES),
        redirect_uri=redirect_uri(settings, path="/auth/entra/callback"),
    )
    if "id_token_claims" not in result:
        raise HTTPException(status_code=401, detail="Entra sign-in failed.")

    tenant_id, object_id, identity_key = resolve_identity_from_claims(result["id_token_claims"])
    display_name = str(result["id_token_claims"].get("name", identity_key))

    user = resolve_or_create_app_user(
        connection,
        identity_kind="entra",
        identity_key=identity_key,
        display_name=display_name,
    )
    maybe_grant_bootstrap_admin(
        connection,
        settings=settings,
        tenant_id=tenant_id,
        object_id=object_id,
        app_user_id=user.id,
    )

    raw_secret = session_store.create_session(connection, app_user_id=user.id, ttl=_SESSION_TTL)
    record_audit_event(connection, actor_app_user_id=user.id, event_type="session.created")

    redirect = RedirectResponse(url="/archivos")
    redirect.set_cookie(SESSION_COOKIE_NAME, raw_secret, httponly=True, samesite="lax", secure=True)
    return redirect


@router.get("/graph-consent/start")
def graph_consent_start(
    user: Annotated["AppUser", Depends(get_current_app_user)],  # noqa: F821 - imported type below
    connection: Annotated[Connection, Depends(get_db_connection)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> RedirectResponse:
    """Incremental consent: only for a user with an UPLOAD-capable grant."""

    grants = list_grants_for_user(connection, app_user_id=user.id)
    if not any(can(g.role, Action.UPLOAD) for g in grants):
        raise HTTPException(
            status_code=403, detail="Graph file access requires an upload-capable grant."
        )

    graph_scope = _required_graph_scope(settings)
    msal_app = build_msal_app(settings)
    auth_url = msal_app.get_authorization_request_url(
        [graph_scope],
        redirect_uri=redirect_uri(settings, path="/auth/entra/graph-consent/callback"),
    )
    return RedirectResponse(auth_url)


def _required_graph_scope(settings: Settings) -> str:
    """Raise until Task 7's RESULT is wired in — never guess a Graph scope."""

    raise NotImplementedError(
        "Graph scope is not yet configured. This must be set from the discovery "
        "RESULT recorded in docs/source-systems/onedrive.md (see Task 7 and "
        "Task 12) before this endpoint is reachable."
    )
```

Note: `_required_graph_scope` is intentionally a hard `NotImplementedError`,
not a guessed default — Task 12 replaces it with a read from
`config/source-catalog.yaml`'s `graph_scope` value once Task 7 has recorded
it. This keeps `graph-consent/start` merely *unreachable* (500, clearly
logged) rather than silently requesting a wrong/broader scope if executed
out of order.

- [ ] **Step 6: Mount the router**

```python
# apps/api/app/main.py — add near the other router includes

from app.routers.entra_auth import router as entra_auth_router

...
app.include_router(entra_auth_router)
```

- [ ] **Step 7: Write the integration test for the callback's identity/bootstrap path**

```python
# apps/api/integration_tests/test_entra_auth_router.py
"""Entra callback identity resolution and bootstrap, isolated from real msal
network calls by monkeypatching build_msal_app's acquire_token_by_authorization_code.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.main import app


def test_callback_creates_user_and_session_cookie(connection) -> None:
    fake_result = {"id_token_claims": {"tid": "tenant-x", "oid": "oid-y", "name": "Someone"}}
    with patch("app.routers.entra_auth.build_msal_app") as build_msal_app:
        build_msal_app.return_value.acquire_token_by_authorization_code.return_value = fake_result
        client = TestClient(app)
        response = client.get("/auth/entra/callback?code=fake-code", follow_redirects=False)

    assert response.status_code in (302, 307)
    assert "campo_session" in response.cookies
```

Adapt this test to however `apps/api/integration_tests/conftest.py` wires
the `connection`/app dependency overrides for other router tests (see
`test_dev_auth_router.py` for the existing pattern) — do not introduce a
second, divergent test-DB setup convention.

- [ ] **Step 8: Run the tests**

Run: `uv run pytest apps/api/tests/test_entra_auth.py apps/api/integration_tests/test_entra_auth_router.py -v`
Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add apps/api/app/entra_auth.py apps/api/app/routers/entra_auth.py apps/api/app/main.py \
        apps/api/tests/test_entra_auth.py apps/api/integration_tests/test_entra_auth_router.py
git commit -m "feat: add Entra ID sign-in flow with bootstrap-admin and consent scaffolding"
```

---

### Task 9: Grants management (admin-only)

**Files:**
- Create: `apps/api/app/routers/access_admin.py`
- Test: `apps/api/integration_tests/test_access_admin_router.py`
- Modify: `apps/api/app/main.py`
- Create: `apps/portal/src/pages/Grants.tsx`
- Create: `apps/portal/src/pages/Grants.test.tsx`
- Modify: `apps/portal/src/lib/platformApi.ts`
- Modify: `apps/portal/src/App.tsx`

**Interfaces:**
- Consumes: `Action.MANAGE_ACCESS`, `ensure_can` (existing `app/deps.py`).
- Produces: `GET /access/users` (admin-only, lists every `app_user` who has
  ever logged in, with their current grants), `PUT /access/users/{id}/grants/{product_key}`
  (body `{"role": "admin"|"operator"|"viewer"|null}`, `null` revokes).

- [ ] **Step 1: Write the failing integration test**

```python
# apps/api/integration_tests/test_access_admin_router.py

from __future__ import annotations

from app.access import Role
from app.access_repository import grant_product_role, resolve_or_create_app_user


def test_list_users_requires_admin_on_some_product(client, connection) -> None:
    viewer = resolve_or_create_app_user(
        connection,
        identity_kind="entra",
        identity_key="t:viewer",
        display_name="Viewer",
    )
    grant_product_role(connection, app_user_id=viewer.id, product_key="forestry", role=Role.VIEWER)
    connection.commit()

    response = client.get("/access/users", cookies={"campo_session": _login_as(viewer.id)})
    assert response.status_code == 403


def test_admin_can_set_and_revoke_a_grant(client, connection) -> None:
    admin = resolve_or_create_app_user(
        connection,
        identity_kind="entra",
        identity_key="t:admin",
        display_name="Admin",
    )
    grant_product_role(connection, app_user_id=admin.id, product_key="lidar", role=Role.ADMIN)
    target = resolve_or_create_app_user(
        connection,
        identity_kind="entra",
        identity_key="t:target",
        display_name="Target",
    )
    connection.commit()

    cookies = {"campo_session": _login_as(admin.id)}
    set_response = client.put(
        f"/access/users/{target.id}/grants/forestry",
        json={"role": "operator"},
        cookies=cookies,
    )
    assert set_response.status_code == 200

    revoke_response = client.put(
        f"/access/users/{target.id}/grants/forestry",
        json={"role": None},
        cookies=cookies,
    )
    assert revoke_response.status_code == 200
```

Fill in `_login_as`/`client` fixtures consistently with whatever
`apps/api/integration_tests/conftest.py` already provides for
`test_ingestion_router.py`'s admin-only `/ingesta/audit` test — reuse that
pattern rather than inventing a new one.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest apps/api/integration_tests/test_access_admin_router.py -v`
Expected: FAIL — router does not exist.

- [ ] **Step 3: Implement the router**

```python
# apps/api/app/routers/access_admin.py
"""Admin-only grants management: onboarding real users beyond the bootstrap admin."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import Connection, text

from app.access import Action, Role
from app.access_repository import AppUser, grant_product_role, list_grants_for_user
from app.audit import record_audit_event
from app.deps import ensure_can, get_current_app_user, get_db_connection

router = APIRouter(prefix="/access", tags=["access"])

PRODUCT_KEYS = ("lidar", "forestry", "transelect")


class GrantView(BaseModel):
    product_key: str
    role: str


class UserWithGrantsView(BaseModel):
    id: int
    identity_kind: str
    display_name: str
    grants: list[GrantView]


class SetGrantRequest(BaseModel):
    role: Role | None


def _require_admin_on_any_product(connection: Connection, *, app_user_id: int) -> None:
    grants = list_grants_for_user(connection, app_user_id=app_user_id)
    if not any(g.role is Role.ADMIN for g in grants):
        raise HTTPException(status_code=403, detail="Admin access required.")


@router.get("/users", response_model=list[UserWithGrantsView])
def list_users(
    user: Annotated[AppUser, Depends(get_current_app_user)],
    connection: Annotated[Connection, Depends(get_db_connection)],
) -> list[UserWithGrantsView]:
    """List every user who has ever logged in, with their current grants."""

    _require_admin_on_any_product(connection, app_user_id=user.id)

    rows = connection.execute(
        text("SELECT id, identity_kind, display_name FROM platform.app_user ORDER BY id")
    ).all()

    return [
        UserWithGrantsView(
            id=row.id,
            identity_kind=row.identity_kind,
            display_name=row.display_name,
            grants=[
                GrantView(product_key=g.product_key, role=g.role.value)
                for g in list_grants_for_user(connection, app_user_id=row.id)
            ],
        )
        for row in rows
    ]


@router.put("/users/{target_user_id}/grants/{product_key}", response_model=list[GrantView])
def set_grant(
    target_user_id: int,
    product_key: str,
    payload: SetGrantRequest,
    user: Annotated[AppUser, Depends(get_current_app_user)],
    connection: Annotated[Connection, Depends(get_db_connection)],
) -> list[GrantView]:
    """Set or revoke one user's role for one product. Admin-only, per product."""

    if product_key not in PRODUCT_KEYS:
        raise HTTPException(status_code=422, detail="Unknown product_key.")

    ensure_can(
        connection, app_user_id=user.id, product_key=product_key, action=Action.MANAGE_ACCESS
    )

    if payload.role is None:
        connection.execute(
            text(
                "DELETE FROM platform.product_grant "
                "WHERE app_user_id = :app_user_id AND product_key = :product_key"
            ),
            {"app_user_id": target_user_id, "product_key": product_key},
        )
        event_type = "grant.revoked"
    else:
        grant_product_role(
            connection,
            app_user_id=target_user_id,
            product_key=product_key,
            role=payload.role,
        )
        event_type = "grant.set"

    record_audit_event(
        connection,
        actor_app_user_id=user.id,
        event_type=event_type,
        product_key=product_key,
        subject_kind="app_user",
        subject_id=str(target_user_id),
        metadata={"role": payload.role.value if payload.role else None},
    )

    return [
        GrantView(product_key=g.product_key, role=g.role.value)
        for g in list_grants_for_user(connection, app_user_id=target_user_id)
    ]
```

- [ ] **Step 4: Mount the router**

```python
# apps/api/app/main.py

from app.routers.access_admin import router as access_admin_router

...
app.include_router(access_admin_router)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest apps/api/integration_tests/test_access_admin_router.py -v`
Expected: PASS

- [ ] **Step 6: Add the portal API client functions**

```typescript
// apps/portal/src/lib/platformApi.ts (append)

export interface GrantView {
  product_key: ProductKey
  role: Role
}

export interface UserWithGrantsView {
  id: number
  identity_kind: string
  display_name: string
  grants: GrantView[]
}

export function listUsersWithGrants(): Promise<ApiResult<UserWithGrantsView[]>> {
  return request<UserWithGrantsView[]>('/api/access/users')
}

export function setGrant(
  userId: number,
  productKey: ProductKey,
  role: Role | null,
): Promise<ApiResult<GrantView[]>> {
  return request<GrantView[]>(`/api/access/users/${userId}/grants/${productKey}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ role }),
  })
}
```

- [ ] **Step 7: Write the minimal Grants page**

```tsx
// apps/portal/src/pages/Grants.tsx
import { useEffect, useState } from 'react'
import { Link } from '../router/Router'
import { listUsersWithGrants, setGrant, type ProductKey, type Role, type UserWithGrantsView } from '../lib/platformApi'

const PRODUCT_KEYS: ProductKey[] = ['lidar', 'forestry', 'transelect']
const ROLE_OPTIONS: (Role | '')[] = ['', 'viewer', 'operator', 'admin']

export function Grants() {
  const [users, setUsers] = useState<UserWithGrantsView[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    listUsersWithGrants().then((result) => {
      if (result.ok) setUsers(result.data)
      else setError(result.error)
    })
  }, [])

  async function handleChange(userId: number, productKey: ProductKey, role: string) {
    const result = await setGrant(userId, productKey, role === '' ? null : (role as Role))
    if (result.ok) {
      const refreshed = await listUsersWithGrants()
      if (refreshed.ok) setUsers(refreshed.data)
    }
  }

  if (error) {
    return <p>Error: {error}</p>
  }

  return (
    <div className="grants">
      <p><Link to="/archivos">← Archivos</Link></p>
      <h1>Gestión de accesos</h1>
      {!users ? (
        <p>Cargando…</p>
      ) : (
        <table>
          <thead>
            <tr><th>Usuario</th>{PRODUCT_KEYS.map((k) => <th key={k}>{k}</th>)}</tr>
          </thead>
          <tbody>
            {users.map((u) => (
              <tr key={u.id}>
                <td>{u.display_name}</td>
                {PRODUCT_KEYS.map((productKey) => {
                  const current = u.grants.find((g) => g.product_key === productKey)?.role ?? ''
                  return (
                    <td key={productKey}>
                      <select
                        value={current}
                        onChange={(e) => handleChange(u.id, productKey, e.target.value)}
                      >
                        {ROLE_OPTIONS.map((role) => (
                          <option key={role} value={role}>{role || 'sin acceso'}</option>
                        ))}
                      </select>
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}
```

- [ ] **Step 8: Route it**

```tsx
// apps/portal/src/App.tsx — add inside Routes()

if (pathname === '/archivos/grants') {
  return <Grants />
}
```

(Full `/archivos` reorganization, including this being an admin-only-visible
link, happens in Task 10 — this task only needs the route and page to
exist and be independently reachable/testable.)

- [ ] **Step 9: Write a component test**

```tsx
// apps/portal/src/pages/Grants.test.tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { Grants } from './Grants'
import * as platformApi from '../lib/platformApi'

describe('Grants', () => {
  it('renders an error message when the API call fails', async () => {
    vi.spyOn(platformApi, 'listUsersWithGrants').mockResolvedValue({
      ok: false, status: 403, error: 'Admin access required.',
    })
    render(<Grants />)
    expect(await screen.findByText(/Admin access required/)).toBeInTheDocument()
  })
})
```

- [ ] **Step 10: Run the frontend tests**

Run: `cd apps/portal && npm test -- --run`
Expected: PASS

- [ ] **Step 11: Commit**

```bash
git add apps/api/app/routers/access_admin.py apps/api/app/main.py \
        apps/api/integration_tests/test_access_admin_router.py \
        apps/portal/src/pages/Grants.tsx apps/portal/src/pages/Grants.test.tsx \
        apps/portal/src/lib/platformApi.ts apps/portal/src/App.tsx
git commit -m "feat: add admin-only grants management endpoint and portal page"
```

---

### Task 10: `Archivos` navigation — rename, discoverable nav, reorganize

**Files:**
- Create: `apps/portal/src/pages/Archivos.tsx` (superset of current `Ingesta.tsx`)
- Create: `apps/portal/src/pages/Archivos.test.tsx`
- Modify: `apps/portal/src/App.tsx`
- Modify: `apps/portal/src/pages/Home.tsx`
- Delete: `apps/portal/src/pages/Ingesta.tsx`, `apps/portal/src/pages/Ingesta.test.tsx`

**Interfaces:**
- Produces: `/archivos` route with sections `Mis archivos` (renamed job
  list, extended with `original_filename`), `Subir archivo` (unchanged
  upload panel), `Desde OneDrive` (placeholder section — Task 12 fills in
  the real panel; render it only when `me` has an `UPLOAD`-capable grant),
  `Audit` (unchanged, admin-only), plus a link to `/archivos/grants`
  (admin-only, from Task 9). `/ingesta` 301-redirects to `/archivos`.

- [ ] **Step 1: Extend `JobView` to carry the source filename**

The spec asks for "Mis archivos" to read as a file list, using
`source_observation.filename`, which is already captured at upload time.
Check `apps/api/app/routers/ingestion.py`'s `list_jobs` query — it currently
selects only from `processing_job`. Extend the join:

```python
# apps/api/app/routers/ingestion.py — replace list_jobs's query and JobView

class JobView(BaseModel):
    id: int
    product_key: str
    status: str
    attempt_count: int
    created_at: str
    error_summary: str | None
    original_filename: str | None


@router.get("/ingesta/jobs", response_model=list[JobView])
def list_jobs(...) -> list[JobView]:
    ...
    rows = connection.execute(
        text(
            """
            SELECT j.id, j.product_key, j.status, j.attempt_count, j.created_at, j.error_summary,
                   so.filename AS original_filename
            FROM platform.processing_job j
            JOIN platform.ingestion_run r ON r.id = j.ingestion_run_id
            JOIN platform.source_snapshot s ON s.id = r.source_snapshot_id
            LEFT JOIN platform.source_observation so ON so.source_snapshot_id = s.id
            WHERE j.product_key = ANY(:products)
            ORDER BY j.created_at DESC
            LIMIT 200
            """
        ),
        {"products": granted_products},
    ).all()
    return [
        JobView(
            id=row.id, product_key=row.product_key, status=row.status,
            attempt_count=row.attempt_count, created_at=row.created_at.isoformat(),
            error_summary=row.error_summary, original_filename=row.original_filename,
        )
        for row in rows
    ]
```

Note the existing `test_ingestion_router.py` asserts on `JobView`'s shape —
update its expected fields alongside this change.

- [ ] **Step 2: Add a redirect route for `/ingesta`**

```python
# apps/api/app/routers/ingestion.py — add a thin redirect for continuity
# (portal-side redirect, since this repo's router is under /ingesta prefix
# for the API, not the portal path — the portal route redirect is what
# actually matters for "no separate engineering screen remains linked")
```

The API's `/ingesta/*` paths remain the JSON endpoints (unchanged, matches
`platformApi.ts`); only the **portal route** `/ingesta` needs to become an
alias. Implement the redirect in the portal router, not the API:

```tsx
// apps/portal/src/App.tsx

if (pathname === '/ingesta') {
  window.history.replaceState({}, '', '/archivos')
  return <Archivos />
}

if (pathname === '/archivos') {
  return <Archivos />
}
```

- [ ] **Step 3: Write `Archivos.tsx`**

Start from the existing `Ingesta.tsx` (read above) and apply these changes:
rename the component and file, change the two `<h1>Ingesta local (dev)</h1>`
headings to `<h1>Archivos</h1>`, remove the
`Autenticación local de desarrollo` note (real sign-in now exists — the
dev-login button list only renders when `me` is null AND
`import.meta.env.DEV` is true, gated so it never appears against a staging
build), replace the manual dev-login buttons with a real sign-in link, add
`original_filename` as a column in the "Trabajos" table (rename its heading
to "Mis archivos"), and add an admin-only link to `/archivos/grants`:

```tsx
// apps/portal/src/pages/Archivos.tsx (key diffs from Ingesta.tsx; keep
// everything else — polling, upload handling, retry — unchanged)

if (!me) {
  return (
    <div className="archivos">
      <p><Link to="/">← Campo Digital</Link></p>
      <h1>Archivos</h1>
      <p className="archivos__note">
        Inicia sesión con tu cuenta de Campo Digital para ver y subir archivos.
      </p>
      <a href="/api/auth/entra/login" className="archivos__login-button">
        Iniciar sesión con Microsoft
      </a>
    </div>
  )
}

// ... inside the authenticated render, rename "Trabajos" heading:
<h2>Mis archivos</h2>
<table>
  <thead>
    <tr>
      <th>ID</th><th>Archivo</th><th>Producto</th><th>Estado</th>
      <th>Intentos</th><th>Creado</th><th />
    </tr>
  </thead>
  <tbody>
    {jobs.map((job) => (
      <tr key={job.id}>
        <td>{job.id}</td>
        <td>{job.original_filename ?? '—'}</td>
        <td>{job.product_key}</td>
        <td>{job.status}</td>
        <td>{job.attempt_count}</td>
        <td>{job.created_at}</td>
        <td>{/* retry button, unchanged */}</td>
      </tr>
    ))}
  </tbody>
</table>

// admin-only grants link, placed near the logout control:
{isAdmin && <Link to="/archivos/grants">Gestión de accesos</Link>}
```

Also update `JobView`'s TypeScript type in `platformApi.ts` to add
`original_filename: string | null`.

- [ ] **Step 4: Add the Home nav link**

```tsx
// apps/portal/src/pages/Home.tsx — inside <footer className="home__footer">

<Link to="/archivos" className="home__footer-link">
  Archivos
</Link>
```

- [ ] **Step 5: Delete the old page and its test**

```bash
git rm apps/portal/src/pages/Ingesta.tsx apps/portal/src/pages/Ingesta.test.tsx
```

- [ ] **Step 6: Write `Archivos.test.tsx`**

Port the existing assertions from the deleted `Ingesta.test.tsx` (login
gate, upload flow, retry visibility, admin-only audit section — read the
original file for the exact expectations) and add:

```tsx
// apps/portal/src/pages/Archivos.test.tsx (new assertions, appended to the
// ported test bodies)

it('shows a real Microsoft sign-in link when logged out', () => {
  render(<Archivos />)
  expect(screen.getByText(/Iniciar sesión con Microsoft/)).toBeInTheDocument()
})

it('shows the original filename in the Mis archivos table', async () => {
  // ...mock getMe/listJobs to include a job with original_filename set,
  // assert the cell renders it.
})
```

- [ ] **Step 7: Run frontend tests and update `App.test.tsx` if it asserts on `/ingesta`**

Run: `cd apps/portal && npm test -- --run`
Expected: PASS. Check `apps/portal/src/App.test.tsx` for any route
assertion mentioning `/ingesta` and update it to `/archivos`.

- [ ] **Step 8: Commit**

```bash
git add apps/portal/src/pages/Archivos.tsx apps/portal/src/pages/Archivos.test.tsx \
        apps/portal/src/App.tsx apps/portal/src/App.test.tsx apps/portal/src/pages/Home.tsx \
        apps/portal/src/lib/platformApi.ts apps/api/app/routers/ingestion.py \
        apps/api/integration_tests/test_ingestion_router.py
git rm apps/portal/src/pages/Ingesta.tsx apps/portal/src/pages/Ingesta.test.tsx
git commit -m "feat: rename /ingesta to /archivos, make it discoverable, add filenames"
```

---

### Task 11: `ExecutionBackend` interface + staging in-process adapter + ephemeral handling

**Files:**
- Create: `apps/api/app/execution.py`
- Test: `apps/api/tests/test_execution.py`
- Modify: `apps/api/app/worker.py`
- Modify: `apps/api/app/main.py`
- Test: `apps/api/integration_tests/test_worker_end_to_end.py` (extend)

**Interfaces:**
- Consumes: `app.worker.run_one_job` (existing), `Settings.staging_execution_max_bytes` (Task 2).
- Produces: `ExecutionBackend` protocol with `async def start(self) -> None` /
  `async def stop(self) -> None`; `InProcessStagingExecutionBackend`
  implementing it via a background `asyncio.Task` polling loop.

- [ ] **Step 1: Write the failing unit test for the size/product guards**

```python
# apps/api/tests/test_execution.py

from app.execution import job_is_within_staging_limits


def test_job_within_limits_when_small_and_not_lidar() -> None:
    assert job_is_within_staging_limits(
        product_key="forestry",
        byte_size=1024,
        max_bytes=25_000_000,
    ) == (True, None)


def test_job_over_size_cap_is_rejected() -> None:
    within, reason = job_is_within_staging_limits(
        product_key="forestry",
        byte_size=30_000_000,
        max_bytes=25_000_000,
    )
    assert within is False
    assert reason == "exceeds staging execution size limit"


def test_lidar_jobs_are_always_rejected_in_staging() -> None:
    within, reason = job_is_within_staging_limits(
        product_key="lidar",
        byte_size=10,
        max_bytes=25_000_000,
    )
    assert within is False
    assert reason == "not processed in staging"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest apps/api/tests/test_execution.py -v`
Expected: FAIL — `app.execution` does not exist.

- [ ] **Step 3: Implement `app/execution.py`**

```python
# apps/api/app/execution.py
"""Execution backend seam: how a queued job actually gets run.

Not a production execution model — see docs/adr/ADR-001 and ADR-004 for the
still-open production compute decision. This gives Render staging (which
deploys no worker per ADR-005) a way to actually finish jobs, bounded and
explicit about what it will not attempt.
"""

from __future__ import annotations

import asyncio
from typing import Protocol

from sqlalchemy import Engine, text

from app.config import Settings
from app.object_store import ObjectStore
from app.worker import run_one_job

_POLL_INTERVAL_SECONDS = 2.0


def job_is_within_staging_limits(
    *, product_key: str, byte_size: int, max_bytes: int
) -> tuple[bool, str | None]:
    """Return (allowed, rejection_reason). LiDAR is refused outright; others capped."""

    if product_key == "lidar":
        return False, "not processed in staging"
    if byte_size > max_bytes:
        return False, "exceeds staging execution size limit"
    return True, None


class ExecutionBackend(Protocol):
    """Something that keeps queued jobs moving."""

    async def start(self) -> None:
        """Begin processing jobs. Must not block the caller."""

    async def stop(self) -> None:
        """Stop processing jobs, allowing any in-flight attempt to finish."""


class InProcessStagingExecutionBackend:
    """Polls run_one_job on an interval, inside the FastAPI process itself.

    Explicitly not a production pattern: guarded by the caller to
    APP_ENV == "staging" only. Blocking DB/inspection work runs via
    asyncio.to_thread so it never blocks the event loop.
    """

    def __init__(self, engine: Engine, store: ObjectStore, settings: Settings) -> None:
        self._engine = engine
        self._store = store
        self._settings = settings
        self._task: asyncio.Task[None] | None = None
        self._stopping = asyncio.Event()

    async def start(self) -> None:
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        self._stopping.set()
        if self._task is not None:
            await self._task

    async def _loop(self) -> None:
        worker_id = "staging-inprocess"
        while not self._stopping.is_set():
            did_work = await asyncio.to_thread(self._run_one_guarded, worker_id)
            if not did_work:
                try:
                    await asyncio.wait_for(self._stopping.wait(), timeout=_POLL_INTERVAL_SECONDS)
                except TimeoutError:
                    pass

    def _run_one_guarded(self, worker_id: str) -> bool:
        with self._engine.connect() as connection:
            snapshot = connection.execute(
                text(
                    """
                    SELECT j.product_key, s.byte_size
                    FROM platform.processing_job j
                    JOIN platform.ingestion_run r ON r.id = j.ingestion_run_id
                    JOIN platform.source_snapshot s ON s.id = r.source_snapshot_id
                    WHERE j.status = 'queued'
                    ORDER BY j.created_at
                    LIMIT 1
                    """
                )
            ).one_or_none()

            if snapshot is not None:
                allowed, reason = job_is_within_staging_limits(
                    product_key=snapshot.product_key,
                    byte_size=snapshot.byte_size,
                    max_bytes=self._settings.staging_execution_max_bytes,
                )
                if not allowed:
                    connection.execute(
                        text(
                            """
                            UPDATE platform.processing_job
                            SET status = 'failed', error_summary = :reason, finished_at = now()
                            WHERE id = (
                                SELECT id FROM platform.processing_job
                                WHERE status = 'queued' AND product_key = :product_key
                                ORDER BY created_at LIMIT 1
                            )
                            """
                        ),
                        {"reason": reason, "product_key": snapshot.product_key},
                    )
                    connection.commit()
                    return True

            return run_one_job(connection, self._store, worker_id=worker_id)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest apps/api/tests/test_execution.py -v`
Expected: PASS

- [ ] **Step 5: Add ephemeral-object-missing handling to `worker.run_one_job`**

```python
# apps/api/app/worker.py — inside run_one_job, before `with store.open(...)`:

    if not store.exists(claimed.object_storage_key):
        fail_job(
            connection,
            job_id=claimed.id,
            worker_id=worker_id,
            error_summary="source object unavailable (ephemeral storage cycled)",
        )
        connection.commit()
        return True
```

- [ ] **Step 6: Write the integration test for the ephemeral case**

```python
# apps/api/integration_tests/test_worker_end_to_end.py (append)


def test_missing_object_fails_job_with_distinct_summary(connection, tmp_path) -> None:
    # ...enqueue a job whose source_snapshot.object_storage_key does not
    # resolve in a fresh LocalObjectStore(tmp_path) (never call store.put
    # for it), then:
    from app.worker import run_one_job
    from app.object_store import LocalObjectStore

    store = LocalObjectStore(tmp_path)
    did_work = run_one_job(connection, store, worker_id="test-worker")
    assert did_work is True

    row = connection.execute(
        text("SELECT status, error_summary FROM platform.processing_job WHERE id = :id"),
        {"id": job_id},  # from the enqueue step above
    ).one()
    assert row.status == "failed"
    assert row.error_summary == "source object unavailable (ephemeral storage cycled)"
```

- [ ] **Step 7: Wire the backend into `main.py`'s startup, staging-only**

```python
# apps/api/app/main.py — add near the bottom

from app.config import get_settings
from app.database import get_database_engine
from app.deps import get_object_store
from app.execution import ExecutionBackend, InProcessStagingExecutionBackend

_execution_backend: ExecutionBackend | None = None


@app.on_event("startup")
async def _start_staging_execution() -> None:
    global _execution_backend
    if os.environ.get("APP_ENV", "development") != "staging":
        return
    settings = get_settings()
    _execution_backend = InProcessStagingExecutionBackend(
        get_database_engine(), get_object_store(), settings
    )
    await _execution_backend.start()


@app.on_event("shutdown")
async def _stop_staging_execution() -> None:
    if _execution_backend is not None:
        await _execution_backend.stop()
```

- [ ] **Step 8: Run tests**

Run: `uv run pytest apps/api/tests/test_execution.py apps/api/integration_tests/test_worker_end_to_end.py -v`
Expected: PASS

- [ ] **Step 9: Add `STAGING_EXECUTION_MAX_BYTES` to `render.yaml`**

```yaml
# render.yaml — under campo-digital-api-staging's envVars
      - key: STAGING_EXECUTION_MAX_BYTES
        value: "26214400"  # 25 MiB
```

- [ ] **Step 10: Commit**

```bash
git add apps/api/app/execution.py apps/api/tests/test_execution.py apps/api/app/worker.py \
        apps/api/app/main.py apps/api/integration_tests/test_worker_end_to_end.py render.yaml
git commit -m "feat: add staging in-process execution backend and ephemeral-object handling"
```

---

### Task 12: Microsoft Graph client + intersection authorization + `Desde OneDrive` browse/select

**Blocked on:** Task 7's RESULT (real `graph_scope` and per-project
`drive_id`/`site_id`/`root_item_id` in `config/source-catalog.yaml`).

**Files:**
- Create: `apps/api/app/graph_client.py`
- Modify: `apps/api/app/routers/entra_auth.py` (`_required_graph_scope`)
- Create: `apps/api/app/routers/onedrive.py`
- Test: `apps/api/tests/test_graph_client.py`
- Test: `apps/api/integration_tests/test_onedrive_router.py`
- Modify: `apps/api/app/main.py`
- Modify: `config/source-catalog.yaml` loader (wherever it is currently
  read — check `app/source_discovery.py` and any `yaml.safe_load` call
  site for the catalog; add a small typed accessor rather than parsing
  YAML ad hoc in the new router)
- Create: `apps/portal/src/components/OneDrivePanel.tsx` + test
- Modify: `apps/portal/src/pages/Archivos.tsx`
- Modify: `apps/api/app/source_provenance.py` (new `campo_digital_graph` source-system row)

**Interfaces:**
- Consumes: `config/source-catalog.yaml`'s `graph:` block (Task 7),
  `platform.ms_graph_grant` (Task 3), `token_crypto` (this task, new file).
- Produces: `GET /onedrive/browse?product_key=...&item_id=...` (metadata
  only; defaults `item_id` to the product's configured `root_item_id`),
  each returned item annotated with whether it is selectable (i.e. its
  `parentReference` chain was proven to resolve beneath the product's root).

- [ ] **Step 1: Implement token encryption helpers**

```python
# apps/api/app/token_crypto.py
"""Fernet encryption for platform.ms_graph_grant token columns."""

from __future__ import annotations

from cryptography.fernet import Fernet

from app.config import Settings


class TokenEncryptionNotConfiguredError(RuntimeError):
    """Raised when PLATFORM_TOKEN_ENCRYPTION_KEY is required but unset."""


def _fernet(settings: Settings) -> Fernet:
    if settings.platform_token_encryption_key is None:
        raise TokenEncryptionNotConfiguredError("PLATFORM_TOKEN_ENCRYPTION_KEY must be set.")
    return Fernet(settings.platform_token_encryption_key.get_secret_value().encode("utf-8"))


def encrypt_token(settings: Settings, raw_token: str) -> bytes:
    return _fernet(settings).encrypt(raw_token.encode("utf-8"))


def decrypt_token(settings: Settings, encrypted: bytes) -> str:
    return _fernet(settings).decrypt(encrypted).decode("utf-8")
```

- [ ] **Step 2: Fill in `_required_graph_scope` from the catalog**

```python
# apps/api/app/routers/entra_auth.py — replace the placeholder

import yaml
from pathlib import Path

_SOURCE_CATALOG_PATH = Path(__file__).resolve().parents[3] / "config" / "source-catalog.yaml"


def _required_graph_scope(settings: Settings) -> str:
    catalog = yaml.safe_load(_SOURCE_CATALOG_PATH.read_text(encoding="utf-8"))
    scope = catalog.get("graph_scope")
    if not scope:
        raise NotImplementedError(
            "config/source-catalog.yaml has no graph_scope — Task 7's RESULT "
            "must be recorded there before Graph consent is reachable."
        )
    return scope
```

Also add the top-level `graph_scope: "<value from Task 7's RESULT>"` key to
`config/source-catalog.yaml` as part of finishing Task 7 (update Task 7's
Step 2 accordingly if executed after this task is drafted — keep the one
key in one place).

- [ ] **Step 3: Persist the Graph grant after consent**

```python
# apps/api/app/routers/entra_auth.py — add after graph_consent_start


@router.get("/graph-consent/callback")
def graph_consent_callback(
    request: Request,
    user: Annotated[AppUser, Depends(get_current_app_user)],
    connection: Annotated[Connection, Depends(get_db_connection)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> RedirectResponse:
    code = request.query_params.get("code")
    if not code:
        raise HTTPException(status_code=400, detail="Missing authorization code.")

    graph_scope = _required_graph_scope(settings)
    msal_app = build_msal_app(settings)
    result = msal_app.acquire_token_by_authorization_code(
        code,
        scopes=[graph_scope],
        redirect_uri=redirect_uri(settings, path="/auth/entra/graph-consent/callback"),
    )
    if "access_token" not in result:
        raise HTTPException(status_code=401, detail="Graph consent failed.")

    from datetime import UTC, datetime, timedelta
    from app.token_crypto import encrypt_token

    connection.execute(
        text(
            """
            INSERT INTO platform.ms_graph_grant
                (app_user_id, access_token_encrypted, refresh_token_encrypted, scope, expires_at)
            VALUES (:app_user_id, :access_token, :refresh_token, :scope, :expires_at)
            ON CONFLICT (app_user_id) DO UPDATE SET
                access_token_encrypted = EXCLUDED.access_token_encrypted,
                refresh_token_encrypted = EXCLUDED.refresh_token_encrypted,
                scope = EXCLUDED.scope,
                expires_at = EXCLUDED.expires_at,
                granted_at = now()
            """
        ),
        {
            "app_user_id": user.id,
            "access_token": encrypt_token(settings, result["access_token"]),
            "refresh_token": encrypt_token(settings, result.get("refresh_token", "")),
            "scope": graph_scope,
            "expires_at": datetime.now(UTC) + timedelta(seconds=result.get("expires_in", 3600)),
        },
    )
    return RedirectResponse(url="/archivos")
```

(`text` and `AppUser`/`Depends` imports already present at the top of this
router from Task 8 — extend, don't duplicate, the import block.)

- [ ] **Step 4: Implement the Graph client**

```python
# apps/api/app/graph_client.py
"""Thin Microsoft Graph HTTP wrapper: metadata-only calls, delegated tokens only."""

from __future__ import annotations

from dataclasses import dataclass

import httpx

GRAPH_BASE = "https://graph.microsoft.com/v1.0"


class GraphClientError(RuntimeError):
    """Base error for Graph client calls."""


@dataclass(frozen=True, slots=True)
class GraphItem:
    item_id: str
    name: str
    is_folder: bool
    parent_item_id: str | None


class GraphClient:
    """Wraps metadata-only Graph calls using one user's delegated access token."""

    def __init__(self, access_token: str) -> None:
        self._client = httpx.Client(
            base_url=GRAPH_BASE,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=30.0,
        )

    def list_children(self, *, drive_id: str, item_id: str) -> list[GraphItem]:
        response = self._client.get(f"/drives/{drive_id}/items/{item_id}/children")
        if response.status_code != 200:
            raise GraphClientError(f"Graph list_children failed: {response.status_code}")
        return [self._to_item(raw) for raw in response.json().get("value", [])]

    def get_item(self, *, drive_id: str, item_id: str) -> GraphItem:
        response = self._client.get(f"/drives/{drive_id}/items/{item_id}")
        if response.status_code != 200:
            raise GraphClientError(f"Graph get_item failed: {response.status_code}")
        return self._to_item(response.json())

    def resolves_beneath_root(self, *, drive_id: str, item_id: str, root_item_id: str) -> bool:
        """Walk parentReference ancestry; True only if root_item_id is an ancestor."""

        current_id = item_id
        for _ in range(64):  # bounded walk; Graph trees are not infinite
            if current_id == root_item_id:
                return True
            item = self.get_item(drive_id=drive_id, item_id=current_id)
            if item.parent_item_id is None:
                return False
            current_id = item.parent_item_id
        return False

    @staticmethod
    def _to_item(raw: dict) -> GraphItem:
        parent = raw.get("parentReference") or {}
        return GraphItem(
            item_id=raw["id"],
            name=raw["name"],
            is_folder="folder" in raw,
            parent_item_id=parent.get("id"),
        )
```

- [ ] **Step 5: Write the failing unit test for the ancestry check**

```python
# apps/api/tests/test_graph_client.py

from unittest.mock import MagicMock

from app.graph_client import GraphClient, GraphItem


def _client_with_chain(chain: dict[str, GraphItem]) -> GraphClient:
    client = GraphClient(access_token="fake")
    client.get_item = MagicMock(side_effect=lambda *, drive_id, item_id: chain[item_id])
    return client


def test_resolves_beneath_root_true_for_direct_child() -> None:
    chain = {
        "child": GraphItem(item_id="child", name="f.txt", is_folder=False, parent_item_id="root"),
    }
    client = _client_with_chain(chain)
    assert client.resolves_beneath_root(drive_id="d", item_id="child", root_item_id="root") is True


def test_resolves_beneath_root_false_for_unrelated_item() -> None:
    chain = {
        "elsewhere": GraphItem(
            item_id="elsewhere", name="f.txt", is_folder=False, parent_item_id=None
        ),
    }
    client = _client_with_chain(chain)
    assert (
        client.resolves_beneath_root(drive_id="d", item_id="elsewhere", root_item_id="root")
        is False
    )
```

- [ ] **Step 6: Run test to verify it fails, then passes**

Run: `uv run pytest apps/api/tests/test_graph_client.py -v`
Expected: FAIL, then implement Step 4 exactly as written, then PASS.

- [ ] **Step 7: Implement the browse router with the full intersection check**

```python
# apps/api/app/routers/onedrive.py
"""Desde OneDrive: metadata-only browse/select, gated by the intersection of
Microsoft-accessible, configured product source root, and Campo product grant.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import yaml
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import Connection, text

from app.access import Action
from app.access_repository import AppUser
from app.config import Settings, get_settings
from app.deps import ensure_can, get_current_app_user, get_db_connection
from app.graph_client import GraphClient
from app.token_crypto import decrypt_token

router = APIRouter(prefix="/onedrive", tags=["onedrive"])

_SOURCE_CATALOG_PATH = Path(__file__).resolve().parents[3] / "config" / "source-catalog.yaml"


class BrowseItemView(BaseModel):
    item_id: str
    name: str
    is_folder: bool


def _project_graph_config(product_key: str) -> tuple[str, str]:
    catalog = yaml.safe_load(_SOURCE_CATALOG_PATH.read_text(encoding="utf-8"))
    project = catalog["projects"].get(product_key)
    if not project or "graph" not in project:
        raise HTTPException(
            status_code=404, detail="No OneDrive source configured for this product."
        )
    return project["graph"]["drive_id"], project["graph"]["root_item_id"]


def _graph_client_for(
    connection: Connection, settings: Settings, *, app_user_id: int
) -> GraphClient:
    row = connection.execute(
        text("SELECT access_token_encrypted FROM platform.ms_graph_grant WHERE app_user_id = :id"),
        {"id": app_user_id},
    ).one_or_none()
    if row is None:
        raise HTTPException(status_code=403, detail="Graph consent not granted yet.")
    return GraphClient(access_token=decrypt_token(settings, row.access_token_encrypted))


@router.get("/browse", response_model=list[BrowseItemView])
def browse(
    product_key: str,
    user: Annotated[AppUser, Depends(get_current_app_user)],
    connection: Annotated[Connection, Depends(get_db_connection)],
    settings: Annotated[Settings, Depends(get_settings)],
    item_id: str | None = None,
) -> list[BrowseItemView]:
    """List children of item_id (or the product's configured root)."""

    ensure_can(connection, app_user_id=user.id, product_key=product_key, action=Action.VIEW)
    drive_id, root_item_id = _project_graph_config(product_key)
    target_item_id = item_id or root_item_id

    client = _graph_client_for(connection, settings, app_user_id=user.id)

    if item_id is not None and not client.resolves_beneath_root(
        drive_id=drive_id, item_id=item_id, root_item_id=root_item_id
    ):
        raise HTTPException(status_code=403, detail="Item is outside the configured product root.")

    children = client.list_children(drive_id=drive_id, item_id=target_item_id)
    return [BrowseItemView(item_id=c.item_id, name=c.name, is_folder=c.is_folder) for c in children]
```

Note the `ENABLE_ONEDRIVE_IMPORT` flag is not referenced here at all — this
router only ever calls `children`/`get_item` (metadata). The byte-fetch
endpoint the spec describes
(`GET /drives/{id}/items/{id}/content` → `object_store.put` →
`persist_uploaded_source_provenance` → `enqueue_processing_job`) is **out
of scope for this task**; do not add it. When the durable-object-storage
decision is made, that endpoint is added behind
`if not settings.enable_onedrive_import: raise HTTPException(403, ...)` as
its very first line — write that endpoint then, not now.

- [ ] **Step 8: Add the `campo_digital_graph` source-system row**

```python
# apps/api/app/source_provenance.py — add alongside UPLOAD_SYSTEM_KEY

GRAPH_SYSTEM_KEY = "campo_digital_graph"
```

Confirm `_resolve_source_system` (already used by
`persist_uploaded_source_provenance`) creates this row idempotently the
first time it is referenced — no migration needed, `source_system` rows are
created on first use per the existing pattern. Do not call
`persist_uploaded_source_provenance` with this key yet — that only happens
once the byte-fetch endpoint (explicitly out of scope, Step 7's note) is
built.

- [ ] **Step 9: Mount the router and write the integration test**

```python
# apps/api/app/main.py
from app.routers.onedrive import router as onedrive_router

...
app.include_router(onedrive_router)
```

```python
# apps/api/integration_tests/test_onedrive_router.py
"""Browse authorization: Campo grant + Graph consent + root-ancestry, all required."""

from __future__ import annotations

from unittest.mock import MagicMock, patch


def test_browse_requires_upload_view_grant(client, connection) -> None:
    response = client.get("/onedrive/browse?product_key=forestry")
    assert response.status_code in (401, 403)


def test_browse_rejects_item_outside_configured_root(client, connection) -> None:
    with patch("app.routers.onedrive._graph_client_for") as get_client:
        fake_client = MagicMock()
        fake_client.resolves_beneath_root.return_value = False
        get_client.return_value = fake_client
        # ...authenticate as a user with a forestry VIEW grant and a Graph
        # grant row (insert directly via SQL, mirroring test_session_store.py),
        # then:
        response = client.get(
            "/onedrive/browse?product_key=forestry&item_id=some-other-item",
            cookies={"campo_session": "..."},
        )
        assert response.status_code == 403
```

- [ ] **Step 10: Run the tests**

Run: `uv run pytest apps/api/tests/test_graph_client.py apps/api/integration_tests/test_onedrive_router.py -v`
Expected: PASS

- [ ] **Step 11: Add the portal panel**

```tsx
// apps/portal/src/lib/platformApi.ts (append)

export interface BrowseItemView {
  item_id: string
  name: string
  is_folder: boolean
}

export function browseOneDrive(
  productKey: ProductKey,
  itemId?: string,
): Promise<ApiResult<BrowseItemView[]>> {
  const query = itemId ? `?product_key=${productKey}&item_id=${itemId}` : `?product_key=${productKey}`
  return request<BrowseItemView[]>(`/api/onedrive/browse${query}`)
}
```

```tsx
// apps/portal/src/components/OneDrivePanel.tsx
import { useState } from 'react'
import { browseOneDrive, type BrowseItemView, type ProductKey } from '../lib/platformApi'

export function OneDrivePanel({ productKey }: { productKey: ProductKey }) {
  const [items, setItems] = useState<BrowseItemView[] | null>(null)
  const [currentItemId, setCurrentItemId] = useState<string | undefined>(undefined)
  const [error, setError] = useState<string | null>(null)

  async function load(itemId?: string) {
    const result = await browseOneDrive(productKey, itemId)
    if (result.ok) {
      setItems(result.data)
      setCurrentItemId(itemId)
      setError(null)
    } else {
      setError(result.error)
    }
  }

  return (
    <section className="onedrive-panel">
      <h2>Desde OneDrive</h2>
      {!items && !error && (
        <button type="button" onClick={() => load()}>
          Conectar con OneDrive
        </button>
      )}
      {error && <p className="onedrive-panel__error">{error}</p>}
      {items && (
        <ul>
          {items.map((item) => (
            <li key={item.item_id}>
              {item.is_folder ? (
                <button type="button" onClick={() => load(item.item_id)}>{item.name}/</button>
              ) : (
                <span>{item.name}</span>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
```

`error` renders the raw API error, which includes the 403 the backend
returns when Graph consent is not yet granted — clicking "Conectar con
OneDrive" the first time is exactly the incremental-consent trigger point;
wire the button to redirect to `/api/auth/entra/graph-consent/start` when
the browse call comes back 403 specifically for that reason
(distinguish it from the root-ancestry 403 by checking `result.error`'s
text, or — cleaner — have the backend return a distinct
`{"detail": "graph_consent_required"}` machine-readable body for that one
case; if changed, update Step 7 and the test in Step 9 accordingly).

- [ ] **Step 12: Wire it into `Archivos.tsx`, upload-capable users only**

```tsx
// apps/portal/src/pages/Archivos.tsx — inside the authenticated render

{canUpload(uploadRole) && <OneDrivePanel productKey={selectedProduct} />}
```

- [ ] **Step 13: Run the full test suites**

Run: `uv run pytest apps/api -v && cd apps/portal && npm test -- --run`
Expected: PASS

- [ ] **Step 14: Commit**

```bash
git add apps/api/app/graph_client.py apps/api/app/token_crypto.py \
        apps/api/app/routers/onedrive.py apps/api/app/routers/entra_auth.py \
        apps/api/app/source_provenance.py apps/api/app/main.py \
        apps/api/tests/test_graph_client.py apps/api/integration_tests/test_onedrive_router.py \
        apps/portal/src/lib/platformApi.ts apps/portal/src/components/OneDrivePanel.tsx \
        apps/portal/src/pages/Archivos.tsx
git commit -m "feat: add metadata-only OneDrive browse with root-ancestry authorization"
```

---

### Task 13: Deploy and verify on Render staging

**Files:**
- Modify: `render.yaml`

**Interfaces:** none new — this is a verification task.

- [ ] **Step 1: Add the new env vars to `render.yaml`**

```yaml
# render.yaml — campo-digital-api-staging envVars (append)
      - key: ENTRA_TENANT_ID
        sync: false   # set manually in the Render Dashboard, never committed
      - key: ENTRA_CLIENT_ID
        sync: false
      - key: ENTRA_CLIENT_SECRET
        sync: false
      - key: ENTRA_REDIRECT_BASE_URL
        value: https://campo-digital-api-staging.onrender.com
      - key: PLATFORM_TOKEN_ENCRYPTION_KEY
        sync: false   # generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
      - key: PLATFORM_BOOTSTRAP_ADMIN_TENANT_ID
        sync: false
      - key: PLATFORM_BOOTSTRAP_ADMIN_OBJECT_ID
        sync: false
      - key: ENABLE_ONEDRIVE_IMPORT
        value: "false"
```

Also add `msal`/`cryptography` awareness to the buildCommand comment if the
`--extra api` set changes — confirm `uv sync --extra api --extra transelec
--no-dev --frozen` picks them up automatically since they were added to the
`api` extra in Task 2 (no `render.yaml` command change should be needed).

- [ ] **Step 2: Validate the blueprint**

Run: `render blueprints validate render.yaml` (per ADR-005's noted
constraint, this requires the target branch to exist on the remote —
push the branch first if not already pushed).

- [ ] **Step 3: Set the manual (sync: false) env vars in the Render Dashboard**

Enter the real `ENTRA_TENANT_ID`/`ENTRA_CLIENT_ID`/`ENTRA_CLIENT_SECRET`
(from the EXTERNAL GATE after Task 1), a freshly generated
`PLATFORM_TOKEN_ENCRYPTION_KEY`, and the bootstrap admin's own
`(tenant_id, object_id)` so the first real deploy has exactly one admin.

- [ ] **Step 4: Deploy and confirm dev-auth is unreachable**

```bash
curl -i https://campo-digital-api-staging.onrender.com/auth/dev-login
```

Expected: `404` (route not mounted — Task 4 restricted this to
`APP_ENV == "development"`, and `render.yaml` sets `APP_ENV=staging`).

- [ ] **Step 5: Exercise real Entra login end to end**

Visit `https://campo-digital-portal-staging.onrender.com/archivos`, click
"Iniciar sesión con Microsoft", complete a real sign-in as the configured
bootstrap admin. Confirm `/auth/entra/callback` sets the session cookie and
`GET /api/auth/entra/... ` — actually confirm via the portal UI that "Mis
archivos" renders with the bootstrap admin's grants across all three
products (from Task 5's bootstrap logic).

- [ ] **Step 6: Exercise OneDrive browse end to end, with import still off**

As the bootstrap admin (an `UPLOAD`-capable grant on at least one product),
click "Conectar con OneDrive" in the portal, complete the incremental Graph
consent, and confirm the browse panel lists real folder/file names from
`00 Hub Digital CampoDigital` (or its resolved drive/site per Task 7's
RESULT). Confirm no upload/import button exists yet — selecting a file
does nothing beyond in-browser state (Task 12 explicitly does not implement
the byte-fetch endpoint).

- [ ] **Step 7: Confirm staging execution processes a small non-LiDAR job**

Upload a small (<25 MB) `forestry` file via "Subir archivo"; confirm its
job transitions from `queued` to `succeeded` within ~2–4 seconds (the
`InProcessStagingExecutionBackend` poll interval) without a manually
started worker process — this is the first time Render staging has ever
completed a queued job (ADR-005 recorded that no jobs completed there
before this slice).

- [ ] **Step 8: Record the deploy verification as a journal-style note**

Per `docs/DOCUMENTATION_POLICY.md`'s workflow, append a short RESULT to
`docs/adr/ADR-005-render-staging-experiment.md`'s Consequences section (or
a new small ADR if this changes a prior decision) noting: dev-auth is now
unreachable in staging, real Entra login and OneDrive browse were verified
end-to-end on `<date>`, and staging now completes small non-LiDAR jobs via
the in-process execution backend. Do not commit this until the manual
verification in Steps 4–7 has actually been performed against the real
deployment.

- [ ] **Step 9: Commit**

```bash
git add render.yaml docs/adr/ADR-005-render-staging-experiment.md
git commit -m "chore: configure Render staging for Entra sign-in and staging execution"
```
