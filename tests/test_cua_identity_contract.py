from pathlib import Path

import worldline.observe as observe


def test_gnome_extension_uses_cua_stable_sequence_for_window_ids():
    source = (Path(__file__).resolve().parents[1] / "gnome-extension" / "extension.js").read_text()
    assert "window.get_stable_sequence()" in source
    assert "window.get_id()" not in source


def test_window_snapshot_maps_compositor_identity_into_stable_id(monkeypatch):
    pid, window_id = 4242, 0x1234
    monkeypatch.setattr(observe, "_atspi_windows", lambda: {
        "available": True,
        "count": 1,
        "items": [{
            "id": 17,
            "stable_id": "window:4242:17",
            "pid": pid,
            "title": "Editor",
            "role": "frame",
            "frame": {"x": 20, "y": 30, "width": 800, "height": 600},
            "active": True,
            "focused": True,
            "visible": True,
            "minimized": False,
            "maximized": False,
            "modal": False,
            "shaded": False,
        }],
    })
    monkeypatch.setattr(observe, "_compositor_windows", lambda: {
        "available": True,
        "items": [{
            "pid": pid,
            "id": window_id,
            "title": "Editor",
            "x": 20,
            "y": 30,
            "w": 800,
            "h": 600,
            "focused": True,
            "visible": True,
            "minimized": False,
            "stacking": 0,
        }],
    })
    monkeypatch.setattr(observe, "_display", lambda: {
        "monitors": [],
        "screen": {"x": 0, "y": 0, "width": 1920, "height": 1080},
    })

    snapshot = observe._windows()
    assert snapshot["count"] == 1
    item = snapshot["items"][0]
    assert item["compositor_id"] == window_id
    assert item["compositor_verified"] is True
    assert item["stable_id"] == f"window:{pid}:{window_id}"
    assert snapshot["focus"]["pid"] == pid
    assert snapshot["focus"]["compositor_id"] == window_id
    assert snapshot["focus"]["stable_id"] == item["stable_id"]
