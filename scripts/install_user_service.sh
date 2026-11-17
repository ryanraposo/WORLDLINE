#!/bin/sh
set -eu

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
unit_dir=${XDG_CONFIG_HOME:-"$HOME/.config"}/systemd/user
unit_file=$unit_dir/worldline.service
extension_id=worldline-window-frames@worldline

if [ "${WORLDLINE_GRANT_WINDOW_FRAMES:-}" != 1 ]; then
    if [ ! -t 0 ]; then
        printf '%s\n' 'WORLDLINE needs permission to install its read-only GNOME window-frame extension.' >&2
        printf '%s\n' 'Run this installer in a terminal, or set WORLDLINE_GRANT_WINDOW_FRAMES=1 after reviewing that access.' >&2
        exit 2
    fi
    printf '%s\n' 'WORLDLINE can install a GNOME Shell extension that reports window frame rectangles, titles, focus, visibility, and stacking.'
    printf '%s\n' 'It does not activate windows or send input. The read-only D-Bus API is available to applications in this user session.'
    printf 'Grant WORLDLINE this access and continue? [y/N] '
    IFS= read -r answer || answer=
    case $answer in
        y|Y|yes|YES) ;;
        *) printf '%s\n' 'Installation cancelled; no files were changed.'; exit 1 ;;
    esac
fi

if ! command -v gnome-extensions >/dev/null 2>&1; then
    printf '%s\n' 'gnome-extensions is required to install the WORLDLINE frame API.' >&2
    exit 1
fi

bundle_dir=$(mktemp -d "${TMPDIR:-/tmp}/worldline-extension.XXXXXX")
bundle=$bundle_dir/$extension_id.zip
trap 'rm -rf "$bundle_dir"' EXIT HUP INT TERM
if ! command -v zip >/dev/null 2>&1; then
    printf '%s\n' 'zip is required to package the WORLDLINE GNOME Shell extension.' >&2
    exit 1
fi
(cd "$repo_root/gnome-extension" && zip -q -j "$bundle" metadata.json extension.js)
if ! gnome-extensions info "$extension_id" >/dev/null 2>&1; then
    gnome-extensions install --force "$bundle"
fi
python3 - "$extension_id" <<'PY'
import ast
import subprocess
import sys

schema = "org.gnome.shell"
key = "enabled-extensions"
extension_id = sys.argv[1]
current = subprocess.check_output(["gsettings", "get", schema, key], text=True).strip()
enabled = ast.literal_eval(current) if current.startswith("[") else []
if extension_id not in enabled:
    enabled.append(extension_id)
    subprocess.run(["gsettings", "set", schema, key, repr(enabled)], check=True)
PY

mkdir -p "$unit_dir"
sed "s|@WORLDLINE_SRC@|$repo_root/src|g" \
    "$repo_root/systemd/worldline.service" > "$unit_file"
chmod 0644 "$unit_file"

# The repository's hooks restart an active daemon after pull/merge/checkout.
git -C "$repo_root" config --local core.hooksPath .githooks

systemctl --user daemon-reload
systemctl --user enable worldline.service
if systemctl --user is-active --quiet worldline.service; then
    systemctl --user restart worldline.service
else
    systemctl --user start worldline.service
fi

printf 'Installed and started %s\n' "$unit_file"
printf 'Git updates will restart the service when the hook runs.\n'
if ! gdbus call --session --dest org.freedesktop.DBus --object-path /org/freedesktop/DBus \
    --method org.freedesktop.DBus.NameHasOwner org.worldline.WindowFrames 2>/dev/null | grep -q 'true'; then
    printf '%s\n' 'GNOME Shell must reload to activate the frame API. Save open work before logging out.'
    if [ -t 0 ]; then
        printf 'Open GNOME’s logout confirmation now? [y/N] '
        IFS= read -r answer || answer=
        case $answer in
            y|Y|yes|YES)
                if command -v gnome-session-quit >/dev/null 2>&1; then
                    gnome-session-quit --logout
                    printf '%s\n' 'After signing back in, the WORLDLINE frame API will load automatically.'
                else
                    printf '%s\n' 'gnome-session-quit is unavailable; log out and back in from the system menu.'
                fi
                ;;
            *) printf '%s\n' 'When convenient, log out and back in from the system menu to activate the frame API.' ;;
        esac
    else
        printf '%s\n' 'When convenient, log out and back in from the system menu to activate the frame API.'
    fi
fi
