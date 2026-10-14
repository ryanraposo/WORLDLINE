from __future__ import annotations

import argparse
import asyncio
import json
import os
from collections import defaultdict
from threading import Lock
from time import monotonic, time
from pathlib import Path
from typing import Any

from .model import Evidence, Fact
from .protocol import CORE_OPS, PROTOCOL_VERSION, Request, error, ok
from .store import WorldStore
from .providers.gnome import GNOMEProvider
from .sources import provider_description


class WorldlineDaemon:
    def __init__(self, store: WorldStore | None = None) -> None:
        self.store = store or WorldStore()
        self._closing = False
        self.providers = {"gnome": GNOMEProvider()}
        self.provider_readings: dict[str, dict] = {}
        self._provider_guards = defaultdict(Lock)
        self._blocking_slots = asyncio.Semaphore(4)

    def _observe_provider(self, provider_name: str, *, mode: str = "active") -> tuple[int, int]:
        provider = self.providers[provider_name]
        if mode not in ("active", "fast"):
            raise ValueError("unsupported observation mode")
        read = (getattr(provider, "observe_fast", None)
                if mode == "fast" else provider.observe)
        if not callable(read):
            raise ValueError("provider does not support fast observation")
        # Avoid overlapping slow reads of the same native producer. Refreshes
        # still take new samples; we do not silently reuse pre-fence evidence.
        with self._provider_guards[provider_name]:
            before = monotonic()
            try:
                facts = list(read())
                # Apply a coherent source transaction. A failed read never
                # withdraws previously valid facts as though the source reported
                # an empty world.
                managed = set(getattr(provider, "managed_keys", ()))
                revision = self.store.reconcile(facts, managed_keys=managed)
            except Exception as exc:
                # Diagnostics record the failure category without leaking details
                # that may contain private command output or file content.
                self.provider_readings[provider_name] = {
                    "mode": mode, "ok": False, "error_type": type(exc).__name__,
                    "duration_ms": round((monotonic() - before) * 1000, 2),
                    "attempted_at": time(),
                }
                raise
            self.provider_readings[provider_name] = {
                "mode": mode, "ok": True, "fact_count": len(facts),
                "duration_ms": round((monotonic() - before) * 1000, 2),
                "attempted_at": time(), "revision": revision,
            }
            return revision, len(facts)

    def dispatch(self, raw: dict[str, Any]) -> dict[str, Any]:
        req = Request.from_dict(raw)
        if req.protocol != PROTOCOL_VERSION:
            return error(req, "protocol_mismatch", f"supported protocol is {PROTOCOL_VERSION}")
        if req.op not in CORE_OPS:
            return error(req, "unknown_op", req.op)
        if req.op in {"hello", "features"}:
            return ok(req, {
                "protocol": PROTOCOL_VERSION,
                "ops": sorted(CORE_OPS),
                "compatibility": ["embedded-worldline-six-op"],
                "extension_model": ["providers", "consumers", "facts", "capabilities", "affordances"],
                "providers": sorted(self.providers),
                "source_catalog": True,
                "observation_modes": ["fast", "active"],
            })
        if req.op == "sources":
            return ok(req, {
                "providers": [provider_description(self.providers[name])
                              for name in sorted(self.providers)],
                "last_reads": dict(self.provider_readings),
                "interpretation": "source observations only; no logical entity associations",
            })
        if req.op == "observe":
            provider_name = str(req.args.get("provider", "gnome"))
            provider = self.providers.get(provider_name)
            if provider is None:
                return error(req, "unknown_provider", provider_name)
            expected_revision = req.args.get("expected_revision")
            if expected_revision is not None and expected_revision != self.store.revision:
                return error(req, "revision_conflict", "expected revision does not match")
            mode = req.args.get("mode", "active")
            if not isinstance(mode, str) or mode not in ("active", "fast"):
                return error(req, "invalid_mode", "mode must be active or fast")
            if mode == "fast" and not callable(getattr(provider, "observe_fast", None)):
                return error(req, "unsupported_mode", "provider does not offer a direct fast read")
            try:
                revision, count = self._observe_provider(provider_name, mode=mode)
            except Exception:
                return error(req, "observation_failed", "provider could not complete read")
            return ok(req, {
                "provider": provider_name,
                "revision": revision,
                "fact_count": count,
                "mode": mode,
            })
        if req.op == "fence":
            revision = self.store.fence()
            return ok(req, {"revision": revision, "code": "fenced"})
        if req.op == "status":
            snap = self.store.snapshot()
            return ok(req, {"revision": snap.revision, "fact_count": len(snap.facts)})
        if req.op in {"query", "capture"}:
            selected = req.args.get("refresh", [])
            if not isinstance(selected, list) or len(selected) > 8 or any(
                not isinstance(name, str) for name in selected
            ):
                return error(req, "invalid_refresh", "refresh must be a provider name list")
            unknown = next((name for name in selected if name not in self.providers), None)
            if unknown is not None:
                return error(req, "unknown_provider", unknown)
            mode = req.args.get("mode", "active")
            if not isinstance(mode, str) or mode not in ("active", "fast"):
                return error(req, "invalid_mode", "mode must be active or fast")
            unsupported = next((name for name in selected if mode == "fast"
                                and not callable(getattr(self.providers[name], "observe_fast", None))), None)
            if unsupported is not None:
                return error(req, "unsupported_mode", f"{unsupported} does not offer a direct fast read")
            for name in dict.fromkeys(selected):
                try:
                    self._observe_provider(name, mode=mode)
                except Exception:
                    return error(req, "observation_failed", f"{name} could not complete read")
            return ok(req, self.store.snapshot().to_dict())
        if req.op == "event":
            key = str(req.args["key"])
            fact = Fact(
                key=key,
                value=req.args.get("value"),
                evidence=Evidence(
                    source=str(req.args.get("source", "rpc:event")),
                    confidence=float(req.args.get("confidence", 1.0)),
                    expires_at=req.args.get("expires_at"),
                ),
                tags=tuple(req.args.get("tags") or ()),
            )
            revision = self.store.apply([fact], expected_revision=req.args.get("expected_revision"))
            return ok(req, {"revision": revision})
        if req.op == "arm":
            return ok(req, {"armed": True, "revision": self.store.revision})
        if req.op == "wait":
            predicate = req.args.get("predicate")
            if not isinstance(predicate, dict):
                predicates = req.args.get("predicates")
                if isinstance(predicates, list) and predicates:
                    predicate = predicates[0]
                else:
                    return error(req, "invalid_wait", "wait requires predicate or predicates")
            after = req.args.get("after_revision", self.store.revision)
            try:
                after = int(after)
                timeout = max(0.001, min(float(req.args.get("timeout", 5.0)), 120.0))
            except (TypeError, ValueError):
                return error(req, "invalid_wait", "after_revision and timeout must be numeric")
            ready, revision = self.store.wait_for(predicate, after_revision=after, timeout=timeout)
            return ok(req, {
                "revision": revision,
                "state": "ready" if ready else "timeout",
                "predicate": predicate,
                "after_revision": after,
            })
        if req.op == "close":
            self._closing = True
            return ok(req, {"closing": True})
        return error(req, "unimplemented", req.op)

    async def handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            while not reader.at_eof():
                line = await reader.readline()
                if not line:
                    break
                try:
                    raw = json.loads(line)
                    op = raw.get("op") if isinstance(raw, dict) else None
                    args = raw.get("args") if isinstance(raw, dict) else None
                    blocking = (
                        op in {"observe", "wait"} or
                        (op in {"query", "capture"} and
                         isinstance(args, dict) and bool(args.get("refresh")))
                    )
                    if blocking:
                        # Service/CLI probes and condition waits must never
                        # stall cached query/status/hello clients on the loop.
                        async with self._blocking_slots:
                            response = await asyncio.to_thread(self.dispatch, raw)
                    else:
                        response = self.dispatch(raw)
                except Exception as exc:  # boundary: never tear down daemon on malformed request
                    response = {"ok": False, "protocol": PROTOCOL_VERSION,
                                "error": {"code": "bad_request", "message": str(exc)}}
                writer.write((json.dumps(response, separators=(",", ":")) + "\n").encode())
                await writer.drain()
                if self._closing:
                    break
        finally:
            writer.close()
            await writer.wait_closed()


async def serve(socket_path: str) -> None:
    path = Path(socket_path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.unlink()
    except FileNotFoundError:
        pass
    daemon = WorldlineDaemon()
    server = await asyncio.start_unix_server(daemon.handle, path=str(path))
    os.chmod(path, 0o600)
    async with server:
        await server.serve_forever()


def default_socket() -> str:
    runtime = os.environ.get("XDG_RUNTIME_DIR", "/tmp")
    return f"{runtime}/worldline/worldline.sock"


def main() -> None:
    parser = argparse.ArgumentParser(description="WORLDLINE daemon")
    parser.add_argument("--socket", default=default_socket())
    args = parser.parse_args()
    try:
        asyncio.run(serve(args.socket))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
