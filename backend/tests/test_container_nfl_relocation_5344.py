"""#5344 — where the authority files each game, and whether a read may act. Pure.

SHIP: when the authoritative schedule moves a game to another week, the next
complete automatic pass moves it and its markets to the correct hub; old links
stay truthful and human withdrawals are not revived. Pillars: MATCHING /
DISCOVER / TRUTH.

The pure half (`container_nfl.placement_snapshot`, `admission_verdict`). The
move itself, its locks and its races are real-PostgreSQL gates in
``tests/integration/test_container_nfl_relocation_5344_pg.py``.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.services.statpal_api import StatPalFixture
from app.utils.container_nfl import (
    ADMIT,
    CONFLICTING_EQUAL_BARRIER,
    EXCLUDED_CONFLICTING_IDENTITY,
    EXCLUDED_NO_WEEK_IDENTITY,
    EXCLUDED_PLACEHOLDER,
    EXCLUDED_WRONG_SEASON,
    REFUSE_DUPLICATE_CONTEST_ROWS,
    REFUSE_PARSE_INCOMPLETE,
    RELOCATION_RULE_VERSION,
    STALE_SNAPSHOT,
    UNAVAILABLE_SEASON_MISMATCH,
    UNAVAILABLE_SEASON_UNKNOWN,
    PriorDecision,
    admission_verdict,
    placement_snapshot,
)

G = datetime(2026, 10, 21, 12, 0, tzinfo=timezone.utc)
W7, W8 = "Regular Season / Week 7", "Regular Season / Week 8"


def _f(cid, kickoff, round_info, home="Eagles", away="Giants", home_id=None, away_id=None):
    return StatPalFixture(
        fixture_id=cid, home_team=home, away_team=away,
        home_team_id=home_id or f"h-{cid}", away_team_id=away_id or f"a-{cid}",
        start_time=kickoff, status="scheduled", round_info=round_info,
    )


def _at(m, d, year=2026):
    return datetime(year, m, d, 17, tzinfo=timezone.utc)


def _season(**over):
    rows = {
        "s701": _f("s701", _at(10, 25), W7),
        "s703": _f("s703", _at(10, 27), W8),
    }
    rows.update(over)
    return [r for r in rows.values() if r is not None]


def _snap(fixtures, **kw):
    kw.setdefault("edition", 2026)
    kw.setdefault("barrier", G)
    kw.setdefault("parse_complete", True)
    return placement_snapshot(fixtures, **kw)


def test_a_complete_read_places_each_contest_in_its_one_week():
    snap = _snap(_season())
    assert snap.complete and snap.refusals == ()
    assert snap.destination("s703") == "nfl-2026-week-8"
    assert snap.destination(" s701 ") == "nfl-2026-week-7"
    assert snap.week_slugs == {"nfl-2026-week-7", "nfl-2026-week-8"}
    assert RELOCATION_RULE_VERSION == "nfl-authority-relocation-v1"
    assert len(RELOCATION_RULE_VERSION) <= 32  # VARCHAR(32)


def test_a_contest_absent_from_the_read_has_no_destination():
    assert _snap(_season(s703=None)).destination("s703") is None


def test_an_incomplete_or_wrong_season_read_places_nothing():
    for snap, reason in (
        (_snap(_season(), parse_complete=False), REFUSE_PARSE_INCOMPLETE),
        (_snap(_season(), edition=2027), UNAVAILABLE_SEASON_MISMATCH),
        (_snap([_f("p1", _at(8, 12), "Pre Season / Week 2")]), UNAVAILABLE_SEASON_UNKNOWN),
    ):
        assert not snap.complete and reason in snap.refusals
        assert snap.placements == {} and snap.week_slugs == frozenset()
        assert snap.destination("s703") is None


def test_every_contest_without_one_week_is_refused_by_name():
    fixtures = _season() + [
        _f("s703", _at(10, 27), W7),  # also filed under Week 7
        _f("s704", _at(10, 27), "Post Season / Wild Card"),
        _f("s705", _at(8, 20, year=2025), "Pre Season / Week 2"),  # last year
        _f("s706", _at(10, 27), W7, home_id="x", away_id="x"),
        _f("s707", _at(10, 27), W7),
    ]
    snap = _snap(fixtures, duplicate_contest_ids=["s707"])
    assert snap.refused == {
        "s703": EXCLUDED_CONFLICTING_IDENTITY,
        "s704": EXCLUDED_NO_WEEK_IDENTITY,
        "s705": EXCLUDED_WRONG_SEASON,
        "s706": EXCLUDED_PLACEHOLDER,
        "s707": REFUSE_DUPLICATE_CONTEST_ROWS,
    }
    assert set(snap.placements) == {"s701"}


def _prior(barrier, to_slug="nfl-2026-week-8", contest="s703", outcome="excluded"):
    return PriorDecision(
        "event", 3, outcome, "authority_relocated",
        {"barrier": barrier.isoformat() if barrier else None, "to_slug": to_slug,
         "contest_id": contest},
    )


def test_a_container_with_no_decision_of_this_rule_admits_any_read():
    assert admission_verdict([], _snap(_season())) == (ADMIT, None)


def test_a_later_barrier_already_applied_makes_an_older_read_stale():
    verdict, detail = admission_verdict([_prior(G + timedelta(seconds=1))], _snap(_season()))
    assert verdict == STALE_SNAPSHOT
    assert detail["applied_barrier"] == (G + timedelta(seconds=1)).isoformat()


def test_an_earlier_barrier_admits_a_newer_read():
    assert admission_verdict([_prior(G - timedelta(microseconds=1))], _snap(_season()))[0] == ADMIT


def test_an_equal_barrier_that_agrees_is_admitted_and_one_that_disagrees_is_refused():
    assert admission_verdict([_prior(G)], _snap(_season()))[0] == ADMIT
    back = _snap(_season(s703=_f("s703", _at(10, 27), W7)))
    verdict, detail = admission_verdict([_prior(G)], back)
    assert verdict == CONFLICTING_EQUAL_BARRIER
    assert detail["recorded_to_slug"] == "nfl-2026-week-8"
    assert detail["this_read_to_slug"] == "nfl-2026-week-7"


def test_an_equal_barrier_an_incomplete_read_cannot_confirm_is_refused():
    snap = _snap(_season(), parse_complete=False)
    assert admission_verdict([_prior(G)], snap)[0] == CONFLICTING_EQUAL_BARRIER


def test_a_pass_with_no_barrier_never_overrides_a_decided_container():
    snap = _snap(_season(), barrier=None)
    assert admission_verdict([], snap)[0] == ADMIT
    assert admission_verdict([_prior(G)], snap)[0] == STALE_SNAPSHOT


def test_a_row_without_a_readable_barrier_is_not_evidence():
    naive = PriorDecision("event", 3, "excluded", "authority_relocated",
                          {"barrier": "2026-10-21T12:00:00", "to_slug": "x"})
    assert admission_verdict([naive, _prior(None)], _snap(_season()))[0] == ADMIT
