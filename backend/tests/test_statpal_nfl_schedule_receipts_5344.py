"""#5344 M1 — the NFL schedule read names every row it drops.

SHIP: an automatic NFL membership correction cannot silently omit a game
because the schedule parser dropped its authority row.

`get_schedule_fixtures("nfl")` drops a row with a missing team, a row whose
parse raised, and any node of the wrong shape, all in silence. A correction
that moves a game out of a week cannot trust that: a second copy of a contest
filed under another week, dropped for a blank team name, leaves the first copy
looking like a clean, single placement.

`get_nfl_schedule_read()` returns the SAME fixtures plus a receipt for each of
those drops. The positive corpus is the two retained real captures. Every
negative is a deliberately broken copy of them; no upstream was asked.

Every arm runs the old parser on the same payload too, so the old read stays
byte-for-byte what it was AND the drop each arm names is shown to have been
silent there (gotcha #43: both directions).
"""
import copy
import json
import sys
from pathlib import Path

import httpx
import pytest

from app.services.statpal_api import (
    REFUSE_MALFORMED_CONTEST_ID,
    REFUSE_NO_CONTEST_ID,
    REFUSE_NO_FIXTURES,
    SKIP_MALFORMED_NODE,
    SKIP_MISSING_TEAM,
    SKIP_PARSE_EXCEPTION,
    StatPalAPIService,
    StatPalUpstreamError,
)

FIXTURES = Path(__file__).parent / "fixtures"
REGULAR = FIXTURES / "statpal_nfl_season_schedule_20260903.json"
POSTSEASON = FIXTURES / "statpal_nfl_post_season_placeholders_20260909.json"

#: Week 1's opener in the 09-03 capture, used as the contest every negative breaks.
WEEK_ONE = "Regular Season / Week 1"


@pytest.fixture
def service():
    return StatPalAPIService(api_key="test-key-not-a-real-key")


def _load(path):
    return json.loads(path.read_text())


def _week_one_games(payload):
    """The game rows of Week 1, flattened, as live references into payload."""
    stage = payload["scores"]["tournament"]["stage"][1]
    assert stage["name"] == "Regular Season"
    week = stage["week"][0]
    assert week["name"] == "Week 1"
    games = []
    for day in week["matches"]:
        match = day["match"]
        games.extend([match] if isinstance(match, dict) else match)
    return games


def _both(service, payload):
    old = service._parse_nfl_season_schedule(copy.deepcopy(payload))
    new = service._parse_nfl_season_schedule_read(copy.deepcopy(payload))
    return old, new


# =============================================================================
# The real captures: same fixtures, zero receipts
# =============================================================================


class TestValidCaptures:
    @pytest.mark.parametrize("path, count", [(REGULAR, 17), (POSTSEASON, 53)])
    def test_same_fixtures_and_nothing_refused(self, service, path, count):
        old, new = _both(service, _load(path))
        assert len(old) == count
        assert new.fixtures == old
        assert new.rows_seen == count
        assert new.skipped == []
        assert new.unidentified == []
        assert new.refusals == ()
        assert new.parse_complete is True

    def test_regular_capture_has_no_duplicates(self, service):
        _, new = _both(service, _load(REGULAR))
        assert new.duplicates == []

    def test_bracket_slots_are_reported_not_refused(self, service):
        """StatPal reuses placeholder contest ids across rounds. Refusing the
        whole read for that would refuse every in-season read, so it is a
        per-member fact for the caller, and the parse stays complete."""
        _, new = _both(service, _load(POSTSEASON))
        by_id = {d.contest_id: d for d in new.duplicates}
        assert sum(len(d.paths) for d in new.duplicates) - len(by_id) == 46
        assert len(by_id["280794"].paths) == 10
        assert "Post Season / Wild Card" in by_id["280794"].rounds
        assert new.parse_complete is True

    async def test_the_service_door_returns_the_same_read(self, service, monkeypatch):
        payload = _load(REGULAR)
        asked = []

        async def fake_get(sport, endpoint, params=None):
            asked.append((sport, endpoint, params))
            return copy.deepcopy(payload)

        monkeypatch.setattr(service, "_get", fake_get)
        read = await service.get_nfl_schedule_read()
        assert asked == [("nfl", "season-schedule", None)]
        assert read.fixtures == await service.get_schedule_fixtures("nfl")
        assert read.parse_complete is True


# =============================================================================
# Every silent drop becomes a receipt
# =============================================================================


class TestEachSilentDropIsNamed:
    def _assert_dropped_and_named(self, service, payload, reason, contest_id=None):
        clean = service._parse_nfl_season_schedule(_load(REGULAR))
        old, new = _both(service, payload)
        assert len(old) == len(clean) - 1, "the old read must drop it silently"
        assert new.fixtures == old
        assert [r.reason for r in new.skipped] == [reason]
        assert new.skipped[0].contest_id == contest_id
        assert new.parse_skipped == 1
        assert new.refusals == (reason,)
        assert new.parse_complete is False
        return new.skipped[0]

    @pytest.mark.parametrize("side", ["home", "away"])
    def test_missing_team_name(self, service, side):
        payload = _load(REGULAR)
        game = _week_one_games(payload)[0]
        game[side]["name"] = ""
        receipt = self._assert_dropped_and_named(
            service, payload, SKIP_MISSING_TEAM, game["contestid"]
        )
        assert (receipt.stage, receipt.week) == ("Regular Season", "Week 1")
        assert receipt.path.startswith("stage[1]/week[0]/matches[")

    def test_missing_team_object(self, service):
        payload = _load(REGULAR)
        game = _week_one_games(payload)[0]
        del game["away"]
        self._assert_dropped_and_named(service, payload, SKIP_MISSING_TEAM, game["contestid"])

    def test_a_row_whose_parse_raises(self, service):
        """Real failure, not a mock: a venue-local clock with no UTC twin takes
        the warning branch, and its f-string calls `.get` on a list `away`."""
        payload = _load(REGULAR)
        game = _week_one_games(payload)[0]
        game.pop("datetime_utc")
        game["timezone"] = "EST"
        game["date"], game["time"] = "13.09.2026", "1:00 PM"
        game["away"] = []
        game["away_team"] = "Visitors"
        receipt = self._assert_dropped_and_named(
            service, payload, SKIP_PARSE_EXCEPTION, game["contestid"]
        )
        assert receipt.detail.startswith("AttributeError")

    def test_a_game_row_that_is_not_a_dict(self, service):
        payload = _load(REGULAR)
        day = payload["scores"]["tournament"]["stage"][1]["week"][0]["matches"][2]
        assert isinstance(day["match"], list)
        day["match"][0] = "280445"
        receipt = self._assert_dropped_and_named(service, payload, SKIP_MALFORMED_NODE)
        assert receipt.detail == "str"
        assert receipt.path == "stage[1]/week[0]/matches[2]/match[0]"

    @pytest.mark.parametrize("value, detail", [(None, "NoneType"), ("tbd", "str"), (7, "int")])
    def test_a_day_whose_match_is_not_a_container(self, service, value, detail):
        payload = _load(REGULAR)
        stage = payload["scores"]["tournament"]["stage"]
        hof = stage[0]["week"][0]["matches"]
        assert isinstance(hof, dict) and isinstance(hof["match"], dict)
        hof["match"] = value
        receipt = self._assert_dropped_and_named(service, payload, SKIP_MALFORMED_NODE)
        assert receipt.detail == f"match is {detail}"
        assert receipt.path == "stage[0]/week[0]/matches[0]/match"

    def test_a_day_with_no_match_key(self, service):
        payload = _load(REGULAR)
        del payload["scores"]["tournament"]["stage"][0]["week"][0]["matches"]["match"]
        receipt = self._assert_dropped_and_named(service, payload, SKIP_MALFORMED_NODE)
        assert receipt.detail == "match is absent"

    def test_a_week_with_no_matches_key(self, service):
        payload = _load(REGULAR)
        del payload["scores"]["tournament"]["stage"][0]["week"][0]["matches"]
        receipt = self._assert_dropped_and_named(service, payload, SKIP_MALFORMED_NODE)
        assert receipt.detail == "matches is absent"
        assert receipt.week == "Hall of Fame Weekend"

    def test_a_day_that_is_not_a_dict(self, service):
        payload = _load(REGULAR)
        payload["scores"]["tournament"]["stage"][0]["week"][0]["matches"] = ["Thursday"]
        self._assert_dropped_and_named(service, payload, SKIP_MALFORMED_NODE)

    def test_a_week_that_is_not_a_dict(self, service):
        payload = _load(REGULAR)
        payload["scores"]["tournament"]["stage"][0]["week"] = ["Hall of Fame Weekend"]
        self._assert_dropped_and_named(service, payload, SKIP_MALFORMED_NODE)

    def test_a_stage_with_no_week_key(self, service):
        payload = _load(REGULAR)
        del payload["scores"]["tournament"]["stage"][0]["week"]
        receipt = self._assert_dropped_and_named(service, payload, SKIP_MALFORMED_NODE)
        assert (receipt.stage, receipt.detail) == ("Pre Season", "week is absent")

    def test_a_stage_that_is_not_a_dict(self, service):
        payload = _load(REGULAR)
        payload["scores"]["tournament"]["stage"][0] = "Pre Season"
        self._assert_dropped_and_named(service, payload, SKIP_MALFORMED_NODE)

    def test_an_explicit_empty_list_is_an_answer_not_a_skip(self, service):
        """Only where a list is accepted (stage, week, matches, match). At
        `scores`/`tournament` a `[]` is malformed: see the next class."""
        payload = _load(REGULAR)
        payload["scores"]["tournament"]["stage"][0]["week"] = []
        old, new = _both(service, payload)
        assert new.fixtures == old and len(old) == 16
        assert new.skipped == [] and new.parse_complete is True

    def test_a_row_with_no_contest_id_is_kept_but_refused(self, service):
        """The old read keeps it with fixture_id ''. It could be a copy of any
        contest, so it cannot leave a roster complete."""
        payload = _load(REGULAR)
        game = _week_one_games(payload)[0]
        del game["contestid"]
        old, new = _both(service, payload)
        assert len(old) == 17 and new.fixtures == old
        assert new.skipped == []
        assert [r.reason for r in new.unidentified] == [REFUSE_NO_CONTEST_ID]
        assert new.refusals == (REFUSE_NO_CONTEST_ID,)
        assert new.parse_complete is False


class TestTheWholePayloadUnreadable:
    @pytest.mark.parametrize(
        "mutate, path, detail",
        [
            (lambda p: [p], "$", "list"),
            (lambda p: {"_recorded": p["_recorded"]}, "scores", "scores is absent"),
            (lambda p: {"scores": {"sport": "nfl", "tournament": "USA: NFL"}},
             "scores/tournament", "tournament is str"),
            (lambda p: {"scores": {"tournament": {"name": "USA: NFL"}}},
             "scores/tournament/stage", "stage is absent"),
            # A list is wrapped at stage/week/day level, never at these two
            # (independent review, 98540b1d): the old walk reads them as empty.
            (lambda p: {"scores": [p["scores"]]}, "scores", "scores is list"),
            (lambda p: {"scores": {"tournament": [p["scores"]["tournament"]]}},
             "scores/tournament", "tournament is list"),
            (lambda p: {"scores": []}, "scores", "scores is list"),
            (lambda p: {"scores": {"tournament": []}}, "scores/tournament", "tournament is list"),
            (lambda p: {"scores": [None]}, "scores", "scores is list"),
            (lambda p: {"scores": {"tournament": ["x"]}}, "scores/tournament", "tournament is list"),
            # A valid first sibling never certifies the read alone (review
            # demonstration `silent_second_tournament`): a malformed or a
            # duplicate second tournament refuses the whole node.
            (lambda p: {"scores": {"tournament": [p["scores"]["tournament"], "x"]}},
             "scores/tournament", "tournament is list"),
            (lambda p: {"scores": {"tournament": [p["scores"]["tournament"]] * 2}},
             "scores/tournament", "tournament is list"),
            (lambda p: {"scores": [p["scores"], p["scores"]]}, "scores", "scores is list"),
        ],
    )
    def test_structure_missing_is_a_receipt_not_an_empty_schedule(
        self, service, mutate, path, detail
    ):
        payload = mutate(_load(REGULAR))
        old, new = _both(service, payload)
        assert old == [] and new.fixtures == []
        assert [(r.reason, r.path) for r in new.skipped] == [(SKIP_MALFORMED_NODE, path)]
        assert new.skipped[0].detail == detail or path == "$"
        assert new.refusals == (SKIP_MALFORMED_NODE, REFUSE_NO_FIXTURES)
        assert new.parse_complete is False

    def test_an_answered_empty_schedule_is_not_a_complete_roster(self, service):
        payload = {"scores": {"tournament": {"name": "USA: NFL", "stage": []}}}
        old, new = _both(service, payload)
        assert old == [] and new.skipped == []
        assert new.refusals == (REFUSE_NO_FIXTURES,)
        assert new.parse_complete is False


# =============================================================================
# The hazard itself: a malformed duplicate cannot vanish into a clean roster
# =============================================================================


class TestMalformedDuplicate:
    def _with_second_copy(self, game_edit):
        """Week 1's opener filed again under a new `Week 2`, edited."""
        payload = _load(REGULAR)
        opener = copy.deepcopy(_week_one_games(payload)[0])
        game_edit(opener)
        payload["scores"]["tournament"]["stage"][1]["week"].append(
            {"name": "Week 2", "matches": {"date": "Sunday", "match": opener}}
        )
        return payload, opener["contestid"]

    def test_old_read_shows_one_clean_placement_new_read_refuses(self, service):
        payload, contest = self._with_second_copy(lambda g: g["home"].update(name=""))
        old, new = _both(service, payload)

        placed = [f.round_info for f in old if f.fixture_id == contest]
        assert placed == [WEEK_ONE], "the hazard: the old read looks clean"

        assert new.fixtures == old
        assert [(r.reason, r.contest_id, r.week) for r in new.skipped] == [
            (SKIP_MISSING_TEAM, contest, "Week 2")
        ]
        dup = {d.contest_id: d for d in new.duplicates}[contest]
        assert dup.rounds == (WEEK_ONE, "Regular Season / Week 2")
        assert len(dup.paths) == 2
        assert new.parse_complete is False

    def test_a_raising_copy_is_attributed_to_its_contest(self, service):
        def raises(g):
            g.pop("datetime_utc")
            g.update(timezone="EST", date="20.09.2026", time="1:00 PM", away=[], away_team="X")

        payload, contest = self._with_second_copy(raises)
        _, new = _both(service, payload)
        assert [(r.reason, r.contest_id) for r in new.skipped] == [
            (SKIP_PARSE_EXCEPTION, contest)
        ]
        assert contest in {d.contest_id for d in new.duplicates}

    def test_a_well_formed_second_copy_is_reported_and_left_to_the_caller(self, service):
        payload, contest = self._with_second_copy(lambda g: None)
        old, new = _both(service, payload)
        assert new.fixtures == old and len(old) == 18
        assert new.skipped == [] and new.parse_complete is True
        dup = {d.contest_id: d for d in new.duplicates}[contest]
        assert dup.rounds == (WEEK_ONE, "Regular Season / Week 2")


# =============================================================================
# A malformed context label or contest id is a receipt, never an escape or an
# identity (independent review 98540b1d, P2 ×2; still open on bf7a4d42)
# =============================================================================


class TestMalformedStageOrWeekName:
    """The old walk joins the two names into `round_info`; a truthy
    non-string raises TypeError there and the whole read is lost. Here the
    label is a receipt and the games under it are still read."""

    @pytest.mark.parametrize("value", [7, ["Regular Season"], {"en": "Week 1"}, 1.5, True])
    @pytest.mark.parametrize("level", ["stage", "week"])
    def test_a_truthy_wrong_type_name_is_a_receipt_not_an_exception(
        self, service, level, value
    ):
        payload = _load(REGULAR)
        stage = payload["scores"]["tournament"]["stage"][1]
        node = stage if level == "stage" else stage["week"][0]
        node["name"] = value
        with pytest.raises(TypeError):
            service._parse_nfl_season_schedule(copy.deepcopy(payload))
        new = service._parse_nfl_season_schedule_read(copy.deepcopy(payload))

        path = "stage[1]/name" if level == "stage" else "stage[1]/week[0]/name"
        assert [(r.reason, r.path) for r in new.skipped] == [(SKIP_MALFORMED_NODE, path)]
        assert new.skipped[0].detail == f"name is {type(value).__name__}"
        assert new.refusals == (SKIP_MALFORMED_NODE,)
        assert new.parse_complete is False
        # Healthy siblings and the games under the bad label are all still read.
        clean = service._parse_nfl_season_schedule(_load(REGULAR))
        assert [f.fixture_id for f in new.fixtures] == [f.fixture_id for f in clean]
        assert new.rows_seen == 17
        # No non-string ever reaches a receipt's or a fixture's label.
        assert all(isinstance(r.stage, (str, type(None))) for r in new.skipped)
        dropped = "Regular Season" if level == "stage" else "Week 1"
        assert all(dropped not in (f.round_info or "") for f in new.fixtures[1:])

    @pytest.mark.parametrize("value", [0, [], {}, False])
    def test_a_falsy_wrong_type_name_keeps_old_fixtures_and_refuses(self, service, value):
        """The old walk skips a falsy label and returns; parity holds, and the
        read still says the node is malformed."""
        payload = _load(REGULAR)
        payload["scores"]["tournament"]["stage"][1]["week"][0]["name"] = value
        old, new = _both(service, payload)
        assert new.fixtures == old and len(old) == 17
        assert [(r.reason, r.path) for r in new.skipped] == [
            (SKIP_MALFORMED_NODE, "stage[1]/week[0]/name")
        ]
        assert new.parse_complete is False

    @pytest.mark.parametrize("value", [None, ""])
    def test_an_absent_or_empty_name_is_not_malformed(self, service, value):
        payload = _load(REGULAR)
        payload["scores"]["tournament"]["stage"][1]["week"][0]["name"] = value
        old, new = _both(service, payload)
        assert new.fixtures == old
        assert new.skipped == [] and new.parse_complete is True

    def test_a_second_copy_under_a_bad_label_still_counts_as_a_duplicate(self, service):
        payload = _load(REGULAR)
        opener = copy.deepcopy(_week_one_games(payload)[0])
        payload["scores"]["tournament"]["stage"][1]["week"].append(
            {"name": ["Week 2"], "matches": {"date": "Sunday", "match": opener}}
        )
        new = service._parse_nfl_season_schedule_read(payload)
        assert opener["contestid"] in {d.contest_id for d in new.duplicates}
        assert new.rows_seen == 18
        assert new.parse_complete is False


class TestMalformedContestId:
    """`_parse_single_fixture` stringifies any truthy id, so the old read keeps
    `{"bad": "123"}` as fixture_id `"{'bad': '123'}"`. The fixture stays for
    parity; the new read refuses to treat it as a contest."""

    @pytest.mark.parametrize(
        "key, value",
        [
            ("contestid", {"bad": "123"}),
            ("contestid", ["280445"]),
            ("contestid", 280445.0),
            ("contestid", True),
            ("id", {"bad": "123"}),
            ("fixture_id", ["280445"]),
        ],
    )
    def test_a_structured_id_is_kept_but_never_an_identity(self, service, key, value):
        payload = _load(REGULAR)
        game = _week_one_games(payload)[0]
        del game["contestid"]
        game[key] = value
        old, new = _both(service, payload)
        assert len(old) == 17 and new.fixtures == old
        # old[0] is the lone Pre Season game; old[1] is Week 1's opener.
        assert old[1].fixture_id == str(value), "the old read vouches for it"
        assert new.skipped == []
        receipt = new.unidentified[0]
        assert [r.reason for r in new.unidentified] == [REFUSE_MALFORMED_CONTEST_ID]
        assert receipt.contest_id is None
        assert receipt.detail == f"{key} is {type(value).__name__}: {value!r}"
        assert receipt.path.endswith("/match[0]") and receipt.week == "Week 1"
        assert new.refusals == (REFUSE_MALFORMED_CONTEST_ID,)
        assert new.parse_complete is False

    def test_a_structured_id_never_enters_duplicates(self, service):
        payload = _load(REGULAR)
        games = _week_one_games(payload)
        games[0]["contestid"] = {"bad": "123"}
        games[1]["contestid"] = {"bad": "123"}
        new = service._parse_nfl_season_schedule_read(payload)
        assert new.duplicates == []
        assert [r.reason for r in new.unidentified] == [REFUSE_MALFORMED_CONTEST_ID] * 2

    def test_precedence_matches_the_fixture_parser(self, service):
        """`id` wins over `contestid` when truthy, as in `_parse_single_fixture`;
        a falsy `id` falls through to a valid `contestid`."""
        payload = _load(REGULAR)
        games = _week_one_games(payload)
        games[0]["id"] = {"bad": "1"}
        games[1]["id"] = 0
        old, new = _both(service, payload)
        assert new.fixtures == old
        assert [r.path for r in new.unidentified] == [new.unidentified[0].path]
        assert new.unidentified[0].detail.startswith("id is dict")
        assert old[1].fixture_id == "{'bad': '1'}"
        assert old[2].fixture_id == games[1]["contestid"]

    @pytest.mark.parametrize("value", ["280445", 280445])
    def test_string_and_integer_ids_stay_identities(self, service, value):
        payload = _load(REGULAR)
        games = _week_one_games(payload)
        games[0]["contestid"] = value
        copy_ = copy.deepcopy(games[0])
        payload["scores"]["tournament"]["stage"][1]["week"].append(
            {"name": "Week 2", "matches": {"date": "Sunday", "match": copy_}}
        )
        old, new = _both(service, payload)
        assert new.fixtures == old
        assert new.unidentified == [] and new.parse_complete is True
        assert "280445" in {d.contest_id for d in new.duplicates}

    def test_a_refused_row_with_a_structured_id_names_it(self, service):
        payload = _load(REGULAR)
        game = _week_one_games(payload)[0]
        game["contestid"] = {"bad": "123"}
        game["home"]["name"] = ""
        new = service._parse_nfl_season_schedule_read(payload)
        assert [(r.reason, r.contest_id) for r in new.skipped] == [(SKIP_MISSING_TEAM, None)]
        assert new.skipped[0].detail == "contestid is dict: {'bad': '123'}"
        assert new.duplicates == []


# =============================================================================
# Transport failure stays a failure; nothing else moved
# =============================================================================


class TestTransportFailureRaises:
    async def test_no_answer_raises(self, service, monkeypatch):
        async def fake_get(sport, endpoint, params=None):
            return None

        monkeypatch.setattr(service, "_get", fake_get)
        with pytest.raises(StatPalUpstreamError):
            await service.get_nfl_schedule_read()

    @pytest.mark.parametrize(
        "response",
        [
            httpx.Response(500, text="oops"),
            httpx.Response(429, text="slow down"),
            httpx.Response(200, json={"error": "Invalid access key"}),
            httpx.Response(200, text="invalid-request"),
        ],
    )
    async def test_real_get_failures_raise_through_the_new_door(self, service, response):
        seen = []

        def handler(request):
            seen.append(request.url.path)
            return response

        await service.client.aclose()
        service.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        try:
            with pytest.raises(StatPalUpstreamError):
                await service.get_nfl_schedule_read()
        finally:
            await service.close()
        assert seen == ["/api/v1/nfl/season-schedule"]


class TestOldCallersUnchanged:
    async def test_get_schedule_fixtures_still_drops_in_silence(self, service, monkeypatch):
        """The old door keeps its old behaviour on a broken payload: the
        malformed row is gone, nothing raises, nothing is reported."""
        payload = _load(REGULAR)
        _week_one_games(payload)[0]["home"]["name"] = ""

        async def fake_get(sport, endpoint, params=None):
            return copy.deepcopy(payload)

        monkeypatch.setattr(service, "_get", fake_get)
        fixtures = await service.get_schedule_fixtures("nfl")
        assert fixtures == service._parse_nfl_season_schedule(copy.deepcopy(payload))
        assert len(fixtures) == 16

    async def test_other_sports_never_reach_the_receipt_walk(self, service, monkeypatch):
        calls = []
        monkeypatch.setattr(
            service,
            "_parse_nfl_season_schedule_read",
            lambda data: calls.append(data),
        )

        async def fake_get(sport, endpoint, params=None):
            return {"scores": {"tournament": {"name": "x", "week": []}}}

        monkeypatch.setattr(service, "_get", fake_get)
        for sport in ("nfl", "nba", "nhl", "mlb"):
            await service.get_schedule_fixtures(sport)
        assert calls == []


def test_every_reason_is_emitted_by_the_walk(service):
    """The closed set is exactly what the walk emits: each reason is produced
    by a real payload here, and no other SKIP_/REFUSE_ name exists."""
    mod = sys.modules[StatPalAPIService.__module__]

    def emitted(payload):
        return set(service._parse_nfl_season_schedule_read(payload).refusals)

    missing_team = _load(REGULAR)
    _week_one_games(missing_team)[0]["home"]["name"] = ""
    raises = _load(REGULAR)
    _week_one_games(raises)[0].pop("datetime_utc")
    _week_one_games(raises)[0].update(
        timezone="EST", date="13.09.2026", time="1:00 PM", away=[], away_team="X"
    )
    no_id = _load(REGULAR)
    del _week_one_games(no_id)[0]["contestid"]
    bad_id = _load(REGULAR)
    _week_one_games(bad_id)[0]["contestid"] = {"bad": "123"}

    seen = (
        emitted({"scores": None})
        | emitted(missing_team)
        | emitted(raises)
        | emitted(no_id)
        | emitted(bad_id)
    )
    declared = {
        getattr(mod, name) for name in dir(mod) if name.startswith(("SKIP_", "REFUSE_"))
    }
    assert seen == declared == {
        SKIP_MALFORMED_NODE,
        SKIP_MISSING_TEAM,
        SKIP_PARSE_EXCEPTION,
        REFUSE_NO_CONTEST_ID,
        REFUSE_MALFORMED_CONTEST_ID,
        REFUSE_NO_FIXTURES,
    }
