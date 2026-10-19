# Ubuntu 26.04 LTS — platform iteration

Ubuntu 26.04 LTS with GNOME on Wayland is the first explicitly documented WORLDLINE host iteration.

## Current implementation boundary

`src/worldline/providers/gnome.py` currently reads `XDG_SESSION_TYPE`, `XDG_CURRENT_DESKTOP`, `WAYLAND_DISPLAY` and `XDG_RUNTIME_DIR`; tests command availability and version output; queries `loginctl` session flags when an ID is present; reads the GNOME color-scheme setting; and probes AT-SPI bus reachability. These are the implemented observation paths, subject to runtime availability. The richer sources below are iteration targets rather than verified provider coverage.

## Proposed observation surfaces

| Surface | Evidence | Operating facts |
| --- | --- | --- |
| OS | `/etc/os-release`, kernel interfaces | distribution, release, kernel |
| Session | `loginctl`, environment | session type, seat, active session |
| Desktop | GNOME Shell, Mutter, D-Bus | desktop version, displays, focus, workspaces |
| UI semantics | AT-SPI2 | accessible application, role, name, state |
| Media | PipeWire, portals | available nodes, authorized capture session |
| System | systemd, NetworkManager, UPower | service, network, power state |
| Processes | `/proc` | process identity and lifecycle |

## Iteration sequence

1. **Discover:** report available observation interfaces and their versions, with evidence and readiness.
2. **Capture:** normalize source observations into typed Operating Facts, preserving timestamps and provenance.
3. **Reconcile:** advance revisions on events and bounded refreshes; record changed and unavailable facts.
4. **Query and wait:** expose snapshots, fences and evidence-backed contingent waits.
5. **Verify:** exercise focus changes, window transitions, workspace changes, session lifecycle and source outages on an Ubuntu 26.04 GNOME Wayland host.

## Acceptance evidence

Capture real host receipts and verify that observed values correspond to source state, revisions are monotonic, and consumers can distinguish DIRECT, CORRELATED, DERIVED and INFERRED evidence. This document specifies the Ubuntu 26 iteration; it does not assert that all providers or tests are implemented.
