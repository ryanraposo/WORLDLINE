from worldline.desktop import DesktopObservationService


def window(*, pid=100, compositor_id=7, title="Editor", x=10, focused=True):
    return {
        "pid": pid, "compositor_id": compositor_id,
        "compositor_verified": True, "accessible_path": "/org/a11y/atspi/accessible/42",
        "title": title, "geometry_source": "worldline-gnome-shell",
        "geometry": {"frame": {"x": x, "y": 20, "width": 800, "height": 600}},
        "focused": focused, "visible": True, "minimized": False,
    }


def reading(items):
    return {
        "available": True, "source": "worldline-gnome-shell+at-spi2",
        "items": items, "screen": {"x": 0, "y": 0, "width": 1920, "height": 1080},
        "monitors": [], "stacking_order": None,
        "sources": {
            "semantic": {"name": "at-spi2", "available": True},
            "geometry": {"name": "worldline-gnome-shell", "available": True},
        },
    }


def test_snapshot_assigns_session_scoped_identity_and_truthful_capabilities():
    service = DesktopObservationService(lambda **_: reading([window()]))
    snapshot = service.refresh()
    item = snapshot["windows"][0]
    assert snapshot["schema"] == "worldline.desktop-observation/1"
    assert item["window_id"].startswith(f"window:{snapshot['session_id']}:")
    assert item["identity"]["scope"] == "worldline-session"
    assert item["geometry"]["verified"] is True
    assert snapshot["capabilities"]["compositor_frame_geometry"]["available"] is True
    assert snapshot["capabilities"]["activation"]["available"] is False
    assert snapshot["capabilities"]["pixel_visibility"]["available"] is False


def test_identity_survives_updates_and_emits_geometry_and_state_events():
    values = [reading([window()]), reading([window(title="Renamed", x=40, focused=False)])]
    service = DesktopObservationService(lambda **_: values.pop(0))
    first = service.refresh()
    stable_id = first["windows"][0]["window_id"]
    second = service.refresh()
    assert second["windows"][0]["window_id"] == stable_id
    events = service.events(0)
    kinds = [event["type"] for event in events["events"]]
    assert "window.geometry_changed" in kinds
    assert "window.state_changed" in kinds
    assert "window.title_changed" in kinds
    assert "focus.changed" in kinds


def test_destroyed_and_recreated_window_gets_a_new_lifetime_identity():
    values = [reading([window()]), reading([]), reading([window()])]
    service = DesktopObservationService(lambda **_: values.pop(0))
    first_id = service.refresh()["windows"][0]["window_id"]
    service.refresh()
    third = service.refresh()
    assert third["windows"][0]["window_id"] != first_id
    assert [e["type"] for e in service.events(0)["events"]].count("window.destroyed") == 1


def test_unavailable_source_does_not_turn_uncertainty_into_destruction():
    values = [reading([window()]), {"available": False, "reason": "extension unavailable",
                                    "items": []}]
    service = DesktopObservationService(lambda **_: values.pop(0))
    first = service.refresh()
    second = service.refresh()
    assert second["available"] is False
    assert second["windows"][0]["window_id"] == first["windows"][0]["window_id"]
    assert not any(e["type"] == "window.destroyed" for e in service.events(0)["events"])


def test_event_cursor_reports_when_consumer_must_resynchronize():
    service = DesktopObservationService(lambda **_: reading([]))
    service.EVENT_LIMIT = 2
    service.refresh()
    service._record("test.one", "", {})
    service._record("test.two", "", {})
    service._record("test.three", "", {})
    result = service.events(0)
    assert result["resync_required"] is True
    assert result["events"] == []
    assert result["earliest_sequence"] > 1
