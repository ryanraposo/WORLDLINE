"""One observation pipeline for the command and the persistent service."""

from __future__ import annotations

from threading import RLock
from time import time
from typing import Any, Iterable

from .model import Evidence, Fact
from .observe import SCHEMA, observe, sections
from .query import QueryError, normalize, resolve, top_level
from .store import WorldStore

SECTION_TTL = {"time": 1.0, "windows": 2.0, "desktop": 5.0, "processes": 5.0}
DEFAULT_TTL = 30.0


class Current:
    def __init__(self, store: WorldStore | None = None) -> None:
        self.store = store or WorldStore()
        self._lock = RLock()
        self._refreshed: dict[str, float] = {}

    def refresh(self, names: Iterable[str] | None = None, *, full: bool = False) -> int:
        requested = list(sections() if names is None else names)
        unknown = set(requested).difference(sections())
        if unknown:
            raise KeyError(f"unknown section: {', '.join(sorted(unknown))}")
        with self._lock:
            for name in requested:
                observed = observe([name], full=full and name == "processes")
                value = observed.get(name)
                if value is None:
                    failure = next((item["error"] for item in observed.get("errors", [])
                                    if item["section"] == name), "source unavailable")
                    value = {"available": False, "reason": failure}
                source = value.get("source", name) if isinstance(value, dict) else name
                now = time()
                self.store.apply([Fact(
                    key=name, value=value,
                    evidence=Evidence(source=str(source), observed_at=now,
                                      expires_at=now + SECTION_TTL.get(name, DEFAULT_TTL)),
                    tags=("observation-section",),
                )])
                self._refreshed[name] = now
            return self.store.revision

    def ensure(self, names: Iterable[str] | None = None, *, fresh: bool = False,
               full: bool = False) -> int:
        requested = list(sections() if names is None else names)
        now = time()
        stale = [name for name in requested if fresh or full and name == "processes"
                 or now - self._refreshed.get(name, 0) >= SECTION_TTL.get(name, DEFAULT_TTL)]
        if stale:
            return self.refresh(stale, full=full)
        return self.store.revision

    def world(self) -> dict[str, Any]:
        snapshot = self.store.snapshot()
        world: dict[str, Any] = {
            "schema": SCHEMA,
            "collected_at": snapshot.captured_at,
            "revision": snapshot.revision,
        }
        sources: dict[str, Any] = {}
        for name in sections():
            fact = snapshot.facts.get(name)
            if fact is None:
                world[name] = {"available": False, "reason": "unobserved_or_expired"}
                sources[name] = {"available": False, "reason": "unobserved_or_expired"}
                continue
            world[name] = fact.value
            value = fact.value
            available = not (isinstance(value, dict) and value.get("available") is False)
            sources[name] = {
                "available": available,
                "source": fact.evidence.source,
                "observed_at": fact.evidence.observed_at,
                "expires_at": fact.evidence.expires_at,
                "reason": value.get("reason") if not available else None,
            }
            if name == "windows" and isinstance(value, dict):
                sources[name]["sources"] = value.get("sources", {})
        world["sources"] = sources
        return world

    def select(self, paths: Iterable[str], *, fresh: bool = False,
               full: bool = False) -> dict[str, Any]:
        requested = list(paths)
        wanted = top_level(requested)
        metadata = {"schema", "collected_at", "revision", "sources"}
        unknown = wanted.difference(sections()).difference(metadata)
        if unknown:
            raise KeyError(f"unknown section: {', '.join(sorted(unknown))}")
        source_names = set()
        for path in requested:
            parts = normalize(path)
            if parts[0] == "sources":
                source_names.update(sections() if len(parts) == 1 or parts[1] == "*"
                                    else [parts[1]])
        self.ensure(wanted.intersection(sections()) | source_names,
                    fresh=fresh, full=full)
        world = self.world()
        values: dict[str, Any] = {}
        facts: dict[str, Any] = {}
        for path in requested:
            value = resolve(world, path)
            name = path.split(".", 1)[0].split("[", 1)[0]
            source = world["sources"].get(name)
            if source is None:
                source = {"available": True, "source": "worldline",
                          "observed_at": world["collected_at"], "expires_at": None,
                          "reason": None}
            source = dict(source)
            if name == "windows" and "geometry" in normalize(path):
                parts = normalize(path)
                window = None
                if len(parts) > 2 and parts[1] == "by_id":
                    window = world["windows"].get("by_id", {}).get(parts[2])
                elif len(parts) > 2 and parts[1] == "items":
                    try:
                        window = world["windows"]["items"][int(parts[2])]
                    except (ValueError, IndexError, KeyError):
                        pass
                source["source"] = (window or {}).get("geometry_source") or world["windows"].get("geometry_source", source["source"])
            values[path] = value
            facts[path] = {"path": path, "value": value, "revision": world["revision"],
                           "evidence": source}
        return {"revision": world["revision"], "values": values, "facts": facts}
