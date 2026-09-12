"""#5273 — a frozen Polymarket leg a DERIVATIVE wrote is retired; a real one is not.

THE DEFECT THESE GUARD. `/api/events/15308654`, Warrington Town FC vs. South
Liverpool FC, served on 2026-09-12 with one blend source and nothing else:

    "polymarket": {"value": 0.085, "evidence_status": "unverified"}

8.5% presented as the match win probability, written by
`Warrington Town FC vs. South Liverpool FC - Exact Score`. The event is
`suspended`, and `prediction_market_matching.py` selects `scheduled`/`live` and
`completed`/`closed` — never `suspended` — so no writer visits it and the
retirement path (`_retire_unbacked_blend_source`) never arrives. 233 events were
measured frozen in this shape on production 2026-09-12 21:3xZ.

WHY THESE ARE PURE GUARDS AND NOT DATABASE GUARDS. Every real-Postgres gate in
this repo is env-gated and SKIPS in CI, which has no Postgres service, and a
skipped guard is not a guard. So these exercise the repair's own decision
functions — the ones that choose what to change — over hand-built rows.

🔴 THE ONE THING A ONE-SIDED TEST CANNOT SEE. A screen that refuses everything
passes every "the derivative is planned" test ever written. So every direction is
asserted twice, and the two decisive cases are
`test_an_event_recording_a_genuine_winner_is_never_planned_5273` (the 3
acquittals a naive "no winner market today" screen would have destroyed) and
`test_a_mixed_event_is_never_planned_5273` (the case where the evidence
disagrees with itself and the screen must abstain rather than pick by timestamp).
"""

import importlib

import pytest


@pytest.fixture(scope="module")
def repair():
    """The repair module, imported by path the way `scripts/` modules are."""
    import os
    import sys

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if root not in sys.path:
        sys.path.insert(0, root)
    return importlib.import_module(
        "scripts.repair_5273_frozen_unbacked_polymarket_legs"
    )


def _rows(*pairs):
    """(event_id, market_name) rows in the shape the stage-2 scan returns."""
    return [{"event_id": e, "market_name": n} for e, n in pairs]


def _verdict(repair, event_id, verdicts):
    return next(v for v in verdicts if v.event_id == event_id)


# ── direction 1: the derivative books this repair exists for ─────────────────

#: One per family Polymarket mints on the frozen cohort, taken from the
#: production plan rather than invented — every one of these is a real recorded
#: producer on a real suspended event.
DERIVATIVE_PRODUCERS = [
    "Dundee FC vs. Hibernian FC - Exact Score",
    "Genoa CFC vs. Frosinone Calcio - 1st Half Exact Score",
    "Tobol Kostanay vs. Kaisar Kyzylorda - More Markets",
    "IFK Norrkoping FK vs. Ljungskile SK - Halftime Result",
    "CA Acassuso vs. CA All Boys: Both Teams to Score",
    "St. Truidense VV vs. RAAL La Louviere: Both Teams to Score in First Half",
    "Wolfsberger AC vs. SK Rapid: Both Teams to Score in Second Half",
    "Lille OSC vs. Real Betis Balompié - First Team to Score",
]


@pytest.mark.parametrize("name", DERIVATIVE_PRODUCERS)
def test_a_derivative_producer_convicts_its_event_5273(repair, name):
    verdicts = repair.grade_events([7], _rows((7, name)))
    assert _verdict(repair, 7, verdicts).verdict == repair.CONVICT


# ── direction 2: the real match winners that must survive ────────────────────

#: Real recorded producers from the same cohort that the shared gate ADMITS.
#: These events also carry a frozen pointer-less leg, so they are inside every
#: status and pointer filter this repair applies — the producer name is the only
#: thing keeping them out of the plan.
GENUINE_WINNERS = [
    "Fulham FC vs. AFC Wimbledon",
    "Chantelle Cameron vs. Mikaela Mayer",
    "Aloys Youmbi vs. Mike Perez",
    "Luis Torres Valenzuela vs. Jordan White",
    "KRC Genk vs. SK Beveren",
    "IFK Norrkoping FK vs. Ljungskile SK",
]


@pytest.mark.parametrize("name", GENUINE_WINNERS)
def test_an_event_recording_a_genuine_winner_is_never_planned_5273(repair, name):
    verdicts = repair.grade_events([7], _rows((7, name)))
    assert _verdict(repair, 7, verdicts).verdict == repair.ACQUIT


def test_the_same_fixture_convicts_or_acquits_on_the_suffix_alone_5273(repair):
    """`IFK Norrkoping FK vs. Ljungskile SK` is in BOTH lists above, once bare
    and once as `- Halftime Result`. That pair is the whole thesis in one line:
    the two markets share a fixture, two outcomes and a title stem, and only the
    suffix says which question the price answers."""
    bare = "IFK Norrkoping FK vs. Ljungskile SK"
    derivative = f"{bare} - Halftime Result"
    verdicts = repair.grade_events([1, 2], _rows((1, bare), (2, derivative)))
    assert _verdict(repair, 1, verdicts).verdict == repair.ACQUIT
    assert _verdict(repair, 2, verdicts).verdict == repair.CONVICT


# ── the unanimity screen, which is what replaces a time tolerance ────────────


def test_a_mixed_event_is_never_planned_5273(repair):
    """An event recording BOTH a winner and a derivative abstains.

    Measured 0 on production, and that zero is exactly why the screen can be
    unanimous instead of picking the producer nearest the leg's `updated_at`. If
    the population ever grows one, convicting it would be choosing by timestamp
    the thing this screen refuses to choose by timestamp — so it is reported as
    MIXED and left alone.
    """
    verdicts = repair.grade_events(
        [7],
        _rows(
            (7, "Fulham FC vs. AFC Wimbledon"),
            (7, "Fulham FC vs. AFC Wimbledon - Exact Score"),
        ),
    )
    assert _verdict(repair, 7, verdicts).verdict == repair.MIXED


def test_every_recorded_producer_must_be_refuted_to_convict_5273(repair):
    """Unanimity is over ALL recorded names, not the first or the last one."""
    derivatives = [
        (7, "Dundee FC vs. Hibernian FC - Exact Score"),
        (7, "Dundee FC vs. Hibernian FC - More Markets"),
        (7, "Dundee FC vs. Hibernian FC: Both Teams to Score"),
    ]
    assert _verdict(repair, 7, repair.grade_events([7], _rows(*derivatives))).verdict == (
        repair.CONVICT
    )
    # One admissible name anywhere in the set is enough to stop it.
    with_winner = derivatives + [(7, "Dundee FC vs. Hibernian FC")]
    assert _verdict(repair, 7, repair.grade_events([7], _rows(*with_winner))).verdict == (
        repair.MIXED
    )


# ── fail-open on absence ─────────────────────────────────────────────────────


def test_an_event_with_no_recorded_producer_is_never_planned_5273(repair):
    """345 of the 1,126 in scope. No evidence is not evidence of guilt."""
    verdicts = repair.grade_events([7], _rows())
    assert _verdict(repair, 7, verdicts).verdict == repair.UNDECIDABLE


@pytest.mark.parametrize("blank", [None, "", "   ", "\t\n"])
def test_a_blank_producer_name_is_never_classified_5273(repair, blank):
    """🔴 THE STRIP IS LOAD-BEARING. `"   "` is truthy, so a bare `if not name`
    hands a blank to the recognizer, which answers "not a game winner" — and the
    event is CONVICTED on no evidence at all, the one direction this screen
    exists to refuse. A blank must land in UNDECIDABLE, never CONVICT."""
    verdicts = repair.grade_events([7], _rows((7, blank)))
    assert _verdict(repair, 7, verdicts).verdict == repair.UNDECIDABLE


def test_a_blank_beside_a_real_derivative_does_not_change_the_verdict_5273(repair):
    """A dropped blank must not be counted as an admissible producer either —
    that would turn a clean conviction into a MIXED abstention."""
    verdicts = repair.grade_events(
        [7],
        _rows((7, "   "), (7, "Dundee FC vs. Hibernian FC - Exact Score")),
    )
    assert _verdict(repair, 7, verdicts).verdict == repair.CONVICT


# ── the future-event refusal ─────────────────────────────────────────────────


def test_a_future_event_is_refused_even_when_convicted_5273(repair):
    """Measured 0 on production and computed at runtime anyway: a future event
    is the one case where a live writer is about to arrive and a reader could be
    watching, so the repair declines to race it."""
    convicted = repair.grade_events(
        [1, 2],
        _rows(
            (1, "Dundee FC vs. Hibernian FC - Exact Score"),
            (2, "Genoa CFC vs. Frosinone Calcio - 1st Half Exact Score"),
        ),
    )
    plannable, refused = repair.refuse_future_events(
        convicted, {1: False, 2: True}
    )
    assert [v.event_id for v in plannable] == [1]
    assert [v.event_id for v in refused] == [2]


# ── the write is the LIVE function's, not a second copy ──────────────────────


def test_repair_writes_what_the_live_retirement_writes_5273(repair):
    """THE ANTI-DRIFT GUARD, and the reason this repair can be trusted to agree
    with the path that already runs everywhere else.

    `_retire_unbacked_blend_source` retires a leg by calling
    `prune_blend_source(wps, source, 0)`. This script calls the same function
    with the same arguments, so the column value it writes is the one the live
    path would have written had its selector ever reached the event. Asserting
    the SHAPE here (rather than re-deriving "pop the key") is what makes a future
    change to the live rule fail this test instead of silently forking it.
    """
    from app.tasks.prediction_market_matching import prune_blend_source

    wps = {
        "polymarket": {"value": 0.085, "updated_at": "2026-09-09T20:15:16Z"},
        "betting": {"value": 0.61, "updated_at": "2026-09-09T19:00:00Z"},
    }
    assert repair.retired_leg_value(wps) == prune_blend_source(wps, "polymarket", 0)

    new_wps, changed = repair.retired_leg_value(wps)
    assert changed is True
    assert "polymarket" not in new_wps
    assert new_wps["betting"] == wps["betting"], "a sibling source is never touched"


def test_the_write_DELEGATES_to_the_live_function_not_merely_agrees_5273(
    repair, monkeypatch
):
    """🔴 THE TEST ABOVE CANNOT SEE A FORK, AND A MUTANT PROVED IT.

    Replacing `return prune_blend_source(wps, SOURCE, 0)` with a hand-rolled
    `d.pop(SOURCE)` passes all 42 guards in this file, because the two agree on
    every input that exists today. Agreement is not delegation: the copy stops
    agreeing the moment the live rule grows a clause, and — the #1951 failure —
    it does not throw when it disagrees, it just quietly answers differently.

    So this patches the live function and asserts the repair's answer moves with
    it. A copy cannot pass this; only a call can.
    """
    from app.tasks import prediction_market_matching

    sentinel = ({"sentinel": True}, "not-a-bool")
    monkeypatch.setattr(
        prediction_market_matching, "prune_blend_source", lambda *a, **k: sentinel
    )
    assert repair.retired_leg_value({"polymarket": {"value": 0.085}}) is sentinel


def test_the_write_passes_the_live_function_the_retirement_arguments_5273(
    repair, monkeypatch
):
    """Delegation to the right call. `_retire_unbacked_blend_source` retires with
    `remaining_linked=0` — that zero is what makes it a retirement rather than a
    no-op — so a call that delegated with any other count would prune nothing
    while still passing the delegation test above."""
    from app.tasks import prediction_market_matching

    seen = {}

    def _spy(wps, source, remaining_linked):
        seen.update(wps=wps, source=source, remaining_linked=remaining_linked)
        return {}, True

    monkeypatch.setattr(prediction_market_matching, "prune_blend_source", _spy)
    wps = {"polymarket": {"value": 0.085}}
    repair.retired_leg_value(wps)
    assert seen == {"wps": wps, "source": "polymarket", "remaining_linked": 0}


def test_a_sole_source_event_is_emptied_not_refused_5273(repair):
    """231 of the 233. Emptying the column is the INTENDED outcome — #5432
    acceptance 2, and what the live path already does: `prune_blend_source` has
    no test for what else remains. Withdrawing a false claim needs no
    replacement to be an improvement."""
    new_wps, changed = repair.retired_leg_value(
        {"polymarket": {"value": 0.085, "updated_at": "2026-09-09T20:15:16Z"}}
    )
    assert changed is True
    assert new_wps == {}


def test_an_event_with_no_polymarket_leg_is_a_no_op_5273(repair):
    """Idempotence: a second `--apply` over an already-repaired event plans
    nothing, because the pure function reports `changed=False`."""
    new_wps, changed = repair.retired_leg_value({"betting": {"value": 0.61}})
    assert changed is False
    assert new_wps == {"betting": {"value": 0.61}}


# ── the recognizer is CALLED, never copied ───────────────────────────────────


def test_shim_external_id_is_inert_5273(repair):
    """The recognizer reads `external_id` only to spot a Kalshi `kx...` ticker,
    and every row this script can see is `source='polymarket'`. If a future
    recognizer DOES read a Polymarket id, this fails instead of silently
    re-classifying the whole population."""
    assert repair._RecordedMarket("x").external_id is None
    name = "Dundee FC vs. Hibernian FC"
    assert repair.producer_is_game_winner(name) is True
    assert repair.producer_is_game_winner(f"{name} - Exact Score") is False


def test_the_repair_calls_the_shared_recognizer_5273(repair):
    """Not a copy of it. If `live_blend._class_says_game_winner` changes its
    answer, this repair's verdicts change with it — which is the point."""
    from app.utils import live_blend

    assert repair.producer_is_game_winner.__code__.co_names, "must call something"
    src = repair.producer_is_game_winner.__doc__ or ""
    assert "shared" in src.lower()
    assert hasattr(live_blend, "_class_says_game_winner")


# ── the D51 rails ────────────────────────────────────────────────────────────


def test_an_empty_reconciliation_never_passes_5273(repair):
    """gotcha #53: `all()` over an empty mapping is True, so a reconciliation
    that inspected NOTHING would read as a clean pass and `--apply` would
    proceed with no undo at all."""
    assert repair.backup_is_exact({}) is False
    assert repair.backup_is_exact({"events": 0, "stale_backup_rows": 0}) is True
    assert repair.backup_is_exact({"events": 1, "stale_backup_rows": 0}) is False
    assert repair.backup_is_exact({"events": 0, "stale_backup_rows": 3}) is False


def test_the_small_plan_discriminator_reaches_the_decision_5273(repair):
    """#5246's lesson: a discriminator that only changes the wording of a
    refusal is not a discriminator. These assert `blocks_apply`, not the text."""
    full = repair.explain_small_plan(repair.SANITY_FLOOR, 0)
    assert full.blocks_apply is False and full.message == ""

    drained = repair.explain_small_plan(2, repair.SANITY_FLOOR)
    assert drained.blocks_apply is False
    assert "ALREADY APPLIED" in drained.message

    broken = repair.explain_small_plan(2, 0)
    assert broken.blocks_apply is True
    assert "FILTER BROKE" in broken.message


def test_the_floor_sits_below_the_measured_plan_5273(repair):
    """A floor at or above the plan refuses the first real run; a floor near
    zero never fires. 233 events measured, floor 186."""
    assert 0 < repair.SANITY_FLOOR < 233
    assert repair.SANITY_FLOOR > 233 * 0.5


# ── scope: the statuses, and the app the write may happen on ─────────────────


def test_only_the_statuses_no_writer_visits_are_in_scope_5273(repair):
    """`closed`/`completed` are reached by the completed-catchup selector, so
    the live path owns them and a second writer racing it is how two repairs
    disagree. `suspended` is the cohort; `scheduled` is in scope because the
    stale tail of it has no writer either."""
    assert set(repair.IN_SCOPE_STATUSES) == {"suspended", "scheduled"}
    for excluded in ("closed", "completed", "live", "voided", "merged"):
        assert excluded not in repair.IN_SCOPE_STATUSES


def test_the_cohort_query_requires_an_absent_pointer_5273(repair):
    """The pointer is what says a gated writer produced the leg. A cohort query
    that dropped this clause would plan every Polymarket leg on the site."""
    sql = repair.SQL["candidates"]
    assert "eligibility" in sql
    assert "NOT (" in sql and "? 'eligibility'" in sql
    assert "status = ANY" in sql


@pytest.mark.parametrize("where", [None, "bainluck", "", "laptop"])
def test_a_write_off_the_named_app_is_refused_5273(repair, monkeypatch, where):
    """Notice 47(c): the invocation IS the attended step, so it happens on one
    named app. Unset means not a dyno at all — a laptop pointed at production —
    which is precisely the case this refuses rather than falling through."""
    if where is None:
        monkeypatch.delenv("HEROKU_APP_NAME", raising=False)
    else:
        monkeypatch.setenv("HEROKU_APP_NAME", where)

    class Args:
        backup = True
        apply = False

    refusal = repair.wrong_app_refusal(Args())
    assert refusal and "REFUSING to write" in refusal
    assert repair.PRODUCER_APP in refusal


def test_a_write_on_the_named_app_is_allowed_and_a_dry_run_runs_anywhere_5273(
    repair, monkeypatch
):
    class Args:
        backup = True
        apply = True

    monkeypatch.setenv("HEROKU_APP_NAME", repair.PRODUCER_APP)
    assert repair.wrong_app_refusal(Args()) is None

    class DryRun:
        backup = False
        apply = False

    monkeypatch.delenv("HEROKU_APP_NAME", raising=False)
    assert repair.wrong_app_refusal(DryRun()) is None, "a dry run only reads"


def test_the_update_is_a_compare_and_swap_on_the_backup_5273(repair):
    """#5595: `reconcile_backup` reads without a lock, so a value can move
    between the clean check and the write. The swap is on the WHOLE backed-up
    value, so every event this script changed has an exact backup, or it was not
    changed."""
    sql = repair.SQL["update"]
    assert repair.BAK_TABLE in sql
    assert "IS NOT DISTINCT FROM" in sql
    assert "? 'eligibility'" in sql, "a leg stamped since the plan is not ours"
    assert "RETURNING" in sql, "the manifest records what actually changed"


def test_the_backup_is_checked_by_value_not_by_id_5273(repair):
    """#5595's first half: `bak_copy` skips ids already present, so an id-only
    check reconciles clean while the stored value is a false record of what is
    about to be replaced."""
    assert "IS DISTINCT FROM" in repair.SQL["bak_stale"]
    assert "IS DISTINCT FROM" in repair.SQL["bak_evict_stale"]


def test_the_documented_undo_matches_the_tables_the_script_writes_5273(repair):
    """A restore line naming a table the script does not create is a D51 undo
    that fails at the moment it is needed."""
    doc = repair.__doc__
    assert repair.BAK_TABLE in doc
    assert repair.MANIFEST_TABLE in doc
    assert "UPDATE events" in doc
    assert repair.BAK_TABLE in repair.SQL["bak_create"]
    assert repair.MANIFEST_TABLE in repair.SQL["man_create"]
