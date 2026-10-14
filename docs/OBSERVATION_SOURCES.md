# Observation Sources

WORLDLINE observes the machine through the places where the machine already knows things.

The observation architecture is **event-driven first, source-local, and reconcilable**.

## Choose the truthful observation path

A source-aware observation plan distinguishes:

| Mechanism | Typical source | Characteristics |
| --- | --- | --- |
| Native event or subscription | D-Bus signals, AT-SPI, kernel/filesystem notifications | Prefer when the producer announces changes; reconcile missed events and source restarts. |
| Direct authoritative read | environment, `/proc`, `/sys`, known state/config files, exposed shared metadata | Read boundedly when the same fact is accessible without asking another service. |
| Existing read-only runtime interface | native properties, Cua observation, PipeWire and GNOME interfaces | Use the established producer's observation API when it alone owns the answer. |
| Bounded service query | `loginctl`, GSettings, D-Bus request/reply | Necessary when the service's internal state is not equivalently available elsewhere; request explicitly or on reconciliation, with deadlines. |
| Privileged native observer | OS-supported, approved restricted introspection | Only with explicit authority, evidence receipts and resource budgets; not a default process-memory scan. |

**Source access is not equivalent to response equivalence.** A PID found in
`/proc` cannot by itself answer whether a desktop window has focus. An
installed binary is not a healthy service. Information must be sufficiently
authoritative, current and complete for the exact fact being asserted.

The `sources` protocol operation and `worldlinectl sources` report only
**implemented acquisition paths**, their cost classes and previous read
timing. In the current GNOME provider, `fast` reads environment and PATH
metadata without a subprocess; `active` additionally uses bounded native
queries for session, accessibility reachability, program versions and
settings. Other providers advertise fast mode only when implemented.

```text
source discovery (no reads)
           |
           v
  choose needed evidence
           |
    native/cached valid?
     /            \\
   yes             no
    |               |
  consume    bounded existing-source read
    |               |
    +------ receipt / expiry ----+
                  |
            revisioned fact
                  |
           consumer interpretation
```

At idle, cached queries require no probes. Fresh sample requests read only
explicitly selected providers, never an all-systems scan. Slow observations
and wait predicates cannot monopolize the protocol event loop. Source reads
are serialized per provider to avoid overlapping reads; the fact update and
withdrawal are one atomic store operation.

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
