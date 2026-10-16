# Changelog

## Resource Manager stack preview 2 — 2026-10-15

Add a browser deployment button, self-contained stack ZIP and guided form for an existing PostgreSQL database and Vault secret. Resource Manager retrieves the public CA, builds/pushes a private image, selects the matching Function architecture, deploys infrastructure and validates a fresh TLS login before linking the secret. Automatic password rotation remains an explicit option.

Use the service-supported hourly health monitor in both Terraform deployment paths, with a two-hour missing-heartbeat alarm. Normalize the scheduler body for provider 9.9.0. Native build and Function deployment passed on the managed ARM runner. See validation details for the completed cloud checks and remaining customer acceptance gates.

## 0.1.1 — 2026-10-15

Fix native rotation responses to emit `versionNo` instead of `currentVersionNo`. Preserve the documented input alias and reject conflicts. Add exact wire-contract regression tests. Deployed native Rotate passed end-to-end with scheduling disabled, advancing Vault CURRENT and verifying a fresh login. Update deployment, testing and acceptance documentation.

## 0.1.0 — 2026-10-15

Initial custom OCI Vault / PostgreSQL application-role integration: discovery, CLI, recoverable engine, Function protocol, Terraform and operating procedures. Administrator and alternating-user strategies remain gated. Customer integration and network-dependent release checks are pending; see the handoff matrix.
