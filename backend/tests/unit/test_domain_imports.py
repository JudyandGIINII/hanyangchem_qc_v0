import ast
import sys
from pathlib import Path


def test_domain_has_no_infrastructure_imports() -> None:
    domain_root = Path(__file__).resolve().parents[2] / "src" / "hyc_domain"
    allowed = sys.stdlib_module_names | {"hyc_domain"}
    for path in domain_root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported = {alias.name.split(".")[0] for alias in node.names}
                assert imported <= allowed, (path, imported - allowed)
            if isinstance(node, ast.ImportFrom) and node.module:
                imported = node.module.split(".")[0]
                assert node.level > 0 or imported in allowed, (path, imported)
