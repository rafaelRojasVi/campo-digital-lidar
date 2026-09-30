"""Serve the built frontends from the same-origin FastAPI service.

A production container packages one FastAPI process together with the
Campo Digital front door (``apps/portal``, served at ``/``) and each hosted
product's React build under its own first path segment (Transelec at
``/transelec/``, Rodales at ``/rodales/``), so there is no separate frontend
origin and no CORS surface to secure (see
``docs/superpowers/specs/2026-09-28-unified-platform-design.md`` and the
Dockerfile at the repo root). Local development is unaffected: every
frontend normally runs via its own Vite dev server, and this module is a no-op
whenever no built ``dist/`` directory is present, which is always true in
local dev and in CI/test, since ``dist/`` is gitignored and only produced by
``npm run build``.
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

_REPO_ROOT = Path(__file__).resolve().parents[3]

PORTAL_DIST_ENV = "CAMPO_PORTAL_DIST"
TRANSELEC_DIST_ENV = "CAMPO_TRANSELEC_DASHBOARD_DIST"
RODALES_DIST_ENV = "CAMPO_RODALES_DASHBOARD_DIST"
DEFAULT_PORTAL_DIST = _REPO_ROOT / "apps" / "portal" / "dist"
DEFAULT_TRANSELEC_DIST = _REPO_ROOT / "products" / "transelect" / "dashboard" / "dist"
DEFAULT_RODALES_DIST = _REPO_ROOT / "products" / "forestry" / "dashboard" / "dist"


def dist_dir_from_environment(env_var: str, default: Path) -> Path | None:
    """The configured build directory, or None when no build is present."""

    configured = os.environ.get(env_var, "").strip()
    candidate = Path(configured) if configured else default
    return candidate if (candidate / "index.html").is_file() else None


def _resolve_within(dist_dir: Path, relative_path: str) -> Path | None:
    """Resolves ``relative_path`` under ``dist_dir``, rejecting escapes."""

    candidate = (dist_dir / relative_path).resolve()

    if candidate != dist_dir and dist_dir not in candidate.parents:
        return None

    return candidate


@dataclass(frozen=True)
class PrefixedDashboard:
    """A product build served under its own first path segment.

    ``page_paths`` lists the frontend's own page paths (no leading slash,
    e.g. ``"transelec/pendientes"``). They share the segment with the API
    routes, so only these exact paths get the shell; anything else under the
    segment is either a build file or a 404, never ``index.html``.
    """

    segment: str
    dist_dir: Path
    page_paths: frozenset[str]


def mount_dashboards(
    app: FastAPI,
    *,
    root_dist: Path | None,
    prefixed: Sequence[PrefixedDashboard],
    reserved_root_segments: frozenset[str],
) -> None:
    """Serve the portal at ``/`` and each product build under its segment.

    ``reserved_root_segments`` must list the first path segment of every
    other route namespace on ``app`` (``api``, ``health``...), so an unmatched
    API path answers 404 instead of the portal. Must be called after every
    other router is registered, because it adds a catch-all route. A no-op
    when no build is present.
    """

    if root_dist is None and not prefixed:
        return

    for site in prefixed:
        if (site.dist_dir / "assets").is_dir():
            app.mount(
                f"/{site.segment}/assets",
                StaticFiles(directory=site.dist_dir / "assets"),
                name=f"{site.segment}-assets",
            )
    if root_dist is not None and (root_dist / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=root_dist / "assets"), name="portal-assets")

    by_segment = {site.segment: site for site in prefixed}

    @app.get("/{full_path:path}", include_in_schema=False)
    def serve_dashboard(full_path: str) -> FileResponse:
        """SPA fallback: a build file if it exists, else the owning shell."""

        first_segment = full_path.split("/", 1)[0]
        site = by_segment.get(first_segment)

        if site is not None:
            # Vite's base makes "/transelec/" the canonical entry; accept both.
            if full_path.rstrip("/") in site.page_paths:
                return FileResponse(site.dist_dir / "index.html")
            inner = full_path[len(first_segment) + 1 :]
            candidate = _resolve_within(site.dist_dir, inner) if inner else None
            if candidate is not None and candidate.is_file():
                return FileResponse(candidate)
            raise HTTPException(status_code=404)

        if first_segment in reserved_root_segments or root_dist is None:
            raise HTTPException(status_code=404)

        if not full_path:
            return FileResponse(root_dist / "index.html")

        candidate = _resolve_within(root_dist, full_path)
        if candidate is None:
            raise HTTPException(status_code=404)
        if candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(root_dist / "index.html")
