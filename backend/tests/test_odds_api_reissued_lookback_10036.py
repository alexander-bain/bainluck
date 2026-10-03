"""#10036 — a past-start Odds API listing the provider never started stops
printing as an upcoming game.

**SHIP: /search?q=valkyries stops listing a "scheduled" Wings @ Valkyries game
on Oct 2 that was never played (row 15322640); the real game opens once.**
(Pillar: MATCHING.)

The specimens are production's, read 2026-10-03 01:29Z (rows) and 02:20Z
(``/v4/sports/basketball_wnba/scores?daysFrom=3``: carried ``d0e97a8d…`` live
37-44 and ``9c267dad…`` final 108-100, and NOT ``69f130a5…``). The phantom's
one price — BetRivers -315/+245 at 10-01 05:37Z — is on 15322555 from BetRivers
at 06:36Z. The SQL half runs against real Postgres in
``tests/integration/test_odds_api_reissued_twin_8422_pg.py``.
"""

# ruff: noqa: F811 — each pass test takes the imported `sweep` fixture as a parameter.
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.utils.odds_api_reissued_twins import (
    LOOKBACK,
    MIN_LEAD,
    SCORES_DAYS_FROM,
    ReissueRow,
    lookback_ghosts,
    lookback_siblings,
    moneylines_moved,
    plan_lookback_tags,
)
from tests.test_odds_api_reissued_twin_8422 import (
    CANON,
    EFL,
    GHOST,
    NEW,
    OLD,
    FakeService,
    sweep,  # noqa: F401 — the #8422 pass fixture; pytest registers it by this name
)

UTC = timezone.utc
NOW = datetime(2026, 10, 3, 2, 20, tzinfo=UTC)
WNBA = "basketball_wnba"
GSV, DAL = "Golden State Valkyries", "Dallas Wings"
PHANTOM_ID, REAL_ID, PRIOR_ID = (
    "69f130a54c408c0aba7ee9dd43adbdc2",
    "d0e97a8dca4d878e7ceb0b32ed20cfa7",
    "9c267dad149001fe5eccdf229290ec13",
)
BETRIVERS = ("betrivers", -315, 245)


def row(eid, oid, at, seen, *, home=GSV, away=DAL, status="scheduled",
        other_anchor=False, tagged=False, sport=WNBA):
    return ReissueRow(
        event_id=eid, sport_key=sport, home=home, away=away, commence_time=at,
        status=status, odds_api_ids=frozenset({oid}), first_seen_at=seen,
        other_anchor=other_anchor, already_tagged=tagged,
    )


PHANTOM = row(15322640, PHANTOM_ID, datetime(2026, 10, 2, 1, tzinfo=UTC),
              datetime(2026, 10, 1, 5, 37, 56, tzinfo=UTC))
REAL = row(15322555, REAL_ID, datetime(2026, 10, 3, 1, tzinfo=UTC),
           datetime(2026, 10, 1, 4, 1, 37, tzinfo=UTC), status="live")
# Game 1, the other way round (Dallas at home), ESPN-anchored and final.
PRIOR = row(15320420, PRIOR_ID, datetime(2026, 10, 1, 1, tzinfo=UTC),
            datetime(2026, 9, 28, 2, 8, tzinfo=UTC), home=DAL, away=GSV,
            status="completed", other_anchor=True)

SCORES = {WNBA: {REAL_ID, PRIOR_ID, "ee2b184fd8957e70d5dfe20da80f01c5"}}
MONEYLINES = {15322640: frozenset({BETRIVERS}),
              15322555: frozenset({BETRIVERS, ("fanduel", -300, 240)})}


def run(mod, service, *, now=NOW, **kw):
    import asyncio

    return asyncio.run(mod.run_odds_api_reissued_twin_sweep(service=service, now=now, **kw))


def plan(rows=(PHANTOM, REAL, PRIOR), scores=SCORES, moneylines=MONEYLINES, **kw):
    return plan_lookback_tags(list(rows), scores, now=NOW, moneylines=moneylines, **kw)


def reasons(p):
    return [r["reason"] for r in p.refusals]


class TestTheJudgement:
    def test_the_phantom_is_tagged_onto_the_real_game_3(self):
        p = plan()
        assert [(t.duplicate_id, t.canonical_id) for t in p.tags] == [(15322640, 15322555)]
        assert p.tags[0].ghost_odds_api_ids == PHANTOM_ID
        assert p.refusals == []

    def test_without_the_moneyline_the_newer_id_refusal_stands(self):
        p = plan(moneylines={15322640: frozenset({("betrivers", -320, 250)}),
                             15322555: MONEYLINES[15322555]})
        assert p.tags == [] and reasons(p) == ["ghost_15322640_prices_not_on_sibling"]

    def test_no_moneylines_read_is_no_evidence(self):
        p = plan(moneylines={})
        assert p.tags == [] and reasons(p) == ["ghost_15322640_prices_not_on_sibling"]

    def test_an_id_the_provider_started_is_never_a_ghost(self):
        p = plan(scores={WNBA: SCORES[WNBA] | {PHANTOM_ID}})
        assert p.tags == [] and reasons(p) == ["ghost_started"]

    def test_an_unread_scores_feed_refuses(self):
        p = plan(scores={})
        assert p.tags == [] and reasons(p) == ["scores_not_read"]

    def test_a_ghost_holding_a_market_is_refused(self):
        p = plan(holds_markets={15322640})
        assert p.tags == [] and reasons(p) == ["ghost_15322640_holds_markets"]

    def test_another_authority_outranks_the_provider(self):
        ghost = row(15322640, PHANTOM_ID, PHANTOM.commence_time, PHANTOM.first_seen_at,
                    other_anchor=True)
        p = plan(rows=(ghost, REAL))
        assert p.tags == [] and reasons(p) == ["ghost_15322640_has_another_authority"]

    def test_a_sibling_the_provider_does_not_carry_is_not_a_canonical(self):
        p = plan(scores={WNBA: {PRIOR_ID}})
        assert p.tags == [] and reasons(p) == ["no_carried_sibling"]

    def test_two_carried_siblings_are_undecidable(self):
        other = row(15322999, "abc", datetime(2026, 10, 4, 1, tzinfo=UTC),
                    datetime(2026, 10, 1, 4, tzinfo=UTC))
        p = plan(rows=(PHANTOM, REAL, other), scores={WNBA: SCORES[WNBA] | {"abc"}},
                 moneylines={**MONEYLINES, 15322999: frozenset({BETRIVERS})})
        assert p.tags == [] and reasons(p) == ["several_carried_siblings"]

    def test_the_reversed_pairing_is_not_a_sibling(self):
        # Game 1 has Dallas at home: another provider pair, even though carried.
        assert lookback_siblings(PHANTOM, [PHANTOM, PRIOR]) == []
        assert plan(rows=(PHANTOM, PRIOR)).tags == []

    def test_a_canonical_that_is_itself_labelled_is_refused(self):
        real = row(15322555, REAL_ID, REAL.commence_time, REAL.first_seen_at,
                   status="live", tagged=True)
        p = plan(rows=(PHANTOM, real))
        assert p.tags == [] and reasons(p) == ["canonical_is_a_duplicate"]

    def test_an_older_id_still_needs_its_prices_on_the_sibling(self):
        # The listing arm's older-id shortcut does not carry over: after the
        # start, a rained-out series game is absent from /scores too, and its
        # one carried sibling is the NEXT game. Its own prices must be there.
        ghost = row(15322640, PHANTOM_ID, PHANTOM.commence_time,
                    datetime(2026, 10, 1, 3, tzinfo=UTC))
        p = plan(rows=(ghost, REAL), moneylines={})
        assert p.tags == [] and reasons(p) == ["ghost_15322640_prices_not_on_sibling"]
        assert [t.duplicate_id for t in plan(rows=(ghost, REAL)).tags] == [15322640]

    def test_fully_priced_lines_also_carry_the_label(self):
        line = ("fanduel", -300, 240, "-7.5", "165.5")
        p = plan(moneylines={}, book_lines={15322640: frozenset({line}),
                                            15322555: frozenset({line})})
        assert [t.duplicate_id for t in p.tags] == [15322640]

    def test_the_window_is_the_scores_feeds(self):
        just_started = row(1, "a", NOW - MIN_LEAD / 2, NOW - timedelta(days=1))
        too_old = row(2, "b", NOW - LOOKBACK - timedelta(minutes=1), NOW - timedelta(days=4))
        edge = row(3, "c", NOW - LOOKBACK, NOW - timedelta(days=4))
        assert [g.event_id for g in lookback_ghosts([just_started, too_old, edge], now=NOW)] == [3]
        # The window must sit inside what daysFrom actually returns.
        assert LOOKBACK < timedelta(days=SCORES_DAYS_FROM)

    def test_a_live_or_settled_row_is_never_a_ghost(self):
        assert lookback_ghosts([REAL, PRIOR], now=NOW) == []

    def test_moneylines_moved_needs_evidence(self):
        assert moneylines_moved(frozenset(), frozenset({BETRIVERS})) is False
        assert moneylines_moved(frozenset({BETRIVERS}), frozenset({BETRIVERS})) is True


class TestThePass:
    def test_the_phantom_is_tagged_and_the_feed_is_read_once(self, sweep):
        mod, state = sweep
        state["rows"] = [CANON]
        state["lb_rows"] = [PHANTOM, REAL, PRIOR]
        state["moneylines"] = MONEYLINES
        service = FakeService(scored=SCORES)
        out = run(mod, service)
        assert out["terminal"] == "complete" and state["written"] == [15322640]
        assert service.score_calls == [(WNBA, SCORES_DAYS_FROM)]
        assert out["lookback"]["pairs_found"] == 1 and out["lookback"]["ghosts_examined"] == 1

    def test_a_quiet_pass_reads_no_scores(self, sweep):
        mod, state = sweep
        state["rows"] = [CANON]
        state["lb_rows"] = [REAL, PRIOR]
        service = FakeService(scored=SCORES)
        out = run(mod, service)
        assert out["terminal"] == "complete" and service.score_calls == []

    def test_a_ghost_holding_markets_is_refused_in_the_pass(self, sweep):
        mod, state = sweep
        state["rows"] = [CANON]
        state["lb_rows"] = [PHANTOM, REAL]
        state["moneylines"] = MONEYLINES
        state["holders"] = {15322640}
        out = run(mod, FakeService(scored=SCORES))
        assert state["written"] == [] and out["lookback"]["refusals"] == 1

    def test_a_failed_scores_read_is_damage_not_a_quiet_zero(self, sweep):
        mod, state = sweep
        state["rows"] = [CANON]
        state["lb_rows"] = [PHANTOM, REAL]
        state["moneylines"] = MONEYLINES
        out = run(mod, FakeService(scores_fail={WNBA}))
        assert out["terminal"] == "partial" and state["written"] == []
        assert any("scores" in e and WNBA in e for e in out["errors"])

    def test_a_failed_lookback_read_leaves_the_listing_arm_working(self, sweep):
        mod, state = sweep
        state["lb_fail"] = True
        out = run(mod, FakeService({EFL: {NEW}}))
        assert out["terminal"] == "partial" and state["written"] == [GHOST.event_id]
        assert any("lookback rows" in e for e in out["errors"])

    def test_a_label_whose_id_the_scores_feed_carries_is_lifted(self, sweep):
        mod, state = sweep
        state["rows"] = [CANON]
        state["lb_rows"] = [
            row(15322641, "zzz", PHANTOM.commence_time, PHANTOM.first_seen_at),
            REAL,
        ]
        state["banked"] = {15322640: (WNBA, frozenset({PHANTOM_ID}), 15322555)}
        out = run(mod, FakeService(scored={WNBA: SCORES[WNBA] | {PHANTOM_ID}}))
        assert state["lifted"] == {15322640: 15322555} and out["lifted"] == 1

    def test_the_forward_arm_is_unchanged(self, sweep):
        mod, state = sweep
        out = run(mod, FakeService({EFL: {NEW}}))
        assert out["terminal"] == "complete" and state["written"] == [GHOST.event_id]
        assert GHOST.odds_api_ids == {OLD}
