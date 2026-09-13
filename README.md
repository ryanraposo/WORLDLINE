# WORLDLINE

**Persistent world-model and execution substrate for agents operating a real computer.**

WORLDLINE keeps evidence-backed state about a changing machine, lets consumers act against explicit preconditions, verifies resulting state, and invalidates assumptions when reality moves.

It is deliberately **agent-agnostic**. Hermes can use WORLDLINE for reliable computer agency. Horner can use the same world truth for embodiment, navigation, contact, and environmental awareness. Future consumers should be able to add new observations and interpretations without changing the core ontology.

## Core idea

```text
world → observations → entities → relationships → affordances
                                      │
                            capabilities + constraints
                                      │
                                  agent intent
                                      │
                                     action
                                      │
                         observed world-state delta
```

WORLDLINE describes **reality and possibility**. Consumers decide what that reality means to them.

## Foundational contracts

- Persistent, revisioned world state rather than repeated screenshot reinterpretation.
- Multi-tier evidence: L0 runtime/static facts, L1 semantic/accessibility state, L2 visual change signals, L3 pixels only when useful.
- Evidence carries provenance, timestamp, confidence, and validity.
- Known-good state may be assumed until invalidated; verification is demand-driven.
- Actions follow `locate → precondition → act → await → assert`.
- Transactions use optimistic concurrency and conflict on stale revisions.
- Capability readiness is evidence-backed: `installed → alive → connected → functional → integrated`.
- **False green is a bug.** Readiness proof expires or is invalidated by relevant changes.
- Consumer semantics stay outside the core. `can_click` and `can_attach` can coexist with Horner-specific `can_stand` or `can_climb` without polluting base truth.
- New needs enter through extension points, not core rewrites.

## Repository shape

```text
src/worldline/
  model.py          typed world facts and evidence
  store.py          optimistic revisioned state store
  capabilities.py   evidence-backed readiness ladder
  transactions.py   pre/postcondition transaction primitives
  protocol.py       versioned RPC envelope + legacy compatibility
  daemon.py         Unix-socket JSONL daemon
  providers/        observation/capability providers
  consumers/        consumer adapters (Hermes, Horner, future agents)

docs/
  RESEARCH_FOUNDATIONS.md
  ARCHITECTURE.md
  EXTENSION_MODEL.md
  COMPATIBILITY.md
schemas/
  worldline.snapshot.schema.json
```

## Quick start

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
pytest
worldline --socket /tmp/worldline.sock
```

Then, from another shell:

```bash
worldlinectl --socket /tmp/worldline.sock status
worldlinectl --socket /tmp/worldline.sock query
```

## Compatibility direction

The standalone daemon preserves the later embedded WORLDLINE Unix-socket vocabulary (`status`, `event`, `capture`, `arm`, `wait`, `close`) as compatibility operations. The protocol itself is versioned and feature-discoverable so the public surface can grow without repeating the original hard-coded six-op limitation.

See `docs/COMPATIBILITY.md`.
