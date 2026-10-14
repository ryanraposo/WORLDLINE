"""Provider-described observation surfaces; no consumer or entity identities.

Descriptions document *where* and *how* a source can be observed. They are
not permission to bypass a service API or evidence that a source is currently
available. Queries of this catalogue perform no observation.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal


Acquisition = Literal["direct_read", "native_event", "service_query"]
Cost = Literal["negligible", "bounded", "expensive"]


@dataclass(frozen=True, slots=True)
class SourceSurface:
    name: str
    origin: str
    acquisition: Acquisition
    cost: Cost
    facts: tuple[str, ...]
    detail: str = ""
    # A source-backed API is sometimes the *only* place truth is exposed.
    # A direct read is preferable only where it is equally authoritative.
    authoritative_interface: bool = True

    def to_dict(self) -> dict:
        return asdict(self)


def provider_description(provider: object) -> dict:
    """Describe actual implemented observation, never imagined interfaces."""
    catalog = getattr(provider, "source_surfaces", ())
    modes = ["active"]
    if callable(getattr(provider, "observe_fast", None)):
        modes.insert(0, "fast")
    return {
        "name": str(getattr(provider, "name", "unknown")),
        "modes": modes,
        "surfaces": [surface.to_dict() for surface in catalog],
    }
