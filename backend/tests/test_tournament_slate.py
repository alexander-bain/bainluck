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

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.utils.tournament_register import SCHEMA_VERSION, load_register
from app.utils.tournament_slate import (
    MATCH_STALE_AFTER_HOURS,
    MAX_PAIR_DEVIATION,
    build_bracket,
    build_props,
    build_results,
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


# ---------------------------------------------------------------------------
# THE MIXED-AGE PAIR — `C-USOPEN-DAY3-TIER2` applied to the slate
#
# The board's specimen has a twin here and it is arguably worse: a slate row
# NORMALIZES its two sides against each other, so a stale side does not sit
# beside the published number, it is baked into it. `normalize_pair` refuses
# the loud version (0.90 + 0.60 -> refused) but a mixed-age pair that still
# sums to 1.00 sails through coherence, because coherence is not freshness.
# ---------------------------------------------------------------------------

def _mixed_pair(fresh_hours: float, stale_hours: float):
    prices = _prices()
    prices[900001]["observed_at"] = NOW - timedelta(hours=fresh_hours)
    prices[900002]["observed_at"] = NOW - timedelta(hours=stale_hours)
    return build_slate(_register(), prices=prices, now=NOW)["matches"][0]


def test_a_pair_with_one_stale_side_is_not_live():
    """Both sides are inside the published number, so both must be fresh."""
    row = _mixed_pair(fresh_hours=1.0, stale_hours=20 * 24)
    # The pair is perfectly coherent — 0.72 + 0.28 = 1.000 exactly — which is
    # the point: the existing gate has no reason to fire.
    assert row["coherent"] is True
    assert row["raw_sum"] == pytest.approx(1.0)
    assert row["probability_is_live"] is False
    assert row["price_state"] == "dark"


def test_a_mixed_pair_ages_from_its_older_side_and_still_shows_the_newer():
    row = _mixed_pair(fresh_hours=1.0, stale_hours=20 * 24)
    assert row["age_hours"] == pytest.approx(480.0)
    assert row["freshest_age_hours"] == pytest.approx(1.0)
    assert row["mixed_freshness"] is True
    assert row["stale_sides"] == ["yexin-ma"]
    by_key = {s["entity_key"]: s for s in row["sides"]}
    assert by_key["clara-burel"]["price_state"] == "live"
    assert by_key["yexin-ma"]["price_state"] == "dark"


def test_a_pair_fresh_on_both_sides_is_still_live():
    """The AND must be able to say yes to two different fresh timestamps."""
    row = _mixed_pair(fresh_hours=0.1, stale_hours=1.0)
    assert row["probability_is_live"] is True
    assert row["mixed_freshness"] is False
    assert row["age_hours"] == pytest.approx(1.0)


def test_the_slate_banner_is_still_the_newest_reading():
    """Row-level AND, slate-level newest — the rule did not leak upward."""
    prices = _prices()
    prices[900002]["observed_at"] = NOW - timedelta(hours=20 * 24)
    slate = build_slate(_register(), prices=prices, now=NOW)
    assert slate["price_state"] == "live"
    assert slate["matches"][0]["probability_is_live"] is False


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
        for side in (block.get("sides") or {}).values()
    }
    prices = {
        oid: {"probability": 0.5, "opening_probability": 0.5, "observed_at": generated}
        for oid in outcome_ids
    }
    slate = build_slate(register, prices=prices, now=generated)

    # EVERY registered matchup renders, priced or not (UX-P142). It used to be
    # every matchup because every matchup was priced; the released main draw
    # added 96 that are not, and the count holding is the ship — a fixture is a
    # fact even when nobody has quoted it.
    assert slate["count"] == len(register["matchups"]) > 0
    assert slate["dropped"] == {}

    unpriced = [row for row in slate["matches"] if row["priced"] is False]
    assert len(unpriced) >= 90
    # `incoherent` counts rows with no trustworthy split. Every one of them is
    # an unpriced fixture and none is a disagreement between two quotes — which
    # is the invariant the old `== 0` was standing in for.
    assert slate["incoherent"] == len(unpriced)
    for row in unpriced:
        assert row["price_state"] == "unpriced"
        assert all(side["probability"] is None for side in row["sides"])

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


# ---------------------------------------------------------------------------
# A TIME-BOUNDED QUESTION STOPS BEING A QUESTION (Q465)
#
# Alex, an hour into opening day: "The 'Will Sinner actually play?' prop doesn't
# make sense now that the tourney has started." The card was printing a live
# probability under a question the world had already answered.
#
# The renderer reads exactly three keys and they are named by the UX lane's
# already-built half: `settled` (explicit true), `settled_answer` (a STRING),
# `settled_at`. A near-miss on any of these ships the fix dead, so each is
# asserted by name below.
# ---------------------------------------------------------------------------

def test_a_prop_that_declares_no_settlement_renders_exactly_as_before():
    """THE FAIL-SAFE. Absent field => nothing about the card changes."""
    prices = {700001: {"probability": 0.22, "observed_at": NOW - timedelta(minutes=5)}}
    card = build_props(_register(props=[_prop()]), prices=prices, now=NOW)[0]
    assert card["settled"] is False
    assert card["settled_answer"] is None
    assert card["settled_at"] is None
    # Still a live question in every other respect.
    assert card["price_state"] == "live"
    assert card["outcomes"][0]["probability"] == pytest.approx(0.22)


def test_a_question_answered_before_now_renders_settled_with_its_answer():
    settles = (NOW - timedelta(hours=6)).isoformat()
    card = build_props(
        _register(props=[_prop(settles_at=settles, settled_answer="No")]),
        prices={700001: {"probability": 0.01, "observed_at": NOW}},
        now=NOW,
    )[0]
    assert card["settled"] is True
    assert card["settled_answer"] == "No"
    assert card["settled_at"] == settles
    # The card is STILL RENDERED — settled is a rendering, not a deletion. The
    # last reading travels so the renderer can demote it to a muted line.
    assert card["outcomes"][0]["probability"] == pytest.approx(0.01)


def test_a_question_whose_instant_has_not_arrived_is_still_live():
    """The instant is a boundary, not a flag: before it, nothing changes."""
    card = build_props(
        _register(props=[_prop(
            settles_at=(NOW + timedelta(hours=2)).isoformat(),
            settled_answer="No",
        )]),
        prices={700001: {"probability": 0.4, "observed_at": NOW}},
        now=NOW,
    )[0]
    assert card["settled"] is False
    assert card["settled_answer"] is None


def test_a_settled_question_with_no_answer_is_withheld_not_printed_as_live():
    """The one case where showing nothing beats showing the card.

    We can prove the question is answered and we do not hold the answer.
    Printing it would put a decided question in the live type, which is the
    defect being fixed — so it is withheld, and the caller logs it rather than
    letting a card disappear silently (gotcha #53).
    """
    props = build_props(
        _register(props=[_prop(settles_at=(NOW - timedelta(hours=1)).isoformat())]),
        prices={700001: {"probability": 0.01, "observed_at": NOW}},
        now=NOW,
    )
    assert props == []


def test_an_unparseable_instant_never_settles_a_card_by_accident():
    """A typo must not silently mark a live question answered, in either
    direction. It leaves the card live; the register validator is what refuses
    it (`PROP_SETTLES_AT_NOT_ISO`, structural)."""
    card = build_props(
        _register(props=[_prop(settles_at="the first ball", settled_answer="No")]),
        prices={700001: {"probability": 0.4, "observed_at": NOW}},
        now=NOW,
    )[0]
    assert card["settled"] is False
    assert card["settled_answer"] is None


def test_a_naive_settles_at_is_read_as_utc_and_never_500s_the_route():
    """CERT-527. `is_iso8601` ACCEPTS an offset-less instant, so
    `2026-08-30T15:05:00` passes the register's own gate — and comparing it
    with an aware `now` raises `TypeError`, which is a 500 on the whole
    tournament route from data the validator called valid.

    UTC is the right reading rather than a shrug: every writer in this codebase
    stamps UTC, and `tournament_board._hours_since` already states the same rule.
    """
    from app.utils.tournament_register import is_iso8601
    # Offset STRIPPED from an instant already in the past, so the assertion is
    # about the missing tzinfo and not about the clock (gotcha #44: offset
    # first, then strip — never a literal that drifts past NOW).
    naive = (NOW - timedelta(hours=6)).replace(tzinfo=None).isoformat()
    # The premise: the gate really does let this through.
    assert is_iso8601(naive) is True

    card = build_props(
        _register(props=[_prop(settles_at=naive, settled_answer="No")]),
        prices={}, now=NOW,
    )[0]
    assert card["settled"] is True
    assert card["settled_answer"] == "No"
    # Normalised on the way out, so the client is never handed a bare instant.
    assert card["settled_at"].endswith("+00:00")

    # ...and the boundary still works on a naive stamp in the FUTURE, which is
    # the arm a naive-as-UTC coercion could silently invert.
    future = (NOW + timedelta(hours=3)).replace(tzinfo=None).isoformat()
    later = build_props(
        _register(props=[_prop(settles_at=future, settled_answer="No")]),
        prices={}, now=NOW,
    )[0]
    assert later["settled"] is False


def test_the_committed_register_answers_the_sinner_question():
    """THE SHIP, on the real file (Q465).

    Alex's exact card. Read at any instant after the first ball, it must render
    settled and say "No" — Jannik Sinner is not one of the 128 named men in
    ESPN's Round 1, and the register carries that verdict because the Kalshi
    market still reads `status='open'` (gotcha #33).
    """
    register = json.loads(
        (
            Path(__file__).resolve().parents[1]
            / "data" / "tournament_registers" / "us-open-2026.json"
        ).read_text()
    )
    after = datetime(2026, 8, 30, 20, 0, tzinfo=timezone.utc)
    cards = {c["key"]: c for c in build_props(register, prices={}, now=after)}
    sinner = cards["sinner-competes"]
    assert sinner["settled"] is True
    assert sinner["settled_answer"] == "No"
    assert sinner["settled_at"] == "2026-08-30T15:05:00+00:00"

    # CERT-527: the committed provenance must state a count that can be
    # re-measured. The first version said "128 competitions"; ESPN returns 64
    # competitions carrying 128 named athletes, and both tour payloads repeat
    # the same 64 — so the original number was a double-count across tours, not
    # a reading of the draw. The verdict was right and its evidence was not.
    prop = next(p for p in register["props"] if p["key"] == "sinner-competes")
    measured = prop["evidence"]["settled_evidence"]["measured"]
    assert measured == {
        "r1_competitions": 64,
        "r1_named_athletes": 128,
        "sinner_present": False,
    }

    # ...and BEFORE the first ball the same file renders it as a live question,
    # so the field is a boundary in time and not a permanent relabelling.
    before = datetime(2026, 8, 29, 12, 0, tzinfo=timezone.utc)
    early = {c["key"]: c for c in build_props(register, prices={}, now=before)}
    assert early["sinner-competes"]["settled"] is False

    # The other four curated questions are NOT time-bounded and must be
    # untouched — this fix has a named subject, not a blast radius.
    for key in ("usa-men-final-berth", "second-major", "sabalenka-title-defence",
                "usa-women-quarterfinal-count"):
        assert cards[key]["settled"] is False, key
        assert cards[key]["settled_answer"] is None, key


# ---------------------------------------------------------------------------
# THE MIXED-AGE PROP CARD — the same defect, one surface further out
#
# `build_props` had the failure in its purest form: it computed ONE section
# age from the newest outcome and then wrote that verdict onto every outcome,
# with a comment explaining that a per-outcome flag disagreeing with the
# section banner would be "the page contradicting itself". It would not have
# been a contradiction, it was the truth — the flags now decide the banner
# rather than the other way round.
# ---------------------------------------------------------------------------

def _mixed_prop(fresh_hours: float, stale_hours: float):
    prices = {
        700001: {"probability": 0.22, "observed_at": NOW - timedelta(hours=stale_hours)},
        700002: {"probability": 0.78, "observed_at": NOW - timedelta(hours=fresh_hours)},
    }
    return build_props(_register(props=[_prop()]), prices=prices, now=NOW)[0]


def test_a_fresh_outcome_cannot_make_a_stale_outcome_read_live():
    """The specimen: outcome B refreshed 5 minutes ago, outcome A 20 days old."""
    card = _mixed_prop(fresh_hours=0.08, stale_hours=20 * 24)
    by_key = {o["entity_key"]: o for o in card["outcomes"]}
    assert by_key["no"]["probability_is_live"] is True     # its own reading is fresh
    assert by_key["yes"]["probability_is_live"] is False   # ...and it cannot lend that
    assert by_key["yes"]["age_hours"] == pytest.approx(480.0)


def test_a_mixed_prop_card_reads_from_its_oldest_priced_outcome():
    """A ranked field is a published artifact: a stale member can outrank fresh ones."""
    card = _mixed_prop(fresh_hours=0.08, stale_hours=20 * 24)
    assert card["price_state"] == "dark"
    assert card["age_hours"] == pytest.approx(480.0)
    assert card["freshest_age_hours"] == pytest.approx(0.08)
    assert card["mixed_freshness"] is True
    assert card["stale_outcomes"] == ["yes"]


def test_a_prop_card_fresh_throughout_is_live():
    card = _mixed_prop(fresh_hours=0.08, stale_hours=1.0)
    assert card["price_state"] == "live"
    assert card["mixed_freshness"] is False
    assert all(o["probability_is_live"] is True for o in card["outcomes"])


def test_an_unpriced_outcome_does_not_darken_a_fresh_card():
    """The other direction. An outcome with no reading has no reading to be
    stale — counting its absence as dark would paint every partially quoted
    card dark and retire the signal."""
    prices = {700001: {"probability": 0.22, "observed_at": NOW - timedelta(minutes=5)}}
    card = build_props(_register(props=[_prop()]), prices=prices, now=NOW)[0]
    assert card["price_state"] == "live"
    assert card["mixed_freshness"] is False
    by_key = {o["entity_key"]: o for o in card["outcomes"]}
    assert by_key["yes"]["probability_is_live"] is True
    assert by_key["no"]["probability"] is None
    assert by_key["no"]["probability_is_live"] is False


# ---------------------------------------------------------------------------
# THE COMPARISON CARD — CERT-430, finding 1
#
# The card above is one market with several outcomes; this one is several
# MARKETS printed side by side as one question, which the register declares in
# `markets`. The difference matters exactly once, and it is the finding: an
# unpriced outcome of a field is a field row nobody has quoted, while an
# unpriced LEG of a comparison is half the comparison missing.
#
# The executed specimen: Alcaraz unpriced, Sinner fresh at .555, and the card
# came back `live` because only priced outcomes voted. One man's number, in the
# confident type, under a two-man question.
# ---------------------------------------------------------------------------

def _comparison_prop():
    return _prop(
        key="second-major",
        title="Who wins a second major this year?",
        markets=[
            {"market_id": 53796, "market_external_id": "KXGRANDSLAM-CALC26"},
            {"market_id": 53795, "market_external_id": "KXGRANDSLAM-JSIN26"},
        ],
        outcomes=[
            {
                "entity_key": "second-major:carlos-alcaraz",
                "display_name": "Carlos Alcaraz",
                "outcome_id": 848773,
                "market_external_id": "KXGRANDSLAM-CALC26",
            },
            {
                "entity_key": "second-major:jannik-sinner",
                "display_name": "Jannik Sinner",
                "outcome_id": 848769,
                "market_external_id": "KXGRANDSLAM-JSIN26",
            },
        ],
    )


def test_a_comparison_card_reports_its_declared_legs():
    prices = {
        848773: {"probability": 0.25, "observed_at": NOW - timedelta(minutes=5)},
        848769: {"probability": 0.555, "observed_at": NOW - timedelta(minutes=5)},
    }
    card = build_props(_register(props=[_comparison_prop()]), prices=prices, now=NOW)[0]
    # The renderer needs both facts, so both are published rather than inferred
    # from the outcome list — a leg that produced NO outcome row is invisible in
    # the outcomes and is exactly the case worth reporting.
    assert card["legs"] == 2
    assert card["unpriced_legs"] == []
    assert card["price_state"] == "live"


def test_SPECIMEN_one_fresh_leg_cannot_make_a_comparison_live():
    """Alcaraz unpriced, Sinner fresh at .555 — the card the cert executed."""
    prices = {848769: {"probability": 0.555, "observed_at": NOW - timedelta(minutes=5)}}
    card = build_props(_register(props=[_comparison_prop()]), prices=prices, now=NOW)[0]

    assert card["price_state"] == "dark"
    assert card["age_hours"] is None
    assert card["unpriced_legs"] == ["KXGRANDSLAM-CALC26"]
    # NOT HIDDEN, and not thinned: both subjects are still on the card, and the
    # one we have nothing for carries a null rather than being dropped.
    by_key = {o["entity_key"]: o for o in card["outcomes"]}
    assert by_key["second-major:carlos-alcaraz"]["probability"] is None
    assert by_key["second-major:jannik-sinner"]["probability"] == pytest.approx(0.555)
    # The fresh leg keeps its own true flag — it is the CARD that may not claim
    # to be current. Reporting the live leg as stale would be a second lie.
    assert by_key["second-major:jannik-sinner"]["probability_is_live"] is True
    assert card["freshest_age_hours"] == pytest.approx(0.083, abs=1e-2)


def test_a_comparison_leg_that_produced_no_outcome_at_all_is_reported():
    """A declared leg with no row is the same hole, one layer earlier."""
    prop = _comparison_prop()
    prop["markets"].append(
        {"market_id": 53794, "market_external_id": "KXGRANDSLAM-NDJO26"}
    )
    prices = {
        848773: {"probability": 0.25, "observed_at": NOW - timedelta(minutes=5)},
        848769: {"probability": 0.555, "observed_at": NOW - timedelta(minutes=5)},
    }
    card = build_props(_register(props=[prop]), prices=prices, now=NOW)[0]
    assert card["legs"] == 3
    assert card["unpriced_legs"] == ["KXGRANDSLAM-NDJO26"]
    assert card["price_state"] == "dark"


def test_the_committed_register_publishes_its_comparison_as_two_legs():
    """The real card, from the real file — a rule nothing exercises is a wish."""
    register = load_register("us-open", "2026")
    props = {p["key"]: p for p in build_props(register, prices={}, now=NOW)}
    assert props["second-major"]["legs"] == 2
    assert props["second-major"]["unpriced_legs"] == [
        "KXGRANDSLAM-CALC26",
        "KXGRANDSLAM-JSIN26",
    ]
    # And an ordinary one-market card still says one, so `legs > 1` means what
    # the renderer thinks it means.
    assert props["sinner-competes"]["legs"] == 1


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

#: The two members of the `second-major` template family (UX-P151 / UX-P154).
#:
#: Prepended to every dump by default, because the pass REFUSES to write at all
#: when a curated family is not detected — a comparison card with one side is
#: not a smaller card, it is a wrong one. Without these rows every test in this
#: section would fail on that refusal instead of on its own subject, which is a
#: fixture problem masquerading as five findings.
#:
#: These are the REAL titles and outcome ids, read from production 2026-08-28.
#: The detector works off the titles, so a fixture with made-up titles would
#: prove nothing about whether the shipped card is found.
COMBINED_LEG_ROWS = [
    [53796, "KXGRANDSLAM-CALC26", "kalshi", "Carlos Alcaraz: Grand Slam wins in 2026",
     "open", 848773, "2+ Grand Slam wins", "0.25"],
    [53795, "KXGRANDSLAM-JSIN26", "kalshi", "Jannik Sinner: Grand Slam wins in 2026",
     "open", 848769, "2+ Grand Slam wins", "0.555"],
]


def _run_props_script(tmp_path, dump_rows, *, with_combined_legs=True):
    import json as _json
    import subprocess
    import sys as _sys
    from pathlib import Path as _Path

    root = _Path(__file__).resolve().parents[1]
    rows = ([*COMBINED_LEG_ROWS, *dump_rows] if with_combined_legs else list(dump_rows))
    dump = {
        "columns": ["market_id", "market_ext", "source", "market_name", "status",
                    "outcome_id", "outcome_name", "current_probability"],
        "rows": rows,
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
        [999, "KXSOMETHING-DULL", "kalshi", "Dull", "open", 5099, "Yes", "0.50"],
    ])
    assert result.returncode == 0, result.stderr
    assert [p["key"] for p in out["props"]] == ["second-major"]
    assert "below the bar" in result.stdout


def test_a_curated_prop_absent_from_the_dump_is_reported_not_invented(tmp_path):
    """A market we curated and did not find must be loud, not silently missing."""
    result, _ = _run_props_script(tmp_path, [])
    assert result.returncode == 0
    assert "curated but ABSENT from the dump" in result.stdout
    assert "KXATPCOMPETE-26USOSIN" in result.stdout


def test_the_props_pass_writes_a_register_that_still_validates(tmp_path):
    from app.utils.tournament_register import us_open_2026_contract, validate_register

    result, out = _run_props_script(tmp_path, [
        [53795, "KXGRANDSLAM-JSIN26", "kalshi", "Jannik Sinner: Grand Slam wins in 2026",
         "open", 848768, "3+ Grand Slam wins", "0.02"],
    ])
    assert result.returncode == 0
    assert validate_register(out, us_open_2026_contract()) == []
    # And the second population pass's work is still intact underneath it.
    assert len(out["matchups"]) > 0
    assert out["version"] == 3 and out["supersedes_version"] == 2


# ── The combined card, BUILT BY THE SYSTEM (UX-P151 shape, UX-P154 mechanism) ─
#
# Alex, 2026-08-28 ~10:45am PT, verbatim: *"ONE COMBINED CARD — 'Who wins a
# second major this year?' — showing BOTH players' probabilities (Alcaraz 2+
# majors, Sinner 2+ majors, each from its own real Kalshi market)."*
#
# Alex, reviewing what shipped for it: *"Was this a bespoke solution? I thought
# we'd built tools to identify groups and surface them as groups. Why didn't any
# of them trigger?"*
#
# It was, and UX-P154 replaced the hand-written legs with
# `detect_template_families`. Two properties are now under test that were not
# before, and they are the ones that make it systemic rather than typed out:
#
#   - the family is DETECTED from the market titles and outcome sets, so an
#     arriving third subject joins the card with no edit anywhere;
#   - a family nobody has written a question for STOPS THE PASS, so the next
#     one cannot ship as repeated cards the way this one did twice.
#
# The older property survives unchanged: the pass cannot produce a HALF of the
# card. Every prior shape of this question failed by quietly losing a player —
# UX-P138's template cap deleted Alcaraz at render time and the hand edit that
# followed deleted him from the file.


def test_the_combined_card_carries_one_row_per_member_and_no_single_answer(tmp_path):
    result, out = _run_props_script(tmp_path, [])
    assert result.returncode == 0, result.stderr

    card = next(p for p in out["props"] if p["key"] == "second-major")
    assert card["title"] == "Who wins a second major this year?"
    # THE SOURCE'S OWN WORDS (Alex's item 4), derived from each market's title
    # rather than curated. UX-P151 hand-wrote "Alcaraz" / "Sinner"; nothing
    # downstream could check those against anything.
    assert [o["display_name"] for o in card["outcomes"]] == [
        "Carlos Alcaraz", "Jannik Sinner",
    ]
    # Two markets, one card. This is the whole shape.
    assert [m["market_external_id"] for m in card["markets"]] == [
        "KXGRANDSLAM-CALC26", "KXGRANDSLAM-JSIN26",
    ]
    assert {o["market_external_id"] for o in card["outcomes"]} == {
        "KXGRANDSLAM-CALC26", "KXGRANDSLAM-JSIN26",
    }
    # NO single answer, by construction: a family has one candidate answer per
    # member, so the renderer ranks rather than guessing a headline.
    assert all(o["is_answer"] is False for o in card["outcomes"])
    # The DETECTION is the evidence, and a reader of the register can check it
    # against the market titles without running anything.
    assert card["evidence"]["kind"] == "prop-census-family"
    assert card["evidence"]["skeleton"] == "{} grand slam wins in 2026"
    assert [leg["source_outcome_name"] for leg in card["evidence"]["legs"]] == [
        "2+ Grand Slam wins", "2+ Grand Slam wins",
    ]
    assert [leg["subject"] for leg in card["evidence"]["legs"]] == [
        "Carlos Alcaraz", "Jannik Sinner",
    ]


def test_a_third_subject_joins_the_card_with_no_code_change(tmp_path):
    """THE test of "by the system", and the one UX-P151 could not have passed.

    A hand-written leg list notices nothing when the market opens a third
    player's ladder — the card keeps printing two men beside a question about
    all of them. Here the third row arrives in the dump and appears on the card,
    with his own name, from nothing but the shared title shape.
    """
    result, out = _run_props_script(tmp_path, [
        [53797, "KXGRANDSLAM-NDJO26", "kalshi", "Novak Djokovic: Grand Slam wins in 2026",
         "open", 848780, "2+ Grand Slam wins", "0.08"],
    ])
    assert result.returncode == 0, result.stderr

    card = next(p for p in out["props"] if p["key"] == "second-major")
    assert [o["display_name"] for o in card["outcomes"]] == [
        "Carlos Alcaraz", "Jannik Sinner", "Novak Djokovic",
    ]
    # And he is NOT also a card of his own — one question, printed once.
    assert [p["key"] for p in out["props"]] == ["second-major"]


def test_a_detected_family_nobody_curated_stops_the_pass(tmp_path):
    """The refusal that makes the detector worth having.

    Two markets asking one question about two people, with no curated question
    for the pair, would otherwise ship as the repetition Alex ruled out — or be
    silently deleted, which is how this went wrong the first time. The pass
    names the skeleton and the members so the fix is one line.
    """
    result, out = _run_props_script(tmp_path, [
        [901, "KXSETS-A", "kalshi", "Aryna Sabalenka: sets dropped in 2026", "open",
         9011, "3+ sets dropped", "0.40"],
        [902, "KXSETS-B", "kalshi", "Iga Swiatek: sets dropped in 2026", "open",
         9021, "3+ sets dropped", "0.55"],
    ])
    assert result.returncode == 1
    assert "template family" in result.stderr
    assert "'{} sets dropped in 2026'" in result.stderr
    assert "KXSETS-A" in result.stderr and "KXSETS-B" in result.stderr
    assert out is None, "a refused population pass must write nothing"


def test_a_curated_family_the_detector_cannot_find_refuses_the_write(tmp_path):
    """THE defect this shape exists to prevent, asserted as a refusal.

    One member present is not a smaller card. It is "Who wins a second major?"
    with one man under it, which reads as an answer and is not one. With only
    Sinner's market in the dump there is no family to find, and the curated
    question has nothing to attach to.
    """
    result, out = _run_props_script(
        tmp_path,
        [[53795, "KXGRANDSLAM-JSIN26", "kalshi", "Jannik Sinner: Grand Slam wins in 2026",
          "open", 848769, "2+ Grand Slam wins", "0.555"]],
        with_combined_legs=False,
    )
    assert result.returncode == 1
    assert "are not present in this dump" in result.stderr
    assert "{} grand slam wins in 2026" in result.stderr
    assert out is None, "a refused population pass must write nothing"


def test_a_member_whose_outcome_was_renamed_refuses_the_write(tmp_path):
    """A source renaming `2+ Grand Slam wins` must stop the pass, not silently
    drop that man from the comparison.

    The rename breaks the shared-outcome half of the detection — the two
    markets no longer offer anything in common — so the family dissolves and
    the curated question has nothing to attach to. Different refusal from
    UX-P151's, same guarantee: no half a card.
    """
    rows = [list(row) for row in COMBINED_LEG_ROWS]
    rows[0][6] = "Two or more Grand Slam wins"
    result, out = _run_props_script(tmp_path, rows, with_combined_legs=False)
    assert result.returncode == 1
    assert "are not present in this dump" in result.stderr
    assert out is None


# ── CERT-430, finding 3: a CLOSED leg is not a quiet one ─────────────────────
#
# The documented dump query filters `fm.status = 'open'` and nothing verified
# that it had. The cert executed the gap: flipping the Alcaraz leg's status to
# `closed` returned exit 0 and wrote the combined card, while the neighbouring
# missing-leg and renamed-outcome controls both refused and wrote nothing.
#
# A settled leg is the worst member a comparison can have. A stale number is old
# and says so; a settled one is FINISHED, and no freshness treatment downstream
# can tell those apart — the page would print a resolved market beside a live
# one as though the two were comparable.


def test_SPECIMEN_a_closed_leg_refuses_the_whole_write(tmp_path):
    rows = [list(row) for row in COMBINED_LEG_ROWS]
    rows[0][4] = "closed"
    result, out = _run_props_script(tmp_path, rows, with_combined_legs=False)
    assert result.returncode == 1
    assert "KXGRANDSLAM-CALC26" in result.stderr
    assert "closed" in result.stderr
    assert out is None, "a refused population pass must write nothing"


def test_a_settled_market_that_is_not_even_curated_still_stops_the_pass(tmp_path):
    """The dump is a contract, not a suggestion.

    A non-open row means the dump did not come from the documented query, and
    the pass cannot then claim any of its OTHER rows are open either. Refusing
    only the rows we happened to curate would leave that hole open for the next
    market that gets curated.
    """
    result, out = _run_props_script(tmp_path, [
        [999, "KXSOMETHING-DULL", "kalshi", "Dull", "settled", 5099, "Yes", "1.00"],
    ])
    assert result.returncode == 1
    assert "KXSOMETHING-DULL" in result.stderr
    assert out is None


def test_a_dump_with_no_status_column_refuses_rather_than_assuming(tmp_path):
    """Fail-safe in the direction the guard can be defeated from.

    A dump written by a different query has no `status` to check, and a check
    that passes when its evidence is absent is gotcha #53's shape — it would
    read exactly like a clean run.
    """
    import json as _json
    import subprocess
    import sys as _sys
    from pathlib import Path as _Path

    root = _Path(__file__).resolve().parents[1]
    dump = {
        "columns": ["market_id", "market_ext", "source", "market_name",
                    "outcome_id", "outcome_name", "current_probability"],
        "rows": [[row[0], row[1], row[2], row[3], row[5], row[6], row[7]]
                 for row in COMBINED_LEG_ROWS],
        "truncated": False,
    }
    (tmp_path / "dump.json").write_text(_json.dumps(dump))
    register = _json.loads(
        (root / "data/tournament_registers/us-open-2026.json").read_text()
    )
    (tmp_path / "reg.json").write_text(_json.dumps(register))
    result = subprocess.run(
        [_sys.executable, str(root / "scripts/populate_tournament_props.py"),
         "--register", str(tmp_path / "reg.json"), "--dump", str(tmp_path / "dump.json"),
         "--observed-at", "2026-08-26T00:00:00+00:00",
         "--version", "3", "--supersedes-version", "2",
         "--out", str(tmp_path / "out.json")],
        capture_output=True, text=True, cwd=str(root),
    )
    assert result.returncode == 1
    assert "no `status` column" in result.stderr
    assert not (tmp_path / "out.json").exists()


def test_an_all_open_dump_still_writes(tmp_path):
    """The control. A refusal that fires on the healthy case is not a guard."""
    result, out = _run_props_script(tmp_path, [])
    assert result.returncode == 0, result.stderr
    assert [p["key"] for p in out["props"]] == ["second-major"]


def test_a_market_cannot_be_both_a_card_and_a_family_member(tmp_path):
    """The repetition Alex ruled out, arriving by a different door.

    If `KXGRANDSLAM-JSIN26` were curated as its own card AND detected into the
    combined one, the section would show the comparison and one of its halves
    again underneath. That is a curation mistake, and the pass names it rather
    than shipping both.

    Asserted through the RUNNING PASS rather than against a static map, because
    since UX-P154 the membership is detected — there is no list of legs left to
    read, and a guard over the curation tables would be checking the wrong side
    of the change.
    """
    import json as _json
    import subprocess
    import sys as _sys
    from pathlib import Path as _Path

    root = _Path(__file__).resolve().parents[1]
    script = (root / "scripts/populate_tournament_props.py").read_text()
    # Curate one of the family's own markets as a standalone card.
    patched = script.replace(
        'CURATION: dict[str, dict] = {',
        'CURATION: dict[str, dict] = {\n'
        '    "KXGRANDSLAM-JSIN26": {"key": "sinner-majors", "title": "t", '
        '"hook": "h", "draw": "mens-singles", "answer": "2+ Grand Slam wins"},',
        1,
    )
    assert patched != script, "the CURATION anchor moved; re-point this guard"
    (tmp_path / "patched.py").write_text(patched)

    dump = {
        "columns": ["market_id", "market_ext", "source", "market_name", "status",
                    "outcome_id", "outcome_name", "current_probability"],
        "rows": [list(row) for row in COMBINED_LEG_ROWS],
        "truncated": False,
    }
    (tmp_path / "dump.json").write_text(_json.dumps(dump))
    register = _json.loads(
        (root / "data/tournament_registers/us-open-2026.json").read_text()
    )
    (tmp_path / "reg.json").write_text(_json.dumps(register))

    import os as _os

    # The script inserts ITS OWN parent's parent on `sys.path` to find `app`,
    # and this copy lives in a tmp dir. `PYTHONPATH` puts the real backend root
    # back rather than the tmp one.
    env = {**_os.environ, "PYTHONPATH": str(root)}
    result = subprocess.run(
        [_sys.executable, str(tmp_path / "patched.py"),
         "--register", str(tmp_path / "reg.json"), "--dump", str(tmp_path / "dump.json"),
         "--observed-at", "2026-08-26T00:00:00+00:00",
         "--version", "3", "--supersedes-version", "2",
         "--out", str(tmp_path / "out.json")],
        capture_output=True, text=True, cwd=str(root), env=env,
    )
    assert result.returncode == 1, result.stdout
    assert "is curated as its own card AND is a member" in result.stderr
    assert not (tmp_path / "out.json").exists()


def test_every_retired_card_is_recorded_where_it_went(tmp_path):
    """`sinner-second-major` and `alcaraz-second-major` did not vanish — they
    became rows of `second-major`, and the file has to say so."""
    result, out = _run_props_script(tmp_path, [])
    assert result.returncode == 0, result.stderr
    declined = out["props_declined"]
    for key in ("alcaraz-second-major", "sinner-second-major"):
        assert "second-major" in declined[key]
        assert "retired INTO" in declined[key]
    # Merged, not replaced: the UX-P139 grid-cell reasons are still there.
    assert "alcaraz-semifinals" in declined


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
    """On the shipped file: a card's shape and its answer count agree.

    UX-P151 AMENDED THIS, and the amendment is the rule rather than an
    exception to it. The old assertion was a flat ``len(answers) == 1``, which
    encoded an assumption that was true of every card at the time — one card,
    one market, one headline number — and stopped being true the moment Alex
    ruled a COMBINED card: *"showing BOTH players' probabilities"*.

    What actually matters has not moved: the card must never be ambiguous about
    which number is its answer. So the count is derived from the shape instead
    of asserted flat. A single-market card names exactly one answer. A card
    whose outcomes come from more than one market names NONE, because no single
    outcome can answer a comparison — and a field card is the shape
    ``validate_prop`` has supported since UX-P134 for exactly this.

    Two answers is still invalid in both shapes, and the flat rule's real job —
    catching the zero-answer card that a source rename produces silently — is
    kept for the single-market case where it is the actual failure mode.
    """
    register = load_register("us-open", "2026")
    props = register.get("props") or []
    assert props, "the props population pass has not run"
    combined = 0
    for prop in props:
        answers = [o for o in prop["outcomes"] if o.get("is_answer")]
        markets = {o.get("market_external_id") for o in prop["outcomes"]}
        assert None not in markets, f"{prop['key']} has an outcome with no provenance"
        if len(markets) > 1:
            combined += 1
            assert len(answers) == 0, (
                f"{prop['key']} spans {len(markets)} markets and still names an answer; "
                "no single outcome can answer a comparison"
            )
        else:
            assert len(answers) == 1, f"{prop['key']} has {len(answers)} answers"
    # And the combined card is actually on the shipped file, so this test cannot
    # go green by the branch above never running.
    assert combined == 1, f"expected the one combined card, found {combined}"


def test_every_prop_removed_from_the_register_says_why_it_went():
    """A shrinking props list is either curation or an accident, and the file
    has to say which (UX-P139, Alex's item 11).

    This replaces a bare ``len(props) >= 4`` floor.  That floor was written in
    UX-P135 as a "did the population pass actually run" sentinel when eleven
    props were committed, and it did its job.  But UX-P139 legitimately removes
    nine of them — eight advance-to-round questions became grid cells, and
    ``alcaraz-second-major`` was the duplicate template Alex named — so the
    floor now fails on CORRECT curation, and the only ways to satisfy it are to
    lower the number (a guard that guards nothing) or to re-add markets the page
    should not show.

    The property that actually matters is not *how many* props survive but that
    none left SILENTLY.  So every key present in a prior version and absent now
    must appear in ``props_declined`` with a reason.  A future pass that quietly
    drops a card still fails; a pass that curates deliberately and writes down
    why does not.
    """
    import json
    import subprocess
    from pathlib import Path as _Path

    register = load_register("us-open", "2026")
    declined = register.get("props_declined") or {}
    current = {p["key"] for p in register.get("props") or []}

    root = _Path(__file__).resolve().parents[2]
    committed = subprocess.run(
        ["git", "-C", str(root), "show",
         "HEAD:backend/data/tournament_registers/us-open-2026.json"],
        capture_output=True, text=True,
    )
    if committed.returncode != 0:  # pragma: no cover — no git in the sandbox
        pytest.skip("register history unavailable")

    previous = {p["key"] for p in json.loads(committed.stdout).get("props") or []}
    vanished = previous - current - set(declined)
    assert not vanished, (
        f"props removed with no reason recorded: {sorted(vanished)}. "
        "Add each to `props_declined` saying why, or restore it."
    )
    # And a reason is a sentence, not a placeholder.
    for key, reason in declined.items():
        assert isinstance(reason, str) and len(reason) > 20, (
            f"props_declined[{key}] does not explain anything"
        )


# ── The draw ingest + fixture swap (UX-P134, item 4) ─────────────────────────
#
# Thursday's ceremony rehearsed on Tuesday. The point is that 08-28 is an
# ingest RUN, not a build day, so every leg of the path is proven here first.


def _synthetic_draw_path():
    from pathlib import Path as _Path
    return _Path(__file__).resolve().parents[1] / "data/tournament_registers/_synthetic-usopen-draw.json"


def _run_ingest(tmp_path, *, allow_unregistered: bool, register=None,
                register_from_draw: bool = False):
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
    if register_from_draw:
        cmd.append("--register-from-draw")
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


# ── The ceremony path (UX-P135): the draw may register the players it names ──
#
# The Tuesday rehearsal found Thursday's blocker: 96 men / 115 women registered
# against 128 slots a side, so the real ingest would have refused on 45 names
# and written nothing. No regeneration over MARKET data can close that gap —
# nobody quotes a qualifier who has not qualified. The draw sheet can, because
# it is the document that decides who is in the tournament.


def test_the_ceremony_can_register_the_players_it_names(tmp_path):
    """The blocker, gone: 128/128 both draws, from a register holding 96/115."""
    result, out = _run_ingest(tmp_path, allow_unregistered=False, register_from_draw=True)
    assert result.returncode == 0, result.stderr
    for draw in ("mens-singles", "womens-singles"):
        slotted = [
            p for p in out["players"]
            if p.get("draw") == draw and p.get("draw_slot") is not None
        ]
        assert len(slotted) == 128, f"{draw} filled {len(slotted)}/128"
        assert sorted(p["draw_slot"] for p in slotted) == list(range(1, 129))


def test_an_admitted_player_carries_a_NAME_AND_NO_MARKET(tmp_path):
    """`sources: []` is the safety property, not an omission.

    The draw is definitive about membership and silent about price. An admitted
    player therefore has a name and a slot and nothing a probability could
    attach to — which is what makes admitting them honest rather than an
    invention.
    """
    _, out = _run_ingest(tmp_path, allow_unregistered=False, register_from_draw=True)
    admitted = [
        p for p in out["players"]
        if (p.get("evidence") or {}).get("kind") == "draw-ceremony"
    ]
    assert len(admitted) == 45
    for player in admitted:
        assert player["sources"] == []
        assert player["role"] == "participant"
        assert player["display_name"]
        assert isinstance(player["draw_slot"], int)


def test_an_admitted_player_can_never_reach_a_championship_board(tmp_path):
    """The containment, asserted rather than argued.

    `board_players` ranks priced contenders; an admitted participant is neither.
    If that ever changed, a nameless 0% would appear below Alcaraz.
    """
    from app.utils.tournament_board import build_boards

    _, out = _run_ingest(tmp_path, allow_unregistered=False, register_from_draw=True)
    admitted = {
        p["entity_key"] for p in out["players"]
        if (p.get("evidence") or {}).get("kind") == "draw-ceremony"
    }
    payload = build_boards(out, prices={}, now=NOW)
    on_board = [
        r["entity_key"] for board in payload["boards"] for r in board["rows"]
        if r["entity_key"] in admitted
    ]
    assert on_board == []
    assert payload["render_findings"] == []


def test_an_admitted_player_renders_in_the_bracket_with_no_number(tmp_path):
    """The payoff: a full bracket where every slot is a name, none a guess."""
    _, out = _run_ingest(tmp_path, allow_unregistered=False, register_from_draw=True)
    for draw in ("mens-singles", "womens-singles"):
        bracket = build_bracket(out, prices={}, draw=draw)
        assert len(bracket) == 128
        assert all(slot is not None for slot in bracket), "no undetermined holes"
        assert all(slot["probability"] is None for slot in bracket)
        assert all(slot["display_name"] for slot in bracket)


def test_admission_never_collides_two_players_onto_one_key(tmp_path):
    """The synthetic draw names 'Synthetic Qualifier 116' in BOTH draws.

    A shared slug would silently overwrite one with the other, and the second
    draw's bracket would point at the first draw's player.
    """
    _, out = _run_ingest(tmp_path, allow_unregistered=False, register_from_draw=True)
    keys = [p["entity_key"] for p in out["players"]]
    assert len(keys) == len(set(keys))


def test_admission_is_OPT_IN_and_the_default_still_refuses(tmp_path):
    """The flag is the decision. Without it nothing is written, unchanged."""
    result, out = _run_ingest(tmp_path, allow_unregistered=False)
    assert result.returncode == 1
    assert out is None


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

    def test_the_bracket_is_empty_because_we_hold_NO_SLOTS(self):
        """⬅️ UX-P142 changed this test's REASON, not its expectation.

        It read "empty before the ceremony" and asserted the latch was down.
        The ceremony happened on 2026-08-27 and the latch is up; the bracket is
        still `[]`, and now for the reason that matters:

        ESPN publishes the pairings and NOT the draw-sheet position, so
        `ingest_espn_draw.py` writes matchups and refuses to write `draw_slot`.
        Inventing positions from ESPN's list order would fabricate the whole
        second round while rendering exactly like the first. The fixtures reach
        the page through the match list instead.

        The sibling test below is the one that guards the LATCH, by handing
        this function slots with the latch down.
        """
        register = load_register("us-open", "2026")
        assert register["draw_released"] is True
        assert all(p.get("draw_slot") is None for p in register["players"])
        for draw in ("mens-singles", "womens-singles"):
            assert build_bracket(register, prices={}, draw=draw) == []

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
    # `KXATPCOMPETE-26USOSIN` and not a `*-second-major` ticker: since UX-P151
    # those two are LEGS of the combined card, and a leg's rename has its own
    # refusal with its own message (`test_a_combined_leg_whose_outcome_was_
    # renamed_refuses_the_write`). This one is the single-market answer rule,
    # which needs a single-market card to be about.
    result, out = _run_props_script(tmp_path, [
        [59172808, "KXATPCOMPETE-26USOSIN", "kalshi", "Sinner to play", "open",
         219796782, "Affirmative", "0.63"],
    ])
    assert result.returncode == 1
    assert "REFUSED" in result.stderr
    assert "is not an outcome of this market" in result.stderr
    assert out is None, "a refused population pass must write nothing"


# ---------------------------------------------------------------------------
# build_results — decided matches with their score (UX-P139, Alex's item 9)
# ---------------------------------------------------------------------------

def _results_register():
    return {
        "schema_version": "tournament-register/v1",
        "tournament": "us-open",
        "season": "2026",
        "version": 1,
        "generated_at": NOW.isoformat(),
        "draw_released": False,
        "players": [
            {
                "entity_key": "jacob-fearnley",
                "display_name": "Jacob Fearnley",
                "draw": "mens-singles",
                "role": "participant",
                "seed": None,
                "sources": [],
            },
            {
                "entity_key": "roberto-carballes-baena",
                "display_name": "Roberto Carballes Baena",
                "draw": "mens-singles",
                "role": "participant",
                "seed": None,
                "sources": [],
            },
        ],
        "matchups": [],
    }


def _espn(**overrides):
    found = {
        "score": "7-6, 6-3",
        "winner_name": "Jacob Fearnley",
        "winner_normalized": "jacobfearnley",
        "players": ["Roberto Carballes Baena", "Jacob Fearnley"],
        "espn_competition_id": "184607",
        "espn_round": "Qualifying 1st Round",
        "completed_at": "2026-08-24T15:05Z",
    }
    found.update(overrides)
    return {
        "draws": {"mens-singles": {"carballesbaena|jacobfearnley": found}},
        "stats": {"final": 199, "scored": 181},
        "errors": [],
    }


def test_a_result_attaches_when_both_players_are_registered():
    payload = build_results(_results_register(), results=_espn())
    assert payload["count"] == 1
    [row] = payload["matches"]
    assert row["score"] == "7-6, 6-3"
    assert row["winner_entity_key"] == "jacob-fearnley"
    assert [p["is_winner"] for p in row["players"]].count(True) == 1
    assert row["source"] == "espn"


def test_the_join_is_the_PAIR_and_not_the_matchup():
    """The correction that made this section exist at all.

    ``build_slate`` retires a matchup the moment it starts, so by the time a
    match has a result the register no longer carries it. Joining on matchups
    produced 0 results against 199 finished ESPN competitions — a section
    structurally guaranteed to be empty.
    """
    register = _results_register()
    assert register["matchups"] == []
    assert build_results(register, results=_espn())["count"] == 1


def test_a_result_naming_one_unregistered_player_is_counted_and_dropped():
    register = _results_register()
    register["players"] = register["players"][:1]
    payload = build_results(register, results=_espn())
    assert payload["count"] == 0
    assert payload["unregistered_pairs"] == 1


def test_a_winner_who_is_neither_player_is_never_attached():
    """A score under the wrong two names looks completely plausible."""
    payload = build_results(
        _results_register(),
        results=_espn(winner_name="Somebody Else", winner_normalized="somebodyelse"),
    )
    assert payload["count"] == 0
    assert payload["winner_not_registered"] == 1


def test_a_retirement_carries_the_outcome_with_no_score():
    payload = build_results(_results_register(), results=_espn(score=None))
    [row] = payload["matches"]
    assert row["score"] is None
    assert row["winner_entity_key"] == "jacob-fearnley"


def test_the_source_error_travels_so_an_empty_section_can_say_why():
    results = _espn()
    results["errors"] = ["atp: timeout"]
    results["draws"] = {}
    payload = build_results(_results_register(), results=results)
    assert payload["count"] == 0
    assert payload["source_errors"] == ["atp: timeout"]


def test_no_results_at_all_is_an_empty_section_not_a_crash():
    payload = build_results(_results_register(), results={})
    assert payload["count"] == 0
    assert payload["source_competitions"] == 0


# ---------------------------------------------------------------------------
# UX-P146 — a finished match carries what the market said BEFORE it
#
# Alex, on the UX-P145 desktop artifact: "finished outcomes on the right must
# show their PRE-MATCH probabilities alongside the result — a result without the
# prior probability is half the story on a probability product."
# ---------------------------------------------------------------------------

def _results_register_with_matchup():
    """The same two players, plus the matchup market the register still pins.

    The 12-of-76 case on production: `build_slate` retires this matchup for
    SCHEDULING reasons the moment it starts, but the register file still carries
    it, and that is where the pre-match number comes from.
    """
    register = _results_register()
    register["matchups"] = [{
        "matchup_key": "mens-singles:jacob-fearnley-vs-roberto-carballes-baena:2026-08-24",
        "draw": "mens-singles",
        "round": "qualifying",
        "scheduled_date": "2026-08-24T13:00:00+00:00",
        "players": ["jacob-fearnley", "roberto-carballes-baena"],
        "sources": [{
            "source": "polymarket",
            "kind": "match",
            "market_id": 59481999,
            "outcome_id": 910001,
            "status": "live",
            "terminal_result": None,
            "evidence": {"kind": "match-market-census", "observed_at": NOW.isoformat()},
            "sides": {
                "jacob-fearnley": {"outcome_id": 910001, "source_label": "Jacob Fearnley"},
                "roberto-carballes-baena": {
                    "outcome_id": 910002, "source_label": "Roberto Carballes Baena"
                },
            },
        }],
    }]
    return register


def _matchup_prices(a_open=0.62, b_open=0.38, a_now=1.0, b_now=0.0):
    return {
        910001: {"probability": a_now, "opening_probability": a_open, "observed_at": NOW},
        910002: {"probability": b_now, "opening_probability": b_open, "observed_at": NOW},
    }


def test_a_finished_match_carries_the_prior_when_we_held_the_market():
    payload = build_results(
        _results_register_with_matchup(), results=_espn(), prices=_matchup_prices()
    )
    [row] = payload["matches"]
    by_key = {p["entity_key"]: p["prematch_probability"] for p in row["players"]}
    assert by_key["jacob-fearnley"] == 0.62
    assert by_key["roberto-carballes-baena"] == 0.38
    assert payload["with_prematch"] == 1


def test_the_prior_is_the_OPENING_number_and_never_the_last_one_we_saw():
    """The whole reason this reads `opening_probability`.

    A decided match's market drifts to the result: the fixture's current pair is
    1.0 / 0.0. Print that as "what the market thought" and every winner is 100%
    and every loser 0% — a perfectly confident number that is really just the
    scoreline read back, which is worse than showing nothing.
    """
    prices = _matchup_prices(a_now=1.0, b_now=0.0)
    payload = build_results(
        _results_register_with_matchup(), results=_espn(), prices=prices
    )
    priors = {p["entity_key"]: p["prematch_probability"] for p in payload["matches"][0]["players"]}
    assert 1.0 not in priors.values()
    assert 0.0 not in priors.values()


def test_the_prior_is_normalized_as_a_PAIR_like_every_other_number_here():
    # 0.55 + 0.50 is one question with a 5-point overround, exactly as the slate
    # treats a live pair — so the printed prior sums to 1 and is quoted on the
    # same basis a live row is.
    payload = build_results(
        _results_register_with_matchup(),
        results=_espn(),
        prices=_matchup_prices(a_open=0.55, b_open=0.50),
    )
    priors = [p["prematch_probability"] for p in payload["matches"][0]["players"]]
    assert sum(priors) == pytest.approx(1.0)
    assert priors[0] != 0.55  # normalized, not passed through


def test_an_INCOHERENT_opening_pair_yields_no_prior_at_all():
    """Refusal 2 of this module, applied to history.

    0.90 + 0.60 is two readings of different vintage, not a distribution.
    Dividing by 1.5 gives 60/40 — a number with no referent that looks exactly
    like a real one, printed under two real players' names, forever.
    """
    payload = build_results(
        _results_register_with_matchup(),
        results=_espn(),
        prices=_matchup_prices(a_open=0.90, b_open=0.60),
    )
    assert all(p["prematch_probability"] is None for p in payload["matches"][0]["players"])
    assert payload["with_prematch"] == 0


def test_no_registered_matchup_means_no_prior_and_the_count_says_so():
    """64 of 76 production results are this case, and it must stay silent.

    We hold player-level markets for both of them and no MATCH market, so there
    is no prior. Substituting the title board's number — a player's chance of
    winning the tournament — would be a fabricated answer to a different
    question wearing a real player's name.
    """
    payload = build_results(_results_register(), results=_espn(), prices=_matchup_prices())
    [row] = payload["matches"]
    assert all(p["prematch_probability"] is None for p in row["players"])
    assert payload["with_prematch"] == 0
    # …and the row is still built. A missing prior never costs a result.
    assert row["score"] == "7-6, 6-3"


def test_prices_is_optional_so_an_older_caller_cannot_crash_the_section():
    payload = build_results(_results_register_with_matchup(), results=_espn())
    assert payload["count"] == 1
    assert payload["with_prematch"] == 0


def test_the_route_hands_build_results_the_prices_it_already_loaded():
    """The wiring, which is the half a unit test cannot see.

    `_load_prices` is called once over the union of every pinned outcome id,
    matchup ids included, so this feature costs no extra query. If the call site
    ever drops the argument the section silently loses every prior and every
    test above still passes.
    """
    source = (Path(__file__).resolve().parents[1] / "app" / "routes" / "tournaments.py").read_text()
    start = source.index("build_results(", source.index('payload["results"]'))
    # Balanced-paren scan rather than "up to the first `)`" — the call is
    # multi-line and contains `_espn_results(slug)`, so the naive version reads
    # a window that stops before the argument it is checking for and fails on a
    # correct call site.
    depth, end = 0, start
    for index in range(start, len(source)):
        if source[index] == "(":
            depth += 1
        elif source[index] == ")":
            depth -= 1
            if depth == 0:
                end = index + 1
                break
    call = source[start:end]
    assert call.endswith(")")
    assert "prices=prices" in call

