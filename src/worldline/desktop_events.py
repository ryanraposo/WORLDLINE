"""Event and direct-oracle inputs for the single WORLDLINE revision store."""
from __future__ import annotations

import hashlib
import json
import os
import socket
import subprocess
import threading
from pathlib import Path
from time import time
from typing import Any

from .model import Evidence, Fact
from .store import WorldStore
from .cua_gnome import read_windows


def direct_facts(*, pids: list[int] | None = None, paths: list[str] | None = None) -> list[Fact]:
    found: list[Fact] = []
    def add(key: str, value: Any, source: str) -> None:
        found.append(Fact(key, value, Evidence(source=source, expires_at=time() + 5)))
    for key, env in (("session.type", "XDG_SESSION_TYPE"),
                     ("session.desktop", "XDG_CURRENT_DESKTOP"),
                     ("session.wayland_display", "WAYLAND_DISPLAY")):
        if os.environ.get(env):
            add(key, os.environ[env], "environment")
    for pid in (pids or [])[:32]:
        if type(pid) is not int or pid <= 0:
            continue
        root = Path(f"/proc/{pid}")
        add(f"process.{pid}.exists", root.exists(), "procfs")
        for name in ("exe", "cwd"):
            try:
                add(f"process.{pid}.{name}", os.readlink(root / name), "procfs")
            except OSError:
                pass
    for raw in (paths or [])[:32]:
        if not isinstance(raw, str) or len(raw) > 2048:
            continue
        path = Path(raw).expanduser()
        key = f"fs.{hashlib.sha256(str(path).encode()).hexdigest()[:16]}"
        try:
            info = path.stat()
        except OSError:
            add(f"{key}.exists", False, "stat")
            continue
        add(f"{key}.path", str(path), "stat")
        add(f"{key}.exists", True, "stat")
        add(f"{key}.size", info.st_size, "stat")
        add(f"{key}.mtime_ns", info.st_mtime_ns, "stat")
    return found


def compositor_focus_fact() -> Fact | None:
    reading = read_windows()
    if not reading.get("available"):
        return None
    focused = [window for window in reading["items"] if window.get("focused") is True]
    if len(focused) != 1:
        return None
    window = focused[0]
    return Fact("windows.focus.identity",
                {"pid": window["pid"], "id": window["id"]},
                Evidence(source="cua-gnome-shell", expires_at=time() + 1,
                         detail={"frame_source": "exact-compositor-frame",
                                 "frame": {"x": window["x"], "y": window["y"],
                                           "width": window["w"], "height": window["h"]}}))


def apply_event(store: WorldStore, event: dict[str, Any]) -> int:
    source = str(event.get("source") or "external")[:80]
    values = event.get("facts", {})
    invalidates = event.get("invalidates", [])
    if not isinstance(values, dict) or not isinstance(invalidates, list):
        raise ValueError("event requires facts object and invalidates array")
    if len(values) > 128 or len(invalidates) > 128:
        raise ValueError("event is too large")
    # Events may invalidate a namespace; the same event can then publish
    # a replacement value under it. Both operations use this store's clock.
    current = store.snapshot(valid_only=False).facts
    keys = [key for key in current if any(
        key == prefix or key.startswith(prefix + ".")
        for prefix in invalidates if isinstance(prefix, str) and prefix)]
    if keys:
        store.invalidate(keys)
    return store.apply([
        Fact(key, value, Evidence(source=source, expires_at=time() + 15))
        for key, value in values.items() if isinstance(key, str) and 0 < len(key) <= 200
    ])


def capture_visual(socket_path: str, timeout_ms: int = 1500) -> Fact:
    """Hash a fresh optional broker frame, never claim it verifies a target."""
    timeout_ms = max(100, min(int(timeout_ms), 5000))
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(timeout_ms / 1000 + 2)
        client.connect(socket_path)
        client.sendall((json.dumps({"v": 1, "op": "capture", "fresh": "next",
                                    "timeout_ms": timeout_ms}) + "\n").encode())
        data = bytearray()
        while b"\n" not in data and len(data) < 1 << 20:
            chunk = client.recv(65536)
            if not chunk:
                break
            data.extend(chunk)
    response = json.loads(bytes(data).split(b"\n", 1)[0])
    value = response.get("result") or {}
    if not response.get("ok") or not isinstance(value.get("path"), str):
        raise RuntimeError(response.get("code", "visual_unavailable"))
    image = Path(value["path"])
    digest = hashlib.sha256(image.read_bytes()).hexdigest()
    return Fact("visual.frame_hash", digest, Evidence(
        source="pipewire-screencast", expires_at=time() + 5,
        detail={"width": value.get("width"), "height": value.get("height"),
                "scope": "visible-screen"}))


def start_atspi_sensor(store: WorldStore) -> threading.Thread:
    """Subscribe to semantic changes without granting input authority."""
    def worker() -> None:
        try:
            import gi
            gi.require_version("Atspi", "2.0")
            gi.require_version("GLib", "2.0")
            from gi.repository import Atspi, GLib
            Atspi.init()
            def on(event: Any, *_: Any) -> None:
                source = getattr(event, "source", None)
                kind = str(getattr(event, "type", "") or "atspi")
                facts: dict[str, Any] = {"ui.last.event": kind}
                if source:
                    for name, method in (("name", "get_name"),
                                         ("role", "get_role_name"),
                                         ("pid", "get_process_id")):
                        try:
                            value = getattr(source, method)()
                            if value:
                                facts[f"ui.last.{name}"] = int(value) if name == "pid" else value
                        except Exception:
                            pass
                if kind.startswith("focus:"):
                    facts.update({f"ui.focus.{name}": facts[f"ui.last.{name}"]
                                  for name in ("name", "role", "pid")
                                  if f"ui.last.{name}" in facts})
                apply_event(store, {"source": "atspi", "facts": facts,
                                    "invalidates": ["ui.semantic"] + (
                                        ["ui.window_roots"] if kind.startswith("window:") else [])})
            listener = Atspi.EventListener.new(on, None)
            for kind in ("focus:", "object:state-changed", "object:children-changed",
                         "object:property-change", "object:text-changed",
                         "object:selection-changed", "object:value-changed",
                         "window:create", "window:destroy", "window:activate",
                         "window:deactivate", "window:move", "window:resize",
                         "window:minimize", "window:maximize", "window:restore"):
                listener.register(kind)
            GLib.MainLoop().run()
        except Exception:
            # The ordinary windows section retains an explicit AT-SPI
            # unavailable reason when native bindings are absent.
            return
    thread = threading.Thread(target=worker, name="worldline-atspi", daemon=True)
    thread.start()
    return thread
