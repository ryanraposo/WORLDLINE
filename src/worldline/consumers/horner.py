from __future__ import annotations

from typing import Any

from .base import ConsumerAdapter
from worldline.store import Snapshot


class HornerAdapter(ConsumerAdapter):
    name = "horner"

    def project(self, snapshot: Snapshot) -> dict[str, Any]:
        physical = {
            key: fact.to_dict()
            for key, fact in snapshot.facts.items()
            if "physical" in fact.tags or "geometry" in fact.tags or "affordance" in fact.tags
        }
        return {
            "revision": snapshot.revision,
            "physical_world": physical,
            "policy": "consume-world-truth; derive-embodiment-semantics",
        }
