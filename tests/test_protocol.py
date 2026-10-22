from worldline.daemon import WorldlineDaemon


def test_feature_discovery_preserves_legacy_ops():
    daemon = WorldlineDaemon()
    res = daemon.dispatch({"op": "features", "args": {}})
    assert res["ok"]
    for name in ("status", "event", "capture", "arm", "wait", "close"):
        assert name in res["result"]["ops"]


def test_event_then_query():
    daemon = WorldlineDaemon()
    res = daemon.dispatch({"op": "event", "args": {"key": "window.1.focused", "value": True}})
    assert res["ok"]
    res = daemon.dispatch({"op": "query", "args": {}})
    assert res["result"]["facts"]["window.1.focused"]["value"] is True


def test_legacy_query_stays_bounded_while_capture_contains_sections(monkeypatch):
    import worldline.current as current_module
    monkeypatch.setattr(current_module, "observe", lambda names, full=False: {
        "windows": {"available": True, "items": [{"title": "Observed"}]}
    })
    daemon = WorldlineDaemon()
    daemon.current.refresh(["windows"])
    assert "windows" not in daemon.dispatch({"op": "query", "args": {}})["result"]["facts"]
    assert "windows" in daemon.dispatch({"op": "capture", "args": {}})["result"]["facts"]


def test_control_client_passes_selective_query_options(monkeypatch, capsys):
    import sys
    from worldline import control

    received = {}
    def fake_request(path, op, args):
        received.update(path=path, op=op, args=args)
        return {"ok": True, "result": {}}

    monkeypatch.setattr(control, "request", fake_request)
    monkeypatch.setattr(sys, "argv", ["worldlinectl", "--socket", "/tmp/test.sock",
                                       "query", "--path", "windows.active.geometry",
                                       "--fresh"])
    control.main()
    assert received == {"path": "/tmp/test.sock", "op": "query",
                        "args": {"paths": ["windows.active.geometry"], "fresh": True}}
    assert '"ok": true' in capsys.readouterr().out
