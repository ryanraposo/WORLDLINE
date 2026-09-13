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
