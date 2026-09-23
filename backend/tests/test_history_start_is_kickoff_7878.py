"""#7878: the chart's "Since Start" window stops cutting at the venue's EXPECTED END.

**SHIP: a finished tennis match stops drawing eight flat minutes at 99% and draws
the two hours of real probability history we captured.** (Pillars: TRUTH /
FORMATTING.)

──────────────────────────────────────────────────────────────────────────────
WHAT A READER SAW
──────────────────────────────────────────────────────────────────────────────
`/events/15317314` — Basilashvili v Cina, ATP, 2026-09-23, read 10:1xZ at 390px.
The page names the winner correctly ("Settled · Nikoloz Basilashvili wins 2-0")
over a Win Probability chart whose whole x-axis is **2:12 AM → 2:20 AM PDT**, a
dead-flat green line at 99%.

The match itself is in the database and it is a real curve. Bucketed by hour, the
contest was played in the **07:00Z hour** — 117 Kalshi points and 126 Polymarket
points carrying 0.39 → 0.995. The stored `commence_time` is **09:10Z**, about two
hours after it finished, so `range=since_start` served **4 Kalshi points and 0
Polymarket out of 528**, every one of them after the winner was decided:

    GET /api/events/15317314/history?range=since_start   kalshi 4   polymarket 0
    GET /api/events/15317314/history                     kalshi 316 polymarket 212

──────────────────────────────────────────────────────────────────────────────
THE CAUSE IS THE CLOCK, NOT THE CAPTURE — AND THE ISSUE'S RECORDED CAUSE IS WRONG
──────────────────────────────────────────────────────────────────────────────
#7878 was filed as "in-game Kalshi snapshots stop ~10 min after commence". They
do not stop: 117 in-contest points is the opposite of a collection outage. What
is ~10 minutes after `commence_time` is the venue's SETTLEMENT, because
`commence_time` is sitting at the far end of the match.

Read at the venue 2026-09-23 (notice 26, Kalshi's own `/markets` by series
discovery), `KXATPMATCH-26SEP24KOUMUL-MUL` carries
`occurrence_datetime == expected_expiration_time == 2026-09-24T09:10:00Z`,
byte-identical, beside `early_close_condition: "This market will close and expire
after a winner is declared."` It is when the CONTRACT is expected to resolve.
Kalshi publishes no kick-off field at all. #5905 read the same equality on
2026-09-13 across soccer, and `kalshi_occurrence_start`'s docstring already says
so; this file is the tennis half that neither recovery can reach.

🔴 **MEASURED, WITH THE OTHER CLOCKS AS THE CONTROL.** Production, events
commencing in the 48 h to 2026-09-23 10:3xZ, restricted to rows with >=50
win-prob points and a >0.30 swing so a match that was never in doubt cannot
count, asking "was the contest already decided before its own stored start?":

    commence_time_source   events   decided before start   pct
    ────────────────────────────────────────────────────────────
    kalshi                    208                    139   66.8
    polymarket_venue          167                      2    1.2
    odds_api                   33                      2    6.1
    espn                       42                      0    0.0

The three non-Kalshi arms are the noise floor of the question itself.

🔴 **WHY THE EXISTING FALLBACK DOES NOT CATCH IT.** `_omit_pre_kickoff_points`
already declines when NOTHING survives the cut (`has_post_start`). That is one
arm — "the trim would empty the chart" — and this population sits just past it
with a handful of post-settlement points. `test_the_existing_fallback_does_not_
save_the_specimen` is that statement as a control: it asserts the OLD behaviour
on the specimen's exact shape, so if someone ever widens `has_post_start` to
cover this, that test goes red and says so rather than leaving this file
silently redundant.

🔴 **WHAT MAKES THESE NON-VACUOUS — MUTATION, RUN AND COUNTED.** Each guarantee
was mutated back on the finished module and this file re-run. Every needle
matched exactly once (a needle matching 0 or 2 times measures nothing, so the
harness refuses rather than reporting a survivor), and the baseline is green
before and after:

    N1  `start_is_kickoff` ignored (trim always runs)   -> 3 red
    N2  predicate returns False always                  -> 2 red
    N3  predicate drops the `external_id` arm           -> 1 red
    N4  predicate drops the occurrence-recovery stamp   -> 1 red
    N5  predicate drops the expiration-recovery stamp   -> 1 red
    N6  predicate widened to every commence source      -> 3 red
    N7  call site passes the literal, not the predicate -> 1 red

N6 is the one that matters: it is the shape in which this change could stop
deferring the pre-kickoff half for the #6925 cohort it was measured on. It kills
3 only because `test_the_6925_cohort_is_trimmed_exactly_as_before` DERIVES
`start_is_kickoff` from the predicate — the first draft passed the literal
`True` and stayed green under N6, which is a control that hard-codes the value
under test and therefore is not one.

N7 is the inertness guard: the predicate can be perfect and the route can still
never ask it. Only `test_the_route_actually_asks_the_predicate` sees that.

The controls are green before and after by design: a control that goes red under
the fix was testing the fix instead of guarding it.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.models.models import Event
from app.routes.events import (
    _commence_time_is_venue_expiration,
    _omit_pre_kickoff_points,
)
from app.utils.kalshi_expiration_start import KALSHI_EXPIRATION_RECOVERY_STAMP
from app.utils.kalshi_occurrence_start import KALSHI_RECOVERY_STAMP
from tests.test_history_prewindow_deferral_6925 import _book_series, _since_start
from tests.test_history_window_budget_6921 import (
    _finished_event,
    _kickoff,
    _population,
)

UTC = timezone.utc

#: The specimen's own instant. Fixed, not derived from the clock: gotcha #44 —
#: an anchor that branches on the wall clock is not an anchor.
STORED_START = datetime(2026, 9, 23, 9, 10, tzinfo=UTC)


def _event(source="kalshi", external_id=None, **stamps):
    """A row clocked the way the specimen was. Nothing here touches a session."""
    event = Event(
        id=15317314,
        sport_id=1,
        external_id=external_id,
        home_team_name="Nikoloz Basilashvili",
        away_team_name="Federico Cina",
        commence_time=STORED_START,
        status="suspended",
    )
    event.commence_time_source = source
    for attr, value in stamps.items():
        setattr(event, attr, value)
    return event


def _specimen_series():
    """The specimen's real shape: the contest before the stored start, and a
    short post-settlement tail after it.

    The tail is what makes this population invisible to `has_post_start`, so it
    is the whole point of the fixture and is not padding.
    """
    contest = [
        {"timestamp": (STORED_START - timedelta(hours=2, minutes=i)).isoformat()}
        for i in range(117)
    ]
    tail = [
        {"timestamp": (STORED_START + timedelta(minutes=3 + i)).isoformat()}
        for i in range(4)
    ]
    return contest, tail


def _trim(commence_time, *, start_is_kickoff=True, **series):
    payload = {
        "history": series.get("history", []),
        "bookmaker_history": series.get("bookmaker_history", {}),
        "win_prob_history": series.get("win_prob_history", {}),
        "win_prob_sources_meta": series.get("win_prob_sources_meta", {}),
        "aggregate_line": series.get("aggregate_line", []),
        "espn_history": series.get("espn_history", []),
    }
    omitted = _omit_pre_kickoff_points(
        commence_time=commence_time, start_is_kickoff=start_is_kickoff, **payload
    )
    return omitted, payload


# ---------------------------------------------------------------------------
# The ship
# ---------------------------------------------------------------------------


def test_a_row_clocked_from_the_venues_expected_expiration_keeps_its_contest():
    """The filed defect: 117 in-contest points deleted, 4 dead ones served."""
    contest, tail = _specimen_series()
    omitted, payload = _trim(
        STORED_START,
        start_is_kickoff=False,
        win_prob_history={"kalshi": contest + tail},
        win_prob_sources_meta={"kalshi": {"snapshot_count": 121}},
    )

    assert omitted is False, (
        "a start that is really the venue's expected END must not be used as a "
        "cut — declining is strictly fail-open, the function only removes points"
    )
    assert len(payload["win_prob_history"]["kalshi"]) == 121, "the contest survives"
    assert payload["win_prob_sources_meta"]["kalshi"]["snapshot_count"] == 121


def test_the_existing_fallback_does_not_save_the_specimen():
    """CONTROL — the OLD behaviour, asserted on the specimen's exact shape.

    `has_post_start` declines only when the trim would empty the chart. Four
    post-settlement points clear it, so without `start_is_kickoff` this row is
    trimmed to its dead tail. If this ever goes red the older arm has been
    widened to cover this class and this file is the thing to re-read.
    """
    contest, tail = _specimen_series()
    omitted, payload = _trim(
        STORED_START,
        win_prob_history={"kalshi": contest + tail},
        win_prob_sources_meta={"kalshi": {"snapshot_count": 121}},
    )

    assert omitted is True
    assert len(payload["win_prob_history"]["kalshi"]) == 4, (
        "the one-armed fallback leaves exactly the post-settlement tail"
    )


def test_the_predicate_fires_on_the_specimens_provenance():
    assert _commence_time_is_venue_expiration(_event(source="kalshi")) is True
    assert _commence_time_is_venue_expiration(_event(source="kalshi_occurrence")) is True


# ---------------------------------------------------------------------------
# Controls — each arm of the predicate, and the cohort #6925 was measured on
# ---------------------------------------------------------------------------


def test_every_other_clock_is_left_alone():
    """The measured control arms. `polymarket_venue`, `odds_api` and `espn` land
    a median 105-139 minutes BEFORE the last uncertain reading — real kick-offs."""
    for source in ("polymarket_venue", "odds_api", "espn", "statpal", "kalshi_ticker"):
        assert _commence_time_is_venue_expiration(_event(source=source)) is False, source
    assert _commence_time_is_venue_expiration(_event(source=None)) is False


def test_a_start_a_schedule_provider_reported_is_not_ours_to_distrust():
    """⚠️ VACUOUS ON TODAY'S POPULATION AND KEPT FOR MECHANISM, NOT REACH: all
    208 measured rows have `external_id IS NULL`, so there is no live specimen on
    this side. Same gate, same reason, as `kalshi_occurrence_scheduled_start`."""
    anchored = _event(source="kalshi", external_id="espn:401584931")
    assert _commence_time_is_venue_expiration(anchored) is False


def test_a_row_either_recovery_already_corrected_is_not_re_judged():
    """Both recoveries run EARLIER in this route and neither rewrites
    `commence_time_source`, so the stamps — not the source — are the only honest
    way to ask whether the served hour is still an expiration."""
    recovered_soccer = _event(source="kalshi", **{KALSHI_RECOVERY_STAMP: True})
    assert _commence_time_is_venue_expiration(recovered_soccer) is False

    recovered_combat = _event(source="kalshi", **{KALSHI_EXPIRATION_RECOVERY_STAMP: True})
    assert _commence_time_is_venue_expiration(recovered_combat) is False


def test_the_6925_cohort_is_trimmed_exactly_as_before():
    """CONTROL — the byte win this change must not give back. The three
    specimens #6925 measured (NFL, NFL, EPL) are `odds_api`/`espn` clocked, so
    they never reach the new arm and their trim is untouched.

    `start_is_kickoff` is DERIVED from the predicate here rather than passed as
    a literal, because a control that hard-codes the value under test cannot see
    a predicate that has been widened to swallow every row.
    """
    kickoff = datetime(2026, 9, 18, 17, 0, tzinfo=UTC)
    pre = [{"timestamp": (kickoff - timedelta(days=9) + timedelta(hours=i)).isoformat()} for i in range(40)]
    game = [{"timestamp": (kickoff + timedelta(minutes=i)).isoformat()} for i in range(60)]

    nfl = _event(source="odds_api")
    omitted, payload = _trim(
        kickoff,
        start_is_kickoff=not _commence_time_is_venue_expiration(nfl),
        history=pre + game,
        win_prob_history={"espn": pre + game},
        win_prob_sources_meta={"espn": {"snapshot_count": 100}},
    )

    assert omitted is True
    assert len(payload["history"]) == 60, "the pre-kickoff half is still deferred"
    assert payload["win_prob_sources_meta"]["espn"]["snapshot_count"] == 60


def test_the_route_actually_asks_the_predicate():
    """WIRING — without this the whole change is inert at the only call site.

    Serves a Kalshi-clocked finished row through `get_event_odds_history` with
    `range=since_start` and asserts the pre-kickoff half SURVIVED, then the same
    row clocked by `odds_api` and asserts it did not. Two arms, because a route
    that ignored the parameter would pass either one alone.
    """
    kickoff = _kickoff()
    rows = _population(kickoff)

    venue_clocked = _finished_event(kickoff)
    venue_clocked.commence_time_source = "kalshi"
    venue_clocked.external_id = None
    served = _since_start(venue_clocked, rows)
    assert served["pre_window_omitted"] is False, (
        "the route must not advertise a trim it was right not to perform"
    )
    assert any(
        datetime.fromisoformat(p["timestamp"]) < kickoff
        for p in _book_series(served)
    ), "the contest before the stored 'start' has to reach the client"

    anchored = _finished_event(kickoff)
    anchored.commence_time_source = "odds_api"
    anchored.external_id = None
    control = _since_start(anchored, rows)
    assert control["pre_window_omitted"] is True, (
        "a real kick-off is still trimmed — this is #6925's cohort"
    )
    assert all(
        datetime.fromisoformat(p["timestamp"]) >= kickoff
        for p in _book_series(control)
    )


def test_the_payload_tells_the_client_whether_its_start_is_a_kickoff():
    """The producer half of the pair. The render half (UX, notice 41) cuts its
    own "Since Start" window at `commence_time` and cannot see provenance, so it
    has to be TOLD — re-deriving this from the served points is impossible, which
    is the same reason `pre_window_omitted` is served rather than inferred."""
    kickoff = _kickoff()
    rows = _population(kickoff)

    venue_clocked = _finished_event(kickoff)
    venue_clocked.commence_time_source = "kalshi"
    venue_clocked.external_id = None
    assert _since_start(venue_clocked, rows)["commence_time_is_kickoff"] is False

    anchored = _finished_event(kickoff)
    anchored.commence_time_source = "espn"
    anchored.external_id = None
    assert _since_start(anchored, rows)["commence_time_is_kickoff"] is True

    # Served on `range=all` too: the flag describes the ROW, not the request.
    from tests.test_history_prewindow_deferral_6925 import _history

    assert _history(venue_clocked, rows)["commence_time_is_kickoff"] is False


def test_declining_never_removes_a_point_no_matter_the_shape():
    """The fail-open property stated directly: with `start_is_kickoff=False` this
    function is the identity on every series it can touch."""
    contest, tail = _specimen_series()
    series = {
        "history": list(contest),
        "bookmaker_history": {"draftkings": list(contest)},
        "win_prob_history": {"kalshi": contest + tail, "polymarket": list(contest)},
        "win_prob_sources_meta": {
            "kalshi": {"snapshot_count": 121},
            "polymarket": {"snapshot_count": 117},
        },
        "aggregate_line": list(contest),
        "espn_history": list(tail),
    }
    omitted, payload = _trim(STORED_START, start_is_kickoff=False, **series)

    assert omitted is False
    assert len(payload["history"]) == 117
    assert len(payload["bookmaker_history"]["draftkings"]) == 117
    assert len(payload["win_prob_history"]["kalshi"]) == 121
    assert len(payload["win_prob_history"]["polymarket"]) == 117
    assert len(payload["aggregate_line"]) == 117
    assert payload["win_prob_sources_meta"]["kalshi"]["snapshot_count"] == 121


def test_a_row_with_no_kickoff_is_still_never_trimmed():
    """The pre-existing guard, unchanged: the new arm is additive."""
    stale = [{"timestamp": "2026-05-12T21:20:00+00:00"}]
    omitted, payload = _trim(None, start_is_kickoff=False, history=list(stale))
    assert omitted is False
    assert payload["history"] == stale
