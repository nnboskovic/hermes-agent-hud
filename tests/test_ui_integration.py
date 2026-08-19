from __future__ import annotations

import json
import os
import stat
import subprocess
import tempfile
import time
import unittest
from pathlib import Path


class HudIntegrationTests(unittest.TestCase):
    LAUNCH_TIMEOUT_SECONDS = 10

    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(__file__).resolve().parents[1]
        cls.display = f":{200 + os.getpid() % 500}"
        cls.xenv = {**os.environ, "DISPLAY": cls.display}
        cls.xvfb = subprocess.Popen(
            ["Xvfb", cls.display, "-screen", "0", "1280x800x24", "-nolisten", "tcp"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        for _ in range(50):
            if cls.xvfb.poll() is not None:
                raise RuntimeError("Xvfb exited before becoming ready")
            ready = subprocess.run(
                ["xdpyinfo"],
                env=cls.xenv,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
            if ready.returncode == 0:
                return
            time.sleep(0.05)
        raise RuntimeError("Xvfb did not become ready")

    @classmethod
    def tearDownClass(cls) -> None:
        cls.xvfb.terminate()
        try:
            cls.xvfb.wait(timeout=3)
        except subprocess.TimeoutExpired:
            cls.xvfb.kill()
            cls.xvfb.wait(timeout=3)

    def _launch(self, suffix: str, position_path: Path) -> tuple[subprocess.Popen[str], str, str]:
        application_id = f"com.hermes.AgentHudTest{os.getpid()}{suffix}"
        env = {
            **self.xenv,
            "HERMES_AGENT_HUD_STATE": str(self.root / "tests" / "demo_state.json"),
            "HERMES_AGENT_HUD_APP_ID": application_id,
            "HERMES_AGENT_HUD_POSITION": str(position_path),
            "HERMES_AGENT_HUD_DISABLE_TRAY": "1",
        }
        process = subprocess.Popen(
            ["gjs", "-m", "hud.js"],
            cwd=self.root,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
        window = ""
        deadline = time.monotonic() + self.LAUNCH_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            if process.poll() is not None:
                _, stderr = process.communicate()
                self.fail(
                    f"HUD exited before creating a window (status {process.returncode}): "
                    f"{(stderr or '')[-2000:]}"
                )
            found = subprocess.run(
                ["xdotool", "search", "--pid", str(process.pid)],
                env=self.xenv,
                capture_output=True,
                text=True,
                check=False,
            )
            for candidate in found.stdout.splitlines():
                name = subprocess.run(
                    ["xdotool", "getwindowname", candidate],
                    env=self.xenv,
                    capture_output=True,
                    text=True,
                    check=False,
                ).stdout.strip()
                if name == "Hermes Agent HUD":
                    window = candidate
                    break
            if window:
                break
            time.sleep(0.05)
        if not window:
            stderr = self._stop(process)
            self.fail(
                f"HUD window did not appear within {self.LAUNCH_TIMEOUT_SECONDS}s: "
                f"{stderr[-2000:]}"
            )
        time.sleep(0.2)
        return process, window, application_id

    def _action(self, application_id: str, action: str) -> None:
        object_path = "/" + application_id.replace(".", "/")
        subprocess.run(
            [
                "gdbus",
                "call",
                "--session",
                "--dest",
                application_id,
                "--object-path",
                object_path,
                "--method",
                "org.gtk.Actions.Activate",
                action,
                "[]",
                "{}",
            ],
            env=self.xenv,
            check=True,
            capture_output=True,
            text=True,
        )

    def _geometry(self, window: str) -> dict[str, int]:
        output = subprocess.run(
            ["xdotool", "getwindowgeometry", "--shell", window],
            env=self.xenv,
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        return {
            key: int(value)
            for line in output.splitlines()
            if "=" in line
            for key, value in [line.split("=", 1)]
            if key in {"X", "Y", "WIDTH", "HEIGHT"}
        }

    def _map_state(self, window: str) -> str:
        output = subprocess.run(
            ["xwininfo", "-id", window],
            env=self.xenv,
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        return next(line.strip() for line in output.splitlines() if "Map State:" in line)

    @staticmethod
    def _stop(process: subprocess.Popen[str]) -> str:
        process.terminate()
        try:
            _, stderr = process.communicate(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            _, stderr = process.communicate(timeout=3)
        return stderr or ""

    def test_expanded_window_grows_to_show_agent_rows_and_activity(self) -> None:
        with tempfile.TemporaryDirectory() as raw_temp:
            position_path = Path(raw_temp) / "position.json"
            process, window, application_id = self._launch("Overview", position_path)
            try:
                collapsed = self._geometry(window)
                self.assertLessEqual(collapsed["HEIGHT"], 64, collapsed)
                self.assertGreaterEqual(collapsed["WIDTH"], 360, collapsed)
                self.assertLessEqual(collapsed["WIDTH"], 430, collapsed)

                self._action(application_id, "toggle")
                expanded = {}
                for _ in range(40):
                    expanded = self._geometry(window)
                    if (
                        expanded["HEIGHT"] >= 240
                        and expanded["X"] + expanded["WIDTH"] <= 1280
                    ):
                        break
                    time.sleep(0.05)
                self.assertGreaterEqual(expanded["HEIGHT"], 240, expanded)
                self.assertLessEqual(expanded["X"] + expanded["WIDTH"], 1280, expanded)

                subprocess.run(
                    ["xdotool", "mousemove", "--window", window, "120", "125", "click", "1"],
                    env=self.xenv,
                    check=True,
                )
                activity = {}
                for _ in range(40):
                    activity = self._geometry(window)
                    if (
                        activity["WIDTH"] >= 620
                        and activity["X"] + activity["WIDTH"] <= 1280
                    ):
                        break
                    time.sleep(0.05)
                self.assertGreaterEqual(activity["WIDTH"], 620, activity)
                self.assertLessEqual(activity["X"] + activity["WIDTH"], 1280, activity)
            finally:
                self._stop(process)

    def test_drag_persists_position_and_minimize_restores(self) -> None:
        with tempfile.TemporaryDirectory() as raw_temp:
            position_path = Path(raw_temp) / "position.json"
            process, window, application_id = self._launch("Shell", position_path)
            try:
                before = self._geometry(window)
                subprocess.run(
                    [
                        "xdotool",
                        "mousemove",
                        "--window",
                        window,
                        "100",
                        "20",
                        "mousedown",
                        "1",
                        "mousemove_relative",
                        "--sync",
                        "--",
                        "-120",
                        "90",
                        "mouseup",
                        "1",
                    ],
                    env=self.xenv,
                    check=True,
                )
                time.sleep(0.3)
                after = self._geometry(window)
                self.assertLess(after["X"], before["X"] - 60, (before, after))
                self.assertGreater(after["Y"], before["Y"] + 40, (before, after))
                saved = json.loads(position_path.read_text(encoding="utf-8"))
                self.assertEqual(stat.S_IMODE(position_path.stat().st_mode), 0o600)
                self.assertAlmostEqual(saved["x"], after["X"], delta=3)
                self.assertAlmostEqual(saved["y"], after["Y"], delta=3)

                subprocess.run(
                    [
                        "xdotool",
                        "mousemove",
                        "--window",
                        window,
                        "100",
                        "20",
                        "mousedown",
                        "1",
                        "mousemove_relative",
                        "--sync",
                        "--",
                        "-2000",
                        "-2000",
                        "mouseup",
                        "1",
                    ],
                    env=self.xenv,
                    check=True,
                )
                time.sleep(0.3)
                clamped = self._geometry(window)
                self.assertGreaterEqual(clamped["X"], 0, clamped)
                self.assertGreaterEqual(clamped["Y"], 0, clamped)
                clamped_saved = json.loads(position_path.read_text(encoding="utf-8"))
                self.assertGreaterEqual(clamped_saved["x"], 0)
                self.assertGreaterEqual(clamped_saved["y"], 0)

                self._action(application_id, "minimize")
                time.sleep(0.2)
                self.assertIn("IsUnMapped", self._map_state(window))
                self._action(application_id, "show")
                time.sleep(0.2)
                self.assertIn("IsViewable", self._map_state(window))
                restored = self._geometry(window)
                self.assertAlmostEqual(restored["X"], clamped["X"], delta=3)
                self.assertAlmostEqual(restored["Y"], clamped["Y"], delta=3)
            finally:
                self._stop(process)


if __name__ == "__main__":
    unittest.main()
