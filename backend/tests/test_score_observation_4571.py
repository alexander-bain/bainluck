"""#4571 — a live score states its own age, and who read it.

The defect class these guard: a stamp that exists but is written on the wrong
condition. Every score write site in this codebase is shaped
`if incoming != current: current = incoming`, so the natural place to put a
stamp is inside that guard — and there it answers "when did the score last
CHANGE", which is null for exactly the row #4571 was filed about (a 0-0 NFL
opener confirmed every 30s and changed never). A test that only asserts "the
stamp is set when the score moves" passes against that bug.

So the assertions below are deliberately weighted to the NO-CHANGE path, plus
an AST guard that the stamp calls are not nested inside the `!=` comparisons —
because a future edit that moves them back in would keep every value-level test
green.
"""

import ast
import inspect
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.utils.score_observation import (
    SCORE_OBSERVATION_SOURCES,
    clear_score_observation,
    score_observation_fields,
    stamp_score_observation,
)

BACKEND = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 9, 9, 20, 0, tzinfo=timezone.utc)


def _event(**kw):
    base = dict(
        id=1,
        status="live",
        home_score=None,
        away_score=None,
        score_source=None,
        score_observed_at=None,
        home_team_name="Home",
        away_team_name="Away",
        commence_time=NOW - timedelta(hours=1),
        completed_at=None,
        game_clock=None,
        period=None,
        broadcast_info=None,
        llm_importance=None,
        espn_id=None,
        commence_time_source=None,
    )
    base.update(kw)
    return SimpleNamespace(**base)


# ───────────────────────── the helper's contract ─────────────────────────


def test_stamp_records_source_and_observation_clock():
    ev = _event()
    assert stamp_score_observation(ev, source="espn", observed_at=NOW) is True
    assert ev.score_source == "espn"
    assert ev.score_observed_at == NOW


def test_stamp_uses_the_callers_clock_not_wall_clock():
    """The clock is the OBSERVATION's, not the row write's.

    A helper that fell back to `now()` would turn a read that lagged ten
    minutes into a fresh-looking stamp — the single failure the column exists
    to make visible.
    """
    stale = NOW - timedelta(minutes=10)
    ev = _event()
    stamp_score_observation(ev, source="statpal", observed_at=stale)
    assert ev.score_observed_at == stale


def test_stamp_without_a_clock_declines_rather_than_inventing_one():
    ev = _event()
    assert stamp_score_observation(ev, source="espn", observed_at=None) is False
    assert ev.score_source is None
    assert ev.score_observed_at is None


@pytest.mark.parametrize("bad", ["ESPN", "odds", "", "statpal_livescores", "mlb"])
def test_unknown_source_raises_rather_than_reaching_the_column(bad):
    """A typo'd source reads as a fourth writer in #4576's attribution query."""
    ev = _event()
    with pytest.raises(ValueError):
        stamp_score_observation(ev, source=bad, observed_at=NOW)
    assert ev.score_source is None


def test_every_permitted_source_fits_the_column():
    from app.models.models import Event

    width = Event.__table__.c.score_source.type.length
    for source in SCORE_OBSERVATION_SOURCES:
        assert len(source) <= width, f"{source!r} overflows score_source"


def test_clear_drops_both_halves():
    ev = _event(score_source="espn", score_observed_at=NOW)
    clear_score_observation(ev)
    assert ev.score_source is None and ev.score_observed_at is None


# ───────────────────────── the payload contract ─────────────────────────


def test_payload_is_present_only_for_an_unread_row():
    assert score_observation_fields(_event()) == {}


def test_payload_serves_both_keys_together():
    ev = _event(score_source="statpal", score_observed_at=NOW)
    assert score_observation_fields(ev) == {
        "score_source": "statpal",
        "score_observed_at": NOW.isoformat(),
    }


@pytest.mark.parametrize(
    "source,observed",
    [("espn", None), (None, NOW)],
)
def test_half_a_stamp_is_served_as_none(source, observed):
    """A source with no clock cannot be aged; a clock with no source cannot be
    attributed. Neither half is served alone."""
    ev = _event(score_source=source, score_observed_at=observed)
    assert score_observation_fields(ev) == {}


def test_payload_is_additive_and_touches_no_existing_key():
    ev = _event(score_source="espn", score_observed_at=NOW)
    assert set(score_observation_fields(ev)) == {
        "score_source",
        "score_observed_at",
    }


# ──────────────── the no-change path, at the real write sites ────────────────


@pytest.mark.asyncio
async def test_espn_stamps_a_score_it_did_not_change():
    """#4571's own specimen: 0-0, confirmed, unchanged.

    This is the assertion that fails if the stamp is ever moved inside the
    `!=` guard, which is where it naturally wants to live.
    """
    from app.utils.espn_helpers import update_event_fields_from_espn

    ev = _event(home_score=0, away_score=0)
    ee = SimpleNamespace(
        home_score=0, away_score=0, clock=None, status_detail=None,
        date=None, broadcasts=None, season_type=None, status="in",
        home_team=None, away_team=None,
    )

    class _Session:
        def add(self, _obj):
            pass

    await update_event_fields_from_espn(
        _Session(), ev, ee, set(), {}, observed_at=NOW,
    )

    assert ev.score_observed_at == NOW, (
        "a 0-0 game ESPN confirmed but did not change carries no age — "
        "the stamp is gated on change, not on observation (#4571)"
    )
    assert ev.score_source == "espn"


@pytest.mark.asyncio
async def test_espn_without_an_observation_clock_leaves_the_row_unstamped():
    from app.utils.espn_helpers import update_event_fields_from_espn

    ev = _event(home_score=0, away_score=0)
    ee = SimpleNamespace(
        home_score=0, away_score=0, clock=None, status_detail=None,
        date=None, broadcasts=None, season_type=None, status="in",
        home_team=None, away_team=None,
    )

    class _Session:
        def add(self, _obj):
            pass

    await update_event_fields_from_espn(_Session(), ev, ee, set(), {})
    assert ev.score_observed_at is None


@pytest.mark.asyncio
async def test_espn_does_not_stamp_a_row_it_read_no_score_for():
    """ESPN stating no score is not an observation of a score."""
    from app.utils.espn_helpers import update_event_fields_from_espn

    ev = _event()
    ee = SimpleNamespace(
        home_score=None, away_score=None, clock=None, status_detail=None,
        date=None, broadcasts=None, season_type=None, status="pre",
        home_team=None, away_team=None,
    )

    class _Session:
        def add(self, _obj):
            pass

    await update_event_fields_from_espn(
        _Session(), ev, ee, set(), {}, observed_at=NOW,
    )
    assert ev.score_source is None and ev.score_observed_at is None


# ─────────────────── the wiring, not just the logic ───────────────────


def _calls_in(tree):
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            fn = node.func
            name = getattr(fn, "id", None) or getattr(fn, "attr", None)
            if name in ("stamp_score_observation", "clear_score_observation"):
                yield node


def _module_tree(relpath):
    return ast.parse((BACKEND / relpath).read_text())


SITES = [
    "app/tasks/statpal_sync.py",
    "app/tasks/espn_sync.py",
    "app/utils/espn_helpers.py",
]


@pytest.mark.parametrize("relpath", SITES)
def test_every_writer_module_stamps(relpath):
    calls = list(_calls_in(_module_tree(relpath)))
    assert calls, f"{relpath} writes scores but never stamps one (#4571)"


@pytest.mark.parametrize("relpath", SITES)
def test_no_stamp_is_nested_inside_a_score_inequality(relpath):
    """The AST guard that pins WHERE the stamp lives.

    Every value-level test above still passes if a stamp is moved back inside
    `if incoming != current:` — the change path is exercised by both shapes.
    Only reading the tree catches the regression that matters, so this asserts
    no stamp call sits under an `if` whose test compares two score expressions
    with `!=`.
    """
    tree = _module_tree(relpath)
    offenders = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.If):
            continue
        test_src = ast.dump(node.test)
        if "NotEq" not in test_src or "score" not in test_src:
            continue
        for body_node in node.body:
            for call in _calls_in(ast.Module(body=[body_node], type_ignores=[])):
                offenders.append((relpath, getattr(call, "lineno", "?")))

    assert not offenders, (
        "score observation stamp nested inside a score `!=` guard "
        f"at {offenders} — it would answer 'when did the score last change', "
        "which is null for the 0-0 row #4571 was filed about"
    )


def test_espn_live_pass_hands_down_its_own_observation_clock():
    """`observed_at` defaults to None, so the feature is inert if the live
    caller stops passing it — and no value-level test would notice."""
    src = (BACKEND / "app/tasks/espn_sync.py").read_text()
    tree = ast.parse(src)

    passed = False
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if getattr(node.func, "id", None) != "update_fields_fn":
            continue
        assert any(k.arg == "observed_at" for k in node.keywords), (
            "the live ESPN pass calls update_fields_fn without observed_at — "
            "scores would be written with no age (#4571)"
        )
        passed = True

    assert passed, "update_fields_fn call site not found — did it get renamed?"


def test_the_clears_drop_the_stamp_with_the_score():
    """A stamp outliving its score is a fresh-looking age over a NULL."""
    src = (BACKEND / "app/tasks/espn_sync.py").read_text()
    tree = ast.parse(src)

    clears = [
        n.lineno
        for n in ast.walk(tree)
        if isinstance(n, ast.Call)
        and getattr(n.func, "id", None) == "clear_score_observation"
    ]
    nulls = [
        n.lineno
        for n in ast.walk(tree)
        if isinstance(n, ast.Assign)
        and isinstance(n.value, ast.Constant)
        and n.value.value is None
        and any(
            getattr(t, "attr", None) == "home_score" for t in n.targets
        )
    ]

    assert len(clears) >= len(nulls), (
        f"{len(nulls)} sites null home_score but only {len(clears)} clear the "
        "stamp — a surviving stamp ages a score that is gone (#4571)"
    )


def test_helper_stays_dependency_free():
    """Imported by two task modules and a helper; it must never be the reason
    one of them acquires a cycle (same discipline as sport_keys, gotcha #3)."""
    import app.utils.score_observation as mod

    src = inspect.getsource(mod)
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            assert not (node.module or "").startswith("app."), (
                f"score_observation imports {node.module} — keep it "
                "dependency-free"
            )
