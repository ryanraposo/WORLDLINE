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
                    "frame_source": "cua-gnome-shell-frame"}},
            {"stable_id": "window:101:4", "stacking": None,
                "title": "Terminal", "geometry": {
                    "frame": {"x": 80, "y": 200, "width": 800, "height": 480},
                    "frame_source": "at-spi2-component-extents"}},
        ], "focus": {"stable_id": "window:100:3", "verified": True,
            "source": "cua-gnome-shell"}},
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


def test_terminal_frame_draws_monitors_and_unknown_z():
    output = render_spatial(project_spatial(sample()), columns=100, rows=30)
    assert "WORLDLINE  /  GEOMETRY" in output
    assert "M0 " in output and "M1 " in output
    assert "?" in output and ("▓" in output or "█" in output)
    assert "q quit" in output

def test_live_map_quits_on_q_and_restores_terminal(monkeypatch):
    import io
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
    monkeypatch.setattr(geometry_cli.select, "select",
        lambda read, write, error, seconds: (read, [], []))
    result = geometry_cli.geometry_command(["--live"],
        connect=lambda path, op, args: {"ok": True, "result": project_spatial(sample())},
        socket_path="/test/worldline.sock", dumps=lambda x: str(x))
    assert result == 0
    assert "\\x1b[?25l" in stdout.getvalue()
    assert "\\x1b[?25h" in stdout.getvalue()
    assert restored == [(5, ["original"])]
