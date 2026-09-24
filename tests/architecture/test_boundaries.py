"""Layer boundaries, checked by reading imports rather than running code.

Each layer lists the internal packages it may import. A new import that crosses a
boundary fails here with the file, the line and the rule it broke. See
docs/project-structure.md for why each rule exists.

Parsed with ast so nothing is imported: importing core.config here would freeze the
settings before the API tests set their environment.
"""
from __future__ import annotations

import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

LAYERS = ["api", "core", "database", "dto", "errors", "integrations", "interfaces", "mapper",
          "policies", "security", "services", "utils"]
INTERNAL = {*LAYERS, "main"}

# Which internal packages each layer may import. Most specific key wins.
ALLOWED: dict[str, set[str]] = {
    "main": {"api", "core"},
    # routers: receive input, resolve auth and dependencies, call a service
    "api": {"api", "services", "dto", "security", "errors", "core"},
    # the composition root is the one place concrete persistence and integrations are named
    "api.dependencies": {"api", "services", "dto", "security", "errors", "core",
                         "database", "integrations", "interfaces"},
    "services": {"interfaces", "dto", "policies", "mapper", "errors", "utils"},
    "policies": {"dto", "interfaces", "errors"},
    "mapper": {"dto", "interfaces"},
    "dto": {"dto"},
    "interfaces": {"interfaces", "dto"},
    "database": {"database", "interfaces", "dto"},
    "integrations": {"interfaces", "dto", "core"},
    "security": {"security", "core", "errors"},
    "errors": {"errors"},
    "core": {"core"},
    "utils": set(),
}

# Third-party modules that belong to exactly one layer.
CONFINED = {
    "sqlite3": {"database"},
    "httpx": {"integrations"},
}

# Layers that must stay free of the web framework, so they can run without it.
FRAMEWORK_FREE = {"services", "policies", "mapper", "dto", "interfaces", "database", "integrations",
                  "utils", "core"}
FRAMEWORKS = {"fastapi", "starlette"}


def _modules():
    yield "main", ROOT / "main.py"
    for layer in LAYERS:
        for path in sorted((ROOT / layer).rglob("*.py")):
            rel = path.relative_to(ROOT).with_suffix("")
            parts = list(rel.parts)
            if parts[-1] == "__init__":
                parts = parts[:-1]
            yield ".".join(parts), path


def _package_of(module: str, path: Path) -> list[str]:
    parts = module.split(".")
    return parts if path.name == "__init__.py" else parts[:-1]


def _imports(module: str, path: Path):
    """(line, fully qualified module) for every import, relative ones resolved."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield node.lineno, alias.name
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = _package_of(module, path)
                base = base[:len(base) - (node.level - 1)] if node.level > 1 else base
                target = ".".join([*base, node.module] if node.module else base)
            else:
                target = node.module or ""
            yield node.lineno, target
            # "from errors import error_codes" names a submodule, not just the package
            for alias in node.names:
                yield node.lineno, f"{target}.{alias.name}"


def _rule_for(module: str) -> tuple[str, set[str]]:
    parts = module.split(".")
    for i in range(len(parts), 0, -1):
        key = ".".join(parts[:i])
        if key in ALLOWED:
            return key, ALLOWED[key]
    raise AssertionError(f"{module} is in no layer")


class LayerImports(unittest.TestCase):
    def test_every_import_stays_inside_its_layer_rules(self):
        broken = []
        for module, path in _modules():
            key, allowed = _rule_for(module)
            for line, target in _imports(module, path):
                top = target.split(".")[0]
                if top in INTERNAL and top not in allowed:
                    broken.append(f"{path.relative_to(ROOT)}:{line}  {key} -> {target}")
        self.assertEqual(broken, [], "layer boundary crossed:\n  " + "\n  ".join(broken))

    def test_mappers_see_only_the_record_interface(self):
        """Mappers convert shapes; a repository interface would let them fetch data."""
        broken = [f"{p.relative_to(ROOT)}:{ln}  {t}"
                  for m, p in _modules() if m.startswith("mapper")
                  for ln, t in _imports(m, p)
                  if t.startswith("interfaces") and t not in ("interfaces", "interfaces.record",
                                                              "interfaces.record.Record")]
        self.assertEqual(broken, [], "mapper imports a non-record interface:\n  " + "\n  ".join(broken))

    def test_confined_libraries_stay_in_their_layer(self):
        broken = []
        for module, path in _modules():
            layer = module.split(".")[0]
            for line, target in _imports(module, path):
                lib = target.split(".")[0]
                if lib in CONFINED and layer not in CONFINED[lib]:
                    broken.append(f"{path.relative_to(ROOT)}:{line}  {lib} used in {layer}")
        self.assertEqual(broken, [], "confined library escaped:\n  " + "\n  ".join(broken))

    def test_inner_layers_do_not_import_the_web_framework(self):
        broken = [f"{p.relative_to(ROOT)}:{ln}  {t}"
                  for m, p in _modules() if m.split(".")[0] in FRAMEWORK_FREE
                  for ln, t in _imports(m, p) if t.split(".")[0] in FRAMEWORKS]
        self.assertEqual(broken, [], "framework import in an inner layer:\n  " + "\n  ".join(broken))

    def test_the_old_app_package_is_gone_and_unreferenced(self):
        self.assertFalse((ROOT / "app").exists(), "app/ should have been removed")
        stale = [f"{p.relative_to(ROOT)}:{ln}  {t}"
                 for m, p in _modules() for ln, t in _imports(m, p)
                 if t == "app" or t.startswith("app.")]
        tests = [f"{p.relative_to(ROOT)}:{ln}  {t}"
                 for p in sorted((ROOT / "tests").rglob("*.py"))
                 for ln, t in _imports("tests", p) if t == "app" or t.startswith("app.")]
        self.assertEqual(stale + tests, [], "import of removed package:\n  " + "\n  ".join(stale + tests))


class NoQueriesAboveTheDatabase(unittest.TestCase):
    """SQL lives in database/repositories. Anything above reaches data through an interface."""

    def test_no_execute_calls_outside_the_database_layer(self):
        broken = []
        for module, path in _modules():
            if module.split(".")[0] == "database":
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Attribute) and node.attr in ("execute", "executescript",
                                                                     "executemany"):
                    broken.append(f"{path.relative_to(ROOT)}:{node.lineno}  .{node.attr}(")
        self.assertEqual(broken, [], "query outside database/:\n  " + "\n  ".join(broken))


class ServicesDependOnInterfaces(unittest.TestCase):
    def test_no_service_names_the_concrete_store(self):
        broken = []
        for path in sorted((ROOT / "services").rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Name) and node.id == "Store":
                    broken.append(f"{path.relative_to(ROOT)}:{node.lineno}")
        self.assertEqual(broken, [], "service refers to concrete Store:\n  " + "\n  ".join(broken))
