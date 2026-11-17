# Desktop observation service

WORLDLINE exposes a compositor-aware, read-only desktop observation API over its existing user-private Unix socket. The API normalizes GNOME Shell compositor frames and AT-SPI semantics into a session-scoped window model. It does not activate windows or inject input.

## Protocol operation

All requests use protocol 1 and the existing newline-delimited JSON socket.

### Coherent snapshot

```json
{"protocol":1,"op":"desktop","args":{"action":"snapshot"}}
```

The response uses `worldline.desktop-observation/1` and includes:

- `session_id`, monotonically increasing `revision`, event sequence and observation timestamp.
- A display frame and monitor layout in desktop logical pixels (origin top-left, positive Y downward).
- Window records with session-scoped `window_id`, process/accessibility/compositor relationships, state, frame geometry, and per-record provenance.
- Explicit capabilities and limitations. Pixel visibility, activation and input are not capabilities of this service.

A `window_id` identifies one observed lifetime within one WORLDLINE daemon session. It is intentionally not a persistent application identifier. Discard all IDs when `session_id` changes.

### Resolve a window

```json
{"protocol":1,"op":"desktop","args":{"action":"resolve","window_id":"window:<session>:<uuid>"}}
```

Resolution refreshes the observation before returning. A missing identity returns `stale_window_identity`; consumers must enumerate again rather than reusing a stale compositor handle.

### Read changes

```json
{"protocol":1,"op":"desktop","args":{"action":"events","after_sequence":0,"limit":128,"timeout_ms":25000}}
```

Events are ordered by a monotonically increasing sequence and include their observation revision. Event history is bounded (512 entries). When `resync_required` is true, the consumer missed retained events and must request a new snapshot. The optional `timeout_ms` performs a bounded long poll (0–30000 ms), refreshing the native observation while waiting. Consumers resume from the last received sequence.

### Query capabilities

```json
{"protocol":1,"op":"desktop","args":{"action":"capabilities"}}
```

Capabilities distinguish unavailable sources from unsupported claims. In particular, compositor frame geometry is not pixel visibility; stacking is not proof of rendered visibility; WORLDLINE never offers activation or input.

## Identity and provenance

Verified compositor window identity plus Linux process start time is the preferred lifetime key; AT-SPI accessible paths plus process start time provide the fallback for semantic-only windows. Public IDs are opaque UUIDs scoped to the current WORLDLINE daemon session. A window that disappears from an available observation and later reappears receives a new ID, even if its PID and compositor identifier are reused.

A failed/unavailable observation does not generate destruction events. Absence is meaningful only in a successful enumeration. Each record identifies the source used for identity and geometry and marks whether compositor geometry is verified. Unsupported or unknown state fields are `null`, not false.

## Source boundaries

- **Mutter DisplayConfig:** logical monitor positions, dimensions, scale and transform.
- **WORLDLINE GNOME Shell extension:** read-only compositor window frames, stacking and compositor state, after existing host attestation.
- **AT-SPI2:** application/window semantics, accessible identity and component extents. Extents do not independently prove compositor frames.
- **WORLDLINE:** normalized snapshots, session identities, revisions, event journal, source metadata and capability reporting.

The service does not infer alpha visibility, shaped-surface visibility, safe activation targets, or application intent. Consumers retain their own policy and action authority.
