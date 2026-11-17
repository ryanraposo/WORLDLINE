# WORLDLINE installation requirements

## Supported environment

- Ubuntu 24.04 LTS or newer.
- GNOME Shell running on Wayland, in the logged-in desktop user's session.
- Python 3.11 or newer.
- A systemd user manager and the normal GNOME session D-Bus.

Other Linux distributions and desktop environments are not currently release-supported.

## Required system tools

The managed installer uses Git, Python, systemd user services, GNOME extension tooling, GSettings, D-Bus, and ZIP packaging. On Ubuntu, install the command-line and accessibility dependencies with:

```bash
sudo apt install git python3 python3-venv python3-pyatspi libglib2.0-bin zip
```

GNOME Shell and its extension tools are expected to be present in the supported GNOME desktop session. The extension is installed only after the user grants permission. It exposes read-only compositor window-frame and state information; it does not activate windows or send input.

## Python package dependencies

WORLDLINE has no third-party Python runtime dependencies declared in `pyproject.toml`. The desktop accessibility provider uses the distribution's AT-SPI/PyGObject bindings, which are supplied by the operating system. Development and test installations add pytest:

```bash
python3 -m pip install -e '.[dev]'
```

The managed installation path is preferred for normal desktop use. See the repository README for lifecycle commands and developer setup.
