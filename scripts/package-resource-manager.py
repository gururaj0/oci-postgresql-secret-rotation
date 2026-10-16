"""Build an allowlisted, self-contained Resource Manager ZIP; never include local config/state."""
import argparse
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def entries():
    result = {}
    for name in ("main.tf", "variables.tf", "outputs.tf", "monitoring.tf", "schema.yaml", ".terraform.lock.hcl"):
        data = (ROOT / "resource-manager" / name).read_bytes()
        if name.endswith(".tf"):
            data = data.replace(b"../terraform/modules/", b"./modules/")
        result[name] = data
    result["scripts/runner.py"] = (ROOT / "resource-manager/scripts/runner.py").read_bytes()
    for module in ("function", "iam", "observability"):
        for path in sorted((ROOT / "terraform/modules" / module).glob("*.tf")):
            result[f"modules/{module}/{path.name}"] = path.read_bytes()
    for folder in ("src", "functions/vault_rotation"):
        for path in sorted((ROOT / folder).rglob("*")):
            if path.is_file() and (path.suffix == ".py" or path.name == "Dockerfile"):
                result["bundle/" + path.relative_to(ROOT).as_posix()] = path.read_bytes()
    for name in ("pyproject.toml", "requirements.resolved.lock"):
        result["bundle/" + name] = (ROOT / name).read_bytes()
    return result


def package(output):
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(entries().items()):
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.external_attr = 0o100644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, data)
    print(output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "dist/resource-manager.zip")
    package(parser.parse_args().output)
