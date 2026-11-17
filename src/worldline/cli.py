"""Agent-facing reads from the revisioned WORLDLINE current."""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Sequence

from . import __version__
from .control import request
from .daemon import default_socket
from .observe import sections

_COMPACT = (",", ":")


def dumps(value: Any, *, pretty: bool = False) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2 if pretty else None,
                      separators=None if pretty else _COMPACT, default=str)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="worldline",
        description="WORLDLINE: Operating Fact. Read the revisioned current as JSON.",
        epilog="Spatial display: worldline geometry [--live | --json] (q quits live view)",
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
    """Query an already-running daemon; a CLI read never starts one.

    Starting a detached, persistent daemon as a side effect of the default
    integration check made every reader an owner of the service. Lifecycle stays
    with the explicit ``worldline-daemon`` entry point and the managed user
    service; the CLI only observes what is already running.
    """
    try:
        return request(path, op, args)
    except (FileNotFoundError, ConnectionRefusedError) as exc:
        raise OSError(
            f"WORLDLINE daemon is not running at {path}; "
            "start it with worldline-daemon or the managed user service"
        ) from exc
    except OSError as exc:
        raise OSError(f"WORLDLINE daemon at {path} could not be queried: {exc}") from exc
    except ValueError as exc:
        raise OSError(f"WORLDLINE daemon at {path} returned an invalid response") from exc


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
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "geometry":
        from .geometry_cli import geometry_command
        return geometry_command(argv[1:], connect=_connect,
            socket_path=os.environ.get("WORLDLINE_SOCKET") or default_socket(), dumps=dumps)
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
