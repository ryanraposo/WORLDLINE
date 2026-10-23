#!/bin/sh
set -eu

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
unit_dir=${XDG_CONFIG_HOME:-"$HOME/.config"}/systemd/user
unit_file=$unit_dir/worldline.service

mkdir -p "$unit_dir"
sed "s|@WORLDLINE_SRC@|$repo_root/src|g" \
    "$repo_root/systemd/worldline.service" > "$unit_file"
chmod 0644 "$unit_file"

# The repository's hooks restart an active daemon after pull/merge/checkout.
git -C "$repo_root" config --local core.hooksPath .githooks

systemctl --user daemon-reload
systemctl --user enable --now worldline.service

printf 'Installed and started %s\n' "$unit_file"
printf 'Git updates will restart the service when the hook runs.\n'
