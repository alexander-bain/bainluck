"""LAT-P241/#3399 — a shed BONUS lane must not make a typeahead answer uncacheable.

THE DEFECT. `typeahead_search` had ONE degraded flag, `_ta_degraded`, set from
two places that lose very different things:

  * the outcome-NAME arm shedding — a bonus lane; the dropdown still answers
    with its market name, ticker and alias matches (the route's own log line
    says so); and
  * the futures query timing out — the whole futures stage is gone.

`if not _ta_degraded ...` gated the cache write, so the first case made an entry
permanently uncacheable. Measured on production, `debug_timing=1` (a real
miss-path build), 5 trials per term:

    term           shed   arm ms                       total ms
    sta            5/5    2032 2038 2026 2014 2042     5034-7845
    stan           5/5    2054 5648 2034 2026 2034     4214-7860
    ben            5/5    2021 2045 2030 2032 2021     5133-6733
    red            5/5    2264 2007 2203 2120 2043     5931-7243
    stanley cup    0/5      71  134   96   71  102     1408-1741
    carlos         0/5     798  726 1154  519 1235     2196-3701
    alc            0/5    1286  755 1017  648  567     2264-3883

5/5 or 0/5, never in between. The shed is a property of the TERM — its trigrams
are extractable but not selective, and selectivity lives in the data — so there
was no fuller answer for the cached one to displace. The warmer rebuilt those
terms ~88 times an hour, counted each as its own `no_write` DEFECT, and no user
ever received a warm answer for them.

WHAT THIS FILE PINS, and the second one matters as much as the first:

 1. the arm-shed branch sets the BONUS flag and NOT the futures-stage flag;
 2. the futures-stage timeout STILL sets `_ta_degraded` and is STILL never
    cached — LAT-P007 is narrowed, not weakened;
 3. the cache-write gate reads `_ta_degraded` and does NOT read the bonus flag.

WHY AST AND NOT `in src`. A substring guard over a 1,000-line function is
defeated by a line break, a rename, or a comment that happens to contain the
string it looks for — and this file's whole subject is a comment block that
mentions both flag names many times. Every assertion below is made against
parsed syntax, and `TestTheGuardIsArmed` fails if the nodes it needs stop being
findable at all, so a rename cannot turn this suite green by making it vacuous.
"""

from __future__ import annotations

import ast
import inspect
import pathlib

import pytest

ROUTE = pathlib.Path(
    inspect.getsourcefile(__import__("app.routes.events", fromlist=["x"]))
)
TREE = ast.parse(ROUTE.read_text())

SHED_FLAG = "_ta_outcome_arm_shed"
STAGE_FLAG = "_ta_degraded"


def _typeahead_fn() -> ast.AsyncFunctionDef:
    for node in ast.walk(TREE):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "typeahead_search":
            return node
    raise AssertionError("typeahead_search not found — this suite is vacuous")


def _assigned_names(node: ast.AST) -> set[str]:
    """Every bare name assigned anywhere under `node`."""
    out: set[str] = set()
    for n in ast.walk(node):
        if isinstance(n, ast.Assign):
            for t in n.targets:
                if isinstance(t, ast.Name):
                    out.add(t.id)
        elif isinstance(n, (ast.AugAssign, ast.AnnAssign)) and isinstance(n.target, ast.Name):
            out.add(n.target.id)
    return out


def _marks(node: ast.AST) -> set[str]:
    """Every string literal passed to `_ta_mark(...)` under `node`."""
    out: set[str] = set()
    for n in ast.walk(node):
        if (isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                and n.func.id == "_ta_mark" and n.args
                and isinstance(n.args[0], ast.Constant)):
            out.add(n.args[0].value)
    return out


def _branch_marking(label: str) -> ast.AST:
    """The smallest `if`/`except` body under `typeahead_search` that marks `label`."""
    best = None
    for n in ast.walk(_typeahead_fn()):
        if not isinstance(n, (ast.If, ast.ExceptHandler)):
            continue
        body = ast.Module(body=n.body, type_ignores=[])
        if label in _marks(body):
            size = len(list(ast.walk(body)))
            if best is None or size < best[0]:
                best = (size, body)
    assert best is not None, f"no branch marks {label!r} — this suite is vacuous"
    return best[1]


def _cache_write_gate() -> ast.If:
    """The `if` whose body performs the typeahead `setex`."""
    for n in ast.walk(_typeahead_fn()):
        if not isinstance(n, ast.If):
            continue
        for c in ast.walk(ast.Module(body=n.body, type_ignores=[])):
            if (isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute)
                    and c.func.attr == "setex"):
                return n
    raise AssertionError("no setex found in typeahead_search — this suite is vacuous")


def _names_read(node: ast.AST) -> set[str]:
    return {n.id for n in ast.walk(node) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}


class TestTheGuardIsArmed:
    """Non-vacuity. Every locator above must actually find something."""

    def test_the_route_function_is_found(self):
        assert _typeahead_fn().name == "typeahead_search"

    def test_both_shed_branches_are_found(self):
        assert _marks(_branch_marking("futures_outcome_arm_SHED"))
        assert _marks(_branch_marking("futures_query_TIMED_OUT"))

    def test_the_cache_write_is_found(self):
        assert isinstance(_cache_write_gate(), ast.If)

    def test_both_flags_are_initialised_in_the_route(self):
        """A flag that is only ever set inside a branch is `NameError` on the
        path that skips it — the bug this pairing exists to make impossible."""
        top = {t.id
               for stmt in _typeahead_fn().body if isinstance(stmt, ast.Assign)
               for t in stmt.targets if isinstance(t, ast.Name)}
        assert {SHED_FLAG, STAGE_FLAG} <= top, sorted(top & {SHED_FLAG, STAGE_FLAG})


class TestTheBonusLaneIsNotTheFuturesStage:
    def test_the_arm_shed_sets_its_own_flag(self):
        assert SHED_FLAG in _assigned_names(_branch_marking("futures_outcome_arm_SHED"))

    def test_the_arm_shed_does_not_mark_the_answer_degraded(self):
        """THE FIX. Setting `_ta_degraded` here is what made `sta`, `stan`,
        `ben` and `red` permanently uncacheable."""
        assigned = _assigned_names(_branch_marking("futures_outcome_arm_SHED"))
        assert STAGE_FLAG not in assigned, (
            f"the bonus outcome-name lane assigns {STAGE_FLAG} again — that is "
            "the conflation LAT-P241 removed, and it re-breaks #3399"
        )

    def test_the_futures_stage_timeout_still_marks_the_answer_degraded(self):
        """LAT-P007 is NARROWED, not weakened. Losing the whole futures stage is
        the sticky-wrong-answer case and must stay uncacheable."""
        assert STAGE_FLAG in _assigned_names(_branch_marking("futures_query_TIMED_OUT"))

    def test_the_futures_stage_timeout_does_not_set_only_the_bonus_flag(self):
        assigned = _assigned_names(_branch_marking("futures_query_TIMED_OUT"))
        assert not (SHED_FLAG in assigned and STAGE_FLAG not in assigned), (
            "a futures-stage timeout downgraded to the bonus flag would make the "
            "whole-stage loss cacheable — the inverse of this fix, and worse"
        )


class TestTheCacheGateReadsTheRightFlag:
    def test_the_gate_reads_the_futures_stage_flag(self):
        assert STAGE_FLAG in _names_read(_cache_write_gate().test)

    def test_the_gate_does_not_read_the_bonus_flag(self):
        assert SHED_FLAG not in _names_read(_cache_write_gate().test), (
            "gating the write on the bonus lane is exactly the defect #3399 "
            "reports; a shed arm must not stop the answer being cached"
        )

    def test_the_gate_still_excludes_both_debug_modes(self):
        """LAT-P050 and LAT-P054, unchanged: a debug body must never be served
        to a normal user from a warm entry."""
        read = _names_read(_cache_write_gate().test)
        assert {"debug_evidence", "debug_timing"} <= read, sorted(read)


class TestTheShedStateIsReportable:
    """The residual risk this change accepts is a term that sheds
    INTERMITTENTLY. That has to be measurable, not merely loggable."""

    @staticmethod
    def _dicts_holding_the_flags() -> list[ast.Dict]:
        out = []
        for n in ast.walk(_typeahead_fn()):
            if isinstance(n, ast.Dict) and any(
                isinstance(v, ast.Name) and v.id in (SHED_FLAG, STAGE_FLAG)
                for v in n.values
            ):
                out.append(n)
        return out

    def test_both_flags_are_reported_under_keys_of_their_own(self):
        keys = {k.value
                for d in self._dicts_holding_the_flags()
                for k, v in zip(d.keys, d.values)
                if isinstance(k, ast.Constant) and isinstance(v, ast.Name)
                and v.id in (SHED_FLAG, STAGE_FLAG)}
        assert len(keys) == 2, (
            "both shed flags must be reported under a key of their own, so a "
            "probe need not infer the state by substring-matching stage labels "
            f"— which silently answers 'no' the day a label is renamed. Got: {keys}"
        )

    def test_the_flags_do_not_live_in_the_numeric_timing_map(self):
        """CERT-2032 follow-up `TYPEAHEAD-DEBUG-STATE-OUTSIDE-TIMING-MAP`.

        Every other entry in `debug_timing` is a stage duration in milliseconds
        and `total_ms` is a SUM over that map. In Python `True` sums as 1, so a
        boolean in there is a reader waiting to add a flag to a millisecond
        total. Two facts of different kinds do not share a dict.
        """
        for d in self._dicts_holding_the_flags():
            literal_keys = {k.value for k in d.keys
                            if isinstance(k, ast.Constant) and isinstance(k.value, str)}
            assert "total_ms" not in literal_keys, (
                "a shed BOOLEAN is in the same dict as `total_ms`, which is a "
                "sum over the millisecond stage map — give it its own key"
            )
            # Nor may it ride in via `**_ta_stage_ms` alongside the booleans.
            assert not any(k is None for k in d.keys), (
                "a shed boolean shares a dict with a `**` spread of the stage "
                "timings — same mixed schema, one level less visible"
            )


@pytest.mark.parametrize("flag", [SHED_FLAG, STAGE_FLAG])
def test_each_flag_is_actually_read_somewhere(flag):
    """A flag nobody reads is a comment with a syntax error's blast radius."""
    fn = _typeahead_fn()
    reads = [n for n in ast.walk(fn)
             if isinstance(n, ast.Name) and n.id == flag and isinstance(n.ctx, ast.Load)]
    assert reads, f"{flag} is assigned but never read"
