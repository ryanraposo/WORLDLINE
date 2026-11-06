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


def _fit_canvas(bounds: dict[str, int], max_width: int,
                max_height: int) -> tuple[int, int]:
    """Fit desktop bounds to terminal cells (about twice as tall as wide)."""
    scale = min(max_width / max(1, bounds["width"]),
                max_height * 2 / max(1, bounds["height"]))
    return (max(2, min(max_width, round(bounds["width"] * scale))),
            max(2, min(max_height, round(bounds["height"] * scale / 2))))



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
    workspaces = frame.get("workspace") if isinstance(frame.get("workspace"), dict) else None
    workspace_count = workspaces.get("count") if workspaces else None
    active_workspace = workspaces.get("active") if workspaces else None
    workspace_known = (type(workspace_count) is int and workspace_count > 0
                       and type(active_workspace) is int
                       and 0 <= active_workspace < workspace_count)
    uncertain_count = sum(not window.get("geometry_verified") for window in windows)
    map_notice = uncertain_count > 0
    bounds = monitors[0]["frame"]
    for monitor in monitors[1:]:
        rect = monitor["frame"]
        left, min_y = min(bounds["x"], rect["x"]), min(bounds["y"], rect["y"])
        right = max(bounds["x"] + bounds["width"], rect["x"] + rect["width"])
        max_y = max(bounds["y"] + bounds["height"], rect["y"] + rect["height"])
        bounds = {"x": left, "y": min_y, "width": right-left, "height": max_y-min_y}

    card_width = max(24, min(42, (content_width - 2) // 2))
    card_columns = max(1, (content_width + 2) // (card_width + 2))
    if workspace_known:
        cards = [(index, index == active_workspace) for index in range(workspace_count)]
    else:
        cards = [(None, True)]
    card_row_count = (len(cards) + card_columns - 1) // card_columns
    map_budget = max(card_row_count * 5,
                     height - 10 - len(shown_windows) - int(omitted)
                     - int(map_notice))
    max_card_height = max(2, map_budget // card_row_count - 3)
    canvas_width, canvas_height = _fit_canvas(bounds, card_width - 6,
                                               max_card_height)
    card_rows: list[str] = []
    for start in range(0, len(cards), card_columns):
        row_cards = cards[start:start + card_columns]
        rendered_cards: list[list[str]] = []
        for workspace_index, active in row_cards:
            label = (f"{'> ' if active else '  '}DESKTOP {workspace_index + 1}"
                     if workspace_index is not None else "  WORKSPACE ?")
            title = safe_text(label, card_width - 2).ljust(card_width - 2)
            mini_w, mini_h = canvas_width, canvas_height
            mini = [[" " for _ in range(mini_w)] for _ in range(mini_h)]
            for yy in range(mini_h):
                for xx in range(mini_w):
                    if yy in (0, mini_h - 1):
                        mini[yy][xx] = "─"
                    elif xx in (0, mini_w - 1):
                        mini[yy][xx] = "│"
            matching = []
            for window in windows:
                if workspace_index is None:
                    if window.get("visible") is not False:
                        matching.append(window)
                elif window.get("sticky") is True:
                    if active:
                        matching.append(window)
                elif window.get("workspace") == workspace_index:
                    matching.append(window)
            # Frame outlines are deliberately simple and uniform. Only focus
            # gets a distinctive double-line border.
            for window in matching:
                rect = window["frame"]
                left = max(rect["x"], bounds["x"])
                top_edge = max(rect["y"], bounds["y"])
                right = min(rect["x"] + rect["width"],
                            bounds["x"] + bounds["width"])
                lower = min(rect["y"] + rect["height"],
                            bounds["y"] + bounds["height"])
                if right <= left or lower <= top_edge:
                    continue
                sx = max(0, min(mini_w - 1, round(
                    (left - bounds["x"]) / max(1, bounds["width"])
                    * (mini_w - 1))))
                sy = max(0, min(mini_h - 1, round(
                    (top_edge - bounds["y"]) / max(1, bounds["height"])
                    * (mini_h - 1))))
                ex = max(sx + 1, min(mini_w - 1, round(
                    (right - bounds["x"]) / max(1, bounds["width"])
                    * (mini_w - 1))))
                ey = max(sy + 1, min(mini_h - 1, round(
                    (lower - bounds["y"]) / max(1, bounds["height"])
                    * (mini_h - 1))))
                border = "?" if not window.get("geometry_verified") else "═" if window.get("focused") else "─"
                for xx in range(sx, ex + 1):
                    mini[sy][xx] = mini[ey][xx] = border
                for yy in range(sy, ey + 1):
                    mini[yy][sx] = mini[yy][ex] = "║" if border == "═" else "?" if border == "?" else "│"
            pad_left = (card_width - 6 - mini_w) // 2
            pad_right = card_width - 6 - mini_w - pad_left
            card = ["┌" + "─" * (card_width - 2) + "┐",
                    "│" + title + "│"]
            card.extend("│  " + " " * pad_left + "".join(line)
                        + " " * pad_right + "  │" for line in mini)
            card.append("└" + "─" * (card_width - 2) + "┘")
            rendered_cards.append(card)
        for line_index in range(max(len(card) for card in rendered_cards)):
            card_rows.append("  ".join(card[line_index] for card in rendered_cards))

    lines.append(section("DESKTOP MAP"))
    lines.extend(box(line) for line in card_rows)
    if color:
        colors = {
            "?": "\x1b[38;2;210;166;109m",
            "═": "\x1b[1;38;2;255;208;112m",
            "║": "\x1b[1;38;2;255;208;112m",
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
        box("═ focused window   ─ other verified window   ? estimated frame   > active workspace"),
        tint(box(footer), "38;2;164;185;200"),
    ])
    while len(lines) < height - 1:
        lines.append(box())
    lines.append(bottom)
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
