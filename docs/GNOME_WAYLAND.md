# GNOME / Wayland platform model

GNOME 51 is the current stable GNOME line. Ubuntu 26.04 remains a distinct distribution target with its own GNOME/Mutter version, so WORLDLINE records the runtime instead of assuming a major version.

## Evidence tiers

```text
direct OS fact
    ↓
correlated source state
    ↓
derived state
    ↓
visual / model inference
```

For the GNOME desktop, preferred sources are:

1. environment and session metadata;
2. system services (`logind`, NetworkManager, UPower);
3. AT-SPI semantic events/state;
4. Cua's exact GNOME integration for window/activation geometry;
5. XDG ScreenCast / PipeWire when pixels are required.

## What changes with GNOME

Mutter owns compositor behavior. WORLDLINE therefore treats compositor generations and window identities as evidence-bearing state rather than durable assumptions.

A compositor restart invalidates compositor-backed identities. A new PipeWire stream creates a new media generation. An AT-SPI interruption makes semantic facts unavailable until evidence returns.

The adapter boundary is deliberate: new Mutter/GNOME releases should usually change the provider, not the world model.

## Observation

Run:

```bash
worldlinectl observe
```

This performs a bounded read-only observation of the local GNOME/Wayland host and commits only facts that were actually observed.

The provider never injects input.

## Mutter 50 / 51 compatibility evidence (October 2026)

Upstream Mutter 51.1 changes window/monitor assignment, cross-Wayland/Xwayland drag-and-drop, sticky-window ordering, and workspace behavior around display reconfiguration. Ubuntu 26.04 stays on its packaged GNOME 50 line unless an update is observed locally. Do not infer distribution behavior from the upstream version.

The GNOME provider reads `mutter-common` and `gnome-shell` package versions from `dpkg-query` where available, publishing `gnome.mutter.package_version` and `gnome.shell.package_version` with provenance. Missing packages produce no version fact; they do not imply a particular version. The package facts identify the installed build, **not** the running compositor after an in-session package upgrade or compositor restart.

Consumer policy:

1. Continue to use an attested live compositor read for actual focus, window identity, monitor ownership and geometry.
2. After a monitor/workspace reconfiguration, refresh geometry before coordinate action; do not reuse the previous placement as an operating fact.
3. Separate action success from a delayed PipeWire visual confirmation. Capture generations and presentation evidence must still match the active observation.
4. Verify GNOME 50 / 51 regressions in a real desktop acceptance lane before claiming support; the provider itself performs no actuation.

No WORLDLINE core schema migration is required for this release. These are new evidence values and consumer preconditions.
