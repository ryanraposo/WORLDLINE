#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
installer="$ROOT/scripts/worldline-install.sh"
bash -n "$installer"
grep -Fq 'INSTALL_REF="${WORLDLINE_INSTALL_REF:-main}"' "$installer"
grep -Fq 'response.get("protocol") != 1' "$installer"
if grep -Fq '\nINSTALL_REF=' "$installer"; then
  printf 'installer ref declaration contains a literal escaped newline\n' >&2
  exit 1
fi
help="$("$installer" install --help)"
grep -Fq 'install [--grant-window-frames]' <<<"$help"
grep -Fq 'upgrade [--grant-window-frames]' <<<"$help"
grep -Fq 'uninstall' <<<"$help"
if "$installer" invalid-command >/dev/null 2>&1; then
  printf 'unknown lifecycle command unexpectedly succeeded\n' >&2
  exit 1
fi
printf 'ok - WORLDLINE lifecycle entrypoint syntax and command surface\n'
