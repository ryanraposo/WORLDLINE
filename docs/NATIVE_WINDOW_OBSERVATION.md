# Native Window Observation

The general GNOME Shell observation adapter reads **ordinary native facts**
for every managed window and associated Mutter window actor. It knows nothing
about an application's logical identity, its self-concept, or why two windows
may belong together. Consumers may make those interpretations themselves.

## Observation source

On Wayland, arbitrary external processes cannot enumerate all Mutter windows.
The optional GNOME Shell observer runs where the native objects exist.
Its only D-Bus operation is `GetSnapshot() → JSON string`; it exposes **no**
focus, input, activation, movement or other mutating methods.

Install the files from `integration/gnome-shell/` in a GNOME Shell extension
directory named `window-observer@worldline.local` and enable it with
`gnome-extensions enable window-observer@worldline.local` after the shell
discovers the installation. Use a nested/development session for initial
validation. No runtime installation is implied by cloning this repository.

The adapter is optional. No attempt is made to relax the access restrictions
of GNOME Shell's built-in Introspect service.

## Inspecting the present

```sh
worldlinectl query                  # cached, validity-filtered facts
# Explicit fresh read of native window records:
gdbus call --session --dest org.worldline.GnomeObserver \
  --object-path /org/worldline/GnomeObserver \
  --method org.worldline.GnomeObserver1.GetSnapshot
```

WORLDLINE protocol consumers should submit
`{"protocol":1,"op":"query","args":{"refresh":["gnome-windows"]}}`
to the private Unix socket for a fresh source read followed by the current
snapshot. `worldlinectl observe` still refreshes the ordinary GNOME host
provider; `worldlinectl` does not yet expose `refresh` flags.

Facts:

- `gnome.windows.source.available`: whether the optional observation
  surface answered and its data passed validation.
- `gnome.windows.snapshot`: one coherent observation generation with native
  window references, app-id / WM-class claims, process ID reported by Mutter,
  window frames, monitor/workspace, focus, minimization, native transient-for
  reference, and actual Meta.Window actor presence. `stack_index` is set only
  when Mutter supplies a native window sort; an actor-enumeration index is **not**
  claimed to be a stacking relationship.

Every fact includes an evidence source, sampling time and short expiry.
A failed fresh sample invalidates the previous snapshot. A process restart
changes the source generation: window IDs must be treated as **scoped to that
generation**, never globally durable.

The service can expose window titles (potentially sensitive). Both WORLDLINE's
Unix socket and GNOME's session bus are session-local, but downstream consumers
should project only needed fields into model context or logs.

## Boundary

The observer preserves only **native source relationships** (for example,
`Meta.Window.get_transient_for()`), plus identifiers and correspondence
metadata. It never groups two windows into a logical application entity,
constructs a special identity, or infers a relationship from matching titles,
process IDs or coordinates.

The normal WORLDLINE `gnome` provider remains responsible for host/session
facts. This optional `gnome-windows` provider adds compositor-local
observations only when requested.
