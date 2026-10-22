"""Agent-facing reads from the revisioned WORLDLINE current."""

from __future__ import annotations

import argparse
import fcntl
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from typing import Any, Sequence

from . import __version__
from .control import request
from .daemon import default_socket
from .observe import sections

_COMPACT = (",", ":")


def _daemon_runtime() -> tuple[str, dict[str, str]]:
    """Choose an interpreter that can read AT-SPI on this host.

    An isolated virtualenv may contain PyGObject without the matching native
    ``_gi`` extension.  The normal system interpreter often has the working
    distro bindings.  Pass this pure-Python package's path explicitly when
    choosing that interpreter.
    """

    environment = os.environ.copy()
    package_root = str(Path(__file__).resolve().parent.parent)
    environment["PYTHONPATH"] = os.pathsep.join(filter(None, (
        package_root, environment.get("PYTHONPATH", "")
    )))
    candidates = dict.fromkeys((sys.executable, shutil.which("python3"), "/usr/bin/python3"))
    for candidate in candidates:
        if not candidate:
            continue
        try:
            probe = subprocess.run(
                [candidate, "-c", "import pyatspi; import worldline.daemon"],
                env=environment, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, timeout=3, check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        if probe.returncode == 0:
            return candidate, environment
    # Other observations still work when this host has no AT-SPI binding.
    return sys.executable, environment


def dumps(value: Any, *, pretty: bool = False) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2 if pretty else None,
                      separators=None if pretty else _COMPACT, default=str)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="worldline",
        description="WORLDLINE: Operating Fact. Read the revisioned current as JSON.",
    )
    parser.add_argument("paths", nargs="*", metavar="PATH",
                        help="dot paths such as windows.active.geometry")
    parser.add_argument("--all", action="store_true", help="include every process")
    parser.add_argument("--pretty", action="store_true", help="indent JSON")
    parser.add_argument("--list", action="store_true", dest="list_paths",
                        help="list sections, or paths under one section")
    parser.add_argument("--explain", action="store_true",
                        help="include evidence, revision and freshness for each path")
    parser.add_argument("--fresh", action="store_true",
                        help="refresh the requested sources before reading")
    parser.add_argument("--socket", default=None, help="override the private socket path")
    parser.add_argument("--version", action="version", version=f"worldline {__version__}")
    return parser


def _connect(path: str, op: str, args: dict[str, Any]) -> dict[str, Any]:
    try:
        return request(path, op, args)
    except (FileNotFoundError, ConnectionRefusedError, ValueError, json.JSONDecodeError):
        pass

    socket_path = Path(path)
    socket_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    lock_path = socket_path.with_suffix(".lock")
    with lock_path.open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            return request(path, op, args, timeout=1.0)
        except (FileNotFoundError, ConnectionRefusedError, ValueError, json.JSONDecodeError):
            daemon_python, daemon_environment = _daemon_runtime()
            process = subprocess.Popen(
                [daemon_python, "-m", "worldline.daemon", "--socket", path],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, start_new_session=True,
                env=daemon_environment,
            )
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    break
                try:
                    return request(path, op, args, timeout=1.0)
                except (FileNotFoundError, ConnectionRefusedError, ValueError, json.JSONDecodeError):
                    time.sleep(0.1)
    raise OSError("WORLDLINE daemon did not become ready")


def _catalog(value: Any, prefix: str, *, limit: int = 200) -> list[str]:
    result: list[str] = []

    def visit(item: Any, path: str, depth: int) -> None:
        if len(result) >= limit:
            return
        result.append(path)
        if depth >= 5:
            return
        if isinstance(item, dict):
            if path == "windows.by_id":
                for key in item:
                    if len(result) >= limit:
                        break
                    result.append(f"{path}.{key}")
                if item:
                    key = next(iter(item))
                    visit(item[key], f"{path}.{key}", depth + 1)
                return
            keys = list(item)
            if path == "windows":
                priority = {"active": 0, "by_id": 1, "items": 2}
                keys.sort(key=lambda key: priority.get(key, 3))
            for key in keys:
                child = item[key]
                visit(child, f"{path}.{key}", depth + 1)
        elif isinstance(item, list) and item:
            visit(item[0], f"{path}.*", depth + 1)

    visit(value, prefix, 0)
    return list(dict.fromkeys(result))


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.list_paths and not args.paths:
        print(dumps(list(sections()), pretty=args.pretty))
        return 0
    if args.list_paths and (len(args.paths) != 1 or args.paths[0] not in sections()):
        print(dumps({"error": "bad_request", "message": "--list accepts one section"}),
              file=sys.stderr)
        return 2
    if args.explain and not args.paths:
        print(dumps({"error": "bad_request", "message": "--explain requires a path"}),
              file=sys.stderr)
        return 2

    path = args.socket or os.environ.get("WORLDLINE_SOCKET") or default_socket()
    query_args: dict[str, Any] = {"fresh": args.fresh, "full": args.all}
    if args.paths:
        query_args["paths"] = args.paths
    else:
        query_args["view"] = "world"
    try:
        response = _connect(path, "query", query_args)
    except OSError as exc:
        print(dumps({"error": "unavailable", "message": str(exc)}), file=sys.stderr)
        return 3
    if not response.get("ok"):
        issue = response.get("error") or {}
        code = issue.get("code", "bad_request")
        print(dumps({"error": code, "message": issue.get("message", code)}), file=sys.stderr)
        return 1 if code == "no_such_path" else 2

    result = response["result"]
    if args.paths:
        if args.list_paths:
            result = _catalog(result["values"][args.paths[0]], args.paths[0])
        elif args.explain:
            facts = result["facts"]
            result = facts[args.paths[0]] if len(args.paths) == 1 else facts
        else:
            values = result["values"]
            result = values[args.paths[0]] if len(args.paths) == 1 else values
    print(dumps(result, pretty=args.pretty))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
