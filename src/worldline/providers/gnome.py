from __future__ import annotations

import os
import shutil
import subprocess
from time import time
from typing import Iterable

from worldline.model import Evidence, Fact
from .base import ObservationProvider


def _run(argv: list[str], timeout: float = 0.8) -> str | None:
    try:
        result = subprocess.run(
            argv, text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            timeout=timeout, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout.strip() if result.returncode == 0 else None


class GNOMEProvider(ObservationProvider):
    """Low-cost GNOME/Wayland host facts; never an actuation path."""

    name = "gnome"

    def observe(self) -> Iterable[Fact]:
        def evidence(source: str, detail: dict | None = None) -> Evidence:
            return Evidence(source=source, detail=detail or {}, expires_at=time() + 65)

        facts: list[Fact] = []
        for key, value in {
            "session.type": os.environ.get("XDG_SESSION_TYPE"),
            "session.desktop": os.environ.get("XDG_CURRENT_DESKTOP"),
            "session.wayland_display": os.environ.get("WAYLAND_DISPLAY"),
            "session.runtime_dir": os.environ.get("XDG_RUNTIME_DIR"),
        }.items():
            if value:
                facts.append(Fact(f"gnome.{key}", value, evidence("environment")))

        for command, fact_key in (
            ("gnome-shell", "gnome.shell.version"),
            ("mutter", "gnome.mutter.version"),
            ("pipewire", "media.pipewire.version"),
            ("wireplumber", "media.wireplumber.version"),
            ("cua-driver", "computer_use.cua_driver.version"),
        ):
            installed = shutil.which(command) is not None
            facts.append(Fact(
                fact_key + ".installed", installed,
                evidence("path", {"command": command}),
            ))
            if installed:
                version = _run([command, "--version"])
                if version:
                    facts.append(Fact(fact_key, version, evidence("command", {"command": command})))

        # Ubuntu's Mutter package can be newer than the shell's reported
        # version. Record the installed package independently: compatibility
        # decisions must use evidence from the running distribution, not a
        # guessed mapping between GNOME and Ubuntu release numbers.
        if shutil.which("dpkg-query"):
            for package, key in (
                ("mutter-common", "gnome.mutter.package_version"),
                ("gnome-shell", "gnome.shell.package_version"),
            ):
                version = _run(["dpkg-query", "-W", "-f=${Version}", package])
                if version:
                    facts.append(Fact(key, version, evidence(
                        "dpkg-query", {"package": package},
                    )))

        session_id = os.environ.get("XDG_SESSION_ID")
        if session_id and shutil.which("loginctl"):
            state = _run([
                "loginctl", "show-session", session_id,
                "-p", "Active", "-p", "LockedHint", "--value",
            ])
            if state:
                values = state.splitlines()
                if values:
                    facts.append(Fact("gnome.session.active", values[0].lower() == "yes",
                                      evidence("loginctl")))
                if len(values) > 1:
                    facts.append(Fact("gnome.session.locked", values[1].lower() == "yes",
                                      evidence("loginctl")))

        if shutil.which("gsettings"):
            scheme = _run(["gsettings", "get", "org.gnome.desktop.interface", "color-scheme"])
            if scheme:
                facts.append(Fact("gnome.settings.color_scheme", scheme.strip("'"),
                                  evidence("gsettings")))

        atspi = (
            _run([
                "gdbus", "introspect", "--session",
                "--dest", "org.a11y.Bus", "--object-path", "/org/a11y/bus",
            ], 1.0)
            if shutil.which("gdbus") else None
        )
        facts.append(Fact(
            "gnome.atspi.bus.reachable", atspi is not None,
            evidence("gdbus", {"destination": "org.a11y.Bus"}),
        ))
        return facts
