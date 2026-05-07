"""Octavius — FastAPI backend for the standalone frontend."""

from __future__ import annotations

import logging
import os
import sys

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

logger = logging.getLogger(__name__)

# Import dispatcher at module load time so the parquet is read and all rules
# are compiled before the first request.  A missing or unreadable parquet is a
# hard failure — we prefer an explicit crash over silently serving no results.
try:
    import logic.dispatcher as _dispatcher
except Exception as exc:  # noqa: BLE001
    logger.critical("Failed to load rulebook — aborting boot: %s", exc)
    sys.exit(1)

from routes.check import router as check_router
from routes.rules import router as rules_router

app = FastAPI(title="Octavius", version="0.2.0")

# Register debug endpoints only when explicitly opted in.
if os.environ.get("OCTAVIUS_DEBUG_ENDPOINTS") == "1":
    from routes.debug import router as debug_router
    app.include_router(debug_router)
    logger.info("Debug endpoints enabled (OCTAVIUS_DEBUG_ENDPOINTS=1)")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(check_router)
app.include_router(rules_router)


# ---------------------------------------------------------------------------
# Frontend serving
# ---------------------------------------------------------------------------
# The Tiptap-based React frontend is built to ``frontend/build/`` (committed
# to git so Render does not need a Node toolchain at deploy time). When that
# build exists, mount its hashed assets at ``/static`` and serve its
# ``index.html`` at ``/``. Otherwise fall back to the legacy hand-written
# ``index.html`` at the repo root.
_FRONTEND_BUILD = Path(__file__).parent / "frontend" / "build"
_FRONTEND_INDEX = _FRONTEND_BUILD / "index.html"
_FRONTEND_STATIC = _FRONTEND_BUILD / "static"

if _FRONTEND_STATIC.is_dir():
    app.mount("/static", StaticFiles(directory=str(_FRONTEND_STATIC)), name="static")


@app.get("/")
def serve_frontend() -> FileResponse:
    if _FRONTEND_INDEX.is_file():
        return FileResponse(str(_FRONTEND_INDEX), media_type="text/html")
    return FileResponse("index.html", media_type="text/html")


# ---------------------------------------------------------------------------
# Legacy /groups alias — keeps the unmodified index.html working until S3.
# Returns taxonomy id + name + rule_count, which is the shape index.html
# currently consumes.
# ---------------------------------------------------------------------------

@app.get("/groups")
def get_groups() -> list[dict]:
    from collections import Counter
    counts: Counter[str] = Counter(r["taxonomy"] for r in _dispatcher.get_rules())
    return [
        {"id": tax, "name": tax.capitalize(), "rule_count": counts[tax]}
        for tax in sorted(counts)
    ]
