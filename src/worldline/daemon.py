from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import socket
import stat
from collections import defaultdict
from threading import Lock
from time import monotonic, time
from pathlib import Path
from typing import Any
from uuid import uuid4

from .current import Current
from .model import Evidence, Fact
from .protocol import CORE_OPS, PROTOCOL_VERSION, Request, error, ok
from .query import QueryError
from .store import RevisionConflict, WorldStore
from .providers.gnome import GNOMEProvider
from .providers.host import HostRuntimeProvider
from .sources import provider_description
from .desktop_events import apply_event, capture_visual, compositor_focus_fact, direct_facts, start_atspi_sensor


class WorldlineDaemon:
    def __init__(self, store: WorldStore | None = None) -> None:
        self.store = store or WorldStore()
        self.domain_id = str(uuid4())
        self.current = Current(self.store)
        self._closing = False
        self.providers = {"gnome": GNOMEProvider(), "host": HostRuntimeProvider()}
        self.provider_readings: dict[str, dict[str, Any]] = {}
        self._provider_guards = defaultdict(Lock)
        self._blocking_slots = asyncio.Semaphore(4)
        self._armed: dict[str, dict[str, Any]] = {}

    def _sample(self, args: dict[str, Any]) -> dict[str, Any]:
        start = self.store.revision
        self.store.apply(direct_facts(pids=args.get("pids"), paths=args.get("paths")))
        if args.get("windows") is True:
            focus = compositor_focus_fact()
            if focus is None:
                self.store.invalidate(["windows.focus.identity"])
            else:
                self.store.apply([focus])
        for prefix in args.get("invalidates", []):
            if isinstance(prefix, str) and prefix:
                keys = [key for key in self.store.snapshot(valid_only=False).facts
                        if key == prefix or key.startswith(prefix + ".")]
                self.store.invalidate(keys)
        visual = {"requested": args.get("visual") is True, "ok": False}
        if visual["requested"]:
            path = os.environ.get("WORLDLINE_OBSERVER_SOCKET") or str(
                Path(os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}"))
                / "gnome-wayland-computer-use" / "observer.sock")
            try:
                fact = capture_visual(path, args.get("visual_timeout_ms", 1500))
                self.store.apply([fact])
                visual.update({"ok": True, "hash": fact.value})
            except Exception as exc:
                visual.update({"code": "observer_unavailable", "detail": str(exc)})
        # A boundary advances even when all direct values happen to agree.
        revision = self.store.fence()
        expect = args.get("expect", [])
        satisfied = [str(p.get("id") or p) for p in expect
                     if isinstance(p, dict) and self._predicate(p, start)]
        return {"revision": revision, "domain_id": self.domain_id,
                "previous_revision": start,
                "boundary": {"monotonic_ns": __import__("time").monotonic_ns(),
                             "wall_time_ns": __import__("time").time_ns()},
                "predicates_satisfied": satisfied, "visual": visual}

    def _predicate(self, predicate: dict[str, Any], after: int) -> bool:
        path = predicate.get("path")
        if not isinstance(path, str) or not path:
            return False
        op = predicate.get("op", "eq")
        witness = self.store.fact_receipt(path)
        fresh = predicate.get("fresh_after")
        if op == "changed":
            return self.store.changed_after(path, int(fresh if fresh is not None else after))
        if op == "invalid":
            return self.store.invalidated_after(path, int(fresh if fresh is not None else after))
        if op == "missing":
            return witness is None and (fresh is None or
                                        self.store.invalidated_after(path, int(fresh)))
        if witness is None or fresh is not None and witness["observed_revision"] <= int(fresh):
            return False
        value, want = witness["value"], predicate.get("value")
        if op == "exists":
            return True
        if op == "eq":
            return value == want
        if op == "ne":
            return value != want
        if op == "in":
            return isinstance(want, list) and value in want
        if op == "contains":
            try:
                return want in value
            except TypeError:
                return False
        return False

    def _wait_once(self, args: dict[str, Any]) -> dict[str, Any]:
        if isinstance(args.get("id"), str) and args["id"] not in self._armed:
            raise ValueError("unknown armed transaction")
        if isinstance(args.get("id"), str) and args["id"] in self._armed:
            armed = self._armed[args["id"]]
            args = {**armed, **args, "after_revision": args.get(
                "after_revision", armed["armed_revision"])}
        after = int(args.get("after_revision", self.store.revision))
        branches = args.get("branches", [])
        predicates = args.get("predicates", [args["predicate"]] if "predicate" in args else [])
        mode = args.get("mode", "all")
        if not isinstance(predicates, list) or not isinstance(branches, list) or mode not in ("all", "any"):
            raise ValueError("invalid predicates, branches or mode")
        if not predicates and not branches:
            raise ValueError("wait requires predicates or branches")
        def matched(group: list, group_mode: str) -> bool:
            states = [self._predicate(p, after) for p in group if isinstance(p, dict)]
            return bool(states) and (all(states) if group_mode == "all" else any(states))
        branch = next((str(item.get("id", "")) for item in branches
                       if isinstance(item, dict) and matched(
                           item.get("predicates", []), item.get("mode", "all"))), None)
        ready = branch is not None or matched(predicates, mode)
        conflicts = [path for path in args.get("conflict_paths", [])
                     if isinstance(path, str) and self.store.touched_after(path, after)]
        code = "ready" if ready else "conflict" if conflicts else "pending"
        witnesses = [self.store.fact_receipt(p.get("path")) for p in predicates
                     if isinstance(p, dict) and self._predicate(p, after)]
        return {"code": code, "state": code, "revision": self.store.revision,
                "after_revision": after, "matched_branch": branch,
                "conflict_paths": conflicts, "witnesses": [w for w in witnesses if w]}

    def _observe_provider(self, provider_name: str, *, mode: str = "active",
                          expected_revision: int | None = None) -> tuple[int, int]:
        provider = self.providers[provider_name]
        read = provider.observe if mode == "active" else getattr(provider, "observe_fast", None)
        if not callable(read):
            raise ValueError("provider does not support fast observation")
        with self._provider_guards[provider_name]:
            started = monotonic()
            try:
                facts = list(read())
                revision = self.store.reconcile(
                    facts, managed_keys=getattr(provider, "managed_keys", ()),
                    expected_revision=expected_revision,
                )
            except Exception as exc:
                self.provider_readings[provider_name] = {
                    "mode": mode, "ok": False, "error_type": type(exc).__name__,
                    "duration_ms": round((monotonic() - started) * 1000, 2),
                    "attempted_at": time(),
                }
                raise
            self.provider_readings[provider_name] = {
                "mode": mode, "ok": True, "fact_count": len(facts),
                "duration_ms": round((monotonic() - started) * 1000, 2),
                "attempted_at": time(), "revision": revision,
            }
            return revision, len(facts)

    def dispatch(self, raw: dict[str, Any]) -> dict[str, Any]:
        req = Request.from_dict(raw)
        if req.protocol != PROTOCOL_VERSION:
            return error(
                req, "protocol_mismatch", f"supported protocol is {PROTOCOL_VERSION}"
            )
        if req.op not in CORE_OPS:
            return error(req, "unknown_op", req.op)
        if req.args.get("domain_id") is not None and req.args["domain_id"] != self.domain_id:
            return error(req, "revision_domain_mismatch", "WORLDLINE daemon instance changed")
        if req.op in {"hello", "features"}:
            return ok(
                req,
                {
                    "protocol": PROTOCOL_VERSION,
                    "ops": sorted(CORE_OPS),
                    "revision_domain": "worldline",
                    "domain_id": self.domain_id,
                    "receipt_schema": "worldline.causal-receipt",
                    "extension_model": [
                        "providers",
                        "consumers",
                        "facts",
                        "capabilities",
                        "affordances",
                    ],
                    "providers": sorted(self.providers),
                    "source_catalog": True,
                    "observation_modes": ["fast", "active"],
                    "query": {"paths": True, "fresh": True,
                              "views": ["world"], "legacy_default": True},
                },
            )
        if req.op == "sources":
            return ok(req, {
                "providers": [provider_description(self.providers[name])
                              for name in sorted(self.providers)],
                "last_reads": dict(self.provider_readings),
            })
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
            expected = req.args.get("expected_revision")
            if expected is not None and expected != self.store.revision:
                return error(req, "revision_conflict", "expected revision does not match")
            mode = req.args.get("mode", "active")
            if mode not in ("fast", "active"):
                return error(req, "invalid_mode", "mode must be fast or active")
            if mode == "fast" and not callable(getattr(provider, "observe_fast", None)):
                return error(req, "unsupported_mode", "provider does not offer a fast read")
            try:
                revision, count = self._observe_provider(
                    provider_name, mode=mode, expected_revision=expected,
                )
            except RevisionConflict:
                return error(req, "revision_conflict", "expected revision does not match")
            except Exception:
                return error(req, "observation_failed", "provider could not complete read")
            return ok(req, {
                "provider": provider_name, "revision": revision,
                "fact_count": count, "mode": mode,
            })
        if req.op == "fence":
            result = self._sample(req.args)
            return ok(req, {"code": "fenced", **result})
        if req.op == "status":
            snap = self.store.snapshot()
            return ok(req, {"revision": snap.revision, "domain_id": self.domain_id,
                            "fact_count": len(snap.facts)})
        if req.op == "capture" and any(key in req.args for key in
                                      ("pids", "paths", "visual", "invalidates", "expect", "windows")):
            return ok(req, self._sample(req.args))
        if req.op in {"query", "capture"}:
            selected = req.args.get("refresh", [])
            if not isinstance(selected, list) or len(selected) > 8 or any(
                not isinstance(name, str) for name in selected
            ):
                return error(req, "invalid_refresh", "refresh must be a provider name list")
            mode = req.args.get("mode", "active")
            if mode not in ("fast", "active"):
                return error(req, "invalid_mode", "mode must be fast or active")
            for name in dict.fromkeys(selected):
                provider = self.providers.get(name)
                if provider is None:
                    return error(req, "unknown_provider", name)
                if mode == "fast" and not callable(getattr(provider, "observe_fast", None)):
                    return error(req, "unsupported_mode", f"{name} does not offer a fast read")
                try:
                    self._observe_provider(name, mode=mode)
                except Exception:
                    return error(req, "observation_failed", f"{name} could not complete read")
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
            if isinstance(req.args.get("event"), dict):
                revision = apply_event(self.store, req.args["event"])
            else:
                key = str(req.args["key"])
                fact = Fact(
                    key=key, value=req.args.get("value"),
                    evidence=Evidence(source=str(req.args.get("source", "rpc:event")),
                                      confidence=float(req.args.get("confidence", 1.0)),
                                      expires_at=req.args.get("expires_at")),
                    tags=tuple(req.args.get("tags") or ()),
                )
                revision = self.store.apply(
                    [fact], expected_revision=req.args.get("expected_revision"))
            return ok(req, {"revision": revision, "code": "applied"})
        if req.op == "arm":
            ident = req.args.get("id")
            if not isinstance(ident, str) or not ident or not isinstance(req.args.get("predicates"), list):
                return error(req, "bad_request", "arm requires id and predicates")
            self._armed[ident] = {**req.args, "armed_revision": self.store.revision}
            if len(self._armed) > 1024:
                del self._armed[next(iter(self._armed))]
            return ok(req, {"armed": True, "id": ident, "revision": self.store.revision})
        if req.op == "receipt":
            args = req.args
            before = args.get("before_revision")
            predicate = args.get("predicate")
            owner = args.get("owner")
            if (type(before) is not int or not isinstance(owner, str) or not owner
                    or not isinstance(predicate, dict)):
                return error(req, "bad_request", "receipt requires owner, before_revision and predicate")
            witness = self.store.fact_receipt(predicate.get("path"))
            observed = (self._predicate({**predicate, "fresh_after": before}, before)
                        and witness is not None
                        and witness["evidence"]["source"] != owner)
            action_ok = args.get("action_ok") is True
            return ok(req, {
                "schema": "worldline.causal-receipt", "protocol": PROTOCOL_VERSION,
                "revision_domain": "worldline", "domain_id": self.domain_id,
                "owner": owner,
                "claim": str(args.get("claim") or "postcondition")[:80],
                "action_id": str(args.get("action_id") or "")[:120],
                "before_revision": before, "after_revision": self.store.revision,
                "action": {"ok": action_ok, "source": owner},
                "observation": witness if observed else None,
                "outcome": "verified" if action_ok and observed
                    else "failed" if not action_ok else "unverified",
            })
        if req.op == "wait":
            try:
                if not any(key in req.args for key in ("predicate", "predicates", "branches", "id")):
                    return error(req, "invalid_wait", "wait requires predicates or branches")
                result = self._wait_once(req.args)
            except (TypeError, ValueError):
                return error(req, "invalid_wait", "invalid wait specification")
            return ok(req, result)
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
                                0.001, min(float(args.get("timeout_ms", float(args.get("timeout", 5)) * 1000)) / 1000, 120.0))
                        except (TypeError, ValueError):
                            deadline = asyncio.get_running_loop().time()
                        while True:
                            short = {**raw, "args": {**args, "timeout": 0.001}}
                            response = self.dispatch(short)
                            if not response.get("ok") or response["result"].get("state") in ("ready", "conflict"):
                                break
                            if asyncio.get_running_loop().time() >= deadline:
                                response["result"]["state"] = "timeout"
                                response["result"]["code"] = "timeout"
                                break
                            if args.get("pids") or args.get("paths") or args.get("visual"):
                                await asyncio.to_thread(self._sample, args)
                            await asyncio.sleep(0.05)
                    elif raw.get("op") in {"observe", "query", "capture"}:
                        async with self._blocking_slots:
                            response = await asyncio.to_thread(self.dispatch, raw)
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
    start_atspi_sensor(daemon.store)
    daemon.current.refresh()
    daemon.dispatch({"op": "observe", "args": {"provider": "gnome"}})
    server = await asyncio.start_unix_server(daemon.handle, path=str(path))
    os.chmod(path, 0o600)
    async def reconcile() -> None:
        ticks = 0
        while True:
            await asyncio.sleep(2)
            ticks += 1
            await asyncio.to_thread(daemon.current.ensure)
            if ticks % 15 == 0:
                await asyncio.to_thread(daemon.dispatch, {"op": "observe", "args": {"provider": "gnome"}})

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
                        await asyncio.to_thread(daemon.current.refresh, ["desktop", "windows"])
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
