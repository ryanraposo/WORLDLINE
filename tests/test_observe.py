import json
import os

import worldline.observe as observe_module
from worldline.observe import _windows, observe, redact
from worldline.window_geometry import rect

DISPLAY = {
    "screen": rect(0, 0, 1920, 1080),
    "monitors": [{
        "index": 0, "x": 0, "y": 0, "width": 1920, "height": 1080,
        "scale": 1.0, "transform": 0, "primary": True, "connector": "eDP-1",
    }],
}


def window(*, pid=42, identity=7, title="ChatGPT", frame=None, active=True):
    return {
        "id": identity,
        "stable_id": f"window:{pid}:{identity}",
        "accessible_path": f"/org/a11y/atspi/accessible/{identity}",
        "pid": pid,
        "app": "Codex",
        "title": title,
        "role": "frame",
        "frame": frame or rect(415, 176, 1090, 760),
        "states": ["active", "showing"] if active else ["showing"],
        "active": active,
        "focused": active,
        "maximized": False,
        "minimized": False,
        "shaded": False,
        "modal": False,
        "source": "at-spi2",
    }


def install_atspi(monkeypatch, items, *, available=True, reason=None, display=DISPLAY):
    monkeypatch.setattr(observe_module, "_atspi_windows", lambda: {
        "source": "at-spi2", "available": available, "count": len(items),
        "items": items, **({"reason": reason} if reason else {}),
    })
    monkeypatch.setattr(observe_module, "_display", lambda: display)


def test_atspi_windows_keep_identity_geometry_and_unknown_occlusion(monkeypatch):
    install_atspi(monkeypatch, [window()])
    world = _windows()
    assert world["source"] == "at-spi2"
    assert world["available"] is True
    assert world["count"] == 1
    assert world["by_id"]["window:42:7"]["title"] == "ChatGPT"
    assert world["active"]["stable_id"] == "window:42:7"
    assert world["stacking_order"] is None
    assert world["counts"]["verified"] == 0
    item = world["items"][0]
    assert item["frame"] == rect(415, 176, 1090, 760)
    assert item["geometry_source"] == "at-spi2"
    assert item["geometry"]["frame_source"] == "at-spi2-component-extents"
    assert item["geometry"]["exposure"]["occlusion_known"] is False
    assert item["geometry"]["exposure"]["topmost"] is None
    assert item["geometry"]["exposure"]["exposed_fraction_upper_bound"] is True
    assert world["sources"]["geometry"]["name"] == "at-spi2"


def test_atspi_identity_survives_reordering_and_title_change(monkeypatch):
    first = window(identity=7, title="Draft")
    second = window(identity=8, title="Other", active=False)
    install_atspi(monkeypatch, [first, second])
    before = _windows()
    assert set(before["by_id"]) == {"window:42:7", "window:42:8"}
    install_atspi(monkeypatch, [second, {**first, "title": "Saved"}])
    after = _windows()
    assert after["by_id"]["window:42:7"]["title"] == "Saved"
    assert after["by_id"]["window:42:8"]["title"] == "Other"
    assert after["count"] == 2


def test_distinct_accessibles_with_same_title_and_extents_are_not_collapsed(monkeypatch):
    install_atspi(monkeypatch, [window(identity=7), window(identity=8, active=False)])
    world = _windows()
    assert world["count"] == 2
    assert world["deduplicated"] == []


def test_duplicate_and_stale_atspi_records_keep_exclusion_reasons(monkeypatch):
    first = window()
    duplicate = dict(first)
    stale = window(identity=9, title="", frame=rect(-99, -99, 1, 1), active=False)
    install_atspi(monkeypatch, [first, duplicate, stale])
    world = _windows()
    assert world["count"] == 1
    assert world["counts"]["duplicate"] == 1
    assert world["counts"]["stale"] == 1
    assert {item["status"] for item in world["deduplicated"]} == {"duplicate", "stale"}


def test_no_accessibility_bus_reports_unavailable_without_helper_dependency(monkeypatch):
    install_atspi(monkeypatch, [], available=False, reason="accessibility bus is not reachable")
    world = _windows()
    assert world["available"] is False
    assert world["count"] == 0
    assert world["reason"] == "accessibility bus is not reachable"
    assert world["sources"]["geometry"]["available"] is False
    assert "WinRects" not in json.dumps(world)


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
