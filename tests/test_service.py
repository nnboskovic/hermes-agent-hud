from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from agent_hud.service import write_snapshot_atomic


class ServiceTests(unittest.TestCase):
    def test_writes_private_snapshot_atomically(self) -> None:
        with tempfile.TemporaryDirectory() as raw_dir:
            directory = Path(raw_dir)
            output = directory / "state.json"
            output.write_text("broken", encoding="utf-8")

            write_snapshot_atomic(output, {"version": 1, "counts": {"total": 3}})

            self.assertEqual(json.loads(output.read_text(encoding="utf-8"))["counts"]["total"], 3)
            self.assertEqual(os.stat(output).st_mode & 0o777, 0o600)
            self.assertEqual(list(directory.glob(".state.json.*.tmp")), [])


if __name__ == "__main__":
    unittest.main()
