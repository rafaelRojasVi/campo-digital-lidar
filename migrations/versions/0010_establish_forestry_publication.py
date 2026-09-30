"""Establish Forestry (Rodales) upload records and the explicit publication marker.

Revision ID: 0010
Revises: 0009

Until this revision the Rodales dashboard showed the *latest ingested*
snapshot, so any new snapshot would have become visible the moment it was
written. Uploading from the dashboard needs the opposite: an uploaded
snapshot stays pending review until someone deliberately publishes it.

Expand-only:

- ``forestry.publication_state``: a singleton row (``CHECK (id = 1)``) naming
  the snapshot the dashboard serves. NULL means nothing is published.
- ``forestry.publication_event``: one append-only row per activation.
  ``publish`` (a pending snapshot made visible), ``restore`` (a previously
  published snapshot made visible again) and ``initial`` (a snapshot that
  was already visible before this workflow existed, or was put there by the
  controlled CLI import). ``publish``/``restore`` always name the signed-in
  actor; ``initial`` never has one.
- ``forestry.snapshot_upload``: one row per accepted dashboard upload (who,
  when, the original filename, size and SHA-256 of the ZIP, and its
  platform source snapshot, whose ``object_storage_key`` points at the
  stored ZIP). Uploading identical content twice records two uploads of one
  snapshot.

Backfill: if a Forestry snapshot already exists (the hosted Degenfeld import
of Rodales hosted release V1), the most recently ingested one becomes the
published snapshot with an ``initial`` event. That is exactly the snapshot
the previous release was showing, so deploying this revision changes
nothing any viewer sees.

Nothing existing is altered, so the previous application revision keeps
working against this schema.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the upload, publication-state and publication-event tables."""

    op.create_table(
        "snapshot_upload",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("shapefile_snapshot_id", sa.BigInteger(), nullable=False),
        sa.Column("source_snapshot_id", sa.BigInteger(), nullable=False),
        sa.Column("uploaded_by_app_user_id", sa.BigInteger(), nullable=False),
        sa.Column("original_filename", sa.Text(), nullable=False),
        sa.Column("byte_size", sa.BigInteger(), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column(
            "uploaded_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "content_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_snapshot_upload_content_sha256",
        ),
        sa.CheckConstraint("byte_size > 0", name="ck_snapshot_upload_byte_size_positive"),
        sa.CheckConstraint(
            "btrim(original_filename) <> ''",
            name="ck_snapshot_upload_original_filename_nonempty",
        ),
        sa.ForeignKeyConstraint(
            ["shapefile_snapshot_id"],
            ["forestry.shapefile_snapshot.id"],
            name="fk_snapshot_upload_shapefile_snapshot_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_snapshot_id"],
            ["platform.source_snapshot.id"],
            name="fk_snapshot_upload_source_snapshot_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["uploaded_by_app_user_id"],
            ["platform.app_user.id"],
            name="fk_snapshot_upload_uploaded_by_app_user_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_snapshot_upload"),
        schema="forestry",
    )
    op.create_index(
        "ix_snapshot_upload_shapefile_snapshot_id",
        "snapshot_upload",
        ["shapefile_snapshot_id"],
        schema="forestry",
    )

    op.create_table(
        "publication_state",
        sa.Column("id", sa.SmallInteger(), nullable=False),
        sa.Column("published_snapshot_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint("id = 1", name="ck_publication_state_singleton"),
        sa.ForeignKeyConstraint(
            ["published_snapshot_id"],
            ["forestry.shapefile_snapshot.id"],
            name="fk_publication_state_published_snapshot_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_publication_state"),
        schema="forestry",
    )

    op.create_table(
        "publication_event",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("shapefile_snapshot_id", sa.BigInteger(), nullable=False),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("previous_snapshot_id", sa.BigInteger(), nullable=True),
        sa.Column("actor_app_user_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "event_type IN ('initial', 'publish', 'restore')",
            name="ck_publication_event_event_type",
        ),
        sa.CheckConstraint(
            "(event_type = 'initial') = (actor_app_user_id IS NULL)",
            name="ck_publication_event_actor_matches_type",
        ),
        sa.ForeignKeyConstraint(
            ["shapefile_snapshot_id"],
            ["forestry.shapefile_snapshot.id"],
            name="fk_publication_event_shapefile_snapshot_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["previous_snapshot_id"],
            ["forestry.shapefile_snapshot.id"],
            name="fk_publication_event_previous_snapshot_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["actor_app_user_id"],
            ["platform.app_user.id"],
            name="fk_publication_event_actor_app_user_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_publication_event"),
        schema="forestry",
    )
    op.create_index(
        "ix_publication_event_shapefile_snapshot_id",
        "publication_event",
        ["shapefile_snapshot_id"],
        schema="forestry",
    )

    # Seed the singleton, then carry over what the previous release showed:
    # the latest ingested snapshot, if there is one.
    op.execute(
        """
        INSERT INTO forestry.publication_state (id, published_snapshot_id)
        VALUES (1, (SELECT max(id) FROM forestry.shapefile_snapshot))
        """
    )
    op.execute(
        """
        INSERT INTO forestry.publication_event (shapefile_snapshot_id, event_type)
        SELECT published_snapshot_id, 'initial'
        FROM forestry.publication_state
        WHERE id = 1 AND published_snapshot_id IS NOT NULL
        """
    )


def downgrade() -> None:
    """Drop the publication and upload tables (snapshots are untouched)."""

    op.drop_table("publication_event", schema="forestry")
    op.drop_table("publication_state", schema="forestry")
    op.drop_table("snapshot_upload", schema="forestry")
