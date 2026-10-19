from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
from typing import Any

from .model import Evidence, Fact
from .protocol import CORE_OPS, PROTOCOL_VERSION, Request, error, ok
from .store import WorldStore
from .providers.gnome import GNOMEProvider


class WorldlineDaemon:
    def __init__(self, store: WorldStore | None = None) -> None:
        self.store = store or WorldStore()
        self._closing = False
        self.providers = {"gnome": GNOMEProvider()}

    def dispatch(self, raw: dict[str, Any]) -> dict[str, Any]:
        req = Request.from_dict(raw)
        if req.protocol != PROTOCOL_VERSION:
            return error(
                req, "protocol_mismatch", f"supported protocol is {PROTOCOL_VERSION}"
            )
        if req.op not in CORE_OPS:
            return error(req, "unknown_op", req.op)
        if req.op in {"hello", "features"}:
            return ok(
                req,
                {
                    "protocol": PROTOCOL_VERSION,
                    "ops": sorted(CORE_OPS),
                    "compatibility": ["embedded-worldline-six-op"],
                    "extension_model": [
                        "providers",
                        "consumers",
                        "facts",
                        "capabilities",
                        "affordances",
                    ],
                    "providers": sorted(self.providers),
                },
            )
        if req.op == "observe":
            provider_name = str(req.args.get("provider", "gnome"))
            provider = self.providers.get(provider_name)
            if provider is None:
                return error(req, "unknown_provider", provider_name)
            facts = list(provider.observe())
            revision = self.store.apply(
                facts, expected_revision=req.args.get("expected_revision")
            )
            return ok(
                req,
                {
                    "provider": provider_name,
                    "revision": revision,
                    "fact_count": len(facts),
                },
            )
        if req.op == "fence":
            revision = self.store.fence()
            return ok(req, {"revision": revision, "code": "fenced"})
        if req.op == "status":
            snap = self.store.snapshot()
            return ok(req, {"revision": snap.revision, "fact_count": len(snap.facts)})
        if req.op in {"query", "capture"}:
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
            revision = self.store.apply(
                [fact], expected_revision=req.args.get("expected_revision")
            )
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
                    return error(
                        req, "invalid_wait", "wait requires predicate or predicates"
                    )
            after = req.args.get("after_revision", self.store.revision)
            try:
                after = int(after)
                timeout = max(0.001, min(float(req.args.get("timeout", 5.0)), 120.0))
            except (TypeError, ValueError):
                return error(
                    req, "invalid_wait", "after_revision and timeout must be numeric"
                )
            ready, revision = self.store.wait_for(
                predicate, after_revision=after, timeout=timeout
            )
            return ok(
                req,
                {
                    "revision": revision,
                    "state": "ready" if ready else "timeout",
                    "predicate": predicate,
                    "after_revision": after,
                },
            )
        if req.op == "close":
            self._closing = True
            return ok(req, {"closing": True})
        return error(req, "unimplemented", req.op)

    async def handle(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        try:
            while not reader.at_eof():
                line = await reader.readline()
                if not line:
                    break
                try:
                    raw = json.loads(line)
                    response = self.dispatch(raw)
                except (
                    Exception
                ) as exc:  # boundary: never tear down daemon on malformed request
                    response = {
                        "ok": False,
                        "protocol": PROTOCOL_VERSION,
                        "error": {"code": "bad_request", "message": str(exc)},
                    }
                writer.write(
                    (json.dumps(response, separators=(",", ":")) + "\n").encode()
                )
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
    parser = argparse.ArgumentParser(
        description="WORLDLINE: Operating Fact. observation daemon"
    )
    parser.add_argument("--socket", default=default_socket())
    args = parser.parse_args()
    try:
        asyncio.run(serve(args.socket))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
