"""Queue 368 — a Redis-overridable threshold must reach the VERDICT, not just the
export. Instance 4 of the frozen-config family; this file is the last one.

The family, stated once:

    THRESHOLD = 48.0                      # module global, overridable from Redis

    def _load_overrides():                # runs at the start of every sentinel run
        globals()["THRESHOLD"] = <redis>

    def check(..., bar: float = THRESHOLD):   # <-- BOUND ONCE, AT IMPORT
        ...

Python evaluates a default argument exactly once, when the ``def`` executes. So
``_load_overrides()`` rebinds the global and the check keeps grading against the
value that was compiled into its signature. The *export* block reads the global
at call time and therefore reports the NEW number — so an operator raising a bar
sees their own value echoed back and gets graded on the old one. It is not a
silent failure; it is worse, a confirming one.

Instances: flow_sentinel (UX-P079, three rails), board_sentinel (C-IF-1, this
queue, three rails). The other two sentinels were clean when swept.

So this guard is deliberately NOT a list of the known offenders. It discovers
every ``_load_overrides``-managed name in ``app/tasks/`` and asserts none of them
is reachable only through a frozen default. A sentinel added next year is
covered on the day it lands.
"""

import ast
import pathlib

import pytest

TASKS_DIR = pathlib.Path(__file__).resolve().parents[1] / "app" / "tasks"


def _board_sentinel_module():
    """The MODULE, not the Celery task proxy.

    ``from app.tasks import board_sentinel`` resolves to the registered task of
    the same name (``app/tasks/__init__.py`` exports it), which has none of the
    module's globals on it. Reaching through ``sys.modules`` is the only way to
    get the object whose globals ``_load_overrides`` rebinds — and it is the same
    object the running sentinel uses.
    """
    import importlib
    import sys

    importlib.import_module("app.tasks.board_sentinel")
    return sys.modules["app.tasks.board_sentinel"]


def _override_managed_names(tree: ast.Module) -> set[str]:
    """Globals that ``_load_overrides`` rebinds from Redis.

    Read two ways and unioned, because the two idioms in the tree disagree: some
    modules declare ``global A, B`` and some rely on ``globals()[name] = ...``
    with the name only ever appearing as a string in the key table. A guard that
    knew about one idiom would pass on a module written in the other.
    """
    names: set[str] = set()
    for node in ast.walk(tree):
        if not (isinstance(node, ast.FunctionDef) and node.name == "_load_overrides"):
            continue
        for child in ast.walk(node):
            if isinstance(child, ast.Global):
                names.update(child.names)
            elif isinstance(child, ast.Constant) and isinstance(child.value, str):
                # The key tables carry ("redis:key", "GLOBAL_NAME", cast).
                if child.value.isupper() and child.value.isidentifier():
                    names.add(child.value)
    return names


def _frozen_defaults(tree: ast.Module, managed: set[str]) -> list[tuple[int, str, str]]:
    """Every function whose default argument reads a managed global by name."""
    out: list[tuple[int, str, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        defaults = list(node.args.defaults) + [d for d in node.args.kw_defaults if d]
        for default in defaults:
            for sub in ast.walk(default):
                if isinstance(sub, ast.Name) and sub.id in managed:
                    out.append((node.lineno, node.name, sub.id))
    return out


def _modules_with_overrides() -> list[pathlib.Path]:
    found = []
    for path in sorted(TASKS_DIR.glob("*.py")):
        if "def _load_overrides" in path.read_text():
            found.append(path)
    return found


def test_the_sweep_finds_the_modules_it_claims_to_cover():
    """Premise check: if the discovery returns nothing, every assertion below is
    vacuously true and the guard is decoration."""
    modules = _modules_with_overrides()
    assert len(modules) >= 4, [m.name for m in modules]
    names = {m.name for m in modules}
    assert {"board_sentinel.py", "flow_sentinel.py"} <= names


@pytest.mark.parametrize(
    "path", _modules_with_overrides(), ids=lambda p: p.name
)
def test_no_overridable_threshold_is_frozen_in_a_default_arg(path):
    tree = ast.parse(path.read_text())
    managed = _override_managed_names(tree)
    assert managed, f"{path.name} defines _load_overrides but manages no names"

    offenders = _frozen_defaults(tree, managed)
    assert not offenders, (
        f"{path.name}: these thresholds are Redis-overridable but bound into a "
        f"default argument at import, so the override reaches the exported "
        f"`thresholds` block and never the verdict. Resolve at call time instead "
        f"(`param: T | None = None` then `param = GLOBAL if param is None else "
        f"param`). Offenders (line, function, global): {offenders}"
    )


class TestTheOverrideActuallyReachesTheBoardVerdict:
    """The AST guard proves the shape. These prove the behaviour, on the module
    that was broken — a structural rule nobody has watched change a verdict is
    a rule about syntax."""

    def test_inbox_triage_override_changes_the_finding(self, monkeypatch):
        from datetime import datetime, timedelta, timezone

        bs = _board_sentinel_module()

        now = datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc)
        seen = now - timedelta(hours=60)
        issues = [{"number": 1, "title": "t", "column": bs.INBOX_COLUMN, "labels": []}]

        # Default bar 48h → 60h of residence is stale.
        monkeypatch.setattr(bs, "INBOX_TRIAGE_HOURS", 48.0)
        assert bs.check_stale_inbox(issues, now, {1: seen}) != []

        # Operator raises the bar past the residence → no longer a finding.
        # Before the fix this still fired: the signature held 48.0.
        monkeypatch.setattr(bs, "INBOX_TRIAGE_HOURS", 72.0)
        assert bs.check_stale_inbox(issues, now, {1: seen}) == []

    def test_template_p1_cap_override_changes_the_finding(self, monkeypatch):
        bs = _board_sentinel_module()

        # 6 intake issues, 4 of them p1 → share 0.667.
        issues = [
            {
                "number": n,
                "title": "t",
                "column": bs.INBOX_COLUMN,
                "labels": ["alert-intake"] + (["priority:p1"] if n <= 4 else []),
            }
            for n in range(1, 7)
        ]
        if not bs._is_intake(issues[0]):
            pytest.skip("intake predicate shape changed — fixture no longer valid")

        monkeypatch.setattr(bs, "TEMPLATE_P1_SHARE_CAP", 0.35)
        assert bs.check_template_p1_share(issues) != []

        monkeypatch.setattr(bs, "TEMPLATE_P1_SHARE_CAP", 0.90)
        assert bs.check_template_p1_share(issues) == []

    def test_explicit_argument_still_wins(self, monkeypatch):
        """Call-time resolution must not swallow an explicitly passed value —
        the tests that inject a bar directly are the sentinel's own harness."""
        from datetime import datetime, timedelta, timezone

        bs = _board_sentinel_module()

        now = datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc)
        seen = now - timedelta(hours=60)
        issues = [{"number": 1, "title": "t", "column": bs.INBOX_COLUMN, "labels": []}]

        monkeypatch.setattr(bs, "INBOX_TRIAGE_HOURS", 1.0)
        assert bs.check_stale_inbox(issues, now, {1: seen}, max_hours=999.0) == []

    def test_graded_bar_equals_exported_bar(self, monkeypatch):
        """The R4 invariant, applied here: the number reported must be the number
        compared against. The finding carries `cap`; assert it is the live one."""
        bs = _board_sentinel_module()

        issues = [
            {
                "number": n,
                "title": "t",
                "column": bs.INBOX_COLUMN,
                "labels": ["alert-intake"] + (["priority:p1"] if n <= 5 else []),
            }
            for n in range(1, 7)
        ]
        monkeypatch.setattr(bs, "TEMPLATE_P1_SHARE_CAP", 0.40)
        findings = bs.check_template_p1_share(issues)
        assert findings and findings[0]["cap"] == 0.40
