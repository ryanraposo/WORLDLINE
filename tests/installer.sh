#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
installer="$ROOT/scripts/worldline-install.sh"
bash -n "$installer"
help="$("$installer" --help)"
grep -Fq 'install [--grant-window-frames]' <<<"$help"
grep -Fq 'upgrade [--grant-window-frames]' <<<"$help"
grep -Fq 'uninstall' <<<"$help"
if "$installer" invalid-command >/dev/null 2>&1; then
  printf 'unknown lifecycle command unexpectedly succeeded\n' >&2
  exit 1
fi
printf 'ok - WORLDLINE lifecycle entrypoint syntax and command surface\n'
