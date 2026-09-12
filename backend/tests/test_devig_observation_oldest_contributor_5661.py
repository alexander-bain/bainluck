"""#5661 / CERT-2745 — a devigged reading is dated by its OLDEST half.

The first cut of #5661 fixed the call site #4028 missed and stamped it
`source_observation_time(reading.outcome)`. CERT-2745 refused it, correctly, on
the supported two-market devig path:

    a fresh 70% primary at 15:00Z averaged with a stale 60% sibling at 13:00Z
    publishes 65%, `devigged=True`, stamped 15:00Z

— because the new call read only `reading.outcome`. Per-market fetch isolation
is what makes that reachable: the two halves of a devig are fetched separately,
so a partial refresh leaves the group mixed-age, and the mean of a live price
and a dead one is dated by the live one.

It is the SAME over-claim as #4028, one level up, and it matters for the same
downstream reason: the hero's recency decay is RELATIVE to the freshest stamp on
the event, so a composite wearing its fresher half's timestamp cannot be demoted
and instead decays the honest sportsbook against itself.

The rule: **a composite is only as fresh as its stalest contributor.**

These are behavioural, on the real helper and the real reading. The structural
half — that no stamp site in the matcher can go back to the single-row
primitive — is `test_observation_stamp_every_call_site_5661.py`. Neither
subsumes the other: this one proves the helper computes the right instant, that
one proves nobody stops calling it.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.utils.aggregation import oldest_observation_time, source_observation_time

NOW = datetime(2026, 9, 12, 15, 30, tzinfo=timezone.utc)
FRESH = datetime(2026, 9, 12, 15, 0, tzinfo=timezone.utc)
STALE = datetime(2026, 9, 12, 13, 0, tzinfo=timezone.utc)


def _row(last_updated):
    """A duck-typed outcome. This module type-checks nothing else either."""
    return SimpleNamespace(last_updated=last_updated)


def test_devigged_reading_uses_oldest_contributing_observation_5661():
    """The exact specimen CERT-2745 named: 15:00Z primary, 13:00Z sibling."""
    primary, sibling = _row(FRESH), _row(STALE)

    stamped = oldest_observation_time((primary, sibling), now=NOW)

    assert stamped == STALE, (
        "a devigged number must be dated by its STALEST contributor; dating it "
        "by the fresh primary is the CERT-2745 defect — 65% published as if the "
        "whole of it had been seen at 15:00Z when half of it froze at 13:00Z"
    )
    # Order must not decide it. The speaker is first by construction, so a `min`
    # replaced by "the last one" or "the sibling" would pass the assertion above
    # on this input alone.
    assert oldest_observation_time((sibling, primary), now=NOW) == STALE


def test_single_market_control_is_unchanged_5661():
    """The control: one contributor must equal the single-row primitive.

    Without this, "take the oldest" could be satisfied by something that also
    changes the ordinary, overwhelmingly common one-market case — which is 18 of
    the 19 live Polymarket events measured on 2026-09-12.
    """
    only = _row(FRESH)

    assert oldest_observation_time((only,), now=NOW) == source_observation_time(
        only, now=NOW
    ) == FRESH


def test_an_unknown_contributor_abstains_rather_than_guessing_5661():
    """`None` from any contributor means the composite cannot be dated.

    An unknown row is not an old row — it is an unmeasured one. Returning the
    oldest KNOWN time would assert an observation for a row that has none, which
    is the same class of claim as the bug. `None` is the contract
    `source_observation_time` already has: "you have no observation time, use
    your own".
    """
    assert oldest_observation_time((_row(FRESH), _row(None)), now=NOW) is None
    assert oldest_observation_time((_row(None), _row(FRESH)), now=NOW) is None
    assert oldest_observation_time((), now=NOW) is None
    assert oldest_observation_time(None, now=NOW) is None


def test_a_future_contributor_is_clamped_not_trusted_5661():
    """Clock skew must not mint the freshest stamp on the event.

    Inherited from `source_observation_time`, and asserted here because the
    minimum of several rows is a new way to reach it: a composite whose rows are
    all in the future would otherwise date itself ahead of every honest source.
    """
    ahead = _row(NOW + timedelta(hours=2))

    assert oldest_observation_time((ahead,), now=NOW) == NOW
    assert oldest_observation_time((ahead, _row(STALE)), now=NOW) == STALE


class _Outcome:
    """A FuturesOutcome stand-in that also remembers when it was last seen.

    Mirrors `tests/test_live_blend.py::_Outcome` — deliberately, because the
    devig fixture below is that file's `test_two_markets_devig_averages_both_
    sides` with observation times added, and the two must stay recognisably the
    same specimen. `last_updated` is the attribute `source_observation_time`
    reads, and its absence there is why that suite cannot catch this class.
    """

    def __init__(self, name, prob, last_updated=None, rank=None):
        self.name = name
        self.current_probability = prob
        self.current_yes_bid = None
        self.current_yes_ask = None
        self.rank = rank
        self.last_updated = last_updated


class _Market:
    def __init__(self, id, external_id, name, source="kalshi"):
        self.id = id
        self.source = source
        self.external_id = external_id
        self.name = name


def _kalshi_pair(primary_seen, sibling_seen):
    """Kalshi's per-team pair for one game — the supported devig path.

    CERT-2745's specimen exactly: a 70% primary and a 60% sibling, publishing
    65%. The only thing added here is that the two halves were observed at
    different times, which is what a partial refresh produces.
    """
    from app.utils.live_blend import MarketOutcomes

    return [
        MarketOutcomes(
            market=_Market(1, "KXNBAGAME-26AUG30BOSGSW-BOS", "Celtics vs. Warriors"),
            outcomes=[
                _Outcome("Boston Celtics", 0.70, primary_seen),
                _Outcome("Golden State Warriors", 0.30, primary_seen),
            ],
        ),
        MarketOutcomes(
            market=_Market(2, "KXNBAGAME-26AUG30BOSGSW-GSW", "Celtics vs. Warriors"),
            outcomes=[
                _Outcome("Boston Celtics", 0.60, sibling_seen),
                _Outcome("Golden State Warriors", 0.40, sibling_seen),
            ],
        ),
    ]


def test_the_real_devig_path_carries_both_halves_and_dates_by_the_stale_one_5661():
    """Drives `compute_source_home_probability`, not a hand-built reading.

    THIS TEST EXISTS BECAUSE THE FIRST VERSION OF IT DID NOT. The original
    constructed `BlendReading(contributing_outcomes=(primary, sibling))` by hand
    and asserted the helper's arithmetic — which is true and useless: a mutation
    that DISCARDS the sibling row inside the real devig branch survived it,
    because no test ever ran that branch. A fixture that asserts the input it
    was handed is the vacuous shape this file is otherwise written against.

    So: the real function, the real group, and the assertion that the wiring
    reaches the stamp.
    """
    from app.utils.live_blend import compute_source_home_probability

    reading = compute_source_home_probability(
        _kalshi_pair(primary_seen=FRESH, sibling_seen=STALE),
        "Boston Celtics",
        "Golden State Warriors",
    )

    assert reading is not None
    assert reading.devigged is True
    assert abs(reading.home_probability - 0.65) < 1e-9, "the specimen's 65%"

    assert len(reading.contributing_outcomes) == 2, (
        "both halves of a devig moved the number, so both must be carried; "
        "carrying only the speaker is the CERT-2745 defect at its source"
    )
    assert reading.contributing_outcomes[0] is reading.outcome, "speaker first"

    # What the two stamp sites compute. 13:00Z, not the primary's 15:00Z.
    assert oldest_observation_time(
        reading.contributing_outcomes or (reading.outcome,), now=NOW
    ) == STALE


def test_a_single_market_group_is_unchanged_end_to_end_5661():
    """The control, driven the same way: one market, dated by its own row."""
    from app.utils.live_blend import MarketOutcomes, compute_source_home_probability

    group = [
        MarketOutcomes(
            market=_Market(1, "KXNBAGAME-26AUG30BOSGSW-BOS", "Celtics vs. Warriors"),
            outcomes=[
                _Outcome("Boston Celtics", 0.70, FRESH),
                _Outcome("Golden State Warriors", 0.30, FRESH),
            ],
        ),
    ]

    reading = compute_source_home_probability(
        group, "Boston Celtics", "Golden State Warriors"
    )

    assert reading is not None
    assert reading.devigged is False
    assert reading.contributing_outcomes == (reading.outcome,)
    assert oldest_observation_time(
        reading.contributing_outcomes or (reading.outcome,), now=NOW
    ) == FRESH
