import oci

from rotation.engine import Engine
from rotation.model import RotationError
from rotation.store import ObjectStore
from vault.client import OciVault


def clients(config, profile="DEFAULT", resource_principal=False):
    if resource_principal:
        signer = oci.auth.signers.get_resource_principals_signer()
        if signer.tenancy_id != config.tenancy_id:
            raise RotationError("Resource principal tenancy differs from configured tenancy")
        auth = {"signer": signer}
        oc = {"region": config.region}
    else:
        oc = oci.config.from_file(profile_name=profile)
        if oc["tenancy"] != config.tenancy_id:
            raise RotationError("OCI profile tenancy differs from configured tenancy")
        oc["region"] = config.region
        auth = {}
    auth.update(timeout=(10, 30), retry_strategy=oci.retry.NoneRetryStrategy())
    return oc, auth


def runtime(c, profile="DEFAULT", resource_principal=False):
    from postgres.client import Postgres
    oc, auth = clients(c, profile, resource_principal)
    vault = OciVault(oci.vault.VaultsClient(oc, **auth), oci.secrets.SecretsClient(oc, **auth),
                     c.secret_id, c.username)
    store = ObjectStore(oci.object_storage.ObjectStorageClient(oc, **auth), c.state_namespace,
                        c.state_bucket, c.db_system_id, c.username)
    return Engine(vault, Postgres(c), store, c.db_system_id, c.username)


def preflight(c, profile="DEFAULT"):
    oc, auth = clients(c, profile)
    pg = oci.psql.PostgresqlClient(oc, **auth).get_db_system(c.db_system_id).data
    if pg.compartment_id != c.compartment_id or pg.lifecycle_state != "ACTIVE":
        raise RotationError("DB system is not ACTIVE in selected compartment")
    if c.username == pg.admin_username:
        raise RotationError("Managed administrator rotation is disabled; choose an application role")
    network = oci.core.VirtualNetworkClient(oc, **auth)
    subnet = network.get_subnet(c.subnet_id).data
    if not subnet.prohibit_public_ip_on_vnic:
        raise RotationError("Function subnet must prohibit public IP addresses")
    secret = oci.vault.VaultsClient(oc, **auth).get_secret(c.secret_id).data
    if secret.lifecycle_state != "ACTIVE" or secret.is_replica:
        raise RotationError("Select an ACTIVE source secret, not a replica")
    object_client = oci.object_storage.ObjectStorageClient(oc, **auth)
    bucket = object_client.get_bucket(c.state_namespace, c.state_bucket).data
    if bucket.public_access_type != "NoPublicAccess":
        raise RotationError("Journal bucket must be private")
    report = runtime(c, profile).validate()
    report["operator_read_access"] = True
    report["function_iam_and_network"] = "must validate from Function using validate action before scheduling"
    return report
