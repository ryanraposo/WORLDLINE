"""Terminal renderer for the source-labelled spatial operating frame."""
from __future__ import annotations

import argparse
import os
import select
import shutil
import sys
import termios
import time
import tty
from math import ceil
from typing import Any, Callable

from .spatial import project_spatial

SHADES = "░▒▓█"


def render_spatial(frame: dict[str, Any], columns: int = 88, rows: int = 32, *,
                   color: bool = False) -> str:
    """Pure visual projection, suitable for CLI output and snapshot tests."""
    width = max(28, min(180, columns))
    height = max(12, min(60, rows))
    canvas = [[" " for _ in range(width)] for _ in range(height)]
    monitors = frame.get("monitors") or []
    rectangles = [m["frame"] for m in monitors if isinstance(m.get("frame"), dict)]
    if not rectangles:
        return "WORLDLINE / GEOMETRY\n  Monitor geometry unavailable\n  Window details: worldline windows.items"
    x0 = min(r["x"] for r in rectangles)
    y0 = min(r["y"] for r in rectangles)
    x1 = max(r["x"] + r["width"] for r in rectangles)
    y1 = max(r["y"] + r["height"] for r in rectangles)
    span_x = max(1, x1 - x0)
    span_y = max(1, y1 - y0)
    usable_width = width - 4
    usable_height = height - 7
    # Character cells are roughly twice as tall as they are wide.
    scale = min(usable_width / span_x, usable_height * 2 / span_y)
    def to_screen(r):
        x = 2 + round((r["x"] - x0) * scale)
        y = 3 + round((r["y"] - y0) * scale / 2)
        w = max(3, round(r["width"] * scale))
        h = max(2, round(r["height"] * scale / 2))
        return x, y, min(w, width - 2 - x), min(h, height - 5 - y)
    def draw(r, fill, border=None):
        x, y, w, h = to_screen(r)
        if w < 2 or h < 2:
            return None
        for yy in range(max(0, y), min(height, y + h)):
            for xx in range(max(0, x), min(width, x + w)):
                is_edge = yy in (y, y + h - 1) or xx in (x, x + w - 1)
                canvas[yy][xx] = border if is_edge and border else fill
        return x, y, w, h
    def title(window, box):
        if not box:
            return
        x, y, w, h = box
        if w < 12 or h < 4:
            return
        label = (window.get("app") or window.get("title") or window.get("ref") or "window")
        tag = f"{'● ' if window.get('focused') else ''}{str(label)[:w - 4]}"
        for delta, char in enumerate(tag):
            xx = x + 2 + delta
            if 0 <= y + 1 < height and 0 <= xx < width:
                canvas[y + 1][xx] = char
    for monitor in monitors:
        draw(monitor["frame"], "·", "╎")
    visible_windows = [w for w in frame.get("windows", []) if w.get("minimized") is not True]
    ranked = [w for w in visible_windows if w.get("z_verified")]
    minimum = min((w["z"] for w in ranked), default=0)
    maximum = max((w["z"] for w in ranked), default=0)
    # Unknown-order windows are unfilled outlines; they cannot be layered
    # as if their observation proved a stacking position.
    for window in (w for w in visible_windows if not w.get("z_verified")):
        title(window, draw(window["frame"], " ", "?"))
    for window in sorted(ranked, key=lambda w: w["z"]):
        shade_index = round(3 * (window["z"] - minimum) / max(1, maximum - minimum))
        title(window, draw(window["frame"], SHADES[shade_index],
             "▣" if window.get("focused") else SHADES[shade_index]))
    header = "WORLDLINE  /  GEOMETRY"
    details = f"rev {frame.get('revision', '—')}  ·  {len(monitors)} monitors  ·  {len(frame.get('windows', []))} windows"
    for col, ch in enumerate(header[:width]):
        canvas[0][col] = ch
    for col, ch in enumerate(details[:width]):
        canvas[1][col] = ch
    legend = "z: ░ low  ▒  ▓  █ high    ?: unverified stacking    ▣: focused"
    footer = "q quit (live)  ·  --json exact data"
    for col, ch in enumerate(legend[:width]):
        canvas[-2][col] = ch
    for col, ch in enumerate(footer[:width]):
        canvas[-1][col] = ch
    # Give the layout stable, legible monitor labels.
    for index, monitor in enumerate(monitors):
        x, y, w, h = to_screen(monitor["frame"])
        tag = f"M{index} {monitor['frame']['width']}×{monitor['frame']['height']}"
        for delta, ch in enumerate(tag[:max(0, w - 1)]):
            if 0 <= y < height and 0 <= x + delta < width:
                canvas[y][x + delta] = ch
    lines = ["".join(row).rstrip() for row in canvas]
    if color:
        colors = {
            "░": "\x1b[38;2;96;119;139m",
            "▒": "\x1b[38;2;131;154;173m",
            "▓": "\x1b[38;2;175;199;219m",
            "█": "\x1b[38;2;224;240;249m",
            "?": "\x1b[38;2;210;166;109m",
            "▣": "\x1b[38;2;107;229;217m",
            "╎": "\x1b[38;2;106;132;151m",
        }
        for index, line in enumerate(lines):
            if index == 0:
                lines[index] = "\x1b[1;38;2;107;229;217m" + line + "\x1b[0m"
                continue
            lines[index] = "".join(colors[ch] + ch + "\x1b[0m" if ch in colors else ch
                                   for ch in line)
    return "\n".join(lines)


def geometry_command(argv: list[str], *, connect: Callable, socket_path: str, dumps: Callable) -> int:
    parser = argparse.ArgumentParser(prog="worldline geometry",
        description="Observe monitor and window geometry with verified z-order.")
    parser.add_argument("--live", action="store_true", help="refresh the geometry map until q")
    parser.add_argument("--json", action="store_true", help="emit the exact spatial frame as JSON")
    parser.add_argument("--socket", default=None)
    parser.add_argument("--interval", type=float, default=0.45, help="live refresh in seconds")
    args = parser.parse_args(argv)
    if args.live and args.json:
        parser.error("--live and --json are mutually exclusive")
    socket_path = args.socket or socket_path

    def read():
        response = connect(socket_path, "query", {"view": "geometry", "fresh": args.live})
        if not response.get("ok"):
            issue = response.get("error") or {}
            raise OSError(str(issue.get("message") or issue.get("code") or "geometry unavailable"))
        return response["result"]

    if not args.live:
        try:
            frame = read()
        except OSError as exc:
            print(f"worldline geometry: {exc}", file=sys.stderr)
            return 3
        if args.json:
            print(dumps(frame))
        else:
            size = shutil.get_terminal_size((88, 32))
            print(render_spatial(frame, size.columns, size.lines,
                color=sys.stdout.isatty() and not os.environ.get('NO_COLOR')))
        return 0

    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        print("worldline geometry --live requires an interactive terminal", file=sys.stderr)
        return 2
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    interval = min(5.0, max(0.1, args.interval))
    try:
        tty.setcbreak(fd)
        sys.stdout.write("\x1b[?25l\x1b[2J")
        while True:
            try:
                frame = read()
                size = shutil.get_terminal_size((88, 32))
                display = render_spatial(frame, size.columns, size.lines,
                    color=not os.environ.get('NO_COLOR'))
            except OSError as exc:
                display = f"WORLDLINE / GEOMETRY\nObservation unavailable: {exc}\nPress q to quit."
            sys.stdout.write("\x1b[H\x1b[J" + display + "\n")
            sys.stdout.flush()
            ready, _, _ = select.select([sys.stdin], [], [], interval)
            if ready and sys.stdin.read(1).lower() == "q":
                break
    except KeyboardInterrupt:
        pass
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
        sys.stdout.write("\x1b[?25h\x1b[0m\n")
        sys.stdout.flush()
    return 0
