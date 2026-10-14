# Desktop observation without a second GNOME Shell extension

## Purpose

WORLDLINE preserves ordinary desktop observations and explicit native
relationships without inferring logical application identities, affiliations,
or consumer-specific semantics.

**The observation producer should already exist.** On GNOME / Wayland,
the preferred source is the maintained Cua / GNOME / AT-SPI machinery and
its public, read-only observation surface. The exact installed Cua interfaces
must be discovered and verified before an adapter is written. Do not assume
a stable `cua-driver` snapshot JSON API from its status command, or treat
a debugging transport as a production control path.

Avoid adding an additional Shell extension, a compositor patch, a duplicate
window enumerator, a second input driver, or a browser-control backchannel.
Observe OS-native parent/transient/process links when the source exposes them,
and keep OS identifiers scoped to the source and compositor generation.

## General provider path

- WORLDLINE owns the stable fact representation, revisions, evidence, expiry,
  fence/wait, and optional on-demand refresh of a registered provider.
- Existing providers own source-specific reads and clearly report when
  observation is unsupported or unavailable.
- `query` accepts `{"refresh":["<registered-provider>"]}` to read requested
  providers before returning the revisioned current. Registration is generic;
  there is **no special named-application consumer**.
- A source may declare `managed_keys`. A fresh read withdraws previously
  held keys that its source no longer reports.
- Freshness, confidence, native IDs, coordinate spaces, and original
  source timestamps must accompany collected facts. Matching IDs or frames
  alone are not assertions of shared logical identity.
- A failed observation must not be represented as a successful empty desktop.
  Existing facts should become unavailable or expire.

## Acceptance before a real desktop adapter

1. Discover and document the existing supported observation method on
   GNOME 50 and its installed driver version. No imagined CLI schemas.
2. Collect a desktop snapshot through that existing read-only route.
3. Project each OS-reported field with evidence and source/generation IDs,
   preserving only native parent/child/transient links.
4. Verify a source failure or compositor restart invalidates previous facts.
5. Verify `fence → existing computer-use mutation → refreshed fact → wait`
   without putting any input or interpretation inside WORLDLINE.

A generic provider is justified only when it can satisfy this acceptance
with real source evidence. Until then WORLDLINE retains its honest host
facts and the generic refresh/expiry plumbing, not a fabricated window source.
