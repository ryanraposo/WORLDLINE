from __future__ import annotations

from typing import Any

from .base import ConsumerAdapter
from worldline.store import Snapshot


class HermesAdapter(ConsumerAdapter):
    name = "hermes"

    def project(self, snapshot: Snapshot) -> dict[str, Any]:
        return {
            "revision": snapshot.revision,
            "facts": {k: v.to_dict() for k, v in snapshot.facts.items()},
            "policy": "use-known-good-state; verify-on-conflict",
        }
