from __future__ import annotations

from dataclasses import dataclass
from typing import Any


PROTOCOL_VERSION = 1
LEGACY_OPS = frozenset({"status", "event", "capture", "arm", "wait", "close"})
CORE_OPS = frozenset({"hello", "status", "query", "features", "observe", "fence", "sources"}) | LEGACY_OPS


@dataclass(frozen=True, slots=True)
class Request:
    op: str
    args: dict[str, Any]
    protocol: int = PROTOCOL_VERSION
    request_id: str | None = None

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Request":
        return cls(
            op=str(raw.get("op", "")),
            args=dict(raw.get("args") or {}),
            protocol=int(raw.get("protocol", PROTOCOL_VERSION)),
            request_id=raw.get("request_id"),
        )


def ok(request: Request, result: Any) -> dict[str, Any]:
    return {
        "ok": True,
        "protocol": PROTOCOL_VERSION,
        "request_id": request.request_id,
        "result": result,
    }


def error(request: Request, code: str, message: str) -> dict[str, Any]:
    return {
        "ok": False,
        "protocol": PROTOCOL_VERSION,
        "request_id": request.request_id,
        "error": {"code": code, "message": message},
    }
