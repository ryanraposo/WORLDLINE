"""Bounded Linux host/runtime facts from the kernel's existing read-only surfaces.

No subprocess, compositor plugin, service restart, or application inspection.
These sources describe host capacity and native device state, not a service's
readiness, user intent, desktop geometry, or inferred logical relationships.
"""
from __future__ import annotations

import os
from pathlib import Path
import re
from time import time
from typing import Callable, Iterable

from worldline.model import Evidence, Fact
from worldline.sources import SourceSurface
from .base import ObservationProvider

_LOAD_NAMES = ("1m", "5m", "15m")
_KIB_FIELDS = {"MemTotal": "host.memory.total_kib",
               "MemAvailable": "host.memory.available_kib",
               "SwapTotal": "host.memory.swap_total_kib",
               "SwapFree": "host.memory.swap_free_kib"}
_OWNED = (
    "host.memory.total_kib", "host.memory.available_kib",
    "host.memory.swap_total_kib", "host.memory.swap_free_kib",
    "host.load.1m", "host.load.5m", "host.load.15m",
    "host.uptime.seconds", "host.power.sources", "host.displays.connectors",
)


def _small_text(path: Path, max_bytes: int) -> str | None:
    """Bounded direct read. Unavailable, unreadable and oversized stay unknown."""
    try:
        with path.open("rb") as stream:
            data = stream.read(max_bytes + 1)
    except (OSError, ValueError):
        return None
    if len(data) > max_bytes:
        return None
    try:
        return data.decode("ascii").strip()
    except UnicodeDecodeError:
        return None


def _number(value: str | None, *, minimum: float = 0, maximum: float = 10**12) -> float | None:
    if not value:
        return None
    try:
        parsed = float(value)
    except ValueError:
        return None
    if not (minimum <= parsed <= maximum):
        return None
    return parsed


class HostRuntimeProvider(ObservationProvider):
    """Direct kernel surface sampling, never a substitute for a service answer."""

    name = "host"
    managed_keys = _OWNED
    source_surfaces = (
        SourceSurface("memory", "Linux /proc/meminfo", "direct_read",
                      "negligible", tuple(_KIB_FIELDS.values())),
        SourceSurface("load", "Linux /proc/loadavg", "direct_read",
                      "negligible", ("host.load.1m", "host.load.5m", "host.load.15m"),
                      "Load averages are not CPU utilization percentages."),
        SourceSurface("uptime", "Linux /proc/uptime", "direct_read",
                      "negligible", ("host.uptime.seconds",)),
        SourceSurface("power", "Linux /sys/class/power_supply", "direct_read",
                      "bounded", ("host.power.sources",),
                      "Battery or AC attributes only, never device serial numbers."),
        SourceSurface("connectors", "Linux /sys/class/drm", "direct_read",
                      "bounded", ("host.displays.connectors",),
                      "DRM connector cable state, not GNOME logical monitor geometry."),
    )

    def __init__(self, *, proc_root: Path = Path("/proc"),
                 sys_root: Path = Path("/sys"), clock: Callable[[], float] = time):
        self.proc_root = Path(proc_root)
        self.sys_root = Path(sys_root)
        self.clock = clock

    def observe_fast(self) -> Iterable[Fact]:
        return self.observe()

    def observe(self) -> Iterable[Fact]:
        at = self.clock()
        facts: list[Fact] = []

        def record(key: str, value: object, source: str, ttl: float) -> None:
            facts.append(Fact(key, value, Evidence(
                source=source, observed_at=at, expires_at=at + ttl,
                detail={"method": "bounded-direct-read"},
            )))

        mem = _small_text(self.proc_root / "meminfo", 16384)
        if mem is not None:
            for line in mem.splitlines()[:128]:
                match = re.fullmatch(r"([A-Za-z_]+):\s*(\d+)\s+kB", line.strip())
                if match and match.group(1) in _KIB_FIELDS:
                    record(_KIB_FIELDS[match.group(1)], int(match.group(2)),
                           "procfs:/proc/meminfo", 5)

        loads = _small_text(self.proc_root / "loadavg", 256)
        if loads:
            first = loads.split()[:3]
            if len(first) == 3:
                readings = [_number(raw, maximum=1_000_000) for raw in first]
                for name, val in zip(_LOAD_NAMES, readings):
                    if val is not None:
                        record(f"host.load.{name}", val, "procfs:/proc/loadavg", 5)

        uptime = _small_text(self.proc_root / "uptime", 128)
        if uptime:
            val = _number(uptime.split()[0], maximum=1_000_000_000)
            if val is not None:
                record("host.uptime.seconds", val, "procfs:/proc/uptime", 5)

        def children(path: Path, maximum: int) -> list[Path] | None:
            try:
                return sorted(path.iterdir(), key=lambda x: x.name)[:maximum]
            except OSError:
                return None

        power_root = self.sys_root / "class/power_supply"
        power_children = children(power_root, 24)
        if power_children is not None:
            sources = []
            for path in power_children:
                # Kernel device names only: no human-readable label or serial.
                if not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", path.name):
                    continue
                typ = _small_text(path / "type", 32)
                if typ not in ("Battery", "Mains", "USB", "USB_C", "Wireless"):
                    continue
                entry = {"kernel_name": path.name, "type": typ}
                status = _small_text(path / "status", 32)
                if status in ("Charging", "Discharging", "Full", "Not charging", "Unknown"):
                    entry["status"] = status
                capacity = _number(_small_text(path / "capacity", 12), maximum=100)
                if typ == "Battery" and capacity is not None:
                    entry["percent"] = capacity
                online = _small_text(path / "online", 4)
                if online in ("0", "1"):
                    entry["online"] = online == "1"
                sources.append(entry)
            record("host.power.sources", sources, "sysfs:/sys/class/power_supply", 10)

        drm_root = self.sys_root / "class/drm"
        drm_children = children(drm_root, 80)
        if drm_children is not None:
            connectors = []
            for path in drm_children:
                if not re.fullmatch(r"card\d+-[A-Za-z0-9_.-]{1,80}", path.name):
                    continue
                state = _small_text(path / "status", 32)
                if state in ("connected", "disconnected", "unknown"):
                    connectors.append({"kernel_name": path.name, "status": state})
            record("host.displays.connectors", connectors, "sysfs:/sys/class/drm", 10)
        return facts
