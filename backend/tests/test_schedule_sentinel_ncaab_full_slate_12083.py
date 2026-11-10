"""#12083: the NCAAB Schedule Sentinel reads ESPN's whole Division I board and
stops filing the right club as MISATTACHED.

**SHIP: the three finished college basketball games that show the wrong winner
(#12379) are filed as score disagreements, instead of hiding among 48 false
findings that said our real games "never happened".** (Pillar: TRUTH.)

Measured Sun Nov 8 (read-only SQL plus ESPN's public scoreboard; replayed offline
through ``reconcile`` + ``classify_findings`` on the same 95 NCAAB rows):

* ESPN's default ``mens-college-basketball`` board is the featured slate: 2, 4
  and 5 games on Nov 7, 8 and 9. With ``groups=50`` it lists 61, 36 and 50.
* Base code on the default board: 48 REAL (46 EXTRA, 2 MISATTACHED), which is
  the 08:09Z run exactly. This code on the full board: 8 REAL, namely the 3
  wrong-score games and 5 EXTRA whose spellings no rule here reads (CSU / Cal
  State, LIU, UT Martin + IU Indianapolis, GW, Antelopes / Lopes).
* The 2 MISATTACHED rows point at the right club: one team row each, carrying
  ESPN's own id. "Wichita St" vs "Wichita State" scored 0.5 under a 0.60 bar.
  NCAAF's (#10783) is ``Appalachian State`` vs ESPN's ``App State``, same id.

WHAT EACH TEST DEFENDS:

* NCAAB asks ESPN for all of Division I; every other league's request is unchanged;
* the parse keeps ESPN's team ids and neutral-site flag;
* a college feed reads a non-leading "St" as "State", and nothing else moves;
* agreeing ESPN team ids clear a MISATTACHED spelling; nothing new is ever filed;
* 🔴 a reversal at a NEUTRAL site is explained, and its wrong score still files;
* 🔴 a reversal at a home venue still files.

Gotcha #44: every instant is a frozen constant and ``now`` is injected, so
``scripts/clock_sweep.py`` is invariant.
"""

import asyncio
import importlib
from datetime import date, datetime, timedelta, timezone

import pytest

ss = importlib.import_module("app.tasks.schedule_sentinel")

NOW = datetime(2026, 11, 8, 8, 9, tzinfo=timezone.utc)  # the 08:09Z run
TIPOFF = NOW - timedelta(hours=12)

NCAAB = next(s for s in ss.SCHEDULE_LEAGUES if s.slug == "ncaab")
NCAAF = next(s for s in ss.SCHEDULE_LEAGUES if s.slug == "ncaaf")


def _truth(home, away, *, key, hs=None, aws=None, home_id=None, away_id=None,
           neutral=False, start=TIPOFF):
    return ss.TruthGame(
        key=key, home=home, away=away, start=start, state="final",
        raw_state="STATUS_FINAL", home_score=hs, away_score=aws,
        home_team_id=home_id, away_team_id=away_id, neutral_site=neutral,
    )


def _ours(eid, home, away, *, hs=None, aws=None, espn_id=None, home_fk=None,
          away_fk=None, home_fk_espn=None, away_fk_espn=None, start=TIPOFF):
    return ss.OurEvent(
        id=eid, home_name=home, away_name=away, home_team_id=1, away_team_id=2,
        home_fk_name=home if home_fk is None else home_fk,
        away_fk_name=away if away_fk is None else away_fk,
        status="completed", home_score=hs, away_score=aws, commence_time=start,
        espn_id=espn_id, external_id=f"odds{eid}",
        home_fk_espn_id=home_fk_espn, away_fk_espn_id=away_fk_espn,
    )


def _run(spec, truth, ours):
    findings, _stats = ss.reconcile(truth, ours, spec, now=NOW)
    return ss.classify_findings(findings, spec, now=NOW)


def _checks(findings):
    return [f["check"] for f in findings]


# ── the request ──────────────────────────────────────────────────────────────


class _Response:
    def raise_for_status(self):
        return None

    def json(self):
        return {"leagues": [], "events": []}


class _Client:
    def __init__(self):
        self.calls = []

    async def get(self, url, params=None, timeout=None):
        self.calls.append((url, dict(params or {})))
        return _Response()


def _params_for(spec):
    client = _Client()
    asyncio.run(ss.fetch_truth(client, spec, date(2026, 11, 7)))
    assert len(client.calls) == 1
    return client.calls[0]


def test_ncaab_asks_espn_for_all_of_division_one():
    url, params = _params_for(NCAAB)
    assert url.endswith("/basketball/mens-college-basketball/scoreboard")
    assert params == {"dates": "20261107", "groups": "50", "limit": "500"}


@pytest.mark.parametrize("slug", ["nfl", "nba", "nhl", "wnba", "mls", "epl", "ucl", "ncaaf"])
def test_every_other_espn_league_still_asks_by_date_only(slug):
    spec = next(s for s in ss.SCHEDULE_LEAGUES if s.slug == slug)
    _url, params = _params_for(spec)
    assert params == {"dates": "20261107"}


# ── the parse ────────────────────────────────────────────────────────────────


def _espn_event(*, neutral=None, home_id="2724", away_id="2413"):
    comp = {
        "status": {"type": {"name": "STATUS_FINAL"}},
        "competitors": [
            {"homeAway": "home", "score": "78",
             "team": {"id": home_id, "displayName": "Wichita State Shockers"}},
            {"homeAway": "away", "score": "76",
             "team": {"id": away_id, "displayName": "Morehead State Eagles"}},
        ],
    }
    if neutral is not None:
        comp["neutralSite"] = neutral
    return {"events": [{"id": "401", "date": "2026-11-07T19:00Z", "competitions": [comp]}]}


def test_the_parse_keeps_espns_team_ids_and_neutral_site():
    game = ss.parse_espn_payload(_espn_event(neutral=True)).games[0]
    assert (game.home_team_id, game.away_team_id, game.neutral_site) == ("2724", "2413", True)


def test_a_missing_id_or_flag_parses_as_absent():
    game = ss.parse_espn_payload(_espn_event(home_id=None, away_id="")).games[0]
    assert (game.home_team_id, game.away_team_id, game.neutral_site) == (None, None, False)


# ── college names ────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "ours, espn",
    [
        ("Wichita St Shockers", "Wichita State Shockers"),
        ("Morehead St Eagles", "Morehead State Eagles"),
        ("Michigan St Spartans", "Michigan State Spartans"),
        ("Sacramento St Hornets", "Sacramento State Hornets"),
    ],
)
def test_a_non_leading_st_is_state_in_a_college_feed(ours, espn):
    assert ss.name_similarity(ours, espn) < ss.MATCH_BAR  # the false MISATTACHED
    assert ss.name_similarity(ours, espn, college=True) == 1.0


def test_a_leading_st_stays_saint():
    assert ss._norm_name("St. John's Red Storm", college=True) == "st johns red storm"
    assert ss._norm_name("St. Bonaventure Bonnies", college=True) == "st bonaventure bonnies"


def test_the_st_a_city_fold_writes_is_never_read_as_state():
    assert ss._norm_name("STL Cardinals", college=True) == ss._norm_name("STL Cardinals")


def test_outside_a_college_feed_nothing_moves():
    assert ss._norm_name("FC St. Gallen") == "fc st gallen"
    assert ss.name_similarity("Wichita St Shockers", "Wichita State Shockers") == pytest.approx(0.5)


# ── MISATTACHED: the club by ESPN's id ───────────────────────────────────────


def _app_state(home_fk_espn, official_home_id):
    """Production NCAAF event 15340425, team 17165, ESPN team 2026."""
    truth = [_truth("App State Mountaineers", "Georgia State Panthers", key="401869927",
                    home_id=official_home_id, away_id="2247")]
    ours = [_ours(15340425, "Appalachian State Mountaineers", "Georgia State Panthers",
                  espn_id="401869927", home_fk_espn=home_fk_espn, away_fk_espn="2247")]
    return _run(NCAAF, truth, ours)


def test_agreeing_espn_ids_clear_a_spelling_the_bar_cannot_read():
    assert "schedule_misattached" not in _checks(_app_state("2026", "2026")["real"])


@pytest.mark.parametrize("ours_id, espn_id", [(None, "2026"), ("2026", None), (None, None)])
def test_without_an_id_on_both_sides_the_name_test_stands(ours_id, espn_id):
    assert "schedule_misattached" in _checks(_app_state(ours_id, espn_id)["real"])


def test_disagreeing_ids_with_disagreeing_names_still_file():
    truth = [_truth("Wichita State Shockers", "Morehead State Eagles", key="401",
                    home_id="2724", away_id="2413")]
    ours = [_ours(15343833, "Wichita State Shockers", "Morehead State Eagles", espn_id="401",
                  home_fk="Tulsa Golden Hurricane", home_fk_espn="202", away_fk_espn="2413")]
    real = _run(NCAAB, truth, ours)["real"]
    assert [f["fk_name"] for f in real if f["check"] == "schedule_misattached"] == [
        "Tulsa Golden Hurricane"
    ]


def test_disagreeing_ids_never_add_a_finding_the_names_did_not():
    truth = [_truth("Wichita State Shockers", "Morehead State Eagles", key="401",
                    home_id="2724", away_id="2413")]
    ours = [_ours(15343833, "Wichita State Shockers", "Morehead State Eagles", espn_id="401",
                  home_fk_espn="9999", away_fk_espn="2413")]
    assert "schedule_misattached" not in _checks(_run(NCAAB, truth, ours)["real"])


def test_wichita_st_with_no_ids_is_cleared_by_the_college_rule():
    """Production NCAAB event 15343833 as the 08:09Z run saw it, without ids."""
    truth = [_truth("Wichita State Shockers", "Morehead State Eagles", key="401")]
    ours = [_ours(15343833, "Wichita St Shockers", "Morehead St Eagles", espn_id="401")]
    assert "schedule_misattached" not in _checks(_run(NCAAB, truth, ours)["real"])


# ── reversals: a neutral site is a designation; a wrong score is not ─────────


def _colorado_v_san_diego_state(neutral):
    """Production NCAAB event 15343426 (Pechanga Arena, neutral per ESPN).

    We serve Colorado 77 @ San Diego St 66; ESPN's final is San Diego State 77 @
    Colorado 66. Our row has no ESPN id, so it pairs on names, reversed."""
    truth = [_truth("Colorado Buffaloes", "San Diego State Aztecs", key="401909760",
                    hs=66, aws=77, neutral=neutral)]
    ours = [_ours(15343426, "San Diego St Aztecs", "Colorado Buffaloes", hs=66, aws=77)]
    return _run(NCAAB, truth, ours)


def test_a_neutral_site_reversal_is_explained_and_its_wrong_score_still_files():
    classified = _colorado_v_san_diego_state(neutral=True)
    assert "schedule_home_away_swapped" in _checks(classified["explained"])
    assert "schedule_home_away_swapped" not in _checks(classified["real"])
    assert "schedule_score_disagreement" in _checks(classified["real"])


def test_a_reversal_at_a_home_venue_still_files():
    assert "schedule_home_away_swapped" in _checks(
        _colorado_v_san_diego_state(neutral=False)["real"]
    )


def test_a_neutral_site_reversal_with_the_right_scores_files_nothing():
    truth = [_truth("Colorado Buffaloes", "San Diego State Aztecs", key="401909760",
                    hs=66, aws=77, neutral=True)]
    ours = [_ours(15343426, "San Diego St Aztecs", "Colorado Buffaloes", hs=77, aws=66)]
    assert _run(NCAAB, truth, ours)["real"] == []


# ── the specimen class: a game only the full board lists ─────────────────────


def test_a_game_whose_only_difference_is_st_pairs_instead_of_filing_extra():
    """Production NCAAB event 15343448: we store Sacramento St Hornets 77 @ Santa
    Clara Broncos 83; ESPN 401917519 is Sacramento State Hornets 77 @ Santa Clara
    Broncos 83. No ESPN id on our row, so it pairs on names or not at all."""
    full = [_truth("Santa Clara Broncos", "Sacramento State Hornets", key="401917519",
                   hs=83, aws=77)]
    ours = [_ours(15343448, "Santa Clara Broncos", "Sacramento St Hornets", hs=83, aws=77)]
    assert _run(NCAAB, full, ours)["real"] == []


def test_a_game_the_featured_board_omits_files_as_extra_and_the_full_board_pairs_it():
    """Production NCAAB event 15343518, North Dakota @ Winthrop, 93-90."""
    ours = [_ours(15343518, "Winthrop Eagles", "North Dakota Fighting Hawks", hs=93, aws=90)]
    featured = _run(NCAAB, [], ours)["real"]
    assert _checks(featured) == ["schedule_extra"]
    full = [_truth("Winthrop Eagles", "North Dakota Fighting Hawks", key="401923000",
                   hs=93, aws=90)]
    assert _run(NCAAB, full, ours)["real"] == []
