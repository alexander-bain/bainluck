"""#2351 — the team-total repair writes only legs their own final score contradicts.

Three specimens, all from the issue record:

* ``KXMLBTEAMTOTAL-26JUN052015CINSTL`` (`docs/mockups/data/reds.json`):
  Cincinnati 3 – St. Louis 5, fourteen "over" legs, stored all-True by the old
  one-leg writer. Truth is six winners and eight losers.
* Boston Red Sox 1 – Tampa Bay Rays 4 (issue comment, 2026-08-30): four legs
  stored True that the score refutes.
* Event 14788069, market 53667298, outcomes 201010270–201010276 (Rays @
  Yankees, 2026-09-22 game 1, final Yankees 2 – Rays 0): all seven legs stored
  True. That grade post-dates the CERT-495 writer, so it also gets a FORWARD
  check below: the shipped resolver, run over the same seven legs under both
  scores that row has carried (2–0 and the game-2 final 1–6, either way round),
  never writes that ladder. Nothing saved names what the event held when it was
  graded; that question goes to the measurement lane, not into this file.
"""

import pytest

import app.tasks.repair_team_total_game_score as rt

# ---------------------------------------------------------------------------
# specimens
# ---------------------------------------------------------------------------

_LINES = (1.5, 2.5, 3.5, 4.5, 5.5, 6.5, 7.5)
CINSTL = {
    "market_id": 7, "ticker": "KXMLBTEAMTOTAL-26JUN052015CINSTL",
    "market_name": "Cincinnati vs St. Louis: Team Total", "event_id": 42,
    "event_status": "completed", "home_team_name": "Cincinnati Reds",
    "away_team_name": "St. Louis Cardinals", "home_score": 3, "away_score": 5,
    "commence_time": None, "completed_at": None, "score_source": None,
}
CINSTL_LEGS = [
    {"id": 100 + i, "name": f"{team} over {line} runs scored",
     "is_winner": True, "resolution_source": "game_score"}
    for i, (team, line) in enumerate(
        [("Cincinnati", ln) for ln in _LINES] + [("St. Louis", ln) for ln in _LINES]
    )
]


def _truth(name, home_runs, away_runs, home_city):
    team, rest = name.split(" over ")
    return (home_runs if team == home_city else away_runs) > float(rest.split()[0])


RAYS_YANKEES = {
    "market_id": 53667298, "ticker": "KXMLBTEAMTOTAL-26SEP22TBNYY",
    "market_name": "Tampa Bay vs New York Y: Team Total", "event_id": 14788069,
    "event_status": "completed", "home_team_name": "New York Yankees",
    "away_team_name": "Tampa Bay Rays", "home_score": 2, "away_score": 0,
    "commence_time": None, "completed_at": None, "score_source": "mlb_statsapi",
}
RAYS_YANKEES_LEGS = [
    {"id": oid, "name": name, "is_winner": True, "resolution_source": "game_score"}
    for oid, name in zip(range(201010270, 201010277), [
        "Tampa Bay over 2.5 runs scored", "Tampa Bay over 3.5 runs scored",
        "Tampa Bay over 4.5 runs scored", "Tampa Bay over 6.5 runs scored",
        "New York Y over 2.5 runs scored", "New York Y over 3.5 runs scored",
        "New York Y over 6.5 runs scored",
    ])
]


def _states(decision):
    return {g["id"]: g["state"] for g in decision["legs"]}


# ---------------------------------------------------------------------------
# the verdict: one leg, its own team, its own line
# ---------------------------------------------------------------------------

class TestOnlyContradictedLegsAreWritten:
    def test_the_captured_ladder_writes_its_eight_false_legs_and_nothing_else(self):
        d = rt.decide_market(CINSTL, CINSTL_LEGS, [])
        assert d["action"] == "plan"
        expected_false = {
            leg["id"] for leg in CINSTL_LEGS
            if not _truth(leg["name"], 3, 5, "Cincinnati")
        }
        assert len(expected_false) == 8
        assert {w["outcome_id"] for w in d["writes"]} == expected_false
        assert all(w["prior"] is True and w["verdict"] is False for w in d["writes"])
        states = _states(d)
        assert sum(s == "already_correct" for s in states.values()) == 6
        assert sum(s == "contradicted" for s in states.values()) == 8

    def test_a_correct_ladder_plans_no_write(self):
        legs = [{**leg, "is_winner": _truth(leg["name"], 3, 5, "Cincinnati")}
                for leg in CINSTL_LEGS]
        d = rt.decide_market(CINSTL, legs, [])
        assert d["action"] == "plan" and d["writes"] == []

    def test_the_issues_boston_example(self):
        m = {**CINSTL, "ticker": "KXMLBTEAMTOTAL-26AUG01BOSTB",
             "home_team_name": "Boston Red Sox", "away_team_name": "Tampa Bay Rays",
             "home_score": 1, "away_score": 4}
        legs = [
            {"id": 1, "name": "Boston over 2.5 runs scored", "is_winner": True,
             "resolution_source": "game_score"},
            {"id": 2, "name": "Boston over 4.5 runs scored", "is_winner": True,
             "resolution_source": "game_score"},
            {"id": 3, "name": "Boston over 7.5 runs scored", "is_winner": True,
             "resolution_source": "game_score"},
            {"id": 4, "name": "Tampa Bay over 5.5 runs scored", "is_winner": True,
             "resolution_source": "game_score"},
            {"id": 5, "name": "Tampa Bay over 3.5 runs scored", "is_winner": True,
             "resolution_source": "game_score"},
        ]
        d = rt.decide_market(m, legs, [])
        assert {w["outcome_id"]: w["verdict"] for w in d["writes"]} == {
            1: False, 2: False, 3: False, 4: False,
        }
        assert _states(d)[5] == "already_correct"

    def test_the_rays_yankees_ladder_is_all_false_at_two_nil(self):
        d = rt.decide_market(RAYS_YANKEES, RAYS_YANKEES_LEGS, [])
        assert {w["outcome_id"] for w in d["writes"]} == set(range(201010270, 201010277))
        assert all(w["verdict"] is False for w in d["writes"])

    def test_a_leg_another_source_graded_is_never_touched(self):
        legs = [dict(leg) for leg in CINSTL_LEGS]
        legs[-1]["resolution_source"] = "api_settlement"  # St. Louis over 7.5, True
        d = rt.decide_market(CINSTL, legs, [])
        assert legs[-1]["id"] not in {w["outcome_id"] for w in d["writes"]}
        assert _states(d)[legs[-1]["id"]] == "not_game_score"

    def test_an_unattributable_or_unparseable_or_ungraded_leg_is_counted_not_written(self):
        legs = CINSTL_LEGS[:2] + [
            {"id": 900, "name": "Toronto over 1.5 runs scored", "is_winner": True,
             "resolution_source": "game_score"},
            {"id": 901, "name": "Yes", "is_winner": True,
             "resolution_source": "game_score"},
            {"id": 902, "name": "St. Louis over 9.5 runs scored", "is_winner": None,
             "resolution_source": "game_score"},
        ]
        d = rt.decide_market(CINSTL, legs, [])
        states = _states(d)
        assert states[900] == "unresolved_identity"
        assert states[901] == "unparseable"
        assert states[902] == "prior_unknown"
        assert {w["outcome_id"] for w in d["writes"]} <= {100, 101}

    def test_shared_city_clubs_are_refused_not_guessed(self):
        m = {**CINSTL, "home_team_name": "New York Yankees",
             "away_team_name": "New York Mets", "home_score": 2, "away_score": 6}
        legs = [{"id": 1, "name": "New York over 4.5 runs scored", "is_winner": True,
                 "resolution_source": "game_score"}]
        d = rt.decide_market(m, legs, [])
        assert _states(d)[1] == "unresolved_identity" and d["writes"] == []


# ---------------------------------------------------------------------------
# when the score itself is not trusted, the whole market is skipped by name
# ---------------------------------------------------------------------------

class TestUntrustedScoreSkipsTheMarket:
    @pytest.mark.parametrize("patch,reason", [
        ({"event_id": None}, "no_linked_event"),
        ({"event_status": "in_progress"}, "event_not_final"),
        ({"event_status": None}, "event_not_final"),
        ({"home_score": None}, "no_final_score"),
        ({"market_name": "Cincinnati vs St. Louis: First Half Team Total"}, "period_market"),
    ])
    def test_skip_reasons(self, patch, reason):
        d = rt.decide_market({**CINSTL, **patch}, CINSTL_LEGS, [])
        assert d["action"] == "skip" and d["reason"] == reason, d

    def test_a_completion_before_the_start_is_a_merge_not_a_final(self):
        from datetime import datetime, timezone
        m = {**CINSTL, "commence_time": datetime(2026, 6, 5, 23, tzinfo=timezone.utc),
             "completed_at": datetime(2026, 6, 5, 20, tzinfo=timezone.utc)}
        assert rt.decide_market(m, CINSTL_LEGS, [])["reason"] == "completed_before_commence"

    def test_the_venues_own_grade_on_the_event_vetoes_a_wrong_score(self):
        """The 14788069 shape: the game-2 final (1–6) written onto game 1. A
        venue-graded game-total leg on the same event pins the total below 6.5;
        a score that says 7 is refused rather than graded from. (The witness
        here is constructed for the shape — the issue does not name the event's
        52 api_settlement legs.)"""
        wrong = {**RAYS_YANKEES, "home_score": 6, "away_score": 1}
        witness = {"id": 1, "name": "Over 6.5 runs scored", "is_winner": False,
                   "ticker": "KXMLBTOTAL-26SEP22TBNYY", "market_name": "Total runs"}
        d = rt.decide_market(wrong, RAYS_YANKEES_LEGS, [witness])
        assert d["action"] == "skip" and d["reason"] == "score_contradicted_by_venue"
        assert d["detail"][0]["venue"] is False and d["detail"][0]["score_implies"] is True

    def test_a_concordant_witness_is_recorded_and_does_not_block(self):
        witness = {"id": 1, "name": "Over 6.5 runs scored", "is_winner": False,
                   "ticker": "KXMLBTOTAL-26SEP22TBNYY", "market_name": "Total runs"}
        d = rt.decide_market(RAYS_YANKEES, RAYS_YANKEES_LEGS, [witness])
        assert d["action"] == "plan" and d["witness"] == {"checked": 1, "concordant": 1}
        assert len(d["writes"]) == 7

    def test_a_venue_graded_sibling_in_the_same_market_testifies_too(self):
        witness = {"id": 9, "name": "New York Y over 1.5 runs scored", "is_winner": True,
                   "ticker": RAYS_YANKEES["ticker"], "market_name": RAYS_YANKEES["market_name"]}
        d = rt.decide_market({**RAYS_YANKEES, "home_score": 0, "away_score": 0},
                             RAYS_YANKEES_LEGS, [witness])
        assert d["reason"] == "score_contradicted_by_venue"

    def test_a_period_witness_cannot_testify_about_the_full_game(self):
        witness = {"id": 1, "name": "Over 6.5 runs scored", "is_winner": True,
                   "ticker": "KXMLBF5TOTAL-26SEP22TBNYY", "market_name": "First 5 innings total"}
        d = rt.decide_market(RAYS_YANKEES, RAYS_YANKEES_LEGS, [witness])
        assert d["action"] == "plan" and d["witness"] == "none"


# ---------------------------------------------------------------------------
# pinned identity
# ---------------------------------------------------------------------------

def _planned(**over):
    base = {"outcome_id": 1, "market_id": 7, "event_id": 42, "prior": True,
            "verdict": False, "home_score": 3, "away_score": 5,
            "name": "Cincinnati over 3.5 runs scored", "home": "Cincinnati Reds",
            "away": "St. Louis Cardinals"}
    return {**base, **over}


class TestPlanHash:
    def test_order_independent(self):
        a, b = _planned(outcome_id=1), _planned(outcome_id=2)
        assert rt.plan_hash_for([a, b]) == rt.plan_hash_for([b, a])

    @pytest.mark.parametrize("field,value", [
        ("outcome_id", 3), ("prior", False), ("home_score", 4), ("away_score", 6),
        ("event_id", 43), ("name", "Cincinnati over 4.5 runs scored"),
        ("home", "Cincinnati"),
    ])
    def test_every_fact_the_apply_rechecks_moves_the_hash(self, field, value):
        assert rt.plan_hash_for([_planned()]) != rt.plan_hash_for([_planned(**{field: value})])

    def test_only_ids_parsing(self):
        assert rt.parse_only_ids(None) is None
        assert rt.parse_only_ids("201010270, 201010271") == {201010270, 201010271}
        for bad in ("", ",", "12,x", "-1"):
            with pytest.raises(ValueError):
                rt.parse_only_ids(bad)


class _NoSession:
    async def execute(self, *a, **k):
        raise AssertionError("a refused call must not touch the database")


@pytest.mark.asyncio
class TestRefusalsWriteNothing:
    async def test_apply_without_a_reviewed_plan_is_refused(self):
        out = await rt.repair(_NoSession(), apply=True)
        assert out["terminal"] == "refused_no_plan_hash" and out["legs_written"] == 0

    async def test_a_malformed_pin_is_refused(self):
        out = await rt.repair(_NoSession(), apply=True, only_ids="", plan_hash="x")
        assert out["terminal"] == "refused_bad_only_ids"


def test_the_rail_is_registered_and_never_scheduled():
    from app.routes.admin_repairs import _REPAIRS
    assert _REPAIRS["team-total-game-score"] == (rt.__name__, "repair")
    assert _REPAIRS["team-total-game-score-restore"] == (rt.__name__, "restore")
    from app.tasks import celery_app
    beat = repr(celery_app.conf.beat_schedule)
    assert "team_total_game_score" not in beat and "team-total-game-score" not in beat


# ---------------------------------------------------------------------------
# forward check: the shipped writer cannot produce the 14788069 ladder
# ---------------------------------------------------------------------------

class _Row:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class _Result:
    def __init__(self, rows, rowcount=1):
        self._rows, self.rowcount = rows, rowcount

    def all(self):
        return self._rows


class _Recorder:
    def __init__(self, legs):
        self._legs, self.writes = legs, {}

    async def execute(self, stmt, params=None):
        sql = str(getattr(stmt, "text", stmt))
        if params and "oid" in params:
            self.writes[params["oid"]] = params["won"]
            return _Result([])
        if "FROM futures_outcomes" in sql:
            return _Result([_Row(market_id=RAYS_YANKEES["market_id"], id=leg["id"],
                                 name=leg["name"]) for leg in self._legs])
        return _Result([])

    async def commit(self):
        return None


class _CM:
    def __init__(self, s):
        self._s = s

    async def __aenter__(self):
        return self._s

    async def __aexit__(self, *a):
        return False


@pytest.mark.asyncio
@pytest.mark.parametrize("home_runs,away_runs", [(2, 0), (6, 1), (1, 6)])
async def test_the_shipped_writer_never_writes_the_rays_yankees_ladder(
    monkeypatch, home_runs, away_runs
):
    import app.tasks.backfill_winners as bw

    rec = _Recorder(RAYS_YANKEES_LEGS)
    monkeypatch.setattr(bw, "get_task_session", lambda: _CM(rec))
    candidate = _Row(
        market_id=RAYS_YANKEES["market_id"], ticker=RAYS_YANKEES["ticker"],
        market_name=RAYS_YANKEES["market_name"], event_id=RAYS_YANKEES["event_id"],
        home_team_name=RAYS_YANKEES["home_team_name"],
        away_team_name=RAYS_YANKEES["away_team_name"],
        home_score=home_runs, away_score=away_runs,
    )
    await bw._resolve_kalshi_spread_total_from_scores(
        {"candidates": [candidate], "locked_market_ids": frozenset()}
    )
    assert set(rec.writes) == {leg["id"] for leg in RAYS_YANKEES_LEGS}
    expected = {
        leg["id"]: _truth(leg["name"].replace("New York Y", "NYY"),
                          home_runs, away_runs, "NYY")
        for leg in RAYS_YANKEES_LEGS
    }
    assert rec.writes == expected
    assert not all(rec.writes.values()), "the all-True ladder is not a score this writer can produce"
