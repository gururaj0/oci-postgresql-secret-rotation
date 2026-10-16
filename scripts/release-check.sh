#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python -m pip install -r requirements-dev.txt
# Produces a complete, hashed runtime lock from the pinned pyproject dependencies.
python -m piptools compile --allow-unsafe --generate-hashes --output-file requirements.resolved.lock pyproject.toml
python -m pip install --require-hashes -r requirements.resolved.lock
python -m pip install --no-deps .
python -m unittest discover -v
python scripts/security-check.py
python -m ruff check src functions tests
python -m pip_audit -r requirements.resolved.lock
terraform -chdir=terraform init -backend=false -input=false
terraform -chdir=terraform fmt -check -recursive
terraform -chdir=terraform validate
python -m build
echo 'Local release checks passed. Complete the approved customer acceptance runbook before production.'
