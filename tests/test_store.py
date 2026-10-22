from worldline.model import Evidence, Fact
from worldline.store import RevisionConflict, WorldStore
from time import time


def test_revision_changes_only_on_change():
    store = WorldStore()
    fact = Fact("app.chrome.running", True, Evidence("test"))
    assert store.apply([fact]) == 1
    assert store.apply([fact]) == 1
    assert store.snapshot().revision == 1


def test_optimistic_conflict():
    store = WorldStore()
    store.apply([Fact("x", 1, Evidence("test"))])
    try:
        store.apply([Fact("x", 2, Evidence("test"))], expected_revision=0)
    except RevisionConflict:
        pass
    else:
        raise AssertionError("expected RevisionConflict")


def test_fence_prevents_cached_truth_from_satisfying_fresh_wait():
    store = WorldStore()
    fact = Fact("task.done", True, Evidence("test"))
    store.apply([fact])
    fence = store.fence()

    ready, revision = store.wait_for(
        {"path": "task.done", "op": "eq", "value": True, "fresh_after": fence},
        after_revision=fence,
        timeout=0.01,
    )
    assert not ready
    assert revision >= fence

    store.apply([Fact("task.done", True, Evidence("test-2"))])
    ready, revision = store.wait_for(
        {"path": "task.done", "op": "eq", "value": True, "fresh_after": fence},
        after_revision=fence,
        timeout=0.01,
    )
    assert ready
    assert revision > fence


def test_fresh_wait_accepts_new_evidence_for_equality():
    store = WorldStore()
    store.apply([Fact("task.done", False, Evidence("seed"))])
    fence = store.fence()
    store.apply([Fact("task.done", True, Evidence("fresh"))])

    ready, revision = store.wait_for(
        {"path": "task.done", "op": "eq", "value": True, "fresh_after": fence},
        after_revision=fence,
        timeout=0.01,
    )
    assert ready
    assert revision > fence


def test_refresh_is_fresh_evidence_without_claiming_value_changed():
    store = WorldStore()
    store.apply([Fact("window.7.x", 10, Evidence("mutter", observed_at=1))])
    fence = store.fence()
    store.apply([Fact("window.7.x", 10, Evidence("mutter", observed_at=2))])
    assert not store.changed_after("window.7.x", fence)
    fresh, _ = store.wait_for(
        {"path": "window.7.x", "op": "eq", "value": 10,
         "fresh_after": fence}, after_revision=fence, timeout=0.01,
    )
    assert fresh


def test_expired_evidence_cannot_satisfy_value_wait():
    store = WorldStore()
    store.apply([Fact("window.x", 10, Evidence("test", expires_at=time() - 1))])
    ready, _ = store.wait_for(
        {"path": "window.x", "op": "eq", "value": 10},
        after_revision=0, timeout=0.01,
    )
    assert not ready
    ready, _ = store.wait_for(
        {"path": "window.x", "op": "exists"},
        after_revision=0, timeout=0.01,
    )
    assert not ready
