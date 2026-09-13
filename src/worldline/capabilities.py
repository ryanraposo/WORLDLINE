from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from time import time
from typing import Any, Mapping

from .model import Evidence


class Readiness(IntEnum):
    UNKNOWN = 0
    INSTALLED = 1
    ALIVE = 2
    CONNECTED = 3
    FUNCTIONAL = 4
    INTEGRATED = 5


@dataclass(frozen=True, slots=True)
class CapabilityState:
    name: str
    readiness: Readiness
    evidence: Evidence
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @property
    def ready(self) -> bool:
        return self.readiness >= Readiness.INTEGRATED and self.evidence.valid_at()

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "readiness": self.readiness.name.lower(),
            "ready": self.ready,
            "evidence_valid": self.evidence.valid_at(time()),
            "evidence": {
                "source": self.evidence.source,
                "observed_at": self.evidence.observed_at,
                "confidence": self.evidence.confidence,
                "expires_at": self.evidence.expires_at,
                "detail": dict(self.evidence.detail),
            },
            "metadata": dict(self.metadata),
        }
