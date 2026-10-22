import worldline.current as current_module
from worldline.current import Current
from worldline.store import WorldStore


def test_targeted_refresh_and_window_identity_survives_reordering(monkeypatch):
    calls = []
    left = {"stable_id": "window:1:7", "geometry_source": "org.cua.WinRects",
            "geometry": {"frame": {"x": 10}}}
    right = {"stable_id": "window:2:8", "geometry": {"frame": {"x": 80}}}
    order = [left, right]

    def observe(names, *, full=False):
        name = next(iter(names))
        calls.append(name)
        if name == "windows":
            return {name: {"source": "org.cua.WinRects", "available": True,
                           "items": list(order),
                           "by_id": {item["stable_id"]: item for item in order}}}
        return {name: {"available": True}}

    monkeypatch.setattr(current_module, "observe", observe)
    current = Current()
    path = "windows.by_id.window:1:7.geometry.frame.x"
    first = current.select([path])
    assert first["values"][path] == 10
    assert first["facts"][path]["evidence"]["source"] == "org.cua.WinRects"
    assert calls == ["windows"]
    order.reverse()
    assert current.select([path], fresh=True)["values"][path] == 10
    assert calls == ["windows", "windows"]
    assert current.world()["windows"]["items"][0]["stable_id"] == "window:2:8"


def test_source_outage_replaces_old_value_with_unavailable(monkeypatch):
    available = True

    def observe(names, *, full=False):
        name = next(iter(names))
        return {name: {"source": "test", "available": available,
                       **({"hostname": "live"} if available else {"reason": "disconnected"})}}

    monkeypatch.setattr(current_module, "observe", observe)
    current = Current(WorldStore())
    assert current.select(["host.hostname"])["values"]["host.hostname"] == "live"
    available = False
    result = current.select(["host"], fresh=True)
    assert result["values"]["host"] == {"source": "test", "available": False,
                                         "reason": "disconnected"}
    assert result["facts"]["host"]["evidence"]["available"] is False
    assert "hostname" not in current.world()["host"]
