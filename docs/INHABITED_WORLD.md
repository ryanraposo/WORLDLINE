# The Inhabited World: Observation Atlas

**An agent's world is the observable machine, physical surroundings and
changing activity in which it operates.** It is not a cast of entities that
WORLDLINE names or a list of behaviours WORLDLINE should choose.

WORLDLINE keeps direct source facts, source-reported native relationships,
coordinates that permit correspondence, and evidence receipts. The consuming
intelligence recognizes its own manifestations, interprets relationships,
forms goals, chooses tools, and decides when an observation is relevant.

This atlas is an **observation coverage map**, not a claim that every interface
listed below is already implemented. The live `worldlinectl sources` command
reports only installed, implemented sources. In the tables:
**implemented** means implemented in WORLDLINE;
**available source** means an existing OS/runtime surface can potentially
provide evidence once its actual contract is verified;
**requires consent** means observation must be permission-scoped and
explicitly requested. A source's presence is not proof that the facts are
accessible in the current session.

## What constitutes the environment?

| Domain | Observable facts worth preserving | Native source and status |
| --- | --- | --- |
| **Time and lifecycle** | Clock readings with monotonic/wall-clock distinction, session uptime, suspend/resume, boot generation, idle duration where authorized | `/proc/uptime` **implemented** for uptime; logind for lifecycle **available source** |
| **Processes and services** | PID, executable, service unit, lifecycle, failures, dependencies and native parent PID; service readiness only from the responsible service | `/proc`, systemd D-Bus, journal **available source**; PATH program presence **implemented** |
| **Windows and workspaces** | Mutter ID and generation, app ID, frame, focus, workspace, monitor, stacking, transient-parent, minimization and compositor visibility | Existing GNOME/Cua observation interface **requires contract verification**; no additional Shell extension |
| **Shell and spatial stage** | Stage extents, transformed actor bounds, monitor scale/rotation, screenshot coordinates, occluded visible regions, pointer hit-test surface | Existing compositor integration and Cua **requires contract verification**; raw connector cable state is *not* stage geometry |
| **Accessible interaction** | Accessible element roles, names, bounds, action availability, focus, state changes, hierarchy and navigation | AT-SPI2 **available source**; session bus reachability **implemented**, not semantic access |
| **Manifestation and physical embodiment** | Rendered-surface availability, source-reported body pose/position, contact with surfaces, presentation completion, movement events and interaction hit regions | Native UI rendering/compositor and the owning physical runtime **available source / consumer-defined projection**; WORLDLINE does **not** define which surfaces constitute one body |
| **Interaction history and causality** | Observed input event, action acknowledgement, permission gate, native state transition, outcome evidence, sequence/correlation IDs | Existing control runtime receipts, source logs and WORLDLINE revision fences **available source / partial implementation**; avoid copying private full action transcripts |
| **Input and attention** | Focus owner, keyboard layout, pointing-device presence, pointer position when available, lock/idle/inhibitors, ongoing user activity | GNOME/Cua, logind, input services **available source**; minimize user activity detail |
| **Media and audio** | Output/input endpoint inventory, stream existence, application routing, playback/capture state, mute/volume and generation | PipeWire/WirePlumber metadata **available source**; detailed media payload requires separate authority |
| **Camera and sensing** | Device present, permissions, active authorized capture, stream format and frame time; image content only with authorization | V4L2, PipeWire, portals **available source / requires consent** |
| **Displays** | DRM connector cable state, modes and GPU-adapter origin; compositor logical monitor mapping is separate | DRM sysfs connector status **implemented**; Mutter/Cua logical layout **requires contract verification** |
| **Power and thermal** | Battery capacity/status, AC presence, power-profile setting, temperature and thermal pressure, charging/suspend constraints | `/sys/class/power_supply` **implemented**; power-profiles-daemon, hwmon **available source** |
| **Compute and contention** | CPU load, memory availability, swap, GPU/VRAM consumption, accelerator capabilities, process contention | `/proc` **implemented** for load/memory; GPU management API **available source / vendor-dependent** |
| **Storage and files** | Mount/device readiness, quota/space, path existence, file metadata, inotify changes, open document location when explicitly exposed | `/proc/mounts`, statvfs, inotify, application APIs **available source**; do not crawl content by default |
| **Network and connectivity** | Link carrier, interface changes, assigned routes, DNS configuration, reachability and latency to *specific tested targets* | NetworkManager D-Bus, `/sys/class/net`, rtnetlink **available source**; interface up ≠ internet connected |
| **Hardware and peripherals** | Bluetooth/USB/HID input capabilities, printers, external devices, permissions, device generation | udev, BlueZ, CUPS, device sysfs **available source** |
| **Applications and documents** | Which application is open, current document identifiers/URIs when application reports them, unsaved state when exposed | Native application/portal APIs **available source**, not inferred from titles alone |
| **Browser and web surface** | Window/tab IDs, URL/title where authorized, DOM/accessibility, visible state, network load and navigation completion | Existing browser/CDP accessibility and Cua integration **available source / permission-scoped** |
| **Communication surfaces** | Notifications, unread counts, ongoing calls, messages addressed to the user/agent through authorized channels | Notification service and linked-app APIs **available source / requires consent**; no mailbox surveillance |
| **Remote and distributed context** | Connection health, remote machine/provider identity, remote revisions, remote job/agent progress | Authorized APIs and remote agents **available source**, with distinct clock and identity scopes |
| **Location and physical environment** | Explicitly shared device geolocation, motion sensors, room/camera semantics, ambient sound, physical obstacles | Portals and hardware with consent **requires consent**; no inferred whereabouts or room observations |
| **Policies and permissions** | Session lock, access granted/denied, portal capabilities, active input/capture lease, approval status | logind, portal and runtime state **available source**; permissions are not replaced by world observations |
| **Tools and capabilities** | Actual installed capabilities, health, permission, runtime-version, supported action schema | Source/service capability APIs **available source**; PATH presence **implemented** as presence only |
| **Outcomes and events** | Acknowledgement, observed change, result, timeout, partial completion, fresh evidence after fence | WORLDLINE revision/fence/wait **implemented**; concrete effect remains sourced to the executor/observer |

## What it means for an agent to inhabit this world

An agent may recognize its own presentation window, interactive overlay,
body renderer, web manifestation or phone surface from **its own repository's
identity and metadata**. WORLDLINE sees the ordinary source observations
those surfaces provide. It does not tell an agent which objects are *it*,
which belong together, or what their relationships mean.

The environment around that agent includes other windows, spatial support,
focus and user attention, device readiness, applications, sounds and media,
foreground changes, running jobs, input permissions, service health, time,
hardware pressure, connectivity and authorized information surfaces.

The agent can compare its own source-reported pose/visibility against OS
window geometry and input observations; the interpretation of "I am behind
that window", "I can stand there", "you are talking to me", or "my action
worked" happens in the consuming intelligence or its owned physical
machinery, **not** in WORLDLINE. The underlying facts remain separable and
independently inspectable.

There are three distinct worlds in practice:

1. **Native physical/operational truth:** measurable processes, devices,
   window/actor coordinates, actual movement, service and permission state.
2. **Perceived content:** images, text, speech, semantic accessibility and
   documents, only as actually exposed by a source and with appropriate
   permissions.
3. **Consumer interpretation and intention:** object meaning, self, identity,
   goals, memories, inferred affordances and relationships. Consumers own it.

This separation permits sophisticated reasoning without turning the
observation engine into a domain-specific ontology.

## Source selection: the least costly *authoritative* evidence

A machine is full of services that normally answer a request. A lot of useful
information is already available in other, simpler places **before calling
those services**. WORLDLINE should be aware of that opportunity:

- Read `/proc/meminfo` for current host memory rather than launching a
  process monitor. Read `/sys/class/power_supply` for source-supplied battery
  attributes rather than launching a desktop battery widget.
- Read the PATH or existing version metadata for program presence; ask the
  actual service for readiness, a negotiated feature list or operation results.
- Use D-Bus properties or subscribed signals when the service exposes the
  state there. Never pretend a /proc PID is proof of the service's health.
- Use compositor/Cua's existing read-only observation when only compositor
  state can establish focus, stacking or native window geometry; do not
  recover equivalent-looking data from window titles, screen images or PIDs.
- A file watcher can tell us a file changed, but only the owner of an editor
  buffer can say whether the user's document has unsaved changes.
- A microphone device can be enumerated without listening to the user. An
  active audio capture or frame requires its own permission and purpose.
- An installed GPU can be observed without allocating VRAM or spinning up
  another inference process; live utilization needs an authoritative driver
  or service counter.

WORLDLINE can expose a **source descriptor** for each implemented provider:
origin, authority, acquisition method, cost class, output fact keys,
last attempt/success/duration and supported fast/active modes. This helps
an agent decide **whether** and **where** to inspect, but never makes the
decision to act for it.

## Efficiency and fidelity contract

1. **No mandatory scan every model turn.** Cached valid facts serve cheap
   queries. Request fresh observations by relevant provider and mode.
2. **Events first, reconciliation second.** Use existing change signals,
   subscriptions and journal/file cursors when possible. Recover from a missed
   event, restart or generation change with a bounded read.
3. **Budgets by source.** Rate-limit, deduplicate and batch expensive reads;
   keep source sampling off the daemon request loop. Never increase request
   load to another service just because facts *might* be interesting.
4. **One coherent receipt per source sample.** Preserve source identity,
   generation, native identifiers, coordinate system, observed timestamp,
   knowledge status and expiry. Source-reported links stay native links.
5. **Distinguish missing from false.** Inaccessible source, stale evidence,
   absent permission and explicit source-reported negative result are distinct.
   A service timeout is not proof of an empty desktop or no active streams.
6. **Privacy by minimization.** Prefer existence/state/capability over file
   contents, UI text, communication bodies, camera frames, audio, location or
   personal identifiers. Sensitive observations require user authority.
7. **Preserve the control boundary.** Observation is read-only. GWCU, device
   services and consumer runtimes own their respective mutations. WORLDLINE
   observes outcomes, not substitute acts.
8. **A native relationship is a fact, not identity.** A transient parent, PID
   parent or app ID is evidence; whether several surfaces are *one entity* is
   the consumer's interpretation.
9. **Memory and identity do not live here.** Conversations, preferences,
   commitments, goals and logical self are maintained by the agent/runtime,
   not inferred or stored as WORLDLINE ontology.
10. **No fictitious completeness.** Every domain may report partial source
    coverage. Never silently replace unavailable privileged observations
    with an inference and label it a direct fact.

## Normalized intermediate representations

Each provider maps source observations into Operating Facts with source
receipts, not into a bespoke world graph. When relevant, preserve:

```text
source identity / generation
native object reference
sample timestamp / expiry
coordinate frame / transform / units
observed value / explicit source relation
source uncertainty / unavailable reason
source revision / WORLDLINE revision
```

These representations make independent consumers capable of comparing
observations and inferring correspondence without making those inferences
WORLDLINE's own truth.

For cross-source events, keep the observations separately attributable.
A correlation may be calculated by a consumer, but it should not erase
the original time, source and identifier context.

## Representative acceptance

- A low-cost host query returns bounded memory, load, uptime, battery and DRM
  connector facts without spinning up a service or exposing device serials.
- A native desktop source, **if verified**, reports ordinary windows and
  native parents; an unrelated consumer can identify its own window based on
  app ID, refs or metadata in its own code, without WORLDLINE being taught
  what that identity means.
- A compositor restart invalidates old generation-scoped window refs; an
  unavailable source reports unknown, not a fabricated empty window list.
- A browser launch, body movement or media playback uses normal approved
  machinery; WORLDLINE can compare fresh before/after source receipts without
  controlling the action.
- A service with accessible read-only state yields truthful service state;
  a PID without an authoritative health response does **not**.
- Model context uses a small projected set of facts and can inspect additional
  sources when needed. It does not receive a bulk dump of every process, UI
  element, microphone, message or document.

**Implementation status:** `gnome` (session/PATH; active bounded service
queries), `host` (bounded kernel power/resource/connector facts), generic
source inventory, fresh provider queries, store reconciliation and
revision/fence/wait exist on the current feature branch. Most domains above
are **coverage targets**, not implemented probes. The maintained native
desktop observation contract must be validated on the target machine before
claiming those window and actor facts.
