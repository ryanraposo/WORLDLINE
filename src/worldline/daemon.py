from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import socket
import stat
from pathlib import Path
from typing import Any

from .current import Current
from .model import Evidence, Fact
from .protocol import CORE_OPS, PROTOCOL_VERSION, Request, error, ok
from .query import QueryError
from .store import WorldStore
from .providers.gnome import GNOMEProvider


class WorldlineDaemon:
    def __init__(self, store: WorldStore | None = None) -> None:
        self.store = store or WorldStore()
        self.current = Current(self.store)
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
                    "query": {"paths": True, "fresh": True,
                              "views": ["world"], "legacy_default": True},
                },
            )
        if req.op == "observe":
            provider_name = str(req.args.get("provider", "gnome"))
            if provider_name == "current":
                try:
                    revision = self.current.refresh(req.args.get("sections"))
                except KeyError as exc:
                    return error(req, "bad_request", str(exc))
                return ok(req, {"provider": "current", "revision": revision})
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
            paths = req.args.get("paths")
            if paths is not None:
                if req.op != "query" or not isinstance(paths, list) or not paths or not all(
                    isinstance(path, str) and path for path in paths
                ):
                    return error(req, "bad_request", "query paths must be a nonempty string list")
                try:
                    return ok(req, self.current.select(
                        paths, fresh=req.args.get("fresh") is True,
                        full=req.args.get("full") is True,
                    ))
                except QueryError as exc:
                    return error(req, "no_such_path", str(exc))
                except KeyError as exc:
                    return error(req, "bad_request", str(exc))
            if req.args.get("view") == "world":
                self.current.ensure(fresh=req.args.get("fresh") is True,
                                    full=req.args.get("full") is True)
                return ok(req, self.current.world())
            snapshot = self.store.snapshot().to_dict()
            if req.op == "query":
                snapshot["facts"] = {
                    key: fact for key, fact in snapshot["facts"].items()
                    if "observation-section" not in fact.get("tags", [])
                }
            return ok(req, snapshot)
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
                    if raw.get("op") == "wait":
                        args = dict(raw.get("args") or {})
                        try:
                            deadline = asyncio.get_running_loop().time() + max(
                                0.001, min(float(args.get("timeout", 5.0)), 120.0))
                        except (TypeError, ValueError):
                            deadline = asyncio.get_running_loop().time()
                        while True:
                            short = {**raw, "args": {**args, "timeout": 0.001}}
                            response = self.dispatch(short)
                            if not response.get("ok") or response["result"].get("state") == "ready":
                                break
                            if asyncio.get_running_loop().time() >= deadline:
                                break
                            await asyncio.sleep(0.05)
                    else:
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
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.exists():
        info = path.stat()
        if not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.getuid():
            raise RuntimeError(f"refusing to replace non-owned socket: {path}")
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as probe:
            probe.settimeout(0.2)
            try:
                probe.connect(str(path))
            except ConnectionRefusedError:
                path.unlink()
            else:
                raise RuntimeError(f"WORLDLINE daemon already listening: {path}")
    daemon = WorldlineDaemon()
    daemon.current.refresh()
    daemon.dispatch({"op": "observe", "args": {"provider": "gnome"}})
    server = await asyncio.start_unix_server(daemon.handle, path=str(path))
    os.chmod(path, 0o600)
    async def reconcile() -> None:
        ticks = 0
        while True:
            await asyncio.sleep(2)
            ticks += 1
            daemon.current.ensure()
            if ticks % 15 == 0:
                daemon.dispatch({"op": "observe", "args": {"provider": "gnome"}})

    async def native_events() -> None:
        if not shutil.which("gdbus") or not os.environ.get("DBUS_SESSION_BUS_ADDRESS"):
            return
        while True:
            process = await asyncio.create_subprocess_exec(
                "gdbus", "monitor", "--session", "--dest", "org.gnome.Shell",
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
            )
            assert process.stdout is not None
            try:
                async for line in process.stdout:
                    if b"signal" in line:
                        daemon.current.refresh(["desktop", "windows"])
            finally:
                if process.returncode is None:
                    process.terminate()
                    await process.wait()
            await asyncio.sleep(5)

    reconciliation = asyncio.create_task(reconcile())
    events = asyncio.create_task(native_events())
    async with server:
        try:
            await server.serve_forever()
        finally:
            reconciliation.cancel()
            events.cancel()


def default_socket() -> str:
    runtime = os.environ.get("XDG_RUNTIME_DIR", f"/tmp/worldline-{os.getuid()}")
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
