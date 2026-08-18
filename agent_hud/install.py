"""Local installer for Hermes Agent HUD."""

from __future__ import annotations

import argparse
import shutil
import subprocess
from collections.abc import Sequence
from pathlib import Path

COLLECTOR_UNIT = "hermes-agent-hud-collector.service"
HUD_UNIT = "hermes-agent-hud.service"


def _safe_unit_path(path: Path) -> str:
    return str(path.resolve())


def _control_escape(character: str) -> str:
    codepoint = ord(character)
    if codepoint <= 0xFF:
        return f"\\x{codepoint:02x}"
    if codepoint <= 0xFFFF:
        return f"\\u{codepoint:04x}"
    return f"\\U{codepoint:08x}"


def _unit_path_value(path: Path) -> str:
    escaped: list[str] = []
    for character in _safe_unit_path(path):
        if character == "%":
            escaped.append("%%")
        elif character in {'"', "'", "\\", "$"} or character.isspace():
            escaped.append(_control_escape(character))
        elif ord(character) == 127:
            escaped.append("\\x7f")
        else:
            escaped.append(character)
    return "".join(escaped)


def _quote_exec_path(path: Path) -> str:
    escaped: list[str] = []
    for character in _safe_unit_path(path):
        codepoint = ord(character)
        if character == "\\":
            escaped.append("\\\\")
        elif character == '"':
            escaped.append('\\"')
        elif character == "%":
            escaped.append("%%")
        elif character == "$":
            escaped.append("$$")
        elif codepoint < 32 or codepoint == 127:
            escaped.append(_control_escape(character))
        else:
            escaped.append(character)
    return f'"{"".join(escaped)}"'


def render_collector_unit(install_root: Path) -> str:
    root = _unit_path_value(install_root)
    return f"""[Unit]
Description=Hermes Agent HUD collector
After=hermes-gateway.service

[Service]
Type=simple
WorkingDirectory={root}
ExecStart=/usr/bin/python3 -m agent_hud.service
Restart=on-failure
RestartSec=2
UMask=0077
Environment=PYTHONDONTWRITEBYTECODE=1
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=default.target
"""


def render_hud_unit(install_root: Path) -> str:
    root = _unit_path_value(install_root)
    hud = _quote_exec_path(install_root / "hud.js")
    return f"""[Unit]
Description=Hermes Agent HUD overlay
After=graphical-session.target hermes-agent-hud-collector.service
Wants=hermes-agent-hud-collector.service
PartOf=graphical-session.target

[Service]
Type=simple
WorkingDirectory={root}
ExecStart=/usr/bin/gjs -m {hud}
Restart=on-failure
RestartSec=2
UMask=0077
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=graphical-session.target
"""


def install_files(source: Path, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    for name in ("hud.js", "ui_model.js"):
        shutil.copy2(source / name, target / name)
    package_target = target / "agent_hud"
    if package_target.exists():
        shutil.rmtree(package_target)
    package_target.mkdir()
    for path in sorted((source / "agent_hud").glob("*.py")):
        shutil.copy2(path, package_target / path.name)
    (target / "hud.js").chmod(0o755)


def _systemctl(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["systemctl", "--user", *args],
        check=check,
        capture_output=True,
        text=True,
        timeout=30,
    )


def install_user(home: Path, source: Path, *, start: bool = True) -> dict[str, Path]:
    install_root = home / ".local" / "share" / "hermes-agent-hud"
    unit_root = home / ".config" / "systemd" / "user"
    unit_root.mkdir(parents=True, exist_ok=True)
    install_files(source, install_root)
    collector_unit = unit_root / COLLECTOR_UNIT
    hud_unit = unit_root / HUD_UNIT
    collector_unit.write_text(render_collector_unit(install_root), encoding="utf-8")
    hud_unit.write_text(render_hud_unit(install_root), encoding="utf-8")
    if start:
        _systemctl("daemon-reload")
        _systemctl("enable", COLLECTOR_UNIT)
        _systemctl("enable", HUD_UNIT)
        _systemctl("restart", COLLECTOR_UNIT)
        _systemctl("restart", HUD_UNIT)
    return {
        "install_root": install_root,
        "collector_unit": collector_unit,
        "hud_unit": hud_unit,
    }


def uninstall_user(home: Path) -> None:
    install_root = home / ".local" / "share" / "hermes-agent-hud"
    unit_root = home / ".config" / "systemd" / "user"
    _systemctl("disable", "--now", HUD_UNIT, check=False)
    _systemctl("disable", "--now", COLLECTOR_UNIT, check=False)
    for path in (unit_root / HUD_UNIT, unit_root / COLLECTOR_UNIT):
        try:
            path.unlink()
        except FileNotFoundError:
            pass
    if install_root.exists():
        shutil.rmtree(install_root)
    _systemctl("daemon-reload", check=False)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Install Hermes Agent HUD for the current user")
    parser.add_argument("--home", type=Path, default=Path.home())
    parser.add_argument("--no-start", action="store_true")
    parser.add_argument("--uninstall", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    home = args.home.expanduser().resolve()
    if args.uninstall:
        uninstall_user(home)
        print("Hermes Agent HUD uninstalled")
        return 0
    source = Path(__file__).resolve().parents[1]
    paths = install_user(home, source, start=not args.no_start)
    print(paths["install_root"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
