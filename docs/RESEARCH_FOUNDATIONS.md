# Research foundations

WORLDLINE starts from a concrete research result: reliable computer agency needs a **persistent, revisioned world model**, not a fresh screenshot interpretation before every action.

## 1. Multi-tier state

The original research separated evidence by cost and semantic value:

- **L0 — runtime/static:** processes, applications, configuration, files, capabilities.
- **L1 — semantic:** accessibility tree, focus, roles, names, state, logical relationships.
- **L2 — visual change:** frame deltas, regions of change, visibility confirmation.
- **L3 — pixels:** full screenshots/vision when lower tiers cannot answer the question.

Reasoning should usually consume L0–L2 and escalate to L3 only when useful.

## 2. Optimistic execution

A plan is evaluated against a world revision. WORLDLINE assumes state remains valid while the action is attempted, then verifies the result. External change creates a conflict rather than silently corrupting the plan.

Canonical loop:

```text
locate → precondition → act → await → assert
```

Unexpected state is a reason to reconcile/replan, not to keep clicking.

## 3. Evidence, not vibes

Every meaningful state claim should be attributable to evidence:

- source
- observation time
- confidence
- revision
- expiry/invalidation rule
- optional supporting detail

This supports the epistemic distinction developed in later WORLDLINE/GWCU work:

- **KNOWN** — established by current evidence.
- **KNOWABLE** — can be established through an available observation/probe.
- **UNKNOWN** — unsupported at present.

## 4. Confidence decays

State that was true can become stale. Long transactions therefore need either event-backed invalidation or explicit re-validation checkpoints. Readiness and capability proof must expire when their supporting evidence becomes old or their source fingerprint changes.

## 5. Readiness is a ladder

A process existing is weak evidence. WORLDLINE adopts the stronger readiness ladder developed during Horner recovery work:

```text
installed → alive → connected → functional → integrated
```

A capability is ready only when its evidence reaches the level actually required by the consumer.

**False green is a bug.**

## 6. Semantic truth and physical truth can coexist

Accessibility semantics and geometry are complementary. A window can simultaneously be:

- an OS entity with identity, process ownership and focus;
- an accessibility tree;
- a visual rectangle with changing pixels;
- a physical surface in Horner's desktop world;
- a host of browser or application-specific affordances.

WORLDLINE stores canonical observations and relationships. Consumers derive their own higher-level meaning.

## 7. Actuation is downstream of truth

The original Linux design used AT-SPI, compositor/portal events, PipeWire capture and persistent RemoteDesktop/libei actuation. The architecture deliberately separates **knowing what is true** from **how an action is emitted**.

That separation remains foundational. WORLDLINE can consume observations from CUA/Hermes/GNOME/native adapters without becoming any one of them.

## 8. Agent calls are exception machinery, not the clock

The executor should remain deterministic while the world matches the plan. LLM calls are most valuable for goal interpretation, ambiguous semantic choice, and conflict/recovery—not for repeatedly rediscovering obvious machine state.

## 9. New needs are expected

WORLDLINE must not encode today's consumer vocabulary as universal ontology. Extension points are therefore first-class:

- observation providers
- capability providers
- entity/fact namespaces
- relationship types
- affordance namespaces
- transaction predicates/actions
- consumer projections
- protocol feature discovery

A new need should normally add a provider, projection or namespaced fact—not require a core rewrite.
