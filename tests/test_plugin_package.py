from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path


class PluginPackageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(__file__).resolve().parents[1]

    def test_native_manifest_is_installable_and_read_only(self) -> None:
        manifest = (self.root / "plugin.yaml").read_text(encoding="utf-8")
        self.assertIn("name: agent-hud", manifest)
        self.assertIn("version: 1.0.1", manifest)
        self.assertIn("license: MIT", manifest)
        self.assertNotIn("provides_tools:", manifest)
        self.assertTrue((self.root / "__init__.py").is_file())

    def test_dashboard_manifest_is_backend_only_and_confined(self) -> None:
        manifest = json.loads(
            (self.root / "dashboard" / "manifest.json").read_text(encoding="utf-8")
        )
        self.assertEqual(manifest["name"], "agent-hud")
        self.assertEqual(manifest["api"], "plugin_api.py")
        self.assertTrue(manifest["tab"]["hidden"])
        self.assertEqual(manifest["entry"], "dist/index.js")
        self.assertTrue((self.root / "dashboard" / "dist" / "index.js").is_file())

    def test_backend_api_reuses_bounded_collector(self) -> None:
        api_path = self.root / "dashboard" / "plugin_api.py"
        fastapi = types.ModuleType("fastapi")

        class APIRouter:
            def get(self, _path: str):
                return lambda function: function

        class HTTPException(Exception):
            def __init__(self, *, status_code: int, detail: str) -> None:
                self.status_code = status_code
                self.detail = detail

        class Response:
            def __init__(self) -> None:
                self.headers: dict[str, str] = {}

        fastapi.APIRouter = APIRouter
        fastapi.HTTPException = HTTPException
        fastapi.Response = Response
        previous = sys.modules.get("fastapi")
        sys.modules["fastapi"] = fastapi
        spec = importlib.util.spec_from_file_location("test_agent_hud_plugin_api", api_path)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)
        finally:
            if previous is None:
                sys.modules.pop("fastapi", None)
            else:
                sys.modules["fastapi"] = previous

        with tempfile.TemporaryDirectory() as raw_home:
            home = Path(raw_home)
            (home / "gateway_state.json").write_text(
                json.dumps({"active_agents": 1000, "gateway_state": "running"}),
                encoding="utf-8",
            )
            snapshot = module.build_snapshot(home=home, now=1_800_000_000.0)

        self.assertEqual(snapshot["version"], 3)
        self.assertEqual(snapshot["counts"]["primary"], 1000)
        self.assertLessEqual(len(snapshot["primary"]), 32)
        self.assertEqual(snapshot["delegations"], [])
        json.dumps(snapshot, allow_nan=False)

    def test_backend_drops_standalone_log_paths(self) -> None:
        api_path = self.root / "dashboard" / "plugin_api.py"
        fastapi = types.ModuleType("fastapi")
        fastapi.APIRouter = lambda: types.SimpleNamespace(get=lambda _path: lambda fn: fn)
        fastapi.HTTPException = Exception
        fastapi.Response = object
        previous = sys.modules.get("fastapi")
        sys.modules["fastapi"] = fastapi
        spec = importlib.util.spec_from_file_location("test_agent_hud_projection", api_path)
        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)
        finally:
            if previous is None:
                sys.modules.pop("fastapi", None)
            else:
                sys.modules["fastapi"] = previous
        snapshot = {
            "delegations": [
                {"children": [{"goal": "Safe goal", "log": "/home/private/task-0.log"}]}
            ]
        }
        projected = module._desktop_projection(snapshot)
        self.assertEqual(projected, {"delegations": [{"children": [{"goal": "Safe goal"}]}]})

    def test_backend_failure_is_generic(self) -> None:
        api_path = self.root / "dashboard" / "plugin_api.py"
        text = api_path.read_text(encoding="utf-8")
        self.assertIn("Agent HUD state unavailable", text)
        self.assertNotIn("traceback", text.lower())
        self.assertNotIn("repr(exc)", text)


if __name__ == "__main__":
    unittest.main()
