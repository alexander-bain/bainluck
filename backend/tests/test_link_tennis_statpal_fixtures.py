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
from datetime import datetime, timedelta, timezone
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
    statpal_read_span,
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


#: Production rows as `events` held them at 2026-09-03 23:5xZ — real ids, real
#: sport keys, real names, real commence times. Read out of production with
#: `db-query`; only the last entry is constructed, and it says so.
POOL = [
    _row(15301172, "tennis_atp_us_open", "Bu Yunchaokete", "Michael Zheng",
         "2026-09-03T22:05:00+00:00"),
    # The twin. Same match, the player's name written the other way round, one
    # hour earlier, under the generic key.
    _row(15302919, "tennis_other", "Yunchaokete Bu", "Michael Zheng",
         "2026-09-03T21:05:00+00:00"),
    _row(15301145, "tennis_atp_us_open", "Alex Michelsen", "Daniel Merida Aguilar",
         "2026-09-04T20:30:00+00:00"),
    _row(15301180, "tennis_atp_us_open", "Botic van de Zandschulp", "Alex de Minaur",
         "2026-09-03T22:00:58+00:00"),
    _row(15301245, "tennis_atp_us_open", "Tomas Martin Etcheverry", "Mariano Navone",
         "2026-09-04T20:00:00+00:00"),
    _row(15301243, "tennis_atp_us_open", "Wu Yibing", "Carlos Alcaraz",
         "2026-09-04T17:00:00+00:00"),
    _row(15300832, "tennis_wta_us_open", "Maria Sakkari", "Yuliia Starodubtseva",
         "2026-09-03T22:13:53+00:00"),
    _row(15301164, "tennis_atp_us_open", "Zachary Svajda", "Arthur Gea",
         "2026-09-03T22:26:00+00:00"),
    # A PROP MARKET ingested as an event row, verbatim from production. It shares
    # one player with the real match and sits 23 hours away, so it is a live
    # candidate for the same fixture — and it must never win one.
    _row(15304077, "tennis_other", "Zachary Svajda", "Arthur Gea - Exact Score",
         "2026-09-02T23:45:02+00:00"),
    # CONSTRUCTED, and the only one: the same two players three months earlier.
    # Production holds no such row today, and the window must exclude it anyway.
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
        assert [m["id"] for m in matches] == [15301180]

    def test_the_family_name_first_row_links(self):
        verdict, matches = classify_fixture(_by_players("Y. Wu"), POOL)
        assert verdict == VERDICT_LINK
        assert matches[0]["id"] == 15301243

    def test_a_prop_market_row_never_wins_a_fixture(self):
        """`"Arthur Gea - Exact Score"` is a real row in `events`, not a match.

        It shares a player with the live match, sits inside the window, and would
        be a second candidate under any rule that matched on one name or on a
        surname appearing ANYWHERE. The surname must END or BEGIN our name, so
        the trailing `- Exact Score` refuses it — and the verdict stays LINK
        rather than becoming an ambiguity that blocks a real link.
        """
        verdict, matches = classify_fixture(_by_players("Z. Svajda"), POOL)
        assert verdict == VERDICT_LINK
        assert [m["id"] for m in matches] == [15301164]

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
        """Production held all seven singles, so this row is REMOVED to make one.

        The nearest thing to a real specimen: with the real row gone, the prop
        row `"Arthur Gea - Exact Score"` is the only thing left carrying either
        player, and a matcher looking for something to link would take it.
        """
        pool = [c for c in POOL if c["id"] != 15301164]
        verdict, matches = classify_fixture(_by_players("Z. Svajda"), pool)
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


class TestTheSpanWeClaimToHaveRead:
    """#3644. The span the agreement row divides by must be days we ASKED about.

    `livescores` is a state query, not a day's schedule, and it keeps returning
    matches for days after they finish. Production 2026-09-06: it dragged the
    published span's start to `2026-09-04T11:10Z`, into two days that
    `SCHEDULE_DAY_OFFSETS` never requests, and every row of ours in that stretch
    was counted as a miss *inside StatPal's span* — a disagreement with a list
    nobody asked for. `ours_covered_in_span_pct` published 13.91% as though it
    were a coverage verdict.
    """

    def test_it_starts_today_and_not_at_whatever_livescores_dredged_up(self):
        """The defect, stated as a date.

        `2026-09-04` and `2026-09-05` are the two days the production span
        wrongly reached back into. Neither may be inside the span we claim.
        """
        first, _ = statpal_read_span(datetime(2026, 9, 6, 11, 10, tzinfo=timezone.utc))
        assert first == datetime(2026, 9, 6, 0, 0, tzinfo=timezone.utc)
        assert first > datetime(2026, 9, 5, 23, 59, tzinfo=timezone.utc)

    def test_it_reaches_the_last_instant_of_the_last_day_requested(self):
        """End-INCLUSIVE, and this is the assertion that says so.

        `day + timedelta(days=max_offset)` ends at that day's MIDNIGHT, which
        excludes all but the first instant of `d2` — the day whose unplayed
        fixtures are most of what `d2` is asked for. The bug would be invisible
        in any test that only checked the start.
        """
        now = datetime(2026, 9, 6, 11, 10, tzinfo=timezone.utc)
        _, last = statpal_read_span(now)
        assert last >= datetime(2026, 9, 8, 23, 59, 59, tzinfo=timezone.utc)
        assert last < datetime(2026, 9, 9, 0, 0, tzinfo=timezone.utc)

    def test_the_span_tracks_the_offsets_it_is_derived_from(self, monkeypatch):
        """Change what we ask for and the span must follow, or it lies.

        A span written out as a literal would keep claiming the old window
        forever after someone widened the read — and it would keep passing the
        two tests above, which is exactly why this one exists.
        """
        import app.tasks.link_tennis_statpal_fixtures as mod

        now = datetime(2026, 9, 6, 11, 10, tzinfo=timezone.utc)
        monkeypatch.setattr(mod, "SCHEDULE_DAY_OFFSETS", (1, 2, 3, 4))
        _, last = mod.statpal_read_span(now)
        assert last >= datetime(2026, 9, 10, 23, 59, 59, tzinfo=timezone.utc)
        assert last < datetime(2026, 9, 11, 0, 0, tzinfo=timezone.utc)

    def test_a_non_utc_clock_does_not_move_the_day_boundary(self):
        """The offsets are UTC days, so the span must be too.

        Handed a `now` in a zone whose local date differs from the UTC date, a
        naive `.replace(hour=0)` floors to the LOCAL midnight and shifts the
        whole span by up to a day — silently, and only for part of the day
        (gotcha #44's shape, in the span rather than in a fixture).
        """
        utc_now = datetime(2026, 9, 6, 2, 30, tzinfo=timezone.utc)
        # 2026-09-05 22:30 in UTC-4 — the same instant, the previous local date.
        other = utc_now.astimezone(timezone(timedelta(hours=-4)))
        assert other.date() != utc_now.date()
        assert statpal_read_span(other) == statpal_read_span(utc_now)
