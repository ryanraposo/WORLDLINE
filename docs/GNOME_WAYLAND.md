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
