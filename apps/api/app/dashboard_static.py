"""Serve a built product dashboard from the same-origin FastAPI service.

A production container packages one FastAPI process together with one
product's React production build, so there is no separate frontend origin
and no CORS surface to secure (see ``docs/platform/production-platform-v1.md``
and the Dockerfile at the repo root). Local development is unaffected: every
dashboard normally runs via its own Vite dev server (see e.g.
``products/transelect/dashboard/README.md``), and this module is a no-op
whenever no built ``dist/`` directory is present — which is always true in
local dev and in CI/test, since ``dist/`` is gitignored and only produced by
``npm run build``.
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

DEFAULT_DIST_DIR = (
    Path(__file__).resolve().parents[3] / "products" / "transelect" / "dashboard" / "dist"
)


def _dist_dir_from_environment() -> Path | None:
    configured = os.environ.get("CAMPO_TRANSELEC_DASHBOARD_DIST", "").strip()
    candidate = Path(configured) if configured else DEFAULT_DIST_DIR
    return candidate if (candidate / "index.html").is_file() else None


def _resolve_within(dist_dir: Path, relative_path: str) -> Path | None:
    """Resolves ``relative_path`` under ``dist_dir``, rejecting escapes."""

    candidate = (dist_dir / relative_path).resolve()

    if candidate != dist_dir and dist_dir not in candidate.parents:
        return None

    return candidate


def mount_dashboard(
    app: FastAPI,
    *,
    reserved_root_segments: frozenset[str],
    spa_page_paths: frozenset[str] = frozenset(),
) -> None:
    """Mount the built React dashboard, if present, as the same-origin UI.

    ``reserved_root_segments`` must list the first path segment of every
    other route mounted on ``app`` (e.g. ``{"health", "ready", "transelec",
    "auth", "api"}``) so the SPA catch-all this function adds never swallows
    a path that belongs to another router's namespace and returns its own
    404 instead of silently serving ``index.html`` for it. This function
    must therefore be called last, after every other router is registered.

    ``spa_page_paths`` must list every exact client-side page path the
    frontend's own router owns (e.g. ``{"transelec", "transelec/importar",
    "transelec/versiones"}`` — see ``ROUTES`` in the dashboard's
    ``src/router.tsx``) whose first segment collides with a reserved backend
    prefix. Without this, a hard navigation or browser refresh on one of
    those pages would 404 instead of loading the app, because the API and
    the SPA deliberately share the same first path segment
    (``/transelec/...``) — the reserved-segment check alone cannot tell
    "unmatched API call" apart from "the frontend's own page route". These
    paths are matched before the reserved-segment check, never after.
    """

    dist_dir = _dist_dir_from_environment()

    if dist_dir is None:
        return

    assets_dir = dist_dir / "assets"

    if assets_dir.is_dir():
        app.mount(
            "/assets",
            StaticFiles(directory=assets_dir),
            name="dashboard-assets",
        )

    @app.get("/{full_path:path}", include_in_schema=False)
    def serve_dashboard(full_path: str) -> FileResponse:
        """SPA fallback: serve a build file if it exists, else index.html."""

        if not full_path:
            return FileResponse(dist_dir / "index.html")

        if full_path in spa_page_paths:
            return FileResponse(dist_dir / "index.html")

        first_segment = full_path.split("/", 1)[0]

        if first_segment in reserved_root_segments:
            raise HTTPException(status_code=404)

        candidate = _resolve_within(dist_dir, full_path)

        if candidate is None:
            raise HTTPException(status_code=404)

        if candidate.is_file():
            return FileResponse(candidate)

        return FileResponse(dist_dir / "index.html")
