"""Optional, general GNOME Shell window observation over read-only D-Bus.

The platform reports native properties. No ownership, logical grouping,
object identity, or occlusion relationships are inferred by this provider.
"""
from __future__ import annotations

import ast
import json
import math
import subprocess
from time import time
from typing import Callable, Iterable

from worldline.model import Evidence, Fact
from .base import ObservationProvider

DESTINATION = "org.worldline.GnomeObserver"
OBJECT_PATH = "/org/worldline/GnomeObserver"
METHOD = "org.worldline.GnomeObserver1.GetSnapshot"
SNAPSHOT_KEY = "gnome.windows.snapshot"
SOURCE_KEY = "gnome.windows.source.available"
SOURCE = "gnome-shell:org.worldline.GnomeObserver1.GetSnapshot"
MAX_REPLY = 262_144
MAX_WINDOWS = 256
WINDOW_FIELDS = (
    "gtk_app_id", "wm_class", "wm_class_instance", "title", "title_truncated",
    "reported_pid", "transient_for", "frame", "monitor", "workspace",
    "minimized", "showing_on_workspace", "focused", "fullscreen", "above",
    "window_type", "actor_present", "actor_visible", "enumeration_index",
    "stack_index",
)


def _optional_string(value: object, limit: int = 512) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or len(value) > limit:
        raise ValueError("invalid string field in observed window")
    return value


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    if type(value) is not int or abs(value) > 10_000_000:
        raise ValueError("invalid integer field in observed window")
    return value


def _optional_bool(value: object) -> bool | None:
    if value is None:
        return None
    if type(value) is not bool:
        raise ValueError("invalid boolean field in observed window")
    return value


def _window(value: object) -> dict:
    if not isinstance(value, dict):
        raise ValueError("window record is not an object")
    ref = _optional_string(value.get("id"), 80)
    if not ref:
        raise ValueError("window has no native reference")
    bounds = value.get("frame")
    if bounds is not None:
        if not isinstance(bounds, dict):
            raise ValueError("window has invalid frame")
        bounds = {key: _optional_int(bounds.get(key)) for key in ("x", "y", "width", "height")}
        if any(number is None for number in bounds.values()):
            raise ValueError("window frame is incomplete")
        if bounds["width"] < 0 or bounds["height"] < 0:
            raise ValueError("window frame has negative size")

    return {
        "id": ref,
        "gtk_app_id": _optional_string(value.get("gtk_app_id"), 160),
        "wm_class": _optional_string(value.get("wm_class"), 160),
        "wm_class_instance": _optional_string(value.get("wm_class_instance"), 160),
        "title": _optional_string(value.get("title")),
        "title_truncated": _optional_bool(value.get("title_truncated")),
        "reported_pid": _optional_int(value.get("reported_pid")),
        # A Meta.Window.get_transient_for result: not a claim of common identity.
        "transient_for": _optional_string(value.get("transient_for"), 80),
        "frame": bounds,
        "monitor": _optional_int(value.get("monitor")),
        "workspace": _optional_int(value.get("workspace")),
        **{key: _optional_bool(value.get(key)) for key in
           ("minimized", "showing_on_workspace", "focused", "fullscreen",
            "above", "actor_present", "actor_visible")},
        "window_type": _optional_int(value.get("window_type")),
        "enumeration_index": _optional_int(value.get("enumeration_index")),
        "stack_index": _optional_int(value.get("stack_index")),
    }


def decode_snapshot(output: str, *, now: float | None = None) -> dict:
    """Decode the gdbus-call (s) tuple, reject malformed/stale/mixed records."""
    if len(output) > MAX_REPLY:
        raise ValueError("observer response exceeds limit")
    tuple_result = ast.literal_eval(output.strip())
    if not (isinstance(tuple_result, tuple) and len(tuple_result) == 1
            and isinstance(tuple_result[0], str)):
        raise ValueError("expected GVariant single-string tuple")
    payload = json.loads(tuple_result[0])
    if not isinstance(payload, dict) or payload.get("schema") != 1:
        raise ValueError("unknown observer schema")
    generation = _optional_string(payload.get("generation"), 128)
    if not generation:
        raise ValueError("missing compositor generation")
    at = payload.get("observed_at")
    current = time() if now is None else now
    if type(at) not in (int, float) or not math.isfinite(at) or abs(at - current) > 10:
        raise ValueError("observation timestamp is stale or implausible")
    items = payload.get("windows")
    if not isinstance(items, list) or len(items) > MAX_WINDOWS:
        raise ValueError("invalid number of window records")
    order_source = payload.get("order_source")
    if order_source not in ("meta-display-stacking", "actor-enumeration"):
        raise ValueError("unsupported window ordering evidence")
    windows = [_window(item) for item in items]
    ids = [item["id"] for item in windows]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate native window references")
    total = payload.get("total_windows")
    truncated = payload.get("truncated")
    if type(total) is not int or total < len(windows) or type(truncated) is not bool:
        raise ValueError("invalid completeness metadata")
    if truncated != (total > len(windows)):
        raise ValueError("inconsistent truncation metadata")
    if order_source != "meta-display-stacking" and any(
        item["stack_index"] is not None for item in windows
    ):
        raise ValueError("unproven stacking order")
    return {
        "generation": generation,
        "observed_at": at,
        "order_source": order_source,
        "total_windows": total,
        "truncated": truncated,
        "windows": windows,
    }


class GNOMEWindowsProvider(ObservationProvider):
    """General compositor observation; no project/application-specific logic."""

    name = "gnome-windows"
    # When a fresh observation cannot be read, the old native snapshot is
    # removed immediately rather than trusted until a TTL happens to expire.
    managed_keys = (SNAPSHOT_KEY, SOURCE_KEY)

    def __init__(self, *, runner: Callable = subprocess.run, clock: Callable = time):
        self._run = runner
        self._clock = clock

    def observe(self) -> Iterable[Fact]:
        now = self._clock()
        receipt = Evidence(
            source="session-dbus",
            observed_at=now,
            expires_at=now + 5,
            detail={"destination": DESTINATION, "method": METHOD},
        )
        args = [
            "gdbus", "call", "--session", "--dest", DESTINATION,
            "--object-path", OBJECT_PATH, "--method", METHOD,
        ]
        try:
            process = self._run(
                args, capture_output=True, text=True, timeout=1.5, check=False,
            )
            if process.returncode:
                return [Fact(SOURCE_KEY, False, receipt)]
            snapshot = decode_snapshot(process.stdout, now=now)
        except (OSError, subprocess.TimeoutExpired, ValueError, SyntaxError,
                TypeError, OverflowError, json.JSONDecodeError):
            return [Fact(SOURCE_KEY, False, receipt)]

        generation = snapshot["generation"]
        return [
            Fact(SOURCE_KEY, True, receipt),
            Fact(
                SNAPSHOT_KEY, snapshot,
                Evidence(
                    source=SOURCE, observed_at=snapshot["observed_at"],
                    expires_at=now + 5,
                    detail={"generation": generation, "transport": "session-dbus"},
                ),
                tags=("windows", "native-observation"),
            ),
        ]
