from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Sequence

from . import __version__
from .observe import observe, sections
from .query import QueryError, many, top_level

_COMPACT = (",", ":")


def dumps(value: Any, *, pretty: bool = False) -> str:
    if pretty:
        return json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            sort_keys=False,
            default=str,
        )
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=_COMPACT,
        sort_keys=False,
        default=str,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="worldline",
        description="WORLDLINE: Operating Fact. A live, revisioned view of what the machine knows now, as JSON.",
    )
    parser.add_argument(
        "paths",
        nargs="*",
        metavar="PATH",
        help="dot paths to select (e.g. host.kernel, windows.active.geometry)",
    )
    parser.add_argument("--all", action="store_true", help="include every process")
    parser.add_argument("--pretty", action="store_true", help="indent JSON")
    parser.add_argument(
        "--list", action="store_true", dest="list_sections", help="list sections"
    )
    parser.add_argument(
        "--version", action="version", version=f"worldline {__version__}"
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)

    if args.list_sections:
        print(dumps(list(sections())))
        return 0

    try:
        if args.paths:
            wanted = top_level(args.paths)
            full = args.all or any("processes" in path for path in args.paths)
            world = observe(wanted, full=full)
            result = many(world, args.paths)
        else:
            result = observe(full=args.all)
    except QueryError as exc:
        print(
            dumps(
                {
                    "error": "no_such_path",
                    "path": exc.path,
                    "message": str(exc),
                }
            ),
            file=sys.stderr,
        )
        return 1
    except KeyError as exc:
        print(
            dumps({"error": "bad_request", "message": str(exc)}),
            file=sys.stderr,
        )
        return 2

    print(dumps(result, pretty=args.pretty))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
