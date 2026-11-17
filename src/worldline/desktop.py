"""Revisioned, session-scoped desktop observation over native window sources.

This layer assigns consumer-safe identities to observed window lifetimes and
publishes coherent snapshots plus a bounded change journal. It is strictly
read-only: resolution never implies activation or permission to act.
"""
from __future__ import annotations

from collections import deque
from pathlib import Path
from threading import RLock
from time import monotonic, time
from typing import Any, Callable
from uuid import uuid4

from .observe import windows_snapshot


class DesktopObservationService:
    """Normalize native window observations into a revisioned desktop stream."""

    SCHEMA = "worldline.desktop-observation/1"
    EVENT_LIMIT = 512

    def __init__(self, reader: Callable[..., dict[str, Any]] = windows_snapshot) -> None:
        self._reader = reader
        self._lock = RLock()
        self._session_id = str(uuid4())
        self._revision = 0
        self._sequence = 0
        self._observed_at: float | None = None
        self._source: dict[str, Any] = {}
        self._windows: dict[str, dict[str, Any]] = {}
        self._identities: dict[str, str] = {}
        self._events: deque[dict[str, Any]] = deque(maxlen=self.EVENT_LIMIT)

    @staticmethod
    def _pid_start_time(pid: int) -> str:
        """Read Linux process start ticks to distinguish PID reuse."""
        try:
            raw = Path(f"/proc/{pid}/stat").read_text(encoding="ascii")
            close = raw.rfind(")")
            fields = raw[close + 2:].split()
            return fields[19] if close >= 0 and len(fields) > 19 else "unknown"
        except (OSError, UnicodeError):
            return "unknown"

    @staticmethod
    def _identity_key(item: dict[str, Any]) -> str | None:
        pid = item.get("pid")
        if type(pid) is not int or pid <= 0:
            return None
        birth = DesktopObservationService._pid_start_time(pid)
        compositor_id = item.get("compositor_id")
        if item.get("compositor_verified") is True and type(compositor_id) is int:
            return f"compositor:{pid}:{birth}:{compositor_id}"
        path = item.get("accessible_path")
        if isinstance(path, str) and path.startswith("/org/a11y/atspi/accessible/"):
            return f"atspi:{pid}:{birth}:{path}"
        return None

    @staticmethod
    def _state(item: dict[str, Any]) -> dict[str, bool | None]:
        result: dict[str, bool | None] = {}
        for key in ("focused", "active", "visible", "minimized", "maximized",
                    "fullscreen", "mapped", "shaded", "modal"):
            value = item.get(key)
            result[key] = value if type(value) is bool else None
        return result

    @staticmethod
    def _frame(item: dict[str, Any]) -> dict[str, Any] | None:
        geometry = item.get("geometry")
        frame = geometry.get("frame") if isinstance(geometry, dict) else None
        if frame is None:
            frame = item.get("frame")
        if not isinstance(frame, dict):
            return None
        keys = ("x", "y", "width", "height")
        if any(type(frame.get(key)) not in (int, float) for key in keys):
            return None
        return {key: frame[key] for key in keys}

    def _record(self, kind: str, stable_id: str, detail: dict[str, Any]) -> None:
        self._sequence += 1
        self._events.append({
            "sequence": self._sequence,
            "revision": self._revision,
            "observed_at": self._observed_at,
            "type": kind,
            "window_id": stable_id,
            "detail": detail,
        })

    def refresh(self) -> dict[str, Any]:
        """Acquire one native observation and atomically publish its revision."""
        started = monotonic()
        reading = self._reader(exact_only=False)
        now = time()
        duration_ms = round((monotonic() - started) * 1000, 3)
        with self._lock:
            if (not isinstance(reading, dict) or reading.get("available") is not True
                    or not isinstance(reading.get("items"), list)):
                self._source = reading if isinstance(reading, dict) else {
                    "available": False, "reason": "invalid observation response"}
                if self._source.get("available") is True and not isinstance(self._source.get("items"), list):
                    self._source = {**self._source, "available": False,
                                    "reason": "window enumeration returned an invalid item list"}
                if self._source.get("available") is True and not isinstance(self._source.get("items"), list):
                    self._source = {**self._source, "available": False,
                                    "reason": "window enumeration returned an invalid item list"}
                return self._snapshot_unlocked()

            next_windows: dict[str, dict[str, Any]] = {}
            next_identities: dict[str, str] = {}
            for raw in reading.get("items", [])[:256]:
                if not isinstance(raw, dict):
                    continue
                key = self._identity_key(raw)
                if key is None:
                    continue
                stable_id = self._identities.get(key)
                if stable_id is None:
                    stable_id = f"window:{self._session_id}:{uuid4()}"
                item = dict(raw)
                item["stable_id"] = stable_id
                item["window_id"] = stable_id
                item["identity"] = {
                    "scope": "worldline-session",
                    "session_id": self._session_id,
                    "process_start_time": self._pid_start_time(item["pid"]),
                    "stable": True,
                    "source_key": "compositor-window" if key.startswith("compositor:") else "atspi-accessible",
                }
                item["state"] = self._state(raw)
                item["client_frame"] = raw.get("component_extents")
                item["buffer_geometry"] = None
                item["geometry"] = {
                    **(raw.get("geometry") if isinstance(raw.get("geometry"), dict) else {}),
                    "frame": self._frame(raw),
                    "coordinate_space": "desktop-logical-px",
                    "source": raw.get("geometry_source") or "unknown",
                    "verified": raw.get("compositor_verified") is True,
                    "buffer_size": None,
                }
                item["provenance"] = {
                    "identity": "worldline-gnome-shell" if key.startswith("compositor:") else "at-spi2",
                    "geometry": raw.get("geometry_source") or "unknown",
                    "semantic": "at-spi2" if raw.get("accessible_path") else None,
                    "compositor_verified": raw.get("compositor_verified") is True,
                    "quality": "compositor_verified" if raw.get("compositor_verified") is True
                               else "semantic_or_estimated",
                    "observed_at": now,
                    "freshness": "current-snapshot",
                }
                next_windows[stable_id] = item
                next_identities[key] = stable_id

            had_previous_observation = self._observed_at is not None
            self._revision += 1
            self._observed_at = now
            self._capture_duration_ms = duration_ms
            self._capture_duration_ms = duration_ms
            for item in next_windows.values():
                item["revision"] = self._revision
                item["observed_at"] = now
            previous = self._windows
            for stable_id, item in next_windows.items():
                old = previous.get(stable_id)
                if old is None:
                    self._record("window.created", stable_id, {
                        "pid": item.get("pid"), "title": item.get("title"),
                    })
                    continue
                if self._frame(old) != self._frame(item):
                    self._record("window.geometry_changed", stable_id, {
                        "before": self._frame(old), "after": self._frame(item),
                    })
                if old.get("state") != item.get("state"):
                    self._record("window.state_changed", stable_id, {
                        "before": old.get("state"), "after": item.get("state"),
                    })
                if old.get("title") != item.get("title"):
                    self._record("window.title_changed", stable_id, {
                        "before": old.get("title"), "after": item.get("title"),
                    })
            for stable_id, item in previous.items():
                if stable_id not in next_windows:
                    self._record("window.destroyed", stable_id, {
                        "pid": item.get("pid"), "title": item.get("title"),
                    })
            old_display = {"screen": self._source.get("screen"),
                           "monitors": self._source.get("monitors", [])}
            new_display = {"screen": reading.get("screen"),
                           "monitors": reading.get("monitors", [])}
            if old_display != new_display and had_previous_observation:
                self._record("display.monitors_changed", "", {
                    "before": old_display, "after": new_display,
                })
            old_focus = next((key for key, item in previous.items()
                              if item.get("state", {}).get("focused") is True), None)
            new_focus = next((key for key, item in next_windows.items()
                              if item.get("state", {}).get("focused") is True), None)
            if old_focus != new_focus:
                self._record("focus.changed", new_focus or "", {
                    "before": old_focus, "after": new_focus,
                })
            self._windows = next_windows
            self._identities = next_identities
            self._source = reading
            return self._snapshot_unlocked()

    def _capabilities_unlocked(self) -> dict[str, Any]:
        sources = self._source.get("sources") or {}
        geometry = sources.get("geometry") or {}
        semantic = sources.get("semantic") or {}
        exact = geometry.get("name") == "worldline-gnome-shell" and geometry.get("available") is True
        return {
            "window_enumeration": {"available": self._source.get("available") is True,
                                   "source": self._source.get("source")},
            "stable_session_identity": {"available": bool(self._windows),
                                        "scope": "worldline-session"},
            "compositor_frame_geometry": {"available": exact,
                                           "source": geometry.get("name"),
                                           "reason": geometry.get("reason")},
            "semantic_metadata": {"available": semantic.get("available") is True,
                                  "source": semantic.get("name"),
                                  "reason": semantic.get("reason")},
            "focus": {"available": any(item.get("state", {}).get("focused") is True
                                       for item in self._windows.values()),
                      "source": "compositor-or-atspi"},
            "stacking": {"available": self._source.get("stacking_order") is not None,
                         "source": geometry.get("name")},
            "workspace": {"available": False,
                          "reason": "the current GNOME observation adapter does not expose workspace membership"},
            "pixel_visibility": {"available": False,
                                 "reason": "window rectangles and stacking do not prove rendered pixels"},
            "activation": {"available": False,
                           "reason": "WORLDLINE is read-only; activation belongs to the actuator"},
            "input": {"available": False,
                      "reason": "WORLDLINE does not inject input"},
        }

    def _snapshot_unlocked(self) -> dict[str, Any]:
        return {
            "schema": self.SCHEMA,
            "session_id": self._session_id,
            "revision": self._revision,
            "event_sequence": self._sequence,
            "observed_at": self._observed_at,
            "capture_duration_ms": getattr(self, "_capture_duration_ms", None),
            "available": self._source.get("available") is True,
            "reason": self._source.get("reason"),
            "coordinates": {"space": "desktop-logical-px", "origin": "top-left",
                            "x_axis": "right", "y_axis": "down"},
            "display": {"screen": self._source.get("screen"),
                        "monitors": self._source.get("monitors", [])},
            "windows": list(self._windows.values()),
            "focus": next(({"window_id": stable_id, "verified":
                            item.get("compositor_verified") is True}
                           for stable_id, item in self._windows.items()
                           if item.get("state", {}).get("focused") is True), None),
            "stacking_order": self._source.get("stacking_order"),
            "workspace": None,
            "capabilities": self._capabilities_unlocked(),
            "provenance": {
                "source": self._source.get("source"),
                "sources": self._source.get("sources", {}),
                "limitations": [
                    "stacking order does not prove pixel visibility",
                    "rectangle occlusion does not model transparency or shaped surfaces",
                    "unknown and unsupported properties remain null",
                ],
            },
        }

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return self._snapshot_unlocked()

    def resolve(self, window_id: str) -> dict[str, Any] | None:
        with self._lock:
            item = self._windows.get(window_id)
            return dict(item) if item is not None else None

    def events(self, after_sequence: int = 0, limit: int = 128) -> dict[str, Any]:
        with self._lock:
            limit = max(1, min(int(limit), 256))
            earliest = self._events[0]["sequence"] if self._events else self._sequence + 1
            gap = after_sequence < earliest - 1
            events = [] if gap else [event for event in self._events
                                     if event["sequence"] > after_sequence][:limit]
            return {
                "session_id": self._session_id,
                "revision": self._revision,
                "latest_sequence": self._sequence,
                "earliest_sequence": earliest,
                "resync_required": gap,
                "events": events,
            }
