"""Direct, one-shot observation of the machine.

Every section is gathered from the operating system itself.  Expensive
sources (AT-SPI, D-Bus, subprocesses) are optional and fail soft: a
missing source produces an explicit error, never a fabricated value.
"""

from __future__ import annotations

import json
import os
import platform
import pwd
import re
import shutil
import signal
import socket
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterable

from . import window_geometry
from .cua_gnome import read_windows as _compositor_windows

SCHEMA = 1
TOP_PROCESSES = 12
_PAGE = os.sysconf("SC_PAGE_SIZE")
_CLK_TCK = os.sysconf("SC_CLK_TCK")


def _read(path: str | Path, default: str | None = None) -> str | None:
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return default


def _text(path: str | Path) -> str | None:
    value = _read(path)
    return value.strip() if value is not None else None


def _int(value: Any, default: int | None = None) -> int | None:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def _num(value: Any, digits: int = 2) -> float | None:
    try:
        return round(float(value), digits)
    except (TypeError, ValueError):
        return None


def _bytes(kib: Any, digits: int = 0) -> int | None:
    value = _int(kib)
    return None if value is None else int(value * 1024)


def _run(args: Iterable[str], timeout: float = 1.5) -> tuple[int, str] | None:
    try:
        proc = subprocess.run(
            list(args),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return proc.returncode, proc.stdout
    except (OSError, subprocess.SubprocessError):
        return None


def _run_json(args: Iterable[str], timeout: float = 1.5) -> Any:
    result = _run(args, timeout)
    if result is None or result[0] != 0:
        return None
    try:
        return json.loads(result[1])
    except json.JSONDecodeError:
        return None


def _now_iso(epoch: float | None = None) -> str:
    if epoch is None:
        dt = datetime.now().astimezone()
    else:
        dt = datetime.fromtimestamp(epoch).astimezone()
    return dt.isoformat(timespec="seconds")


_SECRET = re.compile(
    r"(?i)(--?[a-z0-9_-]*(?:password|passwd|token|secret|api[-_]?key|access[-_]?key)"
    r"[a-z0-9_-]*(?:=|\s+))([^\s]+)"
)
_URL_SECRET = re.compile(r"(?i)(https?://[^\s:/]+:)[^@\s]+@")


def redact(value: str) -> str:
    """Remove common credentials from command lines before export."""

    value = _SECRET.sub(r"\1***", value)
    return _URL_SECRET.sub(r"\1***@", value)


def _cmdline(pid: int) -> str:
    raw = _read(f"/proc/{pid}/cmdline") or ""
    parts = [part for part in raw.split("\x00") if part]
    line = " ".join(redact(part) for part in parts)
    return line[:500]


def _time() -> dict[str, Any]:
    now = time.time()
    dt = datetime.now().astimezone()
    offset = dt.utcoffset()
    return {
        "epoch": now,
        "milliseconds": int(now * 1000),
        "iso": dt.isoformat(timespec="milliseconds"),
        "timezone": dt.tzname(),
        "utc_offset_s": int(offset.total_seconds()) if offset else 0,
    }


_VIRT = (
    ("vmware", "vmware"),
    ("virtualbox", "virtualbox"),
    ("innotek", "virtualbox"),
    ("qemu", "qemu"),
    ("kvm", "kvm"),
    ("xen", "xen"),
    ("bochs", "bochs"),
    ("parallels", "parallels"),
    ("bhyve", "bhyve"),
)


def _container() -> str | None:
    if os.path.exists("/.dockerenv"):
        return "docker"
    if os.path.exists("/run/.containerenv"):
        return "container"
    cgroup = _read("/proc/1/cgroup", "")
    for marker in ("docker", "kubepods", "lxc", "podman", "containerd"):
        if marker in cgroup:
            return marker
    return None


def _virtualization() -> str | None:
    release = platform.release().lower()
    if "microsoft" in release:
        return "wsl"

    hypervisor = _text("/sys/hypervisor/type") or ""
    dmi = " ".join(
        filter(
            None,
            (
                _text("/sys/devices/virtual/dmi/id/sys_vendor"),
                _text("/sys/devices/virtual/dmi/id/product_name"),
                _text("/sys/devices/virtual/dmi/id/board_vendor"),
            ),
        ),
    ).lower()
    for hint, name in _VIRT:
        if hint in hypervisor or hint in dmi:
            return name

    cpuinfo = (_read("/proc/cpuinfo") or "").lower()
    if re.search(r"\bhypervisor\b", cpuinfo):
        return "hypervisor"
    if "virtual" in dmi:
        return "virtual"
    return None


def _gpus() -> list[dict[str, Any]]:
    gpus: list[dict[str, Any]] = []
    root = Path("/sys/class/drm")
    if not root.exists():
        return gpus

    for card in sorted(root.glob("card[0-9]*")):
        if not re.fullmatch(r"card\d+", card.name):
            continue
        uevent = _read(card / "device" / "uevent") or ""
        values: dict[str, str] = {}
        for line in uevent.splitlines():
            key, _, value = line.partition("=")
            if value:
                values[key] = value
        pci = values.get("PCI_ID", "")
        vendor_id = pci.split(":", 1)[0].lower() if ":" in pci else ""
        vendor = {"1002": "amd", "10de": "nvidia", "8086": "intel"}.get(vendor_id)
        gpus.append(
            {
                "card": card.name,
                "driver": values.get("DRIVER"),
                "pci_id": pci or None,
                "pci_slot": values.get("PCI_SLOT_NAME"),
                "vendor": vendor,
            }
        )
    return gpus


def _host() -> dict[str, Any]:
    uptime_raw = _read("/proc/uptime", "0") or "0"
    uptime = _num(uptime_raw.split()[0], 2) or 0.0
    boot_id = _text("/proc/sys/kernel/random/boot_id")
    booted_at = time.time() - uptime if uptime else None
    return {
        "hostname": socket.gethostname(),
        "machine_id": _text("/etc/machine-id"),
        "boot_id": boot_id,
        "arch": platform.machine(),
        "uptime_s": uptime,
        "booted_at": _now_iso(booted_at) if booted_at else None,
        "hardware": {
            "vendor": _text("/sys/devices/virtual/dmi/id/sys_vendor"),
            "model": _text("/sys/devices/virtual/dmi/id/product_name"),
            "version": _text("/sys/devices/virtual/dmi/id/product_version"),
            "board": _text("/sys/devices/virtual/dmi/id/board_name"),
            "bios": _text("/sys/devices/virtual/dmi/id/bios_version"),
        },
        "gpus": _gpus(),
        "virtualization": _virtualization(),
        "container": _container(),
    }


_OS_FIELDS = {
    "NAME": "name",
    "ID": "id",
    "VERSION": "version",
    "VERSION_ID": "version_id",
    "VERSION_CODENAME": "codename",
    "PRETTY_NAME": "pretty_name",
}


def _os() -> dict[str, Any]:
    data: dict[str, str] = {}
    for line in (_read("/etc/os-release", "") or "").splitlines():
        key, sep, value = line.partition("=")
        if sep:
            data[key.strip()] = value.strip().strip("\"'")
    distro = {name: data.get(key) for key, name in _OS_FIELDS.items()}
    libc, libc_version = platform.libc_ver()
    return {
        "name": distro.get("name"),
        "id": distro.get("id"),
        "version": distro.get("version"),
        "version_id": distro.get("version_id"),
        "codename": distro.get("codename"),
        "pretty_name": distro.get("pretty_name"),
        "kernel": platform.release(),
        "arch": platform.machine(),
        "libc": libc or None,
        "libc_version": libc_version or None,
        "python": platform.python_version(),
        "locale": os.environ.get("LANG"),
    }


def _cpu() -> dict[str, Any]:
    model = None
    vendor = None
    physical: set[tuple[str, str]] = set()
    sockets: set[str] = set()
    blocks = [
        block
        for block in (_read("/proc/cpuinfo", "") or "").split("\n\n")
        if block.strip()
    ]
    for block in blocks:
        fields: dict[str, str] = {}
        for line in block.splitlines():
            key, sep, value = line.partition(":")
            if sep:
                fields[key.strip()] = value.strip()
        model = model or fields.get("model name")
        vendor = vendor or fields.get("vendor_id")
        socket_id = fields.get("physical id")
        if socket_id is not None:
            sockets.add(socket_id)
        if socket_id is not None and fields.get("core id") is not None:
            physical.add((socket_id, fields["core id"]))

    current = _int(_text("/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq"))
    minimum = _int(_text("/sys/devices/system/cpu/cpu0/cpufreq/scaling_min_freq"))
    maximum = _int(_text("/sys/devices/system/cpu/cpu0/cpufreq/scaling_max_freq"))
    mhz = None
    if current is not None:
        mhz = round(current / 1000, 2)
    elif blocks:
        first = blocks[0]
        match = re.search(r"cpu MHz\s*:\s*([0-9.]+)", first)
        mhz = _num(match.group(1)) if match else None

    counters: dict[str, int] = {}
    for line in (_read("/proc/stat", "") or "").splitlines():
        key, _, value = line.partition(" ")
        if value:
            counters[key] = _int(value.split()[0], 0) or 0

    load = os.getloadavg() if hasattr(os, "getloadavg") else (0.0, 0.0, 0.0)
    logical = os.cpu_count() or len(blocks)
    return {
        "model": model,
        "vendor": vendor,
        "sockets": len(sockets) or None,
        "physical_cores": len(physical) or None,
        "logical_cores": logical,
        "mhz": mhz,
        "frequency": {
            "current": mhz,
            "min": round(minimum / 1000, 2) if minimum else None,
            "max": round(maximum / 1000, 2) if maximum else None,
        },
        "load": {
            "1m": _num(load[0], 2),
            "5m": _num(load[1], 2),
            "15m": _num(load[2], 2),
            "running": counters.get("procs_running"),
            "blocked": counters.get("procs_blocked"),
        },
        "context_switches": counters.get("ctxt"),
    }


def _pressure_file(path: str) -> dict[str, Any] | None:
    raw = _read(path)
    if raw is None:
        return None
    result: dict[str, Any] = {}
    for line in raw.splitlines():
        parts = line.split()
        if len(parts) < 2:
            continue
        kind = parts[0]
        values: dict[str, float] = {}
        for item in parts[1:]:
            key, _, value = item.partition("=")
            number = _num(value)
            if number is not None:
                values[key] = number
        result[kind] = values
    return result or None


def _pressure() -> dict[str, Any]:
    return {
        name: _pressure_file(f"/proc/pressure/{name}")
        for name in ("cpu", "memory", "io")
    }


def _memory() -> dict[str, Any]:
    info: dict[str, int] = {}
    for line in (_read("/proc/meminfo", "") or "").splitlines():
        key, _, value = line.partition(":")
        kib = _int(value.strip().split()[0] if value.strip() else None)
        if kib is not None:
            info[key] = kib

    def kib(name: str) -> int:
        return info.get(name, 0) * 1024

    total = kib("MemTotal")
    available = kib("MemAvailable") or kib("MemFree")
    used = max(0, total - available)
    swap_total = kib("SwapTotal")
    swap_free = kib("SwapFree")
    return {
        "total": total,
        "free": kib("MemFree"),
        "available": available,
        "used": used,
        "percent": round(used / total * 100, 2) if total else 0.0,
        "buffers": kib("Buffers"),
        "cached": kib("Cached") + kib("SReclaimable"),
        "dirty": kib("Dirty"),
        "swap_total": swap_total,
        "swap_used": max(0, swap_total - swap_free),
        "swap_free": swap_free,
        "swap_percent": round((swap_total - swap_free) / swap_total * 100, 2)
        if swap_total
        else 0.0,
    }


_LOCAL_FS = frozenset(
    {
        "ext4",
        "fuseblk",
        "ext3",
        "ext2",
        "tmpfs",
        "ramfs",
        "exfat",
        "vfat",
        "zfs",
        "ntfs",
        "erofs",
        "xfs",
        "overlay",
        "btrfs",
        "ntfs3",
        "f2fs",
    }
)
_SKIP_MOUNT_PREFIX = (
    "/snap/",
    "/proc",
    "/sys",
    "/dev",
    "/run/credentials",
    "/run/docker/netns",
    "/run/snapd/ns",
    "/run/user/1000/gvfs",
    "/run/user/1000/doc",
)


def _unescape_mount(value: str) -> str:
    return re.sub(r"\\([0-7]{3})", lambda match: chr(int(match.group(1), 8)), value)


def _storage() -> list[dict[str, Any]]:
    mounts: list[dict[str, Any]] = []
    seen: set[str] = set()
    for line in (_read("/proc/mounts", "") or "").splitlines():
        parts = line.split()
        if len(parts) < 4:
            continue
        source, target, fstype, options = parts[:4]
        source = _unescape_mount(source)
        target = _unescape_mount(target)
        if fstype not in _LOCAL_FS:
            continue
        if target.startswith(_SKIP_MOUNT_PREFIX):
            continue
        if re.match(r"^/run/user/\d+$", target):
            continue
        if target in seen:
            continue
        try:
            stats = os.statvfs(target)
        except OSError:
            continue
        seen.add(target)
        total = stats.f_frsize * stats.f_blocks
        free = stats.f_frsize * stats.f_bfree
        available = stats.f_frsize * stats.f_bavail
        used = max(0, total - free)
        mounts.append(
            {
                "target": target,
                "source": source,
                "type": fstype,
                "options": options.split(","),
                "total": total,
                "used": used,
                "free": free,
                "available": available,
                "percent": round(used / total * 100, 2) if total else 0.0,
            }
        )
    return sorted(mounts, key=lambda item: item["target"])


def _net_stats(name: str) -> dict[str, int]:
    root = f"/sys/class/net/{name}/statistics"
    return {
        key: _int(_text(f"{root}/{key}"), 0) or 0
        for key in (
            "rx_bytes",
            "tx_bytes",
            "rx_packets",
            "tx_packets",
            "rx_errors",
            "tx_errors",
            "rx_dropped",
            "tx_dropped",
        )
    }


def _network_fallback() -> list[dict[str, Any]]:
    interfaces: list[dict[str, Any]] = []
    root = Path("/sys/class/net")
    if not root.exists():
        return interfaces
    for entry in sorted(root.iterdir()):
        name = entry.name
        flags = _text(entry / "flags") or "0x0"
        interfaces.append(
            {
                "name": name,
                "index": _int(_text(entry / "ifindex")),
                "mac": _text(entry / "address"),
                "mtu": _int(_text(entry / "mtu")),
                "operstate": _text(entry / "operstate"),
                "up": bool(int(flags, 16) & 1),
                "type": "loopback" if name == "lo" else "ether",
                "wireless": (entry / "wireless").exists(),
                "addresses": [],
                "stats": _net_stats(name),
            }
        )
    return interfaces


def _endpoint(value: str) -> tuple[str | None, int | None]:
    """Split an ``ss`` endpoint, including bracketed IPv6 and zone suffixes."""

    if value.startswith("["):
        end = value.find("]")
        if end < 0:
            return None, None
        host = value[1:end]
        rest = value[end + 1 :]
    else:
        host, _, rest = value.rpartition(":")
        if not rest:
            return value, None
    port = rest.strip(":")
    return host or None, int(port) if port.isdigit() else None


def _listeners() -> list[dict[str, Any]]:
    """Listening TCP sockets and bound UDP sockets, when ss is available."""

    result = _run(("ss", "-H", "-lnptu"), timeout=1.0)
    if result is None or result[0] != 0:
        return []
    items: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for line in result[1].splitlines():
        parts = line.split()
        if len(parts) < 5:
            continue
        protocol, state, _, _, local = parts[:5]
        peer = parts[5] if len(parts) > 5 else ""
        host, port = _endpoint(local.rpartition(" ")[2])
        process = None
        pid = None
        match = re.search(r'\("([^"]+)",pid=(\d+)', line)
        if match:
            process, pid = match.group(1), int(match.group(2))
        key = (protocol.lower(), host, port)
        if key in seen:
            continue
        seen.add(key)
        items.append(
            {
                "protocol": protocol.lower(),
                "state": state,
                "address": host,
                "port": port,
                "process": process,
                "pid": pid,
                "peer": peer,
            }
        )
    return sorted(items, key=lambda item: (item["protocol"], item["port"] or 0))


def _network() -> dict[str, Any]:
    addresses = _run_json(("ip", "-j", "address", "show"))
    routes = _run_json(("ip", "-j", "route", "show"))
    if isinstance(addresses, list):
        interfaces = []
        for item in addresses:
            name = item.get("ifname")
            interfaces.append(
                {
                    "name": name,
                    "index": item.get("ifindex"),
                    "mac": item.get("address"),
                    "mtu": item.get("mtu"),
                    "operstate": item.get("operstate", "unknown"),
                    "up": "UP" in (item.get("flags") or []),
                    "type": "loopback"
                    if item.get("link_type") == "loopback"
                    else "ether",
                    "wireless": Path(f"/sys/class/net/{name}/wireless").exists(),
                    "addresses": [
                        {
                            "family": addr.get("family"),
                            "address": addr.get("local"),
                            "prefix": addr.get("prefixlen"),
                            "scope": addr.get("scope"),
                        }
                        for addr in item.get("addr_info", [])
                    ],
                    "stats": _net_stats(name),
                }
            )
    else:
        interfaces = _network_fallback()

    route_list = routes if isinstance(routes, list) else []
    default = next((item for item in route_list if item.get("dst") == "default"), None)

    dns: list[str] = []
    search: list[str] = []
    for line in (_read("/etc/resolv.conf", "") or "").splitlines():
        key, _, value = line.partition(" ")
        value = value.strip()
        if key == "nameserver" and value:
            dns.append(value.split()[0])
        elif key == "search" and value:
            search.extend(value.split())
    return {
        "hostname": socket.gethostname(),
        "interfaces": interfaces,
        "default_route": {
            "gateway": default.get("gateway"),
            "interface": default.get("dev"),
            "source": default.get("prefsrc"),
            "metric": default.get("metric"),
        }
        if default
        else None,
        "routes": route_list,
        "dns": {"nameservers": dns, "search": search},
        "listeners": _listeners(),
    }


_ENV_KEYS = (
    "PATH",
    "SHELL",
    "TERM",
    "LANG",
    "LC_ALL",
    "HOME",
    "USER",
    "LOGNAME",
    "TMPDIR",
    "XDG_DATA_HOME",
    "XDG_CONFIG_HOME",
    "XDG_CACHE_HOME",
    "XDG_STATE_HOME",
    "XDG_RUNTIME_DIR",
    "DESKTOP_SESSION",
    "GDMSESSION",
    "XDG_SESSION_ID",
    "XDG_SEAT",
    "XDG_VTNR",
    "SSH_CONNECTION",
    "SUDO_USER",
)


def _env() -> dict[str, str]:
    return {key: os.environ[key] for key in _ENV_KEYS if key in os.environ}


def _session() -> dict[str, Any]:
    user = pwd.getpwuid(os.getuid())
    try:
        tty = os.ttyname(0)
    except OSError:
        tty = None
    return {
        "name": user.pw_name,
        "uid": user.pw_uid,
        "gid": user.pw_gid,
        "home": user.pw_dir,
        "shell": user.pw_shell,
        "user": user.pw_name,
        "session_id": os.environ.get("XDG_SESSION_ID") or _text("/proc/self/sessionid"),
        "seat": os.environ.get("XDG_SEAT"),
        "type": os.environ.get("XDG_SESSION_TYPE"),
        "desktop": os.environ.get("XDG_CURRENT_DESKTOP"),
        "display": os.environ.get("DISPLAY"),
        "wayland_display": os.environ.get("WAYLAND_DISPLAY"),
        "tty": tty,
        "pid": os.getpid(),
        "ppid": os.getppid(),
        "loginuid": _int(_text("/proc/self/loginuid")),
        "cgroup": (_read("/proc/self/cgroup", "") or "").splitlines(),
        "runtime_dir": os.environ.get("XDG_RUNTIME_DIR"),
        "dbus": os.environ.get("DBUS_SESSION_BUS_ADDRESS"),
        "env": _env(),
        "is_root": os.geteuid() == 0,
        "is_ssh": bool(os.environ.get("SSH_CONNECTION")),
    }


_GIO: tuple[Any, Any, Any] | None = None
_GIO_FAILED = False


def _gio():
    """Lazily connect to the session bus.  Returns (Gio, GLib, bus)."""

    global _GIO, _GIO_FAILED
    if _GIO is not None:
        return _GIO
    if _GIO_FAILED:
        return None
    try:
        from gi.repository import Gio, GLib

        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        _GIO = (Gio, GLib, bus)
        return _GIO
    except Exception:
        _GIO_FAILED = True
        return None


def _dbus_call(
    dest: str,
    path: str,
    interface: str,
    method: str,
    value: Any = None,
    timeout: float = 1.0,
):
    connection = _gio()
    if connection is None:
        return None
    Gio, GLib, bus = connection
    try:
        result = bus.call_sync(
            dest,
            path,
            interface,
            method,
            value,
            None,
            Gio.DBusCallFlags.NONE,
            max(1, int(timeout * 1000)),
            None,
        )
        return result.unpack()
    except Exception:
        return None


def _display_monitors(state: Any) -> list[dict[str, Any]]:
    """Normalize a Mutter ``GetCurrentState`` reply into logical monitors.

    The wire shape is ``(serial, monitors, logical_monitors, properties)``.
    Physical modes carry the current resolution; logical monitors carry
    position, scale and transform.  Malformed members are skipped rather than
    failing the whole display observation.
    """

    if not isinstance(state, (tuple, list)) or len(state) < 3:
        return []

    current: dict[tuple[Any, ...], dict[str, Any]] = {}
    for monitor in state[1] or ():
        if not isinstance(monitor, (tuple, list)) or len(monitor) < 2:
            continue
        header = monitor[0]
        if not isinstance(header, (tuple, list)):
            continue
        key: tuple[Any, ...] = (tuple(header),)
        for mode in monitor[1] or ():
            if not isinstance(mode, (tuple, list)) or len(mode) < 5:
                continue
            properties = mode[-1]
            if not isinstance(properties, dict) or not properties.get("is-current"):
                continue
            try:
                current[key] = {
                    "mode": mode[0],
                    "mode_width": int(mode[1]),
                    "mode_height": int(mode[2]),
                    "refresh_hz": _num(mode[3], 3),
                }
            except (TypeError, ValueError):
                continue

    built: list[dict[str, Any]] = []
    for index, monitor in enumerate(state[2] or ()):
        if not isinstance(monitor, (tuple, list)) or len(monitor) < 6:
            continue
        try:
            x = int(monitor[0])
            y = int(monitor[1])
            scale = float(monitor[2])
            transform = int(monitor[3])
        except (TypeError, ValueError):
            continue
        refs = tuple(
            tuple(ref) if isinstance(ref, (tuple, list)) else (ref,)
            for ref in (monitor[5] or ())
        )
        mode = current.get(refs, {})
        width = int(round(mode.get("mode_width", 0) / max(scale, 0.0001)))
        height = int(round(mode.get("mode_height", 0) / max(scale, 0.0001)))
        if transform in (1, 3):
            width, height = height, width
        built.append(
            {
                "index": index,
                "x": x,
                "y": y,
                "width": width,
                "height": height,
                "scale": scale,
                "transform": transform,
                "primary": bool(monitor[4]),
                "connector": refs[0][0] if refs else None,
                "connectors": [ref[0] for ref in refs],
                "mode": mode.get("mode"),
                "refresh_hz": mode.get("refresh_hz"),
            }
        )
    return built


def _display() -> dict[str, Any]:
    """Read the compositor's logical desktop layout.

    Mutter's DisplayConfig is the authority for monitor geometry; Shell's
    Introspect interface supplies the stage size.  Both are optional.
    """

    desktop: dict[str, Any] = {
        "type": os.environ.get("XDG_SESSION_TYPE"),
        "desktop": os.environ.get("XDG_CURRENT_DESKTOP"),
        "source": "environment",
        "compositor": None,
        "screen": None,
        "monitors": [],
        "accessibility_bus": False,
    }
    connection = _gio()
    if connection is None:
        return desktop
    _, GLib, _ = connection

    version = _dbus_call(
        "org.freedesktop.DBus",
        "/org/freedesktop/DBus",
        "org.freedesktop.DBus",
        "NameHasOwner",
        GLib.Variant("(s)", ("org.gnome.Shell",)),
    )
    shell = _dbus_call(
        "org.gnome.Shell",
        "/org/gnome/Shell",
        "org.freedesktop.DBus.Properties",
        "Get",
        GLib.Variant("(ss)", ("org.gnome.Shell", "ShellVersion")),
    )
    shell_version = shell[0] if shell else None
    if shell_version or version == (True,):
        desktop["compositor"] = {"name": "gnome-shell", "version": shell_version}
        desktop["source"] = "gnome-dbus"

    props = _dbus_call(
        "org.gnome.Shell.Introspect",
        "/org/gnome/Shell/Introspect",
        "org.freedesktop.DBus.Properties",
        "GetAll",
        GLib.Variant("(s)", ("org.gnome.Shell.Introspect",)),
    )
    size = None
    if isinstance(props, tuple) and props and isinstance(props[0], dict):
        size = props[0].get("ScreenSize")
    if size and len(size) == 2:
        desktop["screen"] = {
            "x": 0,
            "y": 0,
            "width": int(size[0]),
            "height": int(size[1]),
        }

    state = _dbus_call(
        "org.gnome.Mutter.DisplayConfig",
        "/org/gnome/Mutter/DisplayConfig",
        "org.gnome.Mutter.DisplayConfig",
        "GetCurrentState",
    )
    built = _display_monitors(state)
    if built:
        desktop["monitors"] = built
        if desktop["screen"] is None:
            desktop["screen"] = window_geometry.union(built)

    a11y = _dbus_call(
        "org.freedesktop.DBus",
        "/org/freedesktop/DBus",
        "org.freedesktop.DBus",
        "NameHasOwner",
        GLib.Variant("(s)", ("org.a11y.Bus",)),
    )
    desktop["accessibility_bus"] = bool(a11y and a11y[0])
    return desktop


# Keep the old private name available to consumers that imported it.
_desktop = _display


_WINDOW_ROLES = frozenset({"window", "frame", "dialog", "alert"})


class _AtspiExpired(Exception):
    """Raised inside the AT-SPI walk so a slow tree cannot stall observation."""


class _AtspiTimeout:
    def __init__(self, seconds: float = 1.5) -> None:
        self.seconds = seconds
        self.old_handler: Any = None
        self.enabled = False

    def __enter__(self) -> "_AtspiTimeout":
        def expire(_signum: int, _frame: Any) -> None:
            raise _AtspiExpired("AT-SPI enumeration timed out")

        try:
            self.old_handler = signal.signal(signal.SIGALRM, expire)
            signal.setitimer(signal.ITIMER_REAL, self.seconds)
            self.enabled = True
        except (ValueError, OSError):
            self.old_handler = None
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        if self.enabled:
            signal.setitimer(signal.ITIMER_REAL, 0)
            if self.old_handler is not None:
                signal.signal(signal.SIGALRM, self.old_handler)


def _atspi_windows() -> dict[str, Any]:
    """Read semantic window identities from AT-SPI."""

    # pyatspi may abort the process when a session advertises an inaccessible
    # accessibility bus (for example inside a filesystem/network sandbox).
    # Probe the bus before importing it so failure remains an unavailable fact.
    probe = _run(("gdbus", "introspect", "--session", "--dest", "org.a11y.Bus",
                  "--object-path", "/org/a11y/bus"), timeout=0.7)
    if probe is None or probe[0] != 0:
        return {"source": "at-spi2", "available": False,
                "reason": "accessibility bus is not reachable", "count": 0, "items": []}

    try:
        import pyatspi
    except Exception as exc:
        return {
            "source": "at-spi2",
            "available": False,
            "reason": f"{type(exc).__name__}: {exc}",
            "count": 0,
            "items": [],
        }

    items: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    try:
        with _AtspiTimeout():
            desktop = pyatspi.Registry.getDesktop(0)
            for app in desktop:
                for window in app:
                    try:
                        role = window.getRoleName()
                        if role not in _WINDOW_ROLES:
                            continue
                        title = window.name or ""
                        states = {
                            getattr(
                                state, "value_nick", getattr(state, "value_name", "")
                            )
                            for state in window.getState().getStates()
                        }
                        if "showing" not in states:
                            continue
                        if app.name == "gnome-shell" and title == "Main stage":
                            continue
                        if app.name == "gjs" and title.startswith("Desktop Icons"):
                            continue
                        extents = window.queryComponent().getExtents(
                            pyatspi.DESKTOP_COORDS
                        )
                        if extents.width <= 0 or extents.height <= 0:
                            continue
                        frame = window_geometry.rect(
                            extents.x, extents.y, extents.width, extents.height
                        )
                        pid = window.get_process_id()
                        path = str(getattr(window, "path", "") or "")
                        # The AT-SPI object path identifies this accessible for
                        # its process lifetime.  A role id is not a window id.
                        token = path.rsplit("/", 1)[-1] if path.startswith(
                            "/org/a11y/atspi/accessible/"
                        ) else ""
                        stable_id = f"window:{pid}:{token}" if pid and token else None
                        key = stable_id or (pid, role, title, tuple(frame.values()))
                        if key in seen:
                            continue
                        seen.add(key)
                        items.append(
                            {
                                "id": int(token) if token.isdecimal() else None,
                                "stable_id": stable_id,
                                "accessible_path": path or None,
                                "pid": pid,
                                "app": app.name,
                                "title": title,
                                "role": role,
                                "frame": frame,
                                "states": sorted(state for state in states if state),
                                "active": "active" in states,
                                "focused": "focused" in states,
                                "maximized": "maximized" in states,
                                "minimized": "minimized" in states,
                                "shaded": "shaded" in states,
                                "modal": "modal" in states,
                                "source": "at-spi2",
                            }
                        )
                    except _AtspiExpired:
                        raise
                    except Exception:
                        # One stale accessibility object must not lose the list.
                        continue
    except Exception as exc:
        return {
            "source": "at-spi2",
            "available": False,
            "reason": f"{type(exc).__name__}: {exc}",
            "count": 0,
            "items": [],
        }

    return {
        "source": "at-spi2",
        "available": True,
        "count": len(items),
        "items": items,
    }


def _semantic_exclusion(
    item: dict[str, Any],
    canonical: list[dict[str, Any]],
    screen: dict[str, Any] | None,
) -> tuple[str, str] | None:
    """Discard only demonstrably duplicate or degenerate AT-SPI records."""

    frame = item["frame"]
    stable_id = item.get("stable_id")
    for other in canonical:
        if stable_id and stable_id == other.get("stable_id"):
            return "duplicate", f"same AT-SPI accessible as {stable_id}"
        if stable_id or other.get("stable_id"):
            continue
        if (
            item.get("pid") == other.get("pid")
            and item.get("role") == other.get("role")
            and item.get("title") == other.get("title")
            and frame == other.get("frame")
        ):
            return "duplicate", "same process, role, title and extents"

    visible = (
        window_geometry.intersection(frame, screen) if screen is not None else frame
    )
    if visible is None and window_geometry.area(frame) <= 1:
        return "stale", f"degenerate off-screen frame at ({frame['x']},{frame['y']})"
    if visible is None and not item.get("title") and window_geometry.area(frame) <= 64:
        return "stale", f"untitled off-screen frame at ({frame['x']},{frame['y']})"
    return None


def _active_summary(items: list[dict[str, Any]]) -> dict[str, Any] | None:
    active = next((item for item in items if item.get("active")), None)
    if active is None:
        active = next((item for item in items if item.get("focused")), None)
    if active is None:
        return None
    return {
        "id": active.get("id"),
        "stable_id": active.get("stable_id"),
        "pid": active.get("pid"),
        "app": active.get("app"),
        "title": active.get("title"),
        "geometry": active.get("geometry"),
    }


def _windows(*, exact_only: bool = False,
             display_override: dict[str, Any] | None = None) -> dict[str, Any]:
    """Observe semantic windows and exact frames from the trusted Shell API.

    AT-SPI supplies process identity, title, states and component extents.
    Mutter DisplayConfig supplies the monitor layout.  Neither source proves
    compositor frame borders, stacking, occlusion or visible pixels; those
    remain unknown in the geometry description.
    """

    # The live geometry view is a compositor fact. Do not make it wait for
    # AT-SPI enumeration or blend in child accessibles when the caller asks
    # for exact frames only.
    compositor = _compositor_windows() if exact_only else None
    atspi = ({"available": False, "reason": "not requested for exact geometry",
              "count": 0, "items": []} if exact_only else _atspi_windows())
    display = display_override if display_override is not None else _display()
    monitors = display.get("monitors") or []
    screen = display.get("screen")
    observed: list[dict[str, Any]] = list(atspi.get("items") or [])
    if compositor is None:
        compositor = _compositor_windows()
    exact = compositor.get("items", []) if compositor.get("available") else []
    if not monitors and not screen:
        screen = window_geometry.union(
            item["frame"] for item in observed if item.get("frame")
        )

    canonical: list[dict[str, Any]] = []
    deduplicated: list[dict[str, Any]] = []
    for window in observed:
        item = dict(window)
        item.update({
            "sources": ["at-spi2"],
            "geometry_source": "at-spi2",
            "status": "semantic_only",
            "confidence": 0.5,
            "match": {
                "method": "semantic_only",
                "confidence": 0.5,
                "band": "semantic_only",
                "score": None,
                "pid_match": None,
                "title_match": None,
                "frame_overlap": None,
            },
            "stacking": None,
        })
        exclusion = _semantic_exclusion(item, canonical, screen)
        if exclusion is not None:
            status, reason = exclusion
            item.update({
                "status": status,
                "reason": reason,
                "confidence": 0.05 if status == "stale" else 0.1,
                "match": {**item["match"], "band": status},
            })
            deduplicated.append(item)
            continue
        canonical.append(item)

    matched_compositor: set[tuple[int, int]] = set()
    for item in canonical:
        # Match the closest same-process, same-title frame. This handles
        # multiple same-title Shell windows while preserving one-to-one IDs.
        # Never infer identity from an accessibility path or title alone.
        candidates = []
        for candidate in exact:
            key = (candidate["pid"], candidate["id"])
            overlap = window_geometry.overlap_fraction(
                item["frame"], {"x": candidate["x"], "y": candidate["y"],
                                "width": candidate["w"], "height": candidate["h"]})
            if (key not in matched_compositor
                    and candidate["pid"] == item.get("pid")
                    and candidate.get("title") == item.get("title")
                    and overlap > 0.5):
                candidates.append((overlap, candidate))
        candidates.sort(key=lambda pair: pair[0], reverse=True)
        if (candidates and (len(candidates) == 1
                            or candidates[0][0] > candidates[1][0])):
            candidate = candidates[0][1]
            matched_compositor.add((candidate["pid"], candidate["id"]))
            item["component_extents"] = item["frame"]
            item["frame"] = window_geometry.rect(
                candidate["x"], candidate["y"], candidate["w"], candidate["h"])
            item["compositor_id"] = candidate["id"]
            # Match the public stable identity to CUA's native window_id.
            item["stable_id"] = f"window:{candidate['pid']}:{candidate['id']}"
            item["compositor_verified"] = True
            item["sources"] = ["at-spi2", "worldline-gnome-shell"]
            item["geometry_source"] = "worldline-gnome-shell"
            item["status"] = "verified"
            item["confidence"] = 1.0
            item["stacking"] = candidate.get("stacking")
            item["focused"] = candidate.get("focused") is True
            item["visible"] = candidate.get("visible") is True
            item["minimized"] = candidate.get("minimized") is True

        frame = item["frame"]
        item.update({
            "x": frame["x"],
            "y": frame["y"],
            "width": frame["width"],
            "height": frame["height"],
            "active": bool(item.get("active") or item.get("focused")),
            "visible": bool(item.get("visible", not item.get("minimized", False))),
            "maximized": bool(item.get("maximized", False)),
            "modal": bool(item.get("modal", False)),
            "minimized": bool(item.get("minimized", False)),
            "shaded": bool(item.get("shaded", False)),
            "focused": bool(item.get("focused", False)),
        })
        item["state"] = {
            key: item[key] for key in (
                "active", "focused", "visible", "minimized", "maximized",
                "shaded", "modal",
            )
        }
        item["geometry"] = window_geometry.describe(
            frame,
            monitors=monitors,
            screen=screen,
            visible=item["visible"],
            minimized=item["minimized"],
            shaded=item["shaded"],
        )
        item["geometry"]["frame_source"] = (
            "worldline-gnome-shell-frame" if item.get("compositor_verified")
            else "at-spi2-component-extents")

    # Once the trusted Shell API is available, it is authoritative for the
    # top-level window set. AT-SPI-only entries can be child accessibles or
    # off-screen helper surfaces, so keep them only as semantic enrichment
    # for a compositor frame that was matched above.
    if compositor.get("available"):
        canonical = [item for item in canonical if item.get("compositor_verified")]

    # Keep compositor-only windows: an inaccessible application can still
    # provide an exact input identity and frame without a semantic tree.
    matched = {(item.get("pid"), item.get("compositor_id")) for item in canonical}
    for candidate in exact:
        if (candidate["pid"], candidate["id"]) in matched:
            continue
        frame = window_geometry.rect(candidate["x"], candidate["y"], candidate["w"], candidate["h"])
        item = {
            "id": candidate["id"], "stable_id": f"window:{candidate['pid']}:{candidate['id']}",
            "pid": candidate["pid"], "compositor_id": candidate["id"],
            "compositor_verified": True, "app": None, "title": candidate.get("title", ""),
            "frame": frame, "focused": candidate.get("focused") is True,
            "active": candidate.get("focused") is True,
            "visible": candidate.get("visible") is True,
            "minimized": candidate.get("minimized") is True,
            "shaded": False, "maximized": False, "modal": False,
            "status": "geometry_only", "confidence": 1.0,
            "sources": ["worldline-gnome-shell"], "geometry_source": "worldline-gnome-shell",
            "stacking": candidate.get("stacking"),
        }
        item["state"] = {key: item[key] for key in (
            "active", "focused", "visible", "minimized", "shaded", "maximized", "modal")}
        item["geometry"] = window_geometry.describe(
            frame, monitors=monitors, screen=screen,
            visible=item["visible"], minimized=item["minimized"])
        item["geometry"]["frame_source"] = "worldline-gnome-shell-frame"
        canonical.append(item)

    # The helper reports bottom-to-top stacking. Rectangle overlap gives an
    # upper bound on exposure; it cannot establish pixel visibility through
    # transparent surfaces.
    for item in canonical:
        stacking = item.get("stacking")
        if not isinstance(stacking, int):
            continue
        occluders = [other["frame"] for other in canonical
                     if isinstance(other.get("stacking"), int)
                     and other["stacking"] > stacking
                     and other.get("visible", True)
                     and not other.get("minimized", False)]
        item["geometry"] = window_geometry.describe(
            item["frame"], monitors=monitors, screen=screen,
            visible=item["visible"], minimized=item["minimized"],
            shaded=item.get("shaded", False), occluders=occluders,
            z_index=stacking)
        item["geometry"]["frame_source"] = (
            "worldline-gnome-shell-frame" if item.get("compositor_verified")
            else "at-spi2-component-extents")

    # AT-SPI enumeration alone supplies no compositor stacking order.
    canonical.sort(key=lambda item: (
        not item["active"], item.get("app") or "", item.get("title") or ""
    ))
    available = bool(atspi.get("available"))
    result: dict[str, Any] = {
        "source": "worldline-gnome-shell+at-spi2" if exact else "at-spi2",
        "available": available or bool(compositor.get("available")),
        "count": len(canonical),
        "items": canonical,
        "by_id": {item["stable_id"]: item for item in canonical if item.get("stable_id")},
        "deduplicated": deduplicated,
        "active": _active_summary(canonical),
        "focus": next(({
            "stable_id": item.get("stable_id"),
            "compositor_id": item.get("compositor_id"),
            "pid": item.get("pid"),
            "source": item.get("geometry_source"),
            "verified": bool(item.get("compositor_verified")),
        } for item in canonical if item.get("focused")), None),
        "screen": screen,
        "monitors": monitors,
        "stacking_order": [item.get("stable_id") for item in sorted(
            (item for item in canonical if isinstance(item.get("stacking"), int)),
            key=lambda item: item["stacking"])] if exact else None,
        "semantic_source": "at-spi2",
        "geometry_source": "worldline-gnome-shell" if exact else "at-spi2",
        "counts": {
            "canonical": len(canonical),
            "semantic": len(observed),
            "geometry": len(canonical),
            "verified": sum(item["status"] == "verified" for item in canonical),
            "semantic_only": sum(item["status"] == "semantic_only" for item in canonical),
            "geometry_only": sum(item["status"] == "geometry_only" for item in canonical),
            "deduplicated": len(deduplicated),
            "stale": sum(item["status"] == "stale" for item in deduplicated),
            "duplicate": sum(item["status"] == "duplicate" for item in deduplicated),
        },
        "sources": {
            "semantic": {
                "name": "at-spi2",
                "available": available,
                "reason": atspi.get("reason"),
                "count": atspi.get("count", 0),
            },
            "geometry": {
                "name": "worldline-gnome-shell" if exact else "at-spi2",
                "available": bool(compositor.get("available")) or available,
                "reason": compositor.get("reason") if not exact else None,
                "count": len(canonical),
                "helper_api": compositor.get("helper_api"),
                "limitations": [
                    "component extents may differ from compositor frames",
                    "stacking and pixel visibility are not observed",
                ],
            },
        },
    }
    if not available:
        result["reason"] = atspi.get("reason") or "accessibility bus is not reachable"
    return result


def windows_snapshot(*, exact_only: bool = False,
                     display: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return a windows section, optionally using compositor frames only."""
    return _windows(exact_only=exact_only, display_override=display)


def _boot_epoch() -> float:
    uptime = _num((_read("/proc/uptime", "0") or "0").split()[0], 2) or 0.0
    return time.time() - uptime


_USERS: dict[int, str] = {}


def _user(uid: int | None) -> str | None:
    if uid is None:
        return None
    if uid not in _USERS:
        try:
            _USERS[uid] = pwd.getpwuid(uid).pw_name
        except KeyError:
            _USERS[uid] = str(uid)
    return _USERS[uid]


def _process(pid: int, boot: float) -> dict[str, Any] | None:
    raw = _read(f"/proc/{pid}/stat")
    if not raw:
        return None
    close = raw.rfind(")")
    open_ = raw.find("(")
    if close < 0 or open_ < 0:
        return None
    name = raw[open_ + 1 : close]
    fields = raw[close + 2 :].split()
    if len(fields) < 22:
        return None
    try:
        uid = os.stat(f"/proc/{pid}").st_uid
    except OSError:
        uid = None
    state = fields[0]
    ppid = _int(fields[1])
    utime = _int(fields[11], 0) or 0
    stime = _int(fields[12], 0) or 0
    threads = _int(fields[17])
    start = _int(fields[19], 0) or 0
    rss = _int(fields[21], 0) or 0
    return {
        "pid": pid,
        "ppid": ppid,
        "user": _user(uid),
        "name": name,
        "state": state,
        "threads": threads,
        "rss_bytes": rss * _PAGE,
        "cpu_ticks": utime + stime,
        "started_at": _now_iso(boot + start / _CLK_TCK),
        "cmdline": _cmdline(pid),
    }


def _processes(full: bool = False) -> dict[str, Any]:
    boot = _boot_epoch()
    processes: list[dict[str, Any]] = []
    for entry in os.scandir("/proc"):
        if not entry.name.isdigit():
            continue
        item = _process(int(entry.name), boot)
        if item is not None:
            processes.append(item)
    processes.sort(key=lambda item: item["rss_bytes"], reverse=True)
    top = [dict(item) for item in processes[:TOP_PROCESSES]]
    for item in top:
        item.pop("cmdline", None)
    result: dict[str, Any] = {
        "count": len(processes),
        "threads": sum(item.get("threads") or 0 for item in processes),
        "top": top,
        "self_pid": os.getpid(),
    }
    if full:
        result["all"] = processes
    return result


_TOOLS = (
    "git",
    "gh",
    "rg",
    "fd",
    "fzf",
    "jq",
    "yq",
    "curl",
    "wget",
    "ssh",
    "scp",
    "rsync",
    "tmux",
    "screen",
    "docker",
    "podman",
    "kubectl",
    "systemctl",
    "journalctl",
    "loginctl",
    "gdbus",
    "busctl",
    "dbus-send",
    "gsettings",
    "dconf",
    "flatpak",
    "snap",
    "apt",
    "dpkg",
    "nmcli",
    "upower",
    "pactl",
    "wpctl",
    "wmctrl",
    "xdotool",
    "ydotool",
    "wtype",
    "grim",
    "slurp",
    "gnome-screenshot",
    "ffmpeg",
    "magick",
    "convert",
    "tesseract",
    "node",
    "npm",
    "pnpm",
    "bun",
    "deno",
    "python3",
    "pip3",
    "uv",
    "cargo",
    "rustc",
    "go",
    "gcc",
    "clang",
    "make",
    "cmake",
    "code",
    "firefox",
    "chromium",
    "google-chrome",
    "libreoffice",
    "nautilus",
)


def _tools() -> dict[str, str | None]:
    return {name: shutil.which(name) for name in _TOOLS}


def _percent(output: str) -> int | None:
    match = re.search(r"(\d+)%", output)
    return int(match.group(1)) if match else None


def _audio() -> dict[str, Any]:
    if shutil.which("pactl") is None:
        return {"available": False}
    info = _run(("pactl", "info"))
    server = None
    if info is not None and info[0] == 0:
        for line in info[1].splitlines():
            if line.startswith("Server Name:"):
                _, _, server = line.partition(":")
                server = server.strip()
                break
    sink = _run(("pactl", "get-default-sink"))
    source = _run(("pactl", "get-default-source"))
    volume = _run(("pactl", "get-sink-volume", "@DEFAULT_SINK@"))
    mute = _run(("pactl", "get-sink-mute", "@DEFAULT_SINK@"))
    return {
        "available": True,
        "server": server,
        "default_sink": sink[1].strip() if sink and sink[0] == 0 else None,
        "default_source": source[1].strip() if source and source[0] == 0 else None,
        "sink_volume_percent": _percent(volume[1])
        if volume and volume[0] == 0
        else None,
        "sink_muted": "yes" in mute[1].lower() if mute and mute[0] == 0 else None,
    }


def _power() -> dict[str, Any]:
    supplies: list[dict[str, Any]] = []
    root = Path("/sys/class/power_supply")
    if root.exists():
        for entry in sorted(root.iterdir()):
            kind = _text(entry / "type")
            if kind == "Mains":
                supplies.append(
                    {
                        "name": entry.name,
                        "type": "ac",
                        "online": _text(entry / "online") == "1",
                    }
                )
            elif kind == "Battery":
                energy = _int(_text(entry / "energy_now"))
                power = _int(_text(entry / "power_now"))
                seconds = None
                if energy is not None and power:
                    seconds = int(energy / power * 3600)
                supplies.append(
                    {
                        "name": entry.name,
                        "type": "battery",
                        "status": _text(entry / "status"),
                        "energy_now": energy,
                        "power_now": power,
                        "percent": _int(_text(entry / "capacity")),
                        "voltage_now": _int(_text(entry / "voltage_now")),
                        "cycle_count": _int(_text(entry / "cycle_count")),
                        "seconds_left": seconds
                        if _text(entry / "status") == "Discharging"
                        else None,
                        "seconds_to_full": seconds
                        if _text(entry / "status") == "Charging"
                        else None,
                    }
                )

    temperatures: list[float] = []
    for zone in sorted(Path("/sys/class/thermal").glob("thermal_zone*")):
        value = _int(_text(zone / "temp"))
        if value is not None:
            temperatures.append(round(value / 1000, 1))

    ac = next((item for item in supplies if item["type"] == "ac"), None)
    batteries = [item for item in supplies if item["type"] == "battery"]
    return {
        "ac": ac,
        "on_ac": bool(ac and ac.get("online")),
        "batteries": batteries,
        "thermal_c": max(temperatures) if temperatures else None,
    }


def _git(directory: Path) -> dict[str, Any]:
    root = None
    for parent in (directory, *directory.parents):
        if (parent / ".git").exists():
            root = parent
            break
    if root is None:
        return {"root": None}

    marker = root / ".git"
    if marker.is_file():
        raw = _read(marker, "")
        line = raw.strip()
        if line.startswith("gitdir:"):
            git_dir = (root / line.partition(":")[2].strip()).resolve()
        else:
            git_dir = marker
    else:
        git_dir = marker

    head = _text(git_dir / "HEAD") or ""
    branch = None
    commit = None
    if head.startswith("ref:"):
        ref = head.partition(":")[2].strip()
        branch = ref.removeprefix("refs/heads/")
        commit = _text(git_dir / ref)
    elif head:
        commit = head
    return {
        "root": str(root),
        "branch": branch,
        "head": commit,
        "detached": bool(commit and branch is None),
    }


def _cwd() -> dict[str, Any]:
    path = Path.cwd()
    try:
        stat = os.stat(path)
    except OSError:
        stat = None
    return {
        "path": str(path),
        "writable": os.access(path, os.W_OK),
        "device": stat.st_dev if stat else None,
        "inode": stat.st_ino if stat else None,
        "git": _git(path),
    }


SECTION_ORDER = (
    "time",
    "host",
    "os",
    "cpu",
    "pressure",
    "memory",
    "storage",
    "network",
    "session",
    "desktop",
    "windows",
    "processes",
    "power",
    "audio",
    "cwd",
    "tools",
)

_COLLECTORS: dict[str, Callable[..., Any]] = {
    "time": _time,
    "host": _host,
    "os": _os,
    "cpu": _cpu,
    "pressure": _pressure,
    "memory": _memory,
    "storage": _storage,
    "network": _network,
    "session": _session,
    "desktop": _desktop,
    "windows": _windows,
    "processes": _processes,
    "power": _power,
    "audio": _audio,
    "cwd": _cwd,
    "tools": _tools,
}


def sections() -> tuple[str, ...]:
    return SECTION_ORDER


def observe(
    sections: Iterable[str] | None = None, *, full: bool = False
) -> dict[str, Any]:
    """Collect a world snapshot.

    ``sections`` limits collection to the named top-level sections.
    ``full`` adds every process (the default snapshot keeps the top 12).
    """

    requested = set(SECTION_ORDER if sections is None else sections)
    unknown = requested.difference(_COLLECTORS)
    if unknown:
        raise KeyError(f"unknown section: {', '.join(sorted(unknown))}")

    world: dict[str, Any] = {"schema": SCHEMA, "collected_at": _now_iso()}
    errors: list[dict[str, str]] = []
    for name in SECTION_ORDER:
        if name not in requested:
            continue
        try:
            if name == "processes":
                world[name] = _processes(full=full)
            else:
                world[name] = _COLLECTORS[name]()
        except Exception as exc:
            errors.append({"section": name, "error": f"{type(exc).__name__}: {exc}"})
    if errors:
        world["errors"] = errors
    return world
