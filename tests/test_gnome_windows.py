import json
import subprocess
from types import SimpleNamespace

import pytest

from worldline.daemon import WorldlineDaemon
from worldline.providers.gnome_windows import (
    GNOMEWindowsProvider, SNAPSHOT_KEY, SOURCE_KEY, decode_snapshot,
)


def observed(window=None):
    return {
        "schema": 1,
        "generation": "shell-session-a",
        "observed_at": 1000.0,
        "order_source": "actor-enumeration",
        "total_windows": 1,
        "truncated": False,
        "windows": [window or {
            "id": "43",
            "gtk_app_id": "example.App",
            "wm_class": "example",
            "title": "Document",
            "reported_pid": 234,
            "transient_for": "21",
            "frame": {"x": 10, "y": -5, "width": 120, "height": 50},
            "focused": True,
            "actor_present": True,
            "enumeration_index": 0,
            "stack_index": None,
        }],
    }


def dbus_response(payload):
    return repr((json.dumps(payload),)) + "\n"


def test_native_metadata_remains_raw_and_non_interpreted():
    captured = []
    def runner(argv, **kwargs):
        captured.append((argv, kwargs))
        return SimpleNamespace(returncode=0, stdout=dbus_response(observed()))
    provider = GNOMEWindowsProvider(runner=runner, clock=lambda: 1000.2)
    available, fact = provider.observe()
    assert available.key == SOURCE_KEY and available.value is True
    assert fact.key == SNAPSHOT_KEY
    snap = fact.value
    assert snap["generation"] == "shell-session-a"
    assert snap["windows"][0]["transient_for"] == "21"
    assert snap["windows"][0]["reported_pid"] == 234
    assert snap["windows"][0]["stack_index"] is None
    assert "owner_entity" not in snap["windows"][0]
    assert "group" not in snap["windows"][0]
    assert fact.evidence.source.startswith("gnome-shell:")
    assert fact.evidence.expires_at == 1005.2
    assert captured[0][1]["timeout"] == 1.5
    assert "--method" in captured[0][0]


@pytest.mark.parametrize("edit", [
    lambda p: p.update(observed_at=900),
    lambda p: p.update(generation=""),
    lambda p: p.update(order_source="made-up"),
    lambda p: p["windows"].append(p["windows"][0]),
    lambda p: p["windows"][0].update(stack_index=1),
    lambda p: p["windows"][0].update(frame={"x": 1}),
    lambda p: p["windows"][0].update(connected_to="unobserved-claim"),
])
def test_source_record_validation(edit):
    payload = observed()
    edit(payload)
    if "connected_to" in payload["windows"][0]:
        # Additional fields are deliberately not projected as observed facts.
        snap = decode_snapshot(dbus_response(payload), now=1000)
        assert "connected_to" not in snap["windows"][0]
    else:
        with pytest.raises(ValueError):
            decode_snapshot(dbus_response(payload), now=1000)


def test_compositor_generation_scopes_identity():
    before = decode_snapshot(dbus_response(observed()), now=1000)
    after_payload = observed()
    after_payload["generation"] = "shell-session-b"
    after = decode_snapshot(dbus_response(after_payload), now=1000)
    assert before["windows"][0]["id"] == after["windows"][0]["id"]
    assert before["generation"] != after["generation"]


def test_failed_transport_does_not_fabricate_windows():
    def unavailable(_argv, **_options):
        raise subprocess.TimeoutExpired("gdbus", 1.5)
    available = list(GNOMEWindowsProvider(runner=unavailable, clock=lambda: 1000).observe())
    assert len(available) == 1
    assert available[0].key == SOURCE_KEY and available[0].value is False


def test_generic_query_refresh_updates_and_invalidates_native_snapshot():
    payload = observed()
    live = True
    def runner(_argv, **_options):
        if live:
            return SimpleNamespace(returncode=0, stdout=dbus_response(payload))
        return SimpleNamespace(returncode=1, stdout="")
    daemon = WorldlineDaemon()
    daemon.providers["gnome-windows"] = GNOMEWindowsProvider(
        runner=runner, clock=lambda: 1000,
    )
    request = {"op": "query", "args": {"refresh": ["gnome-windows"]}}
    first = daemon.dispatch(request)
    assert first["ok"]
    assert first["result"]["facts"][SNAPSHOT_KEY]["value"]["windows"][0]["id"] == "43"
    live = False
    second = daemon.dispatch(request)
    assert second["ok"]
    assert second["result"]["facts"][SOURCE_KEY]["value"] is False
    assert SNAPSHOT_KEY not in second["result"]["facts"]
    assert not daemon.dispatch({"op": "query", "args": {"refresh": ["bogus"]}})["ok"]
    assert not daemon.dispatch({"op": "query", "args": {"refresh": "gnome-windows"}})["ok"]
