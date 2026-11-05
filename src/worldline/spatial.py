"""The desktop as observed geometry, without agent-specific interpretations.

This projection never invents compositor stacking, safe activation, workspaces,
or pixel-level visibility from AT-SPI extents.
"""
from __future__ import annotations

from math import isfinite
from typing import Any


def _rect(value: Any) -> dict[str, int] | None:
    if not isinstance(value, dict):
        return None
    try:
        values = {k: value[k] for k in ("x", "y", "width", "height")}
        if any(type(v) not in (int, float) or not isfinite(v) for v in values.values()):
            return None
        result = {k: round(v) for k, v in values.items()}
        return result if result["width"] > 0 and result["height"] > 0 else None
    except KeyError:
        return None


def project_spatial(world: dict[str, Any]) -> dict[str, Any]:
    """A stable, renderer-independent spatial operating frame.

    Keep the full evidence receipts in WORLDLINE's existing query API. This
    bounded projection carries source/freshness summaries beside direct facts.
    """
    desktop = world.get("desktop") or {}
    windows = world.get("windows") or {}
    if not isinstance(desktop, dict):
        desktop = {}
    if not isinstance(windows, dict):
        windows = {}
    monitors = []
    for index, monitor in enumerate((desktop.get("monitors") or windows.get("monitors") or [])[:16]):
        if not isinstance(monitor, dict):
            continue
        frame = _rect(monitor.get("bounds") or monitor)
        if frame is None:
            continue
        monitors.append({
            "id": str(monitor.get("connector") or f"monitor:{monitor.get('index', index)}")[:100],
            "index": monitor.get("index", index),
            "frame": frame,
            "scale": monitor.get("scale", 1),
            "primary": monitor.get("primary") is True,
        })
    items = []
    for item in (windows.get("items") or [])[:128]:
        if not isinstance(item, dict):
            continue
        geometry = item.get("geometry") or {}
        frame = _rect(geometry.get("frame") or item.get("frame"))
        if frame is None:
            continue
        verified = item.get("compositor_verified") is True
        z = item.get("stacking")
        z = z if verified and type(z) is int else None
        focus = item.get("focused")
        ref = str(item.get("stable_id") or "")[:140]
        if not ref:
            continue
        items.append({
            "ref": ref,
            "compositor_id": item.get("compositor_id") if verified else None,
            "pid": item.get("pid") if type(item.get("pid")) is int else None,
            "app": str(item.get("app") or "")[:80],
            "title": str(item.get("title") or "")[:100],
            "frame": frame,
            "z": z,
            "z_verified": z is not None,
            "focused": focus if type(focus) is bool else None,
            "minimized": item.get("minimized") if type(item.get("minimized")) is bool else None,
            "visible": item.get("visible") if type(item.get("visible")) is bool else None,
            "geometry_source": str(geometry.get("frame_source") or item.get("geometry_source") or "unknown")[:100],
            "geometry_verified": verified,
            "activation": {
                "focused_observed": focus if type(focus) is bool else None,
                "safe_target_activation": None,
            },
        })
    # Preserve unknown ordering, rather than assigning invented z values.
    items.sort(key=lambda item: (item["z"] is None, item["z"] if item["z"] is not None else 0, item["ref"]))
    focus = windows.get("focus") if isinstance(windows.get("focus"), dict) else {}
    sources = world.get("sources") or {}
    return {
        "schema": "worldline.spatial-frame/1",
        "revision": world.get("revision"),
        "observed_at": world.get("collected_at"),
        "coordinates": {"unit": "logical_px", "origin": "desktop-top-left", "y": "down"},
        "screen": _rect(desktop.get("screen") or windows.get("screen")),
        "workspace": None,
        "monitors": monitors,
        "windows": items,
        "focus": {
            "window_ref": focus.get("stable_id"),
            "verified": focus.get("verified") is True,
            "source": focus.get("source"),
        },
        "stacking_verified": bool(items) and all(item["z_verified"] for item in items),
        "sources": {
            name: {key: (sources.get(name) or {}).get(key)
                   for key in ("available", "source", "observed_at", "expires_at", "reason")}
            for name in ("desktop", "windows")
        },
    }
