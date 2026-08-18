"""FastAPI scaffold. Only /health is wired up -- everything else (auth,
DB, job queue, viewer endpoints) is future scope, see docs/architecture.md.
"""

from __future__ import annotations

from fastapi import FastAPI

app = FastAPI(title="Campo Digital LiDAR API", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
