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

## CI verification

WORLDLINE runs ordinary pytest via GitHub Actions on `ubuntu-24.04`, Python 3.12. This matches the successful CI run on October 2, 2026 (run 37013757626). No self-hosted runner is needed.

For private repositories, standard GitHub-hosted runners draw from the account's included Actions minutes; exceeding the included allowance can require payment. This repository cannot change account-level quotas. Workflow triggers cover pull requests to `dev` and `main` and pushes to integration branches, with cancellation of superseded runs to avoid consuming unnecessary minutes.

Run the same tests locally without any GitHub compute:

```bash
python3 -m pip install -e '.[dev]'
python3 -m pytest -q
```

**Merge gate:** require the actual `test` job to execute and pass on the proposed revision. A job that fails before any runner is assigned or remains queued is **not** a test failure and is **not** a passing check. Investigate GitHub Actions billing/runner availability rather than altering assertions or inventing green checks.
