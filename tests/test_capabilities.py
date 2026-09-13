from time import time

from worldline.capabilities import CapabilityState, Readiness
from worldline.model import Evidence


def test_false_green_expires():
    state = CapabilityState(
        "browser",
        Readiness.INTEGRATED,
        Evidence("probe", expires_at=time() - 1),
    )
    assert state.ready is False


def test_integrated_current_evidence_is_ready():
    state = CapabilityState("browser", Readiness.INTEGRATED, Evidence("probe"))
    assert state.ready is True
