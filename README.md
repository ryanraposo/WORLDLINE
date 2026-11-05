<p align="center">
  <img src="assets/banner.png" alt="WORLDLINE logo and wordmark" width="1200">
</p>

# WORLDLINE

**A live, revisioned view of what the machine knows now.**

WORLDLINE observes the host and desktop, records when each fact was observed,
and makes the current state available to people and tools as JSON. Reads can be
refreshed before a decision; revisions let independent consumers compare new
evidence with a known boundary.

WORLDLINE observes only. It does not inject input, activate windows, or decide
whether an action is safe.

## Get started

WORLDLINE targets Ubuntu with GNOME on Wayland.

```bash
sudo apt install git python3 python3-venv python3-pyatspi libglib2.0-bin
git clone https://github.com/ryanraposo/WORLDLINE.git
cd WORLDLINE
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev]'
worldline --fresh --explain windows.active.geometry
```

The command starts a private observation daemon when one is not already
running. WORLDLINE uses the system Python when needed to access the desktop's
AT-SPI bindings. Run `pytest` to check the installation.

For a daemon that stays available throughout the graphical session, install the
user service:

```bash
./scripts/install_user_service.sh
systemctl --user status worldline.service
```

The service runs this checkout. Repository hooks restart it after local Git
pull, merge, or checkout operations; they do not fetch updates automatically.

## Read the current state

```bash
worldline                                      # full snapshot and source status
worldline os.kernel memory.percent             # selected values
worldline windows.active.geometry              # active window geometry
worldline --fresh windows.active.geometry      # refresh before reading
worldline --explain windows.active.geometry    # value, source, revision and age
worldline --list                               # available sections
worldline --list windows                       # paths in a section
worldlinectl sources                           # provider and source catalogue
```

Output is JSON. A path query returns its value. `--explain` adds the fact's
revision and evidence, including its source and freshness. `--fresh` samples the
requested source before returning. Window records have stable IDs that can be
queried later through `windows.by_id`.

## Explore desktop geometry

```bash
worldline geometry                 # terminal map and source-labelled details
worldline geometry --json          # spatial-frame JSON
worldline geometry --live          # refresh the map; press q to quit
worldline geometry --live --interval 1.0  # live refresh interval, in seconds
```

The terminal map places monitors and window frames in logical desktop
coordinates. Verified windows are shaded by observed compositor stacking
order. Unverified frames are transparent outlines; `?` marks their edges and
`╳` marks intersecting edges. Intersections do not imply which window is in
front. The details below the map list each monitor and window's coordinates,
dimensions, source, and whether its stacking order is verified. Window names
are kept outside the drawing so overlapping frames cannot obscure or corrupt
their labels.

`--live` requires an interactive terminal. It refreshes observations until you
press `q` and restores the terminal when it exits. `--json` returns the
`worldline.spatial-frame/1` projection, including the source and verification
status for each frame. It does not upgrade uncertain observations into exact
ones. Use the ordinary `windows` facts or the JSON Lines query API when you need
full evidence receipts.

### What geometry means

Monitor layout comes from Mutter DisplayConfig. AT-SPI provides application
semantics, state, and component extents. Those extents are not proof of a
window's compositor frame or stacking position. When the Cua GNOME helper is
hosted by the trusted GNOME Shell, its compositor frames and stacking can be
joined to a unique same-process, same-title, overlapping AT-SPI match.
Unmatched compositor windows remain geometry-only. The helper's owner and
host executable are checked before its data is accepted as compositor
evidence.

Even a verified frame and stacking order describe rectangles, not rendered
pixels. Transparency, shaped surfaces, shadows, and actual pixel visibility
remain unknown. Missing sources are reported as unavailable; WORLDLINE does
not fill those gaps with inferred focus, workspaces, activation targets, or
stacking order.

## Integrate through the socket

The daemon exposes a user-private Unix socket using newline-delimited JSON.
For example, request the spatial projection with:

```json
{"protocol":1,"op":"query","args":{"view":"geometry"}}
```

The response includes a `worldline.spatial-frame/1` object. `worldlinectl hello`
reports the socket's `domain_id`, protocol, and receipt schema.

Protocol 1 includes `fence`, `event`, `capture`, `wait`, and `receipt` operations
for comparing evidence across revisions. GWCU and Horner use the same
WORLDLINE instance when they need to share a revision domain. A nested Horner
DevKit intentionally uses a separate socket and domain. Start the WORLDLINE
service before installing GWCU, then verify GWCU's doctor before bringing up
Horner. If the daemon restarts, discard old fences and take a new one. A
foreground observation alone does not establish that an application's
intended effect occurred; a receipt identifies the specific claim that newer,
independent evidence supports.

## Update an existing checkout

```bash
./update.sh
```

The updater fast-forwards the current branch, refreshes the editable virtual
environment, restarts the installed user service (or on-demand daemon), and
checks a fresh operating fact. It stops if the checkout has local changes.

## Development

```bash
.venv/bin/python -m pytest -q
git diff --check
```

The source catalogue describes each provider, its acquisition method, and read
cost. Operating facts carry source, observation time, validity, and revision;
source outages are represented as unavailable observations.

The canonical mark and supporting artwork live in [`assets/brand/`](assets/brand/).
