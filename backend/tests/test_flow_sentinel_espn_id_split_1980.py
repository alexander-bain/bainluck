"""#1980 (queue 380) — TWO DEFECT CLASSES WITH OPPOSITE REMEDIES SHARED ONE FLOW.

A settled event that disagrees with ESPN is wrong in one of two FIELDS:

* ``score_drifted`` — the ``espn_id`` is proven this row's own game and the stored
  score is not that game's final. Remedy: ``event-final-scores?apply=true``.
* ``espn_id_drifted`` — the ``espn_id`` is ITSELF wrong; it names a different
  game. **The score remedy on this row writes another game's final onto it.**
  Remedy: the attended ``event-espn-id`` linkage repair.

Until this split the rail computed the linkage classes and DISCARDED them.
``espn_not_found`` was a bare counter with no ledger row at all;
``skip_identity_mismatch`` / ``skip_espn_id_wrong_date`` landed in the ledger and
were then filtered out by ``frozen_final_score_events``. So they were neither
repaired nor reported — while the failure text the sentinel printed on EVERY line
was the score remedy.

THE MEASUREMENT THAT MAKES THIS A P1 AND NOT A TIDY-UP (2026-08-19, read-only,
262 settled MLB rows over the previous 32 days, cross-checked against BOTH the
ESPN scoreboard and the ESPN summary endpoint):

    236/262 clean · 21 espn_id_drifted · 0 score_drifted · 5 unadjudicable

and for **8 of the 21 the stored score is already CORRECT**. The remedy the flow
printed would have corrupted a correct score on eight rows. The anchors below are
three of those real rows.

The second half is the denominator: the flow reported a specific integer while
scanning 6 of ~1,000 (sport, date) groups — 0.6% of its own surface. A gate that
reports a specific integer while measuring 0.6% of its surface READS AS A
POPULATION. Sampling stays (a full sweep is ~11 minutes against a 30 s router
wall, measured); the label is what was missing.
"""

from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.tasks.flow_sentinel import (
    build_flow_issue_body,
    build_flow_issue_title,
    build_flow_redetect_comment,
    coverage_phrase,
    espn_id_linkage_defects,
    espn_id_unresolvable_rows,
    estimated_population_defects,
    frozen_final_score_events,
    sampled_measurement,
)
from scripts.repair_event_final_scores import (
    ESPN_ID_DRIFTED,
    ESPN_ID_UNRESOLVABLE,
    LINK_PROVEN,
    SCORE_DRIFTED,
    classify_espn_link,
    measurement_coverage,
)

UTC = timezone.utc


def _game(espn_id, home, away, home_score, away_score, when, status="post"):
    return SimpleNamespace(
        espn_id=espn_id, status=status, date=when,
        home_team=SimpleNamespace(display_name=home, name=home, short_name=home),
        away_team=SimpleNamespace(display_name=away, name=away, short_name=away),
        home_score=home_score, away_score=away_score,
    )


# ---------------------------------------------------------------------------
# The classifier — which FIELD is wrong
# ---------------------------------------------------------------------------
class TestClassifyEspnLink:
    """Pure over an already-fetched slate, so it costs no extra network call and
    every branch is provable without production."""

    def test_id_on_our_slate_with_our_fixture_is_proven(self):
        board = [_game("401816456", "New York Yankees", "Atlanta Braves", 1, 2,
                       datetime(2026, 8, 9, 17, 35, tzinfo=UTC))]
        verdict, target, _ = classify_espn_link(
            espn_id="401816456",
            commence_time=datetime(2026, 8, 9, 17, 35, tzinfo=UTC),
            game_date=date(2026, 8, 9),
            home_team_name="New York Yankees", away_team_name="Atlanta Braves",
            board=board,
        )
        assert verdict == LINK_PROVEN
        assert target.espn_id == "401816456"

    def test_ev15191123_the_anchor_correct_score_wrong_id(self):
        """THE row that proves the two remedies are opposite.

        Real production row, measured 2026-08-19: ev15191123 Braves @ Yankees,
        commence 2026-08-09T17:35Z, stored H1-A2 — which IS the final of the
        2026-08-09 game (espn 401816456). But its ``espn_id`` is 401816441, the
        2026-08-08 game (H5-A4). The espn_id is 15 LOWER in ESPN id space: one
        slate-day of the same series.

        Handing this row the score remedy overwrites a CORRECT 1-2 with 5-4.
        """
        board = [_game("401816456", "New York Yankees", "Atlanta Braves", 1, 2,
                       datetime(2026, 8, 9, 17, 35, tzinfo=UTC))]
        verdict, target, reason = classify_espn_link(
            espn_id="401816441",  # the 08-08 game — not on the 08-09 slate
            commence_time=datetime(2026, 8, 9, 17, 35, tzinfo=UTC),
            game_date=date(2026, 8, 9),
            home_team_name="New York Yankees", away_team_name="Atlanta Braves",
            board=board,
        )
        assert verdict == ESPN_ID_DRIFTED
        assert target.espn_id == "401816456", "the target is PROVEN, not guessed"
        assert "absent" in reason

    def test_absent_id_with_no_fixture_on_the_slate_is_unresolvable(self):
        """Gotcha #53: an empty read is not a fact.

        A postponement, a slate gap and a real drift all produce this identical
        absence, so nothing may be CLAIMED — but it must not be invisible either,
        which is what the bare ``espn_not_found`` counter made it.
        """
        board = [_game("999", "Chicago Cubs", "St. Louis Cardinals", 4, 2,
                       datetime(2026, 8, 9, 20, 0, tzinfo=UTC))]
        verdict, target, reason = classify_espn_link(
            espn_id="401816441",
            commence_time=datetime(2026, 8, 9, 17, 35, tzinfo=UTC),
            game_date=date(2026, 8, 9),
            home_team_name="New York Yankees", away_team_name="Atlanta Braves",
            board=board,
        )
        assert verdict == ESPN_ID_UNRESOLVABLE
        assert target is None
        assert "NO game" in reason

    def test_absent_id_in_a_doubleheader_names_no_target(self):
        board = [
            _game("A", "Cincinnati Reds", "St. Louis Cardinals", 1, 2,
                  datetime(2026, 8, 17, 17, 40, tzinfo=UTC)),
            _game("B", "Cincinnati Reds", "St. Louis Cardinals", 6, 5,
                  datetime(2026, 8, 17, 22, 40, tzinfo=UTC)),
        ]
        verdict, target, reason = classify_espn_link(
            espn_id="ZZZ",
            commence_time=datetime(2026, 8, 17, 17, 40, tzinfo=UTC),
            game_date=date(2026, 8, 17),
            home_team_name="Cincinnati Reds", away_team_name="St. Louis Cardinals",
            board=board,
        )
        assert verdict == ESPN_ID_UNRESOLVABLE
        assert target is None
        assert "doubleheader" in reason

    def test_same_city_impostor_clears_the_fuzzy_guard_and_is_caught_anyway(self):
        """ev15173316: our row is Dodgers @ METS; its espn_id 401816142 is
        Dodgers @ YANKEES.

        This is the specimen that forced a SECOND, stricter name predicate.
        ``names_match`` falls back to a >= 0.5 token overlap, and

            names_match("New York Mets", "New York Yankees") -> True

        so the rail's existing ``_identity_matches`` guard — whose entire job is
        to stop a score being imported off the wrong game — PASSES on this row.
        The classifier catches it because exactly one STRICTLY-matching game sits
        on the same slate under a different id.
        """
        board = [
            _game("401816240", "New York Mets", "Los Angeles Dodgers", 2, 4,
                  datetime(2026, 7, 24, 23, 10, tzinfo=UTC)),
            _game("401816142", "New York Yankees", "Los Angeles Dodgers", 1, 2,
                  datetime(2026, 7, 24, 23, 5, tzinfo=UTC)),
        ]
        from scripts.repair_event_final_scores import _identity_matches

        assert _identity_matches(
            "New York Mets", "Los Angeles Dodgers",
            "New York Yankees", "Los Angeles Dodgers",
        ) is True, "the loose guard is blind to this — that is the point"

        verdict, target, reason = classify_espn_link(
            espn_id="401816142",
            commence_time=datetime(2026, 7, 24, 23, 10, tzinfo=UTC),
            game_date=date(2026, 7, 24),
            home_team_name="New York Mets", away_team_name="Los Angeles Dodgers",
            board=board,
        )
        assert verdict == ESPN_ID_DRIFTED
        assert target.espn_id == "401816240"
        assert "IMPOSTOR" in reason

    def test_an_unrelated_fixture_on_our_slate_is_drifted(self):
        """The plain case the loose guard DOES see (the CAL-P002 NCAA rows)."""
        board = [
            _game("A", "Chicago Cubs", "Milwaukee Brewers", 4, 2,
                  datetime(2026, 7, 24, 23, 10, tzinfo=UTC)),
        ]
        verdict, target, reason = classify_espn_link(
            espn_id="A",
            commence_time=datetime(2026, 7, 24, 23, 10, tzinfo=UTC),
            game_date=date(2026, 7, 24),
            home_team_name="Boston Red Sox", away_team_name="Toronto Blue Jays",
            board=board,
        )
        assert verdict == ESPN_ID_DRIFTED
        assert target is None, "no strict candidate on the slate — nothing proposed"
        assert "DIFFERENT fixture" in reason

    def test_a_loose_only_match_with_no_strict_alternative_still_repairs(self):
        """The other direction (gotcha #43). The strict predicate ELECTS a
        target; it must not narrow what may be written. With no strictly-matching
        alternative on the slate, an unusually-named source still resolves."""
        board = [
            _game("A", "Boston Bruins", "Minnesota Wild", 6, 3,
                  datetime(2026, 7, 24, 23, 10, tzinfo=UTC)),
        ]
        verdict, target, _ = classify_espn_link(
            espn_id="A",
            commence_time=datetime(2026, 7, 24, 23, 10, tzinfo=UTC),
            game_date=date(2026, 7, 24),
            home_team_name="Bruins", away_team_name="Wild",
            board=board,
        )
        assert verdict == LINK_PROVEN
        assert target.espn_id == "A"

    def test_id_resolving_to_another_date_is_drifted(self):
        board = [
            _game("401816456", "New York Yankees", "Atlanta Braves", 1, 2,
                  datetime(2026, 8, 9, 17, 35, tzinfo=UTC)),
            _game("401816441", "New York Yankees", "Atlanta Braves", 5, 4,
                  datetime(2026, 8, 8, 19, 5, tzinfo=UTC)),
        ]
        verdict, target, reason = classify_espn_link(
            espn_id="401816441",
            commence_time=datetime(2026, 8, 9, 17, 35, tzinfo=UTC),
            game_date=date(2026, 8, 9),
            home_team_name="New York Yankees", away_team_name="Atlanta Braves",
            board=board,
        )
        assert verdict == ESPN_ID_DRIFTED
        assert target.espn_id == "401816456"
        assert "DIFFERENT date" in reason

    def test_doubleheader_sibling_is_unresolvable_not_a_score_defect(self):
        """The arm the two pre-existing guards were structurally blind to.

        Both games of a doubleheader sit on the same slate with the same two
        teams, so ``espn_date_matches`` passes AND ``_identity_matches`` passes on
        the WRONG sibling. Real pair (2026-08-17, Cardinals @ Reds): ev14788546
        and ev15200380 both store commence 17:40Z, while ev14788546's espn_id and
        score both belong to the 22:40Z game. One of espn_id / commence_time
        drifted and this rail cannot tell which — so it says so.
        """
        board = [
            _game("401873710", "Cincinnati Reds", "St. Louis Cardinals", 1, 2,
                  datetime(2026, 8, 17, 17, 40, tzinfo=UTC)),
            _game("401816567", "Cincinnati Reds", "St. Louis Cardinals", 6, 5,
                  datetime(2026, 8, 17, 22, 40, tzinfo=UTC)),
        ]
        verdict, target, reason = classify_espn_link(
            espn_id="401816567",
            commence_time=datetime(2026, 8, 17, 17, 40, tzinfo=UTC),
            game_date=date(2026, 8, 17),
            home_team_name="Cincinnati Reds", away_team_name="St. Louis Cardinals",
            board=board,
        )
        assert verdict == ESPN_ID_UNRESOLVABLE
        assert "cannot tell which" in reason

    def test_the_correctly_paired_doubleheader_row_is_still_proven(self):
        """The other direction of the same guard — the healthy sibling must NOT
        be swept up. A cap's guard tests assert both directions (gotcha #43)."""
        board = [
            _game("401873710", "Cincinnati Reds", "St. Louis Cardinals", 1, 2,
                  datetime(2026, 8, 17, 17, 40, tzinfo=UTC)),
            _game("401816567", "Cincinnati Reds", "St. Louis Cardinals", 6, 5,
                  datetime(2026, 8, 17, 22, 40, tzinfo=UTC)),
        ]
        verdict, target, _ = classify_espn_link(
            espn_id="401873710",
            commence_time=datetime(2026, 8, 17, 17, 40, tzinfo=UTC),
            game_date=date(2026, 8, 17),
            home_team_name="Cincinnati Reds", away_team_name="St. Louis Cardinals",
            board=board,
        )
        assert verdict == LINK_PROVEN
        assert target.espn_id == "401873710"

    def test_a_missing_commence_time_cannot_elect_a_doubleheader_winner(self):
        """No time, no pairing — and no silent pass either."""
        board = [
            _game("A", "Cincinnati Reds", "St. Louis Cardinals", 1, 2,
                  datetime(2026, 8, 17, 17, 40, tzinfo=UTC)),
            _game("B", "Cincinnati Reds", "St. Louis Cardinals", 6, 5,
                  datetime(2026, 8, 17, 22, 40, tzinfo=UTC)),
        ]
        verdict, _, _ = classify_espn_link(
            espn_id="B", commence_time=None, game_date=date(2026, 8, 17),
            home_team_name="Cincinnati Reds", away_team_name="St. Louis Cardinals",
            board=board,
        )
        # Nothing proves the pairing is wrong, and nothing proves it is right;
        # the id IS on our slate with our fixture, so the score comparison is the
        # honest reading. What must never happen is a silent write on a row whose
        # sibling was nearer — and with no time there is no "nearer".
        assert verdict == LINK_PROVEN


# ---------------------------------------------------------------------------
# repair() — the write boundary
# ---------------------------------------------------------------------------
_GROUPS = [
    SimpleNamespace(sport_key="baseball_mlb", game_date=date(2026, 8, 9), n=3),
]

_EVENTS = [
    # 1. score_drifted — espn_id proven, score frozen. MUST get the score write.
    SimpleNamespace(
        event_id=1001, espn_id="S1", sport_key="baseball_mlb", ev_status="completed",
        home_team_name="Chicago Cubs", away_team_name="Milwaukee Brewers",
        home_score=0, away_score=0,
        commence_time=datetime(2026, 8, 9, 18, 0, tzinfo=UTC),
        completed_at=datetime(2026, 8, 9, 21, 0, tzinfo=UTC), game_date=date(2026, 8, 9),
    ),
    # 2. espn_id_drifted (ev15191123's shape) — score already CORRECT, id names
    #    the previous day's game. MUST NEVER be written.
    SimpleNamespace(
        event_id=1002, espn_id="401816441", sport_key="baseball_mlb",
        ev_status="completed",
        home_team_name="New York Yankees", away_team_name="Atlanta Braves",
        home_score=1, away_score=2,
        commence_time=datetime(2026, 8, 9, 17, 35, tzinfo=UTC),
        completed_at=datetime(2026, 8, 9, 20, 30, tzinfo=UTC), game_date=date(2026, 8, 9),
    ),
    # 3. espn_id_unresolvable — id absent and no game on our slate is our
    #    fixture. Reported, never claimed, never written.
    SimpleNamespace(
        event_id=1003, espn_id="GHOST", sport_key="baseball_mlb",
        ev_status="completed",
        home_team_name="Seattle Mariners", away_team_name="Texas Rangers",
        home_score=3, away_score=1,
        commence_time=datetime(2026, 8, 9, 19, 0, tzinfo=UTC),
        completed_at=datetime(2026, 8, 9, 22, 0, tzinfo=UTC), game_date=date(2026, 8, 9),
    ),
]

_BOARDS = {
    ("baseball_mlb", "20260809"): [
        _game("S1", "Chicago Cubs", "Milwaukee Brewers", 7, 5,
              datetime(2026, 8, 9, 18, 0, tzinfo=UTC)),
        _game("401816456", "New York Yankees", "Atlanta Braves", 1, 2,
              datetime(2026, 8, 9, 17, 35, tzinfo=UTC)),
    ],
}


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows

    def one(self):
        return self._rows[0]

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None


class _Session:
    def __init__(self):
        self.score_writes = []
        self.commits = 0

    async def execute(self, stmt, params=None):
        sql = str(stmt)
        if "GROUP BY 1, 2" in sql:
            return _Result(list(_GROUPS))
        if "unnest(" in sql:
            return _Result(list(_EVENTS))
        if "MAX(x.captured_at)" in sql:
            return _Result([])
        if "COUNT(*) AS n" in sql:
            return _Result([SimpleNamespace(n=len(_EVENTS))])
        if "UPDATE events SET home_score" in sql:
            self.score_writes.append(params)
            return _Result([])
        if "UPDATE events SET completed_at" in sql:
            return _Result([])
        if sql.startswith("SELECT events.win_probability_sources"):
            return _Result([{"final_result": {"probability": 0.0}}])
        if sql.startswith("UPDATE events SET win_probability_sources"):
            return _Result([])
        raise AssertionError(f"unexpected SQL: {sql[:160]}")

    async def commit(self):
        self.commits += 1


def _fake_espn():
    svc = SimpleNamespace()
    svc.get_scoreboard = AsyncMock(
        side_effect=lambda sport_key, d: list(_BOARDS.get((sport_key, d), []))
    )
    return svc


async def _run(**kw):
    from scripts import repair_event_final_scores as mod

    s = _Session()
    with patch("app.services.espn_api.get_espn_service", return_value=_fake_espn()):
        res = await mod.repair(s, kw.pop("apply", False), **kw)
    return s, res


def _by_event(ledger):
    return {e["event_id"]: e for e in ledger if "event_id" in e}


class TestTheSplitAtTheWriteBoundary:
    """BOTH directions (gotcha #43): the score class still gets the score remedy
    AND the linkage class is reported and never gets it."""

    @pytest.mark.asyncio
    async def test_score_class_still_gets_the_score_write(self):
        s, res = await _run(apply=True)
        assert res["score_defects"] == 1
        assert [w["event_id"] for w in s.score_writes] == [1001]
        assert s.score_writes[0]["home_score"] == 7
        assert s.score_writes[0]["away_score"] == 5

    @pytest.mark.asyncio
    async def test_linkage_class_is_never_written(self):
        """The whole point. ev1002's stored 1-2 is CORRECT; the score remedy
        would have written its espn_id's game (5-4) over it."""
        s, _ = await _run(apply=True)
        written = {w["event_id"] for w in s.score_writes}
        assert 1002 not in written
        assert 1003 not in written

    @pytest.mark.asyncio
    async def test_every_disposition_lands_in_the_ledger(self):
        """The silent skip is gone. ``espn_not_found`` used to be a bare counter
        with NO ledger row — neither repaired nor reported."""
        _, res = await _run()
        led = _by_event(res["ledger"])
        assert set(led) == {1001, 1002, 1003}
        assert led[1001]["defect_class"] == SCORE_DRIFTED
        assert led[1002]["defect_class"] == ESPN_ID_DRIFTED
        assert led[1003]["defect_class"] == ESPN_ID_UNRESOLVABLE

    @pytest.mark.asyncio
    async def test_the_linkage_row_carries_the_linkage_remedy_and_not_the_score_one(self):
        _, res = await _run()
        led = _by_event(res["ledger"])
        linkage = led[1002]["remedy"]
        assert "event-espn-id" in linkage
        assert "event-final-scores" not in linkage
        # ...and the score row keeps the score remedy.
        assert "event-final-scores" in led[1001]["remedy"]

    @pytest.mark.asyncio
    async def test_the_linkage_row_names_its_proven_target(self):
        _, res = await _run()
        assert _by_event(res["ledger"])[1002]["proposed_espn_id"] == "401816456"
        assert res["espn_id_drifted_with_target"] == 1

    @pytest.mark.asyncio
    async def test_the_unresolvable_row_proposes_nothing(self):
        _, res = await _run()
        row = _by_event(res["ledger"])[1003]
        assert "proposed_espn_id" not in row
        assert "NO remedy is proven" in row["remedy"]
        assert "event-final-scores" not in row["remedy"]

    @pytest.mark.asyncio
    async def test_the_classes_are_counted_separately_and_never_summed(self):
        _, res = await _run()
        assert res["score_defects"] == 1
        assert res["espn_id_drifted"] == 1
        assert res["espn_id_unresolvable"] == 1
        # The legacy counters keep their old meanings so nothing downstream that
        # reads them silently changes what it is reading.
        assert res["espn_not_found"] == 2


# ---------------------------------------------------------------------------
# The sentinel detectors
# ---------------------------------------------------------------------------
_LEDGER = [
    {"action": "fix_score", "defect_class": "score_drifted", "event_id": 1001,
     "sport_key": "baseball_mlb", "matchup": "Chicago Cubs vs Milwaukee Brewers",
     "status": "completed", "stored_score": "0-0", "espn_final": "7-5",
     "winner_flip": True},
    {"action": "skip_espn_id_off_slate", "defect_class": "espn_id_drifted",
     "event_id": 1002, "sport_key": "baseball_mlb",
     "matchup": "New York Yankees vs Atlanta Braves", "status": "completed",
     "espn_id": "401816441", "proposed_espn_id": "401816456",
     "stored_score": "1-2", "reason": "espn_id is absent from this row's own slate"},
    {"action": "skip_espn_id_off_slate", "defect_class": "espn_id_unresolvable",
     "event_id": 1003, "sport_key": "baseball_mlb",
     "matchup": "Seattle Mariners vs Texas Rangers", "espn_id": "GHOST",
     "stored_score": "3-1", "reason": "NO game on that slate is our fixture"},
    {"action": "fix_completed_at_only", "event_id": 1004, "sport_key": "baseball_mlb"},
]


class TestDetectorsPartitionTheLedger:
    def test_score_detector_returns_only_the_score_class(self):
        assert [f["event_id"] for f in frozen_final_score_events(_LEDGER)] == [1001]

    def test_linkage_detector_returns_only_the_linkage_class(self):
        found = espn_id_linkage_defects(_LEDGER)
        assert [f["event_id"] for f in found] == [1002]
        assert found[0]["proposed_espn_id"] == "401816456"

    def test_unresolvable_rows_are_their_own_class(self):
        found = espn_id_unresolvable_rows(_LEDGER)
        assert [f["event_id"] for f in found] == [1003]
        assert "NOT the score repair" in found[0]["remedy"]

    def test_no_row_appears_in_two_classes(self):
        ids = (
            [f["event_id"] for f in frozen_final_score_events(_LEDGER)]
            + [f["event_id"] for f in espn_id_linkage_defects(_LEDGER)]
            + [f["event_id"] for f in espn_id_unresolvable_rows(_LEDGER)]
        )
        assert len(ids) == len(set(ids))

    def test_a_clean_ledger_is_green_for_all_three(self):
        assert frozen_final_score_events([]) == []
        assert espn_id_linkage_defects([]) == []
        assert espn_id_unresolvable_rows([]) == []


# ---------------------------------------------------------------------------
# One measurement, two flows
# ---------------------------------------------------------------------------
_REPAIR_RESULT = {
    "result": {
        "events_scanned": 87,
        "groups_scanned": 6,
        "groups_total": 998,
        "groups_remaining": 992,
        "next_offset": 6,
        "population": 14300,
        "score_defects": 1,
        "espn_id_drifted": 1,
        "espn_id_drifted_with_target": 1,
        "espn_id_unresolvable": 1,
        "winner_flips": 1,
        "coverage": {
            "mode": "sampled", "groups_scanned": 6, "groups_total": 998,
            "group_sample_rate": 0.006, "events_scanned": 87,
            "population": 14300, "event_sample_rate": 0.0061,
        },
        "ledger": _LEDGER,
    }
}


class _FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _FakeClient:
    def __init__(self, payload):
        self._payload = payload
        self.posts = 0

    async def post(self, path, **kwargs):
        self.posts += 1
        return _FakeResp(self._payload)


async def _flows(payload=_REPAIR_RESULT, token="tok"):
    from app.tasks import flow_sentinel as fs

    client = _FakeClient(payload)
    with patch.dict("os.environ", {"ADMIN_TOKEN": token} if token else {}, clear=False):
        if not token:
            import os

            os.environ.pop("ADMIN_TOKEN", None)
        out = await fs._run_settled_score_integrity(client)
    return client, {f["flow"]: f for f in out}


class TestOneMeasurementTwoFlows:
    @pytest.mark.asyncio
    async def test_both_flows_come_from_a_single_http_call(self):
        """The ESPN scoreboard fetches are the expensive half (~0.66 s per
        (sport, date) group, measured). Measuring twice would double the nightly
        cost to learn nothing new."""
        client, flows = await _flows()
        assert client.posts == 1
        assert set(flows) == {"frozen_final_scores", "espn_id_linkage_drift"}

    @pytest.mark.asyncio
    async def test_the_score_flow_carries_only_the_score_class(self):
        _, flows = await _flows()
        f = flows["frozen_final_scores"]
        assert len(f["failures"]) == 1
        assert f["failures"][0]["event_id"] == 1001
        assert "event-final-scores?apply=true" in f["failures"][0]["detail"]

    @pytest.mark.asyncio
    async def test_the_linkage_flow_is_reported_and_never_handed_the_score_remedy(self):
        """The load-bearing assertion of #1980. The rail DID skip these rows —
        silently — so they were neither repaired nor reported, and the remedy
        printed on every failing line was the one that corrupts them."""
        _, flows = await _flows()
        f = flows["espn_id_linkage_drift"]
        assert f["passed"] is False
        assert len(f["failures"]) == 1
        detail = f["failures"][0]["detail"]
        assert "event-espn-id" in detail
        assert "DO NOT run event-final-scores" in detail
        assert "event-final-scores?apply=true" not in detail
        assert f["failures"][0]["proposed_espn_id"] == "401816456"

    @pytest.mark.asyncio
    async def test_the_linkage_row_is_absent_from_the_score_flow(self):
        _, flows = await _flows()
        assert all(
            x["event_id"] != 1002 for x in flows["frozen_final_scores"]["failures"]
        )

    @pytest.mark.asyncio
    async def test_unresolvable_rows_are_surfaced_but_never_failed(self):
        """Gotcha #53 in both directions: an empty read is not a fact (so it does
        not fail the flow) and it is not nothing either (so it is written down)."""
        _, flows = await _flows()
        f = flows["espn_id_linkage_drift"]
        watch = f["evidence"]["espn_id_unresolvable_watch"]
        assert [w["event_id"] for w in watch] == [1003]
        assert all(x["event_id"] != 1003 for x in f["failures"])

    @pytest.mark.asyncio
    async def test_both_flows_report_unknown_when_the_instrument_is_broken(self):
        _, flows = await _flows(payload={"result": {}})
        assert set(flows) == {"frozen_final_scores", "espn_id_linkage_drift"}
        assert all(f.get("unknown") for f in flows.values())

    @pytest.mark.asyncio
    async def test_a_crash_still_emits_a_result_for_every_flow_the_runner_owns(self):
        """A runner that owns two flows must not be able to delete one from the
        scorecard by throwing — that is the same invisibility this split closes."""
        from app.tasks import flow_sentinel as fs

        names = [n for n, _ in _runner_entries(fs)]
        assert ("frozen_final_scores", "espn_id_linkage_drift") in names


def _runner_entries(fs):
    """Read the runner registry out of ``_run_flow_sentinel``'s source, which is
    where the (names, runner) pairs are declared."""
    import inspect
    import re

    src = inspect.getsource(fs._run_flow_sentinel)
    out = []
    for m in re.finditer(r'\(\("([a-z_]+)", "([a-z_]+)"\), (_run_[a-z_]+)\)', src):
        out.append(((m.group(1), m.group(2)), m.group(3)))
    return out


class TestFlowRegistration:
    def test_the_new_flow_has_a_title_and_an_area_label(self):
        from app.tasks.flow_sentinel import _FLOW_AREA_LABELS, _FLOW_TITLES

        assert "espn_id_linkage_drift" in _FLOW_TITLES
        # A LINKAGE defect routes to event-details, not calibration: filing it
        # next to the score class is how the wrong remedy gets applied.
        assert _FLOW_AREA_LABELS["espn_id_linkage_drift"] == "area:event-details"

    def test_the_two_flows_get_distinct_dedup_fingerprints(self):
        from app.tasks.flow_sentinel import flow_fingerprint

        assert flow_fingerprint("frozen_final_scores") != flow_fingerprint(
            "espn_id_linkage_drift"
        )

    def test_the_runner_registry_declares_both_names(self):
        from app.tasks import flow_sentinel as fs

        assert _runner_entries(fs) == [
            (("frozen_final_scores", "espn_id_linkage_drift"),
             "_run_settled_score_integrity"),
        ]


# ---------------------------------------------------------------------------
# (b) The denominator
# ---------------------------------------------------------------------------
class TestSampledDenominatorIsLabelled:
    """A gate that reports a specific integer while measuring 0.6% of its surface
    READS AS A POPULATION. The sample stays; the label is the fix."""

    def test_coverage_marks_a_partial_scan_as_sampled(self):
        cov = measurement_coverage(
            groups_scanned=6, groups_total=998, events_scanned=87, population=14300
        )
        assert cov["mode"] == "sampled"
        assert cov["group_sample_rate"] == 0.006
        assert cov["population"] == 14300

    def test_coverage_marks_a_complete_scan_as_full(self):
        cov = measurement_coverage(
            groups_scanned=12, groups_total=12, events_scanned=140, population=140
        )
        assert cov["mode"] == "full"
        assert cov["event_sample_rate"] == 1.0

    def test_the_flow_carries_the_coverage_and_a_reader_warning(self):
        cov = sampled_measurement(_REPAIR_RESULT["result"])
        assert cov["mode"] == "sampled"
        assert "Do not quote it as a total" in cov["reader_warning"]

    def test_an_older_deploy_without_coverage_is_reconstructed_not_dropped(self):
        """An absent label would reintroduce exactly the ambiguity this removes."""
        legacy = dict(_REPAIR_RESULT["result"])
        legacy.pop("coverage")
        cov = sampled_measurement(legacy)
        assert cov["mode"] == "sampled"
        assert cov["population"] == 14300

    def test_the_title_says_SAMPLE_and_names_the_population(self):
        flow = {"flow": "frozen_final_scores", "checked": 87,
                "failures": [{"detail": "x"}],
                "coverage": _REPAIR_RESULT["result"]["coverage"]}
        title = build_flow_issue_title(flow)
        assert "SAMPLE of 87/14300 events" in title
        assert "0.6% of the population" in title

    def test_a_flow_with_no_coverage_renders_exactly_as_before(self):
        """Additive for every other flow — this must not churn 14 issue titles."""
        flow = {"flow": "duplicate_events", "checked": 49,
                "failures": [{"detail": "a"}, {"detail": "b"}]}
        assert coverage_phrase(flow) == "2 failing, 49 checked"
        assert build_flow_issue_title(flow).endswith("(2 failing, 49 checked)")

    def test_a_full_scan_is_not_labelled_sampled(self):
        flow = {"flow": "frozen_final_scores", "checked": 140,
                "failures": [{"detail": "x"}],
                "coverage": measurement_coverage(
                    groups_scanned=12, groups_total=12, events_scanned=140,
                    population=140)}
        assert coverage_phrase(flow) == "1 failing, 140 checked"

    def test_the_issue_body_carries_the_sampled_banner_and_the_extrapolation(self):
        flow = {"flow": "frozen_final_scores", "checked": 87,
                "failures": [{"detail": "x"}],
                "coverage": _REPAIR_RESULT["result"]["coverage"],
                "evidence": {"estimated_population_failures": 164}}
        body = build_flow_issue_body(flow)
        assert "SAMPLED MEASUREMENT" in body
        assert "6 of 998" in body
        assert "~164 failing" in body

    def test_the_redetect_comment_carries_the_denominator_too(self):
        """UX-P091 proved the comment is the only live channel on a deduped
        issue; a denominator missing there is a denominator missing full stop."""
        flow = {"flow": "frozen_final_scores", "checked": 87,
                "failures": [{"detail": "x"}],
                "coverage": _REPAIR_RESULT["result"]["coverage"]}
        assert "SAMPLE of 87/14300" in build_flow_redetect_comment(flow)

    def test_extrapolation_is_None_when_there_is_no_rate_to_scale_by(self):
        assert estimated_population_defects(3, {}) is None
        assert estimated_population_defects(3, {"event_sample_rate": 0}) is None

    def test_extrapolation_scales_the_sample_count(self):
        assert estimated_population_defects(1, {"event_sample_rate": 0.0061}) == 164

    @pytest.mark.asyncio
    async def test_both_flows_report_the_same_coverage_from_the_shared_call(self):
        _, flows = await _flows()
        a = flows["frozen_final_scores"]["coverage"]
        b = flows["espn_id_linkage_drift"]["coverage"]
        assert a == b
        assert a["mode"] == "sampled"

    @pytest.mark.asyncio
    async def test_the_class_counts_are_reported_side_by_side_never_summed(self):
        _, flows = await _flows()
        counts = flows["espn_id_linkage_drift"]["evidence"]["class_counts"]
        assert counts == {
            "score_drifted": 1,
            "espn_id_drifted": 1,
            "espn_id_drifted_with_target": 1,
            "espn_id_unresolvable": 1,
        }
