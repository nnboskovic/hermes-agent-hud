"""Hermes Agent HUD plugin registration.

The root plugin intentionally registers no model-facing tools or mutation
surfaces. Its enabled state gates the read-only backend projection; Hermes
Desktop loads the visual half from ``desktop/plugin.js`` separately.
"""

from __future__ import annotations

from typing import Any


def register(_ctx: Any) -> None:
    """Register no model-facing capabilities."""
