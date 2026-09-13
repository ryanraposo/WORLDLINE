from __future__ import annotations

from dataclasses import dataclass
from threading import RLock
from time import time
from typing import Any, Iterable

from .model import Fact


class RevisionConflict(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class Snapshot:
    revision: int
    facts: dict[str, Fact]
    captured_at: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "revision": self.revision,
            "captured_at": self.captured_at,
            "facts": {key: fact.to_dict() for key, fact in self.facts.items()},
        }


class WorldStore:
    """Thread-safe, revisioned fact store with optimistic compare-and-swap writes."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._revision = 0
        self._facts: dict[str, Fact] = {}

    @property
    def revision(self) -> int:
        with self._lock:
            return self._revision

    def snapshot(self, *, valid_only: bool = True) -> Snapshot:
        now = time()
        with self._lock:
            facts = {
                key: fact
                for key, fact in self._facts.items()
                if not valid_only or fact.evidence.valid_at(now)
            }
            return Snapshot(self._revision, facts, now)

    def get(self, key: str, *, valid_only: bool = True) -> Fact | None:
        with self._lock:
            fact = self._facts.get(key)
            if fact is None:
                return None
            if valid_only and not fact.evidence.valid_at():
                return None
            return fact

    def apply(self, facts: Iterable[Fact], *, expected_revision: int | None = None) -> int:
        with self._lock:
            if expected_revision is not None and expected_revision != self._revision:
                raise RevisionConflict(
                    f"expected revision {expected_revision}, current revision {self._revision}"
                )
            changed = False
            for fact in facts:
                if self._facts.get(fact.key) != fact:
                    self._facts[fact.key] = fact
                    changed = True
            if changed:
                self._revision += 1
            return self._revision

    def invalidate(self, keys: Iterable[str], *, expected_revision: int | None = None) -> int:
        with self._lock:
            if expected_revision is not None and expected_revision != self._revision:
                raise RevisionConflict(
                    f"expected revision {expected_revision}, current revision {self._revision}"
                )
            changed = False
            for key in keys:
                changed |= self._facts.pop(key, None) is not None
            if changed:
                self._revision += 1
            return self._revision
