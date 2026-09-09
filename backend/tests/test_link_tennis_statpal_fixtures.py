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

A SECOND corpus was added on 2026-09-08 when the doubles arm shipped
(`statpal_tennis_livescores_doubles_20260908.json` + `LIVE_POOL`), because the
day the first was taken had the doubles draw only as a bystander: it is the live
US Open doubles board of that evening, read the same minute as our rows for it.

## what each test can fail on

* the parser reading the payload at all (tennis's `tournament` is a LIST);
* the window being too tight for two placeholder start times to meet;
* a doubles pair reaching the SINGLES matcher, or a singles fixture reaching a
  doubles row — the two draws are joined by different keys and must stay apart;
* a doubles match joining on one agreeing team, which pairs two rounds;
* an ambiguity being resolved instead of reported — the failure that writes a
  wrong anchor and looks like success.
"""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.services.statpal_api import StatPalAPIService
from app.tasks.link_tennis_statpal_fixtures import (
    MATCH_WINDOW,
    SCHEDULE_DAY_OFFSETS,
    VERDICT_AMBIGUOUS,
    VERDICT_DOUBLES_UNREADABLE,
    VERDICT_LINK,
    VERDICT_UNMATCHED,
    classify_fixture,
    doubles_pair_matches,
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
    # ── THE DOUBLES DRAW ────────────────────────────────────────────────────
    # Also production, read with `db-query` on 2026-09-08 over the same days:
    # our four doubles rows for the four doubles fixtures in the pinned payload.
    #
    # Note the spelling. StatPal writes `Galloway/ Goransson` and we hold
    # `Galloway/Goransson` — the space is the difference, which is exactly the
    # kind of thing a token fallback used to paper over by matching on
    # `galloway` alone.
    _row(15301476, "tennis_other", "Galloway/Goransson", "Rojer/Winegar",
         "2026-09-03T04:10:24+00:00"),
    _row(15301493, "tennis_other", "Frantzen/Haase", "Gonzalez/Molteni",
         "2026-09-03T04:10:31+00:00"),
    # THE HALF-AGREEMENT, and the reason the doubles arm cannot be a one-team
    # rule. StatPal's `Guarachi/ Sherif` v `Danilina/ Krunic` starts 15:00 on
    # 9/4; these two rows are inside the window and share EXACTLY ONE team with
    # it. They are different matches of the same draw and must never be linked.
    _row(15304904, "tennis_other", "Maria/Sonmez", "Danilina/Krunic",
         "2026-09-04T23:20:13+00:00"),
    _row(15304900, "tennis_other", "Muhammad/Stollar", "Hozumi/Klepac",
         "2026-09-04T23:20:16+00:00"),
    # CONSTRUCTED, and the only one: the same two players three months earlier.
    # Production holds no such row today, and the window must exclude it anyway.
    _row(15200000, "tennis_atp", "Botic van de Zandschulp", "Alex de Minaur",
         "2026-06-03T12:00:00+00:00"),
]

#: The second corpus: the live US Open doubles board of 2026-09-08 ~23:2xZ and
#: our unlinked rows for it, both read that minute (`_get("tennis",
#: "livescores")` and `db-query`). See `TestTheDoublesDrawOnTheDayItWasBuilt`.
DOUBLES_FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "statpal_tennis_livescores_doubles_20260908.json"
)

LIVE_POOL = [
    _row(15307402, "tennis_other", "Hsieh/Ostapenko", "Mertens/Shnaider",
         "2026-09-07T23:20:16+00:00"),
    _row(15307337, "tennis_other", "Gonzalez/Molteni", "Granollers/Zeballos",
         "2026-09-08T15:00:00+00:00"),
    _row(15307251, "tennis_atp", "Heliovaara / Patten", "Cabral / Tracy",
         "2026-09-08T18:00:00+00:00"),
    _row(15306994, "tennis_atp", "Nys / Roger-Vasselin", "Andreozzi / Guinard",
         "2026-09-08T18:00:00+00:00"),
    _row(15307250, "tennis_atp", "Gonzalez / Molteni", "Granollers / Zeballos",
         "2026-09-08T18:00:00+00:00"),
    _row(15306271, "tennis_atp", "Carpico / Filin N", "Ram / Salisbury",
         "2026-09-08T18:00:00+00:00"),
    _row(15307370, "tennis_wta", "Siniakova / Townsend", "Bucsa / Melichar-Martinez",
         "2026-09-08T22:00:00+00:00"),
    _row(15307368, "tennis_wta", "Hsieh S-W / Ostapenko", "Mertens / Shnaider",
         "2026-09-08T23:10:00+00:00"),
    # The next round, and the crossed near-miss: our HOME is the fixture's AWAY.
    _row(15308219, "tennis_atp", "Ram / Salisbury", "Granollers / Zeballos",
         "2026-09-09T18:00:00+00:00"),
]


def _doubles_fixtures():
    service = StatPalAPIService.__new__(StatPalAPIService)
    return service._parse_tennis_daily(json.loads(DOUBLES_FIXTURE.read_text()))


def _doubles_by_players(name_a: str):
    for f in _doubles_fixtures():
        if f.home_team == name_a:
            return f
    raise AssertionError(f"{name_a} not in the pinned doubles payload")


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
        "home,event_id",
        [("Galloway/ Goransson", 15301476), ("Frantzen/ Haase", 15301493)],
    )
    def test_a_doubles_pair_links_to_our_doubles_row(self, home, event_id):
        """The arm this file used to assert could not exist.

        Both of these are ~35 hours from our row's placeholder clock, so they
        also prove the ±36h window is what carries the doubles draw and not
        only the singles one.
        """
        verdict, matches = classify_fixture(_by_players(home), POOL)
        assert verdict == VERDICT_LINK
        assert [m["id"] for m in matches] == [event_id]

    @pytest.mark.parametrize("home", ["Guarachi/ Sherif", "Payne/ Shumate"])
    def test_one_agreeing_team_is_not_a_match(self, home):
        """The failure a one-team doubles rule commits, on the real rows.

        `Guarachi/ Sherif` v `Danilina/ Krunic` and our `Maria/Sonmez` v
        `Danilina/Krunic` are two matches of one draw eight hours apart. Linking
        them stamps a fixture id onto the wrong match and reports a success.
        """
        verdict, matches = classify_fixture(_by_players(home), POOL)
        assert verdict == VERDICT_UNMATCHED
        assert matches == []

    def test_a_doubles_fixture_never_reaches_a_singles_row(self):
        """The hits that closed this arm: 30+ doubles-to-singles matches.

        Driven through the whole pool rather than asserted on one pair, so a
        widening anywhere in the join has to keep the two draws apart.
        """
        singles_ids = {
            r["id"] for r in POOL if "/" not in r["home"] and "/" not in r["away"]
        }
        for home in ("Galloway/ Goransson", "Frantzen/ Haase", "Guarachi/ Sherif",
                     "Payne/ Shumate"):
            _, matches = classify_fixture(_by_players(home), POOL)
            assert not ({m["id"] for m in matches} & singles_ids)

    def test_a_singles_fixture_never_reaches_a_doubles_row(self):
        """And the same wall from the other side, which nothing asserted before.

        The old refusal was on the FIXTURE, so our doubles rows have always been
        in the candidate pool for a singles fixture to hit. It does not happen
        today; this pins it, because the doubles rows above make the pool a
        genuine test of it for the first time.
        """
        doubles_ids = {
            r["id"] for r in POOL if "/" in r["home"] or "/" in r["away"]
        }
        for home in ("B. Van De Zandschulp", "Y. Wu", "Z. Svajda"):
            _, matches = classify_fixture(_by_players(home), POOL)
            assert not ({m["id"] for m in matches} & doubles_ids)

    @pytest.mark.parametrize(
        "home,away",
        [
            ("Galloway/", "Rojer/Winegar"),
            ("Galloway/Goransson/Rojer", "Rojer/Winegar"),
            ("Galloway/Goransson", "R. Winegar"),
        ],
    )
    def test_a_pair_that_does_not_read_as_two_players_is_receipted(self, home, away):
        """A half-readable pair is the one case that still refuses.

        Third case is the important one: a doubles side against a singles side
        is not a doubles match with a typo, and matching it on the half that
        parses is precisely how a pair lands on one player's row.
        """
        fixture = replace(
            _by_players("Galloway/ Goransson"), home_team=home, away_team=away
        )
        verdict, matches = classify_fixture(fixture, POOL)
        assert verdict == VERDICT_DOUBLES_UNREADABLE
        assert matches == []

    def test_one_team_on_both_sides_of_both_records_is_refused(self):
        """The orientation-decided-by-evaluation-order case, on the pure helper.

        CONSTRUCTED on both sides, and it has to be: the branch is reachable
        only when StatPal AND we list the same team twice for one match, and
        production holds neither half — 0 tennis rows whose two team names fold
        to one pair, measured with `db-query` on 2026-09-08. Kept for
        `pair_matches`' reason: with both orientations true the pairing is
        decided by which arm ran first, which is not a decision.
        """
        assert not doubles_pair_matches(
            ("Rojer/ Winegar", "Rojer/ Winegar"), ("Rojer/Winegar", "Rojer/Winegar")
        )
        # The control: the same helper on the same names, one side changed, is
        # a match — so the refusal above is the duplicated team and not the
        # spelling.
        assert doubles_pair_matches(
            ("Rojer/ Winegar", "Galloway/ Goransson"),
            ("Rojer/Winegar", "Galloway/Goransson"),
        )

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


class TestTheDoublesDrawOnTheDayItWasBuilt:
    """The doubles arm against the live US Open doubles board, 2026-09-08.

    A second real payload rather than more rows on the first, because the day
    the first was taken had the doubles draw only as a bystander. This one is
    `/v1/tennis/livescores` at 2026-09-08 ~23:2xZ trimmed to six matches: the
    three that link, one of the seven ghost/real twins, and BOTH of the day's
    real misses. The event rows are production's, read the same minute.

    Read as a whole it is also the ship's measurement: 12 doubles fixtures live
    on the board, 3 link, 7 are ambiguous because we hold two rows for the match
    (#2878), 2 miss on a name shape (#4095). Nothing in it is fabricated.
    """

    def test_the_pinned_doubles_payload_is_what_the_docstring_says(self):
        fixtures = _doubles_fixtures()
        assert len(fixtures) == 6
        assert all(
            "/" in f.home_team and "/" in f.away_team for f in fixtures
        ), "every match in this corpus is a doubles match"

    @pytest.mark.parametrize(
        "home,event_id",
        [
            ("Nys/ Roger-Vasselin", 15306994),
            ("Heliovaara/ Patten", 15307251),
            ("Siniakova/ Townsend", 15307370),
        ],
    )
    def test_the_three_live_matches_link(self, home, event_id):
        verdict, matches = classify_fixture(_doubles_by_players(home), LIVE_POOL)
        assert verdict == VERDICT_LINK
        assert [m["id"] for m in matches] == [event_id]

    def test_the_ghost_and_the_real_row_are_reported_as_the_twin_they_are(self):
        """Seven of the twelve looked like this on the day. Not ours to resolve.

        One id-less `tennis_other` row at the 15:00 session placeholder and one
        real `tennis_atp` row three hours later, for one match — #2878 in the
        doubles draw. Stamping either one buries it (D35, #2693).
        """
        verdict, matches = classify_fixture(
            _doubles_by_players("Gonzalez/ Molteni"), LIVE_POOL
        )
        assert verdict == VERDICT_AMBIGUOUS
        assert sorted(m["id"] for m in matches) == [15307250, 15307337]

    def test_a_team_listed_the_other_way_round_still_links(self):
        """CONSTRUCTED, minimally: the real linking row with its sides swapped.

        Tennis has no home side — `_parse_tennis_match` calls players[0] "home"
        for want of anything better — so the crossed orientation is a shape the
        join must carry. No live doubles match on 2026-09-08 happened to be
        listed crossed, so the row is a real one with `home` and `away`
        exchanged and nothing else touched.
        """
        swapped = _row(15307251, "tennis_atp", "Cabral / Tracy", "Heliovaara / Patten",
                       "2026-09-08T18:00:00+00:00")
        pool = [c for c in LIVE_POOL if c["id"] != 15307251] + [swapped]
        verdict, matches = classify_fixture(_doubles_by_players("Heliovaara/ Patten"), pool)
        assert verdict == VERDICT_LINK
        assert [m["id"] for m in matches] == [15307251]

    def test_one_agreeing_team_is_not_a_match_in_either_orientation(self):
        """The real crossed near-miss, and the one that decides the whole rule.

        StatPal's `Carpico/ Filin` v `Ram/ Salisbury` (9/8 20:10) against our
        `Ram / Salisbury` v `Granollers / Zeballos` (9/9 18:00): our HOME is the
        fixture's AWAY, 22 hours away and well inside ±36h. It is the next
        round. A rule that accepted one agreeing team in the crossed arm — the
        arm no straight-orientation test can reach — stamps this fixture onto a
        match that has not been played yet.
        """
        pool = [c for c in LIVE_POOL if c["id"] == 15308219]
        verdict, matches = classify_fixture(_doubles_by_players("Carpico/ Filin"), pool)
        assert verdict == VERDICT_UNMATCHED
        assert matches == []

    @pytest.mark.parametrize(
        "home,ours",
        [("Carpico/ Filin", "Carpico / Filin N"), ("Hsieh S-/Ostapenko", "Hsieh S-W / Ostapenko")],
    )
    def test_the_two_real_misses_are_a_name_shape_and_are_reported(self, home, ours):
        """Both of the day's misses, pinned as misses on purpose (#4095).

        Neither is an absence — we hold the match. `doubles_key` is a pair of
        whole folded surnames with no initial slot, so our `Filin N` and
        StatPal's `Filin` are two different surnames, as are `Hsieh S-W` and
        `Hsieh S-`. Widening that key is a change to the identity the AGREEMENT
        row is scored on, so it is filed rather than smuggled in here; this test
        holds the exact shape so the fix has something to flip.
        """
        assert any(
            ours in (c["home"], c["away"]) for c in LIVE_POOL
        ), "the row we miss is in the pool — this is a miss, not an absence"
        verdict, matches = classify_fixture(_doubles_by_players(home), LIVE_POOL)
        assert verdict == VERDICT_UNMATCHED
        assert matches == []


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
