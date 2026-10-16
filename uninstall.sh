#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
# Plan only. Existing Vault credentials and durable recovery evidence are retained.
exec .venv/bin/pg-vault-rotation "${@}" uninstall --plan
