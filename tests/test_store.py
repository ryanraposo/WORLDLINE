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
