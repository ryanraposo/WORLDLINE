from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

from .store import RevisionConflict, Snapshot, WorldStore


Predicate = Callable[[Snapshot], bool]
Action = Callable[[], Any]


class PreconditionFailed(RuntimeError):
    pass


class PostconditionFailed(RuntimeError):
    pass


@dataclass(slots=True)
class Step:
    name: str
    action: Action
    preconditions: tuple[Predicate, ...] = ()
    postconditions: tuple[Predicate, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class StepReceipt:
    name: str
    before_revision: int
    after_revision: int
    result: Any


class Executor:
    """Small deterministic OCC executor; providers perform the actual observation/actuation."""

    def __init__(self, store: WorldStore) -> None:
        self.store = store

    def run(self, steps: Iterable[Step]) -> list[StepReceipt]:
        receipts: list[StepReceipt] = []
        for step in steps:
            before = self.store.snapshot()
            if not all(pred(before) for pred in step.preconditions):
                raise PreconditionFailed(step.name)
            result = step.action()
            after = self.store.snapshot()
            if after.revision < before.revision:
                raise RevisionConflict("world revision moved backwards")
            if not all(pred(after) for pred in step.postconditions):
                raise PostconditionFailed(step.name)
            receipts.append(StepReceipt(step.name, before.revision, after.revision, result))
        return receipts
