"""Pure geometry for canonical desktop windows.

The compositor reports window frames in the logical desktop coordinate space
used by Mutter: one unit is one logical pixel, the origin is the top-left of the
desktop, and ``y`` grows downward.  This module never guesses a window's
identity or visibility state; it only describes rectangles against the display
layout and against higher windows in the compositor's stacking order.
"""

from __future__ import annotations

from math import gcd
from typing import Any, Iterable, Mapping, Sequence


def rect(x: float, y: float, width: float, height: float) -> dict[str, int]:
    return {
        "x": int(x),
        "y": int(y),
        "width": int(width),
        "height": int(height),
    }


def from_rect(value: Mapping[str, Any]) -> dict[str, int]:
    return rect(value["x"], value["y"], value["width"], value["height"])


def area(value: Mapping[str, Any]) -> int:
    return max(0, int(value["width"])) * max(0, int(value["height"]))


def right(value: Mapping[str, Any]) -> int:
    return int(value["x"]) + int(value["width"])


def bottom(value: Mapping[str, Any]) -> int:
    return int(value["y"]) + int(value["height"])


def center(value: Mapping[str, Any]) -> dict[str, float]:
    return {
        "x": round(int(value["x"]) + int(value["width"]) / 2, 3),
        "y": round(int(value["y"]) + int(value["height"]) / 2, 3),
    }


def intersection(
    first: Mapping[str, Any], second: Mapping[str, Any]
) -> dict[str, int] | None:
    left = max(int(first["x"]), int(second["x"]))
    top = max(int(first["y"]), int(second["y"]))
    width = min(right(first), right(second)) - left
    height = min(bottom(first), bottom(second)) - top
    if width <= 0 or height <= 0:
        return None
    return rect(left, top, width, height)


def union(rectangles: Iterable[Mapping[str, Any]]) -> dict[str, int] | None:
    items = [from_rect(item) for item in rectangles]
    if not items:
        return None
    left = min(item["x"] for item in items)
    top = min(item["y"] for item in items)
    width = max(right(item) for item in items) - left
    height = max(bottom(item) for item in items) - top
    return rect(left, top, width, height)


def _fraction(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 6)


def screen_bounds(
    monitors: Sequence[Mapping[str, Any]], screen: Mapping[str, Any] | None = None
) -> dict[str, int] | None:
    if screen is not None:
        return from_rect(screen)
    return union(monitors)


def _monitor_bounds(monitor: Mapping[str, Any]) -> dict[str, int]:
    if isinstance(monitor.get("bounds"), Mapping):
        return from_rect(monitor["bounds"])  # type: ignore[arg-type]
    return rect(monitor["x"], monitor["y"], monitor["width"], monitor["height"])


def monitor_for(
    frame: Mapping[str, Any], monitors: Sequence[Mapping[str, Any]]
) -> tuple[Mapping[str, Any] | None, int]:
    """Return the monitor containing the largest part of ``frame``."""

    best: Mapping[str, Any] | None = None
    best_area = 0
    for monitor in monitors:
        overlap = intersection(frame, _monitor_bounds(monitor))
        overlap_area = area(overlap) if overlap else 0
        if overlap_area > best_area:
            best = monitor
            best_area = overlap_area
    if best is not None and best_area > 0:
        return best, best_area

    # A fully off-screen window still belongs to the nearest monitor.
    if monitors:
        point = center(frame)
        nearest = min(
            monitors,
            key=lambda monitor: (
                abs(point["x"] - (monitor["x"] + monitor["width"] / 2))
                + abs(point["y"] - (monitor["y"] + monitor["height"] / 2))
            ),
        )
        return nearest, 0
    return None, 0


def _public_monitor(monitor: Mapping[str, Any], index: int) -> dict[str, Any]:
    bounds = _monitor_bounds(monitor)
    result: dict[str, Any] = {
        "index": int(monitor.get("index", index)),
        "bounds": bounds,
        "x": bounds["x"],
        "y": bounds["y"],
        "width": bounds["width"],
        "height": bounds["height"],
        "primary": bool(monitor.get("primary", False)),
        "scale": float(monitor.get("scale", 1.0)),
        "transform": int(monitor.get("transform", 0)),
    }
    for key in ("connector", "connectors", "name", "mode", "refresh_hz"):
        if key in monitor:
            result[key] = monitor[key]
    if result.get("connector") is None and result.get("connectors"):
        result["connector"] = result["connectors"][0]
    return result


def _gcd_size(width: int, height: int) -> tuple[int, int] | None:
    if width <= 0 or height <= 0:
        return None
    divisor = gcd(width, height)
    return width // divisor, height // divisor


def _exposure(
    frame: Mapping[str, int], occluders: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    """Estimate how much of ``frame`` remains visible.

    This is deliberately a rectangle model.  It is useful for reasoning about
    stacking and off-screen clipping, not a pixel-accurate alpha or shape mask.
    """

    if area(frame) <= 0:
        return {
            "exposed_fraction": 0.0,
            "exposed_area": 0,
            "occluded_area": 0,
            "topmost": False,
            "method": "frame_rectangles",
        }

    clips = [
        overlap
        for item in occluders
        if (overlap := intersection(frame, item)) is not None
    ]
    if not clips:
        return {
            "exposed_fraction": 1.0,
            "exposed_area": area(frame),
            "occluded_area": 0,
            "topmost": True,
            "method": "frame_rectangles",
        }

    xs = sorted(
        {frame["x"], right(frame)}
        | {clip["x"] for clip in clips}
        | {right(clip) for clip in clips}
    )
    ys = sorted(
        {frame["y"], bottom(frame)}
        | {clip["y"] for clip in clips}
        | {bottom(clip) for clip in clips}
    )
    exposed = 0
    for x1, x2 in zip(xs, xs[1:]):
        if x2 <= x1:
            continue
        for y1, y2 in zip(ys, ys[1:]):
            if y2 <= y1:
                continue
            cell = rect(x1, y1, x2 - x1, y2 - y1)
            if not any(intersection(cell, clip) is not None for clip in clips):
                exposed += area(cell)

    total = area(frame)
    return {
        "exposed_fraction": _fraction(exposed, total),
        "exposed_area": exposed,
        "occluded_area": max(0, total - exposed),
        "topmost": False,
        "method": "frame_rectangles",
    }


def describe(
    frame: Mapping[str, Any],
    *,
    monitors: Sequence[Mapping[str, Any]] = (),
    screen: Mapping[str, Any] | None = None,
    buffer_origin: Mapping[str, Any] | None = None,
    occluders: Sequence[Mapping[str, Any]] = (),
    z_index: int | None = None,
) -> dict[str, Any]:
    """Describe one window frame against the display and stacking order."""

    window = from_rect(frame)
    display = screen_bounds(monitors, screen)
    result: dict[str, Any] = {
        "coordinate_space": "desktop-logical-px",
        "frame": window,
        "size": {"width": window["width"], "height": window["height"]},
        "area": area(window),
        "center": center(window),
    }

    ratio = _gcd_size(window["width"], window["height"])
    if ratio is not None:
        result["aspect_ratio"] = f"{ratio[0]}:{ratio[1]}"
        result["aspect_value"] = round(window["width"] / window["height"], 6)

    if buffer_origin is not None:
        buffer_x = int(buffer_origin["x"])
        buffer_y = int(buffer_origin["y"])
        result["buffer"] = {
            "x": buffer_x,
            "y": buffer_y,
            "offset_x": buffer_x - window["x"],
            "offset_y": buffer_y - window["y"],
        }

    if display is not None:
        visible = intersection(window, display)
        visible_area = area(visible) if visible else 0
        result["screen"] = display
        result["on_screen"] = visible is not None
        result["visible_rect"] = visible or rect(
            max(window["x"], display["x"]),
            max(window["y"], display["y"]),
            0,
            0,
        )
        result["visible_area"] = visible_area
        result["visible_fraction"] = _fraction(visible_area, area(window))
        result["fully_on_screen"] = visible_area == area(window) and area(window) > 0
        result["offscreen"] = {
            "left": max(0, display["x"] - window["x"]),
            "top": max(0, display["y"] - window["y"]),
            "right": max(0, right(window) - right(display)),
            "bottom": max(0, bottom(window) - bottom(display)),
        }
        result["edges"] = {
            "left": window["x"] - display["x"],
            "top": window["y"] - display["y"],
            "right": right(display) - right(window),
            "bottom": bottom(display) - bottom(window),
        }

    monitor, covered = monitor_for(window, monitors)
    if monitor is not None:
        index = next(
            (position for position, item in enumerate(monitors) if item is monitor),
            0,
        )
        public = _public_monitor(monitor, index)
        bounds = _monitor_bounds(monitor)
        overlap = intersection(window, bounds)
        result["monitor"] = public
        result["monitor_relative"] = rect(
            window["x"] - bounds["x"],
            window["y"] - bounds["y"],
            window["width"],
            window["height"],
        )
        result["on_monitor"] = overlap is not None
        result["monitor_coverage"] = _fraction(covered, area(window))
        result["monitor_visible_fraction"] = _fraction(
            area(overlap) if overlap else 0, area(window)
        )
        scale = public["scale"]
        if scale > 0:
            result["device_pixels"] = rect(
                round((window["x"] - bounds["x"]) * scale),
                round((window["y"] - bounds["y"]) * scale),
                round(window["width"] * scale),
                round(window["height"] * scale),
            )

        intersections: list[dict[str, Any]] = []
        for position, candidate in enumerate(monitors):
            candidate_bounds = _monitor_bounds(candidate)
            overlap = intersection(window, candidate_bounds)
            if overlap is None:
                continue
            candidate_public = _public_monitor(candidate, position)
            intersections.append(
                {
                    "index": candidate_public["index"],
                    "connector": candidate_public.get("connector"),
                    "intersection": overlap,
                    "fraction": _fraction(area(overlap), area(window)),
                }
            )
        result["monitor_intersections"] = intersections
        result["spans_monitors"] = len(intersections) > 1

    result["exposure"] = _exposure(window, occluders)
    result["exposure"]["occlusion_known"] = z_index is not None
    if z_index is not None:
        # WinRects numbers windows from the bottom of the stack (0) upward.
        result["exposure"]["stacking_index"] = int(z_index)
        result["exposure"]["stacking_order"] = "bottom-to-top"
    else:
        # Without a compositor stack there is no evidence for a topmost claim.
        result["exposure"]["topmost"] = None
    return result


def rect_distance(first: Mapping[str, Any], second: Mapping[str, Any]) -> int:
    """Manhattan distance between rectangle centres, used for fuzzy matching."""

    a = center(first)
    b = center(second)
    return round(abs(a["x"] - b["x"]) + abs(a["y"] - b["y"]))


def overlap_fraction(first: Mapping[str, Any], second: Mapping[str, Any]) -> float:
    overlap = intersection(first, second)
    if overlap is None:
        return 0.0
    base = min(area(first), area(second))
    return _fraction(area(overlap), base)
