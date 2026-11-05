"""Terminal renderer for the source-labelled spatial operating frame."""
from __future__ import annotations

import argparse
import os
import select
import shutil
import sys
import termios
import tty
import unicodedata
from typing import Any, Callable

from .spatial import project_spatial

SHADES = "░▒▓█"
ACTIVE_BORDER = ("═", "║", "╔", "╗", "╚", "╝")
MONITOR_BORDER = frozenset("┄┆┌┐└┘")


def render_spatial(frame: dict[str, Any], columns: int = 88, rows: int = 32, *,
                   color: bool = False, live: bool = False) -> str:
    """Render a compact, source-conscious desktop dashboard."""
    width = max(28, min(180, columns))
    height = max(12, min(60, rows))
    monitors = [m for m in frame.get("monitors") or []
                if isinstance(m, dict) and isinstance(m.get("frame"), dict)]
    windows = [w for w in frame.get("windows", [])
               if isinstance(w, dict) and isinstance(w.get("frame"), dict)
               and w.get("minimized") is not True
               and w.get("visible") is not False]

    content_width = width - 4

    def display_width(value: str) -> int:
        return sum(0 if unicodedata.combining(ch) else
                   2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
                   for ch in value)

    def safe_text(value: Any, limit: int) -> str:
        result: list[str] = []
        used = 0
        for char in str(value):
            char = char if char.isprintable() else " "
            size = display_width(char)
            if used + size > limit:
                break
            result.append(char)
            used += size
        return "".join(result)

    def box(text: str = "") -> str:
        text = safe_text(text, content_width)
        padding = max(0, content_width - display_width(text))
        return "│ " + text + " " * padding + " │"

    def section(text: str) -> str:
        label = f"─ {safe_text(text, content_width - 2)} "
        return "├" + label + "─" * max(0, width - 2 - display_width(label)) + "┤"

    top = "╭" + "─" * (width - 2) + "╮"
    bottom = "╰" + "─" * (width - 2) + "╯"
    stacking = ("verified" if windows and all(w.get("z_verified") for w in windows)
                else "partial" if any(w.get("z_verified") for w in windows)
                else "unknown")
    status = (f"rev {frame.get('revision', '—')}  ·  {len(monitors)} displays  ·  "
              f"{len(windows)} windows  ·  stacking {stacking}")

    def tint(text: str, code: str) -> str:
        return f"\x1b[{code}m{text}\x1b[0m" if color else text

    lines = [top, tint(box("◈  WORLDLINE  /  GEOMETRY"), "1;38;2;107;229;217"),
             tint(box(status), "38;2;164;185;200")]

    if not monitors:
        lines.extend([
            section("DESKTOP MAP"),
            box(frame.get("notice") or "Monitor layout is unavailable for this observation."),
            box("Window details below use the frame source shown for each item."),
            section("WINDOWS"),
        ])
        detail_limit = max(0, height - 10)
        shown_windows = windows[:detail_limit]
        omitted = len(windows) > len(shown_windows)
        if omitted:
            shown_windows = windows[:max(0, detail_limit - 1)]
        for index, window in enumerate(shown_windows):
            rect = window["frame"]
            marker = "?" if not window.get("z_verified") else "●"
            label = safe_text(window.get("app") or window.get("title") or window.get("ref") or "window", 32)
            source = safe_text(window.get("geometry_source") or "unknown", 20)
            lines.append(box(f"{index + 1:02d} {marker} {label}  ({rect.get('x')}, {rect.get('y')}) "
                             f"{rect.get('width')}×{rect.get('height')}  ·  {source}"))
        if omitted:
            lines.append(box(f"… {len(windows) - len(shown_windows)} more · use --json for all windows"))
        footer = "q quit · retrying observation" if live else "--json  full source-labelled frame"
        lines.extend([box(footer), bottom])
        return "\n".join(lines)

    # Reserve room for a status frame, display summary, legend and a useful
    # number of window rows before choosing the map's height.
    detail_limit = min(len(windows), max(0, (height - 15) // 2))
    shown_windows = windows[:detail_limit]
    omitted = len(windows) > len(shown_windows)
    rectangles = [m["frame"] for m in monitors]
    x0 = min(r["x"] for r in rectangles)
    y0 = min(r["y"] for r in rectangles)
    x1 = max(r["x"] + r["width"] for r in rectangles)
    y1 = max(r["y"] + r["height"] for r in rectangles)
    span_x = max(1, x1 - x0)
    span_y = max(1, y1 - y0)
    def clip_to_desktop(r):
        left, top = max(r["x"], x0), max(r["y"], y0)
        right = min(r["x"] + r["width"], x1)
        bottom = min(r["y"] + r["height"], y1)
        if right <= left or bottom <= top:
            return None
        return {"x": left, "y": top, "width": right - left, "height": bottom - top}

    mapped = [(window, clip_to_desktop(window["frame"])) for window in windows]
    mapped = [(window, frame) for window, frame in mapped if frame is not None]
    uncertain_count = sum(not window.get("geometry_verified") for window, _ in mapped)
    map_notice = uncertain_count > 0
    chart_height = max(1, height - 10 - len(shown_windows) - int(omitted)
                       - int(map_notice))
    canvas = [[" " for _ in range(content_width)] for _ in range(chart_height)]
    usable_width = content_width - 2
    chart_bottom = chart_height - 1
    usable_height = max(1, chart_bottom - 1)
    # Character cells are roughly twice as tall as they are wide.
    scale = min(usable_width / span_x, usable_height * 2 / span_y)

    def to_screen(r):
        x = 1 + round((r["x"] - x0) * scale)
        y = 1 + round((r["y"] - y0) * scale / 2)
        w = max(3, round(r["width"] * scale))
        h = max(2, round(r["height"] * scale / 2))
        return x, y, min(w, content_width - 1 - x), min(h, chart_bottom - y)

    def draw(r, fill, border=None, *, transparent=False, merge=False,
             clip_to_monitors=None):
        x, y, w, h = to_screen(r)
        if w < 2 or h < 2:
            return None
        for yy in range(max(0, y), min(chart_height, y + h)):
            for xx in range(max(0, x), min(content_width, x + w)):
                if clip_to_monitors is not None and not any(
                    mx <= xx < mx + mw and my <= yy < my + mh
                    for mx, my, mw, mh in clip_to_monitors
                ):
                    continue
                is_edge = yy in (y, y + h - 1) or xx in (x, x + w - 1)
                if transparent and not is_edge:
                    continue
                char = fill
                if is_edge and border:
                    if isinstance(border, tuple):
                        top, right = yy == y, xx == x + w - 1
                        bottom, left = yy == y + h - 1, xx == x
                        if top and left:
                            char = border[2]
                        elif top and right:
                            char = border[3]
                        elif bottom and left:
                            char = border[4]
                        elif bottom and right:
                            char = border[5]
                        elif top or bottom:
                            char = border[0]
                        else:
                            char = border[1]
                    else:
                        char = border
                if (merge and canvas[yy][xx] != " "
                        and canvas[yy][xx] not in MONITOR_BORDER):
                    canvas[yy][xx] = "╳"
                elif not transparent or is_edge:
                    canvas[yy][xx] = char
        return x, y, w, h

    monitor_cells = [to_screen(monitor["frame"]) for monitor in monitors]
    for monitor in monitors:
        draw(monitor["frame"], " ", ("┄", "┆", "┌", "┐", "└", "┘"))
    # Clip every frame to the desktop bounds. Unverified AT-SPI extents can be
    # useful for an approximate layout, but the ? outline keeps them distinct
    # from exact compositor frames and the details list preserves provenance.
    ranked = [(w, rect) for w, rect in mapped
              if w.get("geometry_verified") and w.get("z_verified")]
    minimum = min((w["z"] for w, _ in ranked), default=0)
    maximum = max((w["z"] for w, _ in ranked), default=0)
    # Verified windows use outlined frames in observed bottom-to-top order.
    for window, frame_rect in sorted(ranked, key=lambda pair: pair[0]["z"]):
        shade_index = round(3 * (window["z"] - minimum) / max(1, maximum - minimum))
        border = ACTIVE_BORDER if window.get("focused") is True else SHADES[shade_index]
        draw(frame_rect, " ", border, transparent=True, merge=True,
             clip_to_monitors=monitor_cells)
    # Unknown-order frames are transparent outlines. At intersections use a
    # neutral crossing glyph, never an apparent front-to-back relationship.
    uncertain = [(w, rect) for w, rect in mapped
                 if not w.get("geometry_verified") or not w.get("z_verified")]
    for window, frame_rect in uncertain:
        draw(frame_rect, " ", "?", transparent=True, merge=True,
             clip_to_monitors=monitor_cells)

    lines.append(section("DESKTOP MAP"))
    lines.extend(box("".join(row).rstrip()) for row in canvas)
    if color:
        colors = {
            "░": "\x1b[38;2;96;119;139m",
            "▒": "\x1b[38;2;131;154;173m",
            "▓": "\x1b[38;2;175;199;219m",
            "█": "\x1b[38;2;224;240;249m",
            "?": "\x1b[38;2;210;166;109m",
            "┄": "\x1b[38;2;106;132;151m",
            "┆": "\x1b[38;2;106;132;151m",
            "┌": "\x1b[38;2;106;132;151m",
            "┐": "\x1b[38;2;106;132;151m",
            "└": "\x1b[38;2;106;132;151m",
            "┘": "\x1b[38;2;106;132;151m",
            "╳": "\x1b[38;2;226;183;116m",
            "═": "1;38;2;255;208;112m",
            "║": "1;38;2;255;208;112m",
            "╔": "1;38;2;255;208;112m",
            "╗": "1;38;2;255;208;112m",
            "╚": "1;38;2;255;208;112m",
            "╝": "1;38;2;255;208;112m",
        }
        lines = ["".join(colors[ch] + ch + "\x1b[0m" if ch in colors else ch
                          for ch in line) if line.startswith("│ ") else line
                 for line in lines]
    monitor_summaries = []
    for index, monitor in enumerate(monitors):
        rect = monitor["frame"]
        label = safe_text(monitor.get("id") or f"monitor:{index}", 28)
        marker = "★" if monitor.get("primary") else "○"
        monitor_summaries.append(
            f"{marker} M{index} {label}  {rect['width']}×{rect['height']} @ ({rect['x']}, {rect['y']})"
        )
    lines.extend([section("DISPLAYS"), box("   ·   ".join(monitor_summaries))])
    lines.append(section(f"WINDOWS  {len(windows)}"))
    if map_notice:
        lines.append(box(f"? {uncertain_count} frame estimate(s), clipped to screen; source is unverified."))
    for index, window in enumerate(shown_windows):
        frame_rect = window["frame"]
        label = safe_text(window.get("app") or window.get("title") or window.get("ref") or "window", 36)
        title = safe_text(window.get("title") or "", 42)
        x, y = frame_rect.get("x", "?"), frame_rect.get("y", "?")
        w, h = frame_rect.get("width", "?"), frame_rect.get("height", "?")
        source = ("Shell frame" if window.get("geometry_verified")
                  else "AT-SPI extent" if "at-spi" in str(window.get("geometry_source", ""))
                  else safe_text(window.get("geometry_source") or "unknown", 20))
        marker = "●" if window.get("focused") is True else "?" if not window.get("z_verified") else "·"
        title_part = f"  /  {title}" if title and title != label else ""
        z_part = f"z {window.get('z')}" if window.get("z_verified") else "z unknown"
        lines.append(box(f"{index + 1:02d} {marker} {label}{title_part}  "
                         f"({x}, {y}) {w}×{h}  ·  {z_part}  ·  {source}"))
    if omitted:
        lines.append(box(f"… {len(windows) - len(shown_windows)} more · use --json for all windows"))
    footer = ("--json  source-labelled data     q  quit live view" if live else
              "--json  source-labelled data     --live  refresh continuously")
    lines.extend([
        box("█ higher stack   ░ lower stack   ═ active   ? order unknown   ╳ overlap"),
        tint(box(footer), "38;2;164;185;200"),
        bottom,
    ])
    return "\n".join(lines)


def geometry_command(argv: list[str], *, connect: Callable, socket_path: str, dumps: Callable) -> int:
    parser = argparse.ArgumentParser(prog="worldline geometry",
        description="A live, source-labelled view of monitor and window geometry.")
    parser.add_argument("--live", action="store_true", help="refresh the geometry map until q")
    parser.add_argument("--json", action="store_true",
                        help="emit the source-labelled spatial frame as JSON")
    parser.add_argument("--title", action="append", default=[], metavar="TITLE",
                        help="include only windows with this exact title (repeatable)")
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
        result = response.get("result")
        if not isinstance(result, dict) or result.get("schema") != "worldline.spatial-frame/1":
            raise OSError("the running daemon does not support geometry views; restart WORLDLINE")
        if args.title:
            result = {**result, "windows": [
                window for window in result.get("windows", [])
                if isinstance(window, dict) and window.get("title") in args.title
            ]}
        return result

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
                color=sys.stdout.isatty() and not os.environ.get("NO_COLOR")
                and os.environ.get("TERM") != "dumb"))
        return 0

    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        print("worldline geometry --live requires an interactive terminal", file=sys.stderr)
        return 2
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    interval = min(5.0, max(0.1, args.interval))
    try:
        tty.setcbreak(fd)
        # Keep refreshes out of scrollback and leave a safety margin at the
        # terminal edges. Some emulators scroll when a redraw reaches the
        # bottom row or triggers delayed autowrap on the rightmost column.
        sys.stdout.write("\x1b[?1049h\x1b[?7l\x1b[?25l\x1b[2J\x1b[H")
        while True:
            try:
                frame = read()
                size = shutil.get_terminal_size((88, 32))
                columns = max(28, size.columns - 1)
                rows = max(12, size.lines - 2)
                display = render_spatial(frame, columns, rows,
                    color=not os.environ.get("NO_COLOR")
                    and os.environ.get("TERM") != "dumb", live=True)
            except OSError as exc:
                size = shutil.get_terminal_size((88, 32))
                columns = max(28, size.columns - 1)
                rows = max(12, size.lines - 2)
                display = render_spatial({"revision": "offline", "monitors": [],
                    "windows": [], "notice": f"Observation unavailable: {exc}"},
                    columns, rows,
                    color=not os.environ.get("NO_COLOR")
                    and os.environ.get("TERM") != "dumb", live=True)
            sys.stdout.write("\x1b[H\x1b[2J\x1b[0m" + display)
            sys.stdout.flush()
            ready, _, _ = select.select([sys.stdin], [], [], interval)
            if ready and sys.stdin.read(1).lower() == "q":
                break
    except KeyboardInterrupt:
        pass
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
        sys.stdout.write("\x1b[?7h\x1b[?25h\x1b[0m\x1b[?1049l")
        sys.stdout.flush()
    return 0
