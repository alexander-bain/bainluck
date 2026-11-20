"""Real `_score_futures` proof for #13100 (Ruling 277: A, second half).

Verifies that when a far-out (>45d), quiet (<2% dated 24h shift) awards market
has its gravity deferred under `DISCOVER_AWARDS_GRAVITY_GATE_ENABLED`:

1. `_score_futures` withholds `_EXTERNAL_CURATOR_RECALL_SCORE_BONUS` (+25) and
   any positive `discover_llm_score` lift (on both display `score` and uncapped
   `_rank_score`), as well as stale/sub-2% `leader_change`/`rank_shakeup`/
   lifetime `surprise` and positive legacy `curation_score_adj`.
2. Stale undated per-write deltas and tiny (<2%) rank swaps do NOT unlock the
   gate; a real dated >=2% 24h move or proximity (<=45 days) unlocks everything.
3. Non-awards markets are completely unchanged (identical `score` and
   `_rank_score` with the switch on vs off).
4. `_score_market_trace` mirrors `_score_futures` so debug traces do not drift.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.routes.feed import (
    PersonalizationContext,
    _EXTERNAL_CURATOR_RECALL_SCORE_BONUS,
    _score_futures,
    _score_market_trace,
)
from app.tasks.enrich_markets import (
    DISCOVER_LLM_METADATA_KEY,
    DISCOVER_LLM_SCHEMA_VERSION,
)
from app.utils.futures_highlights import (
    AWARDS_GRAVITY_HORIZON_DAYS,
    DISCOVER_AWARDS_GRAVITY_GATE_ENV,
)
from app.utils.futures_market_snapshot import DATED_BASIS_METADATA_KEY

FROZEN_NOW = datetime(2025, 2, 15, 18, 0, tzinfo=timezone.utc)


def _positive_llm_meta(salience: int = 4) -> dict:
    return {
        DISCOVER_LLM_METADATA_KEY: {
            "schema_version": DISCOVER_LLM_SCHEMA_VERSION,
            "topic": "entertainment",
            "subtopic": "awards",
            "archetype": "other",
            "audience_scope": "broad",
            "salience_score": salience,
            "junk_flags": [],
            "entities": ["The Odyssey"],
            "comparison_axes": [],
        }
    }


def _negative_llm_meta() -> dict:
    return {
        DISCOVER_LLM_METADATA_KEY: {
            "schema_version": DISCOVER_LLM_SCHEMA_VERSION,
            "topic": "entertainment",
            "subtopic": "awards",
            "archetype": "other",
            "audience_scope": "niche",
            "salience_score": 2,
            "junk_flags": [],
            "entities": [],
            "comparison_axes": [],
        }
    }


class _Outcome:
    def __init__(
        self,
        oid: int,
        name: str,
        prob: float,
        *,
        rank: int = 1,
        opening_prob: float | None = None,
        change_24h: float | None = None,
        rank_change_24h: int | None = None,
    ):
        self.id = oid
        self.name = name
        self.external_id = f"out-{oid}"
        self.current_probability = prob
        self.opening_probability = opening_prob if opening_prob is not None else prob
        self.probability_change_24h = change_24h
        self.rank = rank
        self.rank_change_24h = rank_change_24h
        self.team_id = None
        self.is_winner = None
        self.resolution_source = None
        self.last_updated = FROZEN_NOW - timedelta(minutes=10)
        self.price_changed_at = FROZEN_NOW - timedelta(hours=2)
        self.current_american_odds = None
        self.opening_american_odds = None


class _Market:
    def __init__(
        self,
        mid: int,
        name: str,
        *,
        category: str = "entertainment",
        source: str = "polymarket",
        days_out: int = 115,
        outcomes: list[_Outcome] | None = None,
        market_metadata: dict | None = None,
        curation_score_adj: int = 0,
        market_tier: int = 1,
    ):
        self.id = mid
        self.name = name
        self.external_id = f"ext-{mid}"
        self.source = source
        self.group_id = f"{source}:{mid}"
        self.group_type = "negrisk" if source == "polymarket" else "kalshi_event"
        self.canonical_market_key = None
        self.llm_sport_category = category
        self.market_tier = market_tier
        self.market_type = "field"
        self.status = "open"
        self.sport = None
        self.sport_id = None
        self.resolution_date = FROZEN_NOW + timedelta(days=days_out)
        self.created_at = FROZEN_NOW - timedelta(days=30)
        self.updated_at = FROZEN_NOW - timedelta(minutes=10)
        self.commence_time = self.resolution_date
        self.volume_24h = 25000
        self.volume = 250000
        self.hook_description = None
        self.hook_generated_at = None
        self.hook_leader_at_generation = None
        self.image_url = None
        self.image_width = None
        self.image_height = None
        self.description = ""
        self.market_metadata = dict(market_metadata or {})
        self.curation_score_adj = curation_score_adj
        self.llm_league = None
        self.llm_gender = None
        self.llm_level = None
        self.outcomes = outcomes or [
            _Outcome(mid * 10 + 1, "The Odyssey", 0.45, rank=1),
            _Outcome(mid * 10 + 2, "Dune: Part Three", 0.30, rank=2),
            _Outcome(mid * 10 + 3, "The Black Ball", 0.15, rank=3),
        ]


def _mock_db(markets: list[_Market]):
    db = AsyncMock()

    def make_result(*_a, **_k):
        r = MagicMock()
        scalars = MagicMock()
        scalars.all.return_value = [m.id for m in markets]
        unique = MagicMock()
        unique.all.return_value = markets
        scalars.unique.return_value = unique
        r.scalars.return_value = scalars
        r.all.return_value = []
        return r

    db.execute = AsyncMock(side_effect=make_result)
    return db


async def _run_score_futures(
    markets: list[_Market],
    *,
    curator_ids: list[int] | None = None,
) -> dict[int, dict]:
    with (
        patch(
            "app.routes.feed._external_curator_recall_market_ids",
            new=AsyncMock(return_value=list(curator_ids or [])),
        ),
        patch(
            "app.routes.feed._get_canonical_source_counts",
            new=AsyncMock(return_value={}),
        ),
        patch(
            "app.tasks.redis_state.get_async_redis_client",
            side_effect=Exception("no redis in test"),
        ),
    ):
        items = await _score_futures(
            _mock_db(markets),
            FROZEN_NOW,
            None,
            PersonalizationContext(),
        )
    by_id: dict[int, dict] = {}
    for item in items:
        if item.get("type") != "futures":
            continue
        by_id[item["data"]["id"]] = item
        for overflow in item.get("_story_overflow_members") or []:
            odata = overflow.get("data") or {}
            if odata.get("id") is not None:
                by_id.setdefault(odata["id"], overflow)
    return by_id


def _live_oscars_and_grammys_fixtures(*, with_positive_llm: bool = True) -> list[_Market]:
    """Build fixtures matching the 6 live Oscars and 6 live Grammys rows from #13100."""
    llm_meta = _positive_llm_meta(salience=4) if with_positive_llm else {}
    return [
        # Oscars (6 rows: Best Picture + 5 craft/category rows seen live on b77633ed)
        _Market(
            6173044,
            "Oscar Winner: Best Picture",
            source="kalshi",
            days_out=407,
            curation_score_adj=30,
            market_metadata=_positive_llm_meta(salience=4),
            outcomes=[
                _Outcome(61730441, "The Odyssey", 0.535, rank=1, opening_prob=0.17, change_24h=0.01),
                _Outcome(61730442, "You Can See Everything", 0.205, rank=2, opening_prob=0.015),
                _Outcome(61730443, "The Black Ball", 0.115, rank=3, opening_prob=0.10),
            ],
        ),
        _Market(
            65814223,
            "Oscars 2027: Best Film Editing Winner",
            days_out=115,
            market_metadata=llm_meta,
            outcomes=[
                _Outcome(658142231, "The Odyssey", 0.40, rank=1, opening_prob=0.20, change_24h=0.002, rank_change_24h=0),
                _Outcome(658142232, "You Can See Everything", 0.30, rank=2, opening_prob=0.25, change_24h=0.003, rank_change_24h=1),
                _Outcome(658142233, "The Black Ball", 0.15, rank=3, opening_prob=0.15, change_24h=-0.003, rank_change_24h=-1),
            ],
        ),
        _Market(
            65814224,
            "Oscars 2027: Best Production Design Winner",
            days_out=115,
            market_metadata=llm_meta,
            outcomes=[
                _Outcome(658142241, "The Odyssey", 0.70, rank=1, opening_prob=0.40, change_24h=0.001, rank_change_24h=0),
                _Outcome(658142242, "Dune: Part Three", 0.28, rank=2, opening_prob=0.35, change_24h=-0.002, rank_change_24h=1),
                _Outcome(658142243, "Digger", 0.01, rank=3, opening_prob=0.02, change_24h=0.001, rank_change_24h=-1),
            ],
        ),
        _Market(
            65814225,
            "Oscars 2027: Best Costume Design Winner",
            days_out=115,
            market_metadata=llm_meta,
            # Stale undated per-write delta (no dated_movement_basis in metadata)
            outcomes=[
                _Outcome(658142251, "The Odyssey", 0.53, rank=1, opening_prob=0.35, change_24h=0.03),
                _Outcome(658142252, "The Black Ball", 0.11, rank=2, opening_prob=0.12),
                _Outcome(658142253, "Wuthering Heights", 0.10, rank=3, opening_prob=0.11),
            ],
        ),
        _Market(
            65814226,
            "Oscars 2027: Best Sound Winner",
            days_out=115,
            market_metadata=llm_meta,
            outcomes=[
                _Outcome(658142261, "The Odyssey", 0.42, rank=1, opening_prob=0.25),
                _Outcome(658142262, "Dune: Part Three", 0.27, rank=2, opening_prob=0.26),
                _Outcome(658142263, "Godzilla Minus Zero", 0.09, rank=3, opening_prob=0.08),
            ],
        ),
        _Market(
            58492242,
            "Oscars 2027: Best International Feature Film Winner",
            days_out=224,
            market_metadata=llm_meta,
            outcomes=[
                _Outcome(584922421, "La Bola Negra", 0.83, rank=1, opening_prob=0.774),
                _Outcome(584922422, "Possible Love", 0.04, rank=2, opening_prob=0.05),
                _Outcome(584922423, "All of a Sudden", 0.04, rank=3, opening_prob=0.04),
            ],
        ),
        # Grammys (6 rows seen live on b77633ed)
        _Market(
            70208645,
            "Grammys 2027: Best Country Song Winner",
            days_out=80,
            market_metadata=llm_meta,
            # 0.05% tick that flipped rank=1 without a real >=2% price move
            outcomes=[
                _Outcome(702086451, "Choosin' Texas - Ella Langley", 0.74, rank=1, opening_prob=0.585, change_24h=0.0005, rank_change_24h=1),
                _Outcome(702086452, "Dry Spell - Kacey Musgraves", 0.10, rank=2, opening_prob=0.14, change_24h=-0.0005, rank_change_24h=-1),
                _Outcome(702086453, "Phone, Keys, Wallet - Lainey Wilson", 0.08, rank=3, opening_prob=0.09),
            ],
        ),
        _Market(
            58492243,
            "Grammys 2027: Song of the Year Winner",
            days_out=224,
            market_metadata=llm_meta,
            outcomes=[
                _Outcome(584922431, "Choosin' Texas - Ella Langley", 0.35, rank=1, opening_prob=0.122, change_24h=0.0085, rank_change_24h=0),
                _Outcome(584922432, "WHERE IS MY HUSBAND! - RAYE", 0.16, rank=2, opening_prob=0.15, change_24h=0.004, rank_change_24h=1),
                _Outcome(584922433, "Man I Need - Olivia Dean", 0.11, rank=3, opening_prob=0.12, change_24h=-0.004, rank_change_24h=-1),
            ],
        ),
        _Market(
            69851819,
            "Grammys 2027: Best Pop Solo Performance Winner",
            days_out=80,
            market_metadata=llm_meta,
            outcomes=[
                _Outcome(698518191, "Man I Need - Olivia Dean", 0.36, rank=1, opening_prob=0.88, change_24h=0.002, rank_change_24h=1),
                _Outcome(698518192, "WHERE IS MY HUSBAND! - RAYE", 0.32, rank=2, opening_prob=0.125, change_24h=-0.002, rank_change_24h=-1),
                _Outcome(698518193, "the cure - Olivia Rodrigo", 0.17, rank=3, opening_prob=0.16),
            ],
        ),
        _Market(
            70208637,
            "Grammys 2027: Best Global Music Album Winner",
            days_out=80,
            market_metadata=llm_meta,
            # Stale undated per-write delta (no dated_movement_basis)
            outcomes=[
                _Outcome(702086371, "HOPE!! - Angelique Kidjo", 0.38, rank=1, opening_prob=0.34, change_24h=0.06),
                _Outcome(702086372, "EQUILIBRIVM - Anitta", 0.22, rank=2, opening_prob=0.10),
                _Outcome(702086373, "Love Is a Kingdom - Tems", 0.21, rank=3, opening_prob=0.20),
            ],
        ),
        _Market(
            70208638,
            "Grammys 2027: Best Latin Pop Album Winner",
            days_out=80,
            market_metadata=llm_meta,
            outcomes=[
                _Outcome(702086381, "No Me Arrepiento de Sentir Tanto - KAROL G", 0.32, rank=1, opening_prob=0.16),
                _Outcome(702086382, "Other Album", 0.25, rank=2, opening_prob=0.26),
            ],
        ),
        _Market(
            70208641,
            "Grammys 2027: Best Reggae Album Winner",
            days_out=80,
            market_metadata=llm_meta,
            outcomes=[
                _Outcome(702086411, "Brightside - Ziggy Marley", 0.33, rank=1, opening_prob=0.11),
                _Outcome(702086412, "Exile - Chronixx", 0.29, rank=2, opening_prob=0.14),
                _Outcome(702086413, "The Art of Acceptance - Protoje", 0.14, rank=3, opening_prob=0.15),
            ],
        ),
    ]


@pytest.mark.asyncio
async def test_deferred_awards_drop_curator_llm_and_stale_lifts_on_real_score_futures(
    monkeypatch,
):
    markets = _live_oscars_and_grammys_fixtures(with_positive_llm=True)
    all_ids = [m.id for m in markets]

    monkeypatch.setenv(DISCOVER_AWARDS_GRAVITY_GATE_ENV, "0")
    off_results = await _run_score_futures(markets, curator_ids=all_ids)

    monkeypatch.setenv(DISCOVER_AWARDS_GRAVITY_GATE_ENV, "1")
    on_results = await _run_score_futures(markets, curator_ids=all_ids)

    assert set(off_results) == set(all_ids)
    assert set(on_results) == set(all_ids)

    for m in markets:
        off_item = off_results[m.id]
        on_item = on_results[m.id]
        # Switch OFF: curator (+25) + gravity (+18) + compelling (+8) + LLM (+5)
        # saturate every display score to 98 and push _rank_score into 115-155.
        assert off_item["score"] == 98, f"{m.name} switch OFF expected 98, got {off_item['score']}"
        assert off_item["_rank_score"] >= 115.0
        # Switch ON: every quiet far-out Oscars/Grammys market lands cleanly at
        # base 59 (40 entertainment + 15 tier_1 + 4 secondary_league) — zero
        # curator lift, zero positive LLM lift, zero stale/sub-2% boost.
        assert on_item["score"] == 59, f"{m.name} switch ON expected 59, got {on_item['score']}"
        assert on_item["_rank_score"] == 59.0


@pytest.mark.asyncio
async def test_curator_and_llm_return_when_awards_gate_opens_by_proximity(monkeypatch):
    near_oscar = _Market(
        900001,
        "Oscar Winner: Best Picture",
        days_out=AWARDS_GRAVITY_HORIZON_DAYS,
        curation_score_adj=15,
        market_metadata=_positive_llm_meta(salience=4),
    )

    monkeypatch.setenv(DISCOVER_AWARDS_GRAVITY_GATE_ENV, "1")
    results = await _run_score_futures([near_oscar], curator_ids=[near_oscar.id])
    item = results[near_oscar.id]
    # 59 base + 18 gravity + 15 curation = 92 -> quality ceiling 88 -> +25 curator -> 98 -> +5 llm -> 98
    assert item["score"] == 98
    # Uncapped rank_score: 59 + 18 + 15 + 25 curator + 5 llm = 122.0
    assert item["_rank_score"] == 122.0


@pytest.mark.asyncio
async def test_curator_and_llm_return_when_awards_market_has_dated_24h_move(monkeypatch):
    observed_18h_ago = (FROZEN_NOW - timedelta(hours=18)).isoformat()
    meta = _positive_llm_meta(salience=4)
    meta[DATED_BASIS_METADATA_KEY] = {
        "9000021": [0.40, observed_18h_ago],
    }
    moved_grammy = _Market(
        900002,
        "Grammys 2027: Song of the Year Winner",
        days_out=120,
        market_metadata=meta,
        outcomes=[
            _Outcome(9000021, "Choosin' Texas - Ella Langley", 0.45, rank=1, opening_prob=0.40, change_24h=0.05),
            _Outcome(9000022, "Man I Need - Olivia Dean", 0.30, rank=2, opening_prob=0.32),
        ],
    )

    monkeypatch.setenv(DISCOVER_AWARDS_GRAVITY_GATE_ENV, "1")
    results = await _run_score_futures([moved_grammy], curator_ids=[moved_grammy.id])
    item = results[moved_grammy.id]
    # Gate opened by real +5% dated 24h shift: 59 + 18 gravity = 77 -> +25 curator = 98
    assert item["score"] == 98
    # Uncapped rank_score: 59 + 18 gravity + 25 curator + 5 llm = 107.0
    assert item["_rank_score"] == 107.0


@pytest.mark.asyncio
async def test_negative_llm_and_negative_curation_still_apply_to_deferred_awards(
    monkeypatch,
):
    demoted_oscar = _Market(
        900003,
        "Oscars 2027: Best Sound Winner",
        days_out=120,
        curation_score_adj=-10,
        market_metadata=_negative_llm_meta(),  # salience 2 (-3) + niche (-15) = -18
    )

    monkeypatch.setenv(DISCOVER_AWARDS_GRAVITY_GATE_ENV, "1")
    results = await _run_score_futures([demoted_oscar], curator_ids=[demoted_oscar.id])
    item = results[demoted_oscar.id]
    # 59 base - 10 curation = 49, curator bonus deferred (+0), negative LLM -18 -> 31
    assert item["score"] == 31
    assert item["_rank_score"] == 31.0


@pytest.mark.asyncio
async def test_non_awards_markets_are_byte_for_byte_unchanged_with_curator_and_llm(
    monkeypatch,
):
    non_awards = [
        _Market(
            109596,
            "Best AI at the end of 2026?",
            category="tech",
            source="kalshi",
            days_out=120,
            market_tier=2,
            curation_score_adj=30,
            market_metadata=_positive_llm_meta(salience=4),
            outcomes=[
                _Outcome(1095961, "Gemini", 0.60, rank=1),
                _Outcome(1095962, "Claude", 0.25, rank=2),
            ],
        ),
        _Market(
            27467306,
            "TIME Person of the Year 2026",
            category="entertainment",
            days_out=200,
            market_tier=2,
            market_metadata=_positive_llm_meta(salience=5),
            outcomes=[
                _Outcome(274673061, "James Talarico", 0.25, rank=1),
                _Outcome(274673062, "Sam Altman", 0.20, rank=2),
            ],
        ),
        _Market(
            109435,
            "Will the U.S. confirm that aliens exist?",
            category="tech",
            days_out=400,
            market_tier=2,
            market_metadata=_positive_llm_meta(salience=4),
            outcomes=[
                _Outcome(1094351, "Yes", 0.14, rank=1),
                _Outcome(1094352, "No", 0.86, rank=2),
            ],
        ),
        _Market(
            108326,
            "2028 U.S. Presidential Election winner?",
            category="politics",
            days_out=600,
            market_tier=1,
            market_metadata=_positive_llm_meta(salience=5),
            outcomes=[
                _Outcome(1083261, "Jon Ossoff", 0.19, rank=1),
                _Outcome(1083262, "JD Vance", 0.18, rank=2),
            ],
        ),
    ]
    ids = [m.id for m in non_awards]

    monkeypatch.setenv(DISCOVER_AWARDS_GRAVITY_GATE_ENV, "0")
    before = await _run_score_futures(non_awards, curator_ids=ids)

    monkeypatch.setenv(DISCOVER_AWARDS_GRAVITY_GATE_ENV, "1")
    after = await _run_score_futures(non_awards, curator_ids=ids)

    for m in non_awards:
        assert after[m.id]["score"] == before[m.id]["score"]
        assert after[m.id]["_rank_score"] == before[m.id]["_rank_score"]
        assert after[m.id]["headline"] == before[m.id]["headline"]
        assert after[m.id]["reason"] == before[m.id]["reason"]


def test_admin_score_market_trace_mirrors_deferred_awards_curator_gate(monkeypatch):
    oscar = _Market(
        65814223,
        "Oscars 2027: Best Film Editing Winner",
        days_out=115,
    )

    monkeypatch.setenv(DISCOVER_AWARDS_GRAVITY_GATE_ENV, "1")
    with patch("app.routes.feed._get_cached_interestingness", return_value=None):
        trace_on = _score_market_trace(
            oscar, FROZEN_NOW, source_count=1, is_external_curator_recall=True
        )
    assert trace_on["score_anatomy"]["display"]["external_curator_recall_bonus"] == 0
    assert trace_on["score_anatomy"]["ranking"]["external_curator_recall_bonus"] == 0
    assert "external_curator_recall_deferred_awards" in trace_on["score_anatomy"]["highlight_reasons"]
    assert trace_on["scores"]["final"] == 59

    monkeypatch.setenv(DISCOVER_AWARDS_GRAVITY_GATE_ENV, "0")
    with patch("app.routes.feed._get_cached_interestingness", return_value=None):
        trace_off = _score_market_trace(
            oscar, FROZEN_NOW, source_count=1, is_external_curator_recall=True
        )
    assert (
        trace_off["score_anatomy"]["display"]["external_curator_recall_bonus"]
        == _EXTERNAL_CURATOR_RECALL_SCORE_BONUS
    )
    assert trace_off["scores"]["final"] == 98
