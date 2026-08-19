from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from agent_hud.collector import (
    _clip_goal,
    _delegation_directory,
    _log_tool_activity,
    _task_index,
    _task_log_path,
    _terminal_state,
    collect_snapshot,
)


class CollectorTests(unittest.TestCase):
    def test_rejects_symlinked_delegation_manifest(self) -> None:
        now = 1_800_000_000.0
        with tempfile.TemporaryDirectory() as raw_home:
            home = Path(raw_home)
            with closing(sqlite3.connect(home / "state.db")) as conn, conn:
                conn.execute(
                    "CREATE TABLE async_delegations ("
                    "delegation_id TEXT PRIMARY KEY, origin_session TEXT, "
                    "parent_session_id TEXT, state TEXT, dispatched_at REAL, "
                    "completed_at REAL, updated_at REAL, task_json TEXT)"
                )
                conn.execute(
                    "INSERT INTO async_delegations VALUES "
                    "('deleg_escape', 'origin', 'parent', 'running', ?, NULL, ?, ?)",
                    (now - 10, now - 1, json.dumps({"goal": "Safe durable goal"})),
                )
            live = home / "cache" / "delegation" / "live" / "deleg_escape"
            live.mkdir(parents=True)
            outside = home / "outside-manifest.json"
            outside.write_text(
                json.dumps(
                    {
                        "tasks": [
                            {
                                "index": 0,
                                "goal": "PRIVATE OUTSIDE MANIFEST DATA",
                                "status": "running",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            (live / "manifest.json").symlink_to(outside)

            snapshot = collect_snapshot(home, now=now)

        self.assertEqual(snapshot["delegations"], [])
        self.assertNotIn("PRIVATE OUTSIDE", json.dumps(snapshot))

    def test_rejects_path_and_index_aliases(self) -> None:
        self.assertEqual(
            _clip_goal("Review /home/alice/My Project/private.txt now"),
            "Review [path]",
        )
        self.assertEqual(
            _clip_goal("Review '~/My Project/private.txt' now"),
            "Review [path] now",
        )
        self.assertEqual(_task_index(True, 7), 7)
        self.assertEqual(_task_index(3.5, 8), 8)
        self.assertEqual(
            _clip_goal('run --token "opaque value 123" now'),
            "run --token [REDACTED] now",
        )
        self.assertEqual(
            _clip_goal('TOKEN="alpha beta gamma" terminal'),
            "TOKEN=[REDACTED] terminal",
        )
        self.assertEqual(
            _clip_goal("curl -H 'Authorization: Bearer \"opaque value 123\"' endpoint"),
            "curl -H 'authorization: [REDACTED]' endpoint",
        )
        self.assertEqual(
            _clip_goal("authorization=Bearer secretvalue123"),
            "authorization=[REDACTED]",
        )
        fake_secret = "super" + "secret123456"
        json_secret = _clip_goal(f'curl -d {{"token":"{fake_secret}"}}')
        query_secret = _clip_goal(f"curl 'https://example.invalid/?api-key={fake_secret}'")
        self.assertNotIn(fake_secret, json_secret)
        self.assertNotIn(fake_secret, query_secret)
        self.assertIn("[REDACTED]", json_secret)
        self.assertIn("[REDACTED]", query_secret)
        self.assertEqual(
            _clip_goal("needle in /home/alice/My Project"),
            "needle in [path]",
        )
        self.assertEqual(_terminal_state("error", "worker crashed"), "")
        generic = _log_tool_activity(
            '-> custom_tool({"query":"raw prompt material","auth":"Bearer secret"})',
            "12:33",
        )
        self.assertEqual(generic["detail"], "query, auth")
        self.assertNotIn("raw prompt", json.dumps(generic))
        self.assertNotIn("secret", json.dumps(generic))
        malformed = [
            _log_tool_activity("-> write_file({'content':'TOP SECRET FILE BODY'})", "12:34"),
            _log_tool_activity("-> read_file({'content':'RAW FILE BODY'})", "12:34"),
            _log_tool_activity(
                "-> terminal({'workdir':'relative-private',"
                "'env':{'PUBLIC':'sensitive-value'}})",
                "12:34",
            ),
        ]
        self.assertEqual([item["detail"] for item in malformed], ["file", "file", "command"])
        self.assertNotIn("SECRET", json.dumps(malformed))
        self.assertNotIn("RAW FILE BODY", json.dumps(malformed))
        self.assertNotIn("sensitive-value", json.dumps(malformed))
        self.assertEqual(
            _log_tool_activity("-> read_file(relative/private/notes.txt)", "12:34")["detail"],
            "notes.txt",
        )
        self.assertEqual(
            _log_tool_activity(
                "-> patch({'mode':'patch','patch':'*** Begin Patch\\n"
                "*** Update File: /home/private/file.py\\n@@\\n-old\\n+new\\n"
                "*** End Patch'})",
                "12:34",
            )["detail"],
            "file.py · +1 −1",
        )

        with tempfile.TemporaryDirectory() as raw_home:
            home = Path(raw_home)
            live = home / "cache" / "delegation" / "live"
            real = live / "deleg_real"
            real.mkdir(parents=True)
            (real / "task-1.log").write_text("safe", encoding="utf-8")
            (real / "task-0.log").symlink_to(real / "task-1.log")
            (live / "deleg_alias").symlink_to(real, target_is_directory=True)

            self.assertIsNone(_task_log_path(real, 0))
            self.assertIsNone(_delegation_directory(home, "deleg_alias"))

        with tempfile.TemporaryDirectory() as raw_home, tempfile.TemporaryDirectory() as raw_out:
            home = Path(raw_home)
            outside_cache = Path(raw_out) / "cache"
            external = outside_cache / "delegation" / "live" / "deleg_external"
            external.mkdir(parents=True)
            (home / "cache").symlink_to(outside_cache, target_is_directory=True)
            self.assertIsNone(_delegation_directory(home, "deleg_external"))

        structured_search = _log_tool_activity(
            "-> search_files({'pattern':'target symbol','path':'/home/private/project'})",
            "12:35",
        )
        self.assertEqual(structured_search["detail"], "target symbol")

    def test_bounds_gateway_counts_without_fabricating_unbounded_rows(self) -> None:
        now = 1_800_000_000.0
        with tempfile.TemporaryDirectory() as raw_home:
            home = Path(raw_home)
            (home / "gateway_state.json").write_text(
                json.dumps(
                    {
                        "gateway_state": "running-" + "x" * 5_000,
                        "active_agents": 1_000,
                    }
                ),
                encoding="utf-8",
            )
            with closing(sqlite3.connect(home / "state.db")) as conn, conn:
                conn.executescript(
                    """
                    CREATE TABLE sessions (
                        id TEXT PRIMARY KEY, source TEXT, started_at REAL,
                        ended_at REAL, last_activity_at REAL
                    );
                    CREATE TABLE messages (
                        session_id TEXT, role TEXT, tool_name TEXT, timestamp REAL
                    );
                    CREATE TABLE async_delegations (
                        delegation_id TEXT, parent_session_id TEXT, state TEXT,
                        dispatched_at REAL, task_json TEXT
                    );
                    """
                )

            snapshot = collect_snapshot(home, now=now)

        self.assertEqual(snapshot["counts"]["primary"], 1_000)
        self.assertLessEqual(len(snapshot["primary"]), 32)
        self.assertTrue(snapshot["counts"]["primary_truncated"])
        self.assertLessEqual(len(snapshot["gateway"]["state"]), 64)

    def test_collects_fresh_desktop_session_when_gateway_reports_idle(self) -> None:
        now = 1_800_000_000.0
        with tempfile.TemporaryDirectory() as raw_home:
            home = Path(raw_home)
            (home / "gateway_state.json").write_text(
                json.dumps({"gateway_state": "running", "active_agents": 0}),
                encoding="utf-8",
            )
            with closing(sqlite3.connect(home / "state.db")) as conn, conn:
                conn.executescript(
                    """
                    CREATE TABLE sessions (
                        id TEXT PRIMARY KEY, source TEXT, title TEXT,
                        started_at REAL, ended_at REAL, last_activity_at REAL,
                        last_activity_description TEXT, session_key TEXT
                    );
                    CREATE TABLE messages (
                        session_id TEXT, role TEXT, tool_name TEXT, timestamp REAL
                    );
                    CREATE TABLE async_delegations (
                        delegation_id TEXT, parent_session_id TEXT, state TEXT,
                        dispatched_at REAL, task_json TEXT
                    );
                    """
                )
                conn.execute(
                    "INSERT INTO sessions VALUES (?, ?, ?, ?, NULL, ?, ?, ?)",
                    (
                        "desktop-live",
                        "cli",
                        "Desktop task",
                        now - 10_000,
                        now - 9_000,
                        "working",
                        "",
                    ),
                )
                conn.execute(
                    "INSERT INTO messages VALUES (?, 'tool', 'terminal', ?)",
                    ("desktop-live", now - 2),
                )
                conn.execute(
                    "INSERT INTO sessions VALUES (?, ?, ?, ?, NULL, ?, ?, ?)",
                    (
                        "desktop-stale",
                        "cli",
                        "Old Desktop task",
                        now - 10_000,
                        now - 9_000,
                        "",
                        "",
                    ),
                )

            snapshot = collect_snapshot(home, now=now)

        self.assertEqual(snapshot["counts"]["primary"], 1)
        self.assertEqual(snapshot["counts"]["primary_visible"], 1)
        self.assertEqual(snapshot["counts"]["total"], 1)
        self.assertEqual([row["session_id"] for row in snapshot["primary"]], ["desktop-live"])

    def test_nonfinite_real_activity_does_not_create_phantom_agents(self) -> None:
        now = 1_800_000_000.0
        with tempfile.TemporaryDirectory() as raw_home:
            home = Path(raw_home)
            (home / "gateway_state.json").write_text(
                json.dumps({"gateway_state": "running", "active_agents": 0}),
                encoding="utf-8",
            )
            with closing(sqlite3.connect(home / "state.db")) as conn, conn:
                conn.executescript(
                    """
                    CREATE TABLE sessions (
                        id TEXT PRIMARY KEY, source TEXT, started_at,
                        ended_at REAL, last_activity_at
                    );
                    CREATE TABLE messages (
                        session_id TEXT, role TEXT, tool_name TEXT, timestamp
                    );
                    CREATE TABLE async_delegations (
                        delegation_id TEXT, parent_session_id TEXT, state TEXT,
                        dispatched_at REAL, task_json TEXT
                    );
                    """
                )
                conn.execute(
                    "INSERT INTO sessions VALUES (?, 'cli', ?, NULL, ?)",
                    ("infinite-start", float("inf"), now - 9_000),
                )
                conn.execute(
                    "INSERT INTO sessions VALUES (?, 'cli', ?, NULL, ?)",
                    ("infinite-message", now - 10_000, now - 9_000),
                )
                conn.execute(
                    "INSERT INTO messages VALUES (?, 'tool', 'terminal', ?)",
                    ("infinite-message", float("inf")),
                )
                conn.execute(
                    "INSERT INTO sessions VALUES (?, 'cli', ?, NULL, ?)",
                    ("malformed-text", "inf", "NaN"),
                )

            snapshot = collect_snapshot(home, now=now)

        self.assertEqual(snapshot["counts"]["primary"], 0)
        self.assertEqual(snapshot["counts"]["primary_visible"], 0)
        self.assertEqual(snapshot["counts"]["total"], 0)
        self.assertEqual(snapshot["primary"], [])

    def test_malformed_and_nonfinite_timestamps_fail_closed(self) -> None:
        now = 1_800_000_000.0
        with tempfile.TemporaryDirectory() as raw_home:
            home = Path(raw_home)
            (home / "gateway_state.json").write_text(
                json.dumps({"gateway_state": "running", "active_agents": 1}),
                encoding="utf-8",
            )
            live = home / "cache" / "delegation" / "live" / "deleg_bad_time"
            live.mkdir(parents=True)
            (live / "manifest.json").write_text(
                json.dumps(
                    {
                        "tasks": [
                            {"index": 0, "goal": "Timestamp probe", "status": "running"}
                        ]
                    }
                ),
                encoding="utf-8",
            )
            (live / "task-0.log").write_text(
                "12:00:00 tool     | -> read_file(notes.txt)\n",
                encoding="utf-8",
            )
            with closing(sqlite3.connect(home / "state.db")) as conn, conn:
                conn.executescript(
                    """
                    CREATE TABLE sessions (
                        id TEXT PRIMARY KEY, source TEXT, title TEXT,
                        started_at, ended_at, last_activity_at,
                        last_activity_description TEXT, session_key TEXT
                    );
                    CREATE TABLE messages (
                        session_id TEXT, role TEXT, tool_name TEXT, timestamp
                    );
                    CREATE TABLE async_delegations (
                        delegation_id TEXT, parent_session_id TEXT, state TEXT,
                        dispatched_at, task_json TEXT
                    );
                    """
                )
                conn.execute(
                    "INSERT INTO sessions VALUES (?, ?, ?, ?, NULL, ?, ?, ?)",
                    ("s-bad-time", "discord", "Bad time", "NaN", now, "working", "key"),
                )
                conn.execute(
                    "INSERT INTO messages VALUES (?, ?, ?, ?)",
                    ("s-bad-time", "tool", "read_file", "also-bad"),
                )
                conn.execute(
                    "INSERT INTO async_delegations VALUES (?, ?, ?, ?, ?)",
                    (
                        "deleg_bad_time",
                        "s-bad-time",
                        "running",
                        "inf",
                        json.dumps({"goal": "Bad timestamp delegation"}),
                    ),
                )

            snapshot = collect_snapshot(home, now=now)

        json.dumps(snapshot, allow_nan=False)
        self.assertEqual(snapshot["primary"][0]["started_at"], now)
        self.assertEqual(snapshot["primary"][0]["last_activity_at"], now)
        self.assertEqual(snapshot["delegations"][0]["started_at"], 0.0)

    def test_collects_fresh_primary_agent_and_current_tool(self) -> None:
        now = 1_800_000_000.0
        fake_key = "sk-" + "testsecret123456"
        with tempfile.TemporaryDirectory() as raw_home:
            home = Path(raw_home)
            (home / "gateway_state.json").write_text(
                json.dumps(
                    {
                        "gateway_state": "running",
                        "active_agents": 1,
                        "updated_at": "2027-01-15T08:00:00+00:00",
                    }
                ),
                encoding="utf-8",
            )
            with closing(sqlite3.connect(home / "state.db")) as conn, conn:
                conn.executescript(
                    """
                    CREATE TABLE sessions (
                        id TEXT PRIMARY KEY,
                        source TEXT,
                        title TEXT,
                        started_at REAL,
                        ended_at REAL,
                        last_activity_at REAL,
                        last_activity_description TEXT,
                        session_key TEXT,
                        model TEXT,
                        model_config TEXT,
                        api_call_count INTEGER,
                        tool_call_count INTEGER,
                        git_repo_root TEXT,
                        git_branch TEXT
                    );
                    CREATE TABLE messages (
                        id INTEGER PRIMARY KEY,
                        session_id TEXT,
                        role TEXT,
                        content TEXT,
                        tool_calls TEXT,
                        tool_name TEXT,
                        timestamp REAL,
                        active INTEGER
                    );
                    CREATE TABLE async_delegations (
                        delegation_id TEXT PRIMARY KEY,
                        origin_session TEXT,
                        parent_session_id TEXT,
                        state TEXT,
                        dispatched_at REAL,
                        completed_at REAL,
                        updated_at REAL,
                        task_json TEXT
                    );
                    """
                )
                conn.execute(
                    "INSERT INTO sessions VALUES (?, ?, ?, ?, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        "s-active",
                        "/home/private/My Source/discord",
                        "Build Agent HUD in /home/private/My Project/repository now",
                        now - 90,
                        now - 4,
                        "running terminal",
                        "discord:thread:123",
                        "private-model-name",
                        json.dumps(
                            {"reasoning_config": {"enabled": True, "effort": "high"}}
                        ),
                        9,
                        4,
                        "/home/test/Work/hermes-agent-hud",
                        "/home/private/My Branch/name",
                    ),
                )
                conn.execute(
                    "INSERT INTO sessions VALUES "
                    "(?, ?, ?, ?, NULL, ?, ?, ?, NULL, NULL, 0, 0, NULL, NULL)",
                    (
                        "s-stale",
                        "discord",
                        "Old unfinished session",
                        now - 10_000,
                        now - 9_000,
                        "",
                        "discord:thread:old",
                    ),
                )
                conn.execute(
                    "INSERT INTO messages "
                    "(id, session_id, role, content, tool_name, timestamp, active) "
                    "VALUES (1, ?, 'tool', ?, 'terminal', ?, 1)",
                    ("s-active", "secret output must not appear", now - 3),
                )
                tool_calls = [
                    {
                        "function": {
                            "name": "terminal",
                            "arguments": json.dumps(
                                {
                                    "command": f"OPENAI_API_KEY={fake_key} "
                                    "python '/home/private/My Project/run.py' "
                                    "--token opaquevalue123",
                                    "workdir": "/home/private",
                                }
                            ),
                        }
                    },
                    {
                        "function": {
                            "name": "patch",
                            "arguments": json.dumps(
                                {
                                    "mode": "patch",
                                    "patch": "*** Begin Patch\n"
                                    "*** Update File: /home/private/collector.py\n"
                                    "@@\n-old_value\n+new_value\n*** End Patch",
                                }
                            ),
                        }
                    },
                    {
                        "function": {
                            "name": "write_file",
                            "arguments": json.dumps(
                                {
                                    "path": "/home/private/notes.py",
                                    "content": "password=hunter2",
                                }
                            ),
                        }
                    },
                ]
                conn.execute(
                    "INSERT INTO messages "
                    "(id, session_id, role, content, tool_calls, timestamp, active) "
                    "VALUES (2, ?, 'assistant', '', ?, ?, 1)",
                    ("s-active", json.dumps(tool_calls), now - 4),
                )

            snapshot = collect_snapshot(home, now=now)

        self.assertEqual(
            snapshot["counts"],
            {
                "primary": 1,
                "primary_visible": 1,
                "primary_truncated": False,
                "subagents": 0,
                "total": 1,
            },
        )
        self.assertEqual(len(snapshot["primary"]), 1)
        self.assertEqual(snapshot["primary"][0]["session_id"], "s-active")
        self.assertEqual(snapshot["primary"][0]["source"], "[path]")
        self.assertEqual(snapshot["primary"][0]["title"], "Build Agent HUD in [path]")
        self.assertEqual(snapshot["primary"][0]["action"], "terminal")
        self.assertEqual(snapshot["primary"][0]["last_activity_at"], now - 3)
        self.assertEqual(snapshot["primary"][0]["effort"], "high")
        self.assertEqual(snapshot["primary"][0]["api_calls"], 9)
        self.assertEqual(snapshot["primary"][0]["tool_calls"], 4)
        self.assertEqual(snapshot["primary"][0]["project"], "hermes-agent-hud")
        self.assertEqual(snapshot["primary"][0]["branch"], "[path]")
        self.assertEqual(
            snapshot["primary"][0]["activity"],
            [
                {
                    "kind": "file",
                    "tool": "write_file",
                    "detail": "notes.py · 16 chars",
                    "at": now - 4,
                },
                {
                    "kind": "diff",
                    "tool": "patch",
                    "detail": "collector.py · +1 −1",
                    "at": now - 4,
                },
                {
                    "kind": "command",
                    "tool": "terminal",
                    "detail": "OPENAI_API_KEY=[REDACTED] python [path] --token [REDACTED]",
                    "at": now - 4,
                },
            ],
        )
        self.assertNotIn("model", snapshot["primary"][0])
        self.assertNotIn("private-model-name", json.dumps(snapshot))
        self.assertNotIn("/home/private", json.dumps(snapshot))
        self.assertNotIn("testsecret", json.dumps(snapshot))
        self.assertNotIn("hunter2", json.dumps(snapshot))
        self.assertNotIn("secret output", json.dumps(snapshot))

    def test_expands_running_delegation_into_live_children(self) -> None:
        now = 1_800_000_000.0
        fake_key = "sk-" + "testsecret123456"
        with tempfile.TemporaryDirectory() as raw_home:
            home = Path(raw_home)
            (home / "gateway_state.json").write_text(
                json.dumps({"gateway_state": "running", "active_agents": 1}),
                encoding="utf-8",
            )
            with closing(sqlite3.connect(home / "state.db")) as conn, conn:
                conn.executescript(
                    """
                    CREATE TABLE sessions (
                        id TEXT PRIMARY KEY, source TEXT, title TEXT,
                        started_at REAL, ended_at REAL, last_activity_at REAL,
                        last_activity_description TEXT, session_key TEXT
                    );
                    CREATE TABLE messages (
                        id INTEGER PRIMARY KEY, session_id TEXT, role TEXT,
                        content TEXT, tool_name TEXT, timestamp REAL, active INTEGER
                    );
                    CREATE TABLE async_delegations (
                        delegation_id TEXT PRIMARY KEY, origin_session TEXT,
                        parent_session_id TEXT, state TEXT, dispatched_at REAL,
                        completed_at REAL, updated_at REAL, task_json TEXT
                    );
                    """
                )
                conn.execute(
                    "INSERT INTO sessions VALUES "
                    "('parent', 'discord', 'Build Agent HUD', ?, NULL, ?, "
                    "'working', 'discord:thread:123')",
                    (now - 120, now - 5),
                )
                conn.execute(
                    "INSERT INTO async_delegations VALUES (?, ?, ?, 'running', ?, NULL, ?, ?)",
                    (
                        "deleg_live",
                        "discord:thread:123",
                        "parent",
                        now - 60,
                        now - 2,
                        json.dumps(
                            {
                                "goal": "Review /home/private/My Project/repository now",
                                "goals": ["Review collector", "Run regression tests"],
                            }
                        ),
                    ),
                )
            live = home / "cache" / "delegation" / "live" / "deleg_live"
            live.mkdir(parents=True)
            (live / "manifest.json").write_text(
                json.dumps(
                    {
                        "delegation_id": "deleg_live",
                        "started": "2027-01-15 07:59:00",
                        "tasks": [
                            {
                                "index": 0,
                                "goal": "Review collector",
                                "status": "running",
                                "log": str(live / "task-0.log"),
                            },
                            {
                                "index": 1,
                                "goal": "Run regression tests",
                                "status": "finalizing",
                                "log": str(home / "outside-secret.log"),
                            },
                            {
                                "index": 2,
                                "goal": "Inspect exact candidate",
                                "status": "completed",
                                "exit_reason": "completed",
                                "log": str(live / "task-2.log"),
                            },
                            {
                                "index": "not-an-int",
                                "goal": "Tolerate malformed task metadata",
                                "status": "running",
                                "log": str(live / "task-3.log"),
                            },
                            {
                                "index": 4,
                                "goal": "Detect exhausted child",
                                "status": "completed",
                                "exit_reason": "max_iterations",
                                "log": str(live / "task-4.log"),
                            },
                            {
                                "index": 5,
                                "goal": "Reject redirected log",
                                "status": "running",
                                "log": str(live / "task-5.log"),
                            },
                            {
                                "index": 6,
                                "goal": "Wait for terminal marker",
                                "status": "running",
                                "log": str(live / "task-6.log"),
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )
            first_log = live / "task-0.log"
            first_log.write_text(
                f"22:00:01 tool     | -> terminal(OPENAI_API_KEY={fake_key} "
                "python '/home/private/My Project/run.py' --token opaquevalue123)\n"
                "22:00:02 tool     | -> read_file(collector.py L1-80)\n"
                "22:00:03 tool     | -> skill_view(specification-compliance-review)\n"
                "22:00:04 tool     | -> patch(/home/private/file.py)\n"
                "22:00:05 final    | end status=completed exit_reason=completed\n",
                encoding="utf-8",
            )
            second_log = live / "task-1.log"
            second_log.write_text(
                "22:00:02 result   | terminal ok: secret result\n",
                encoding="utf-8",
            )
            (home / "outside-secret.log").write_text(
                "22:00:04 tool     | -> stolen({'secret':'must not read'})\n",
                encoding="utf-8",
            )
            (live / "task-3.log").write_text(
                "22:00:05 tool     | -> read_file({'path':'private'})\n",
                encoding="utf-8",
            )
            (live / "task-5.log").symlink_to(home / "outside-secret.log")
            (live / "task-6.log").write_text(
                "22:00:06 final    | status=completed duration=1.0s\n",
                encoding="utf-8",
            )
            first_log.touch()
            second_log.touch()

            snapshot = collect_snapshot(home, now=now)

        self.assertEqual(
            snapshot["counts"],
            {
                "primary": 1,
                "primary_visible": 1,
                "primary_truncated": False,
                "subagents": 4,
                "total": 5,
            },
        )
        self.assertEqual(len(snapshot["delegations"]), 1)
        delegation = snapshot["delegations"][0]
        self.assertEqual(delegation["parent_session_id"], "parent")
        self.assertEqual(delegation["goal"], "Review [path]")
        self.assertNotIn("/home/private", json.dumps(snapshot))
        self.assertEqual(
            [child["goal"] for child in delegation["children"]],
            [
                "Review collector",
                "Run regression tests",
                "Inspect exact candidate",
                "Tolerate malformed task metadata",
                "Detect exhausted child",
                "Reject redirected log",
                "Wait for terminal marker",
            ],
        )
        self.assertEqual(
            delegation["progress"],
            {
                "total": 7,
                "running": 3,
                "finalizing": 1,
                "stalling": 0,
                "completed": 2,
                "failed": 1,
            },
        )
        self.assertEqual(delegation["children"][0]["state"], "completed")
        self.assertEqual(delegation["children"][0]["action"], "completed")
        self.assertEqual(
            [item["tool"] for item in delegation["children"][0]["activity"]],
            ["patch", "skill_view", "read_file", "terminal"],
        )
        self.assertEqual(
            [item["detail"] for item in delegation["children"][0]["activity"]],
            [
                "file.py · diff",
                "specification-compliance-review",
                "collector.py L1-80",
                "OPENAI_API_KEY=[REDACTED] python [path] --token [REDACTED]",
            ],
        )
        self.assertEqual(
            [item["clock"] for item in delegation["children"][0]["activity"]],
            ["22:00", "22:00", "22:00", "22:00"],
        )
        self.assertNotIn("testsecret", json.dumps(delegation["children"][0]["activity"]))
        self.assertNotIn("opaquevalue", json.dumps(delegation["children"][0]["activity"]))
        self.assertNotIn("/home/private", json.dumps(delegation["children"][0]["activity"]))
        self.assertEqual(delegation["children"][1]["action"], "between turns")
        self.assertEqual(delegation["children"][1]["log"], str(live / "task-1.log"))
        self.assertEqual(delegation["children"][3]["index"], 3)
        self.assertEqual(delegation["children"][3]["current_tool"], "read_file")
        self.assertEqual(delegation["children"][4]["state"], "failed")
        self.assertEqual(delegation["children"][5]["log"], "")
        self.assertEqual(delegation["children"][5]["action"], "starting")
        self.assertEqual(delegation["children"][6]["state"], "running")
        self.assertEqual(delegation["children"][6]["action"], "finalizing")
        self.assertNotIn("outside-secret", json.dumps(snapshot))
        self.assertNotIn("stolen", json.dumps(snapshot))
        self.assertNotIn("secret command", json.dumps(snapshot))
        self.assertNotIn("secret result", json.dumps(snapshot))


if __name__ == "__main__":
    unittest.main()
