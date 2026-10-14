from __future__ import annotations

from worldline.daemon import WorldlineDaemon
from worldline.model import Evidence, Fact
from worldline.sources import SourceSurface
from worldline.store import WorldStore


class FastObserver:
    name = "test-observer"
    managed_keys = ("test.a", "test.b")
    source_surfaces = (
        SourceSurface("native", "in-memory test source", "direct_read",
                      "negligible", ("test.a", "test.b")),
    )

    def __init__(self):
        self.calls = []
        self.facts = [Fact("test.a", 1, Evidence("native"))]

    def observe_fast(self):
        self.calls.append("fast")
        return list(self.facts)

    def observe(self):
        self.calls.append("active")
        return list(self.facts)


def test_source_catalogue_is_discovery_not_observation():
    daemon = WorldlineDaemon()
    observer = FastObserver()
    daemon.providers[observer.name] = observer
    catalog = daemon.dispatch({"op": "sources", "args": {}})
    assert catalog["ok"]
    info = next(x for x in catalog["result"]["providers"] if x["name"] == observer.name)
    assert info["modes"] == ["fast", "active"]
    assert info["surfaces"][0]["acquisition"] == "direct_read"
    assert observer.calls == []


def test_cheap_read_never_calls_external_active_path():
    daemon = WorldlineDaemon()
    observer = FastObserver()
    daemon.providers[observer.name] = observer
    result = daemon.dispatch({
        "op": "query", "args": {"refresh": [observer.name], "mode": "fast"},
    })
    assert result["ok"]
    assert observer.calls == ["fast"]
    assert result["result"]["facts"]["test.a"]["value"] == 1


def test_unadvertised_fast_mode_is_not_silently_active():
    class ActiveOnly:
        name = "active-only"
        def observe(self):
            raise AssertionError("should not call active from a fast request")
    daemon = WorldlineDaemon()
    daemon.providers["active-only"] = ActiveOnly()
    result = daemon.dispatch({"op": "observe", "args": {
        "provider": "active-only", "mode": "fast",
    }})
    assert result["error"]["code"] == "unsupported_mode"


def test_atomic_source_reconciliation_and_withdrawal():
    store = WorldStore()
    a = Fact("test.a", 1, Evidence("native"))
    b = Fact("test.b", 2, Evidence("native"))
    assert store.reconcile([a, b], managed_keys=("test.a", "test.b")) == 1
    assert store.reconcile([a], managed_keys=("test.a", "test.b")) == 2
    assert "test.b" not in store.snapshot().facts
    assert store.invalidated_after("test.b", 1)
    assert store.reconcile([a], managed_keys=("test.a", "test.b")) == 2


def test_bad_sample_does_not_erase_valid_facts():
    store = WorldStore()
    value = Fact("test.a", "ok", Evidence("native"))
    store.reconcile([value], managed_keys=("test.a",))
    try:
        store.reconcile([
            Fact("test.a", "new", Evidence("native")),
            Fact("test.z", "foreign", Evidence("native")),
        ], managed_keys=("test.a",))
    except ValueError:
        pass
    else:
        raise AssertionError("invalid provider sample was accepted")
    assert store.snapshot().facts["test.a"].value == "ok"


def test_observe_fast_tracks_duration_and_revisions():
    daemon = WorldlineDaemon()
    observer = FastObserver()
    daemon.providers[observer.name] = observer
    result = daemon.dispatch({"op": "observe", "args": {
        "provider": observer.name, "mode": "fast",
    }})
    assert result["ok"] and result["result"]["mode"] == "fast"
    sources = daemon.dispatch({"op": "sources", "args": {}})["result"]
    recorded = sources["last_reads"][observer.name]
    assert recorded["ok"] and recorded["mode"] == "fast"
    assert recorded["duration_ms"] >= 0


def test_reader_failure_does_not_invalidate_previously_collected_evidence():
    daemon = WorldlineDaemon()
    observer = FastObserver()
    daemon.providers[observer.name] = observer
    first = daemon.dispatch({"op": "observe", "args": {"provider": observer.name}})
    assert first["ok"]
    def broken():
        raise RuntimeError("source temporarily unavailable")
    observer.observe = broken
    failure = daemon.dispatch({"op": "observe", "args": {"provider": observer.name}})
    assert not failure["ok"]
    assert failure["error"]["code"] == "observation_failed"
    cached = daemon.dispatch({"op": "query", "args": {}})
    assert cached["result"]["facts"]["test.a"]["value"] == 1
    status = daemon.dispatch({"op": "sources", "args": {}})["result"]["last_reads"][observer.name]
    assert status["ok"] is False and status["error_type"] == "RuntimeError"


def test_native_stale_read_is_not_implicitly_replayed_for_post_fence_refresh():
    daemon = WorldlineDaemon()
    observer = FastObserver()
    daemon.providers[observer.name] = observer
    daemon.dispatch({"op": "observe", "args": {"provider": observer.name, "mode": "fast"}})
    revision = daemon.dispatch({"op": "fence", "args": {}})["result"]["revision"]
    observer.facts = [Fact("test.a", 1, Evidence("native-new"))]
    result = daemon.dispatch({"op": "query", "args": {
        "refresh": [observer.name], "mode": "fast",
    }})
    assert result["ok"]
    assert result["result"]["revision"] > revision
    assert observer.calls == ["fast", "fast"]
