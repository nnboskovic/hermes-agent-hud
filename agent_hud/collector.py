"""Read-only Hermes runtime collector for Agent HUD."""

from __future__ import annotations

import json
import math
import os
import re
import sqlite3
import stat
import time
from pathlib import Path
from typing import Any

SNAPSHOT_VERSION = 3
PRIMARY_FRESHNESS_SECONDS = 300
MAX_DELEGATIONS = 64
MAX_CHILDREN = 64
MAX_GOAL_CHARS = 140
MAX_ACTIVITY_ITEMS = 12
MAX_ACTIVITY_DETAIL_CHARS = 220
MAX_PRIMARY_ROWS = 32
MAX_IDENTIFIER_CHARS = 160
MAX_GATEWAY_STATE_CHARS = 64
MAX_MANIFEST_BYTES = 1_048_576
_EVENT_RE = re.compile(r"^\d{2}:\d{2}:\d{2}\s+(\w+)\s+\|\s*(.*)$")
_TOOL_RE = re.compile(r"^->\s+([A-Za-z0-9_.:-]+)")
_DOUBLE_QUOTED_PATH_RE = re.compile(r'(?<![A-Za-z0-9])"(?:~/|/)[^"]+"')
_SINGLE_QUOTED_PATH_RE = re.compile(r"(?<![A-Za-z0-9])'(?:~/|/)[^']+'")
_ABS_PATH_RE = re.compile(r"(?<![A-Za-z0-9:/~])/[^,;|)\]}\n]+")
_HOME_PATH_RE = re.compile(r"(?<![A-Za-z0-9])~/[^,;|)\]}\n]+")
_STATUS_RE = re.compile(r"(?:^|\s)(?:end\s+)?status=([a-z_]+)")
_EXIT_REASON_RE = re.compile(r"(?:^|\s)exit_reason=([a-z_]+)")
_SECRET_ENV_RE = re.compile(
    r"\b([A-Z0-9_]*(?:API_?KEY|TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIAL|AUTH)"
    r"[A-Z0-9_]*)\s*=\s*(?!\[REDACTED\])(?:\"[^\"]*\"|'[^']*'|[^\s,;)\]}]+)",
    re.IGNORECASE,
)
_SECRET_PREFIX_RE = re.compile(
    r"(?:sk-|ghp_|github_pat_|xox[baprs]-|hf_|pypi-|glpat-)[A-Za-z0-9_.-]{10,}",
    re.IGNORECASE,
)
_AUTH_RE = re.compile(
    r"(?i)\b(?:authorization\s*:\s*)?(?:bearer|basic)\s+"
    r"(?:\"[^\"]*\"|'[^']*'|[^\s'\"]+)"
)
_AUTH_ASSIGN_RE = re.compile(
    r"(?i)\bauthorization\s*=\s*(?:(?:bearer|basic)\s+)?"
    r"(?:\"[^\"]*\"|'[^']*'|\S+)"
)
_SECRET_KV_RE = re.compile(
    r"(?i)(?<![A-Za-z0-9_-])((?:['\"])?(?:api[-_]?key|access[-_]?token|"
    r"refresh[-_]?token|token|secret|client[-_]?secret|password|passwd|credential|"
    r"authorization)(?:['\"])?\s*[:=]\s*)(?!\[REDACTED\])"
    r"(?:\"[^\"]*\"|'[^']*'|[^&,\s}\]]+)"
)
_SECRET_FLAG_RE = re.compile(
    r"(?i)(--(?:api[-_]?key|token|secret|password|passwd|credential|auth)(?:=|\s+))"
    r"(?:\"[^\"]*\"|'[^']*'|\S+)"
)
_COMMAND_FIELD_RE = re.compile(r"['\"]command['\"]\s*:\s*['\"](.*?)['\"](?:[,}])")
_PATH_FIELD_RE = re.compile(r"['\"]path['\"]\s*:\s*['\"](.*?)['\"](?:[,}])")
_ACTIVE_STATES = {"running", "stalling", "finalizing"}
_FAILED_STATES = {"error", "failed", "stalled", "interrupted"}
_VISIBLE_STATES = _ACTIVE_STATES | _FAILED_STATES | {"completed"}
_EFFORTS = {"none", "minimal", "low", "medium", "high", "xhigh", "max", "ultra"}


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _read_confined_json(path: Path, *, max_bytes: int = MAX_MANIFEST_BYTES) -> dict[str, Any]:
    descriptor: int | None = None
    try:
        before = path.lstat()
        if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
            return {}
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags)
        after = os.fstat(descriptor)
        if (
            not stat.S_ISREG(after.st_mode)
            or not os.path.samestat(before, after)
            or after.st_size > max_bytes
        ):
            return {}
        with os.fdopen(descriptor, "rb") as handle:
            descriptor = None
            payload = handle.read(max_bytes + 1)
        if len(payload) > max_bytes:
            return {}
        value = json.loads(payload.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    finally:
        if descriptor is not None:
            os.close(descriptor)
    return value if isinstance(value, dict) else {}


def _connect_read_only(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True, timeout=2)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    return connection


def _table_columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {str(row["name"]) for row in connection.execute(f"PRAGMA table_info({table})")}


def _latest_action(
    connection: sqlite3.Connection,
    session_id: str,
    fallback: str,
) -> tuple[str, float]:
    columns = _table_columns(connection, "messages")
    required = {"session_id", "role", "tool_name", "timestamp"}
    if not required.issubset(columns):
        return fallback or "working", 0.0
    active_clause = "AND active=1" if "active" in columns else ""
    row = connection.execute(
        "SELECT role, tool_name, timestamp FROM messages "
        f"WHERE session_id=? {active_clause} ORDER BY timestamp DESC LIMIT 1",
        (session_id,),
    ).fetchone()
    if row is not None:
        timestamp = _finite_float(row["timestamp"])
        if str(row["role"] or "") == "tool" and row["tool_name"]:
            return str(row["tool_name"]), timestamp
        return fallback or "working", timestamp
    return fallback or "working", 0.0


def _reasoning_effort(value: Any) -> str:
    try:
        config = json.loads(str(value or "{}"))
    except json.JSONDecodeError:
        return ""
    if not isinstance(config, dict):
        return ""
    reasoning = config.get("reasoning_config")
    if not isinstance(reasoning, dict):
        return ""
    if reasoning.get("enabled") is False:
        return "none"
    effort = str(reasoning.get("effort") or "").strip().lower()
    return effort if effort in _EFFORTS else ""


def _optional_column(columns: set[str], name: str, default: str = "NULL") -> str:
    return name if name in columns else f"{default} AS {name}"


def _safe_nonnegative_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError, OverflowError):
        return 0


def _finite_float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return number if math.isfinite(number) else default


def _sanitize_text(value: Any, *, limit: int) -> str:
    text = " ".join(str(value or "").split())
    text = _AUTH_ASSIGN_RE.sub("authorization=[REDACTED]", text)
    text = _AUTH_RE.sub("authorization: [REDACTED]", text)
    text = _SECRET_KV_RE.sub(lambda match: f"{match.group(1)}[REDACTED]", text)
    text = _SECRET_ENV_RE.sub(lambda match: f"{match.group(1)}=[REDACTED]", text)
    text = _SECRET_PREFIX_RE.sub("[REDACTED]", text)
    text = _SECRET_FLAG_RE.sub(lambda match: f"{match.group(1)}[REDACTED]", text)
    text = _DOUBLE_QUOTED_PATH_RE.sub("[path]", text)
    text = _SINGLE_QUOTED_PATH_RE.sub("[path]", text)
    text = _HOME_PATH_RE.sub("[path]", text)
    text = _ABS_PATH_RE.sub("[path]", text)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _clip_goal(value: Any) -> str:
    return _sanitize_text(value, limit=MAX_GOAL_CHARS)


def _activity_detail(value: Any) -> str:
    return _sanitize_text(value, limit=MAX_ACTIVITY_DETAIL_CHARS)


def _bounded_identifier(value: Any) -> str:
    return _sanitize_text(value, limit=MAX_IDENTIFIER_CHARS)


def _project_name(value: Any) -> str:
    raw = str(value or "").rstrip("/\\")
    if not raw:
        return ""
    return _clip_goal(Path(raw).name)


def _argument_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str):
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _basename(value: Any) -> str:
    raw = str(value or "").rstrip("/\\")
    return _activity_detail(Path(raw).name) if raw else ""


def _diff_detail(arguments: dict[str, Any]) -> str:
    patch_text = str(arguments.get("patch") or "")
    paths = re.findall(r"^\*\*\* (?:Update|Add|Delete) File:\s*(.+)$", patch_text, re.MULTILINE)
    if not paths and arguments.get("path"):
        paths = [str(arguments["path"])]
    names = list(dict.fromkeys(filter(None, (_basename(path) for path in paths))))
    label = ", ".join(names[:2]) or "code change"
    if patch_text:
        additions = sum(
            line.startswith("+") and not line.startswith("+++")
            for line in patch_text.splitlines()
        )
        removals = sum(
            line.startswith("-") and not line.startswith("---")
            for line in patch_text.splitlines()
        )
        return _activity_detail(f"{label} · +{additions} −{removals}")
    mode = str(arguments.get("mode") or "replace")
    return _activity_detail(f"{label} · {mode}")


def _activity_item(name: Any, raw_arguments: Any, timestamp: Any) -> dict[str, Any]:
    tool = _activity_detail(name or "tool")
    arguments = _argument_dict(raw_arguments)
    kind = "tool"
    if tool == "terminal":
        kind = "command"
        detail = _activity_detail(arguments.get("command") or "command")
    elif tool == "patch":
        kind = "diff"
        detail = _diff_detail(arguments)
    elif tool == "write_file":
        kind = "file"
        detail = _activity_detail(
            f"{_basename(arguments.get('path')) or 'file'} · "
            f"{len(str(arguments.get('content') or ''))} chars"
        )
    elif tool == "read_file":
        kind = "file"
        detail = _basename(arguments.get("path")) or "file"
        offset = _safe_nonnegative_int(arguments.get("offset"))
        limit = _safe_nonnegative_int(arguments.get("limit"))
        if offset and limit:
            detail = _activity_detail(f"{detail} · lines {offset}–{offset + limit - 1}")
    elif tool == "search_files":
        kind = "file"
        target = _basename(arguments.get("path")) or "files"
        pattern = _activity_detail(arguments.get("pattern") or "")
        detail = _activity_detail(f"{target} · {pattern}" if pattern else target)
    else:
        keys = ", ".join(sorted(str(key) for key in arguments)[:6])
        detail = _activity_detail(keys or "invoked")
    at = _finite_float(timestamp)
    return {"kind": kind, "tool": tool, "detail": detail, "at": at}


def _primary_activity(connection: sqlite3.Connection, session_id: str) -> list[dict[str, Any]]:
    columns = _table_columns(connection, "messages")
    required = {"session_id", "role", "tool_calls", "timestamp"}
    if not required.issubset(columns):
        return []
    active_clause = "AND active=1" if "active" in columns else ""
    rows = connection.execute(
        "SELECT tool_calls, timestamp FROM messages "
        f"WHERE session_id=? AND role='assistant' AND tool_calls IS NOT NULL {active_clause} "
        "ORDER BY timestamp DESC LIMIT 30",
        (session_id,),
    ).fetchall()
    activity: list[dict[str, Any]] = []
    for row in rows:
        try:
            calls = json.loads(str(row["tool_calls"] or "[]"))
        except json.JSONDecodeError:
            continue
        if not isinstance(calls, list):
            continue
        for call in reversed(calls):
            if not isinstance(call, dict):
                continue
            function = call.get("function")
            if not isinstance(function, dict):
                continue
            activity.append(
                _activity_item(function.get("name"), function.get("arguments"), row["timestamp"])
            )
            if len(activity) >= MAX_ACTIVITY_ITEMS:
                return activity
    return activity


def _primary_agents(home: Path, *, count: int, now: float) -> list[dict[str, Any]]:
    if count <= 0 or not (home / "state.db").is_file():
        return []
    try:
        connection = _connect_read_only(home / "state.db")
    except sqlite3.Error:
        return []
    try:
        columns = _table_columns(connection, "sessions")
        required = {"id", "source", "started_at", "ended_at", "last_activity_at"}
        if not required.issubset(columns):
            return []
        title_sql = "title" if "title" in columns else "'' AS title"
        description_sql = (
            "last_activity_description"
            if "last_activity_description" in columns
            else "'' AS last_activity_description"
        )
        session_key_sql = "session_key" if "session_key" in columns else "'' AS session_key"
        optional_sql = ", ".join(
            _optional_column(columns, name)
            for name in (
                "model_config",
                "api_call_count",
                "tool_call_count",
                "git_repo_root",
                "git_branch",
            )
        )
        rows = connection.execute(
            f"SELECT id, source, {title_sql}, started_at, last_activity_at, "
            f"{description_sql}, {session_key_sql}, {optional_sql} FROM sessions "
            "WHERE ended_at IS NULL AND COALESCE(source, '') != 'subagent' "
            "ORDER BY COALESCE(last_activity_at, started_at) DESC LIMIT ?",
            (max(count * 4, count),),
        ).fetchall()
        agents: list[dict[str, Any]] = []
        for row in rows:
            raw_started_at = _finite_float(row["started_at"])
            activity_at = _finite_float(row["last_activity_at"], raw_started_at)
            started_at = _finite_float(row["started_at"], activity_at)
            if now - activity_at > PRIMARY_FRESHNESS_SECONDS:
                continue
            session_id = str(row["id"])
            action, message_activity_at = _latest_action(
                connection,
                session_id,
                str(row["last_activity_description"] or ""),
            )
            agents.append(
                {
                    "session_id": _bounded_identifier(session_id),
                    "session_key": _bounded_identifier(row["session_key"]),
                    "source": _clip_goal(row["source"] or "hermes"),
                    "title": _clip_goal(row["title"] or "Hermes agent"),
                    "state": "running",
                    "action": _clip_goal(action),
                    "effort": _reasoning_effort(row["model_config"]),
                    "api_calls": _safe_nonnegative_int(row["api_call_count"]),
                    "tool_calls": _safe_nonnegative_int(row["tool_call_count"]),
                    "project": _project_name(row["git_repo_root"]),
                    "branch": _clip_goal(row["git_branch"]),
                    "activity": _primary_activity(connection, session_id),
                    "started_at": started_at,
                    "last_activity_at": max(activity_at, message_activity_at),
                }
            )
            if len(agents) >= count:
                break
        while len(agents) < count:
            agents.append(
                {
                    "session_id": "",
                    "session_key": "",
                    "source": "hermes",
                    "title": "Hermes agent",
                    "state": "running",
                    "action": "working",
                    "effort": "",
                    "api_calls": 0,
                    "tool_calls": 0,
                    "project": "",
                    "branch": "",
                    "activity": [],
                    "started_at": now,
                    "last_activity_at": now,
                }
            )
        return agents
    except sqlite3.Error:
        return []
    finally:
        connection.close()


def _terminal_state(role: str, detail: str) -> str:
    if role != "final":
        return ""
    normalized = detail.strip().lower()
    if not normalized.startswith("end "):
        return ""
    status_match = _STATUS_RE.search(normalized)
    exit_match = _EXIT_REASON_RE.search(normalized)
    status = status_match.group(1) if status_match else ""
    exit_reason = exit_match.group(1) if exit_match else ""
    if status in _FAILED_STATES or (exit_reason and exit_reason != "completed"):
        return "failed"
    return "completed" if status == "completed" else ""


def _file_preview(preview: str) -> str:
    path_match = _PATH_FIELD_RE.search(preview)
    if path_match:
        return _basename(path_match.group(1)) or "file"
    if preview.lstrip().startswith("{"):
        return "file"
    range_match = re.match(r"^(.*?)(\s+L\d+(?:-\d+)?)$", preview)
    if range_match:
        return _activity_detail(f"{_basename(range_match.group(1))} {range_match.group(2).strip()}")
    if "/" in preview or "\\" in preview:
        return _basename(preview) or "file"
    if re.fullmatch(r"[^{}\s]+\.[A-Za-z0-9]{1,10}", preview):
        return _basename(preview)
    return "file"


def _preview_field(preview: str, field: str) -> str:
    match = re.search(
        rf"['\"]{re.escape(field)}['\"]\s*:\s*(['\"])(.*?)\1",
        preview,
    )
    return _activity_detail(match.group(2)) if match else ""


def _preview_keys(preview: str) -> str:
    keys = re.findall(r"['\"]([A-Za-z_][A-Za-z0-9_]*)['\"]\s*:", preview)
    return ", ".join(dict.fromkeys(keys)) or "invoked"


def _log_tool_activity(detail: str, clock: str) -> dict[str, Any]:
    tool_match = _TOOL_RE.match(detail)
    tool = tool_match.group(1) if tool_match else "tool"
    wrapped = detail[tool_match.end() :].strip() if tool_match else ""
    preview = (
        wrapped[1:-1].strip()
        if wrapped.startswith("(") and wrapped.endswith(")")
        else wrapped
    )
    kind = "tool"
    if tool == "terminal":
        kind = "command"
        command_match = _COMMAND_FIELD_RE.search(preview)
        projected = (
            command_match.group(1)
            if command_match
            else "command"
            if preview.lstrip().startswith("{")
            else preview or "command"
        )
    elif tool == "patch":
        kind = "diff"
        path_match = _PATH_FIELD_RE.search(preview)
        patch_path = re.search(
            r"\*\*\* (?:Update|Add|Delete) File:\s*(.+?)(?:\\n|$)",
            preview,
        )
        target = (
            path_match.group(1)
            if path_match
            else patch_path.group(1)
            if patch_path
            else preview
        )
        normalized_patch = preview.replace("\\n", "\n")
        additions = sum(
            line.startswith("+") and not line.startswith("+++")
            for line in normalized_patch.splitlines()
        )
        removals = sum(
            line.startswith("-") and not line.startswith("---")
            for line in normalized_patch.splitlines()
        )
        if target and not target.startswith("{"):
            suffix = f"+{additions} −{removals}" if additions or removals else "diff"
            projected = f"{_basename(target)} · {suffix}"
        else:
            projected = "code change"
    elif tool in {"read_file", "write_file"}:
        kind = "file"
        projected = _file_preview(preview)
        if tool == "write_file" and projected != "file":
            projected = f"{projected} · write"
    elif tool == "search_files":
        kind = "file"
        projected = (
            _preview_field(preview, "pattern")
            if preview.lstrip().startswith("{")
            else _activity_detail(preview)
        ) or "search files"
    elif tool == "skill_view":
        if preview.lstrip().startswith("{"):
            name = _preview_field(preview, "name")
            linked = _preview_field(preview, "file_path")
            projected = name or "view skill"
            if linked:
                projected = f"{projected} → {_basename(linked)}"
        else:
            projected = preview or "view skill"
    elif tool == "web_search":
        projected = "web search"
    elif tool in {"prime_agent_run", "delegate_task"}:
        projected = "delegated task"
    elif tool == "todo":
        projected = "update task list"
    elif tool == "vision_analyze":
        projected = "inspect image"
    elif preview.lstrip().startswith("{"):
        projected = _preview_keys(preview)
    else:
        projected = "invoked"
    return {
        "kind": kind,
        "tool": _activity_detail(tool),
        "detail": _activity_detail(projected),
        "at": 0.0,
        "clock": clock,
    }


def _log_activity(
    path: Path | None,
) -> tuple[str, str, float, str, list[dict[str, Any]]]:
    action = "starting"
    current_tool = ""
    terminal_state = ""
    activity: list[dict[str, Any]] = []
    if path is None:
        return action, current_tool, 0.0, terminal_state, activity
    descriptor: int | None = None
    try:
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags)
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise OSError("live log is not a regular file")
        with os.fdopen(descriptor, "rb") as handle:
            descriptor = None
            handle.seek(0, 2)
            size = handle.tell()
            handle.seek(max(0, size - 65_536))
            lines = handle.read().decode("utf-8", "replace").splitlines()
        modified_at = metadata.st_mtime
    except OSError:
        return action, current_tool, 0.0, terminal_state, activity
    finally:
        if descriptor is not None:
            os.close(descriptor)
    for line in reversed(lines):
        match = _EVENT_RE.match(line)
        if match is None:
            continue
        role, detail = match.groups()
        terminal_state = _terminal_state(role, detail)
        if role == "tool":
            tool_match = _TOOL_RE.match(detail)
            current_tool = tool_match.group(1) if tool_match else "tool"
            action = current_tool
        elif role == "result":
            action = "between turns"
        elif role == "think":
            action = "thinking"
        elif role == "assistant":
            action = "responding"
        elif role in {"final", "error"}:
            action = "finalizing" if role == "final" else "error"
        else:
            action = "starting"
        break
    for line in reversed(lines):
        match = _EVENT_RE.match(line)
        if match is None or match.group(1) != "tool":
            continue
        activity.append(_log_tool_activity(match.group(2), line[:5]))
        if len(activity) >= MAX_ACTIVITY_ITEMS:
            break
    return action, current_tool, modified_at, terminal_state, activity


def _child_state(task: dict[str, Any], delegation_state: str, log_state: str) -> str:
    state = str(task.get("status") or delegation_state).strip().lower()
    if state in _FAILED_STATES:
        return "failed"
    if state == "completed":
        exit_reason = str(task.get("exit_reason") or "completed").strip().lower()
        return "completed" if exit_reason == "completed" else "failed"
    if log_state in {"completed", "failed"}:
        return log_state
    if delegation_state == "stalling" and state in _ACTIVE_STATES:
        return "stalling"
    return state


def _task_index(value: Any, fallback: int) -> int:
    if type(value) is not int:
        return fallback
    return value if 0 <= value < MAX_CHILDREN else fallback


def _delegation_directory(home: Path, delegation_id: str) -> Path | None:
    if (
        not delegation_id
        or Path(delegation_id).name != delegation_id
        or not re.fullmatch(r"[A-Za-z0-9_.-]+", delegation_id)
    ):
        return None
    root = home.absolute()
    try:
        if root.resolve() != root:
            return None
    except OSError:
        return None
    current = root
    for component in ("cache", "delegation", "live"):
        try:
            metadata = current.lstat()
        except OSError:
            return None
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
            return None
        current /= component
    try:
        metadata = current.lstat()
    except OSError:
        return None
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        return None
    live_root = current
    named = live_root / delegation_id
    try:
        metadata = named.lstat()
    except OSError:
        return None
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        return None
    candidate = named.resolve()
    return candidate if candidate.parent == live_root else None


def _task_log_path(directory: Path, task_index: int) -> Path | None:
    candidate = directory / f"task-{task_index}.log"
    try:
        metadata = candidate.lstat()
    except OSError:
        return None
    if (
        candidate.parent != directory
        or stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISREG(metadata.st_mode)
    ):
        return None
    return candidate


def _progress(children: list[dict[str, Any]]) -> dict[str, int]:
    result = {
        "total": len(children),
        "running": 0,
        "finalizing": 0,
        "stalling": 0,
        "completed": 0,
        "failed": 0,
    }
    for child in children:
        state = str(child.get("state") or "")
        key = state if state in result else "failed"
        if key != "total":
            result[key] += 1
    return result


def _delegations(home: Path) -> tuple[list[dict[str, Any]], int]:
    database = home / "state.db"
    if not database.is_file():
        return [], 0
    try:
        connection = _connect_read_only(database)
    except sqlite3.Error:
        return [], 0
    try:
        columns = _table_columns(connection, "async_delegations")
        required = {
            "delegation_id",
            "parent_session_id",
            "state",
            "dispatched_at",
            "task_json",
        }
        if not required.issubset(columns):
            return [], 0
        rows = connection.execute(
            "SELECT delegation_id, parent_session_id, state, dispatched_at, task_json "
            "FROM async_delegations WHERE state IN ('running','stalling','finalizing') "
            "ORDER BY dispatched_at DESC LIMIT ?",
            (MAX_DELEGATIONS,),
        ).fetchall()
    except sqlite3.Error:
        return [], 0
    finally:
        connection.close()

    delegations: list[dict[str, Any]] = []
    child_count = 0
    for row in rows:
        delegation_id = str(row["delegation_id"])
        try:
            task_data = json.loads(str(row["task_json"] or "{}"))
        except json.JSONDecodeError:
            task_data = {}
        goals = task_data.get("goals") if isinstance(task_data, dict) else []
        if not isinstance(goals, list):
            goals = []
        delegation_directory = _delegation_directory(home, delegation_id)
        if delegation_directory is None:
            continue
        manifest_path = delegation_directory / "manifest.json"
        manifest = _read_confined_json(manifest_path)
        manifest_tasks = manifest.get("tasks") if isinstance(manifest.get("tasks"), list) else []
        children: list[dict[str, Any]] = []
        task_rows = manifest_tasks or [
            {"index": index, "goal": goal, "status": row["state"]}
            for index, goal in enumerate(goals)
        ]
        for index, task in enumerate(task_rows[:MAX_CHILDREN]):
            if not isinstance(task, dict):
                continue
            task_index = _task_index(task.get("index", index), index)
            goal = task.get("goal")
            if not goal and task_index < len(goals):
                goal = goals[task_index]
            log_path = _task_log_path(delegation_directory, task_index)
            action, current_tool, last_activity_at, log_state, activity = _log_activity(
                log_path
            )
            state = _child_state(task, str(row["state"]), log_state)
            if state not in _VISIBLE_STATES and state != "failed":
                continue
            if state == "completed":
                action = "completed"
            elif state == "failed":
                action = "failed"
            children.append(
                {
                    "index": task_index,
                    "goal": _clip_goal(goal or f"Subagent {task_index + 1}"),
                    "state": state,
                    "action": action,
                    "current_tool": current_tool,
                    "last_activity_at": last_activity_at,
                    "log": str(log_path) if log_path is not None else "",
                    "activity": activity,
                }
            )
        if not children:
            continue
        child_count += sum(child["state"] in _ACTIVE_STATES for child in children)
        delegations.append(
            {
                "delegation_id": _bounded_identifier(delegation_id),
                "parent_session_id": _bounded_identifier(row["parent_session_id"]),
                "state": _clip_goal(row["state"]),
                "started_at": _finite_float(row["dispatched_at"]),
                "goal": _clip_goal(task_data.get("goal") if isinstance(task_data, dict) else ""),
                "progress": _progress(children),
                "children": children,
            }
        )
    return delegations, child_count


def collect_snapshot(home: Path, *, now: float | None = None) -> dict[str, Any]:
    """Collect a sanitized, read-only snapshot from one Hermes home."""
    timestamp = _finite_float(time.time() if now is None else now, time.time())
    gateway = _read_json(home / "gateway_state.json")
    try:
        primary_count = max(0, int(gateway.get("active_agents", 0)))
    except (TypeError, ValueError, OverflowError):
        primary_count = 0
    primary = _primary_agents(home, count=min(primary_count, MAX_PRIMARY_ROWS), now=timestamp)
    delegations, subagent_count = _delegations(home)
    return {
        "version": SNAPSHOT_VERSION,
        "generated_at": timestamp,
        "gateway": {
            "running": gateway.get("gateway_state") == "running",
            "state": _sanitize_text(
                gateway.get("gateway_state") or "unknown",
                limit=MAX_GATEWAY_STATE_CHARS,
            ),
        },
        "counts": {
            "primary": primary_count,
            "primary_visible": len(primary),
            "primary_truncated": primary_count > len(primary),
            "subagents": subagent_count,
            "total": primary_count + subagent_count,
        },
        "primary": primary,
        "delegations": delegations,
    }
