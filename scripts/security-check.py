"""Guard delivery sources against accidental credential-bearing IaC/config and unsafe SQL execution."""
import ast
from pathlib import Path

root = Path(__file__).resolve().parents[1]
errors = []
for path in [*(root / "terraform").rglob("*.tf"), *(root / "resource-manager").rglob("*.tf")]:
    text = path.read_text()
    if path == root / "resource-manager/main.tf":
        # Explicit exception: reviewed managed-runner build and metadata-only linking.
        # Inputs are environment values; neither command interpolates shell arguments.
        allowed = ('command     = "python3 scripts/runner.py build"',
                   'command     = "python3 scripts/runner.py configure"')
        if text.count('provisioner "local-exec"') != 2 or not all(x in text for x in allowed):
            errors.append("Unexpected Resource Manager execution surface")
        text = text.replace('provisioner "local-exec"', 'provisioner "reviewed-helper"')
    for forbidden in ("secret_content", "secret_bundle", 'variable "password"', "local-exec", "remote-exec"):
        if forbidden in text:
            errors.append(f"{path.relative_to(root)}: forbidden Terraform secret/execution surface: {forbidden}")
for path in (root / "src").rglob("*.py"):
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if any(k.arg == "shell" and isinstance(k.value, ast.Constant) and k.value.value for k in node.keywords):
                errors.append(f"{path.name}:{node.lineno}: shell=True")
            if isinstance(node.func, ast.Attribute) and node.func.attr == "execute" and node.args:
                if isinstance(node.args[0], ast.JoinedStr):
                    errors.append(f"{path.name}:{node.lineno}: interpolated SQL")
for path in (root / "config.example.yaml",):
    if any(line.strip().startswith("password:") for line in path.read_text().splitlines()):
        errors.append(f"{path.name}: password field")
if errors:
    raise SystemExit("\n".join(errors))
print("Source security guards passed (not a substitute for dependency/container scanning).")
