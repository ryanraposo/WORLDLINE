# Operating Fact

An **Operating Fact** is a typed statement about the machine at a particular revision.

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

The value is the useful present coordinate.

The type tells the system what kind of thing that coordinate is.

The evidence receipt tells an agent where the coordinate came from.

That combination makes a fact usable as machinery rather than merely as text.

## Examples

```text
gnome.session.type
  type: enum
  value: wayland
  evidence: environment

gnome.mutter.version
  type: version
  value: 51.x
  evidence: command / package metadata

gnome.atspi.bus.reachable
  type: boolean
  value: true
  evidence: D-Bus

computer_use.cua_driver.version
  type: version
  value: ...
  evidence: Cua runtime
```

A fact may be produced by an event, a state observation, a file, a journal, a service API, or a bounded probe. WORLDLINE records the source alongside the value.

## Evidence receipt

A receipt answers the question: **Where did we get this?**

For an agent, that is operational information.

A fact can therefore carry a source such as:

- AT-SPI event
- Mutter state
- D-Bus property
- PipeWire metadata
- journal entry
- state/config file
- environment
- Cua observation
- bounded command

The receipt can point an agent toward the system that can explain or refresh the fact.

## Revision

A revision is the present coordinate of WORLDLINE.

Fences create a causal boundary. A postcondition can require evidence whose revision follows that boundary.

That makes `fact == true` different from `fact == true because evidence arrived after this action`. The latter is an Operating Fact suitable for contingent continuation.

## Loss

Facts can become unavailable.

Loss is itself typed state: `available`, `stale`, `unavailable`, or `invalidated`.

The world model therefore represents what it currently knows, what evidence supports that knowledge, and where new knowledge can arrive.