"""#7382 — the `/entertainment` trending rows carry up to six priced rungs.

At 1280px the lead hero card spans both grid rows (421px, set by the two side
cards stacked beside it) and printed three rungs under a 196px blank band
(production read 2026-10-22 03:52Z, "Oscar Winner: Best Picture", 41 outcomes).
The page already asked for a fourth rung on the lead; the payload never carried
one, because the trending rows were built at `_market_row`'s default
`max_outcomes=3`. They are now built at 6, so the desktop lead can show more of
its own priced field. The page keeps side cards and narrow widths at three.

What must NOT move with it, and is pinned here:

* the rungs are still the priced, non-withheld legs in price order (#6255,
  #8083) — six is a ceiling, never a pad;
* `outcome_count`, `prob`, `kind` and the headline are slice-independent, so
  `_score_for_trending` sees the same rows and the same markets trend;
* the theme sections keep their own slices.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.routes import entertainment as ent

FIXED_NOW = datetime(2026, 10, 22, 3, 52, 0, tzinfo=timezone.utc)
FRESH = FIXED_NOW - timedelta(minutes=20)


def _leg(idx, name, prob):
    return SimpleNamespace(
        id=idx, name=name, current_probability=prob, rank=idx, last_updated=FRESH,
        is_winner=False, resolution_source=None, probability_change_24h=None,
        previous_probability=None,
    )


def _market(mid, ext, name, legs, *, category="entertainment"):
    return SimpleNamespace(
        id=mid, name=name, source="kalshi", external_id=ext, outcomes=legs,
        status="open", llm_sport_category=category, group_id=None,
        volume=100_000, volume_24h=59_000,
        resolution_date=datetime(2027, 12, 31, tzinfo=timezone.utc),
        market_metadata=None, image_url=None, hook_description=None,
        market_tier=2, event_id=None, updated_at=FRESH, created_at=FRESH,
    )


#: The production lead's top of field (`KXOSCARPIC-27`, read 2026-10-22 04:08Z
#: from `/api/futures/6173044`), with an UNPRICED leg and a WITHHELD leg placed
#: inside the six-slot window so the ceiling cannot be met by padding.
OSCAR_LEGS = [
    _leg(101, "The Odyssey", 0.455),
    _leg(102, "You Can See Everything", 0.245),
    _leg(103, "The Black Ball", 0.165),
    _leg(104, "Dune: Part Three", 0.095),
    _leg(105, "Unpriced Picture", None),
    _leg(106, "Withheld Picture", 0.04),
    _leg(107, "Wild Horse Nine", 0.025),
    _leg(108, "Artificial", 0.015),
    _leg(109, "Eighth Priced", 0.01),
    _leg(110, "Ninth Priced", 0.005),
]
WITHHELD = {106}


def oscar():
    return _market(6173044, "KXOSCARPIC-27", "Oscar Winner: Best Picture", list(OSCAR_LEGS))


def four_way():
    return _market(
        108264, "KXSPEED-100M", "When will IShowSpeed reach 100 million Youtube subscribers?",
        [_leg(201, "A", 0.40), _leg(202, "B", 0.30), _leg(203, "C", 0.20), _leg(204, "D", 0.10)],
    )


def binary():
    return _market(56775492, "KXBRADYWWE-28", "Tom Brady to fight in the WWE before 2028",
                   [_leg(301, "Yes", 0.50)])


def _db(markets):
    result_obj = MagicMock()
    result_obj.scalars.return_value.unique.return_value.all.return_value = list(markets)
    db = MagicMock()
    db.execute = AsyncMock(return_value=result_obj)
    return db


async def _entertainment(markets, withheld=frozenset()):
    with patch("app.routes.entertainment.datetime") as dt, \
            patch.object(ent, "_withheld_price_outcome_ids",
                         AsyncMock(return_value=set(withheld))):
        dt.now.return_value = FIXED_NOW
        return await ent.get_entertainment(_db(markets))


def _trending(payload, market_id):
    rows = [r for r in payload["trending"] if r["market_id"] == market_id]
    assert len(rows) == 1, f"{market_id} not served once in trending: {payload['trending']}"
    return rows[0]


@pytest.mark.asyncio
class TestTrendingRowsCarrySixPricedRungs:
    async def test_a_wide_field_serves_its_six_priced_rungs_in_price_order(self):
        payload = await _entertainment([oscar(), four_way(), binary()], WITHHELD)
        row = _trending(payload, 6173044)
        assert [o["name"] for o in row["top_outcomes"]] == [
            "The Odyssey", "You Can See Everything", "The Black Ball",
            "Dune: Part Three", "Wild Horse Nine", "Artificial",
        ]
        assert [o["prob"] for o in row["top_outcomes"]] == [45.5, 24.5, 16.5, 9.5, 2.5, 1.5]
        # Arity is the ladder's, not the slice's.
        assert row["outcome_count"] == len(OSCAR_LEGS)

    async def test_the_unpriced_and_withheld_legs_never_fill_a_slot(self):
        payload = await _entertainment([oscar(), four_way(), binary()], WITHHELD)
        names = {o["name"] for o in _trending(payload, 6173044)["top_outcomes"]}
        assert "Unpriced Picture" not in names
        assert "Withheld Picture" not in names

    async def test_six_is_a_ceiling_never_a_pad(self):
        payload = await _entertainment([oscar(), four_way(), binary()], WITHHELD)
        assert len(_trending(payload, 108264)["top_outcomes"]) == 4
        assert len(_trending(payload, 56775492)["top_outcomes"]) == 1


class TestTheSliceMovesNothingTrendingRanksOn:
    """The selection is a function of fields the slice never touches."""

    def test_every_field_but_the_rungs_is_slice_independent(self):
        for m in (oscar(), four_way(), binary()):
            three = ent._market_row(m, withheld_ids=WITHHELD)
            six = ent._market_row(m, max_outcomes=6, withheld_ids=WITHHELD)
            assert {k: v for k, v in three.items() if k != "top_outcomes"} == {
                k: v for k, v in six.items() if k != "top_outcomes"
            }
            assert six["top_outcomes"][: len(three["top_outcomes"])] == three["top_outcomes"]

    def test_the_same_markets_trend_in_the_same_order(self):
        markets = [oscar(), four_way(), binary()]
        three = [ent._market_row(m, withheld_ids=WITHHELD) for m in markets]
        six = [ent._market_row(m, max_outcomes=6, withheld_ids=WITHHELD) for m in markets]
        assert [r["market_id"] for r in ent._build_trending(three)] == [
            r["market_id"] for r in ent._build_trending(six)
        ]


@pytest.mark.asyncio
class TestTheSectionsKeepTheirOwnSlices:
    async def test_the_same_markets_outside_trending_still_carry_three(self):
        """The widened list is trending's alone.

        On this fixture the Oscar field is ALSO served in `cultural_moments` and
        the four-way in `themes.tech_culture` — both built at the default three.
        A widened default (rather than the trending call) reddens here.
        """
        payload = await _entertainment([oscar(), four_way(), binary()], WITHHELD)
        cultural = [r for r in payload["cultural_moments"] if r["market_id"] == 6173044]
        tech = [r for r in payload["themes"]["tech_culture"]["markets"]
                if r["market_id"] == 108264]
        assert len(cultural) == 1 and len(tech) == 1, "fixture no longer reaches both sections"
        assert len(cultural[0]["top_outcomes"]) == 3
        assert len(tech[0]["top_outcomes"]) == 3
        # ...while the same two markets carry more in trending.
        assert len(_trending(payload, 6173044)["top_outcomes"]) == 6
        assert len(_trending(payload, 108264)["top_outcomes"]) == 4
