# WORLDLINE: Operating Fact.

Observation Sources

WORLDLINE observes the machine through the places where the machine already knows things.

The observation architecture is **event-driven first, source-local, and reconcilable**.

## Native events

Examples include:

- AT-SPI accessibility events
- GNOME Shell / Mutter signals
- D-Bus property changes
- PipeWire stream and metadata events
- system service notifications

A native event can advance an Operating Fact directly and carry its evidence receipt.

## State surfaces

Many facts have a durable or queryable home:

- `/proc` and `/sys`
- XDG runtime state
- application state files
- GNOME settings
- service state
- journal entries
- ordinary log files

WORLDLINE observes these surfaces at their source. File notifications, journal cursors, service subscriptions, and bounded reads provide reconciliation while the producer keeps owning its state.

## Runtime interfaces

Some facts are naturally exposed through active runtimes:

- D-Bus
- AT-SPI
- PipeWire
- Cua
- GNOME Shell extension APIs

These interfaces expose the machine's current representation.

## Privileged observation

WORLDLINE can have privileged observers where a platform exposes useful state only inside a process.

The design question is:

> Can the state be read where it naturally exists, with a receipt that identifies the source?

For ordinary desktop state, source-owned interfaces, state files, journals, shared metadata, and runtime APIs provide rich evidence.

Where process memory is genuinely the native source of an otherwise unavailable fact, a privileged provider can observe it and record the source, address or range, process identity, sampling time, and interpretation as evidence metadata.

The fact remains in its native system. WORLDLINE observes it.

## The daemon

`worldlined` is the persistent observation engine.

```text
native event
    ↓
source-local observation
    ↓
typed Operating Fact
    ↓
evidence receipt
    ↓
revision
    ↓
query / wait / continuation
```

A reconciliation cycle supplies the same path when an event is unavailable or a source needs periodic confirmation.

## Privilege

Privilege belongs to the observer boundary.

A configured observer may use the privileges required to observe its source. The resulting WORLDLINE contains the facts that its observers can actually see.
