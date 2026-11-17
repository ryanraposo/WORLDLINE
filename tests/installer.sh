#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
installer="$ROOT/scripts/worldline-install.sh"
bash -n "$installer"
grep -Fq 'INSTALL_REF="${WORLDLINE_INSTALL_REF:-main}"' "$installer"
grep -Fq 'response.get("protocol") != 1' "$installer"
grep -Fq 'preexisting-enabled' "$installer"
grep -Fq 'preexisting-disabled' "$installer"
grep -Fq 'gnome-extensions info "$extension_id"' "$ROOT/scripts/install_user_service.sh"
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

# Unmanaged source and service paths must survive install refusal and uninstall.
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
mkdir -p "$tmp/bin" "$tmp/data/worldline/source" "$tmp/config/systemd/user" "$tmp/runtime"
printf 'user checkout\n' > "$tmp/data/worldline/source/keep.txt"
printf '[Service]\nExecStart=/opt/user-worldline\n' > "$tmp/config/systemd/user/worldline.service"
cat > "$tmp/bin/systemctl" <<'SH'
#!/usr/bin/env bash
exit 0
SH
chmod +x "$tmp/bin/systemctl"
env PATH="$tmp/bin:$PATH" XDG_DATA_HOME="$tmp/data" XDG_CONFIG_HOME="$tmp/config" \
  XDG_RUNTIME_DIR="$tmp/runtime" WORLDLINE_SOCKET="$tmp/runtime/missing.sock" \
  "$installer" install >/dev/null 2>&1 && {
    printf 'install unexpectedly accepted unmanaged source/service paths\n' >&2
    exit 1
  }
test -f "$tmp/data/worldline/source/keep.txt"
grep -Fq '/opt/user-worldline' "$tmp/config/systemd/user/worldline.service"
env PATH="$tmp/bin:$PATH" XDG_DATA_HOME="$tmp/data" XDG_CONFIG_HOME="$tmp/config" \
  XDG_RUNTIME_DIR="$tmp/runtime" WORLDLINE_SOCKET="$tmp/runtime/missing.sock" \
  "$installer" uninstall >/dev/null
test -f "$tmp/data/worldline/source/keep.txt"
grep -Fq '/opt/user-worldline' "$tmp/config/systemd/user/worldline.service"
printf 'ok - unmanaged WORLDLINE checkout and service survive refusal/uninstall\n'
