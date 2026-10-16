# Changelog

## 0.1.1 — 2026-10-15

Fix native rotation responses to emit `versionNo` instead of `currentVersionNo`. Preserve the documented input alias and reject conflicts. Add exact wire-contract regression tests. Deployed native Rotate passed end-to-end with scheduling disabled, advancing Vault CURRENT and verifying a fresh login. Update deployment, testing and acceptance documentation.

## 0.1.0 — 2026-10-15

Initial custom OCI Vault / PostgreSQL application-role integration: discovery, CLI, recoverable engine, Function protocol, Terraform and operating procedures. Administrator and alternating-user strategies remain gated. Customer integration and network-dependent release checks are pending; see the handoff matrix.
