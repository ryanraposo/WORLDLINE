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


## CI checks without GitHub-hosted runner charges

This is a private repository. The `CI` workflow runs on a **self-hosted Linux x64 runner** so it does not consume metered GitHub-hosted runner minutes. GitHub currently makes self-hosted Actions usage free; review GitHub's current pricing before changing this policy.

Keep the `test` check meaningful: a queued check means no suitable runner is online, **not** that tests passed. Never substitute a skipped job or a success-only status for test execution.

To connect a runner, use this repository's **Settings → Actions → Runners → New self-hosted runner**. Use a dedicated, isolated, least-privilege environment rather than a personal desktop session. The workflow accepts pull requests only when their head originates in this repository and also checks pushes to `dev` and `main`. Forked pull requests are not executed on the private runner.

The same tests can be verified locally without GitHub Actions:

```bash
python3 -m pip install -e '.[dev]'
python3 -m pytest -q
```

**Merge gate:** require a successful, actually executed `test` job on the proposed commit. Do not treat a queued, skipped, or runner-provisioning failure as a green test result.
