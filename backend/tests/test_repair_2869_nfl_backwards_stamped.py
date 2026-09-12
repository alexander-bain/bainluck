"""#2869: what may a repair rewrite an event row on the strength of?

The script itself is two SQL statements. Everything that decides whether a
production row gets its kickoff moved lives in `judge()`, so that is what is
tested here: the table of reasons ESPN's answer is allowed to REFUSE a row.

The failure this guards against is not "the repair does not run". It is the
repair running on a row it should have left alone — a confident write that
points an event at a different game. That is why every assertion below is a
refusal, with exactly one accept to prove the gate is not simply closed.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "repair_2869_nfl_backwards_stamped_fixtures.py"


def _load():
    spec = importlib.util.spec_from_file_location("repair_2869", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


repair = _load()


#: The row as production holds it — Chiefs/Chargers, stamped into August.
ROW = {
    "id": 14781719,
    "home_team_name": "Kansas City Chiefs",
    "away_team_name": "Los Angeles Chargers",
}


def _payload(
    *,
    season_type=2,
    state="STATUS_SCHEDULED",
    home="Kansas City Chiefs",
    away="Los Angeles Chargers",
    home_score=None,
    away_score=None,
    date="2026-10-18T20:25Z",
):
    comp = {
        "status": {"type": {"name": state}},
        "competitors": [
            {"homeAway": "home", "team": {"displayName": home}, "score": home_score},
            {"homeAway": "away", "team": {"displayName": away}, "score": away_score},
        ],
    }
    if date is not None:
        comp["date"] = date
    return {"header": {"season": {"type": season_type}, "competitions": [comp]}}


def test_it_confirms_the_specimen_that_started_the_issue():
    """The one accept. Without it every refusal below is satisfied by a gate
    that is simply shut, which is the classic vacuous guard."""
    v = repair.judge(ROW, _payload())
    assert v.ok, v.reason
    assert v.new_commence == "2026-10-18T20:25Z"
    assert v.event_id == ROW["id"]


def test_a_preseason_id_is_refused():
    """The hypothesis that had to be killed before this repair was safe.

    Mid-August IS NFL preseason, so "a game dated 2026-08-15 that says it
    finished" has an innocent reading: a real preseason game. If the espn_id
    resolved to a preseason fixture, swapping in a regular-season date would
    destroy a legitimate finished row. ESPN's `season.type` is what separates
    the two, and it is checked before anything else is believed.
    """
    v = repair.judge(ROW, _payload(season_type=1))
    assert not v.ok
    assert "not regular" in v.reason
    assert v.new_commence is None


def test_a_game_espn_says_was_played_is_refused():
    """If ESPN says it finished, our `closed` was RIGHT and the missing scores
    are the defect. That is a different repair; this one must not touch it."""
    v = repair.judge(ROW, _payload(state="STATUS_FINAL"))
    assert not v.ok
    assert "not unplayed" in v.reason


def test_a_scheduled_game_carrying_a_score_is_refused():
    """Two ESPN fields disagreeing about whether the game happened. The repair
    takes the pessimistic reading rather than picking the convenient one."""
    v = repair.judge(ROW, _payload(home_score="24", away_score="17"))
    assert not v.ok
    assert "carries a score" in v.reason


@pytest.mark.parametrize(
    "kwargs, side",
    [
        ({"home": "Denver Broncos"}, "home"),
        ({"away": "Denver Broncos"}, "away"),
    ],
)
def test_an_id_resolving_to_another_game_is_refused(kwargs, side):
    """THE ONE THAT IS NOT CEREMONY.

    An id from the wrong provider — or a stale one — resolves to a DIFFERENT
    entity and returns HTTP 200, not an error. Nothing upstream raises. Without
    this check the repair would move a row's kickoff to a game involving teams
    it does not name, and it would do so confidently.
    """
    v = repair.judge(ROW, _payload(**kwargs))
    assert not v.ok
    assert f"{side} team disagrees" in v.reason


def test_team_matching_survives_case_and_spacing_but_not_abbreviation():
    """The name check must refuse another GAME, not another SPELLING — but the
    tolerance is deliberately narrow.

    Case and whitespace are noise and are absorbed. An ABBREVIATION is not:
    `_norm` refuses `"L.A. Chargers"` against `"Los Angeles Chargers"`, and
    that is the correct trade. ESPN's `displayName` is consistently the full
    name (verified on both specimen ids), so nothing real is refused; widening
    the matcher to accept abbreviations would buy no live row and would spend
    the precision that makes `test_an_id_resolving_to_another_game_is_refused`
    mean anything. If ESPN ever does start abbreviating, this test is where it
    surfaces — as a refusal, which is the safe direction.
    """
    assert repair.judge(ROW, _payload(home="kansas city  chiefs")).ok

    v = repair.judge(ROW, _payload(away="L.A. Chargers"))
    assert not v.ok
    assert "away team disagrees" in v.reason


def test_an_absent_payload_is_refused_not_crashed():
    """ESPN being unreachable must read as "no verdict", never as consent. A
    `None` here is the sandbox-egress case and the outage case at once."""
    v = repair.judge(ROW, None)
    assert not v.ok
    assert "nothing" in v.reason


@pytest.mark.parametrize(
    "payload, fragment",
    [
        ({"header": {"season": {"type": 2}, "competitions": []}}, "no competition"),
        # `{}` is falsy, so it lands on the same arm as an unreachable ESPN.
        # Both mean "no verdict", which is the reading that refuses.
        ({}, "nothing"),
        ({"header": {}}, "not regular"),
    ],
)
def test_a_malformed_payload_is_refused_not_crashed(payload, fragment):
    """A shape the API is not documented to return must not raise out of the
    loop — one bad row may never wipe the pass for the healthy ones."""
    v = repair.judge(ROW, payload)
    assert not v.ok
    assert fragment in v.reason


def test_a_confirmed_game_with_no_date_is_refused():
    """Everything else agrees and the one field the repair WRITES is missing.
    Without this the update would set `commence_time = NULL` on a real row."""
    v = repair.judge(ROW, _payload(date=None))
    assert not v.ok
    assert "no date" in v.reason


def test_the_cohort_asks_for_self_refuting_rows_only():
    """The signature is the whole safety argument for scanning rather than
    naming two ids, so it is pinned: NFL by KEY, closed, and BOTH scores NULL.

    A cohort that dropped the score clause would sweep every legitimately
    closed game — including `15292757` (Titans/Bears, a real 15-24 preseason
    result), which is the row that proves the signature discriminates.
    """
    sql = " ".join(repair.SCAN_SQL.split()).lower()
    assert "s.key = 'americanfootball_nfl'" in sql
    assert "e.status = 'closed'" in sql
    assert "e.home_score is null" in sql
    assert "e.away_score is null" in sql
    assert "e.espn_id is not null" in sql


def test_the_write_clears_completed_at_and_the_box_score():
    """Gotcha #46: `completed_at >= commence_time` is an invariant whose breach
    is a matching-layer P1. Moving `commence_time` to October while leaving a
    `completed_at` in August would CREATE that violation — the repair would
    file its own P1. This is the assertion that keeps the two-field fix from
    being a three-field bug.
    """
    body = SCRIPT.read_text()
    update = body[body.index("UPDATE events SET commence_time") :][:260]
    assert "status = 'scheduled'" in update
    assert "completed_at = NULL" in update
    assert "box_score_data = NULL" in update
    # 267 of 268 healthy scheduled fixtures carry it; clearing would move the
    # row further from the norm, not closer.
    assert "win_probability_sources" not in update


def test_the_undo_is_attributable_and_not_just_a_row_copy():
    """A full-row backup records what a row WAS; it cannot record that THIS
    script moved it, so a restore could not tell a row this repair wrote from
    one a poller has legitimately re-timed since. The manifest is what makes
    the D51 undo attributable rather than a blind overwrite.
    """
    body = SCRIPT.read_text()
    assert repair.BAK_TABLE == "bak_2869_events"
    assert repair.MANIFEST_TABLE == "bak_2869_repair_manifest"
    assert f"SELECT event_id FROM {{MANIFEST_TABLE}}" in body
    # `LIKE events` copies columns and types but NOT foreign keys; a backup
    # that cascaded with its source would be no backup at all.
    #
    # Asserted against the f-string TEMPLATE rather than the resolved name,
    # because that is what the file holds. This one is a source scan and is
    # weaker than the behavioural tests above — it proves the statement is
    # written, not that it ran. The statements themselves need a live
    # Postgres, which is what the `--backup` step is for.
    assert "CREATE TABLE IF NOT EXISTS {BAK_TABLE} (LIKE events)" in body
