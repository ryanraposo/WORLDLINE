# Architecture

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
    ├── native links + correspondence evidence
    └── affordance evidence
    │
    ▼
Transactional executor
    │
    ▼
Actuation providers
```

## Consumers

WORLDLINE publishes source-observed facts, native links, correspondence
coordinates, provenance, revisions and expiry. The source may explicitly
report a native link (for example, the transient parent of a window); such
a link remains an observation with a source receipt.

**A matching process ID, application ID, title, coordinate or geometric
overlap never causes WORLDLINE to declare two objects members of one logical
entity.** Any such assertion, including self-identification and ownership
of multiple interfaces, belongs entirely to a downstream interpreter.

Consumer projections are defined and maintained by their consumers;
WORLDLINE does not ship named adapters or identity policies. Consumers can
correlate sources across a common revision and refresh evidence at the source
when correspondence is uncertain.

## State mutation

Every committed change increments the revision. Writers may supply `expected_revision`; a mismatch produces a conflict.

External event providers should invalidate affected facts as narrowly as practical. Broad recapture is a fallback, not the default.

## Protocol

The initial standalone transport is JSON Lines over a user-private Unix socket. The transport is intentionally replaceable. Requests carry a protocol version and can query supported features.

A future D-Bus/gRPC adapter can sit over the same service contract without changing the store.
