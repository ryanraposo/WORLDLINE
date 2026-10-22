"""Dot-path selection over an observation tree."""

from __future__ import annotations

import re
from typing import Any, Iterable

_BRACKET = re.compile(r"\[([^\]]+)\]")


class QueryError(KeyError):
    """A path could not be resolved against the observation tree."""

    def __init__(self, path: str, message: str | None = None) -> None:
        super().__init__(message or f"no such path: {path}")
        self.path = path


def normalize(path: str) -> list[str]:
    """Turn ``storage[0].percent`` into ``["storage", "0", "percent"]``."""

    expanded = _BRACKET.sub(r".\1", path.strip())
    return [part for part in expanded.split(".") if part]


def _wildcard(value: Any, parts: list[str], original: str) -> list[Any]:
    if isinstance(value, dict):
        values = list(value.values())
    elif isinstance(value, list):
        values = list(value)
    else:
        raise QueryError(original, f"cannot expand '*': {original}")

    result: list[Any] = []
    for item in values:
        resolved = _resolve(item, parts, original)
        if isinstance(resolved, list):
            result.extend(resolved)
        else:
            result.append(resolved)
    return result


def _resolve(value: Any, parts: list[str], original: str) -> Any:
    for index, part in enumerate(parts):
        rest = parts[index + 1 :]
        if part == "*":
            return _wildcard(value, rest, original)

        if isinstance(value, dict):
            if part not in value:
                raise QueryError(original, f"no such key: {part} (in {original})")
            value = value[part]
            continue

        if isinstance(value, list):
            try:
                position = int(part)
            except ValueError as exc:
                raise QueryError(
                    original, f"list index must be an integer: {part} (in {original})"
                ) from exc
            try:
                value = value[position]
            except IndexError as exc:
                raise QueryError(
                    original, f"index {position} out of range (in {original})"
                ) from exc
            continue

        raise QueryError(
            original, f"cannot descend into {type(value).__name__} (in {original})"
        )

    return value


def resolve(world: dict[str, Any], path: str) -> Any:
    """Resolve one dot/bracket path. Wildcards return a list of matches."""

    parts = normalize(path)
    if not parts:
        raise QueryError(path)
    return _resolve(world, parts, path)


def many(world: dict[str, Any], paths: Iterable[str]) -> Any:
    """Resolve many paths.

    A single path returns its value directly so scalar queries stay scalar.
    Multiple paths return a mapping from the original path text to its value.
    """

    requested = list(paths)
    values = {path: resolve(world, path) for path in requested}
    if len(requested) == 1:
        return values[requested[0]]
    return values


def top_level(paths: Iterable[str]) -> set[str]:
    """Return the top-level sections a set of paths needs."""

    result: set[str] = set()
    for path in paths:
        parts = normalize(path)
        if parts:
            result.add(parts[0])
    return result
