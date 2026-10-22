<p align="center">
  <img src="assets/banner.png" alt="WORLDLINE" width="1200">
</p>

# WORLDLINE

**Operating fact.**

WORLDLINE answers four questions for an agent: **What is true now? How current is
it? Where did it come from? Where should I look next?** It reads the machine's
own sources and exposes a revisioned current. Missing evidence stays missing.

## Read the current

```bash
worldline                              # full snapshot, including revision and source status
worldline windows.active.geometry      # one value
worldline os.kernel memory.percent     # several values in one JSON object
worldline --explain windows.active.geometry  # value, revision, source and freshness
worldline --fresh windows.active.geometry    # refresh this source before reading
worldline --list                       # available sections
worldline --list windows               # discover paths under a section
```

The command starts the private observation daemon on first use. Later commands
read its current. A path query refreshes its source when the cached observation
is due; `--fresh` forces a new read. `stdout` is JSON. Errors are JSON on
`stderr`: exit `1` means the path is missing, `2` means the request is invalid,
and `3` means WORLDLINE could not start or reach its daemon.

The full snapshot retains the familiar sections (`host`, `os`, `desktop`,
`windows`, `processes`, and others). It adds a `revision` and a `sources` map
with observation time, expiry, availability, and reason when a source is down.
Ordinary path queries still return just the selected value; use `--explain` when
the decision depends on provenance or freshness.

## Locate a window

```bash
worldline windows.active.geometry
worldline windows.items
worldline windows.by_id
worldline --explain 'windows.by_id.window:42:7.geometry.frame'
```

`windows.items` is ordered for inspection. `windows.by_id` indexes windows
whose AT-SPI process and accessible object path provide a `stable_id`, so a
later step need not rely on a list position. Read fresh extents after a window
moves. AT-SPI supplies titles, states and component extents; Mutter supplies
monitor layout. These extents may differ from compositor frames, and WORLDLINE
does not know stacking or pixel occlusion. Geometry reports those limits rather
than claiming a window is topmost. Do not construct an ID from an app name.

## Use facts during an agent turn

Start with the small, source-labelled context your runtime supplies. Query a
specific path when the task needs more. After an action that can change the
desktop, refresh the affected fact and inspect the outcome before reporting
success. An old fact does not prove that the action caused a new state.

Horner, for example, gets a bounded prompt package with his observed companion
window frame and his local body state. The window metadata locates his visible
presentation on the desktop; his physics runtime supplies foot position,
contacts, and motion. During a longer plan he can use his terminal tool to run
`worldline --fresh windows.active.geometry` or inspect a particular observed
window. Horner identifies his own window and decides physical actions in his
own runtime; WORLDLINE publishes generic desktop observations.

## What an Operating Fact carries

An Operating Fact has a value, source, observation time, validity, and revision.
The source can be GNOME/Mutter, AT-SPI, D-Bus, `/proc`, a state file, or another
machine interface. A fact can be direct, correlated, derived, or inferred. The
receipt lets an agent check its basis and decide whether to refresh it.

The daemon gathers a baseline on startup, follows GNOME signals when present,
and reconciles sources with bounded reads. A source outage is reported as
unavailable; a previous value is not presented as current. `worldline-daemon`
and `worldlinectl` expose the revisioned store, fences, and waits over a private
Unix socket. The no-argument socket `query` keeps its existing fact-snapshot
response; selective `query` accepts `paths` and returns values plus receipts.
For example, `worldlinectl query --path windows.active.geometry --fresh`
requests one fresh fact with its evidence.

## Install

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
pytest
worldline
```

The target desktop is GNOME on Wayland. Other sections continue to report what
their available host sources can actually observe.
If the virtualenv's PyGObject binding is incomplete, the CLI starts the
observation daemon with a working system Python and loads this checkout there.
If no AT-SPI binding is available, window facts report the source failure.

For the model, evidence rules, and platform details, see
[`Operating Fact`](docs/OPERATING_FACT.md),
[`Architecture`](docs/ARCHITECTURE.md),
[`Observation Sources`](docs/OBSERVATION_SOURCES.md), and
[`GNOME/Wayland`](docs/GNOME_WAYLAND.md). The brand assets are in
[`assets/brand/`](assets/brand/README.md).
