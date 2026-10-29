<p align="center">
  <img src="assets/banner.png" alt="WORLDLINE logo and wordmark" width="1200">
</p>

# WORLDLINE

**A live, revisioned view of what the machine knows now.** WORLDLINE reads host
and desktop sources, records when each observation was made, and gives agents
JSON facts they can refresh before acting.

## Install

On Ubuntu with GNOME and Wayland:

```bash
sudo apt install git python3 python3-venv python3-pyatspi libglib2.0-bin
git clone https://github.com/ryanraposo/WORLDLINE.git
cd WORLDLINE
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev]'
worldline --fresh --explain windows.active.geometry
```

The CLI starts its private observation daemon on first use. The daemon uses a
Python interpreter with the system AT-SPI binding for window observations.
Run `pytest` to check the installation and repository tests.

To keep the daemon running for the graphical session and restart it when Git
updates the checkout, install the user service:

```bash
./scripts/install_user_service.sh
```

The service runs this checkout directly. The installer configures repository
hooks that restart an active service after pull/merge or checkout; it does not
fetch or apply remote updates automatically. Check it with
`systemctl --user status worldline.service`.

## Update

From the existing checkout, run:

```bash
./update.sh
```

This fast forwards the current branch, refreshes the virtual environment,
restarts an installed user service (or the on-demand daemon), and checks a
fresh operating fact. It stops if the checkout has local changes.

## Use

```bash
worldline                                 # current snapshot and source status
worldline os.kernel memory.percent        # selected values as JSON
worldline windows.active.geometry         # active window extents and display context
worldline --fresh windows.active.geometry # refresh before reading
worldline --explain windows.active.geometry # value, revision and evidence
worldline --list                          # available sections
worldline --list windows                  # paths in the windows section
worldlinectl sources                      # provider and source catalogue
```

`stdout` contains JSON. A path query returns its value; `--explain` adds its
revision, source, observation time and freshness. `--fresh` samples the
requested source before returning. The `windows.by_id` map lets a later query
address an observed window by its `stable_id`.

For integrations, the JSON Lines socket exposes `fence` and predicate-based
`wait` operations to compare an action with later evidence.

## Operating facts

An operating fact couples a value with a source receipt, observation time,
validity and revision. WORLDLINE reports source availability in the full
snapshot. A source outage appears as an unavailable observation.

Window titles, states and component extents come from AT-SPI. Mutter
DisplayConfig supplies monitor layout. When the Cua GNOME helper is hosted by
the attested GNOME Shell, its stable window IDs and exact compositor frames
join unique process/title/overlap matches; AT-SPI component extents remain
separate. Unmatched compositor windows remain geometry-only. Every frame
names its source. Compositor stacking bounds rectangle exposure; transparency
and pixel visibility remain uncertain.

The socket is protocol 1 and rejects other versions before mutation. GWCU and
Horner share its revision domain: `fence` seals a pre-action boundary, `event`
and `capture` add observations, `wait` tests fresh predicates and conflicts,
and `receipt` correlates actuator acknowledgement with a newer observation
from another source. The receipt's `claim` identifies what was verified;
foreground admission alone does not establish an application's intended
effect. WORLDLINE observes but never injects input.

Check the live integration with `worldlinectl hello`: the response identifies
the socket's `domain_id`, protocol and receipt schema. GWCU and Horner must
use that same instance for a shared action; a nested Horner DevKit deliberately
uses a separate socket and domain. Start the WORLDLINE service before GWCU's
installer, then verify GWCU's doctor before bringing up Horner. If the daemon
restarts, discard outstanding fences and take a new one before acting.

The source catalogue identifies each provider, its acquisition method and
read cost. The daemon serves revisioned facts over a user-private Unix socket. Agents can
read a focused path, refresh its source, and compare later evidence with a
fence. Observation stays independent of each consumer's identity and actions.

The canonical mark and supporting artwork live in [`assets/brand/`](assets/brand/).
