from __future__ import annotations

import os
import shutil
import subprocess
from time import time
from typing import Iterable

from worldline.model import Evidence, Fact
from worldline.sources import SourceSurface
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
    source_surfaces = (
        SourceSurface("session-environment", "process environment",
                      "direct_read", "negligible",
                      ("gnome.session.*",),
                      "Reads XDG session values without contacting a service."),
        SourceSurface("installed-programs", "PATH and filesystem executable metadata",
                      "direct_read", "negligible",
                      ("*.installed",),
                      "Uses shutil.which rather than launching a program."),
        SourceSurface("program-versions", "installed program --version",
                      "service_query", "bounded",
                      ("gnome.shell.version", "gnome.mutter.version",
                       "media.pipewire.version", "media.wireplumber.version",
                       "computer_use.cua_driver.version"),
                      "Runs only when an explicit active sample is requested."),
        SourceSurface("package-versions", "Ubuntu package metadata via dpkg-query",
                      "service_query", "bounded",
                      ("gnome.mutter.package_version", "gnome.shell.package_version")),
        SourceSurface("session-properties", "logind via loginctl",
                      "service_query", "bounded",
                      ("gnome.session.active", "gnome.session.locked"),
                      "Session truth belongs to logind; do not substitute /proc guesses."),
        SourceSurface("desktop-configuration", "GSettings",
                      "service_query", "bounded",
                      ("gnome.settings.color_scheme",)),
        SourceSurface("accessibility-reachability", "AT-SPI session bus via gdbus",
                      "service_query", "bounded",
                      ("gnome.atspi.bus.reachable",),
                      "A bus introspection proves reachability, not accessible UI content."),
    )

    def observe_fast(self) -> Iterable[Fact]:
        """Direct bounded reads only; no shelling out, D-Bus query or service RPC."""
        return self._collect(active=False)

    def observe(self) -> Iterable[Fact]:
        """Full on-demand sample; external queries have per-command timeouts."""
        return self._collect(active=True)

    def _collect(self, *, active: bool) -> list[Fact]:
        sampled_at = time()

        def evidence(source: str, detail: dict | None = None) -> Evidence:
            # Fact observation is not a timeless assertion. Long-lived daemon
            # snapshots must expire when a host/service might have changed.
            return Evidence(source=source, observed_at=sampled_at,
                            expires_at=sampled_at + (30 if active else 10),
                            detail=detail or {})

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
            if installed and active:
                version = _run([command, "--version"])
                if version:
                    facts.append(Fact(fact_key, version, evidence("command", {"command": command})))

        if active and shutil.which("dpkg-query"):
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
        if active and session_id and shutil.which("loginctl"):
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

        if active and shutil.which("gsettings"):
            scheme = _run(["gsettings", "get", "org.gnome.desktop.interface", "color-scheme"])
            if scheme:
                facts.append(Fact("gnome.settings.color_scheme", scheme.strip("'"),
                                  evidence("gsettings")))

        if not active:
            return facts

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
