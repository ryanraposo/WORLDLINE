from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from time import time
from typing import Any, Mapping


class Knowledge(str, Enum):
    KNOWN = "known"
    KNOWABLE = "knowable"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class Evidence:
    source: str
    observed_at: float = field(default_factory=time)
    confidence: float = 1.0
    revision: int | None = None
    expires_at: float | None = None
    detail: Mapping[str, Any] = field(default_factory=dict)

    def valid_at(self, now: float | None = None) -> bool:
        now = time() if now is None else now
        return self.expires_at is None or now <= self.expires_at


@dataclass(frozen=True, slots=True)
class Fact:
    key: str
    value: Any
    evidence: Evidence
    knowledge: Knowledge = Knowledge.KNOWN
    tags: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["knowledge"] = self.knowledge.value
        return data


@dataclass(frozen=True, slots=True)
class Entity:
    id: str
    kind: str
    attributes: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Relationship:
    subject: str
    predicate: str
    object: str
    evidence: Evidence


@dataclass(frozen=True, slots=True)
class Affordance:
    subject: str
    verb: str
    available: bool
    evidence: Evidence
    constraints: Mapping[str, Any] = field(default_factory=dict)
