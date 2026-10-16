#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
python3 -m venv .venv
if [[ -f requirements.resolved.lock ]]; then
  .venv/bin/python -m pip install --require-hashes -r requirements.resolved.lock
else
  echo 'Implementation candidate: transitive release lock and security audit are still required.'
  .venv/bin/python -m pip install -r requirements.lock
fi
.venv/bin/python -m pip install --no-deps .
echo 'Installed. Activate with: source .venv/bin/activate'
echo 'Start read-only: pg-vault-rotation discover'
