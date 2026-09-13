from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterable

from worldline.model import Fact


class ObservationProvider(ABC):
    """Produces world facts. Providers own acquisition mechanics, never global policy."""

    name: str

    @abstractmethod
    def observe(self) -> Iterable[Fact]:
        raise NotImplementedError


class CapabilityProvider(ABC):
    """Discovers/ensures a capability and emits evidence-backed state."""

    name: str

    @abstractmethod
    def probe(self):
        raise NotImplementedError

    def ensure(self):
        """Optional repair/acquisition path. Implementations must be idempotent."""
        return self.probe()
