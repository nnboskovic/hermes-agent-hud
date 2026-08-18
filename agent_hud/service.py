"""Snapshot publisher service for Hermes Agent HUD."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from .collector import collect_snapshot

DEFAULT_INTERVAL_SECONDS = 1.0


def default_hermes_home() -> Path:
    configured = os.environ.get("HERMES_HOME", "").strip()
    return Path(configured).expanduser() if configured else Path.home() / ".hermes"


def default_output_path() -> Path:
    cache = os.environ.get("XDG_CACHE_HOME", "").strip()
    root = Path(cache).expanduser() if cache else Path.home() / ".cache"
    return root / "hermes-agent-hud" / "state.json"


def write_snapshot_atomic(path: Path, snapshot: dict[str, Any]) -> None:
    """Replace a private JSON snapshot without exposing partial writes."""
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    temporary = Path(temporary_name)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(snapshot, handle, ensure_ascii=False, separators=(",", ":"))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        path.chmod(0o600)
    except Exception:
        try:
            os.close(fd)
        except OSError:
            pass
        try:
            temporary.unlink()
        except OSError:
            pass
        raise


def publish_once(home: Path, output: Path, *, now: float | None = None) -> dict[str, Any]:
    snapshot = collect_snapshot(home, now=now)
    write_snapshot_atomic(output, snapshot)
    return snapshot


def run_service(home: Path, output: Path, *, interval: float = DEFAULT_INTERVAL_SECONDS) -> None:
    delay = max(0.25, float(interval))
    while True:
        started = time.monotonic()
        try:
            publish_once(home, output)
        except Exception as exc:
            print(f"agent-hud collector error: {type(exc).__name__}: {exc}", flush=True)
        remaining = delay - (time.monotonic() - started)
        if remaining > 0:
            time.sleep(remaining)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Publish sanitized Hermes Agent HUD state")
    parser.add_argument("--home", type=Path, default=default_hermes_home())
    parser.add_argument("--output", type=Path, default=default_output_path())
    parser.add_argument("--interval", type=float, default=DEFAULT_INTERVAL_SECONDS)
    parser.add_argument("--once", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.once:
        publish_once(args.home.expanduser(), args.output.expanduser())
        return 0
    try:
        run_service(args.home.expanduser(), args.output.expanduser(), interval=args.interval)
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
