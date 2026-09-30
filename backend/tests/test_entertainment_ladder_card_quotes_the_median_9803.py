"""#9803 — an /entertainment ladder card quotes the rung the market leans on, not its loosest.

Production 2026-09-30 10:50Z, `/entertainment` at 390px: every Rotten Tomatoes
card printed `top_outcomes[0]`, and `_market_row` sorts by price, so a cumulative
ladder always led with its loosest rung ("Clayface · Above 45 · 95%"). /weather
(#9283) and the market page (#9531) quote `ladder_median_row`; this card links to
that page, so `_market_row` now serves the same rung as `headline` — only when it
differs from the priced leader, so every other row is unchanged.

The legs below are the stored production rungs (db-query, 10:55Z), unedited.
"""

import itertools
from datetime import datetime, timezone
from types import SimpleNamespace

from app.routes.entertainment import _build_movies_tv, _market_row

_IDS = itertools.count(1)


def _market(market_id: int, name: str, legs, external_id: str | None = None):
    return SimpleNamespace(
        id=market_id,
        name=name,
        external_id=external_id or f"KXROTTENTOMATOES-{market_id}",
        source="kalshi",
        outcomes=[
            SimpleNamespace(
                id=next(_IDS), name=leg[0], current_probability=leg[1],
                probability_change_24h=0.0,
                external_id=leg[2] if len(leg) > 2 else None,
            )
            for leg in legs
        ],
        volume_24h=1000,
        resolution_date=None,
        updated_at=datetime(2026, 9, 30, tzinfo=timezone.utc),
        image_url=None,
        hook_description=None,
        llm_sport_category="entertainment",
    )


CLAYFACE = _market(58728375, "Clayface · Rotten Tomatoes score", [
    ("Above 45", 0.945), ("Above 50", 0.925), ("Above 55", 0.875),
    ("Above 60", 0.825), ("Above 65", 0.705), ("Above 70", 0.655),
    ("Above 75", 0.555), ("Above 80", 0.425), ("Above 85", 0.245),
    ("Above 90", 0.065),
])

SOCIAL_RECKONING = _market(60653755, "The Social Reckoning · Rotten Tomatoes score", [
    ("Above 45", 0.935), ("Above 50", 0.875), ("Above 55", 0.805),
    ("Above 60", 0.725), ("Above 65", 0.645), ("Above 70", 0.515),
    ("Above 75", 0.375), ("Above 80", 0.255), ("Above 85", 0.125),
    ("Above 90", 0.055),
])

# Polymarket's "N+" grammar. The stored Yes/No legs are the 60+ condition's
# `_yes`/`_no` twins, which `clean_and_dedupe_outcomes` drops (#2427) — their
# external ids are carried so the fixture takes the production path.
_C60 = "0xdeee600dc5b83ea07945314247ce8f4a6d4085dcaf2220c58b6785356a5cd54a"
SENSE_AND_SENSIBILITY = _market(61998665, '"Sense and Sensibility" Rotten Tomatoes Score?', [
    ("Yes", 0.91, _C60 + "_yes"), ("No", 0.09, _C60 + "_no"), ("60+", 0.9765, _C60),
    ("65+", 0.945, "0xfed9"), ("75+", 0.54, "0x95bd"), ("85+", 0.047, "0xfacb"),
    ("90+", 0.043, "0xc338"), ("70+", 0.8, "0xf33a"), ("80+", 0.23, "0xda39"),
], external_id="1066511")

# Controls. A race of named contenders is not a ladder.
BIG_BROTHER = _market(1, "Big Brother Season 28 · Winner", [
    ("Rick Devens", 0.52), ("Drew Campbell", 0.34), ("Taylor Brown", 0.17),
], external_id="KXBIGBROTHER-28")

# A ladder that is long odds all the way up has no median; the leader stands.
LONG_ODDS = _market(2, "OG Anunoby Game-Winning Tip-In Basketball: Sale Price", [
    ("Above $500K", 0.07), ("Above $1.5M", 0.06), ("Above $4M", 0.06),
], external_id="KXSALEPRICE-OG")


def _row(market):
    return _market_row(market, max_outcomes=8)


def test_the_rt_cards_quote_the_tightest_rung_the_market_still_favours():
    assert _row(CLAYFACE)["headline"] == {"name": "Above 75", "prob": 55.5}
    assert _row(SOCIAL_RECKONING)["headline"] == {"name": "Above 70", "prob": 51.5}
    assert _row(SENSE_AND_SENSIBILITY)["headline"] == {"name": "75+", "prob": 54.0}


def test_strawman_the_loosest_rung_is_what_the_card_used_to_print():
    # What the card printed before: top_outcomes[0] beside `prob`. The fix must
    # not have moved either, because ranking and the hook gate read them.
    row = _row(CLAYFACE)
    assert (row["top_outcomes"][0]["name"], row["prob"]) == ("Above 45", 94.5)
    assert row["headline"]["name"] != row["top_outcomes"][0]["name"]


def test_a_race_and_a_long_odds_ladder_serve_no_headline():
    assert _row(BIG_BROTHER)["headline"] is None
    assert _row(LONG_ODDS)["headline"] is None
    assert _row(BIG_BROTHER)["top_outcomes"][0]["name"] == "Rick Devens"


def test_the_rt_section_serves_the_headline_through_the_route_builder():
    section = _build_movies_tv({"movies": [CLAYFACE, SOCIAL_RECKONING, BIG_BROTHER]})
    by_id = {r["market_id"]: r for r in section["rt_markets"]}
    assert by_id[58728375]["headline"]["name"] == "Above 75"
    assert by_id[60653755]["headline"]["name"] == "Above 70"
