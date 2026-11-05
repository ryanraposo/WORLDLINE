#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$root"
if [[ -n "$(git status --porcelain)" ]]; then
    echo "WORLDLINE checkout has local changes; commit or resolve them before updating." >&2
    exit 2
fi

git pull --ff-only
if [[ ! -x .venv/bin/python ]]; then
    python3 -m venv .venv
fi
.venv/bin/python -m pip install -e .

if systemctl --user cat worldline.service >/dev/null 2>&1; then
    # A daemon started on demand may still own the socket. Close it before
    # starting the persistent service so the service takes over the new code.
    .venv/bin/worldlinectl close >/dev/null 2>&1 || true
    systemctl --user stop worldline.service >/dev/null 2>&1 || true
    ./scripts/install_user_service.sh
    ready=false
    for _ in {1..40}; do
        if systemctl --user is-active --quiet worldline.service \
            && .venv/bin/worldlinectl hello >/dev/null 2>&1; then
            ready=true
            break
        fi
        sleep 0.25
    done
    if [[ "$ready" != true ]]; then
        systemctl --user status worldline.service --no-pager -l >&2 || true
        echo "WORLDLINE service did not become ready." >&2
        exit 1
    fi
else
    .venv/bin/worldlinectl close >/dev/null 2>&1 || true
fi
.venv/bin/worldline --fresh os.kernel
