"""Guard tests for the daily slate (UX-P132, charter layer 2).

Anchored to what the 2026-08-25 measurement actually found, not to hypotheticals:

* **The sides mapping is the whole feature.** Match-market outcomes are named
  ``Yes`` and ``No`` in our database, and nothing in our schema records which
  player ``Yes`` means. Rendering them directly gives a slate of "Yes 54% /
  No 47%". The register's ``sides`` map is what makes it print players.
* **Independent binaries.** All 162 US Open qualification pairs summed to
  exactly 1.000 at the measured moment — but the Day-1 census's Cincinnati
  sample summed to 1.01, so coherence is checked every time rather than assumed
  (gotcha #23).
* **Stale-open at scale.** 95 of 162 matches were already played while every row
  read ``status='open'`` with a resolution_date inside US Open week (gotcha #33),
  and our ``resolution_date`` is a close time, not a start (gotcha #14).
* **The boards are dark and the slate is live** — the inverse of the ship plan's
  assumption (#2199).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.utils.tournament_register import SCHEMA_VERSION, load_register
from app.utils.tournament_slate import (
    MATCH_STALE_AFTER_HOURS,
    MAX_PAIR_DEVIATION,
    build_bracket,
    build_props,
    build_slate,
    normalize_pair,
)

NOW = datetime(2026, 8, 25, 21, 30, tzinfo=timezone.utc)
SOON = (NOW + timedelta(hours=2)).isoformat()


def _register(**overrides):
    register = {
        "schema_version": SCHEMA_VERSION,
        "tournament": "us-open",
        "season": "2026",
        "version": 2,
        "generated_at": NOW.isoformat(),
        "draw_released": False,
        "players": [
            {
                "entity_key": "clara-burel", "display_name": "Clara Burel",
                "draw": "womens-singles", "role": "participant",
                "seed": None, "country": None, "draw_slot": None, "section": None,
                "sources": [],
            },
            {
                "entity_key": "yexin-ma", "display_name": "Yexin Ma",
                "draw": "womens-singles", "role": "participant",
                "seed": None, "country": None, "draw_slot": None, "section": None,
                "sources": [],
            },
        ],
        "matchups": [_matchup()],
    }
    register.update(overrides)
    return register


def _matchup(**overrides):
    matchup = {
        "matchup_key": "womens-singles:clara-burel-vs-yexin-ma:2026-08-25",
        "draw": "womens-singles",
        "round": "qualifying",
        "scheduled_date": SOON,
        "players": ["clara-burel", "yexin-ma"],
        "sources": [{
            "source": "polymarket",
            "kind": "match",
            "market_id": 59481742,
            "outcome_id": 900001,
            "status": "live",
            "terminal_result": None,
            "evidence": {"kind": "match-market-census", "observed_at": NOW.isoformat()},
            "sides": {
                "clara-burel": {"outcome_id": 900001, "source_label": "Clara Burel"},
                "yexin-ma": {"outcome_id": 900002, "source_label": "Yexin Ma"},
            },
        }],
    }
    matchup.update(overrides)
    return matchup


def _prices(a_now=0.72, b_now=0.28, a_open=0.65, b_open=0.35, observed=None):
    at = observed if observed is not None else NOW - timedelta(minutes=10)
    return {
        900001: {"probability": a_now, "opening_probability": a_open, "observed_at": at},
        900002: {"probability": b_now, "opening_probability": b_open, "observed_at": at},
    }


# ---------------------------------------------------------------------------
# The sides mapping — the slate prints players, never Yes/No
# ---------------------------------------------------------------------------

def test_slate_prints_player_names_not_yes_no():
    """The measured failure this exists to prevent: 'Yes 54% / No 47%'."""
    slate = build_slate(_register(), prices=_prices(), now=NOW)
    assert slate["count"] == 1
    names = [side["display_name"] for side in slate["matches"][0]["sides"]]
    assert names == ["Clara Burel", "Yexin Ma"]
    assert "Yes" not in names and "No" not in names


def test_each_side_takes_its_own_mapped_outcome():
    """Both sides reading one outcome would be a 50/50 that means nothing."""
    slate = build_slate(_register(), prices=_prices(), now=NOW)
    sides = slate["matches"][0]["sides"]
    assert sides[0]["probability"] == pytest.approx(0.72)
    assert sides[1]["probability"] == pytest.approx(0.28)


def test_an_unmapped_side_yields_no_row_rather_than_a_guess():
    matchup = _matchup()
    del matchup["sources"][0]["sides"]["yexin-ma"]
    slate = build_slate(_register(matchups=[matchup]), prices=_prices(), now=NOW)
    assert slate["count"] == 0
    assert slate["dropped"] == {"SIDES_UNMAPPED": 1}


def test_a_side_naming_an_unregistered_player_yields_no_row():
    matchup = _matchup(players=["clara-burel", "ghost-player"])
    matchup["sources"][0]["sides"] = {
        "clara-burel": {"outcome_id": 900001},
        "ghost-player": {"outcome_id": 900002},
    }
    slate = build_slate(_register(matchups=[matchup]), prices=_prices(), now=NOW)
    assert slate["count"] == 0
    assert slate["dropped"] == {"PLAYER_NOT_REGISTERED": 1}


# ---------------------------------------------------------------------------
# Independent binaries — gotcha #23
# ---------------------------------------------------------------------------

def test_a_complementary_pair_passes_through_unchanged():
    """The measured case: all 162 US Open pairs summed to exactly 1.000."""
    a, b, total, coherent = normalize_pair(0.72, 0.28)
    assert (a, b, total, coherent) == (0.72, 0.28, 1.0, True)


def test_a_one_point_overround_is_normalized():
    """The census's Cincinnati specimen: Yes=0.54 / No=0.47 sums to 1.01."""
    a, b, total, coherent = normalize_pair(0.54, 0.47)
    assert coherent is True
    assert total == pytest.approx(1.01)
    assert a + b == pytest.approx(1.0)
    assert a == pytest.approx(0.54 / 1.01)


def test_a_wildly_incoherent_pair_is_refused_not_normalized():
    """0.90 + 0.60 renormalized is a tidy 60/40 with no referent at all."""
    a, b, total, coherent = normalize_pair(0.90, 0.60)
    assert coherent is False
    assert a is None and b is None
    assert total == pytest.approx(1.5)


def test_the_deviation_bound_is_the_thing_being_tested():
    """A guard that passes for every input is not a guard."""
    assert normalize_pair(0.5, 0.5 + MAX_PAIR_DEVIATION - 0.01)[3] is True
    assert normalize_pair(0.5, 0.5 + MAX_PAIR_DEVIATION + 0.01)[3] is False


@pytest.mark.parametrize("a,b", [(None, 0.5), (0.5, None), (0.0, 0.0), (-0.1, 1.1)])
def test_unusable_pairs_are_refused(a, b):
    assert normalize_pair(a, b)[3] is False


def test_an_incoherent_row_still_appears_but_carries_no_probability():
    """The match is still on — that is useful. The split is not trustworthy."""
    slate = build_slate(
        _register(), prices=_prices(a_now=0.90, b_now=0.60), now=NOW
    )
    row = slate["matches"][0]
    assert row["coherent"] is False
    assert row["probability_is_live"] is False
    assert all(side["probability"] is None for side in row["sides"])
    assert row["raw_sum"] == pytest.approx(1.5)
    assert row["favourite"] is None
    assert slate["incoherent"] == 1


# ---------------------------------------------------------------------------
# The script vs the divergence
# ---------------------------------------------------------------------------

def test_the_move_is_the_difference_between_the_row_own_two_numbers():
    """Computing the delta on a different basis than the display is the bug."""
    slate = build_slate(_register(), prices=_prices(), now=NOW)
    for side in slate["matches"][0]["sides"]:
        assert side["move"] == pytest.approx(
            side["probability"] - side["opening_probability"], abs=1e-9
        )


def test_the_script_is_normalized_on_its_own_sum():
    """An opening pair has its own overround; mixing bases fakes a move."""
    slate = build_slate(
        _register(),
        prices=_prices(a_now=0.50, b_now=0.50, a_open=0.55, b_open=0.55),
        now=NOW,
    )
    row = slate["matches"][0]
    assert row["opening_raw_sum"] == pytest.approx(1.10)
    # Both sides opened level and are level now: the move is zero, not -5pp.
    assert all(side["move"] == pytest.approx(0.0) for side in row["sides"])
    assert row["has_moved"] is False


def test_a_real_move_is_reported_as_moved():
    slate = build_slate(_register(), prices=_prices(), now=NOW)
    row = slate["matches"][0]
    assert row["has_moved"] is True
    assert row["favourite"] == "clara-burel"


def test_no_opening_price_means_no_move_rather_than_a_move_from_zero():
    slate = build_slate(
        _register(), prices=_prices(a_open=None, b_open=None), now=NOW
    )
    row = slate["matches"][0]
    assert all(side["move"] is None for side in row["sides"])
    assert all(side["opening_probability"] is None for side in row["sides"])
    # The current split is still trustworthy and still shown.
    assert row["coherent"] is True
    assert row["sides"][0]["probability"] == pytest.approx(0.72)


# ---------------------------------------------------------------------------
# Freshness and the stale-open class
# ---------------------------------------------------------------------------

def test_a_match_already_played_is_dropped_at_serve_time():
    """The register is a committed file; the clock is not."""
    played = (NOW - timedelta(hours=MATCH_STALE_AFTER_HOURS + 1)).isoformat()
    slate = build_slate(
        _register(matchups=[_matchup(scheduled_date=played)]),
        prices=_prices(),
        now=NOW,
    )
    assert slate["count"] == 0
    assert slate["dropped"] == {"ALREADY_PLAYED": 1}


def test_a_match_inside_the_grace_window_is_still_shown():
    """A live five-setter must not vanish mid-match."""
    started = (NOW - timedelta(hours=MATCH_STALE_AFTER_HOURS - 1)).isoformat()
    slate = build_slate(
        _register(matchups=[_matchup(scheduled_date=started)]),
        prices=_prices(),
        now=NOW,
    )
    assert slate["count"] == 1


def test_a_match_with_no_start_time_is_dropped():
    """No anchor is not 'starts soon' (gotcha #53)."""
    slate = build_slate(
        _register(matchups=[_matchup(scheduled_date="")]), prices=_prices(), now=NOW
    )
    assert slate["dropped"] == {"NO_SCHEDULED_START": 1}


def test_a_stale_price_is_never_presented_as_live():
    old = NOW - timedelta(hours=30)
    slate = build_slate(_register(), prices=_prices(observed=old), now=NOW)
    row = slate["matches"][0]
    assert row["price_state"] == "stale"
    assert row["probability_is_live"] is False
    # The number is KEPT — throwing away real information is its own failure.
    assert row["sides"][0]["probability"] == pytest.approx(0.72)


def test_a_never_observed_price_reads_dark_not_fresh():
    prices = _prices()
    for value in prices.values():
        value["observed_at"] = None
    slate = build_slate(_register(), prices=prices, now=NOW)
    assert slate["matches"][0]["price_state"] == "dark"
    assert slate["matches"][0]["probability_is_live"] is False


def test_a_fresh_price_is_presented_as_live():
    """The positive direction: the slate is the half of this page that works."""
    slate = build_slate(_register(), prices=_prices(), now=NOW)
    row = slate["matches"][0]
    assert row["price_state"] == "live"
    assert row["probability_is_live"] is True


def test_every_drop_is_named_and_counted():
    """A short slate must always have an answer; silent truncation reads as absence."""
    played = (NOW - timedelta(days=1)).isoformat()
    slate = build_slate(
        _register(matchups=[_matchup(), _matchup(
            matchup_key="other", scheduled_date=played
        )]),
        prices=_prices(),
        now=NOW,
    )
    assert slate["count"] == 1
    assert sum(slate["dropped"].values()) == 1
    assert slate["dropped"]["ALREADY_PLAYED"] == 1


def test_an_empty_slate_is_an_honest_shape_not_an_error():
    slate = build_slate(_register(matchups=[]), prices={}, now=NOW)
    assert slate == {
        "matches": [], "count": 0, "incoherent": 0, "dropped": {},
        "price_state": "dark", "newest_observed_at": None, "age_hours": None,
        "dark_after_hours": 48.0,
    }


def test_rows_are_ordered_by_scheduled_time():
    later = _matchup(
        matchup_key="later", scheduled_date=(NOW + timedelta(hours=5)).isoformat()
    )
    later["sources"][0]["sides"] = {
        "clara-burel": {"outcome_id": 900001},
        "yexin-ma": {"outcome_id": 900002},
    }
    slate = build_slate(
        _register(matchups=[later, _matchup()]), prices=_prices(), now=NOW
    )
    assert [r["matchup_key"] for r in slate["matches"]] == [
        "womens-singles:clara-burel-vs-yexin-ma:2026-08-25", "later"
    ]


# ---------------------------------------------------------------------------
# The committed register, served
# ---------------------------------------------------------------------------

def test_the_committed_register_produces_a_real_slate():
    """End to end on the shipped file: the second population pass paid off."""
    register = load_register("us-open", "2026")
    assert register is not None
    generated = datetime.fromisoformat(register["generated_at"].replace("Z", "+00:00"))

    outcome_ids = {
        side["outcome_id"]
        for matchup in register["matchups"]
        for block in matchup["sources"]
        for side in block["sides"].values()
    }
    prices = {
        oid: {"probability": 0.5, "opening_probability": 0.5, "observed_at": generated}
        for oid in outcome_ids
    }
    slate = build_slate(register, prices=prices, now=generated)

    assert slate["count"] == len(register["matchups"]) > 0
    assert slate["dropped"] == {}
    assert slate["incoherent"] == 0
    for row in slate["matches"]:
        assert len(row["sides"]) == 2
        for side in row["sides"]:
            assert side["display_name"] not in {"Yes", "No", ""}


# ---------------------------------------------------------------------------
# Curated props & futures (UX-P132 re-skin, Alex's item 5)
# ---------------------------------------------------------------------------

def _prop(**overrides):
    prop = {
        "key": "calendar-slam",
        "title": "Can Sinner complete the calendar slam?",
        "hook": "He has three of the four.",
        "draw": None,
        "source": "kalshi",
        "outcomes": [
            {"entity_key": "yes", "display_name": "Jannik Sinner", "outcome_id": 700001},
            {"entity_key": "no", "display_name": "Nobody", "outcome_id": 700002},
        ],
    }
    prop.update(overrides)
    return prop


def test_build_props_reads_only_the_register():
    """Curated, not a dump — there is no path that surfaces an unregistered market."""
    register = _register(props=[_prop()])
    prices = {
        700001: {"probability": 0.22, "observed_at": NOW - timedelta(minutes=5)},
        700002: {"probability": 0.78, "observed_at": NOW - timedelta(minutes=5)},
        # A market the register does not curate. It must not appear.
        999999: {"probability": 0.5, "observed_at": NOW},
    }
    props = build_props(register, prices=prices, now=NOW)
    assert len(props) == 1
    assert props[0]["key"] == "calendar-slam"
    assert [o["entity_key"] for o in props[0]["outcomes"]] == ["yes", "no"]


def test_a_prop_with_no_prices_still_renders_without_inventing_one():
    props = build_props(_register(props=[_prop()]), prices={}, now=NOW)
    assert len(props) == 1
    assert props[0]["price_state"] == "dark"
    assert all(o["probability"] is None for o in props[0]["outcomes"])
    assert all(o["probability_is_live"] is False for o in props[0]["outcomes"])


def test_a_stale_prop_is_never_presented_as_live():
    prices = {700001: {"probability": 0.22, "observed_at": NOW - timedelta(hours=30)}}
    props = build_props(_register(props=[_prop()]), prices=prices, now=NOW)
    assert props[0]["price_state"] == "stale"
    assert props[0]["outcomes"][0]["probability"] == pytest.approx(0.22)
    assert props[0]["outcomes"][0]["probability_is_live"] is False


def test_a_register_with_no_props_yields_an_empty_section():
    assert build_props(_register(), prices={}, now=NOW) == []


def test_a_prop_reusing_one_outcome_twice_is_rejected():
    """One quote rendered as two outcomes of the same question."""
    from app.utils.tournament_register import us_open_2026_contract, validate_register

    bad = _prop(outcomes=[
        {"entity_key": "yes", "display_name": "A", "outcome_id": 700001},
        {"entity_key": "no", "display_name": "B", "outcome_id": 700001},
    ])
    findings = validate_register(_register(props=[bad]), us_open_2026_contract())
    assert "PROP_OUTCOME_REUSED" in findings


def test_a_prop_outcome_without_an_identity_is_rejected():
    from app.utils.tournament_register import us_open_2026_contract, validate_register

    bad = _prop(outcomes=[{"entity_key": "yes", "display_name": "A"}])
    findings = validate_register(_register(props=[bad]), us_open_2026_contract())
    assert "PROP_OUTCOME_MISSING_IDENTITY" in findings


def test_two_props_sharing_a_key_are_rejected():
    from app.utils.tournament_register import us_open_2026_contract, validate_register

    findings = validate_register(_register(props=[_prop(), _prop()]), us_open_2026_contract())
    assert "DUPLICATE_PROP_KEY" in findings


# ---------------------------------------------------------------------------
# Where to watch (Alex's item 4)
# ---------------------------------------------------------------------------

def test_broadcasts_validate_and_are_optional():
    from app.utils.tournament_register import validate_broadcasts

    assert validate_broadcasts(None) == []
    assert validate_broadcasts([{"region": "US", "channels": ["ESPN"]}]) == []


def test_a_broadcast_with_no_channels_is_rejected():
    """"Where to watch: " with nothing after it is worse than no section."""
    from app.utils.tournament_register import validate_broadcasts

    assert validate_broadcasts([{"region": "US", "channels": []}]) == ["BROADCAST_NO_CHANNELS"]
    assert validate_broadcasts([{"region": "US", "channels": ["  "]}]) == ["BROADCAST_NO_CHANNELS"]


def test_the_committed_register_answers_where_to_watch():
    from app.utils.tournament_register import TournamentRegister, load_register

    view = TournamentRegister(load_register("us-open", "2026") or {})
    regions = {entry["region"] for entry in view.broadcasts}
    assert "US" in regions
    us = next(e for e in view.broadcasts if e["region"] == "US")
    assert "ESPN" in us["channels"]


# ---------------------------------------------------------------------------
# The curation bar (scripts/populate_tournament_props.py)
# ---------------------------------------------------------------------------

def _run_props_script(tmp_path, dump_rows):
    import json as _json
    import subprocess
    import sys as _sys
    from pathlib import Path as _Path

    root = _Path(__file__).resolve().parents[1]
    dump = {
        "columns": ["market_id", "market_ext", "source", "market_name", "status",
                    "outcome_id", "outcome_name", "current_probability"],
        "rows": dump_rows,
        "truncated": False,
    }
    (tmp_path / "dump.json").write_text(_json.dumps(dump))
    register = _json.loads((root / "data/tournament_registers/us-open-2026.json").read_text())
    (tmp_path / "reg.json").write_text(_json.dumps(register))

    result = subprocess.run(
        [_sys.executable, str(root / "scripts/populate_tournament_props.py"),
         "--register", str(tmp_path / "reg.json"), "--dump", str(tmp_path / "dump.json"),
         "--observed-at", "2026-08-26T00:00:00+00:00",
         "--version", "3", "--supersedes-version", "2",
         "--out", str(tmp_path / "out.json")],
        capture_output=True, text=True, cwd=str(root),
    )
    out = (
        _json.loads((tmp_path / "out.json").read_text())
        if (tmp_path / "out.json").exists() else None
    )
    return result, out


def test_the_curation_bar_excludes_an_uncurated_market(tmp_path):
    """"Curated, not a dump" — a market in the dump but not in CURATION is skipped.

    This is the property that has to survive the tournament growing: the bar is
    an allowlist written by an agent, not a filter over whatever the query
    returned, so a new high-volume dull market cannot arrive on the page.
    """
    result, out = _run_props_script(tmp_path, [
        [111, "KXGRANDSLAM-JSIN26", "kalshi", "Sinner majors", "open", 5001, "2+ Grand Slam wins", "0.18"],
        [999, "KXSOMETHING-DULL", "kalshi", "Dull", "open", 5099, "Yes", "0.50"],
    ])
    assert result.returncode == 0, result.stderr
    assert [p["key"] for p in out["props"]] == ["sinner-second-major"]
    assert "below the bar" in result.stdout


def test_a_curated_prop_absent_from_the_dump_is_reported_not_invented(tmp_path):
    """A market we curated and did not find must be loud, not silently missing."""
    result, _ = _run_props_script(tmp_path, [
        [111, "KXGRANDSLAM-JSIN26", "kalshi", "Sinner majors", "open", 5001, "2+ Grand Slam wins", "0.18"],
    ])
    assert result.returncode == 0
    assert "curated but ABSENT from the dump" in result.stdout
    assert "KXATPCOMPETE-26USOSIN" in result.stdout


def test_the_props_pass_writes_a_register_that_still_validates(tmp_path):
    from app.utils.tournament_register import us_open_2026_contract, validate_register

    result, out = _run_props_script(tmp_path, [
        [111, "KXGRANDSLAM-JSIN26", "kalshi", "Sinner majors", "open", 5001, "2+ Grand Slam wins", "0.18"],
        [111, "KXGRANDSLAM-JSIN26", "kalshi", "Sinner majors", "open", 5002, "3+ Grand Slam wins", "0.02"],
    ])
    assert result.returncode == 0
    assert validate_register(out, us_open_2026_contract()) == []
    # And the second population pass's work is still intact underneath it.
    assert len(out["matchups"]) > 0
    assert out["version"] == 3 and out["supersedes_version"] == 2


# ── The answer rule (UX-P134) ────────────────────────────────────────────────
#
# A prop card prints one number under one question, so something decides WHICH
# outcome that number is. It used to be "the biggest one", and the census that
# populated this section proved how badly that fails on a threshold ladder.


def _prop_register(outcomes):
    return {
        "props": [{
            "key": "sinner-second-major",
            "title": "Can Sinner win a second major this year?",
            "hook": None,
            "draw": "mens-singles",
            "source": "kalshi",
            "outcomes": outcomes,
        }]
    }


def test_the_answer_is_the_curated_outcome_not_the_biggest_number():
    """THE specimen. `1+` at 99% must never answer "can he win a second major".

    The real Kalshi market `KXGRANDSLAM-JSIN26` carries the ladder 1+/2+/3+.
    Picking the max prints 99% under a question whose true answer is 55.5% —
    and on Alcaraz's equivalent ladder, 25%. The number is true of something;
    it is not an answer to the question above it.
    """
    now = datetime(2026, 8, 25, 23, 0, tzinfo=timezone.utc)
    register = _prop_register([
        {"entity_key": "s:1", "display_name": "1+ Grand Slam wins", "outcome_id": 1},
        {"entity_key": "s:2", "display_name": "2+ Grand Slam wins", "outcome_id": 2,
         "is_answer": True},
        {"entity_key": "s:3", "display_name": "3+ Grand Slam wins", "outcome_id": 3},
    ])
    prices = {
        1: {"probability": 0.99, "observed_at": now},
        2: {"probability": 0.555, "observed_at": now},
        3: {"probability": 0.01, "observed_at": now},
    }
    built = build_props(register, prices=prices, now=now)[0]

    assert built["answer_entity_key"] == "s:2"
    answer = next(o for o in built["outcomes"] if o["entity_key"] == built["answer_entity_key"])
    assert answer["probability"] == 0.555
    # The 99% is still carried — it is real information about the market — it
    # just is not the card's answer.
    assert max(o["probability"] for o in built["outcomes"]) == 0.99


def test_a_field_market_names_no_answer_and_gets_none():
    """No single outcome answers "who will win a slam", so nothing leads."""
    now = datetime(2026, 8, 25, 23, 0, tzinfo=timezone.utc)
    register = _prop_register([
        {"entity_key": "f:a", "display_name": "Alcaraz", "outcome_id": 1},
        {"entity_key": "f:b", "display_name": "Sinner", "outcome_id": 2},
    ])
    prices = {
        1: {"probability": 0.4, "observed_at": now},
        2: {"probability": 0.6, "observed_at": now},
    }
    built = build_props(register, prices=prices, now=now)[0]
    assert built["answer_entity_key"] is None
    assert all(o["is_answer"] is False for o in built["outcomes"])


def test_two_outcomes_claiming_the_answer_is_structurally_invalid():
    """The card prints one number; two claimants means the register cannot say
    which, and any renderer tie-break would be arbitrary dressed as authority."""
    from app.utils.tournament_register import STRUCTURAL_FINDINGS, validate_prop

    findings = validate_prop({
        "key": "k", "title": "t", "source": "kalshi",
        "outcomes": [
            {"entity_key": "a", "display_name": "A", "outcome_id": 1, "is_answer": True},
            {"entity_key": "b", "display_name": "B", "outcome_id": 2, "is_answer": True},
        ],
    }, sources={"kalshi"})

    assert "PROP_MULTIPLE_ANSWERS" in findings
    # And it must be classified, not merely emitted — the Day-2 meta-guard's point.
    assert "PROP_MULTIPLE_ANSWERS" in STRUCTURAL_FINDINGS


def test_the_committed_props_each_answer_their_own_question():
    """On the shipped file: every curated prop names exactly one answer."""
    register = load_register("us-open", "2026")
    props = register.get("props") or []
    assert len(props) >= 4, "the props population pass has not run"
    for prop in props:
        answers = [o for o in prop["outcomes"] if o.get("is_answer")]
        assert len(answers) == 1, f"{prop['key']} has {len(answers)} answers"


# ── The draw ingest + fixture swap (UX-P134, item 4) ─────────────────────────
#
# Thursday's ceremony rehearsed on Tuesday. The point is that 08-28 is an
# ingest RUN, not a build day, so every leg of the path is proven here first.


def _synthetic_draw_path():
    from pathlib import Path as _Path
    return _Path(__file__).resolve().parents[1] / "data/tournament_registers/_synthetic-usopen-draw.json"


def _run_ingest(tmp_path, *, allow_unregistered: bool, register=None):
    import json as _json
    import subprocess
    import sys as _sys
    from pathlib import Path as _Path

    root = _Path(__file__).resolve().parents[1]
    reg = register if register is not None else _json.loads(
        (root / "data/tournament_registers/us-open-2026.json").read_text()
    )
    (tmp_path / "reg.json").write_text(_json.dumps(reg))

    cmd = [
        _sys.executable, str(root / "scripts/ingest_tournament_draw.py"),
        "--register", str(tmp_path / "reg.json"),
        "--draw", str(_synthetic_draw_path()),
        "--version", str(reg["version"] + 1),
        "--supersedes-version", str(reg["version"]),
        "--out", str(tmp_path / "out.json"),
    ]
    if allow_unregistered:
        cmd.append("--allow-unregistered")
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(root))
    out = (
        _json.loads((tmp_path / "out.json").read_text())
        if (tmp_path / "out.json").exists() else None
    )
    return result, out


def test_an_unregistered_drawn_player_refuses_the_whole_ingest(tmp_path):
    """A drawn name with no registered identity would render a person the rest
    of the page cannot price or link. It stops the run rather than being
    dropped quietly — a silent omission is the failure a register prevents."""
    result, out = _run_ingest(tmp_path, allow_unregistered=False)
    assert result.returncode == 1
    assert "NOT REGISTERED" in result.stderr
    assert "REFUSING TO WRITE" in result.stderr
    assert out is None, "a refused ingest must write nothing at all"


def test_the_ingest_latches_draw_released_and_writes_slots(tmp_path):
    """The end-to-end rehearsal: ingest -> latch -> clean transition."""
    result, out = _run_ingest(tmp_path, allow_unregistered=True)
    assert result.returncode == 0, result.stderr
    assert out["draw_released"] is True
    slotted = [p for p in out["players"] if p.get("draw_slot") is not None]
    assert len(slotted) > 100
    assert all(1 <= p["draw_slot"] <= 128 for p in slotted)


def test_the_ingest_result_is_a_valid_transition_not_merely_a_valid_file(tmp_path):
    from app.utils.tournament_register import (
        us_open_2026_contract,
        validate_register,
        validate_transition,
    )
    import json as _json
    from pathlib import Path as _Path

    root = _Path(__file__).resolve().parents[1]
    before = _json.loads((root / "data/tournament_registers/us-open-2026.json").read_text())
    _, after = _run_ingest(tmp_path, allow_unregistered=True)

    contract = us_open_2026_contract()
    assert validate_register(after, contract) == []
    assert validate_transition(before, after, contract) == []
    assert after["version"] == before["version"] + 1
    assert after["supersedes_version"] == before["version"]


def test_the_latch_cannot_be_un_latched_by_a_later_ingest(tmp_path):
    """`draw_released` true -> false would make every committed slot
    unvalidated again, silently."""
    from app.utils.tournament_register import us_open_2026_contract, validate_transition

    _, released = _run_ingest(tmp_path, allow_unregistered=True)
    regressed = dict(released)
    regressed["draw_released"] = False
    regressed["version"] = released["version"] + 1
    regressed["supersedes_version"] = released["version"]
    findings = validate_transition(released, regressed, us_open_2026_contract())
    assert "INVALID_DRAW_RELEASED_UNLATCH" in findings


class TestTheFixtureSwap:
    """The bracket must come from the register, so 08-28 is a data change."""

    def test_the_bracket_is_empty_before_the_ceremony(self):
        register = load_register("us-open", "2026")
        assert register["draw_released"] is False
        assert build_bracket(register, prices={}, draw="mens-singles") == []

    def test_the_latch_alone_suppresses_the_bracket_even_with_slots_present(self):
        """The guard above passes trivially — the committed register carries no
        `draw_slot` at all, so it would return `[]` with the latch check
        deleted. This one hands it slots and keeps the latch DOWN, which is the
        only version that fails when the latch stops being consulted.

        Such a register is itself invalid (`INVALID_DRAW_SLOT_BEFORE_RELEASE`),
        and that is the point: if a bad file ever reaches the serving path, the
        page shows no bracket rather than a draw nobody ceremonially made.
        """
        register = load_register("us-open", "2026")
        register["draw_released"] = False
        for index, player in enumerate(register["players"][:8]):
            player["draw_slot"] = index + 1
        assert build_bracket(register, prices={}, draw="mens-singles") == []

    def test_the_bracket_fills_from_the_register_after_release(self, tmp_path):
        _, released = _run_ingest(tmp_path, allow_unregistered=True)
        slots = build_bracket(released, prices={}, draw="mens-singles")

        # Power of two, or the frontend fold refuses it outright.
        assert len(slots) == 128
        assert len(slots) & (len(slots) - 1) == 0
        filled = [s for s in slots if s is not None]
        assert len(filled) > 50
        assert all(s["display_name"] for s in filled)

    def test_an_unfilled_slot_is_none_and_never_an_invented_name(self, tmp_path):
        _, released = _run_ingest(tmp_path, allow_unregistered=True)
        slots = build_bracket(released, prices={}, draw="mens-singles")
        holes = [s for s in slots if s is None]
        assert holes, "the synthetic draw has unregistered slots; they must be holes"

    def test_a_slot_with_no_priced_source_carries_no_probability(self, tmp_path):
        _, released = _run_ingest(tmp_path, allow_unregistered=True)
        slots = build_bracket(released, prices={}, draw="mens-singles")
        assert all(s["probability"] is None for s in slots if s is not None)


def test_a_curated_answer_missing_from_the_market_refuses_the_write(tmp_path):
    """A source renaming an outcome must stop the pass, not silently produce a
    card with a question and no answer — which the renderer would then show as
    a ranked field, quietly turning a curated question into a list."""
    result, out = _run_props_script(tmp_path, [
        [111, "KXGRANDSLAM-JSIN26", "kalshi", "Sinner majors", "open", 5001, "Affirmative", "0.18"],
    ])
    assert result.returncode == 1
    assert "REFUSED" in result.stderr
    assert "is not an outcome of this market" in result.stderr
    assert out is None, "a refused population pass must write nothing"
