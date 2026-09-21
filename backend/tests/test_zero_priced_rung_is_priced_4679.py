"""#4679 — a rung priced 0% is priced, not unpriced.

`routes/feed.py` read every outcome's price with a TRUTHINESS test, ten times:

    float(o.current_probability) if o.current_probability else None

`0.0` is falsy, so a rung the market genuinely prices at 0% arrived downstream as
`None` — *unpriced* — and `incoherent_ladder_verdict` skips unpriced rungs when
it counts `priced_rungs`. A ladder carrying a real 0% rung was therefore measured
one or more rungs SHORT, and when the short count fell under
`_LADDER_MIN_PRICED_RUNGS` (3) the whole coherence check switched off.

THE PRODUCTION POPULATION, measured 2026-09-21 06:45Z on open, feed-eligible,
Discover-tier markets (`futures_outcomes` grouped by `market_id`):

    market 411     "MVP Winner"              tier 3   1 rung > 0,  71 priced 0.0
    market 10      "FIFA World Cup Winner"   tier 1   2 rungs > 0, 63 priced 0.0
    market 109617  "Eurovision Winner 2026?" tier 1   1 rung > 0,  34 priced 0.0

Each reports `priced_rungs` of 1 or 2 against a floor of 3, so each has its
coherence check switched off by this defect alone.

WHY THE SPECIMEN BELOW IS ATTRIBUTABLE. The floor exists because with two rungs a
reversal is real but UNATTRIBUTABLE — either price could be the wrong one. The
zero rungs do not merely lift the count over the floor, they resolve the
ambiguity: the longest coherent run through `0.55 / 0.80 / 0.0 / 0.0` keeps the
0.55 and both zeros (three rungs) and drops the 0.80, because a run that ends at
0.0 is the one a later rung can still join. That is the verdict the reader was
denied.

THE CONTROL IS THE WHOLE TEST. `test_none_priced_rungs_leave_the_check_off` is
the same ladder with the zero rungs priced `None` instead of `0.0`. It must still
serve the impossible rung as leader. Without it, a guard that dropped incoherent
rungs unconditionally — or that lowered the floor — would pass everything else
here.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.routes.feed import _score_futures
from app.utils.personalization import PersonalizationContext


_FROZEN_NOW = datetime(2026, 9, 21, 12, 0, 0, tzinfo=timezone.utc)


class _Outcome:
    def __init__(self, id, name, prob):
        self.id = id
        self.name = name
        self.external_id = None
        self.current_probability = prob
        self.probability_change_24h = 0.0
        self.opening_probability = None
        self.rank = None
        self.rank_change_24h = None
        self.team_id = None
        self.calibration_probability = None
        self.current_yes_bid = None
        self.current_yes_ask = None


class _Market:
    def __init__(self, id, name, outcomes):
        self.id = id
        self.name = name
        self.source = "kalshi"
        self.external_id = f"kalshi-{id}"
        self.sport_id = None
        self.sport = None
        self.category = "economics"
        self.llm_sport_category = "economics"
        self.market_tier = 1
        self.canonical_market_key = None
        self.group_id = None
        self.group_type = None
        self.image_url = None
        self.hook_description = None
        self.hook_generated_at = None
        self.hook_leader_at_generation = None
        self.market_metadata = {}
        self.curation_score_adj = 0
        self.volume_24h = 250_000
        self.updated_at = _FROZEN_NOW
        self.commence_time = _FROZEN_NOW - timedelta(days=1)
        self.resolution_date = _FROZEN_NOW + timedelta(days=120)
        self.status = "open"
        self.created_at = _FROZEN_NOW - timedelta(days=10)
        self.llm_league = None
        self.llm_gender = None
        self.llm_level = None
        self.outcomes = outcomes


def _market(market_id, name, pairs):
    return _Market(
        market_id,
        name,
        [
            _Outcome(market_id * 10 + n, label, probability)
            for n, (label, probability) in enumerate(pairs)
        ],
    )


def _mock_db(markets):
    db = AsyncMock()

    def make_result(*a, **k):
        result = MagicMock()
        scalars = MagicMock()
        scalars.all.return_value = [m.id for m in markets]
        unique = MagicMock()
        unique.all.return_value = markets
        scalars.unique.return_value = unique
        result.scalars.return_value = scalars
        result.all.return_value = []
        return result

    db.execute = AsyncMock(side_effect=make_result)
    return db


async def _serve_one_futures_card(market):
    """Run the REAL `_score_futures` over one market and return its card data."""
    with (
        patch(
            "app.routes.feed._external_curator_recall_market_ids",
            new=AsyncMock(return_value=[]),
        ),
        patch(
            "app.tasks.redis_state.get_async_redis_client",
            side_effect=Exception("no redis in test"),
        ),
    ):
        items = await _score_futures(
            _mock_db([market]), _FROZEN_NOW, None, PersonalizationContext()
        )
    for item in items:
        if item["type"] == "futures" and item["data"]["id"] == market.id:
            return item["data"]
    return None


def _outcome_names(card):
    return [o["name"] for o in card["top_outcomes"]]


def _probability_of(card, name):
    for outcome in card["top_outcomes"]:
        if outcome["name"] == name:
            return outcome["probability"]
    raise AssertionError(f"{name!r} not on the card: {_outcome_names(card)}")


# The specimen. "Above 20" cannot be likelier than "Above 10" on a cumulative
# ladder, so 0.80 over 0.55 is arithmetic that does not close. The two 0% rungs
# are what carry the priced count from 2 (under the floor, check off) to 4.
LADDER = [
    ("Above 10", 0.55),
    ("Above 20", 0.80),
    ("Above 30", 0.0),
    ("Above 40", 0.0),
]

# The same ladder with the zero rungs genuinely UNPRICED. This is what the
# serializer used to hand downstream for the specimen above, and it must still
# behave the old way — the floor is unchanged and nothing here lowered it.
LADDER_UNPRICED_TAIL = [
    (name, None if probability == 0.0 else probability) for name, probability in LADDER
]


class TestTheZeroRungIsCounted:
    @pytest.mark.asyncio
    async def test_the_impossible_rung_stops_leading_the_card(self):
        card = await _serve_one_futures_card(
            _market(4679001, "Widget shipments in September", LADDER)
        )
        assert card is not None, "the specimen card must still reach the feed"
        assert "Above 20" not in _outcome_names(card), (
            "the 0% rungs carry the priced count over the floor, so the "
            "coherence check runs and drops the rung that cannot be true"
        )
        assert _outcome_names(card)[0] == "Above 10"

    @pytest.mark.asyncio
    async def test_the_printed_number_arrived_with_6195(self):
        """The scope fence came DOWN when #6195 landed, which is what it was for.

        Its predecessor asserted `probability is None` here and said in writing
        that it was a fence and not a behaviour anyone wanted: #4679 fixed what
        the card COUNTS and deliberately left what it PRINTS to #6195, because
        the print sites share `outcome_prints_a_price` with
        `displayed_price_stamp` and moving one without the other re-opens #6256
        (a card dating its age mark from a row rendering `—`). #6195 moved the
        predicate and all three print sites in one change, so the fence has
        nothing left to fence and the assertion is simply inverted.

        Kept rather than deleted because the rung is the same rung: this is now
        the end-to-end statement that a 0% ladder step reaches the reader as a
        NUMBER on the card whose coherence check #4679 taught to count it. The
        two halves of one rung, asserted in one place.
        """
        card = await _serve_one_futures_card(
            _market(4679002, "Widget shipments in September", LADDER)
        )
        assert card is not None
        assert _probability_of(card, "Above 30") == 0.0


class TestTheControls:
    @pytest.mark.asyncio
    async def test_none_priced_rungs_leave_the_check_off(self):
        """The inverse. Genuinely unpriced rungs still do not count."""
        card = await _serve_one_futures_card(
            _market(4679003, "Widget shipments in September", LADDER_UNPRICED_TAIL)
        )
        assert card is not None
        assert "Above 20" in _outcome_names(card), (
            "with only two PRICED rungs the reversal is unattributable and the "
            "floor must still switch the check off — if this fails, the fix "
            "lowered the floor instead of counting the zeros"
        )
        assert _outcome_names(card)[0] == "Above 20"

    @pytest.mark.asyncio
    async def test_an_all_zero_field_is_not_resurrected(self):
        """#921's guard. Counting zeros must not put a dead card back on page one."""
        card = await _serve_one_futures_card(
            _market(
                4679004,
                "Conference Champion",
                [("Chiefs", 0.0), ("Bills", 0.0), ("Eagles", 0.0)],
            )
        )
        assert card is None, "a field with no real price stays suppressed"

    @pytest.mark.asyncio
    async def test_a_dead_field_reads_as_settled(self):
        """The one deliberate suppression change, pinned rather than ridden.

        `all_settled` is `len(probs_available) >= 2 and all(p < 0.05 or p > 0.95)`.
        A field priced `[0.04, 0.0, 0.0]` used to offer it a SINGLE value — the
        zeros arrived as `None` — so the `>= 2` arm was False and a field whose
        every outcome is a long shot kept a live Discover slot, printing a 4%
        leader with nothing beside it. It is now three values, all under 0.05, so
        the field reads as the dead thing it is.

        THE SPECIMEN IS MEASURED, NOT ASSUMED. `[0.96, 0.0, 0.0]` was the obvious
        candidate and is the WRONG one: it is suppressed on both sides of this
        change by a near-certain filter upstream, so a test written on it would
        have asserted nothing. `0.04` is the shape that actually moves — verified
        served on `origin/master` and suppressed here.
        """
        card = await _serve_one_futures_card(
            _market(
                4679005,
                "Conference Champion",
                [("Chiefs", 0.04), ("Bills", 0.0), ("Eagles", 0.0)],
            )
        )
        assert card is None, "a field of long shots is settled, not live"

    @pytest.mark.asyncio
    async def test_an_undecided_field_with_zero_rungs_still_serves(self):
        """The inverse of the one above — the suppression is not a blanket."""
        card = await _serve_one_futures_card(
            _market(
                4679006,
                "Conference Champion",
                [("Chiefs", 0.55), ("Bills", 0.0), ("Eagles", 0.0)],
            )
        )
        assert card is not None, (
            "a live leader keeps the field live however many rungs sit at zero"
        )
        assert _outcome_names(card)[0] == "Chiefs"

    @pytest.mark.asyncio
    async def test_a_zero_rung_never_outranks_a_priced_one(self):
        """The two `else 0` SORT KEYS were deliberately left truthy.

        `0.0` and `0` sort identically, so the sweep had nothing to do there.
        This asserts the ordering it protects rather than the source line.
        """
        card = await _serve_one_futures_card(
            _market(
                4679007,
                "Conference Champion",
                [("Bills", 0.0), ("Chiefs", 0.55), ("Eagles", 0.30)],
            )
        )
        assert card is not None
        assert _outcome_names(card)[0] == "Chiefs"
        assert _outcome_names(card)[-1] == "Bills"
