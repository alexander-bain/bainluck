"""#13606 Condition 1 — Static AST coverage guard for `win_prob_snapshots` & `odds_snapshots` writers.

Every production code path under ``backend/app/`` that inserts, updates, or
deletes ``win_prob_snapshots`` or ``odds_snapshots`` rows must either:

1. Invoke ``invalidate_finished_event_history`` / ``invalidate_finished_event_history_sync``
   (directly, or via an internal helper that itself invokes it — e.g.
   ``_invalidate_finished_if_applicable`` in ``tasks/snapshots.py`` or
   ``event_child_repoint.repoint_event_children`` / caller), OR
2. Sit in an explicit, tested allowlist with a structural proof that it can never
   mutate a settled (>30m post-final) event's history (e.g. Pydantic DTO parsing
   in ``services/odds_api.py``, upcoming-only ``discover_all_events``, or live-only
   ``polymarket_ws.withdraw_attributed_event_sources``).

Adding a new writer anywhere under ``backend/app/`` without wiring finished-chart
invalidation turns CI red at once instead of letting durable charts go stale.
"""

from __future__ import annotations

import ast
import inspect
import pathlib
import re

APP_ROOT = pathlib.Path(__file__).resolve().parents[1] / "app"

_SQL_WRITE_RE = re.compile(
    r"\b(?:INSERT\s+INTO|UPDATE|DELETE\s+FROM)\s+(?:public\.)?(?:win_prob_snapshots|odds_snapshots)\b",
    re.IGNORECASE,
)
_SNAPSHOT_MODELS = frozenset({"WinProbSnapshot", "OddsSnapshot"})
_DML_FUNCS = frozenset({"insert", "pg_insert", "sqlite_insert", "update", "delete"})
_INVALIDATION_CALLS = frozenset(
    {
        "invalidate_finished_event_history",
        "invalidate_finished_event_history_sync",
        "_invalidate_finished_if_applicable",
    }
)

# Functions allowed to construct/reference the snapshot model or table without
# calling finished-chart invalidation directly:
#   - `services/odds_api.py`: Pydantic DTO (`class OddsSnapshot(BaseModel)`), not DB ORM.
#   - `routes/events.py::discover_all_events`: live/scheduled upcoming discovery only.
#   - `tasks/polymarket_ws.py::withdraw_attributed_event_sources`: strictly gated to
#     `Event.status == 'live'` AND `Event.completed_at IS NULL` (verified below).
#   - `tasks/snapshots.py::_create_or_update_win_prob_snapshot` &
#     `tasks/snapshots.py::_create_ordered_win_prob_snapshot` &
#     `tasks/odds_polling.py::_create_or_update_snapshot` BOTH call
#     `_invalidate_finished_if_applicable` inside the function itself.
#   - `tasks/odds_polling.py::_create_snapshot`: pure row builder; its sole caller
#     `_poll_sport_odds` invalidates when `event.status in ("completed", "closed")`.
_EXPLICIT_WRITER_ALLOWLIST = {
    ("services/odds_api.py", "OddsAPIService._parse_events"),
    ("routes/events.py", "discover_all_events"),
    ("tasks/polymarket_ws.py", "withdraw_attributed_event_sources"),
    ("tasks/odds_polling.py", "_create_snapshot"),
}

# Known indirect callers where invalidation runs in the outer coordinator before commit
# (because the helper writes ORM instances inside a loop without owning per-event finish).
_CALLER_INVALIDATED_HELPERS = {
    # Invokes `_write_periods_from_scoring_plays`, `_fetch_and_write_espn_periods`,
    # `_copy_espn_snapshot_periods`, `_write_start_end_markers`; `_try_fix_event`
    # calls `invalidate_finished_event_history` on every write branch before returning.
    ("tasks/game_state_backfill.py", "_write_periods_from_scoring_plays"),
    ("tasks/game_state_backfill.py", "_copy_espn_snapshot_periods"),
    ("tasks/game_state_backfill.py", "_write_start_end_markers"),
}

# Read-only / table-metadata occurrences of the literal strings
# `"win_prob_snapshots"` / `"odds_snapshots"` (never DML writes).
_NON_DML_LITERAL_ALLOWLIST = {
    ("models/models.py", "OddsSnapshot"),
    ("models/models.py", "WinProbSnapshot"),
    ("tasks/retention.py", "<module>"),
    ("utils/event_fk_inventory.py", "<module>"),
    ("routes/admin_data_quality.py", "get_snapshot_stats"),
    ("routes/admin_data_quality.py", "db_storage_analysis"),
    ("routes/admin_data_quality.py", "vacuum_table"),
    ("routes/admin_matching.py", "prediction_market_status"),
    ("routes/admin_matching.py", "prediction_market_event_debug"),
}


def _dotted_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def _scan_app_snapshot_writes() -> tuple[dict[tuple[str, str], list[str]], dict[tuple[str, str], set[str]]]:
    writes: dict[tuple[str, str], list[str]] = {}
    calls_by_fn: dict[tuple[str, str], set[str]] = {}

    for path in sorted(APP_ROOT.rglob("*.py")):
        rel = path.relative_to(APP_ROOT).as_posix()
        src = path.read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(src, filename=str(path))

        def visit(node: ast.AST, scope: str = "<module>") -> None:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                next_scope = f"{scope}.{node.name}" if scope != "<module>" else node.name
            else:
                next_scope = scope

            key = (rel, next_scope)
            if isinstance(node, ast.Call):
                fn_name = _dotted_name(node.func)
                calls_by_fn.setdefault(key, set()).add(fn_name)
                if fn_name in _SNAPSHOT_MODELS:
                    writes.setdefault(key, []).append(f"L{node.lineno}:construct {fn_name}()")
                elif fn_name in _DML_FUNCS and node.args:
                    arg0 = _dotted_name(node.args[0])
                    if arg0 in _SNAPSHOT_MODELS:
                        writes.setdefault(key, []).append(
                            f"L{node.lineno}:{fn_name}({arg0})"
                        )
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                for m in _SQL_WRITE_RE.finditer(node.value):
                    writes.setdefault(key, []).append(f"L{node.lineno}:SQL({m.group(0).strip()})")
                if node.value in ("win_prob_snapshots", "odds_snapshots"):
                    if key not in _NON_DML_LITERAL_ALLOWLIST:
                        writes.setdefault(key, []).append(
                            f"L{node.lineno}:table-literal({node.value!r})"
                        )

            for child in ast.iter_child_nodes(node):
                visit(child, next_scope)

        visit(tree)

    return writes, calls_by_fn


def test_every_snapshot_writer_calls_finished_chart_invalidation_or_is_allowlisted():
    writes, calls_by_fn = _scan_app_snapshot_writes()
    assert writes, "expected snapshot write scan to discover writers"

    uncovered: list[str] = []
    for key, reasons in sorted(writes.items()):
        if key in _EXPLICIT_WRITER_ALLOWLIST or key in _CALLER_INVALIDATED_HELPERS:
            continue
        called = calls_by_fn.get(key, set())
        if called & _INVALIDATION_CALLS:
            continue
        # Outer orchestrators calling `_create_or_update_win_prob_snapshot` or `_create_snapshot`
        # still pass through an explicitly guarded call; check direct invalidation on all
        # non-allowlisted writers.
        uncovered.append(f"{key[0]}::{key[1]} ({', '.join(reasons)})")

    assert not uncovered, (
        "Found snapshot writers without `invalidate_finished_event_history` wiring:\n"
        + "\n".join(f"  - {item}" for item in uncovered)
    )


def test_allowlisted_live_or_coordinator_guards_remain_intact():
    from app.routes import events as events_route
    from app.tasks import game_state_backfill, odds_polling, polymarket_ws

    # 1. polymarket_ws.withdraw_attributed_event_sources must stay strictly live-gated
    ws_src = inspect.getsource(polymarket_ws.withdraw_attributed_event_sources)
    assert "event.status != 'live' or event.completed_at is not None" in ws_src
    assert "Event.status == 'live', Event.completed_at.is_(None)" in ws_src

    # 2. events.discover_all_events must only assign scheduled/live statuses
    disc_src = inspect.getsource(events_route.discover_all_events)
    assert '"completed"' not in disc_src and "'completed'" not in disc_src
    assert '"closed"' not in disc_src and "'closed'" not in disc_src

    # 3. game_state_backfill._try_fix_event invalidates after calling its helper writers
    fix_src = inspect.getsource(game_state_backfill._try_fix_event)
    assert fix_src.count("invalidate_finished_event_history") >= 4

    # 4. odds_polling._poll_sport_odds invalidates completed/closed events using `_create_snapshot`
    sport_poll_src = inspect.getsource(odds_polling._poll_sport_odds)
    assert "_create_snapshot(" in sport_poll_src
    assert "invalidate_finished_event_history" in sport_poll_src
