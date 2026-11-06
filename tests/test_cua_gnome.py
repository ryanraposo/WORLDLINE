import pytest

from worldline.cua_gnome import _parse_rects_payload


def test_workspace_snapshot_parser_accepts_atomic_state_and_frames():
    items, state = _parse_rects_payload(
        '(\'{"workspaces":{"active":2,"count":4},"items":[{"id":7}]}\',)')
    assert items == [{"id": 7}]
    assert state == {"count": 4, "active": 2}


def test_workspace_snapshot_parser_preserves_unknown_and_supports_legacy_arrays():
    with pytest.raises(ValueError):
        _parse_rects_payload("not-json")
    assert _parse_rects_payload('(\'{"workspaces":{"active":4,"count":4},"items":[]}\',)') == ([], None)
    assert _parse_rects_payload('(\'{"workspaces":{"active":false,"count":4},"items":[]}\',)') == ([], None)
    assert _parse_rects_payload('(\'[ {"id":7} ]\',)') == ([{"id": 7}], None)
