"""Contract test keeping docs/content-understanding-signals.md in sync with the CU v2 writer (#13902)."""

from __future__ import annotations

import ast
import inspect
import re
from pathlib import Path

from app.tasks.enrich_markets import enrich_cu_v2_profiles

REPO_ROOT = Path(__file__).resolve().parents[2]
DOC_PATH = REPO_ROOT / "docs" / "content-understanding-signals.md"

_CONSUMER_RE = re.compile(r"`((?:backend|frontend)/[^`:]+):([A-Za-z_][A-Za-z0-9_.]*)`")


def _extract_writer_profile_keys() -> set[str]:
    """Read exact dict keys written to `profile = { ... }` in enrich_cu_v2_profiles."""
    src = inspect.getsource(enrich_cu_v2_profiles)
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name) and target.id == "profile" and isinstance(node.value, ast.Dict):
                keys = set()
                for key_node in node.value.keys:
                    if isinstance(key_node, ast.Constant) and isinstance(key_node.value, str):
                        keys.add(key_node.value)
                return keys
    raise AssertionError("Could not locate `profile = { ... }` literal inside enrich_cu_v2_profiles")


def _parse_signal_table(markdown_text: str) -> dict[str, dict[str, str]]:
    rows: dict[str, dict[str, str]] = {}
    headers: list[str] | None = None
    for line in markdown_text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if headers is None:
            headers = cells
            continue
        if all(set(cell) <= {"-", ":"} for cell in cells):
            continue
        if len(cells) != len(headers):
            continue
        row = dict(zip(headers, cells, strict=True))
        field_key = row["Field"].strip("` ")
        rows[field_key] = row
    return rows


def _symbol_exists_in_file(rel_path: str, symbol: str) -> bool:
    file_path = REPO_ROOT / rel_path
    if not file_path.exists():
        return False
    src = file_path.read_text(encoding="utf-8")
    tree = ast.parse(src)
    parts = symbol.split(".")
    if len(parts) == 1:
        name = parts[0]
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name == name:
                return True
        return False
    cls_name, method_name = parts[0], parts[-1]
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == cls_name:
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == method_name:
                    return True
    return False


def _validate_signal_registry(writer_keys: set[str], rows: dict[str, dict[str, str]]) -> list[str]:
    errors: list[str] = []
    missing_from_doc = sorted(writer_keys - set(rows))
    if missing_from_doc:
        errors.append(f"Fields emitted by CU v2 writer missing from doc: {missing_from_doc}")
    extra_in_doc = sorted(set(rows) - writer_keys)
    if extra_in_doc:
        errors.append(f"Fields in doc not emitted by CU v2 writer: {extra_in_doc}")

    required_cols = (
        "Field", "Meaning", "Decided by", "Reader (`file:symbol`)",
        "What it changes for a reader", "Test", "Target", "Freshness",
    )
    for field_key, row in rows.items():
        for col in required_cols:
            if not row.get(col):
                errors.append(f"Row {field_key!r} is missing required column {col!r}")
        reader_text = row.get("Reader (`file:symbol`)", "")
        for rel_path, symbol in _CONSUMER_RE.findall(reader_text):
            if rel_path.endswith(".py") and not _symbol_exists_in_file(rel_path, symbol):
                errors.append(f"Row {field_key!r} names missing consumer {rel_path}:{symbol}")
    return errors


def test_every_writer_field_has_doc_row_and_every_named_consumer_exists():
    writer_keys = _extract_writer_profile_keys()
    rows = _parse_signal_table(DOC_PATH.read_text(encoding="utf-8"))
    errors = _validate_signal_registry(writer_keys, rows)
    assert errors == []


def test_negative_controls_catch_undocumented_field_and_phantom_consumer():
    writer_keys = _extract_writer_profile_keys()
    rows = _parse_signal_table(DOC_PATH.read_text(encoding="utf-8"))

    # Control 1: writer asks for a field with no row in the doc.
    errors_missing = _validate_signal_registry(writer_keys | {"phantom_score"}, rows)
    assert any("phantom_score" in err for err in errors_missing)

    # Control 2: doc row names a consumer function that does not exist.
    broken_rows = dict(rows)
    broken_rows["topic"] = {
        **rows["topic"],
        "Reader (`file:symbol`)": "`backend/app/routes/feed.py:nonexistent_cu_consumer_xyz`",
    }
    errors_consumer = _validate_signal_registry(writer_keys, broken_rows)
    assert any("nonexistent_cu_consumer_xyz" in err for err in errors_consumer)
