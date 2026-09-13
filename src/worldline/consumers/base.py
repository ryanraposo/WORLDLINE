from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from worldline.store import Snapshot


class ConsumerAdapter(ABC):
    """Projects canonical WORLDLINE truth into a consumer-specific view."""

    name: str

    @abstractmethod
    def project(self, snapshot: Snapshot) -> dict[str, Any]:
        raise NotImplementedError
