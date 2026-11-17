import sys
from types import SimpleNamespace

import worldline.observe as observe_module
from worldline.observe import _atspi_windows, _display_monitors


def test_atspi_object_path_provides_window_identity(monkeypatch):
    class Window:
        path = "/org/a11y/atspi/accessible/17"
        name = "Draft"

        def getRoleName(self):
            return "frame"

        def getState(self):
            return SimpleNamespace(getStates=lambda: [SimpleNamespace(value_nick="showing")])

        def queryComponent(self):
            return SimpleNamespace(getExtents=lambda _coords: SimpleNamespace(
                x=20, y=30, width=400, height=300
            ))

        def get_process_id(self):
            return 4242

    class App(list):
        name = "Editor"

    app = App([Window()])
    monkeypatch.setattr(observe_module, "_run", lambda *_args, **_kwargs: (0, "", ""))
    monkeypatch.setitem(sys.modules, "pyatspi", SimpleNamespace(
        Registry=SimpleNamespace(getDesktop=lambda _index: [app]),
        DESKTOP_COORDS=0,
    ))
    observed = _atspi_windows()
    assert observed["available"] is True
    assert observed["count"] == 1
    item = observed["items"][0]
    assert item["id"] == 17
    assert item["stable_id"] == "window:4242:17"
    assert item["cua_window_id"] == 4242 << 16
    assert item["frame"] == {"x": 20, "y": 30, "width": 400, "height": 300}


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
