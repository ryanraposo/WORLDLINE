from worldline.model import Evidence, Fact
from worldline.store import RevisionConflict, WorldStore


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

def test_expired_fact_cannot_satisfy_wait_postcondition():
    store = WorldStore()
    store.apply([Fact("gnome.windows.source.available", True, Evidence(
        "test", expires_at=1,
    ))])
    ready, _revision = store.wait_for(
        {"path": "gnome.windows.source.available", "op": "eq", "value": True},
        after_revision=0, timeout=0.01,
    )
    assert not ready
