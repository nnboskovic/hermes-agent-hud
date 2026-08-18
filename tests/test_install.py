from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent_hud.install import install_files, install_user, render_collector_unit, render_hud_unit


class InstallTests(unittest.TestCase):
    def test_units_bind_collector_and_hud_to_user_session(self) -> None:
        install_root = Path("/home/test/.local/share/hermes-agent-hud")

        collector = render_collector_unit(install_root)
        hud = render_hud_unit(install_root)

        self.assertIn(f"WorkingDirectory={install_root}", collector)
        self.assertIn("ExecStart=/usr/bin/python3 -m agent_hud.service", collector)
        self.assertIn("WantedBy=default.target", collector)
        self.assertIn("After=graphical-session.target hermes-agent-hud-collector.service", hud)
        self.assertIn(f'ExecStart=/usr/bin/gjs -m "{install_root / "hud.js"}"', hud)
        self.assertIn("WantedBy=graphical-session.target", hud)

    def test_units_quote_spaces_and_escape_systemd_specifiers(self) -> None:
        install_root = Path("/tmp/HUD Path/%n/$HOME")

        collector = render_collector_unit(install_root)
        hud = render_hud_unit(install_root)

        self.assertIn(r"WorkingDirectory=/tmp/HUD\x20Path/%%n/\x24HOME", collector)
        self.assertIn(r"WorkingDirectory=/tmp/HUD\x20Path/%%n/\x24HOME", hud)
        self.assertIn(
            'ExecStart=/usr/bin/gjs -m "/tmp/HUD Path/%%n/$$HOME/hud.js"',
            hud,
        )

    def test_install_copies_only_runtime_files(self) -> None:
        source = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as raw_target:
            target = Path(raw_target)

            install_files(source, target)

            self.assertTrue((target / "hud.js").is_file())
            self.assertTrue((target / "ui_model.js").is_file())
            self.assertTrue((target / "agent_hud" / "collector.py").is_file())
            self.assertFalse((target / "tests").exists())

    def test_install_restarts_existing_services_after_copy(self) -> None:
        source = Path(__file__).resolve().parents[1]
        calls: list[tuple[str, ...]] = []

        def record(*args: str, check: bool = True):
            calls.append(args)
            return None

        with tempfile.TemporaryDirectory() as raw_home:
            with patch("agent_hud.install._systemctl", side_effect=record):
                install_user(Path(raw_home), source, start=True)

        self.assertIn(("restart", "hermes-agent-hud-collector.service"), calls)
        self.assertIn(("restart", "hermes-agent-hud.service"), calls)


if __name__ == "__main__":
    unittest.main()
