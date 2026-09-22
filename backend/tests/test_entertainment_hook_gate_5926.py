"""#5926 — /entertainment stops filling its cards with prose from the retired prompt.

THE READER'S COMPLAINT, from a production screenshot at 15:08Z on 2026-09-13
(`artifacts/5906b-entertainment-scroll1200-1508Z.png`). Every card carried five
to seven lines of narrative ABOVE its probabilities, and the prose was the
dominant element of the card:

    Big Brother Season 28 · Week 10 elimination
    "As tensions rise in the Big Brother house, the impending Week 10
     elimination has fans on edge, with alliances shifting and strategies
     evolving. With only a handful of players left, every vote could
     dramatically alter the dynamics of the game..."

Nothing in our data supports "alliances shifting and strategies evolving".
Another card named people — "emerging favorites like Callum Turner and Edward
B…" — which is verbatim the shape #5461 retired the hook prompt for.

THE THIRD AND LAST UNCONVERTED CALL SITE. ``routes/feed.py`` has gated hooks on
``is_hook_stale`` since ``app/utils/hook_staleness.py`` shipped; ``routes/
futures.py`` adopted it in #5906; this route served ``market.hook_description``
raw. Measured on production the same day: 69 of this endpoint's 112 cards
carried a hook, and of the 11,444 open markets carrying one, **0 are policy 2**.

WHAT WOULD MAKE THIS FILE VACUOUS, stated so a later reader can check it:
a gate that emptied every hook would satisfy every suppression assertion here,
so ``test_a_publishable_hook_survives`` is the control — a policy-2, fresh,
leader-unchanged hook must come through this serializer UNCHANGED.
"""

import itertools
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.routes.entertainment import _market_row
from app.utils.hook_staleness import (
    CURRENT_HOOK_POLICY_VERSION,
    HOOK_POLICY_METADATA_KEY,
)

#: The card production served, verbatim.
_BIG_BROTHER_HOOK = (
    "As tensions rise in the Big Brother house, the impending Week 10 "
    "elimination has fans on edge, with alliances shifting and strategies "
    "evolving."
)


#: #8083: `_market_row` now reads `o.id` for the per-outcome price refusal.
_OUTCOME_IDS = itertools.count(1)


def _outcome(name, prob):
    return SimpleNamespace(
        id=next(_OUTCOME_IDS),
        name=name,
        current_probability=prob,
        probability_change_24h=0.01,
        external_id=None,
    )


def _market(*, hook, generated_at, leader_at_generation, policy_version):
    metadata = None
    if policy_version is not None:
        metadata = {HOOK_POLICY_METADATA_KEY: policy_version}
    return SimpleNamespace(
        id=109281,
        name="Big Brother Season 28 · Week 10 elimination",
        external_id="KXBIGBROTHER-28",
        source="kalshi",
        status="open",
        llm_sport_category="entertainment",
        volume_24h=12000,
        resolution_date=None,
        updated_at=datetime.now(timezone.utc),
        image_url=None,
        hook_description=hook,
        hook_generated_at=generated_at,
        hook_leader_at_generation=leader_at_generation,
        market_metadata=metadata,
        outcomes=[
            _outcome("Melody Morris", 0.53),
            _outcome("Barrett Pfeiffer", 0.43),
            _outcome("Taylor Brown", 0.26),
        ],
    )


class TestEntertainmentHookGate:
    def test_the_big_brother_narrative_is_refused(self):
        market = _market(
            hook=_BIG_BROTHER_HOOK,
            generated_at=datetime.now(timezone.utc) - timedelta(days=40),
            leader_at_generation="Melody Morris",
            policy_version=None,  # policy 1, as all 11,444 production rows are
        )
        row = _market_row(market)

        assert row is not None
        assert row["hook"] is None, (
            "prose from the prompt #5461 retired must not be published here "
            "either"
        )

    def test_a_publishable_hook_survives(self):
        """THE CONTROL. Delete this and the file proves nothing."""
        hook = "Melody Morris leads the Week 10 vote at 53%."
        market = _market(
            hook=hook,
            generated_at=datetime.now(timezone.utc) - timedelta(days=1),
            leader_at_generation="Melody Morris",
            policy_version=CURRENT_HOOK_POLICY_VERSION,
        )
        row = _market_row(market)

        assert row["hook"] == hook

    def test_a_fresh_policy_one_hook_is_refused_on_the_policy_rule_alone(self):
        # Rules 0 and 1 pinned separately — on the futures side a mutation
        # battery found them masking each other, because the natural specimen
        # is both old AND policy 1.
        market = _market(
            hook="Melody Morris leads the Week 10 vote.",
            generated_at=datetime.now(timezone.utc) - timedelta(days=1),
            leader_at_generation="Melody Morris",
            policy_version=None,
        )
        assert _market_row(market)["hook"] is None

    def test_an_aged_policy_two_hook_is_refused_on_the_age_rule_alone(self):
        market = _market(
            hook="Melody Morris leads the Week 10 vote.",
            generated_at=datetime.now(timezone.utc) - timedelta(days=40),
            leader_at_generation="Melody Morris",
            policy_version=CURRENT_HOOK_POLICY_VERSION,
        )
        assert _market_row(market)["hook"] is None

    def test_a_superseded_leader_is_refused(self):
        # Rule 2, through this serializer: `outcomes[0]` genuinely is the leader
        # here (sorted immediately above, and this route withholds no prices),
        # which is the difference from the futures detail page.
        market = _market(
            hook="Barrett Pfeiffer has taken control of the house.",
            generated_at=datetime.now(timezone.utc) - timedelta(days=1),
            leader_at_generation="Barrett Pfeiffer",
            policy_version=CURRENT_HOOK_POLICY_VERSION,
        )
        row = _market_row(market)

        assert row["top_outcomes"][0]["name"] == "Melody Morris"
        assert row["hook"] is None

    def test_a_market_with_no_hook_is_unchanged(self):
        market = _market(
            hook=None,
            generated_at=None,
            leader_at_generation=None,
            policy_version=CURRENT_HOOK_POLICY_VERSION,
        )
        assert _market_row(market)["hook"] is None

    def test_the_rest_of_the_row_is_untouched(self):
        """The gate must change the hook and nothing else.

        This row feeds five card variants on the page; a serializer edit that
        also moved a probability or dropped a key would be a much larger bug
        than the one being fixed.
        """
        market = _market(
            hook=_BIG_BROTHER_HOOK,
            generated_at=datetime.now(timezone.utc) - timedelta(days=40),
            leader_at_generation="Melody Morris",
            policy_version=None,
        )
        row = _market_row(market)

        assert row["q"] == "Big Brother Season 28 · Week 10 elimination"
        assert row["prob"] == 53.0
        assert row["outcome_count"] == 3
        assert [o["name"] for o in row["top_outcomes"]] == [
            "Melody Morris",
            "Barrett Pfeiffer",
            "Taylor Brown",
        ]
        assert row["volume_24h"] == 12000
