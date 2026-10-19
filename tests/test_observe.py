import json
import os

import worldline.observe as observe_module
from worldline.observe import _windows, observe, redact
from worldline.window_geometry import rect

DISPLAY = {
    "screen": {"x": 0, "y": 0, "width": 1920, "height": 1080},
    "monitors": [
        {
            "index": 0,
            "x": 0,
            "y": 0,
            "width": 1920,
            "height": 1080,
            "scale": 1.0,
            "transform": 0,
            "primary": True,
            "connector": "eDP-1",
        }
    ],
}


def atspi_window(**overrides):
    item = {
        "pid": 42,
        "app": "Codex",
        "title": "ChatGPT",
        "role": "frame",
        "frame": rect(0, 0, 100, 100),
        "states": ["active", "showing"],
        "active": True,
        "focused": False,
        "maximized": False,
        "minimized": False,
        "modal": False,
        "source": "at-spi2",
    }
    item.update(overrides)
    return item


def compositor_window(**overrides):
    item = {
        "id": 7,
        "pid": 42,
        "app": "codex",
        "title": "ChatGPT",
        "role": "frame",
        "frame": rect(415, 176, 1090, 760),
        "buffer_origin": {"x": 415, "y": 176},
        "focused": True,
        "minimized": False,
        "visible": True,
        "stacking": 1,
        "source": "org.cua.WinRects",
    }
    item.update(overrides)
    return item


def install_sources(monkeypatch, atspi, compositor, display=DISPLAY):
    monkeypatch.setattr(observe_module, "_atspi_windows", lambda: atspi)
    monkeypatch.setattr(observe_module, "_compositor_windows", lambda: compositor)
    monkeypatch.setattr(observe_module, "_display", lambda: display)


def test_merge_prefers_compositor_geometry_and_keeps_semantics(monkeypatch):
    install_sources(
        monkeypatch,
        {
            "source": "at-spi2",
            "available": True,
            "count": 1,
            "items": [atspi_window()],
        },
        {
            "source": "org.cua.WinRects",
            "available": True,
            "version": 8,
            "count": 1,
            "items": [compositor_window()],
        },
    )
    world = _windows()
    assert world["source"] == "at-spi2"
    assert world["geometry_source"] == "org.cua.WinRects"
    assert world["available"] is True
    assert world["count"] == 1
    assert world["active"]["app"] == "Codex"
    assert world["active"]["id"] == 7

    item = world["items"][0]
    assert item["id"] == 7
    assert item["stable_id"] == "window:42:7"
    assert item["app"] == "Codex"
    assert item["title"] == "ChatGPT"
    assert item["focused"] is True
    assert item["active"] is True
    assert item["sources"] == ["at-spi2", "org.cua.WinRects"]
    assert item["geometry_source"] == "org.cua.WinRects"
    assert item["x"] == 415 and item["width"] == 1090

    geometry = item["geometry"]
    assert geometry["frame"] == {"x": 415, "y": 176, "width": 1090, "height": 760}
    assert geometry["monitor"]["connector"] == "eDP-1"
    assert geometry["visible_fraction"] == 1.0
    assert geometry["exposure"]["occlusion_known"] is True
    assert geometry["exposure"]["topmost"] is True
    assert geometry["buffer"]["offset_x"] == 0
    assert geometry["monitor_relative"]["x"] == 415


def test_atspi_geometry_fallback_preserves_clipping(monkeypatch):
    install_sources(
        monkeypatch,
        {
            "source": "at-spi2",
            "available": True,
            "count": 1,
            "items": [
                atspi_window(
                    title="Offscreen",
                    frame=rect(-100, -50, 200, 100),
                    active=False,
                )
            ],
        },
        {
            "source": "org.cua.WinRects",
            "available": False,
            "reason": "WinRects helper is not available",
            "count": 0,
            "items": [],
        },
    )
    world = _windows()
    assert world["source"] == "at-spi2"
    assert world["geometry_source"] == "at-spi2"
    item = world["items"][0]
    assert item["geometry"].get("monitor") is not None
    assert item["geometry"]["visible_rect"] == {
        "x": 0,
        "y": 0,
        "width": 100,
        "height": 50,
    }
    assert item["geometry"]["visible_fraction"] == 0.25
    assert item["geometry"]["offscreen"] == {
        "left": 100,
        "top": 50,
        "right": 0,
        "bottom": 0,
    }


def test_compositor_only_uses_stacking_for_exposure(monkeypatch):
    install_sources(
        monkeypatch,
        {
            "source": "at-spi2",
            "available": False,
            "reason": "pyatspi missing",
            "count": 0,
            "items": [],
        },
        {
            "source": "org.cua.WinRects",
            "available": True,
            "version": 8,
            "count": 2,
            "items": [
                compositor_window(
                    id=1,
                    title="bottom",
                    frame=rect(0, 0, 100, 100),
                    buffer_origin={"x": 0, "y": 0},
                    focused=False,
                    stacking=0,
                ),
                compositor_window(
                    id=2,
                    title="top",
                    frame=rect(50, 0, 100, 100),
                    buffer_origin={"x": 50, "y": 0},
                    focused=True,
                    stacking=1,
                ),
            ],
        },
    )
    world = _windows()
    assert world["source"] == "org.cua.WinRects"
    assert world["stacking_order"] == "bottom-to-top"
    assert [item["title"] for item in world["items"]] == ["top", "bottom"]

    top, bottom = world["items"]
    assert top["geometry"]["exposure"]["topmost"] is True
    assert top["geometry"]["exposure"]["exposed_fraction"] == 1.0
    assert bottom["geometry"]["exposure"]["topmost"] is False
    assert bottom["geometry"]["exposure"]["exposed_fraction"] == 0.5


def test_no_window_source_reports_explicit_failure(monkeypatch):
    install_sources(
        monkeypatch,
        {
            "source": "at-spi2",
            "available": False,
            "reason": "pyatspi missing",
            "count": 0,
            "items": [],
        },
        {
            "source": "org.cua.WinRects",
            "available": False,
            "reason": "WinRects helper is not available",
            "count": 0,
            "items": [],
        },
    )
    world = _windows()
    assert world["source"] == "at-spi2"
    assert world["available"] is False
    assert world["count"] == 0
    assert "pyatspi missing" in world["reason"]
    assert "WinRects" in world["reason"]


def test_core_snapshot_is_real():
    world = observe(("time", "host", "os", "cpu", "memory"))
    assert world["schema"] == 1
    assert isinstance(world["host"]["hostname"], str)
    assert world["os"]["kernel"]
    assert world["cpu"]["logical_cores"] >= 1
    assert 0 <= world["memory"]["percent"] <= 100
    assert "T" in world["time"]["iso"]
    json.dumps(world)


def test_expensive_sections_are_not_collected_unless_asked(monkeypatch):
    def fail():
        raise AssertionError("windows collected")

    monkeypatch.setitem(observe_module._COLLECTORS, "windows", fail)
    world = observe(("host",))
    assert "windows" not in world
    assert "host" in world


def test_secret_environment_is_not_exported(monkeypatch):
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "do-not-export")
    monkeypatch.setenv("OPENAI_API_KEY", "do-not-export")
    world = observe(("session",))
    exported = world["session"]["env"]
    assert "AWS_SECRET_ACCESS_KEY" not in exported
    assert "OPENAI_API_KEY" not in exported
    assert "do-not-export" not in json.dumps(world)


def test_cmdline_redaction():
    assert (
        redact("app --password=hunter2 --token abc --api-key xyz")
        == "app --password=*** --token *** --api-key ***"
    )
    assert (
        redact("curl https://user:pw@example.com/x")
        == "curl https://user:***@example.com/x"
    )


def test_processes_top_and_full():
    top = observe(("processes",))["processes"]
    assert top["count"] >= 1
    assert top["self_pid"] == os.getpid()
    assert all("all" not in item for item in top["top"])

    full = observe(("processes",), full=True)["processes"]
    assert full["count"] == len(full["all"])
    assert full["count"] >= len(full["top"])
