# ADR-003 — Migration revision allocation convention

## Status

Accepted.

## Context

`feat/forestry-dashboard-v1` and `feat/transelec-hosted-pilot-v1` were
developed in parallel git worktrees sharing the same repository. Each branch
independently added a migration with `revision = "0003"` and
`down_revision = "0002"`, since `0002` was each branch's own most recent head
at the time. Alembic's migration graph, and this repository's
`scripts/migration_check.py` / `apps/api/app/migration_graph.py`, require
exactly one base and one head. Two independently authored `"0003"` files are
either a hard load-time collision or, if somehow both loaded, two heads —
both invalid.

## Decision

Migration revision ids are a single, globally linear sequence
(`0001`, `0002`, `0003`, ...) shared across every product context, even though
product contexts remain domain-independent. The sequence encodes deployment
ordering only — it must never encode or imply a business dependency between
products.

Before starting a new migration on a feature branch:

1. Run `git log --all --oneline -- migrations/versions/` from a worktree with
   all relevant branches fetched, and inspect `migrations/versions/` on every
   active sibling worktree, to find the current highest allocated revision id.
2. Claim the next integer id for the new migration's `revision` value, and set
   `down_revision` to the highest id found in step 1.
3. When two branches turn out to have allocated the same id in parallel (as
   happened here), the branch integrating second renumbers only its own
   migration's revision header (`revision`, `down_revision`, filename) to the
   next free id after the other branch's migration. The table/column bodies
   of neither migration are rewritten — only the header changes.
4. `apps/api/tests/test_migration_graph.py` enforces, independently of
   Alembic's own graph construction, that revision ids are unique and form a
   single linear chain with exactly one base and one head. A future collision
   fails this test with the names of the exact colliding files.

## Consequences

Product branches remain free to develop schema in isolation; only the
integration branch (or whichever branch merges second) pays the small cost of
renumbering a migration header. No merge revision or multi-head graph is
introduced, so `scripts/migration_check.py`'s single-base/single-head
assumption continues to hold without modification. The regression test in
`apps/api/tests/test_migration_graph.py` makes a future silent collision
fail fast in CI rather than surfacing as a confusing Alembic runtime error.

This ADR was applied immediately to resolve the first real collision:
Forestry's migration kept revision `0003`; Transelec's colliding migration was
renumbered to revision `0004` with `down_revision = "0003"`. Neither
migration's table/column definitions were altered.
