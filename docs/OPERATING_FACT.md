# WORLDLINE: Operating Fact.

> **WORLDLINE is the current.**

WORLDLINE is a live, revisioned view of what the machine knows now. Every useful
fact carries its own evidence — where it came from, when it was observed, how
confident the system is, and whether it is still valid — so an agent can act
from the present rather than from a stale screenshot interpretation.

## Operating Fact

An **Operating Fact** is a typed statement about the machine at a particular
revision.

```text
Operating Fact
├── type
├── value
├── revision
└── evidence
    ├── source
    ├── observed_at
    └── detail
```

- `type` — DIRECT / CORRELATED / DERIVED / INFERRED knowledge about the machine.
- `value` — the present coordinate.
- `revision` — the world revision when this fact became true.
- `evidence` — the receipt answering "where did we get this?".

## Evidence receipt

Every useful fact has somewhere it came from. Examples:

```text
AT-SPI event
Mutter state
D-Bus property
PipeWire metadata
journal entry
state/config file
environment
Cua observation
bounded command
```

A receipt gives an agent a path back to the system that can explain or refresh
the fact.

## Truth has a type

```text
DIRECT
  ↓
CORRELATED
  ↓
DERIVED
  ↓
INFERRED
```

A direct operating-system fact carries the authority of the subsystem that
stated it. A correlated fact carries the evidence that joined its sources. A
derived fact carries the calculation that produced it. An inferred fact carries
the observation and interpretation that produced it. The type travels with the
fact.

## Revision

A revision is the present coordinate of the fact world. A fence establishes a
causal boundary; a contingent wait can require evidence whose revision follows
that boundary. This lets the current carry both what is true and the evidence
that makes the present knowable.

## Observation now

The `worldline` command is a one-shot observation client. It collects only the
sections a query needs, returns compact JSON, and exits.

```bash
worldline                          # the whole current world
worldline os.kernel                # one fact
worldline windows.active           # the active window
worldline windows.active.geometry  # its frame, screen, monitor and exposure
worldline storage[0].percent       # bracket form
worldline storage.*.percent        # wildcard
worldline host os storage.0        # several facts in one object
worldline --list                   # every section
worldline --pretty windows         # indented JSON
worldline --all processes          # include full process list
```

`stdout` is JSON. Errors are JSON on `stderr`: exit `1` means the path does not
exist, exit `2` means the request itself is invalid.

Daemon entry points remain `worldline-daemon` and `worldlinectl` over a Unix
socket, joined to revisioned facts through the `observe` op.
