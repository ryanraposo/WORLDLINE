# Cua / GWCU integration

WORLDLINE is the **truth and contingent-continuation layer** around a computer-use system.

```text
agent / skill
     |
     v
GWCU policy
     |
     v
Cua Driver  ----------------> desktop actuation
     |
     +---- evidence ----------> WORLDLINE
                                  |
                                  +--> revision
                                  +--> invalidation
                                  +--> fence
                                  +--> wait / predicate
                                  +--> receipt
     |
     +---- durable local identity / preferences --> .gwcu
```

## Ownership

- **Cua Driver** owns GUI actuation, application/window targeting, sessions, input, cursor and compositor-specific control.
- **GWCU** owns local policy, capability adaptation and action-span composition.
- **WORLDLINE** owns transient, revisioned facts and evidence-backed continuation.
- **.gwcu** owns low-churn durable machine/workspace truth.
- **Agent reasoning** owns intent and ambiguity.

WORLDLINE must never grow a parallel input path. In particular, it must not call `ydotool`, `/dev/uinput`, a project-owned RDP/VNC server, or a hidden browser control plane.

## The causal boundary

For an awaited mutation:

```text
PRESENT
  |
  v
WORLDLINE fence
  |
  v
Cua mutation
  |
  v
new evidence/event
  |
  v
WORLDLINE wait(fresh_after=fence)
  |
  v
postcondition proved
```

A fact that was already true before the fence cannot satisfy a freshness-constrained postcondition. This distinguishes state being true from this action producing evidence that state is true.

## Runtime discovery

Cua evolves independently. WORLDLINE should discover the capabilities actually present on the machine rather than hard-code an imagined Cua API.

The maintained Cua/Hermes path is:

- `hermes computer-use status`
- `hermes computer-use doctor`
- `cua-driver status`
- `cua-driver skills status`

Use Hermes' built-in `computer_use` surface for agent interaction. Raw `cua-driver mcp` is a development/debugging surface, not a second production control plane.

## Persistent installation

The computer-use driver is a machine capability, not a per-task dependency. Installation belongs to the host integration (GWCU/Hermes), and subsequent sessions reuse the installed driver/service.

WORLDLINE may observe driver availability and version:

```text
computer_use.cua_driver.version.installed
computer_use.cua_driver.version
```

It does not install, restart, or mutate the driver as part of ordinary observation.

## GNOME 50 / 51 boundary

GNOME/Mutter is a versioned platform adapter, not WORLDLINE's ontology.

WORLDLINE consumes stable facts such as session state, AT-SPI reachability and observed compositor/runtime versions. Window geometry, exact activation and foreground proof remain Cua/GNOME-helper responsibilities.

That lets GNOME 51 evolve without turning the truth core into a Mutter API compatibility layer.
