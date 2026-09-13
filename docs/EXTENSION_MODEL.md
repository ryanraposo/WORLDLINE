# Extension model

WORLDLINE assumes new needs will arrive.

## Rule

**Extend at the narrowest truthful layer.**

A new integration should answer: is this new reality, a new way to observe reality, a new action, or merely a new consumer interpretation?

## Extension types

### Observation provider

Adds facts from a source such as AT-SPI, GNOME Shell, PipeWire, filesystem events, browser CDP, hardware sensors, or a remote machine.

Providers normalize source-specific data into namespaced facts with evidence.

### Capability provider

Describes whether a capability exists and, optionally, how to acquire/repair it idempotently. Readiness is represented using the shared ladder rather than custom booleans.

### Consumer adapter

Projects canonical truth into the vocabulary needed by an agent. Hermes and Horner are initial adapters, not special cases in the store.

### Affordance namespace

Consumers may publish or derive namespaced affordances:

```text
web.can_click
system.can_focus
horner.can_stand
horner.can_grip
robot.can_reach
```

The core does not need to understand every verb.

### Protocol feature

New RPC capabilities must be discoverable through `hello/features` and versioned. Existing operations retain semantics within their protocol version.

## Admission test for a new core concept

Promote a concept into WORLDLINE core only when it is:

1. consumer-independent;
2. evidence-backed;
3. useful across more than one provider or consumer;
4. stable enough to version;
5. not expressible cleanly as a namespaced extension.

This keeps the center small while letting the edges grow aggressively.
