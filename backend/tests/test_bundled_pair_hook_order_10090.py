"""#10090 — the bundled Challenger pair's current-book proof is installed before
any path can refresh (lane1b's attempt181 port hazard P1).

The Kalshi consumer installs four readers on its blend refresher: the proof
requirement, the midpoint and primary-price readers, and the landed
primary-quote reader. A refresh that runs without them stamps the bundled pair
with no book proof. In attempt190 they were assigned after `adopt_handed_off`
and every nested refresh path; safe there only because nothing refreshed
before the flush loop started. The port installs them first, so a later
early path (a live-first startup, a refresh of adopted handoff events) cannot
run unproven.
"""
import ast
from pathlib import Path

import app.tasks.kalshi_ws as consumer
from app.tasks.live_blend_refresh import LiveBlendRefresher

HOOKS = {
    "require_current_book_proof",
    "current_book_midpoint",
    "current_book_primary_price",
    "current_primary_input",
    # #11317 P2: the refused-pair parking reader rides the same install.
    "current_book_signature",
}


def _run_body():
    tree = ast.parse(Path(consumer.__file__).read_text())
    return next(
        node for node in tree.body
        if isinstance(node, ast.AsyncFunctionDef)
        and node.name == "_run_kalshi_ws_consumer"
    )


def _hook_lines(run):
    lines = {}
    for stmt in run.body:
        if not isinstance(stmt, ast.Assign):
            continue
        for target in stmt.targets:
            if (isinstance(target, ast.Attribute)
                    and isinstance(target.value, ast.Name)
                    and target.value.id == "blend_refresher"
                    and target.attr in HOOKS):
                lines[target.attr] = stmt.lineno
    return lines


def _first_line(run, predicate):
    hits = [node.lineno for node in ast.walk(run) if predicate(node)]
    return min(hits) if hits else None


def test_every_proof_reader_is_installed_once_at_the_top_level():
    run = _run_body()
    lines = _hook_lines(run)
    assert set(lines) == HOOKS
    installs = [
        node for node in ast.walk(run)
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Attribute) and t.attr in HOOKS
            and isinstance(t.value, ast.Name) and t.value.id == "blend_refresher"
            for t in node.targets
        )
    ]
    assert len(installs) == len(HOOKS), "installed once, not re-bound later"


def test_proof_readers_are_installed_before_adoption_and_every_refresh_path():
    run = _run_body()
    installed = max(_hook_lines(run).values())

    def calls(name):
        return lambda node: (
            isinstance(node, ast.Call)
            and isinstance(node.func, (ast.Name, ast.Attribute))
            and (node.func.id if isinstance(node.func, ast.Name)
                 else node.func.attr) == name
        )

    adopted = _first_line(run, calls("adopt_handed_off"))
    assert adopted is not None and installed < adopted
    for name in ("refresh", "refresh_pending", "adopt_pending", "admit_fresh"):
        first = _first_line(run, calls(name))
        assert first is not None, name
        assert installed < first, f"{name} at line {first} precedes the proof"


def test_the_readers_iterate_a_client_list_bound_before_them():
    run = _run_body()
    bound = [
        stmt.lineno for stmt in run.body
        if isinstance(stmt, ast.AnnAssign)
        and isinstance(stmt.target, ast.Name) and stmt.target.id == "game_clients"
    ]
    readers = [
        stmt.lineno for stmt in run.body
        if isinstance(stmt, ast.FunctionDef) and stmt.name in {
            "steady_book_midpoint", "steady_book_primary_price",
            "steady_primary_input", "steady_book_signature",
        }
    ]
    assert len(bound) == 1 and len(readers) == 4
    assert bound[0] < min(readers)
    assert bound[0] < max(_hook_lines(run).values())


def test_a_refresher_without_an_owner_requires_no_book_proof():
    # Polymarket and the poll path construct their own refresher; the proof is
    # off unless the Kalshi WS owner installs it.
    refresher = LiveBlendRefresher("polymarket")
    assert refresher.require_current_book_proof is False
    assert refresher.current_book_midpoint is None
    assert refresher.current_book_primary_price is None
    assert refresher.current_primary_input is None
    assert refresher.current_book_signature is None
