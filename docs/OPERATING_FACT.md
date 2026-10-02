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

The value is the present coordinate.

The type tells the system what kind of coordinate it is.

The evidence receipt tells an agent where the coordinate came from.

That combination makes a fact useful as machinery.

## Evidence receipt

A receipt answers a simple question:

**Where did we get this?**

It can identify an event, subsystem, runtime interface, state file, journal entry, command, or other native source.

The receipt travels with the fact.

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

The type travels with the fact.

## Revision

A revision is the present coordinate of the fact world.

A fence establishes a causal boundary. A contingent wait can require evidence whose revision follows that boundary.

This lets the current carry both what is true and the evidence that makes the present knowable.
