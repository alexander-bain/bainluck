"""#4160 / #4133 — the ban, proven at the ROUTE, not at the generator.

CERT-2326 BLOCKed the first presentation of this ship and was right. The
generator-only census in `test_feed_reasons_serve_no_diagnostics_4160.py` cannot
see the boundary that actually serves the card: `routes/feed.py` composes

    headline = generate_futures_headline(...) or highlight_result.primary_reason

at THREE sites, and `primary_reason` came off a second label table carrying
"Sources disagree", "Rankings shakeup" and "Multi-source". The bus's falsifier
served an admitted two-source card whose headline AND context_summary were both
the word `Multi-source` — with every generator-level assertion green.

🔴 SO THIS GUARD RUNS `_score_futures` ITSELF and reads the served dict. The
lesson generalises past this issue: **a ban on a producer is not a ban on a
surface.** If a value can reach the reader through an `or`, the guard has to
stand where the `or` is.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.routes.feed import _score_futures
from app.utils.feed_reasons import contains_diagnostic_phrase
from app.utils.futures_highlights import PRIMARY_REASON_LABELS
from app.utils.personalization import PersonalizationContext

#: The card class the falsifier used: carried by two sources, with nothing else
#: to say. `multi_source` is the only signal it can score on, so before the fix
#: every served string on it came from the diagnostic vocabulary.
CANONICAL_KEY = "brazil-presidential-election"


class _Outcome:
    def __init__(self, id, name, probability):
        self.id = id
        self.name = name
        self.external_id = None
        self.current_probability = probability
        self.probability_change_24h = 0.0
        self.opening_probability = None
        self.rank = None
        self.rank_change_24h = None
        self.team_id = None
        self.calibration_probability = None
        self.current_yes_bid = None
        self.current_yes_ask = None


class _Market:
    """A real object so `__dict__.get(...)` reads work, as in #250's harness."""

    def __init__(self, id, *, outcomes):
        now = datetime.now(timezone.utc)
        self.id = id
        self.name = "Brazil Presidential Election"
        self.source = "polymarket"
        self.external_id = f"poly-{id}"
        self.sport_id = None
        self.sport = None
        self.category = "politics"
        self.llm_sport_category = "politics"
        self.market_tier = 1
        # NOT None: this is what makes the card two-source, which is the whole
        # point of the fixture. A None key short-circuits the count to 1.
        self.canonical_market_key = CANONICAL_KEY
        self.group_id = None
        self.group_type = None
        self.image_url = None
        self.hook_description = None
        self.hook_generated_at = None
        self.hook_leader_at_generation = None
        self.market_metadata = {}
        self.curation_score_adj = 0
        self.volume_24h = 250000
        self.updated_at = now
        self.commence_time = now - timedelta(days=1)
        self.resolution_date = now + timedelta(days=30)
        self.status = "open"
        self.created_at = now - timedelta(days=10)
        self.llm_league = None
        self.llm_gender = None
        self.llm_level = None
        self.outcomes = outcomes


def _mock_db(markets):
    db = AsyncMock()

    def make_result(*a, **k):
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


async def _serve(markets, *, source_count: int):
    """Run the real scorer with the canonical source count forced."""
    with (
        patch(
            "app.routes.feed._external_curator_recall_market_ids",
            new=AsyncMock(return_value=[]),
        ),
        patch(
            "app.routes.feed._get_canonical_source_counts",
            new=AsyncMock(return_value={CANONICAL_KEY: source_count}),
        ),
        patch(
            "app.tasks.redis_state.get_async_redis_client",
            side_effect=Exception("no redis in test"),
        ),
    ):
        return await _score_futures(
            _mock_db(markets),
            datetime.now(timezone.utc),
            None,
            PersonalizationContext(),
        )


def _served_strings(item: dict) -> dict[str, str]:
    return {
        "headline": item.get("headline") or "",
        "reason": item.get("reason") or "",
        "context_summary": item.get("context_summary") or "",
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("source_count", [2, 3])
async def test_a_multi_source_card_serves_no_diagnostic_string(source_count):
    """The falsifier's own card, through the real route."""
    market = _Market(
        1,
        outcomes=[
            _Outcome(11, "Luiz Inácio Lula da Silva", 0.52),
            _Outcome(12, "Jair Bolsonaro", 0.31),
        ],
    )
    items = await _serve([market], source_count=source_count)
    futures = [i for i in items if i["type"] == "futures"]

    # The eligible denominator: the card was admitted and scored. Without this,
    # a change that dropped the card would pass this test having proved nothing.
    assert len(futures) == 1, f"the fixture card was not served: {items}"

    offenders = {
        slot: text
        for slot, text in _served_strings(futures[0]).items()
        if contains_diagnostic_phrase(text)
    }
    assert not offenders, f"served at {source_count} sources: {offenders}"


@pytest.mark.asyncio
async def test_a_card_with_nothing_to_say_says_nothing_rather_than_multi_source():
    """The exact shape CERT-2326 served: two sources, no usable outcome.

    Before the repair the headline and the context_summary were both the word
    `Multi-source`, straight off `primary_reason`. It may now be empty — a card
    that can say nothing yields the slot (#4080 clause d) — but it may never be
    a word about our pipeline.
    """
    market = _Market(2, outcomes=[])
    items = await _serve([market], source_count=2)
    futures = [i for i in items if i["type"] == "futures"]

    # This card may legitimately be suppressed. If it IS served, every slot on
    # it must be clean; the assertion is written so neither outcome is vacuous.
    assert len(items) == len(futures), "unexpected non-futures item in the pass"
    for item in futures:
        for slot, text in _served_strings(item).items():
            assert not contains_diagnostic_phrase(text), f"{slot}: {text!r}"
            assert text.strip().lower() != "multi-source", f"{slot} is the old label"


def test_no_scoring_signal_has_a_diagnostic_display_label():
    """The table behind `primary_reason`, read directly.

    Cheap, deterministic, and it names the failure precisely when the next
    signal is given a label describing our machinery instead of the world.
    """
    offenders = [
        (code, label)
        for code, label in PRIMARY_REASON_LABELS
        if contains_diagnostic_phrase(label)
    ]
    assert not offenders, f"primary_reason labels talk about our pipeline: {offenders}"

    # And the table is not empty — a fallback that never fires would pass the
    # assertion above while quietly removing every last-resort label.
    assert len(PRIMARY_REASON_LABELS) >= 6
    assert ("leader_change", "New favorite") in PRIMARY_REASON_LABELS
