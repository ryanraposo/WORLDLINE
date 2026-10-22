from __future__ import annotations

import argparse
import json
import socket
from uuid import uuid4

from .daemon import default_socket


def request(path: str, op: str, args: dict | None = None, *, timeout: float = 15.0) -> dict:
    payload = {"protocol": 1, "request_id": str(uuid4()), "op": op, "args": args or {}}
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        sock.connect(path)
        sock.sendall((json.dumps(payload) + "\n").encode())
        data = b""
        while not data.endswith(b"\n"):
            chunk = sock.recv(65536)
            if not chunk:
                break
            data += chunk
    return json.loads(data)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="WORLDLINE: Operating Fact. control client"
    )
    parser.add_argument("--socket", default=default_socket())
    parser.add_argument("--path", action="append", dest="paths", default=[],
                        help="select a path for query; repeat for several")
    parser.add_argument("--fresh", action="store_true",
                        help="refresh selected sources before query")
    parser.add_argument("--view", choices=["world"],
                        help="request the full section view")
    parser.add_argument(
        "op",
        choices=[
            "hello",
            "features",
            "sources",
            "observe",
            "fence",
            "status",
            "query",
            "capture",
            "arm",
            "wait",
            "close",
        ],
    )
    args = parser.parse_args()
    query_args = {}
    if args.paths:
        query_args["paths"] = args.paths
    if args.fresh:
        query_args["fresh"] = True
    if args.view:
        query_args["view"] = args.view
    print(json.dumps(request(args.socket, args.op, query_args), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
