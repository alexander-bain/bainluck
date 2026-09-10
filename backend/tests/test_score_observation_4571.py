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
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.utils.score_observation import (
    SCORE_OBSERVATION_SOURCES,
    SCORE_SOURCE_ODDS,
    clear_score_observation,
    score_observation_fields,
    score_observation_values,
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
            if name in (
                "stamp_score_observation",
                "clear_score_observation",
                # The Core-UPDATE spelling. `_poll_all_odds` writes scores
                # through `Event.__table__.update()`, so it cannot assign an ORM
                # attribute (gotcha #5) — it merges columns instead. Same rule,
                # different verb, and it must be held to both guards below.
                "score_observation_values",
            ):
                yield node


def _module_tree(relpath):
    return ast.parse((BACKEND / relpath).read_text())


SITES = [
    "app/tasks/statpal_sync.py",
    "app/tasks/espn_sync.py",
    "app/utils/espn_helpers.py",
    # CERT-2460: missed by the first cut of #4571 because the issue's scope line
    # named "MLB Stats API" (which writes no score at all) and not this — an
    # active production writer, every ~5.5 min.
    "app/tasks/odds_polling.py",
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


# ────────── the payload wiring, proved on the real formatter's output ──────────
#
# CERT-2444's follow-up on #4582 asked for exactly this distinction: an AST guard
# proving "both operations occur" is weaker than reading the value the formatter
# actually returns. These call `_format_event` and assert on its dict.


def _formattable_event(**kw):
    """The minimum `_format_event` needs. It degrades on missing optional
    attributes (logging a warning), which is why a namespace suffices."""
    base = dict(
        id=1,
        home_team_name="Home",
        away_team_name="Away",
        commence_time=NOW - timedelta(hours=1),
        completed_at=None,
        status="live",
        home_score=3,
        away_score=1,
        score_source=None,
        score_observed_at=None,
        sport=SimpleNamespace(key="baseball_mlb", name="MLB"),
        box_score_data=None,
        win_probability_sources={},
        external_id="x",
    )
    base.update(kw)
    return SimpleNamespace(**base)


def test_format_event_serves_the_stamp_it_holds():
    from app.routes.events import _format_event

    out = _format_event(
        _formattable_event(score_source="statpal", score_observed_at=NOW)
    )
    assert out["score_source"] == "statpal"
    assert out["score_observed_at"] == NOW.isoformat()


def test_format_event_omits_the_stamp_on_an_unread_row():
    """Present-only on the real formatter, not just in the helper — two null
    keys on every row of a 500-row single-sport list are bytes that can never
    carry an answer."""
    from app.routes.events import _format_event

    out = _format_event(_formattable_event())
    assert "score_source" not in out
    assert "score_observed_at" not in out


def test_format_event_still_serves_the_score_itself():
    """The stamp is ADDITIVE (#4571 scope item 2): no existing key changes
    shape, name or meaning, so no client is forced to cut over."""
    from app.routes.events import _format_event

    without = _format_event(_formattable_event())
    with_stamp = _format_event(
        _formattable_event(score_source="espn", score_observed_at=NOW)
    )

    assert with_stamp["home_score"] == without["home_score"] == 3
    assert with_stamp["away_score"] == without["away_score"] == 1
    assert set(without).issubset(set(with_stamp))
    assert set(with_stamp) - set(without) == {
        "score_source",
        "score_observed_at",
    }


def test_helper_stays_dependency_free():
    """Imported by two task modules and a helper; it must never be the reason
    one of them acquires a cycle (same discipline as sport_keys, gotcha #3).

    Read from the path like the AST guards above rather than re-importing the
    module under a second name: `from … import` at the top of this file plus an
    `import …` here is the same module bound two ways, which CodeQL flags
    (`py/import-and-import-from`, notice level) and which the rest of this file
    has no need of.
    """
    tree = _module_tree("app/utils/score_observation.py")
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            assert not (node.module or "").startswith("app."), (
                f"score_observation imports {node.module} — keep it "
                "dependency-free"
            )


# ══ CERT-2460 REPAIR — 4571-ODDS-API-SCORE-WRITER-STAMPS-THE-READ ════════════
#
# The first cut of #4571 stamped ESPN and StatPal and MISSED
# `odds_polling._poll_all_odds`, which fetches The Odds API scores and writes
# `events.home_score`/`away_score` through a Core UPDATE every ~5.5 minutes.
#
# An unstamped writer is worse than an unstamped column. The row keeps whichever
# stamp a DIFFERENT source last left, so the payload serves an Odds API score
# under ESPN's name with a fresh-looking age — the precise lie the field exists
# to remove. #4576's attribution query would then name the wrong writer, which
# is the question this ship exists to answer.
#
# The site writes columns, not attributes, so the controls below exercise
# `score_observation_values` — the helper the site actually calls — and the AST
# guards pin that the site calls it, atomically, ungated by change. That is the
# same division this file already uses, and the same one
# `test_live_cadence_lat_p159` uses for this function: "the helper
# `_poll_all_odds` calls, never a local copy of its rule."

ODDS_SITE = "app/tasks/odds_polling.py"


# ── executable: the UNCHANGED 0-0 control ────────────────────────────────────


def test_core_values_stamp_a_score_that_did_not_change():
    """The 0-0 opener a writer confirms every pass and changes never.

    `score_observation_values` takes NO previous score — it cannot be made
    change-sensitive without adding a parameter, which is the strongest form
    this control can take.
    """
    assert score_observation_values(
        source=SCORE_SOURCE_ODDS, observed_at=NOW
    ) == {
        "score_source": "odds_api",
        "score_observed_at": NOW,
    }


@pytest.mark.parametrize("home,away", [(0, 0), (3, 1), (0, 7)])
def test_the_stamp_does_not_depend_on_the_score_at_all(home, away):
    """Whatever the numbers, an observation is an observation."""
    assert score_observation_values(
        source=SCORE_SOURCE_ODDS, observed_at=NOW
    ) == {
        "score_source": "odds_api",
        "score_observed_at": NOW,
    }


# ── executable: the NO-SCORE / no-clock controls ─────────────────────────────


def test_core_values_without_a_clock_stamp_nothing():
    """No clock, no stamp — an absent stamp reads as 'unknown age', which is
    honest. A wrong one is not."""
    assert score_observation_values(
        source=SCORE_SOURCE_ODDS, observed_at=None
    ) == {}


@pytest.mark.parametrize("bad", ["odds", "oddsapi", "OddsAPI", "", "espn2"])
def test_core_values_refuse_a_source_outside_the_registry(bad):
    with pytest.raises(ValueError):
        score_observation_values(source=bad, observed_at=NOW)


def test_odds_api_is_in_the_registry_and_fits_the_column():
    assert "odds_api" in SCORE_OBSERVATION_SOURCES
    assert len("odds_api") <= 20


def test_both_paths_share_one_registry():
    """The ORM stamp and the Core stamp must never disagree about who exists —
    a drift shows up as a silently unstamped writer, i.e. CERT-2460 again."""
    ev = SimpleNamespace(score_source=None, score_observed_at=None)
    for source in sorted(SCORE_OBSERVATION_SOURCES):
        assert stamp_score_observation(ev, source=source, observed_at=NOW) is True
        assert score_observation_values(source=source, observed_at=NOW)

    for bad in ("nope", "mlb"):
        with pytest.raises(ValueError):
            stamp_score_observation(ev, source=bad, observed_at=NOW)
        with pytest.raises(ValueError):
            score_observation_values(source=bad, observed_at=NOW)


# ── the wiring at the odds site ──────────────────────────────────────────────


def _odds_stamp_calls():
    return list(_calls_in(_module_tree(ODDS_SITE)))


def test_the_odds_writer_stamps_at_all():
    """The CERT-2460 defect itself: this returned [] before the repair."""
    assert _odds_stamp_calls(), (
        "odds_polling writes events.home_score but never stamps an observation "
        "(#4571 / CERT-2460)"
    )


def test_the_odds_stamp_is_merged_into_the_same_update_values():
    """ATOMICITY. The stamp must ride the SAME `update_values` dict as the score.

    Two separate writes would leave a window in which the row holds an Odds API
    score under the previous writer's attribution — a narrower version of the
    bug being fixed, and a much harder one to see.
    """
    tree = _module_tree(ODDS_SITE)
    merged = False
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        # `update_values.update(score_observation_values(...))`
        if getattr(fn, "attr", None) != "update":
            continue
        if getattr(getattr(fn, "value", None), "id", None) != "update_values":
            continue
        for arg in node.args:
            if isinstance(arg, ast.Call) and getattr(
                arg.func, "id", None
            ) == "score_observation_values":
                merged = True

    assert merged, (
        "the odds stamp is not merged into `update_values` — it must land in "
        "the same UPDATE as the score it describes"
    )


def test_the_odds_stamp_passes_the_pass_clock_not_a_fresh_now():
    """One clock per poll, never `now()` per row.

    A slow pass would otherwise stamp its last event fresher than its first when
    both came off a single provider payload — the stamp would then encode our
    loop's progress rather than the provider's reading.
    """
    for call in _odds_stamp_calls():
        kwargs = {k.arg: k.value for k in call.keywords}
        assert "observed_at" in kwargs, "the site must name its clock"
        observed = kwargs["observed_at"]
        assert isinstance(observed, ast.Name), (
            "observed_at must be the pass clock bound above the loop, not an "
            f"expression like now() — got {ast.dump(observed)}"
        )
        assert observed.id == "now"


def test_the_odds_stamp_is_gated_on_a_score_being_present():
    """The NO-SCORE control, at the site.

    A provider record with no `scores` array must not stamp: we did not read a
    score, so there is nothing to date. The guard is the `is not None` pair, and
    it must be an `or` — a partial read is still a read.
    """
    tree = _module_tree(ODDS_SITE)
    guarded = False
    for node in ast.walk(tree):
        if not isinstance(node, ast.If):
            continue
        if not list(_calls_in(ast.Module(body=node.body, type_ignores=[]))):
            continue
        test_src = ast.dump(node.test)
        if "home_score" in test_src and "away_score" in test_src:
            assert "BoolOp" in test_src and "Or" in test_src, (
                "the score-presence guard must be an `or` — a record carrying "
                "only one side was still a read"
            )
            assert "NotEq" not in test_src, (
                "the odds stamp is gated on the score having CHANGED; it must "
                "be gated only on a score having been READ"
            )
            guarded = True

    assert guarded, "the odds stamp is not gated on a score being present"


def test_a_refused_id_never_reaches_the_stamp():
    """The REFUSED-ID control.

    #1981's guard `continue`s on a STALE/UNVERIFIABLE/UNBOUND external_id before
    any `update_values` is built. A stamp written on that path would date a
    score we deliberately refused to write — attribution for a number that is
    not there.
    """
    src = (BACKEND / ODDS_SITE).read_text().splitlines()

    continue_line = next(
        i for i, line in enumerate(src)
        if line.strip() == "continue"
        and any("IdCurrency.CURRENT" in src[j] for j in range(max(0, i - 30), i))
    )
    stamp_line = min(
        call.lineno for call in _odds_stamp_calls()
    )
    assert continue_line < stamp_line, (
        "the stale-id refusal must short-circuit BEFORE the stamp; a refused "
        "write that still stamps dates a score it did not make"
    )


# ── The straggler settle door (#4652) also signs its reads ───────────────────
#
# #4652 landed on master while this branch waited for a merge slot, adding a
# SECOND writer into the same settle door: `_settle_authority_stragglers` ends
# a match the authority finished on a board day the ordinary pass never asks
# about. It called `update_event_fields_from_espn` without `observed_at`, and
# the stamp helper returns False on a None clock rather than raising — so that
# path wrote scores with no age, silently, on exactly the rows a reader is most
# likely to be looking at (a match that has just been settled).
#
# The AST guard above proves the keyword is TYPED at every call site. This one
# proves a real clock travels through the door and lands on the row.

def _straggler_harness():
    """The captured #4652 fixtures, reused rather than re-invented.

    Loaded by PATH, not by module name: `tests/` is not a package and is not on
    `sys.path` under every pytest rootdir, so a plain import passes here and
    ImportErrors in CI.
    """
    import importlib.util

    path = Path(__file__).with_name("test_authority_straggler_board_day_4652.py")
    spec = importlib.util.spec_from_file_location("_straggler_4652", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.asyncio
async def test_a_straggler_settled_off_a_prior_day_board_carries_a_stamp():
    s = _straggler_harness()
    rows = s._suspended_specimens()

    await s._run(rows, s.BOARD_0909)

    assert [e.status for e in rows] == ["completed", "completed"], (
        "precondition: #4652's pass must still settle these two rows"
    )
    for event in rows:
        assert getattr(event, "score_observed_at", None) is not None, (
            f"event {event.id} was settled off the prior-day board with no "
            "observation stamp — the page would print a corrected score whose "
            "age is unknown (#4571 + #4652)"
        )
        assert event.score_source == "espn"


@pytest.mark.asyncio
async def test_the_straggler_stamp_is_the_board_read_not_the_pass_clock():
    """Each group is its own fetch, so each carries its own read moment.

    `now` is the pass's entry clock and can be arbitrarily older than the
    board request that actually produced these scores; stamping with it would
    report the score as older than it is.
    """
    s = _straggler_harness()
    rows = s._suspended_specimens()

    await s._run(rows, s.BOARD_0909, now=s.NOW)

    for event in rows:
        assert event.score_observed_at != s.NOW, (
            "the straggler stamp reused the pass-entry clock instead of the "
            "moment its own board was read"
        )
        assert event.score_observed_at.tzinfo is not None, "stamp must be aware"


@pytest.mark.asyncio
async def test_an_authority_dark_straggler_board_stamps_nothing():
    """No board, no read, no age. An absence must not be dated (#3473)."""
    s = _straggler_harness()
    rows = s._suspended_specimens()

    await s._run(rows, s.BOARD_0909, dark=True)

    for event in rows:
        assert getattr(event, "score_observed_at", None) is None, (
            "a dark board settled nothing, so it must not have stamped a score"
        )
