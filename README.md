<!-- WORLDLINE: Operating Fact -->
<p align="center">
  <img src="assets/brand/vector/worldline-readme-header.svg" alt="WORLDLINE" width="100%">
</p>

# WORLDLINE

**Operating facts.**

WORLDLINE is a read-only observation service for Ubuntu desktops running GNOME on Wayland. It turns what the host and desktop can currently establish into structured, revisioned facts that people and independent tools can inspect.

It records where a fact came from, when it was observed, how fresh it is, and which revision it belongs to. Consumers can refresh observations, compare revisions, and verify whether newer evidence supports a specific claim.

WORLDLINE does not inject input, activate windows, or decide whether an action is safe. It supplies the observable state; the consumer remains responsible for policy and action.

## Get started

### Managed installation

The recommended path installs a persistent user service from the public repository. Run it as the logged-in desktop user, not with sudo.

~~~bash
sudo apt install git python3 python3-venv python3-pyatspi libglib2.0-bin zip
git clone https://github.com/ryanraposo/WORLDLINE.git
cd WORLDLINE
./scripts/worldline-install.sh install
./scripts/worldline-install.sh status
~~~

The installer owns its managed checkout, user service, and readiness checks. It will not overwrite an unmanaged checkout or service. It asks before installing and enabling the read-only GNOME Shell frame extension. See [installation requirements](docs/INSTALLATION.md) for the supported environment and system dependencies. Review the permission prompt: the extension exposes compositor window-frame and state information over a user-session D-Bus API; it does not send input or activate windows.

If GNOME needs to reload the extension, save your work and follow the installer's instructions. For unattended installation, use the explicit grant option only after the user has authorized that access:

~~~bash
./scripts/worldline-install.sh install --grant-window-frames
~~~

### Lifecycle commands

~~~bash
./scripts/worldline-install.sh status --json
./scripts/worldline-install.sh start
./scripts/worldline-install.sh upgrade
./scripts/worldline-install.sh repair
./scripts/worldline-install.sh uninstall
~~~

The managed source is normally stored at ~/.local/share/worldline/source. The service is a systemd user unit and the canonical socket is $XDG_RUNTIME_DIR/worldline/worldline.sock.

### Developer setup

For a temporary CLI session or source development, use an editable virtual environment instead:

~~~bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev]'
# In another terminal, start the daemon explicitly (the CLI never starts one):
worldline-daemon
~~~

~~~bash
worldline --fresh --explain windows.active.geometry
~~~

The CLI only queries an already-running daemon; a read never starts a persistent service as a side effect. WORLDLINE uses the system Python when required to access the desktop's AT-SPI bindings. The managed service installer is separate from this developer workflow.

## Read operating facts

~~~bash
worldline                                      # complete snapshot and source status
worldline os.kernel memory.percent             # selected values
worldline windows.active.geometry              # active window geometry
worldline --fresh windows.active.geometry      # refresh before reading
worldline --explain windows.active.geometry    # value, source, revision and age
worldline --list                               # available sections
worldline --list windows                       # paths in a section
worldlinectl sources                           # provider and source catalogue
worldlinectl hello                             # socket and protocol metadata
~~~

Output is JSON. A path query returns its value. Explain mode adds the fact's source, observation time, revision, and freshness. Fresh mode samples the requested source before returning. Window records have stable IDs that can be queried later through windows.by_id.

## Explore desktop geometry

~~~bash
worldline geometry
worldline geometry --json
worldline geometry --live
worldline geometry --live --interval 1.0
worldline geometry --live --title "WORLDLINE"
~~~

The terminal view arranges monitors and window frames in logical desktop coordinates. Verified outlines follow observed compositor stacking order; the active window is highlighted. Unverified frames are visibly marked rather than presented as exact. Window names and source details appear below the drawing so overlapping frames cannot obscure labels.

The live view requires an interactive terminal, redraws in the alternate screen, and exits with q. The JSON view returns the worldline.spatial-frame/1 projection with source and verification status.

### Geometry and evidence boundaries

Monitor layout comes from Mutter DisplayConfig. AT-SPI supplies application semantics, state, and component extents; those extents alone do not prove a compositor frame or stacking position.

When the WORLDLINE GNOME Shell extension is hosted by the trusted GNOME Shell, compositor frames and stacking can be joined to a unique same-process, same-title, overlapping AT-SPI match. Unmatched compositor windows remain geometry-only. WORLDLINE verifies the API owner and host executable before accepting compositor evidence.

A verified frame and stacking order describe rectangles, not rendered pixels. Transparency, shaped surfaces, shadows, and actual pixel visibility remain unknown. Missing sources stay unavailable; WORLDLINE does not invent focus, workspace membership, activation targets, or stacking order.

## Compositor-native desktop observation

WORLDLINE exposes a session-scoped, revisioned desktop model through the daemon's `desktop` protocol operation. It enumerates and resolves observed window identities, reports geometry/state/provenance/capabilities, and publishes a bounded lifecycle event journal. It remains read-only; unavailable sources never become fabricated window destruction or state changes. See [the desktop observation contract](docs/DESKTOP_OBSERVATION.md) for request/response examples and identity semantics.

## Integrate through the socket

The daemon exposes a user-private Unix socket using newline-delimited JSON. For example, request the spatial projection:

~~~json
{"protocol":1,"op":"query","args":{"view":"geometry"}}
~~~

Protocol 1 exposes feature discovery and the fence, event, capture, wait, and receipt operations. The features response advertises the supported operations, protocol version, package version, revision domain, and receipt schema. GWCU verifies protocol 1 and receipt support before declaring the dependency ready.

Independent consumers that need to compare observations must use the same WORLDLINE instance and revision domain. If the daemon restarts, discard old fences and establish a new baseline. A foreground observation alone does not prove an application's intended effect; a receipt records the specific claim supported by newer, independent evidence.

### Ownership

- **WORLDLINE:** host and desktop observation, facts, source metadata, revisions, socket, readiness, and its own installation lifecycle.
- **GWCU:** execution policy and causal completion verification.
- **Cua Driver:** the actuator. WORLDLINE remains read-only.

GWCU does not vendor WORLDLINE, install a duplicate daemon, or own WORLDLINE's service unit. GWCU's durable local state remains separate.

## Update a developer checkout

~~~bash
./update.sh
~~~

The updater fast-forwards the current branch, refreshes the editable environment, restarts the installed user service when one is managed, and checks a fresh operating fact from the running daemon. It stops when the checkout has local changes.

## Development and tests

~~~bash
python -m pip install -e '.[dev]'
python -m pytest -q
bash -n scripts/worldline-install.sh
bash tests/installer.sh
git diff --check
~~~

The tests cover the Python observation and protocol layers, CLI behavior, geometry, source handling, and installer lifecycle safeguards. The installer checks include refusal to replace unmanaged source and service paths, and preservation of pre-existing extension state.

## Project site and assets

The project site is published with GitHub Pages from the site directory. The canonical mark, lockups, icons, social card, and supporting diagrams are maintained as vector artwork in assets/brand/. The site build copies those source assets into its deployment artifact.

## License

WORLDLINE is distributed under the MIT License. See LICENSE.
