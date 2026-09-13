"""Soccer's arm of the v1 StatPal stamper: the read, the spec, the join. #3366 / D50.

`test_soccer_team_matching_3366.py` proves the RULE (67 of a pinned 90 where
equality gets 17). This file proves the three things the CALLER had to grow
before that rule could be used, each of which soccer answers differently from
all three incumbent leagues:

  1. **the READ** — `/v2/soccer/matches/daily?offset=N`, three boards, one call
     each, where NBA/NHL/MLB take one `season-schedule` call;
  2. **the ANCHOR** — `fallback_id_3`, where the other three use `id`;
  3. **the AGREEMENT JOIN** — `pair_soccer_sides`, where the other three use the
     default key join.

Every number here is pinned against a real payload or the real corpus, and the
two that matter most are stated as CONTROLS rather than as bare assertions: the
soccer join is asserted to differ from the default join on the same inputs, and
the soccer pair rule is asserted to accept a pair the incumbent rule refuses.
An assertion that would also pass on the old behaviour proves nothing.
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services.anchor_channel import WROTE
from app.services.statpal_api import (
    StatPalAPIService,
    StatPalFixture,
    StatPalUpstreamError,
)
from app.tasks import reconcile_shared_fixture_ids as reconcile
from app.tasks import stamp_v1_statpal_fixtures as task
from app.utils.authority_agreement import Side, build_agreement_row
from app.utils.authority_soccer_agreement import (
    REFUSAL_TWO_FIXTURES,
    REFUSAL_TWO_ROWS,
    SOCCER_REFUSAL_NAMES,
    names_a_club,
    pair_soccer_sides,
)
from app.utils.nfl_team_matching import normalize_team, pair_matches

#: The two statements #5779's look-back arm may run, read from the module that
#: owns them so a rename cannot leave these drivers silently answering rows to a
#: query that asks for ids.
_LOOKBACK_SQL = (
    reconcile.SHARED_FIXTURE_IDS_BY_SPORT,
    reconcile.SHARED_FIXTURE_IDS_BY_SPORT_PREFIX,
)


class _EmptyResult:
    """No contest in these drivers' inventories is held twice."""

    rowcount = 0

    def fetchall(self):
        return []

    def all(self):
        return []


FIXTURES = Path(__file__).parent / "fixtures"
DAILY_OFFSET1 = (
    FIXTURES / "statpal_soccer_matches_daily_offset1_20260907_fullcensus.json"
)
LIVE_BOARD = FIXTURES / "statpal_soccer_matches_live_20260907_fullcensus.json"
JOIN_CORPUS = FIXTURES / "statpal_soccer_join_corpus_20260907.json"

UTC = timezone.utc


def _crontab_minutes(schedule) -> set[int]:
    """Every minute of the hour a crontab fires on.

    Expanded rather than string-compared because the beat schedule states a
    minute in three different notations — `6`, `"*/15"`, `"0,30"` — and a guard
    that only understood the literal form would silently pass a StatPal reader
    running every fifteen minutes straight through soccer's window.
    """
    raw = str(schedule._orig_minute)
    minutes: set[int] = set()
    for part in raw.split(","):
        part = part.strip()
        if part == "*":
            return set(range(60))
        if part.startswith("*/"):
            minutes.update(range(0, 60, int(part[2:])))
        elif "-" in part:
            span, _, step = part.partition("/")
            lo, _, hi = span.partition("-")
            minutes.update(range(int(lo), int(hi) + 1, int(step or 1)))
        else:
            minutes.add(int(part))
    return minutes


@pytest.fixture(scope="module")
def daily_body() -> dict:
    return json.loads(DAILY_OFFSET1.read_text())


@pytest.fixture(scope="module")
def live_body() -> dict:
    return json.loads(LIVE_BOARD.read_text())


@pytest.fixture(scope="module")
def corpus() -> dict:
    return json.loads(JOIN_CORPUS.read_text())


def _service() -> StatPalAPIService:
    """A service object without its network constructor. Parsers only."""
    return StatPalAPIService.__new__(StatPalAPIService)


def _row(event_id, home, away, start, held=None, sport="soccer_epl"):
    return {
        "id": event_id,
        "home": home,
        "away": away,
        "commence_time": start,
        "statpal_fixture_id": held,
        "status": "scheduled",
        "sport_key": sport,
    }


def _fixture(fid, home, away, start, *, fallback=None):
    return StatPalFixture(
        fixture_id=fid,
        fallback_id_3=fallback,
        home_team=home,
        away_team=away,
        start_time=start,
    )


class TestTheDailyBoardIsRead:
    """`matches/daily?offset=N` — the read `LeagueSpec` grew a field for."""

    def test_the_offset_one_census_parses_every_row_with_an_anchor(self, daily_body):
        """274 rows, 274 anchors, 274 distinct. The anchor is not sometimes-there."""
        fixtures = _service()._parse_soccer_daily_matches(daily_body)
        assert len(fixtures) == 274
        anchors = [f.fallback_id_3 for f in fixtures]
        assert all(anchors), "a blank anchor is #2963's 8,272-row repair waiting"
        assert len(set(anchors)) == 274

    def test_the_board_is_not_a_utc_day_and_that_is_why_three_are_read(
        self, daily_body
    ):
        """~25.5h, 23:00Z to 00:30Z — the measurement behind `schedule_day_offsets`.

        If a board were one UTC day, offsets 1 and 2 would reach the end of the
        second day and the third would be padding. It is not, so they do not,
        and it is not.
        """
        starts = [
            f.start_time for f in _service()._parse_soccer_daily_matches(daily_body)
        ]
        assert min(starts) == datetime(2026, 9, 7, 23, 0, tzinfo=UTC)
        assert max(starts) == datetime(2026, 9, 9, 0, 30, tzinfo=UTC)
        assert max(starts) - min(starts) > timedelta(hours=25)

    def test_the_daily_parser_refuses_a_live_body_rather_than_absorbing_it(
        self, live_body
    ):
        """A board section is matched by SHAPE, and `live_matches` is not it.

        This is the guard on #3800: `offset=0` answers 200 with a `live_matches`
        body. Silently parsing it would mean a caller asking for a schedule
        received whatever was in play, and could not tell.
        """
        assert _service()._parse_soccer_daily_matches(live_body) == []
        assert len(_service()._parse_soccer_live_matches(live_body)) == 195

    def test_the_two_boards_share_one_row_parser(self, daily_body, live_body):
        """Same fields, same reading — so a fix to one is a fix to both.

        Asserted on the two behaviours the shared parser exists for: scores come
        from `goals` (an unplayed match serves `"?"`, which must not read as 0),
        and a wall-clock status is a KICKOFF TIME, not a period.
        """
        for body, parse in (
            (daily_body, _service()._parse_soccer_daily_matches),
            (live_body, _service()._parse_soccer_live_matches),
        ):
            unplayed = [f for f in parse(body) if f.status == "scheduled"]
            assert unplayed, "expected unplayed fixtures on both boards"
            assert all(f.home_score is None for f in unplayed)
            assert all(f.raw_status is None for f in unplayed)

    @pytest.mark.asyncio
    async def test_offset_zero_is_refused_by_name_not_by_range(self):
        """It is a valid offset that returns the WRONG THING (#3800), so the
        message has to say which door to use instead of quoting a range."""
        with pytest.raises(ValueError) as e:
            await _service().get_schedule_fixtures("soccer", day_offset=0)
        assert "matches/live" in str(e.value)
        assert "get_live_fixtures" in str(e.value)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("offset", [None, 8, -8, 99])
    async def test_an_unserved_offset_is_a_caller_bug_not_an_absence(self, offset):
        """±8 is HTTP 400 upstream, measured. A caller bug and an upstream
        absence must never arrive as the same empty list (gotcha #53)."""
        with pytest.raises(ValueError):
            await _service().get_schedule_fixtures("soccer", day_offset=offset)

    @pytest.mark.asyncio
    async def test_a_failed_read_raises_rather_than_returning_empty(self, monkeypatch):
        service = _service()

        async def _dead(*a, **k):
            return None

        monkeypatch.setattr(service, "_get", _dead)
        with pytest.raises(StatPalUpstreamError) as e:
            await service.get_schedule_fixtures("soccer", day_offset=1)
        assert "offset=1" in str(e.value), "the receipt must name the board it lost"

    @pytest.mark.asyncio
    async def test_the_offset_reaches_the_url_it_says_it_does(self, monkeypatch):
        """The one thing a parser test cannot see: which board was requested."""
        service = _service()
        asked: list[tuple] = []

        async def _spy(sport, endpoint, params=None):
            asked.append((sport, endpoint, params))
            return {"matches_10_09_2026": {"league": []}}

        monkeypatch.setattr(service, "_get", _spy)
        await service.get_schedule_fixtures("soccer", day_offset=3)
        assert asked == [("soccer", "matches/daily", {"offset": 3})]


class TestTheSoccerLeagueSpec:
    """The four questions soccer answers differently, each a NAMED field."""

    def test_it_reads_three_daily_boards_where_the_v1_sports_read_one_schedule(self):
        assert task.SOCCER.schedule_day_offsets == (1, 2, 3)
        for spec in (task.NBA, task.NHL, task.MLB):
            assert spec.schedule_day_offsets == ()

    def test_both_of_its_boards_anchor_on_fallback_id_3(self):
        """The FIRST league whose schedule anchor is not `id` — which is why
        `schedule_anchor_field` exists rather than being derived from the live one."""
        assert task.SOCCER.schedule_anchor_field == task.ANCHOR_IS_FALLBACK_ID_3
        assert task.SOCCER.live_anchor_field == task.ANCHOR_IS_FALLBACK_ID_3
        assert task.NBA.schedule_anchor_field == task.LIVE_ANCHOR_IS_ID
        assert task.MLB.live_anchor_field == task.LIVE_ANCHOR_IS_ODDS_ID

    def test_the_anchor_read_takes_fallback_id_3_and_never_main_id(self):
        """`main_id` collides ACROSS competitions (CERT-2189). Anchoring on it
        is the bug this field exists to make impossible, so the two are given
        DIFFERENT values here — a fixture where they agreed would pass either way.
        """
        f = _fixture(
            "2026090846246",
            "Everton",
            "Wolves",
            datetime(2026, 9, 9, 18, 45, tzinfo=UTC),
            fallback="9546789",
        )
        assert task.schedule_anchor_id(task.SOCCER, f) == "9546789"
        assert task.live_anchor_id(task.SOCCER, f) == "9546789"
        assert task.schedule_anchor_id(task.NBA, f) == "2026090846246"

    def test_a_blank_anchor_is_none_and_is_never_a_blank_string(self):
        f = _fixture("2026090846246", "A", "B", None, fallback="")
        assert task.schedule_anchor_id(task.SOCCER, f) is None

    def test_its_sport_key_is_a_prefix_because_ours_is_forty_keys_and_theirs_is_one(
        self,
    ):
        assert task.SOCCER.sport_key_is_prefix is True
        assert task.SOCCER.sport_key == "soccer"
        for spec in (task.NBA, task.NHL, task.MLB):
            assert spec.sport_key_is_prefix is False

    def test_it_is_not_in_LEAGUES_because_LEAGUES_is_keyed_on_OUR_sport_key(self):
        """Absence with a reason, so it reads as a decision and not an omission.

        This absence used to carry a second meaning — soccer had no runner and
        no beat entry — and that half is now false: it runs hourly at :06. What
        survives is the narrow reason, which is about KEYS and nothing else.
        `LEAGUES` is keyed on our `sports.key`; `SOCCER.sport_key` is `"soccer"`,
        a StatPal-side prefix spanning ~40 of ours. Being scheduled did not give
        soccer a key this dict could hold, so this assertion is unchanged while
        the sentence next to it is not.
        """
        assert not any(k.startswith("soccer") for k in task.LEAGUES)
        assert set(task.LEAGUES) == {"basketball_nba", "icehockey_nhl", "baseball_mlb"}
        assert task.SOCCER.sport_key_is_prefix is True
        # The half that is now false, pinned in its true direction so this test
        # can never again be read as "soccer does not run".
        from app.tasks import celery_app

        scheduled = {e["task"] for e in celery_app.conf.beat_schedule.values()}
        assert "app.tasks.stamp_soccer_statpal_fixtures" in scheduled

    def test_every_spec_names_a_pair_rule_and_a_fold(self):
        """`LeagueSpec.pair_rule` has NO default, so a half-configured sport
        cannot exist — this pins that the dataclass still refuses one."""
        for spec in (task.NBA, task.NHL, task.MLB, task.SOCCER):
            assert callable(spec.pair_rule)
            assert callable(spec.normalize)
        with pytest.raises(TypeError):
            task.LeagueSpec(  # type: ignore[call-arg]
                sport_key="soccer_epl",
                statpal_sport="soccer",
                label="half-configured",
                stats_id_coverage=task.STATS_ID_ON_NO_FIXTURE,
                stats_id_measured="",
            )

    def test_a_league_with_a_non_default_pair_rule_also_names_a_join_strategy(self):
        """The coupling that keeps the ledger row measuring what the pass writes.

        A row built by the default key join over a sport whose links are made by
        a subset rule publishes the gap between two of OUR definitions as if it
        were a disagreement with StatPal.
        """
        for spec in (task.NBA, task.NHL, task.MLB, task.SOCCER):
            if spec.pair_rule is pair_matches:
                assert spec.join_strategy is None
            else:
                assert spec.join_strategy is not None, (
                    f"{spec.label} matches on a rule the default key join does "
                    "not implement, so its agreement row would measure a "
                    "different relation from the one it links on"
                )


class TestTheCandidateQuerySelectsEveryOneOfOurSoccerKeys:
    """`s.key = 'soccer'` selects nothing; our rows are `soccer_epl` and ~40 more."""

    @pytest.mark.asyncio
    async def test_soccer_selects_by_prefix_and_the_wildcard_is_a_BIND(self):
        captured: dict = {}

        class _Session:
            async def execute(self, stmt, params):
                captured["sql"] = str(stmt)
                captured["params"] = params
                return _Result()

        class _Result:
            def fetchall(self):
                return []

        await task._candidates(
            _Session(),
            task.SOCCER,
            datetime(2026, 9, 7, tzinfo=UTC),
            datetime(2026, 9, 11, tzinfo=UTC),
        )
        assert "s.key LIKE :sport_key" in captured["sql"]
        assert captured["params"]["sport_key"] == "soccer%"
        # gotcha #45: a pattern spliced into the text() would not be a bind, and
        # `%` inside `text()` is where that goes wrong.
        assert "soccer%" not in captured["sql"]

    @pytest.mark.asyncio
    async def test_the_v1_sports_keep_their_equality_predicate(self):
        captured: dict = {}

        class _Session:
            async def execute(self, stmt, params):
                captured["sql"] = str(stmt)
                captured["params"] = params
                return _Result()

        class _Result:
            def fetchall(self):
                return []

        await task._candidates(
            _Session(),
            task.NBA,
            datetime(2026, 9, 7, tzinfo=UTC),
            datetime(2026, 9, 11, tzinfo=UTC),
        )
        assert "s.key = :sport_key" in captured["sql"]
        assert "LIKE" not in captured["sql"]
        assert captured["params"]["sport_key"] == "basketball_nba"


class TestClassifyFixtureUsesTheLeaguesOwnRule:
    """The positive control: the same pair, both rules, opposite answers."""

    def test_a_short_name_stamps_under_soccers_rule_and_misses_under_the_nfls(self):
        start = datetime(2026, 9, 8, 19, 0, tzinfo=UTC)
        ours = [_row(1, "Wrexham AFC", "Cardiff City", start)]
        f = _fixture("m", "Wrexham", "Cardiff", start, fallback="9500001")

        assert task.classify_fixture(f, ours, pair_rule=task.SOCCER.pair_rule) == (
            task.VERDICT_STAMP,
            ours,
        )
        assert task.classify_fixture(f, ours, pair_rule=pair_matches) == (
            task.VERDICT_UNMATCHED,
            [],
        )

    def test_the_default_is_still_the_incumbent_rule(self):
        """Every pre-existing caller passes no rule and must be unchanged."""
        start = datetime(2026, 9, 8, 19, 0, tzinfo=UTC)
        ours = [_row(1, "Wrexham AFC", "Cardiff City", start)]
        f = _fixture("m", "Wrexham", "Cardiff", start)
        assert task.classify_fixture(f, ours) == (task.VERDICT_UNMATCHED, [])

    def test_the_window_still_binds_under_the_looser_name_rule(self):
        """A looser NAME rule must not become a looser TIME rule: the corpus
        carries `Liverpool U19 v Atl. Madrid U19` five hours from its senior
        fixture, and ±1h is what stands between them."""
        start = datetime(2026, 9, 8, 19, 0, tzinfo=UTC)
        ours = [_row(1, "Wrexham AFC", "Cardiff City", start + timedelta(hours=2))]
        f = _fixture("m", "Wrexham", "Cardiff", start, fallback="9500001")
        assert task.classify_fixture(f, ours, pair_rule=task.SOCCER.pair_rule) == (
            task.VERDICT_UNMATCHED,
            [],
        )

    def test_two_of_our_rows_are_ambiguous_and_never_a_link(self):
        """#3813 is open: soccer fixtures exist twice in our table. The stamper
        files them; it does not choose (D35)."""
        start = datetime(2026, 9, 8, 19, 0, tzinfo=UTC)
        ours = [
            _row(1, "Wrexham AFC", "Cardiff City", start),
            _row(2, "Wrexham", "Cardiff", start + timedelta(minutes=30)),
        ]
        verdict, matches = task.classify_fixture(
            _fixture("m", "Wrexham", "Cardiff", start, fallback="9500001"),
            ours,
            pair_rule=task.SOCCER.pair_rule,
        )
        assert verdict == task.VERDICT_AMBIGUOUS
        assert {m["id"] for m in matches} == {1, 2}


class TestTheRosterCheckIsSkippedForALeagueThatHasNoRoster:
    """`is_known_league_team` answers False for every unmeasured league, so
    running it over soccer would file its whole club vocabulary every pass."""

    def test_soccer_reports_no_unknown_names(self):
        run = task.StampRun()
        task._note_unknown_names(run, task.SOCCER, "Bodø/Glimt", "Sabah FK")
        assert run.unknown_team_names == []

    def test_a_league_with_a_roster_still_reports(self):
        run = task.StampRun()
        task._note_unknown_names(run, task.NBA, "Not A Real Franchise")
        assert run.unknown_team_names == ["Not A Real Franchise"]


class TestTheMultiBoardRead:
    """Three boards, three labelled sources, and one failure costs the others nothing."""

    class _Service:
        def __init__(self, fail_on=()):
            self.fail_on = set(fail_on)
            self.asked: list = []

        async def get_schedule_fixtures(self, sport, day_offset=None):
            self.asked.append(day_offset)
            if day_offset in self.fail_on:
                raise StatPalUpstreamError(f"offset {day_offset} is dark")
            return [
                _fixture(
                    f"main-{day_offset}",
                    f"Home{day_offset}",
                    f"Away{day_offset}",
                    datetime(2026, 9, 7 + day_offset, 19, 0, tzinfo=UTC),
                    fallback=f"95000{day_offset}",
                )
            ]

        async def get_live_fixtures(self, sport):
            return []

    @pytest.mark.asyncio
    async def test_it_asks_for_every_declared_offset_and_labels_each(self):
        service = self._Service()
        run = task.StampRun()
        fixtures, anchor_space = await task._read_fixtures(service, task.SOCCER, run)
        assert service.asked == [1, 2, 3]
        assert run.sources_read == [
            "matches/daily?offset=1",
            "matches/daily?offset=2",
            "matches/daily?offset=3",
            "matches/live",
        ]
        assert anchor_space == {"950001", "950002", "950003"}
        assert [f.fixture_id for f in fixtures] == ["950001", "950002", "950003"]

    @pytest.mark.asyncio
    async def test_one_dark_board_costs_the_other_two_nothing_but_is_recorded(self):
        service = self._Service(fail_on=(2,))
        run = task.StampRun()
        fixtures, anchor_space = await task._read_fixtures(service, task.SOCCER, run)
        assert anchor_space == {"950001", "950003"}
        assert len(fixtures) == 2
        assert run.sources_read == [
            "matches/daily?offset=1",
            "matches/daily?offset=3",
            "matches/live",
        ]
        assert len(run.read_failures) == 1
        assert "offset 2" in run.read_failures[0]

    @pytest.mark.asyncio
    async def test_the_live_source_is_labelled_with_the_path_it_actually_asked(self):
        """Soccer's live board is `matches/live`; a receipt saying `livescores`
        sends a reader to a URL that was never requested."""
        run = task.StampRun()
        await task._read_fixtures(self._Service(), task.SOCCER, run)
        assert "matches/live" in run.sources_read
        assert "livescores" not in run.sources_read

    @pytest.mark.asyncio
    async def test_the_boards_overlap_and_the_anchor_dedupes_them(self):
        """~25.5h boards repeat rows verbatim. The same anchor twice is ONE
        fixture, not two — and it must be the anchor that dedupes, not `main_id`,
        which is blank on 3.6-4.6% of rows."""

        class _Repeating(self._Service):
            async def get_schedule_fixtures(self, sport, day_offset=None):
                return [
                    _fixture(
                        "",
                        "Everton",
                        "Wolves",
                        datetime(2026, 9, 9, 18, 45, tzinfo=UTC),
                        fallback="9546789",
                    )
                ]

        run = task.StampRun()
        fixtures, anchor_space = await task._read_fixtures(
            _Repeating(), task.SOCCER, run
        )
        assert len(fixtures) == 1
        assert anchor_space == {"9546789"}


class TestTheSoccerJoinStrategy:
    """The agreement row measures the SAME relation the stamper writes on."""

    @staticmethod
    def _sides(corpus):
        fixtures = [
            Side(
                ref=f["fallback_id_3"],
                home=f["home"],
                away=f["away"],
                start=datetime.fromisoformat(f["kickoff"]),
            )
            for f in corpus["statpal_fixtures"]
        ]
        rows = [
            Side(
                ref=str(e["event_id"]),
                home=e["home"],
                away=e["away"],
                start=datetime.fromisoformat(e["commence_time"]),
            )
            for e in corpus["our_events"]
        ]
        return fixtures, rows

    def test_it_joins_67_of_the_pinned_90_where_the_default_join_gets_17(self, corpus):
        """THE CONTROL. Both rows built from identical inputs; the only thing
        that differs is the strategy, and it is worth 50 games.

        67 and 17 are the same two numbers `test_soccer_team_matching_3366`
        pins on the rule itself, which is the point: the row and the writer
        agree about what a match is.
        """
        fixtures, rows = self._sides(corpus)
        assert len(rows) == 90

        soccer = build_agreement_row(
            sport_key="soccer",
            fixtures=fixtures,
            rows=rows,
            normalize=normalize_team,
            pair_sides=pair_soccer_sides,
        )
        default = build_agreement_row(
            sport_key="soccer",
            fixtures=fixtures,
            rows=rows,
            normalize=normalize_team,
        )
        assert soccer["identity"]["both"] == 67
        assert default["identity"]["both"] == 17
        assert soccer["identity"]["ours_only"] == 23
        assert default["identity"]["ours_only"] == 73

    def test_it_declares_both_refusal_names_even_when_neither_fires(self, corpus):
        """#3275: a declared name at 0 says *measured, none*; an absent key says
        nothing at all, and the two must not be confused on the sport whose
        duplicates are an open finding."""
        fixtures, rows = self._sides(corpus)
        row = build_agreement_row(
            sport_key="soccer",
            fixtures=fixtures,
            rows=rows,
            normalize=normalize_team,
            pair_sides=pair_soccer_sides,
        )
        for name in SOCCER_REFUSAL_NAMES:
            assert row["excluded"][name] == 0

    def test_it_describes_its_own_denominator(self, corpus):
        fixtures, rows = self._sides(corpus)
        row = build_agreement_row(
            sport_key="soccer",
            fixtures=fixtures,
            rows=rows,
            normalize=normalize_team,
            pair_sides=pair_soccer_sides,
        )
        assert "soccer_pair_matches" in row["denominator_is"]
        assert "within 1h" in row["denominator_is"]

    def test_a_fixture_reaching_two_of_our_rows_is_refused_not_counted_either_way(self):
        start = datetime(2026, 9, 8, 19, 0, tzinfo=UTC)
        fixtures = [Side(ref="f1", home="Wrexham", away="Cardiff", start=start)]
        rows = [
            Side(ref="1", home="Wrexham AFC", away="Cardiff City", start=start),
            Side(ref="2", home="Wrexham", away="Cardiff", start=start),
        ]
        join = pair_soccer_sides(fixtures, rows, normalize_team)
        assert join.paired == []
        assert join.statpal_only == []
        assert join.ours_only == []
        assert len(join.refusals[REFUSAL_TWO_ROWS]) == 1
        assert {r["ref"] for r in join.refusals[REFUSAL_TWO_ROWS][0]["reached"]} == {
            "1",
            "2",
        }

    def test_one_of_our_rows_reached_by_two_fixtures_is_its_own_refusal(self):
        """A different bug with a different owner from the case above, so it is
        counted apart rather than folded in."""
        start = datetime(2026, 9, 8, 19, 0, tzinfo=UTC)
        fixtures = [
            Side(ref="f1", home="Wrexham", away="Cardiff", start=start),
            Side(ref="f2", home="Wrexham AFC", away="Cardiff City", start=start),
        ]
        rows = [Side(ref="1", home="Wrexham AFC", away="Cardiff City", start=start)]
        join = pair_soccer_sides(fixtures, rows, normalize_team)
        assert join.paired == []
        assert len(join.refusals[REFUSAL_TWO_FIXTURES]) == 1

    def test_a_name_that_is_nothing_but_club_form_is_unusable_not_a_miss(self):
        """`FC` identifies no club. Published as `unusable_*` so the denominator
        moves visibly rather than silently."""
        start = datetime(2026, 9, 8, 19, 0, tzinfo=UTC)
        assert not names_a_club(Side(ref="x", home="FC", away="Cardiff", start=start))
        assert names_a_club(Side(ref="y", home="Wrexham", away="Cardiff", start=start))

        join = pair_soccer_sides(
            [Side(ref="f", home="FC", away="Cardiff", start=start)],
            [Side(ref="1", home="Wrexham AFC", away="Cardiff City", start=start)],
            normalize_team,
        )
        assert [f.ref for f in join.unusable_fixtures] == ["f"]
        assert join.paired == []

    def test_it_declines_to_answer_same_game_on_our_side(self, corpus):
        """Soccer's relation is a subset, so no conservative bucket key exists.
        `None` publishes as *not measured*, which is true; a zero would publish
        as *measured, no duplicates* about a sport with an open duplicate
        finding (#3813)."""
        fixtures, rows = self._sides(corpus)
        join = pair_soccer_sides(fixtures, rows, normalize_team)
        assert join.same_game_on_our_side is None
        assert join.our_side_bucket_key is None

        row = build_agreement_row(
            sport_key="soccer",
            fixtures=fixtures,
            rows=rows,
            normalize=normalize_team,
            pair_sides=pair_soccer_sides,
        )
        assert row["identity"]["ours_only_in_span_composition"] is None

    def test_the_one_hour_window_binds_in_the_strategy_too(self):
        """The window is what stands between a named reserve side and a wrong
        claim, and it has to bind in the ROW as well as in the writer.

        The corpus's own case: `Liverpool U19 v Atl. Madrid U19` sits five hours
        from `Liverpool v Atl. Madrid`. The suffix rule catches THAT pair — but
        `Real Madrid` matches `Real Madrid Castilla` and no suffix rule can
        catch a named B-team, so on a reserve fixture the hour is the only thing
        left. Asserted at 5h apart, and then at 59 minutes to prove the test
        discriminates rather than refusing everything.
        """
        start = datetime(2026, 9, 8, 19, 0, tzinfo=UTC)
        far = pair_soccer_sides(
            [Side(ref="f", home="Real Madrid", away="Sevilla", start=start)],
            [
                Side(
                    ref="1",
                    home="Real Madrid Castilla",
                    away="Sevilla FC",
                    start=start + timedelta(hours=5),
                )
            ],
            normalize_team,
        )
        assert far.paired == []
        assert [f.ref for f in far.statpal_only] == ["f"]
        assert [r.ref for r in far.ours_only] == ["1"]

        near = pair_soccer_sides(
            [Side(ref="f", home="Real Madrid", away="Sevilla", start=start)],
            [
                Side(
                    ref="1",
                    home="Real Madrid",
                    away="Sevilla FC",
                    start=start + timedelta(minutes=59),
                )
            ],
            normalize_team,
        )
        assert [(f.ref, r.ref) for f, r in near.paired] == [("f", "1")]

    def test_a_side_with_no_kickoff_joins_nothing(self, corpus):
        """No start is not a wide window, it is no window — two clubs meet twice
        a season and names alone would pair September with February."""
        start = datetime(2026, 9, 8, 19, 0, tzinfo=UTC)
        join = pair_soccer_sides(
            [Side(ref="f", home="Wrexham", away="Cardiff", start=None)],
            [Side(ref="1", home="Wrexham AFC", away="Cardiff City", start=start)],
            normalize_team,
        )
        assert join.paired == []
        assert [f.ref for f in join.statpal_only] == ["f"]
        assert [r.ref for r in join.ours_only] == ["1"]


class TestTheSoccerRunnerPlansRatherThanWrites:
    """Soccer writes on a beat now, and the plan mode it was born in still works.

    These two tests are the RETIRED form of the pair that pinned soccer dark.
    They used to assert `apply is False` and "not scheduled", each with the
    condition for lifting it written into the assertion message: soccer had
    never run against production, so its first pass owed a receipt rather than
    a beat entry (D51). That receipt was paid on 2026-09-08 — plan (1203
    fixtures, 116 would-write, 0 ambiguous), backup (1,281 rows of pre-image),
    apply (116 stamped), and a verification read against the DATABASE showing
    116 anchors where there had been zero, 116 distinct events, 0 phantoms.

    So the assertions invert rather than disappear. What must not be lost with
    them is the property they were protecting, which was never "soccer does not
    write" but "soccer does not write UNPLANNED" — that is
    `test_a_plan_pass_that_FINDS_work_still_writes_nothing` below, which drives
    the whole runner and is the guard that still has teeth.
    """

    def test_the_soccer_runner_applies_like_its_four_siblings(self):
        import inspect

        for fn in (
            task._run_stamp_soccer_statpal_fixtures,
            task._run_stamp_nba_statpal_fixtures,
            task._run_stamp_nhl_statpal_fixtures,
            task._run_stamp_mlb_statpal_fixtures,
        ):
            assert inspect.signature(fn).parameters["apply"].default is True

    def test_the_celery_task_is_scheduled_hourly_clear_of_every_statpal_reader(self):
        """The beat entry, and the reason its minute is the one it is.

        Asserting only "soccer is scheduled" would pass on any minute, including
        the ones the census ruled out. Soccer's soft limit is 300s where its
        siblings' is 240s, so the claim being pinned is about the WINDOW a pass
        can occupy, not the minute it starts on: no StatPal reader of any kind
        may fire inside :06–:11, and the pass may not reach the settlement
        sweep's :31–:47.
        """
        from celery.schedules import crontab

        from app.tasks import celery_app

        name = "app.tasks.stamp_soccer_statpal_fixtures"
        assert name in celery_app.tasks

        entries = {
            key: entry
            for key, entry in celery_app.conf.beat_schedule.items()
            if entry["task"] == name
        }
        assert len(entries) == 1, f"expected exactly one soccer beat entry, got {entries}"
        entry = next(iter(entries.values()))
        assert entry["options"]["queue"] == "background"

        schedule = entry["schedule"]
        assert isinstance(schedule, crontab)
        assert str(schedule._orig_minute) == "6"
        assert str(schedule._orig_hour) == "*", "hourly, like the four siblings"

        window = {(6 + k) % 60 for k in range(6)}
        assert not window & set(range(31, 48)), (
            "a 300s pass must not reach the settlement sweep's :31-:47"
        )

        # The beat entry passes no kwargs, so what it WRITES is decided by the
        # Celery task's own default — a different object from the runner
        # asserted above, and the one the scheduler actually calls. Flipping it
        # back to False would leave a scheduled, green, hourly task that stamps
        # nothing, which is the silent shape: soccer simply stops gaining
        # anchors and no gate anywhere goes red.
        assert "kwargs" not in entry or not entry.get("kwargs"), (
            "the beat passes kwargs now, so the task default is no longer what "
            "decides whether this pass writes — assert the kwargs instead"
        )
        import inspect

        assert (
            inspect.signature(celery_app.tasks[name].run).parameters["apply"].default
            is True
        )

        # Every OTHER StatPal reader must sit outside the window soccer occupies.
        for key, other in celery_app.conf.beat_schedule.items():
            if key in entries or "statpal" not in other["task"]:
                continue
            other_schedule = other["schedule"]
            if not isinstance(other_schedule, crontab):
                # `sync-statpal-livescores` runs on a raw interval, not a
                # crontab, so there is no minute to be clear OF — it overlaps
                # everything by construction and is not what this guard is about.
                continue
            fires = _crontab_minutes(other_schedule)
            assert not (fires & window), (
                f"{key} fires at {sorted(fires & window)}, inside soccer's "
                f":06-:11 window — the census picked :06 because no StatPal "
                f"reader does"
            )

    @pytest.mark.asyncio
    async def test_a_plan_pass_that_FINDS_work_still_writes_nothing(self, monkeypatch):
        """`SOCCER-PLAN-NO-WRITE-BEHAVIOR-GUARD-3366` (CERT-2195 follow-up).

        The two tests above read a DEFAULT ARGUMENT. That is worth pinning and it
        is not the claim the ship rests on: what D51 needs is that a pass which
        finds real work performs no write. So this drives the whole runner and
        watches the two things that can write — the `UPDATE` and `record_anchor`
        — while asserting the pass DID match a fixture. A guard that passed
        because nothing matched would be a green light on an empty room.

        The `apply=True` arm is the control: same fixtures, same rows, and both
        writes happen. Without it, a runner that had lost the ability to write
        at all would pass the plan half.
        """
        start = datetime(2026, 9, 8, 19, 0, tzinfo=UTC)
        fixture = _fixture(
            "2026090812079", "Wrexham AFC", "Cardiff", start, fallback="9544921"
        )
        # `home_team_name`, `away_team_name` in our row order; the pool builder in
        # `_candidates` reads the tuple positionally.
        rows = [(1, "Wrexham", "Cardiff City", start, None, "scheduled")]

        async def _drive(apply: bool):
            executed: list[str] = []
            anchors: list[dict] = []

            class _Result:
                rowcount = 1

                def fetchall(self):
                    return list(rows)

                def all(self):
                    # #5746's duplicate reconciliation reads through `.all()`; every stamp
                    # statement reads through `.fetchall()`. It answers NO ROWS because
                    # this guard's inventory is one row per contest, so there is no pair
                    # to fold — a second row for one fixture must be projected into
                    # `SELECT_ROWS_FOR_FIXTURES`'s own column order, not hidden here.
                    return []

            class _Session:
                async def execute(self, statement, params=None):
                    executed.append(str(statement))
                    if str(statement) in _LOOKBACK_SQL:
                        # #5779's look-back arm. Answered EMPTY by name rather
                        # than through `_Result`, whose `fetchall` hands back
                        # candidate rows — read as fixture ids those become our
                        # own event ids, a contest this inventory never holds.
                        return _EmptyResult()
                    return _Result()

                async def commit(self):
                    return None

                async def rollback(self):
                    return None

            @asynccontextmanager
            async def _session():
                yield _Session()

            import app.tasks.base as task_base

            monkeypatch.setattr(task_base, "get_task_session", _session)

            async def _schedule(sport, day_offset=None):
                return [fixture] if day_offset == 1 else []

            async def _live(sport):
                return []

            async def _close():
                return None

            monkeypatch.setattr(
                task,
                "get_statpal_service",
                lambda: SimpleNamespace(
                    get_schedule_fixtures=_schedule,
                    get_live_fixtures=_live,
                    close=_close,
                ),
            )

            async def _record_anchor(_s, *, event_id, key, claim_context=None):
                anchors.append({"event_id": event_id, "key": key})
                return SimpleNamespace(outcome=WROTE)

            monkeypatch.setattr(task, "record_anchor", _record_anchor)

            summary = await task._run_stamp_soccer_statpal_fixtures(
                apply=apply, now=start
            )
            return summary, executed, anchors

        planned, executed, anchors = await _drive(apply=False)

        # It FOUND the work — otherwise "wrote nothing" is vacuous.
        assert planned["stamped"] == 1
        # And wrote none of it.
        assert anchors == []
        assert not [
            s for s in executed if "UPDATE" in s.upper()
        ], "a plan pass executed an UPDATE"

        applied, executed_w, anchors_w = await _drive(apply=True)
        assert applied["stamped"] == 1
        assert [a["event_id"] for a in anchors_w] == [1]
        assert [
            s for s in executed_w if "UPDATE" in s.upper()
        ], "the control arm wrote nothing either, so the plan arm proves nothing"
        # The anchor is keyed on `fallback_id_3` in the SOCCER id space — NOT on
        # `main_id` (`2026090812079`) and NOT on one of our ~40 sport keys. Both
        # halves matter: the first is CERT-2189's collision finding, the second
        # is its `statpal_id_space` collapse, and this is their first reader.
        assert anchors_w[0]["key"].source_id == "soccer:9544921"
        assert anchors_w[0]["key"].source == "statpal"

    @pytest.mark.asyncio
    async def test_an_unattended_pass_names_itself_so_one_hour_can_be_undone(
        self, monkeypatch
    ):
        """`SOCCER-BEAT-RUN-ID-GUARD-3366`.

        Soccer writes hourly and unattended, with the loosest matcher of the five
        stampers, so every pass has to be nameable: the undo
        (`restore --identity <id> --apply`) finds its rows by
        `claim_context->>'apply_run_id'` and can do nothing for a pass that never
        wrote one. The three siblings pass `None` here — the shared runner calls
        them "the beat-driven leagues, which have no undo" — so this is soccer's
        own property and a regression to the sibling behaviour would be silent:
        the anchors would still be written, correctly, and simply stop being
        reversible.

        Three claims, and the last two are what stop the first from being
        cosmetic: the id exists, it is in the BEAT namespace rather than the
        script's `:apply:` one, and an explicitly supplied id is left alone.
        """
        start = datetime(2026, 9, 8, 19, 0, tzinfo=UTC)
        fixture = _fixture(
            "2026090812079", "Wrexham AFC", "Cardiff", start, fallback="9544921"
        )
        rows = [(1, "Wrexham", "Cardiff City", start, None, "scheduled")]

        async def _drive(**kwargs):
            contexts: list[dict] = []

            class _Result:
                rowcount = 1

                def fetchall(self):
                    return list(rows)

                def all(self):
                    # #5746's duplicate reconciliation reads through `.all()`; every stamp
                    # statement reads through `.fetchall()`. It answers NO ROWS because
                    # this guard's inventory is one row per contest, so there is no pair
                    # to fold — a second row for one fixture must be projected into
                    # `SELECT_ROWS_FOR_FIXTURES`'s own column order, not hidden here.
                    return []

            class _Session:
                async def execute(self, statement, params=None):
                    if str(statement) in _LOOKBACK_SQL:
                        # See the sibling driver above: the look-back reads ids,
                        # and `_Result` would hand it rows.
                        return _EmptyResult()
                    return _Result()

                async def commit(self):
                    return None

                async def rollback(self):
                    return None

            @asynccontextmanager
            async def _session():
                yield _Session()

            import app.tasks.base as task_base

            monkeypatch.setattr(task_base, "get_task_session", _session)

            async def _schedule(sport, day_offset=None):
                return [fixture] if day_offset == 1 else []

            monkeypatch.setattr(
                task,
                "get_statpal_service",
                lambda: SimpleNamespace(
                    get_schedule_fixtures=_schedule,
                    get_live_fixtures=lambda sport: _empty(),
                    close=_empty,
                ),
            )

            async def _record_anchor(_s, *, event_id, key, claim_context=None):
                contexts.append(claim_context or {})
                return SimpleNamespace(outcome=WROTE)

            monkeypatch.setattr(task, "record_anchor", _record_anchor)

            summary = await task._run_stamp_soccer_statpal_fixtures(
                now=start, **kwargs
            )
            return summary, contexts

        async def _empty():
            return []

        summary, contexts = await _drive(apply=True)
        assert summary["stamped"] == 1, "no write happened, so there is no id to read"
        assert len(contexts) == 1
        run_id = contexts[0].get("apply_run_id")
        assert run_id, (
            "an unattended soccer pass wrote an anchor with no `apply_run_id`; "
            "`restore --identity` can never reach it"
        )
        assert run_id == f"{task.BEAT_RUN_ID_PREFIX}:20260908T190000Z"

        # The namespace, not just the prefix constant: the script refuses a
        # `:backup:` identity by name and reads `:apply:` as an attended write,
        # so a beat pass must be neither.
        assert run_id.startswith("authority:soccer_statpal_stamp:beat:")
        assert ":apply:" not in run_id and ":backup:" not in run_id

        # An operator's explicit id is never overridden — `cmd_apply` supplies
        # its own and the two namespaces have to stay distinguishable.
        _, operator = await _drive(
            apply=True, apply_run_id="authority:soccer_statpal_stamp:apply:XYZ"
        )
        assert operator[0]["apply_run_id"] == (
            "authority:soccer_statpal_stamp:apply:XYZ"
        )

    @pytest.mark.asyncio
    async def test_a_plan_pass_mints_no_run_id_because_it_names_no_writes(
        self, monkeypatch
    ):
        """A plan pass must reach the runner with `apply_run_id=None`.

        Minting one unconditionally is invisible in behaviour — a plan writes
        nothing either way — which is exactly why it needs a guard rather than
        an argument. The cost lands later: an id that names zero writes is one
        an operator can pass to `restore --identity`, and the restore will
        cheerfully report zero rows reversed. "It returned" is not "it worked"
        (gotcha #53), and a zero-row undo that reads as success is the worst
        shape for a safety line to take.

        This spies on the delegation rather than on `record_anchor`, because in
        a plan pass no anchor is ever recorded and so there is nothing there to
        read — the absence being tested has to be observed where the value is
        passed, not where it would have been used.
        """
        seen: list[dict] = []

        async def _spy(spec, *, apply, now=None, apply_run_id=None):
            seen.append(
                {"spec": spec, "apply": apply, "apply_run_id": apply_run_id}
            )
            return {}

        monkeypatch.setattr(task, "_run_stamp_v1_statpal_fixtures", _spy)
        now = datetime(2026, 9, 8, 19, 0, tzinfo=UTC)

        await task._run_stamp_soccer_statpal_fixtures(apply=False, now=now)
        assert seen[-1]["apply_run_id"] is None, (
            "a plan pass minted a run id; it names no writes and a restore on "
            "it would report zero rows reversed as though it had worked"
        )

        # The control: the same call path DOES mint when it is going to write,
        # so the assertion above cannot be passing because minting is broken.
        await task._run_stamp_soccer_statpal_fixtures(apply=True, now=now)
        assert seen[-1]["apply_run_id"] == f"{task.BEAT_RUN_ID_PREFIX}:20260908T190000Z"
        assert seen[-1]["spec"] is task.SOCCER
