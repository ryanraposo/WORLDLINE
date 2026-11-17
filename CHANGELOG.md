# Changelog

All notable WORLDLINE changes are documented here.

## [0.3.0] — 2026-11-17

First prepared public release candidate.

- **Observation service:** Read-only, revisioned observations across host, operating system, resources, processes, networking, desktop session, displays, windows, audio, working context, available tools, and time.
- **Desktop geometry:** Logical monitor and window geometry with explicit source and verification status; compositor-derived frame and stacking observations are kept distinct from accessibility extents.
- **Protocol:** Version 1 newline-delimited JSON over a user-private Unix socket, including feature discovery and receipt support for independent consumers.
- **Installation:** Managed user-service lifecycle with install, status, start, upgrade, repair, and uninstall commands; safeguards preserve unmanaged checkouts, services, and pre-existing extension state.
- **GNOME integration:** Optional read-only window-frame extension with explicit permission before installation and enablement.
- **Developer interface:** JSON CLI, path queries, freshness and explanation modes, geometry terminal view, and control client.
- **Documentation and site:** Installation and integration guidance, capability overview, geometry demonstration, canonical brand assets, and GitHub Pages site.
- **Validation:** Python test suite, installer lifecycle tests, CI matrix, distribution build checks, and tag-driven release verification.

This release targets Ubuntu with GNOME on Wayland. It is an observation layer, not an input actuator or action-policy engine.
