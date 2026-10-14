from __future__ import annotations

from dataclasses import dataclass
from threading import Condition, RLock
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
        self._changed = Condition(self._lock)
        self._revision = 0
        self._facts: dict[str, Fact] = {}
        self._changed_at: dict[str, int] = {}
        self._invalidated_at: dict[str, int] = {}

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
        facts = list(facts)
        with self._lock:
            if expected_revision is not None and expected_revision != self._revision:
                raise RevisionConflict(
                    f"expected revision {expected_revision}, current revision {self._revision}"
                )
            changed = False
            changed_keys: list[str] = []
            for fact in facts:
                if self._facts.get(fact.key) != fact:
                    self._facts[fact.key] = fact
                    changed = True
                    changed_keys.append(fact.key)
            if changed:
                self._revision += 1
                for key in changed_keys:
                    self._changed_at[key] = self._revision
                self._changed.notify_all()
            return self._revision

    def invalidate(self, keys: Iterable[str], *, expected_revision: int | None = None) -> int:
        keys = list(keys)
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
                for key in keys:
                    self._invalidated_at[key] = self._revision
                self._changed.notify_all()
            return self._revision


    def fence(self) -> int:
        """Seal the current world so later waits can demand newer evidence."""
        with self._changed:
            self._revision += 1
            self._changed.notify_all()
            return self._revision

    def changed_after(self, key: str, revision: int) -> bool:
        with self._lock:
            return self._changed_at.get(key, 0) > revision

    def invalidated_after(self, key: str, revision: int) -> bool:
        with self._lock:
            return self._invalidated_at.get(key, 0) > revision

    def wait_for(
        self,
        predicate: dict[str, Any],
        *,
        after_revision: int,
        timeout: float,
    ) -> tuple[bool, int]:
        import time as _time

        deadline = _time.monotonic() + timeout
        path = predicate.get("path")
        op = predicate.get("op", "eq")
        want = predicate.get("value")
        if not isinstance(path, str) or not path:
            return False, self.revision

        with self._changed:
            while True:
                fresh_after = predicate.get("fresh_after", after_revision)
                try:
                    fresh_after = int(fresh_after)
                except (TypeError, ValueError):
                    return False, self._revision

                fact = self._facts.get(path)
                # Expired operating facts are no longer valid postconditions.
                if fact is not None and not fact.evidence.valid_at():
                    fact = None
                if op == "changed":
                    ready = self._changed_at.get(path, 0) > fresh_after
                elif op == "invalid":
                    ready = self._invalidated_at.get(path, 0) > fresh_after
                elif op == "exists":
                    ready = fact is not None
                    if predicate.get("fresh_after") is not None:
                        ready = ready and self._changed_at.get(path, 0) > fresh_after
                elif op == "missing":
                    ready = fact is None
                    if predicate.get("fresh_after") is not None:
                        ready = ready and self._invalidated_at.get(path, 0) > fresh_after
                elif op == "ne":
                    ready = fact is not None and fact.value != want
                    if predicate.get("fresh_after") is not None:
                        ready = ready and self._changed_at.get(path, 0) > fresh_after
                else:
                    ready = fact is not None and fact.value == want
                    if predicate.get("fresh_after") is not None:
                        ready = ready and self._changed_at.get(path, 0) > fresh_after

                if ready:
                    return True, self._revision

                remaining = deadline - _time.monotonic()
                if remaining <= 0:
                    return False, self._revision
                self._changed.wait(remaining)
