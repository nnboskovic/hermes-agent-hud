"""Read-only backend API for the Hermes Agent HUD desktop plugin."""

from __future__ import annotations

import asyncio
import importlib.util
import sys
import time
from pathlib import Path
from types import ModuleType
from typing import Any

from fastapi import APIRouter, HTTPException, Response

router = APIRouter()
_PLUGIN_ROOT = Path(__file__).resolve().parents[1]
_COLLECTOR_PATH = _PLUGIN_ROOT / "agent_hud" / "collector.py"
_COLLECTOR_MODULE = "hermes_agent_hud_bounded_collector"


def _load_collector() -> ModuleType:
    existing = sys.modules.get(_COLLECTOR_MODULE)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(_COLLECTOR_MODULE, _COLLECTOR_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Agent HUD collector is unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[_COLLECTOR_MODULE] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(_COLLECTOR_MODULE, None)
        raise
    return module


def _active_hermes_home() -> Path:
    try:
        from hermes_constants import get_hermes_home

        return Path(get_hermes_home())
    except (ImportError, OSError, TypeError, ValueError):
        return Path.home() / ".hermes"


def _desktop_projection(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Remove standalone-only local fields before crossing the REST boundary."""
    for delegation in snapshot.get("delegations", []):
        if not isinstance(delegation, dict):
            continue
        for child in delegation.get("children", []):
            if isinstance(child, dict):
                child.pop("log", None)
    return snapshot


def build_snapshot(*, home: Path | None = None, now: float | None = None) -> dict[str, Any]:
    """Build the collector's bounded projection for one active Hermes home."""
    collector = _load_collector()
    target = Path(home) if home is not None else _active_hermes_home()
    snapshot = collector.collect_snapshot(target, now=time.time() if now is None else now)
    return _desktop_projection(snapshot)


@router.get("/state")
async def state(response: Response) -> dict[str, Any]:
    """Return sanitized agent state; never expose backend exception details."""
    response.headers["Cache-Control"] = "no-store"
    try:
        return await asyncio.to_thread(build_snapshot)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Agent HUD state unavailable") from exc
