"""Read exact GNOME window frames from the attested WORLDLINE Shell API.

This source observes only. It never activates windows or sends input.
The bus name is pinned to its unique owner for the complete read.
"""
from __future__ import annotations

import json
import os
import re
import stat
import subprocess
from pathlib import Path
from typing import Any

DEST = "org.worldline.WindowFrames"
PATH = "/org/worldline/WindowFrames"
MIN_API = 1


def _call(dest: str, path: str, method: str, *args: str) -> str:
    result = subprocess.run(
        ["gdbus", "call", "--session", "--dest", dest, "--object-path", path,
         "--method", method, *args],
        capture_output=True, text=True, timeout=0.9, check=True,
    )
    return result.stdout.strip()


def _number(value: str) -> int:
    match = re.search(r"\b(\d+)\b", value.split("uint32", 1)[-1])
    if match is None:
        raise ValueError("missing unsigned integer")
    return int(match.group(1))


def _parse_rects_payload(raw: str) -> tuple[list[Any], dict[str, int] | None]:
    """Parse frames and workspace state from one Shell snapshot payload."""
    object_start, array_start = raw.find("{"), raw.find("[")
    if array_start >= 0 and (object_start < 0 or array_start < object_start):
        end = raw.rfind("]")
        parsed = json.loads(raw[array_start:end + 1]) if end >= array_start else None
    else:
        end = raw.rfind("}")
        parsed = json.loads(raw[object_start:end + 1]) if object_start >= 0 and end >= object_start else None
    if isinstance(parsed, list):
        return parsed, None  # API 1 compatibility: no workspace evidence.
    if not isinstance(parsed, dict) or not isinstance(parsed.get("items"), list):
        raise ValueError("helper returned an invalid frame snapshot")
    state = parsed.get("workspaces")
    if not isinstance(state, dict):
        return parsed["items"], None
    count, active = state.get("count"), state.get("active")
    if (type(count) is int and 1 <= count <= 128
            and type(active) is int and 0 <= active < count):
        return parsed["items"], {"count": count, "active": active}
    return parsed["items"], None


def read_windows() -> dict[str, Any]:
    """Return source-labelled frames or an explicit unavailable reading."""
    try:
        bus = "org.freedesktop.DBus"
        bus_path = "/org/freedesktop/DBus"
        owner_raw = _call(bus, bus_path, f"{bus}.GetNameOwner", DEST)
        match = re.search(r"'(:[^']+)'", owner_raw)
        if match is None:
            raise ValueError("helper has no unique owner")
        owner = match.group(1)
        pid = _number(_call(bus, bus_path, f"{bus}.GetConnectionUnixProcessID", owner))
        uid = _number(_call(bus, bus_path, f"{bus}.GetConnectionUnixUser", owner))
        exe = Path(f"/proc/{pid}/exe").resolve(strict=True)
        mode = exe.stat()
        if (uid != os.getuid() or Path(f"/proc/{pid}/comm").read_text().strip() != "gnome-shell"
                or exe.name != "gnome-shell" or mode.st_uid != 0
                or stat.S_IMODE(mode.st_mode) & 0o022):
            raise ValueError("helper is not hosted by the trusted GNOME Shell")
        version = _number(_call(owner, PATH, f"{DEST}.GetVersion"))
        if version < MIN_API:
            raise ValueError("unsupported helper API")
        raw = _call(owner, PATH, f"{DEST}.GetRects")
        data, workspace_state = _parse_rects_payload(raw)
        if version < 2:
            workspace_state = None
        frames = []
        seen = set()
        for item in data:
            if not isinstance(item, dict):
                continue
            ident = (item.get("pid"), item.get("id"))
            values = (item.get("x"), item.get("y"), item.get("w"), item.get("h"))
            if (any(type(v) is not int for v in (*ident, *values))
                    or ident[0] <= 0 or not 0 <= ident[1] <= 0xffffffff
                    or values[2] <= 0 or values[3] <= 0 or ident in seen):
                continue
            seen.add(ident)
            workspace = item.get("workspace")
            item["workspace"] = workspace if type(workspace) is int and workspace >= 0 else None
            item["sticky"] = item.get("sticky") if type(item.get("sticky")) is bool else None
            frames.append(item)
        return {"available": True, "source": "worldline-gnome-shell",
                "helper_api": version, "owner_pid": pid, "items": frames,
                "workspaces": workspace_state}
    except (OSError, ValueError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
        return {"available": False, "source": "worldline-gnome-shell",
                "reason": f"{type(exc).__name__}: {exc}", "items": [],
                "workspaces": None}
