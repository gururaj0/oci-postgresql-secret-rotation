# Security

Report security issues privately to the customer's designated security owner; include the affected release, operation ID, state and sanitized reproduction. Never include a secret bundle, password, SCRAM verifier, OCI private key, API authorization header or database query text.

Credentials exist only in Vault and process memory. Bootstrap accepts the existing password through `getpass` on a real local terminal. Terraform has no secret content resources/data sources; Function configuration contains identifiers and connection settings only. Memory is not guaranteed to be securely erased by Python. Restrict debugging, crash dumps, interactive access, journal access and Vault bundle permissions accordingly.

The SQL adapter generates a SCRAM verifier locally so the plaintext password is not sent in `ALTER ROLE`. Treat verifiers as sensitive too. Database administrators must review statement/audit logging configuration before acceptance. The package never logs SQL or raw third-party exceptions. OCI Audit still records service operations under the invoking principal.

Use verified TLS with a customer-approved CA and the database's certificate hostname, private routing, service gateways/NAT only as needed, and NSGs restricted to Function-to-database TCP/5432 (or the approved configured port). Never disable TLS verification to solve a certificate error.

Use a dedicated private Object Storage bucket with versioning. Keep each database/role mapped to exactly one journal bucket and one active deployment; a second independent bucket cannot coordinate its lock. Do not enable retention rules that prevent lock deletion. Encrypt with the service's at-rest encryption or an approved customer-managed key. Never create public access or preauthenticated requests for journal objects.

Before release, run the hashed dependency audit and lint in `scripts/release-check.sh`; scan the built image with the customer's approved container scanner. Review findings, patch pins, rerun failure tests, and record the image digest. The resolved dependency audit completed on 2026-10-15 with no known vulnerabilities. The deployed demo image was also scanned: no critical findings, but unresolved OS-package findings include 44 high-severity entries without listed fixes. Production security acceptance remains open.
