"""Dependency direction: a module may import its own top-level package or strictly lower layers."""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "src" / "kinolog"

# Lower number = lower layer. Packages absent from this map (or not yet created) are ignored.
LAYERS = {
    "config": 0,
    "domain": 0,
    "store": 1,
    "ingest": 2,  # becomes `sources` in the sources phase
    "sources": 2,
    "index": 2,
    "retrieval": 3,
    "rag": 4,
    "taste": 4,
    "features": 5,
    "pipeline": 6,
    "services": 6,
    "eval": 7,
    "interfaces": 8,
    "__main__": 9,  # entry point: sits above interfaces and may import them
}


def _top(module: str) -> str | None:
    parts = module.split(".")
    if parts[0] != "kinolog" or len(parts) < 2:
        return None
    return parts[1]


def _imported_modules(path: Path) -> list[tuple[int, str]]:
    """Every kinolog module imported anywhere in the file, including inside functions."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.append((node.lineno, alias.name))
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                continue  # the codebase uses absolute imports only; test_no_relative_imports
            if node.module == "kinolog":
                found.extend((node.lineno, f"kinolog.{a.name}") for a in node.names)
            elif node.module:
                found.append((node.lineno, node.module))
    return [(line, m) for line, m in found if m == "kinolog" or m.startswith("kinolog.")]


def _source_files():
    return sorted(p for p in ROOT.rglob("*.py") if "__pycache__" not in p.parts)


def _own_top(path: Path) -> str:
    rel = path.relative_to(ROOT)
    return rel.parts[0] if len(rel.parts) > 1 else rel.stem


def test_no_relative_imports():
    bad = []
    for path in _source_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        bad += [f"{path.relative_to(ROOT)}:{n.lineno}" for n in ast.walk(tree)
                if isinstance(n, ast.ImportFrom) and n.level]
    assert not bad, "relative imports are not allowed:\n" + "\n".join(bad)


def test_every_package_is_in_the_layer_map():
    """A new top-level package must be given a layer, or the check below silently skips it."""
    tops = {_own_top(p) for p in _source_files()}
    tops.discard("__init__")
    assert tops <= set(LAYERS), f"add to LAYERS: {sorted(tops - set(LAYERS))}"


def test_layering():
    violations = []
    for path in _source_files():
        own = _own_top(path)
        if own not in LAYERS:
            continue
        for lineno, module in _imported_modules(path):
            target = _top(module)
            if target is None or target not in LAYERS or target == own:
                continue
            if LAYERS[target] >= LAYERS[own]:
                violations.append(
                    f"{path.relative_to(ROOT)}:{lineno} imports {module} "
                    f"({own}[{LAYERS[own]}] -> {target}[{LAYERS[target]}])"
                )
    assert not violations, "layering violations:\n" + "\n".join(violations)
