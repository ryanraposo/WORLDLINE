from worldline.window_geometry import (
    describe,
    intersection,
    monitor_for,
    overlap_fraction,
    rect,
    screen_bounds,
    union,
)

MONITORS = [
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
]


def test_frame_on_screen_and_monitor():
    geometry = describe(rect(415, 176, 1090, 760), monitors=MONITORS)
    assert geometry["coordinate_space"] == "desktop-logical-px"
    assert geometry["frame"] == {"x": 415, "y": 176, "width": 1090, "height": 760}
    assert geometry["area"] == 828400
    assert geometry["center"] == {"x": 960.0, "y": 556.0}
    assert geometry["on_screen"] is True
    assert geometry["fully_on_screen"] is True
    assert geometry["visible_fraction"] == 1.0
    assert geometry["offscreen"] == {"left": 0, "top": 0, "right": 0, "bottom": 0}
    assert geometry["monitor"]["connector"] == "eDP-1"
    assert geometry["monitor_relative"] == {
        "x": 415,
        "y": 176,
        "width": 1090,
        "height": 760,
    }
    assert geometry["spans_monitors"] is False


def test_partially_offscreen_frame_reports_clipped_rect():
    geometry = describe(rect(-100, -50, 200, 100), monitors=MONITORS)
    assert geometry["on_screen"] is True
    assert geometry["visible_rect"] == {"x": 0, "y": 0, "width": 100, "height": 50}
    assert geometry["visible_area"] == 5000
    assert geometry["visible_fraction"] == 0.25
    assert geometry["offscreen"] == {"left": 100, "top": 50, "right": 0, "bottom": 0}
    assert geometry["fully_on_screen"] is False


def test_fully_offscreen_frame_stays_attached_to_nearest_monitor():
    geometry = describe(rect(3000, 100, 100, 100), monitors=MONITORS)
    assert geometry["on_screen"] is False
    assert geometry["visible_area"] == 0
    assert geometry["visible_fraction"] == 0.0
    assert geometry["offscreen"]["right"] == 1180
    assert geometry["monitor"]["connector"] == "eDP-1"
    assert geometry["on_monitor"] is False


def test_negative_origin_multi_monitor_layout():
    monitors = [
        {
            "index": 0,
            "x": -1920,
            "y": 0,
            "width": 1920,
            "height": 1080,
            "scale": 1.0,
            "primary": False,
            "connector": "DP-1",
        },
        {
            "index": 1,
            "x": 0,
            "y": 0,
            "width": 1920,
            "height": 1080,
            "scale": 1.0,
            "primary": True,
            "connector": "eDP-1",
        },
    ]
    assert screen_bounds(monitors) == {
        "x": -1920,
        "y": 0,
        "width": 3840,
        "height": 1080,
    }
    geometry = describe(rect(-100, 100, 200, 200), monitors=monitors)
    assert geometry["monitor"]["connector"] == "DP-1"
    assert geometry["monitor_relative"]["x"] == 1820
    assert geometry["spans_monitors"] is True
    assert len(geometry["monitor_intersections"]) == 2


def test_stacking_exposure_is_bottom_to_top():
    covered = describe(
        rect(0, 0, 100, 100),
        monitors=MONITORS,
        occluders=[rect(50, 0, 100, 100)],
        z_index=0,
    )
    assert covered["exposure"]["exposed_fraction"] == 0.5
    assert covered["exposure"]["topmost"] is False
    assert covered["exposure"]["stacking_order"] == "bottom-to-top"

    top = describe(rect(0, 0, 100, 100), monitors=MONITORS, z_index=1)
    assert top["exposure"]["exposed_fraction"] == 1.0
    assert top["exposure"]["topmost"] is True


def test_unknown_stacking_never_claims_topmost():
    geometry = describe(rect(0, 0, 100, 100), monitors=MONITORS)
    assert geometry["exposure"]["occlusion_known"] is False
    assert geometry["exposure"]["topmost"] is None


def test_device_pixels_follow_monitor_scale():
    monitors = [{**MONITORS[0], "scale": 2.0}]
    geometry = describe(rect(10, 20, 100, 50), monitors=monitors)
    assert geometry["device_pixels"] == {
        "x": 20,
        "y": 40,
        "width": 200,
        "height": 100,
    }


def test_zero_size_frame_does_not_divide_by_zero():
    geometry = describe(rect(5, 5, 0, 0), monitors=MONITORS)
    assert geometry["area"] == 0
    assert geometry["visible_fraction"] == 0.0
    assert geometry["exposure"]["exposed_fraction"] == 0.0


def test_rect_helpers():
    assert intersection(rect(0, 0, 10, 10), rect(5, 5, 10, 10)) == {
        "x": 5,
        "y": 5,
        "width": 5,
        "height": 5,
    }
    assert intersection(rect(0, 0, 10, 10), rect(20, 20, 10, 10)) is None
    assert union([rect(0, 0, 10, 10), rect(20, 20, 10, 10)]) == {
        "x": 0,
        "y": 0,
        "width": 30,
        "height": 30,
    }
    assert overlap_fraction(rect(0, 0, 10, 10), rect(5, 0, 10, 10)) == 0.5
    monitor, covered = monitor_for(rect(1, 1, 2, 2), MONITORS)
    assert monitor is MONITORS[0]
    assert covered == 4
