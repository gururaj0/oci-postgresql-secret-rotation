import oci


def all_results(call, *args, **kwargs):
    kwargs.setdefault("retry_strategy", oci.retry.NoneRetryStrategy())
    # Explicit pagination avoids the SDK helper's independent default retry loop.
    # Discovery must return partial results promptly when a regional endpoint is unreachable.
    values = []
    while True:
        result = call(*args, **kwargs)
        data = result.data
        values.extend(data.items if hasattr(data, "items") and not isinstance(data, dict) else data)
        page = result.headers.get("opc-next-page")
        if not page:
            return values
        kwargs["page"] = page


def discover(config, database_only=False):
    options = {"timeout": (5, 10), "retry_strategy": oci.retry.NoneRetryStrategy()}
    identity = oci.identity.IdentityClient(config, **options)
    tenancy = config["tenancy"]
    compartments = all_results(identity.list_compartments, tenancy, compartment_id_in_subtree=True,
                               access_level="ACCESSIBLE", lifecycle_state="ACTIVE")
    scope = [{"id": tenancy, "name": "tenancy-root"}] + [
        {"id": c.id, "name": c.name} for c in compartments]
    regions = all_results(identity.list_region_subscriptions, tenancy)
    result = {"tenancy": tenancy, "profile_region": config["region"], "compartments": scope,
              "regions": [], "errors": []}
    for region in regions:
        if region.status != "READY":
            continue
        rc = dict(config, region=region.region_name)
        pg = oci.psql.PostgresqlClient(rc, **options)
        network = oci.core.VirtualNetworkClient(rc, **options)
        vault = oci.key_management.KmsVaultClient(rc, **options)
        secrets = oci.vault.VaultsClient(rc, **options)
        functions = oci.functions.FunctionsManagementClient(rc, **options)
        resources = {"region": rc["region"], "databases": [], "vaults": [], "keys": [],
                     "secrets": [], "vcns": [], "subnets": [], "applications": []}
        queries = [("databases", pg.list_db_systems)]
        if not database_only:
            queries += [("vaults", vault.list_vaults), ("secrets", secrets.list_secrets),
                        ("vcns", network.list_vcns), ("subnets", network.list_subnets),
                        ("applications", functions.list_applications)]
        failed_services = set()
        for compartment in scope:
            for kind, method in queries:
                if kind in failed_services:
                    continue
                try:
                    values = all_results(method, compartment_id=compartment["id"])
                    for v in values:
                        item = {"id": v.id, "name": getattr(v, "display_name", None) or
                                getattr(v, "secret_name", None), "compartment_id": compartment["id"],
                                "state": v.lifecycle_state}
                        if kind == "subnets":
                            item.update(private=v.prohibit_public_ip_on_vnic, vcn_id=v.vcn_id)
                        if kind == "vaults" and v.lifecycle_state == "ACTIVE" and not database_only:
                            try:
                                km = oci.key_management.KmsManagementClient(rc, service_endpoint=v.management_endpoint, **options)
                                resources["keys"] += [{"id": k.id, "name": k.display_name, "vault_id": v.id}
                                                      for k in all_results(km.list_keys, compartment_id=compartment["id"])]
                            except Exception as exc:
                                result["errors"].append({"region": rc["region"], "resource": "keys",
                                                         "status": getattr(exc, "status", type(exc).__name__)})
                        resources[kind].append(item)
                except Exception as exc:
                    result["errors"].append({"region": rc["region"], "compartment": compartment["id"],
                                             "resource": kind, "status": getattr(exc, "status", type(exc).__name__)})
                    if not isinstance(exc, oci.exceptions.ServiceError):
                        failed_services.add(kind)
        result["regions"].append(resources)
    return result
