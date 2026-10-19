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
        "shaded": False,
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
    assert item["status"] == "verified"
    assert item["match"]["method"] == "pid_title"
    assert item["match"]["pid_match"] is True
    assert item["match"]["title_match"] == "exact"
    assert item["match"]["frame_overlap"] == 0.0
    assert item["confidence"] >= 0.95
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


def test_stale_atspi_frame_is_deduplicated_with_reason(monkeypatch):
    stale = atspi_window(
        pid=77,
        app="gjs",
        title="",
        role="window",
        frame=rect(-99, -99, 1, 1),
        active=False,
        focused=False,
        states=["showing", "visible"],
    )
    install_sources(
        monkeypatch,
        {
            "source": "at-spi2",
            "available": True,
            "count": 2,
            "items": [atspi_window(), stale],
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
    assert world["count"] == 1
    assert world["counts"] == {
        "canonical": 1,
        "semantic": 2,
        "geometry": 1,
        "verified": 1,
        "semantic_only": 0,
        "geometry_only": 0,
        "deduplicated": 1,
        "stale": 1,
        "duplicate": 0,
    }
    assert [item["title"] for item in world["items"]] == ["ChatGPT"]
    assert len(world["deduplicated"]) == 1
    dropped = world["deduplicated"][0]
    assert dropped["title"] == ""
    assert dropped["sources"] == ["at-spi2"]
    assert dropped["frame"] == rect(-99, -99, 1, 1)
    assert dropped["status"] == "stale"
    assert "degenerate off-screen frame" in dropped["reason"]
    assert dropped["match"]["band"] == "stale"
    assert dropped["confidence"] < 0.1


def test_duplicate_semantic_frame_is_reported_not_counted(monkeypatch):
    duplicate = atspi_window(
        role="window",
        frame=rect(415, 176, 1090, 760),
        active=False,
        focused=False,
    )
    install_sources(
        monkeypatch,
        {
            "source": "at-spi2",
            "available": True,
            "count": 2,
            "items": [atspi_window(), duplicate],
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
    assert world["count"] == 1
    assert world["counts"]["duplicate"] == 1
    dropped = world["deduplicated"][0]
    assert dropped["status"] == "duplicate"
    assert dropped["title"] == "ChatGPT"
    assert dropped["sources"] == ["at-spi2"]
    assert "window:42:7" in dropped["reason"]


def test_plausible_atspi_only_window_stays_canonical(monkeypatch):
    popup = atspi_window(
        pid=99,
        app="helper",
        title="Preferences",
        role="dialog",
        frame=rect(700, 300, 400, 300),
        active=False,
        focused=False,
    )
    install_sources(
        monkeypatch,
        {
            "source": "at-spi2",
            "available": True,
            "count": 1,
            "items": [popup],
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
    assert world["count"] == 2
    assert world["counts"]["semantic_only"] == 1
    assert world["counts"]["geometry_only"] == 1
    assert world["deduplicated"] == []

    item = next(item for item in world["items"] if item["pid"] == 99)
    assert item["status"] == "semantic_only"
    assert item["geometry_source"] == "at-spi2"
    assert item["sources"] == ["at-spi2"]
    assert item["match"]["method"] == "semantic_only"
    assert item["confidence"] == 0.5
    assert item["geometry"]["exposure"]["topmost"] is None


def test_empty_title_single_process_joins_by_pid(monkeypatch):
    install_sources(
        monkeypatch,
        {
            "source": "at-spi2",
            "available": True,
            "count": 1,
            "items": [atspi_window(title="", frame=rect(0, 0, 100, 100))],
        },
        {
            "source": "org.cua.WinRects",
            "available": True,
            "version": 8,
            "count": 1,
            "items": [
                compositor_window(
                    title="",
                    frame=rect(400, 100, 100, 100),
                    buffer_origin={"x": 400, "y": 100},
                )
            ],
        },
    )
    world = _windows()
    assert world["count"] == 1
    item = world["items"][0]
    assert item["status"] == "verified"
    assert item["match"]["method"] == "pid_only"
    assert item["confidence"] == 0.5
    assert item["frame"] == rect(400, 100, 100, 100)


def test_minimized_window_does_not_occlude_lower_windows(monkeypatch):
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
                    pid=43,
                    title="bottom",
                    frame=rect(0, 0, 100, 100),
                    buffer_origin={"x": 0, "y": 0},
                    focused=False,
                    stacking=0,
                ),
                compositor_window(
                    id=2,
                    pid=44,
                    title="minimized",
                    frame=rect(50, 0, 100, 100),
                    buffer_origin={"x": 50, "y": 0},
                    focused=False,
                    minimized=True,
                    visible=False,
                    stacking=1,
                ),
            ],
        },
    )
    world = _windows()
    bottom = next(item for item in world["items"] if item["title"] == "bottom")
    minimized = next(item for item in world["items"] if item["title"] == "minimized")

    assert bottom["geometry"]["exposure"]["exposed_fraction"] == 1.0
    assert bottom["geometry"]["exposure"]["topmost"] is True
    assert minimized["geometry"]["presented"] is False
    assert minimized["geometry"]["exposure"]["not_presented_reason"] == "minimized"
    assert minimized["geometry"]["exposure"]["exposed_fraction"] == 0.0


def test_shaded_window_and_occluder_preserve_uncertainty(monkeypatch):
    top = atspi_window(
        pid=42,
        title="shaded",
        frame=rect(50, 0, 100, 100),
        shaded=True,
    )
    install_sources(
        monkeypatch,
        {
            "source": "at-spi2",
            "available": True,
            "count": 1,
            "items": [top],
        },
        {
            "source": "org.cua.WinRects",
            "available": True,
            "version": 8,
            "count": 2,
            "items": [
                compositor_window(
                    id=1,
                    pid=43,
                    title="bottom",
                    frame=rect(0, 0, 100, 100),
                    buffer_origin={"x": 0, "y": 0},
                    focused=False,
                    stacking=0,
                ),
                compositor_window(
                    id=2,
                    pid=42,
                    title="shaded",
                    frame=rect(50, 0, 100, 100),
                    buffer_origin={"x": 50, "y": 0},
                    focused=True,
                    stacking=1,
                ),
            ],
        },
    )
    world = _windows()
    shaded = next(item for item in world["items"] if item["title"] == "shaded")
    bottom = next(item for item in world["items"] if item["title"] == "bottom")

    assert shaded["state"]["shaded"] is True
    assert shaded["geometry"]["shaded"] is True
    assert shaded["geometry"]["exposure"]["surface"] == "shaded"
    assert shaded["geometry"]["exposure"]["topmost"] is None

    assert bottom["geometry"]["exposure"]["topmost"] is None
    assert bottom["geometry"]["exposure"]["occlusion_known"] is False
    assert "shaded window" in bottom["geometry"]["exposure"]["limitations"][0]


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
