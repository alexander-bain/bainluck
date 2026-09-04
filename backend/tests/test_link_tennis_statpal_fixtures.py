"""The forward tennis linker's decision, driven by a REAL StatPal payload. #2867.

`app/tasks/link_tennis_statpal_fixtures.classify_fixture` is the whole judgement
the task makes: which of our rows, if any, is this StatPal match. It is pure, so
these tests drive the code that runs rather than a mock that agrees with whatever
it is told.

## the corpus is a real response, trimmed, not a fabrication

`tests/fixtures/statpal_tennis_livescores_20260903.json` is a slice of the actual
`/v1/tennis/livescores` body of 2026-09-03 23:5xZ: 7 singles carrying the hard
name shapes that were live at the time (`Y. Bu`, `B. Van De Zandschulp`,
`T. M. Etcheverry`, `D. Merida Aguilar`, `Y. Wu`, `Z. Svajda`) and 4 doubles.
A fabricated payload would agree with the parser by construction; this one has
already disagreed with three earlier attempts at it.

The event rows are likewise real — id, sport key, names and commence times as
production held them the same evening, including the `tennis_other` twin of
`Y. Bu` v `M. Zheng` that makes one fixture genuinely ambiguous.

## what each test can fail on

* the parser reading the payload at all (tennis's `tournament` is a LIST);
* the window being too tight for two placeholder start times to meet;
* a doubles pair reaching the matcher;
* an ambiguity being resolved instead of reported — the failure that writes a
  wrong anchor and looks like success.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from app.services.statpal_api import StatPalAPIService
from app.tasks.link_tennis_statpal_fixtures import (
    MATCH_WINDOW,
    SCHEDULE_DAY_OFFSETS,
    VERDICT_AMBIGUOUS,
    VERDICT_DOUBLES,
    VERDICT_LINK,
    VERDICT_UNMATCHED,
    classify_fixture,
)

FIXTURE = (
    Path(__file__).parent / "fixtures" / "statpal_tennis_livescores_20260903.json"
)


def _fixtures():
    service = StatPalAPIService.__new__(StatPalAPIService)  # no HTTP client needed
    return service._parse_tennis_daily(json.loads(FIXTURE.read_text()))


def _by_players(name_a: str):
    for f in _fixtures():
        if f.home_team == name_a:
            return f
    raise AssertionError(f"{name_a} not in the pinned payload")


def _row(event_id, sport_key, home, away, when, **extra):
    return {
        "id": event_id,
        "sport_key": sport_key,
        "home": home,
        "away": away,
        "commence_time": datetime.fromisoformat(when),
        "sport_id": 1,
        **extra,
    }


#: Production rows, 2026-09-03 evening, verbatim.
POOL = [
    _row(15301172, "tennis_atp_us_open", "Bu Yunchaokete", "Michael Zheng",
         "2026-09-03T22:05:00+00:00"),
    _row(15302919, "tennis_other", "Yunchaokete Bu", "Michael Zheng",
         "2026-09-03T21:05:00+00:00"),
    _row(15301145, "tennis_atp_us_open", "Alex Michelsen", "Daniel Merida Aguilar",
         "2026-09-04T20:30:00+00:00"),
    _row(15301300, "tennis_atp_us_open", "Botic van de Zandschulp", "Alex de Minaur",
         "2026-09-03T22:05:00+00:00"),
    _row(15301301, "tennis_atp_us_open", "Tomas Martin Etcheverry", "Mariano Navone",
         "2026-09-03T21:40:00+00:00"),
    _row(15301302, "tennis_atp_us_open", "Wu Yibing", "Carlos Alcaraz",
         "2026-09-04T23:00:00+00:00"),
    _row(15301303, "tennis_wta_us_open", "Maria Sakkari", "Yuliia Starodubtseva",
         "2026-09-03T22:20:00+00:00"),
    # A bystander: right names, wrong week. The window must exclude it.
    _row(15200000, "tennis_atp", "Botic van de Zandschulp", "Alex de Minaur",
         "2026-06-03T12:00:00+00:00"),
]


class TestThePinnedPayloadIsWhatTheDocstringSays:
    """A corpus check first — every assertion below is worthless if this drifts."""

    def test_the_parser_reads_the_list_shaped_tournament(self):
        fixtures = _fixtures()
        assert len(fixtures) == 11, (
            "tennis serves `tournament` as a LIST where every other sport serves "
            "a dict; a parser that walks the dict shape returns 0 here"
        )

    def test_it_carries_the_hard_shapes_and_the_doubles(self):
        names = {f.home_team for f in _fixtures()} | {f.away_team for f in _fixtures()}
        assert {"Y. Bu", "B. Van De Zandschulp", "T. M. Etcheverry", "Y. Wu"} <= names
        assert any("/" in n for n in names), "the doubles arm needs doubles"

    def test_every_fixture_has_an_id_and_a_start_time(self):
        for f in _fixtures():
            assert f.fixture_id and f.fixture_id.isdigit()
            assert f.start_time is not None


class TestTheVerdicts:
    def test_an_ordinary_fixture_links_to_exactly_one_row(self):
        verdict, matches = classify_fixture(_by_players("B. Van De Zandschulp"), POOL)
        assert verdict == VERDICT_LINK
        assert [m["id"] for m in matches] == [15301300]

    def test_the_family_name_first_row_links(self):
        verdict, matches = classify_fixture(_by_players("Y. Wu"), POOL)
        assert verdict == VERDICT_LINK
        assert matches[0]["id"] == 15301302

    def test_a_fixture_a_day_out_still_links(self):
        """`A. Michelsen` v `D. Merida Aguilar` is listed today, played tomorrow.

        StatPal stamps unplayed tennis at a placeholder hour and backfills the
        real minute afterwards, so the gap here is between two placeholders and
        not a disagreement about when the match is.
        """
        verdict, matches = classify_fixture(_by_players("A. Michelsen"), POOL)
        assert verdict == VERDICT_LINK
        assert matches[0]["id"] == 15301145

    @pytest.mark.parametrize(
        "home", ["Galloway/ Goransson", "Guarachi/ Sherif", "Frantzen/ Haase"]
    )
    def test_every_doubles_pair_is_refused_before_matching(self, home):
        verdict, matches = classify_fixture(_by_players(home), POOL)
        assert verdict == VERDICT_DOUBLES
        assert matches == []

    def test_the_real_twin_is_reported_not_resolved(self):
        """Two of our rows hold `Bu Yunchaokete` v `Michael Zheng`, one hour apart.

        This is the failure that looks like success: picking either row writes a
        plausible anchor and buries a duplicate. The verdict must be AMBIGUOUS and
        must carry BOTH rows, because a receipt saying "2 candidates" is a count.
        """
        verdict, matches = classify_fixture(_by_players("Y. Bu"), POOL)
        assert verdict == VERDICT_AMBIGUOUS
        assert sorted(m["id"] for m in matches) == [15301172, 15302919]

    def test_a_fixture_we_do_not_hold_is_unmatched_not_forced(self):
        verdict, matches = classify_fixture(_by_players("Z. Svajda"), POOL)
        assert verdict == VERDICT_UNMATCHED
        assert matches == []

    def test_the_same_two_players_in_a_different_month_are_out_of_window(self):
        """The bystander row shares both names and differs only by three months.

        Without a window this is a second candidate and every fixture in the draw
        becomes ambiguous with its own rematch.
        """
        _, matches = classify_fixture(_by_players("B. Van De Zandschulp"), POOL)
        assert 15200000 not in [m["id"] for m in matches]

    def test_a_fixture_with_no_start_time_is_unmatched_rather_than_unbounded(self):
        f = _by_players("B. Van De Zandschulp")
        object.__setattr__(f, "start_time", None) if hasattr(
            f, "__dataclass_fields__"
        ) else setattr(f, "start_time", None)
        verdict, matches = classify_fixture(f, POOL)
        assert verdict == VERDICT_UNMATCHED
        assert matches == []

    def test_a_row_with_no_commence_time_never_becomes_a_candidate(self):
        pool = [dict(POOL[3], commence_time=None)]
        verdict, _ = classify_fixture(_by_players("B. Van De Zandschulp"), pool)
        assert verdict == VERDICT_UNMATCHED


class TestTheWindow:
    def test_it_is_wide_enough_for_two_placeholders_to_meet(self):
        """36h is a decision, not a default, and it is written down here too.

        StatPal's session placeholder is 15:00 UTC and ours is midnight UTC. Any
        window under 15 hours reads those as different days for a match both
        sides agree is the same one.
        """
        assert MATCH_WINDOW >= timedelta(hours=15)

    def test_a_row_exactly_at_the_boundary_is_included(self):
        f = _by_players("B. Van De Zandschulp")
        edge = _row(
            999, "tennis_atp", "Botic van de Zandschulp", "Alex de Minaur",
            (f.start_time + MATCH_WINDOW).isoformat(),
        )
        verdict, matches = classify_fixture(f, [edge])
        assert verdict == VERDICT_LINK

    def test_a_row_one_second_past_it_is_not(self):
        f = _by_players("B. Van De Zandschulp")
        past = _row(
            999, "tennis_atp", "Botic van de Zandschulp", "Alex de Minaur",
            (f.start_time + MATCH_WINDOW + timedelta(seconds=1)).isoformat(),
        )
        verdict, _ = classify_fixture(f, [past])
        assert verdict == VERDICT_UNMATCHED


class TestTheReadPlan:
    def test_it_asks_for_d1_and_d2_and_never_d0(self):
        """There is no `daily/d0` — it answers HTTP 500, not an empty envelope.

        A linker that asked for it would raise on every pass through the
        authority door, which is why today's play comes from `livescores`.
        """
        assert 0 not in SCHEDULE_DAY_OFFSETS
        assert SCHEDULE_DAY_OFFSETS == (1, 2)

    def test_the_offsets_are_ones_the_service_accepts(self):
        for offset in SCHEDULE_DAY_OFFSETS:
            assert offset in StatPalAPIService.TENNIS_DAILY_OFFSETS
