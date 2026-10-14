from __future__ import annotations

import argparse
import json
import socket
from uuid import uuid4

from .daemon import default_socket


def request(path: str, op: str, args: dict | None = None) -> dict:
    payload = {"protocol": 1, "request_id": str(uuid4()), "op": op, "args": args or {}}
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
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
    parser = argparse.ArgumentParser(description="WORLDLINE control client")
    parser.add_argument("--socket", default=default_socket())
    parser.add_argument("op", choices=["hello", "features", "observe", "fence", "status", "query", "capture", "arm", "wait", "close"])
    parser.add_argument("--provider", default="gnome", help="Provider name for observe")
    parser.add_argument("--refresh", action="append", metavar="PROVIDER", default=[],
                        help="For query/capture, freshly sample provider before reading; repeatable")
    args = parser.parse_args()
    if args.refresh and args.op not in ("query", "capture"):
        parser.error("--refresh is only supported by query and capture")
    if args.provider != "gnome" and args.op != "observe":
        parser.error("--provider is only supported by observe")
    payload = ({"refresh": args.refresh} if args.op in ("query", "capture")
               else {"provider": args.provider} if args.op == "observe" else {})
    print(json.dumps(request(args.socket, args.op, payload), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
