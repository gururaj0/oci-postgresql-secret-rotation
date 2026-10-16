# IAM and private networking

The Terraform IAM module binds one dynamic group to the exact Function OCID and another to the exact Vault secret resource principal. This follows Oracle's [documented rotation Function permissions](https://docs.oracle.com/en-us/iaas/Content/Functions/Tasks/functions_pbf_database_secret_rotation_with_wallet.htm). The independent monitor schedule has its own exact-resource dynamic group.

The Function can read bundles for the selected secret, inspect its versions and update that secret, access journal objects in the dedicated bucket, and post metrics in `pg_vault_rotation`. It receives no permission to create/delete secrets or administer PostgreSQL systems. The secret resource principal and monitor schedule can invoke only the selected Function. Review target-condition support and policy propagation in the customer's identity domain before acceptance.

Deploying policies/dynamic groups requires a tenancy administrator. The installer identity additionally needs read discovery access, approved Functions deployment and image access, network use, bucket creation if requested, logging/monitoring and Resource Scheduler management. The bootstrap-secret operator needs `CreateSecret`, key use and the customer's approved Vault policies; the rotation Function does not.

Use a dedicated journal bucket so object read/create/update/delete access cannot expose unrelated data. Conditional writes (`if-none-match`/`if-match`) implement lock and journal coordination. Bucket metadata reads are needed by the operator's validation command. Audit and restrict manual lock deletion to incident responders.

The selected Function subnet must prohibit public VNIC IPs. Customers own route tables and NSGs: allow DB traffic only between approved Function and DB subnets/NSGs; allow the private Function to reach OCI service endpoints and pull images. A private subnet alone does not prove these routes work. No public database ingress is created by this package.

IAM cannot be fully proven read-only before a Function exists. Validate effective permissions with the deployed resource principal and approved acceptance rotation, including deliberate denied-access tests. Do not work around a denied API by granting tenancy-wide management.
