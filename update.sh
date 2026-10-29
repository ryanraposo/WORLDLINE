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
    ./scripts/install_user_service.sh
    systemctl --user restart worldline.service
    systemctl --user is-active --quiet worldline.service
else
    .venv/bin/worldlinectl close >/dev/null 2>&1 || true
fi
.venv/bin/worldline --fresh os.kernel
