from worldline.spatial import project_spatial
from worldline.geometry_cli import render_spatial


def sample():
    return {"revision": 5, "collected_at": 100,
        "desktop": {"screen": {"x": -1280, "y": 0, "width": 3200, "height": 1080},
            "monitors": [{"index": 0, "x": -1280, "y": 0, "width": 1280,
                "height": 800, "scale": 1.25, "connector": "HDMI-1"},
                {"index": 1, "x": 0, "y": 0, "width": 1920,
                    "height": 1080, "connector": "eDP-1"}]},
        "windows": {"items": [
            {"stable_id": "window:100:3", "compositor_id": 3,
                "compositor_verified": True, "stacking": 2, "focused": True,
                "title": "Editor", "geometry": {
                    "frame": {"x": -600, "y": 20, "width": 1100, "height": 680},
                    "frame_source": "worldline-gnome-shell-frame"}},
            {"stable_id": "window:101:4", "stacking": None,
                "title": "Terminal", "geometry": {
                    "frame": {"x": 80, "y": 200, "width": 800, "height": 480},
                    "frame_source": "at-spi2-component-extents"}},
        ], "focus": {"stable_id": "window:100:3", "verified": True,
            "source": "worldline-gnome-shell"}},
        "sources": {"windows": {"available": True, "source": "test",
            "observed_at": 90, "expires_at": 110},
            "desktop": {"available": True, "source": "gnome-dbus",
                "observed_at": 90, "expires_at": 110}}}


def test_spatial_has_signed_monitor_coordinates_and_verified_stack():
    view = project_spatial(sample())
    assert view["schema"] == "worldline.spatial-frame/1"
    assert view["monitors"][0]["frame"]["x"] == -1280
    assert view["windows"][0]["z"] == 2
    assert view["windows"][1]["z"] is None
    assert view["windows"][1]["geometry_verified"] is False
    assert view["windows"][0]["activation"]["safe_target_activation"] is None
    assert view["workspace"] is None
    assert view["focus"]["verified"] is True


def test_terminal_frame_scales_and_clips_unverified_extents_with_warning():
    output = render_spatial(project_spatial(sample()), columns=100, rows=30, live=True)
    assert "WORLDLINE  /  GEOMETRY" in output
    assert "M0 " in output and "M1 " in output
    assert "?" in output and ("▓" in output or "█" in output)
    assert "q  quit live view" in output
    assert "02 ? Terminal" in output
    assert "frame estimate(s), clipped to screen; source is unverified." in output
    map_area = output.split("DESKTOP MAP", 1)[1].split("DISPLAYS", 1)[0]
    assert "?" in map_area
    assert len(output.splitlines()) == 30
    assert all(len(line) == 100 for line in output.splitlines())


def test_verified_frames_are_outlines_with_bright_active_border_and_screen_clip():
    world = sample()
    world["windows"]["items"] = [{
        "stable_id": "window:100:3", "compositor_id": 3,
        "compositor_verified": True, "stacking": 2, "focused": True,
        "title": "Fullscreen", "visible": True,
        "geometry": {"frame": {"x": -1280, "y": 0, "width": 3200, "height": 1080},
                     "frame_source": "worldline-gnome-shell-frame"},
    }]
    output = render_spatial(project_spatial(world), columns=100, rows=30)
    map_area = output.split("DESKTOP MAP", 1)[1].split("DISPLAYS", 1)[0]
    assert "═" in map_area
    assert "█" not in map_area
    assert "╔" in map_area and "╝" in map_area


def test_terminal_geometry_hides_windows_from_other_workspaces():
    world = sample()
    world["windows"]["items"][0]["visible"] = True
    world["windows"]["items"][1]["visible"] = False
    output = render_spatial(project_spatial(world), columns=100, rows=30)
    assert "01" in output
    assert "Terminal" not in output
    assert "WINDOWS  1" in output


def test_overlapping_window_labels_are_separate_and_terminal_safe():
    world = sample()
    world["windows"]["items"][1]["app"] = "\x1b[31mBad\nName"
    output = render_spatial(project_spatial(world), columns=100, rows=30)
    assert "\x1b" not in output
    assert "Bad Name" in output
    assert "╳" in output


def test_unicode_labels_keep_panel_columns_aligned():
    import unicodedata

    world = sample()
    world["windows"]["items"][1]["app"] = "東京"
    output = render_spatial(project_spatial(world), columns=100, rows=30)
    for line in output.splitlines():
        columns = sum(0 if unicodedata.combining(char) else
                      2 if unicodedata.east_asian_width(char) in ("W", "F") else 1
                      for char in line)
        assert columns == 100

def test_live_map_quits_on_q_and_restores_terminal(monkeypatch):
    import io
    import os
    from worldline import geometry_cli

    stdin = io.StringIO("q")
    stdin.isatty = lambda: True
    stdin.fileno = lambda: 5
    stdout = io.StringIO()
    stdout.isatty = lambda: True
    restored = []
    monkeypatch.setattr(geometry_cli.sys, "stdin", stdin)
    monkeypatch.setattr(geometry_cli.sys, "stdout", stdout)
    monkeypatch.setattr(geometry_cli.termios, "tcgetattr", lambda fd: ["original"])
    monkeypatch.setattr(geometry_cli.termios, "tcsetattr",
        lambda fd, mode, saved: restored.append((fd, saved)))
    monkeypatch.setattr(geometry_cli.tty, "setcbreak", lambda fd: None)
    monkeypatch.setattr(geometry_cli.shutil, "get_terminal_size",
        lambda fallback=(88, 32): os.terminal_size((100, 30)))
    dimensions = []
    render = geometry_cli.render_spatial
    def recording_render(frame, columns, rows, **kwargs):
        dimensions.append((columns, rows))
        return render(frame, columns, rows, **kwargs)
    monkeypatch.setattr(geometry_cli, "render_spatial", recording_render)
    monkeypatch.setattr(geometry_cli.select, "select",
        lambda read, write, error, seconds: (read, [], []))
    result = geometry_cli.geometry_command(["--live"],
        connect=lambda path, op, args: {"ok": True, "result": project_spatial(sample())},
        socket_path="/test/worldline.sock", dumps=lambda x: str(x))
    assert result == 0
    assert dimensions == [(99, 28)]
    assert "\x1b[?1049h" in stdout.getvalue()
    assert "\x1b[?1049l" in stdout.getvalue()
    assert "\x1b[?7l" in stdout.getvalue()
    assert "\x1b[?7h" in stdout.getvalue()
    assert "\x1b[?25l" in stdout.getvalue()
    assert "\x1b[?25h" in stdout.getvalue()
    assert restored == [(5, ["original"])]
    rendered = stdout.getvalue().split("\x1b[?7h", 1)[0]
    assert rendered.endswith("╯")
    assert not rendered.endswith("\n")


def test_terminal_fallback_caps_details_to_avoid_live_screen_overflow():
    frame = {"revision": 1, "monitors": [], "windows": [
        {"title": f"Window {i}", "frame": {"x": 0, "y": 0,
         "width": 10, "height": 10}} for i in range(40)
    ]}
    output = render_spatial(frame, columns=80, rows=20, live=True)
    assert len(output.splitlines()) <= 20
    assert "more · use --json" in output
