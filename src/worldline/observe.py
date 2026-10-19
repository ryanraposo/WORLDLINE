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
                        key = (pid, role, title, tuple(frame.values()))
                        if key in seen:
                            continue
                        seen.add(key)
                        items.append(
                            {
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


def _parse_winrects(payload: Any, *, version: Any = None) -> dict[str, Any]:
    """Normalize a decoded WinRects payload into compositor window records."""

    if not isinstance(payload, list):
        return {
            "source": "org.cua.WinRects",
            "available": False,
            "reason": "WinRects payload is not a window list",
            "count": 0,
            "items": [],
        }

    items: list[dict[str, Any]] = []
    for entry in payload:
        if not isinstance(entry, dict):
            continue
        try:
            frame = window_geometry.rect(entry["x"], entry["y"], entry["w"], entry["h"])
            if frame["width"] <= 0 or frame["height"] <= 0:
                continue
            pid = int(entry.get("pid") or 0)
            title = str(entry.get("title") or "")
            items.append(
                {
                    "id": int(entry["id"]) if entry.get("id") is not None else None,
                    "pid": pid,
                    "app": _text(f"/proc/{pid}/comm") if pid else None,
                    "title": title,
                    "role": "frame",
                    "frame": frame,
                    "buffer_origin": {
                        "x": int(entry.get("buffer_x", entry["x"])),
                        "y": int(entry.get("buffer_y", entry["y"])),
                    },
                    "focused": bool(entry.get("focused")),
                    "minimized": bool(entry.get("minimized")),
                    "visible": bool(entry.get("visible", True)),
                    "stacking": int(entry["stacking"])
                    if entry.get("stacking") is not None
                    else None,
                    "source": "org.cua.WinRects",
                }
            )
        except (KeyError, TypeError, ValueError):
            continue

    return {
        "source": "org.cua.WinRects",
        "available": True,
        "version": version,
        "count": len(items),
        "items": items,
    }


def _winrects_reply(raw: Any, *, version: Any = None) -> dict[str, Any]:
    """Decode a ``GetRects`` D-Bus reply into a WinRects observation."""

    if not raw:
        return {
            "source": "org.cua.WinRects",
            "available": False,
            "reason": "WinRects helper is not available",
            "count": 0,
            "items": [],
        }
    try:
        payload = json.loads(raw[0] if isinstance(raw, tuple) else raw)
    except (TypeError, json.JSONDecodeError) as exc:
        return {
            "source": "org.cua.WinRects",
            "available": False,
            "reason": f"{type(exc).__name__}: {exc}",
            "count": 0,
            "items": [],
        }
    return _parse_winrects(payload, version=version)


def _compositor_windows() -> dict[str, Any]:
    """Read exact frame rectangles from the Cua WinRects Shell helper."""

    version = _dbus_call(
        "org.cua.WinRects",
        "/org/cua/WinRects",
        "org.cua.WinRects",
        "GetVersion",
        timeout=0.5,
    )
    raw = _dbus_call(
        "org.cua.WinRects",
        "/org/cua/WinRects",
        "org.cua.WinRects",
        "GetRects",
        timeout=0.75,
    )
    return _winrects_reply(
        raw,
        version=version[0] if isinstance(version, tuple) and version else None,
    )


_MATCH_CONFIDENCE = {
    "pid_title_frame": 0.99,
    "pid_title": 0.95,
    "pid_partial_title": 0.8,
    "title_frame": 0.75,
    "pid_frame": 0.7,
    "pid_only": 0.5,
    "semantic_only": 0.5,
    "compositor_only": 0.9,
    "stale": 0.05,
    "duplicate": 0.1,
}


def _title_state(first: Any, second: Any) -> str | None:
    left = (first or "").strip().casefold()
    right = (second or "").strip().casefold()
    if not left or not right:
        return None
    if left == right:
        return "exact"
    if left in right or right in left:
        return "partial"
    return None


def _match_evidence(
    window: dict[str, Any], candidate: dict[str, Any]
) -> dict[str, Any] | None:
    """Score one semantic/compositor pair and describe the join evidence.

    A join is only proposed when the evidence supports identity: the same
    process (with a title or frame signal) or an exact cross-process title with
    a frame overlap.  Geometry alone never joins unrelated processes.
    """

    pid = window.get("pid")
    candidate_pid = candidate.get("pid")
    same_pid = bool(pid and candidate_pid == pid)
    title = _title_state(window.get("title"), candidate.get("title"))
    overlap = window_geometry.overlap_fraction(window["frame"], candidate["frame"])
    if not same_pid and not (title == "exact" and overlap > 0):
        return None
    if same_pid and title is None and overlap <= 0:
        # Weak same-process pair: resolved only by the unambiguous-pid fallback.
        return None

    if same_pid and title == "exact" and overlap >= 0.5:
        method = "pid_title_frame"
    elif same_pid and title == "exact":
        method = "pid_title"
    elif same_pid and title == "partial":
        method = "pid_partial_title"
    elif same_pid and overlap >= 0.5:
        method = "pid_frame"
    else:
        method = "title_frame"

    score = 0.0
    if title == "exact":
        score += 100.0
    elif title == "partial":
        score += 35.0
    score += overlap * 60.0
    score -= min(
        30.0, window_geometry.rect_distance(window["frame"], candidate["frame"]) / 40.0
    )
    if candidate.get("focused") and window.get("focused"):
        score += 5.0
    return {
        "method": method,
        "confidence": _MATCH_CONFIDENCE[method],
        "band": "verified",
        "score": round(score, 3),
        "pid_match": same_pid,
        "title_match": title,
        "frame_overlap": overlap,
    }


def _join_windows(
    semantic: list[dict[str, Any]], compositor: list[dict[str, Any]]
) -> tuple[dict[int, dict[str, Any]], set[int]]:
    """Join semantic windows to compositor frames by evidence strength.

    Pairs are assigned strongest-first so a stale or untitled semantic object
    cannot consume the compositor frame that belongs to a better-evidenced
    sibling.  A final unambiguous same-process pass handles windows whose
    titles are empty and whose geometry has moved between the two sources.
    """

    pairs: list[tuple[float, int, int, dict[str, Any]]] = []
    for semantic_index, window in enumerate(semantic):
        for compositor_index, candidate in enumerate(compositor):
            evidence = _match_evidence(window, candidate)
            if evidence is not None:
                pairs.append(
                    (evidence["score"], semantic_index, compositor_index, evidence)
                )
    pairs.sort(key=lambda pair: (-pair[0], pair[1], pair[2]))

    joins: dict[int, dict[str, Any]] = {}
    used_compositor: set[int] = set()
    for _, semantic_index, compositor_index, evidence in pairs:
        if semantic_index in joins or compositor_index in used_compositor:
            continue
        joins[semantic_index] = {
            "candidate": compositor[compositor_index],
            "evidence": evidence,
        }
        used_compositor.add(compositor_index)

    # Empty titles and moved frames can leave one window on each side of a
    # process.  That is still meaningful identity evidence, but only when the
    # mapping is unambiguous.
    remaining_semantic: dict[int, list[int]] = {}
    remaining_compositor: dict[int, list[int]] = {}
    for index, window in enumerate(semantic):
        pid = window.get("pid")
        if index not in joins and pid:
            remaining_semantic.setdefault(pid, []).append(index)
    for index, candidate in enumerate(compositor):
        pid = candidate.get("pid")
        if index not in used_compositor and pid:
            remaining_compositor.setdefault(pid, []).append(index)
    for pid, semantic_indexes in remaining_semantic.items():
        compositor_indexes = remaining_compositor.get(pid, [])
        if len(semantic_indexes) != 1 or len(compositor_indexes) != 1:
            continue
        semantic_index = semantic_indexes[0]
        compositor_index = compositor_indexes[0]
        joins[semantic_index] = {
            "candidate": compositor[compositor_index],
            "evidence": {
                "method": "pid_only",
                "confidence": _MATCH_CONFIDENCE["pid_only"],
                "band": "verified",
                "score": 0.0,
                "pid_match": True,
                "title_match": None,
                "frame_overlap": window_geometry.overlap_fraction(
                    semantic[semantic_index]["frame"],
                    compositor[compositor_index]["frame"],
                ),
            },
        }
        used_compositor.add(compositor_index)

    return joins, used_compositor


def _semantic_exclusion(
    item: dict[str, Any],
    canonical: list[dict[str, Any]],
    screen: dict[str, Any] | None,
) -> tuple[str, str] | None:
    """Classify an unmatched semantic frame that should not be canonical.

    The rule is intentionally conservative and evidence-bearing: an item is
    deduplicated only when it duplicates a represented window or has a
    degenerate off-screen frame that cannot be a usable surface.
    """

    frame = item["frame"]
    width, height = frame["width"], frame["height"]
    title = (item.get("title") or "").strip()
    pid = item.get("pid")
    for other in canonical:
        if not pid or other.get("pid") != pid:
            continue
        other_title = (other.get("title") or "").strip()
        same_title = bool(
            title and other_title and title.casefold() == other_title.casefold()
        )
        if not same_title:
            continue
        # A second compositor-only window with the same identity may be a real
        # sibling (for example two documents with the same title), so only
        # collapse when no unpaired compositor frame remains.
        has_unpaired_geometry = any(
            candidate.get("status") == "geometry_only"
            and (candidate.get("pid") or None) == (pid or None)
            and (candidate.get("title") or "").strip().casefold() == title.casefold()
            for candidate in canonical
        )
        if not has_unpaired_geometry:
            label = other.get("stable_id") or other.get("id") or "another frame"
            return (
                "duplicate",
                f"same process and title as {label}; no unpaired compositor frame",
            )

    visible = (
        window_geometry.intersection(frame, screen) if screen is not None else frame
    )
    if visible is None and window_geometry.area(frame) <= 1:
        return (
            "stale",
            f"degenerate off-screen frame {width}x{height} at "
            f"({frame['x']},{frame['y']})",
        )
    if visible is None and not title and window_geometry.area(frame) <= 64:
        return (
            "stale",
            f"untitled off-screen frame {width}x{height} at "
            f"({frame['x']},{frame['y']})",
        )
    return None


def _active_summary(items: list[dict[str, Any]]) -> dict[str, Any] | None:
    active = next((item for item in items if item.get("active")), None)
    if active is None:
        active = next((item for item in items if item.get("focused")), None)
    if active is None:
        return None
    return {
        "id": active.get("id"),
        "pid": active.get("pid"),
        "app": active.get("app"),
        "title": active.get("title"),
        "geometry": active.get("geometry"),
    }


def _windows() -> dict[str, Any]:
    """Collect window identities, state and canonical frame geometry.

    AT-SPI supplies semantic identity (application, title, role, modal state).
    The WinRects compositor helper supplies exact frame rectangles, stable
    window ids, stacking order and visibility.  When both exist the window is
    joined by process, title and geometry evidence; neither source is required.

    Unmatched semantic frames are retained as canonical windows when they look
    like real surfaces.  Degenerate stale frames and duplicates are moved to
    ``deduplicated`` with an explicit reason, so the window count describes
    distinct windows without discarding the original observation.
    """

    atspi = _atspi_windows()
    compositor = _compositor_windows()
    display = _display()
    monitors = display.get("monitors") or []
    screen = display.get("screen")

    atspi_items: list[dict[str, Any]] = list(atspi.get("items") or [])
    compositor_items: list[dict[str, Any]] = list(compositor.get("items") or [])
    joins, used = _join_windows(atspi_items, compositor_items)
    merged: list[dict[str, Any]] = []

    for index, window in enumerate(atspi_items):
        item = dict(window)
        join = joins.get(index)
        if join is not None:
            match = join["candidate"]
            item.update(
                {
                    "id": match.get("id"),
                    "pid": match.get("pid") or window.get("pid"),
                    "app": window.get("app") or match.get("app"),
                    "title": match.get("title") or window.get("title"),
                    "frame": match["frame"],
                    "buffer_origin": match.get("buffer_origin"),
                    "focused": bool(match.get("focused") or window.get("focused")),
                    "minimized": bool(
                        match.get("minimized") or window.get("minimized")
                    ),
                    "visible": bool(match.get("visible", True)),
                    "stacking": match.get("stacking"),
                    "sources": ["at-spi2", "org.cua.WinRects"],
                    "geometry_source": "org.cua.WinRects",
                    "status": "verified",
                    "confidence": join["evidence"]["confidence"],
                    "match": join["evidence"],
                }
            )
        else:
            item.update(
                {
                    "sources": ["at-spi2"],
                    "geometry_source": "at-spi2",
                    "status": "semantic_only",
                    "confidence": _MATCH_CONFIDENCE["semantic_only"],
                    "match": {
                        "method": "semantic_only",
                        "confidence": _MATCH_CONFIDENCE["semantic_only"],
                        "band": "semantic_only",
                        "score": None,
                        "pid_match": None,
                        "title_match": None,
                        "frame_overlap": None,
                    },
                }
            )
        merged.append(item)

    for index, candidate in enumerate(compositor_items):
        if index in used:
            continue
        item = dict(candidate)
        item.update(
            {
                "sources": ["org.cua.WinRects"],
                "geometry_source": "org.cua.WinRects",
                "status": "geometry_only",
                "confidence": _MATCH_CONFIDENCE["compositor_only"],
                "match": {
                    "method": "compositor_only",
                    "confidence": _MATCH_CONFIDENCE["compositor_only"],
                    "band": "geometry_only",
                    "score": None,
                    "pid_match": None,
                    "title_match": None,
                    "frame_overlap": None,
                },
            }
        )
        merged.append(item)

    if not monitors and not screen:
        frames = [item["frame"] for item in merged if item.get("frame")]
        if frames:
            screen = window_geometry.union(frames)
            if screen is not None:
                screen = {
                    "x": 0,
                    "y": 0,
                    "width": screen["width"],
                    "height": screen["height"],
                }

    # Stable ids exist before deduplication so exclusion reasons can cite them.
    for item in merged:
        if item.get("id") is not None and item.get("pid") is not None:
            item["stable_id"] = f"window:{item['pid']}:{item['id']}"

    verified = [item for item in merged if item["status"] != "semantic_only"]
    semantic_only = [item for item in merged if item["status"] == "semantic_only"]
    canonical: list[dict[str, Any]] = list(verified)
    deduplicated: list[dict[str, Any]] = []
    for item in semantic_only:
        exclusion = _semantic_exclusion(item, canonical, screen)
        if exclusion is None:
            canonical.append(item)
            continue
        status, reason = exclusion
        item.update(
            {
                "status": status,
                "reason": reason,
                "confidence": _MATCH_CONFIDENCE[status],
                "match": {
                    **item["match"],
                    "band": status,
                    "confidence": _MATCH_CONFIDENCE[status],
                },
            }
        )
        deduplicated.append(item)

    merged = canonical
    for item in merged:
        if item.get("stacking") is None:
            item["stacking"] = None
        frame = item["frame"]
        item["x"] = frame["x"]
        item["y"] = frame["y"]
        item["width"] = frame["width"]
        item["height"] = frame["height"]
        item["active"] = bool(item.get("active", False) or item.get("focused", False))
        item["visible"] = bool(item.get("visible", not item.get("minimized", False)))
        item["maximized"] = bool(item.get("maximized", False))
        item["modal"] = bool(item.get("modal", False))
        item["minimized"] = bool(item.get("minimized", False))
        item["shaded"] = bool(item.get("shaded", False))
        item["focused"] = bool(item.get("focused", False))
        item["state"] = {
            "active": item["active"],
            "focused": item["focused"],
            "visible": item["visible"],
            "minimized": item["minimized"],
            "maximized": item["maximized"],
            "shaded": item["shaded"],
            "modal": item["modal"],
        }

    for item in merged:
        stacking = item.get("stacking")
        occluders: list[dict[str, int]] = []
        occlusion_uncertain = False
        if stacking is not None:
            higher = [
                other
                for other in merged
                if other.get("stacking") is not None
                and int(other["stacking"]) > int(stacking)
                and other.get("visible", True)
                and not other.get("minimized", False)
            ]
            occluders = [other["frame"] for other in higher]
            occlusion_uncertain = any(
                other.get("shaded", False)
                and window_geometry.intersection(item["frame"], other["frame"])
                is not None
                for other in higher
            )
        item["geometry"] = window_geometry.describe(
            item["frame"],
            monitors=monitors,
            screen=screen,
            buffer_origin=item.get("buffer_origin"),
            occluders=occluders,
            z_index=stacking,
            visible=item["visible"],
            minimized=item["minimized"],
            shaded=item["shaded"],
            occlusion_uncertain=occlusion_uncertain,
        )

    # Present topmost windows first; AT-SPI-only windows have no proven z-order.
    merged.sort(
        key=lambda item: (
            item.get("stacking") is None,
            -(item.get("stacking") or 0),
            item.get("app") or "",
            item.get("title") or "",
        )
    )

    available = bool(atspi.get("available") or compositor.get("available"))
    if atspi.get("available"):
        source = "at-spi2"
    elif compositor.get("available"):
        source = compositor.get("source", "org.cua.WinRects")
    else:
        # AT-SPI is the canonical semantic source even when unavailable.
        source = "at-spi2"
    result: dict[str, Any] = {
        "source": source,
        "available": available,
        "count": len(merged),
        "items": merged,
        "deduplicated": deduplicated,
        "active": _active_summary(merged),
        "screen": screen,
        "monitors": monitors,
        "stacking_order": "bottom-to-top",
        "semantic_source": atspi.get("source", "at-spi2"),
        "geometry_source": compositor.get("source")
        if compositor.get("available")
        else atspi.get("source", "at-spi2"),
        "counts": {
            "canonical": len(merged),
            "semantic": len(atspi_items),
            "geometry": len(compositor_items),
            "verified": sum(1 for item in merged if item.get("status") == "verified"),
            "semantic_only": sum(
                1 for item in merged if item.get("status") == "semantic_only"
            ),
            "geometry_only": sum(
                1 for item in merged if item.get("status") == "geometry_only"
            ),
            "deduplicated": len(deduplicated),
            "stale": sum(1 for item in deduplicated if item.get("status") == "stale"),
            "duplicate": sum(
                1 for item in deduplicated if item.get("status") == "duplicate"
            ),
        },
        "sources": {
            "semantic": {
                "name": atspi.get("source", "at-spi2"),
                "available": bool(atspi.get("available")),
                "reason": atspi.get("reason"),
                "count": atspi.get("count", 0),
            },
            "geometry": {
                "name": compositor.get("source", "org.cua.WinRects"),
                "available": bool(compositor.get("available")),
                "reason": compositor.get("reason"),
                "version": compositor.get("version"),
                "count": compositor.get("count", 0),
            },
        },
    }
    if not available:
        reasons = [
            value for value in (atspi.get("reason"), compositor.get("reason")) if value
        ]
        result["reason"] = "; ".join(reasons) or "no window source available"
    return result


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
