#!/usr/bin/env bash
# WORLDLINE owns its installation and user-service lifecycle.
set -euo pipefail

APP_ROOT="${XDG_DATA_HOME:-$HOME/.local/share}/worldline"
SOURCE="$APP_ROOT/source"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
UNIT_FILE="$UNIT_DIR/worldline.service"
SOCKET="${WORLDLINE_SOCKET:-${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/worldline/worldline.sock}"
REPO="https://github.com/ryanraposo/WORLDLINE.git"
GRANT_FRAMES=0
JSON=0
COMMAND="${1:-status}"
shift || true

while (($#)); do
  case "$1" in
    --grant-window-frames) GRANT_FRAMES=1 ;;
    --json) JSON=1 ;;
    -h|--help)
      cat <<'HELP'
WORLDLINE installation manager

Usage:
  scripts/worldline-install.sh install [--grant-window-frames]
  scripts/worldline-install.sh status [--json]
  scripts/worldline-install.sh start
  scripts/worldline-install.sh upgrade [--grant-window-frames]
  scripts/worldline-install.sh repair [--grant-window-frames]
  scripts/worldline-install.sh uninstall

WORLDLINE owns its source checkout, user service and socket. Existing
unmanaged checkouts are never overwritten or removed.
HELP
      exit 0 ;;
    *) printf 'Unknown option: %s\n' "$1" >&2; exit 2 ;;
  esac
  shift
done

die(){ printf 'WORLDLINE: %s\n' "$*" >&2; exit 1; }
need(){ command -v "$1" >/dev/null 2>&1 || die "Required command not found: $1"; }

rpc(){
  python3 - "$SOCKET" <<'PY'
import json, socket, sys
path=sys.argv[1]
with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
    client.settimeout(3)
    client.connect(path)
    client.sendall((json.dumps({"protocol":1,"op":"features","args":{}})+"\n").encode())
    data=b""
    while b"\n" not in data and len(data)<1048576:
        chunk=client.recv(65536)
        if not chunk: break
        data+=chunk
response=json.loads(data.split(b"\n",1)[0])
if not response.get("ok") or "receipt" not in response.get("result",{}).get("ops",[]):
    raise SystemExit(1)
print(json.dumps({"ok":True,"protocol":response.get("protocol"),"ops":response["result"]["ops"]},separators=(",",":")))
PY
}

managed_source(){
  [ -f "$APP_ROOT/.worldline-managed" ] && [ -d "$SOURCE/.git" ]
}

install_source(){
  need git
  mkdir -p "$APP_ROOT"
  if [ -e "$SOURCE" ] && ! managed_source; then
    die "Refusing to replace unmanaged path $SOURCE. Choose another XDG_DATA_HOME or manage that checkout directly."
  fi
  if ! managed_source; then
    mkdir -p "$APP_ROOT"
    git clone --depth 1 "$REPO" "$SOURCE"
    printf '%s\n' 'managed-install-v1' > "$APP_ROOT/.worldline-managed"
    chmod 600 "$APP_ROOT/.worldline-managed"
  fi
}

install_service(){
  [ -x "$SOURCE/scripts/install_user_service.sh" ] || die "WORLDLINE service installer is missing from $SOURCE"
  if [ "$GRANT_FRAMES" -eq 1 ]; then
    WORLDLINE_GRANT_WINDOW_FRAMES=1 "$SOURCE/scripts/install_user_service.sh"
  else
    "$SOURCE/scripts/install_user_service.sh"
  fi
  verify_ready
}

verify_ready(){
  local attempt
  for attempt in {1..20}; do
    if rpc >/dev/null 2>&1; then
      printf 'WORLDLINE ready: protocol 1, receipt support, socket %s\n' "$SOCKET"
      return 0
    fi
    sleep 0.5
  done
  systemctl --user status worldline.service --no-pager >&2 || true
  die "WORLDLINE service did not answer the protocol-1 receipt check at $SOCKET"
}

case "$COMMAND" in
  install)
    need python3; need git; need systemctl
    install_source
    install_service
    ;;
  status)
    active=0; systemctl --user is-active --quiet worldline.service && active=1 || true
    payload=""
    if payload="$(rpc 2>/dev/null)"; then ready=1; else ready=0; fi
    if [ "$JSON" -eq 1 ]; then
      printf '{"installed":%s,"service_active":%s,"ready":%s,"socket":"%s","protocol":1}\n' \
        "$([ -f "$UNIT_FILE" ] && printf true || printf false)" \
        "$([ "$active" -eq 1 ] && printf true || printf false)" \
        "$([ "$ready" -eq 1 ] && printf true || printf false)" "$SOCKET"
    else
      printf 'Installation: %s\nService: %s\nProtocol RPC: %s\nSocket: %s\n' \
        "$([ -f "$UNIT_FILE" ] && printf installed || printf missing)" \
        "$([ "$active" -eq 1 ] && printf active || printf inactive)" \
        "$([ "$ready" -eq 1 ] && printf ready || printf unavailable)" "$SOCKET"
    fi
    [ "$ready" -eq 1 ]
    ;;
  start)
    need systemctl
    systemctl --user start worldline.service
    verify_ready
    ;;
  upgrade)
    need git; need systemctl
    managed_source || die "This installation is not owned by WORLDLINE's installer; update its original checkout instead."
    [ -z "$(git -C "$SOURCE" status --porcelain)" ] || die "Refusing to overwrite local changes in $SOURCE"
    git -C "$SOURCE" pull --ff-only
    install_service
    ;;
  repair)
    need systemctl
    if managed_source; then install_service
    elif [ -f "$UNIT_FILE" ]; then
      systemctl --user restart worldline.service
      verify_ready
    else
      die "WORLDLINE is not installed. Run: worldline-install.sh install"
    fi
    ;;
  uninstall)
    need systemctl
    systemctl --user disable --now worldline.service >/dev/null 2>&1 || true
    rm -f "$UNIT_FILE"
    systemctl --user daemon-reload
    if command -v gnome-extensions >/dev/null 2>&1; then
      gnome-extensions uninstall worldline-window-frames@worldline >/dev/null 2>&1 || true
    fi
    if managed_source; then rm -rf "$APP_ROOT"; fi
    printf 'WORLDLINE service uninstalled. User data and unmanaged checkouts were preserved.\n'
    ;;
  *) die "Unknown command: $COMMAND" ;;
esac
