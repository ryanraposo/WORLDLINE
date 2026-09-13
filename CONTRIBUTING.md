# Contributing

WORLDLINE is intentionally extensible, but core vocabulary is expensive.

Before adding a core concept, ask whether the need belongs in a provider, consumer projection, namespaced fact, capability, affordance, or protocol feature.

Every behavior change should preserve:

- evidence/provenance;
- revision safety;
- explicit invalidation;
- consumer independence;
- compatibility semantics;
- observable verification.

New providers should include deterministic tests with mocked source events. New capabilities should prove failure as well as success; a stale success must not remain green.
