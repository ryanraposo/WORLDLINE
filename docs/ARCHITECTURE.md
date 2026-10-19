# WORLDLINE: Operating Fact.

Architecture

## Core boundary

WORLDLINE is a truth/execution substrate. It does not own agent personality, conversational memory, model routing, or consumer-specific behavior policy.

```text
Sensors / providers
    │
    ▼
Observation normalization
    │
    ▼
Revisioned WorldStore ──────► subscriptions / snapshots / query
    │
    ├── capability readiness
    ├── relationships
    └── affordance evidence
    │
    ▼
Transactional executor
    │
    ▼
Actuation providers
```

## Consumers

### Hermes

Hermes remains responsible for conversation, memory, tools, approvals, intent and execution lifecycle. WORLDLINE supplies durable machine truth, capability readiness, receipts and conflicts.

### Horner

Horner remains responsible for identity, embodiment, performance and character. WORLDLINE supplies canonical desktop geometry/state and evidence from which Horner can derive walkable surfaces, grips, hazards, visibility, attention targets and other embodied affordances.

Neither consumer becomes WORLDLINE's privileged ontology.

## State mutation

Every committed change increments the revision. Writers may supply `expected_revision`; a mismatch produces a conflict.

External event providers should invalidate affected facts as narrowly as practical. Broad recapture is a fallback, not the default.

## Protocol

The initial standalone transport is JSON Lines over a user-private Unix socket. The transport is intentionally replaceable. Requests carry a protocol version and can query supported features.

A future D-Bus/gRPC adapter can sit over the same service contract without changing the store.
