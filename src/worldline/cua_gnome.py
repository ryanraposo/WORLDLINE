"""Read exact GNOME window frames from the attested Cua Shell helper.

This source observes only. Input and activation remain with Cua's actuator.
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

DEST = "org.cua.WinRects"
PATH = "/org/cua/WinRects"
MIN_API = 8


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
        start, end = raw.find("["), raw.rfind("]")
        if start < 0 or end < start:
            raise ValueError("helper returned no frame array")
        data = json.loads(raw[start:end + 1])
        if not isinstance(data, list):
            raise ValueError("helper returned an invalid frame array")
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
            frames.append(item)
        return {"available": True, "source": "cua-gnome-shell",
                "helper_api": version, "owner_pid": pid, "items": frames}
    except (OSError, ValueError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
        return {"available": False, "source": "cua-gnome-shell",
                "reason": f"{type(exc).__name__}: {exc}", "items": []}
