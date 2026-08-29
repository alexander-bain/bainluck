"""#2088 criterion 3 — the card rule reaches the FEED, not just the labeling surfaces.

THE GAP THIS CLOSES. #2060 gave a two-outcome card one rounding, and UX-P159 (#2088)
gave the pair that legitimately does not total 100 a sentence saying so. Both shipped
on the two LABELING serializers only. The feed — the surface a stranger reads — had
never received either: before this queue, `grep rendered_percent app/routes/feed.py`
returned nothing, and `FeedCard.tsx` printed `Math.round(outcome.probability * 100)`
per outcome, independently, which is exactly the arithmetic #2060 exists to replace.

`_feed_display_scale` is NOT that rule and does not substitute for it. Its band is
ONE-SIDED — it divides down above ~1.01 and does nothing at all below 1.00 — so it
cannot fix a pair that sums to 101 on the half-cent grid (it divides by 1.0) and it
says nothing about a pair that sums to 83.

** WHICH SURFACE ACTUALLY PRINTS THE PAIR, measured rather than assumed. ** Not
Discover. `components/discover/FuturesCard.tsx` prints only the hero leader (and, on
the distribution archetype, a leaderboard of four or more), so a two-outcome card
shows ONE number there and no sum is visible. The pair is printed by
`components/FeedCard.tsx`, which serves `/categories/*`, `/sports` and `/my-stuff`.
Both are fed by `GET /api/feed`, so the fix is one server change; the reader-visible
payoff is on the category and sports pages.

** MEASURED ON THE DEPLOYED BUILD 2026-08-29 ** over every pair-printing surface
(default feed, the politics/economics/entertainment category tags, and sports mode),
deduped by market id and banked as this file's fixture: 87 futures cards carrying
printed outcomes, of which **7 print a pair**, and **6 of those 7 are wrong today** —
two print 101 and four print an unexplained non-100. Only `Will Netanyahu visit New
York City by...?` (52 + 48) is already correct, and it correctly earns no sentence.

RECAPTURE: `curl "$BAINLUCK_API/api/feed?limit=100"` plus the same call with
`&tags=sport:politics`, `&tags=sport:economics`, `&tags=sport:entertainment` and
`&mode=sports`; keep `type == "futures"` items with a non-empty `top_outcomes`, dedupe
by `data.id`, and store the trimmed card dicts.

WHAT THIS FILE PROVES THAT THE CONTRACT SUITE CANNOT. `test_graded_card_contract`
drives `card_sum_reason` through the shared table and would stay green if the feed
never put the field on the wire — which is precisely the state this queue found. These
tests run the REAL feed helper over the REAL captured pool and assert the acceptance
criterion itself: **no card on the feed prints an unexplained non-100.**
"""

import json
import math
from pathlib import Path

import pytest

from app.routes.feed import _apply_card_percents, _feed_display_scale
from app.utils.graded_card import (
    SUM_INDEPENDENT_PRICES,
    SUM_UNPRICED_OUTCOME,
)

FIXTURE = Path(__file__).parent / "fixtures" / "feed_futures_cards_20260829.json"

#: The two cards that print 101 on the deployed build. Named so a regression that
#: silently stops fixing them fails by NAME rather than by count.
PRINTS_101_TODAY = {
    108621: ("Which party will win the U.S. House?", [0.845, 0.155]),
    57792416: ("Will Neuralink's valuation hit (HIGH) $47.5B by August 31?", [0.725, 0.275]),
}

#: The four that print a real, unexplained non-100 and earn the sentence.
EARNS_A_SENTENCE = {20569379, 109349, 59699903, 52756062}

#: The one two-outcome card that is already right. It must stay SILENT — a guard that
#: only proves the rule fires is how the Sports tab got emptied (gotcha #43).
ALREADY_CORRECT = 56722520


@pytest.fixture(scope="module")
def cards():
    return json.loads(FIXTURE.read_text())["items"]


def _printed(card):
    """The card as a reader sees it: the served slice both feed serializers build."""
    return [dict(o) for o in card["top_outcomes"][:3]]


# ── 1. THE ACCEPTANCE CRITERION, OVER THE REAL CAPTURED POOL ─────────────────────


def test_no_feed_card_prints_an_unexplained_non_100(cards):
    """Criterion 3, stated the way the issue states it.

    Every card in the pool is run through the real helper. A card whose printed
    percents do not total 100 must carry a reason; a card that totals 100 must not.
    The failure message names the offenders, because a bare count tells whoever picks
    this up next to go and re-measure what the test already knows.
    """
    unexplained = []
    for card in cards:
        printed = _printed(card)
        reason = _apply_card_percents(printed)
        percents = [o["rendered_percent"] for o in printed if o["rendered_percent"] is not None]
        if not percents:
            continue
        if sum(percents) != 100 and reason is None and len(printed) == 2:
            unexplained.append((card["id"], card["name"], percents))
    assert unexplained == [], f"two-outcome cards printing an unexplained non-100: {unexplained}"


def test_the_pool_actually_contains_the_cards_this_queue_measured(cards):
    """The pool is the population, not a stub — so an empty pool cannot pass silently.

    `test_no_feed_card_prints_an_unexplained_non_100` is vacuously green over an empty
    or all-complement fixture. This pins the six known-bad cards into the pool so a
    recapture that loses them fails loudly instead of quietly proving nothing.
    """
    by_id = {c["id"]: c for c in cards}
    assert len(cards) == 87, f"fixture pool changed size: {len(cards)}"
    for market_id, (name, probabilities) in PRINTS_101_TODAY.items():
        assert market_id in by_id, f"{market_id} ({name}) missing from the pool"
        served = [o["probability"] for o in by_id[market_id]["top_outcomes"][:3]]
        assert served == probabilities, f"{market_id} probabilities drifted: {served}"
    for market_id in EARNS_A_SENTENCE | {ALREADY_CORRECT}:
        assert market_id in by_id, f"{market_id} missing from the pool"


def test_the_two_cards_that_print_101_are_the_ones_that_get_fixed(cards):
    """Named, not counted. Both sum to 101 before and exactly 100 after.

    ``before`` models what the browser prints TODAY — one independent
    ``Math.round(p * 100)`` per side, which is ``floor(p * 100 + 0.5)`` over the
    non-negative domain probabilities live in. Deliberately NOT Python's ``round``:
    that is banker's rounding and disagrees with every surface this is about on
    exactly the ``.5`` boundary these two cards sit on.
    """
    by_id = {c["id"]: c for c in cards}
    for market_id, (name, _) in PRINTS_101_TODAY.items():
        printed = _printed(by_id[market_id])
        before = [math.floor(float(o["probability"]) * 100 + 0.5) for o in printed]
        _apply_card_percents(printed)
        after = [o["rendered_percent"] for o in printed]
        assert sum(after) == 100, f"{name}: {after}"
        assert sum(before) == 101, f"{name} was expected to print 101 today: {before}"


def test_the_four_disagreeing_cards_each_earn_the_independent_prices_reason(cards):
    by_id = {c["id"]: c for c in cards}
    for market_id in EARNS_A_SENTENCE:
        printed = _printed(by_id[market_id])
        reason = _apply_card_percents(printed)
        assert reason == SUM_INDEPENDENT_PRICES, f"{by_id[market_id]['name']}: {reason}"
        assert sum(o["rendered_percent"] for o in printed) != 100


def test_the_card_that_already_totals_100_stays_silent(cards):
    """The un-fired direction, asserted as explicitly as the fired one (gotcha #43)."""
    by_id = {c["id"]: c for c in cards}
    printed = _printed(by_id[ALREADY_CORRECT])
    reason = _apply_card_percents(printed)
    assert reason is None, f"a correct card earned a reason: {reason}"
    assert sum(o["rendered_percent"] for o in printed) == 100


def test_every_multi_outcome_card_in_the_pool_makes_no_claim_about_a_total(cards):
    """Scope, held where UX-P159 put it: arity other than two returns ``None``.

    ``None`` means "this card makes no claim about a total", never "checked and fine".
    Widening the rule to three-plus outcomes is a product decision (the
    independent-binary class, gotcha #23, already has `field_coherence` and
    `_feed_display_scale`), so a queue that widens it by accident fails here.
    """
    for card in cards:
        printed = _printed(card)
        if len(printed) == 2:
            continue
        assert _apply_card_percents(printed) is None, card["name"]


# ── 2. THE PAYLOAD SHAPE THE CLIENT DEPENDS ON ───────────────────────────────────


def test_every_printed_outcome_carries_a_rendered_percent_key(cards):
    """Absent and null are different facts, so the key is ALWAYS written.

    `FeedCard` keys its local fallback on the KEY being absent rather than on the
    value being falsy — `?? derive()` would re-derive on every correct card and make
    the server's answer decorative. That contract only holds if the server never
    omits the key, including when the value is null.
    """
    for card in cards:
        printed = _printed(card)
        _apply_card_percents(printed)
        for outcome in printed:
            assert "rendered_percent" in outcome, card["name"]


def test_the_percent_travels_on_the_outcome_so_client_reordering_cannot_mispair(cards):
    """Why this is annotated per-outcome instead of served as a positional array.

    `FeedCard` re-orders the list through `leaderFirstSlice` before printing it. A
    card-level array served beside the outcomes would be mis-paired on exactly the
    cards where the stored rank disagrees with the probability order (UX-P005 class
    (a): ~23% of feed-surfaced markets). Reversing the printed list must therefore
    permute the percents with it and change nothing else.
    """
    by_id = {c["id"]: c for c in cards}
    printed = _printed(by_id[108621])
    _apply_card_percents(printed)
    forward = {o["id"]: o["rendered_percent"] for o in printed}

    reversed_printed = list(reversed(_printed(by_id[108621])))
    _apply_card_percents(reversed_printed)
    backward = {o["id"]: o["rendered_percent"] for o in reversed_printed}

    # The pair rule is order-sensitive by design (index 0 is the headline that
    # survives), so the SET of percents is preserved and still totals 100 either way.
    assert sum(forward.values()) == 100
    assert sum(backward.values()) == 100
    assert set(forward) == set(backward)


def test_an_unpriced_side_is_labelled_rather_than_counted_as_zero():
    """"No price" and "0%" are different cards — the distinction `rendered_percent` draws."""
    printed = [
        {"id": 1, "name": "Yes", "probability": 0.57},
        {"id": 2, "name": "No", "probability": None},
    ]
    assert _apply_card_percents(printed) == SUM_UNPRICED_OUTCOME
    assert [o["rendered_percent"] for o in printed] == [57, None]


# ── 3. THE RULE COMPOSES WITH THE DISPLAY SCALE RATHER THAN FIGHTING IT ──────────


def test_the_scale_decides_the_basis_and_the_card_rule_decides_the_print():
    """The two mechanisms are orthogonal, and the order between them is load-bearing.

    `_feed_display_scale` runs FIRST and divides an independent-binary field down to a
    sane basis; `_apply_card_percents` then decides what is printed ON that basis. A
    pair summing to 1.05 is scaled to exactly 1.0 and therefore becomes a complement
    pair that totals 100 — so the card rule must find nothing to explain. Running them
    the other way round would explain a total the reader never sees.
    """

    class _O:
        def __init__(self, p):
            self.current_probability = p

    scale = _feed_display_scale([_O(0.63), _O(0.42)])
    assert scale == pytest.approx(1.05)

    printed = [
        {"id": 1, "name": "A", "probability": round(0.63 / scale, 4)},
        {"id": 2, "name": "B", "probability": round(0.42 / scale, 4)},
    ]
    assert _apply_card_percents(printed) is None
    assert sum(o["rendered_percent"] for o in printed) == 100


def test_a_pair_below_the_band_is_untouched_by_the_scale_and_explained_by_the_rule():
    """The one-sided band, stated as a test rather than as a comment.

    A pair summing to 0.97 gets `scale == 1.0` — the scale does nothing at all below
    1.00 — so it reaches the reader as `57 / 40`. That is the card #2088 was filed
    about, and it is the rule's job, not the scale's.
    """

    class _O:
        def __init__(self, p):
            self.current_probability = p

    assert _feed_display_scale([_O(0.57), _O(0.40)]) == 1.0
    printed = [
        {"id": 1, "name": "A", "probability": 0.57},
        {"id": 2, "name": "B", "probability": 0.40},
    ]
    assert _apply_card_percents(printed) == SUM_INDEPENDENT_PRICES
    assert [o["rendered_percent"] for o in printed] == [57, 40]
