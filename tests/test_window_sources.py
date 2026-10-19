import json

from worldline.observe import _display_monitors, _parse_winrects, _winrects_reply


def rect(x, y, width, height):
    return {"x": x, "y": y, "width": width, "height": height}


def test_winrects_payload_is_normalized_and_malformed_entries_are_skipped():
    payload = [
        {
            "id": 7,
            "pid": 4242,
            "title": "ChatGPT",
            "x": 415,
            "y": 176,
            "w": 1090,
            "h": 760,
            "buffer_x": 415,
            "buffer_y": 176,
            "focused": True,
            "visible": True,
            "stacking": 1,
        },
        {
            "id": 8,
            "pid": 4243,
            "title": "",
            "x": 10,
            "y": 20,
            "w": 30,
            "h": 40,
            "buffer_x": 5,
            "buffer_y": 6,
            "focused": False,
            "minimized": True,
            "visible": False,
            "stacking": None,
        },
        {"id": 9, "pid": 4244, "x": 0, "y": 0, "w": 0, "h": 100},
        {"id": 10, "pid": "not-a-pid", "x": 0, "y": 0, "w": 10, "h": 10},
        {"id": 11, "pid": 4245, "title": "missing geometry"},
        "not a window",
        None,
    ]

    result = _parse_winrects(payload, version=8)

    assert result["source"] == "org.cua.WinRects"
    assert result["available"] is True
    assert result["version"] == 8
    assert result["count"] == 2
    first, second = result["items"]

    assert first["id"] == 7
    assert first["pid"] == 4242
    assert first["title"] == "ChatGPT"
    assert first["role"] == "frame"
    assert first["frame"] == rect(415, 176, 1090, 760)
    assert first["buffer_origin"] == {"x": 415, "y": 176}
    assert first["focused"] is True
    assert first["visible"] is True
    assert first["stacking"] == 1
    assert first["source"] == "org.cua.WinRects"

    assert second["id"] == 8
    assert second["title"] == ""
    assert second["frame"] == rect(10, 20, 30, 40)
    assert second["buffer_origin"] == {"x": 5, "y": 6}
    assert second["minimized"] is True
    assert second["visible"] is False
    assert second["stacking"] is None


def test_winrects_reply_accepts_a_dbus_tuple_and_json_string():
    payload = [{"id": 1, "pid": 2, "title": "x", "x": 1, "y": 2, "w": 3, "h": 4}]
    assert _winrects_reply((json.dumps(payload),))["count"] == 1
    assert _winrects_reply(json.dumps(payload))["count"] == 1


def test_winrects_reply_reports_missing_invalid_and_non_list_payloads():
    missing = _winrects_reply(None)
    assert missing["available"] is False
    assert "not available" in missing["reason"]

    invalid = _winrects_reply("{not json")
    assert invalid["available"] is False
    assert "JSONDecodeError" in invalid["reason"]

    non_list = _winrects_reply("{}")
    assert non_list["available"] is False
    assert "not a window list" in non_list["reason"]

    assert _parse_winrects({"windows": []})["available"] is False


def test_mutter_state_maps_modes_scales_and_transforms():
    edp = ("eDP-1", "BOE", "0x095f", "0x00000000")
    dp = ("DP-1", "Dell", "0x1234", "0x0001")
    hdmi = ("HDMI-1", "Vendor", "0x0000", "0x0002")
    state = (
        12,
        [
            (
                edp,
                [
                    (
                        "1920x1080@60.008",
                        1920,
                        1080,
                        60.008,
                        1.0,
                        [1.0],
                        {"is-current": True},
                    ),
                    ("1280x720@60", 1280, 720, 60.0, 1.0, [1.0], {}),
                ],
                {},
            ),
            (
                dp,
                [
                    (
                        "3840x2160@60",
                        3840,
                        2160,
                        60.0,
                        2.0,
                        [1.0, 2.0],
                        {"is-current": True},
                    )
                ],
                {},
            ),
            (
                hdmi,
                [("1920x1080@60", 1920, 1080, 60.0, 1.0, [1.0], {"is-current": True})],
                {},
            ),
        ],
        [
            (0, 0, 1.0, 0, True, [edp]),
            (1920, 0, 2.0, 0, False, [dp]),
            (3840, 0, 1.0, 1, False, [hdmi]),
        ],
        {},
    )

    monitors = _display_monitors(state)

    assert monitors == [
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
            "connectors": ["eDP-1"],
            "mode": "1920x1080@60.008",
            "refresh_hz": 60.008,
        },
        {
            "index": 1,
            "x": 1920,
            "y": 0,
            "width": 1920,
            "height": 1080,
            "scale": 2.0,
            "transform": 0,
            "primary": False,
            "connector": "DP-1",
            "connectors": ["DP-1"],
            "mode": "3840x2160@60",
            "refresh_hz": 60.0,
        },
        {
            "index": 2,
            "x": 3840,
            "y": 0,
            "width": 1080,
            "height": 1920,
            "scale": 1.0,
            "transform": 1,
            "primary": False,
            "connector": "HDMI-1",
            "connectors": ["HDMI-1"],
            "mode": "1920x1080@60",
            "refresh_hz": 60.0,
        },
    ]


def test_mutter_state_skips_malformed_members():
    valid = ("eDP-1", "BOE", "0x095f", "0x0")
    state = (
        1,
        [
            (
                valid,
                [("1920x1080", 1920, 1080, 60.0, 1.0, [1.0], {"is-current": True})],
                {},
            ),
            "not a monitor",
            (valid, ["not a mode"], {}),
        ],
        [
            (0, 0, 1.0, 0, True, [valid]),
            (0, 0, "bad-scale", 0, True, [valid]),
            (0, 0, 1.0, 0, True),
            "not a logical monitor",
        ],
        {},
    )
    assert len(_display_monitors(state)) == 1
    assert _display_monitors(None) == []
    assert _display_monitors(()) == []
    assert _display_monitors(("too-short",)) == []


def test_mutter_state_without_a_current_mode_keeps_the_monitor():
    monitor = ("eDP-1", "BOE", "0x095f", "0x0")
    monitors = _display_monitors(
        (
            1,
            [(monitor, [("1920x1080", 1920, 1080, 60.0, 1.0, [1.0], {})], {})],
            [(0, 0, 1.0, 0, True, [monitor])],
            {},
        )
    )
    assert len(monitors) == 1
    assert monitors[0]["width"] == 0
    assert monitors[0]["height"] == 0
    assert monitors[0]["mode"] is None
