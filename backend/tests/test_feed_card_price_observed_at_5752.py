"""#5752 — a futures card on the wire says WHEN its prices were last seen.

## The specimen

`bainluck.com/events/15310026`, the US Open women's final, live, 2026-09-12
20:48Z. The hero said Sabalenka **40%** with a `20s` freshness stamp; two screens
down, under `MORE TENNIS`, the winner market said Sabalenka **59%** with no stamp
at all. A knockout final's winner IS its match winner, so that is one question
with two answers nineteen points apart and nothing telling a reader which is
current.

It was a LAG, not a freeze — re-read in one command, the market repriced to
0.345 against a hero of 34%. Its price was 61 minutes old and had been set 20
minutes before the match started. The number was defensible; the silence was not.

## What was actually missing

Nothing had to be computed. `price_poll_stamp` — `MAX(FuturesOutcome.
last_updated)` — has existed since CERT-949, is loaded on both carriers, and is
already read by the My Stuff scorer. It simply never reached the wire, so the
whole client half of the disclosure was unbuildable and was reported as needing
a producer lane (ux/1222 → `runner-inbox/fable/`, 21:22Z). It needed a key.

## What this file proves, in the order it has to be proven

1. **The fold answers the right question on BOTH carriers.** A market from a
   plain ORM query holds the stamp on its outcomes; one rehydrated from the
   shared snapshot holds it folded on the row and its outcomes carry nothing.
   A caller must not have to know which it holds.
2. **Unknown stays unknown.** A market with no datable price serialises `None`,
   never "now" and never a wrong stamp. `lib/sourceAge`'s "ABSENT IS NOT ZERO":
   a price we have never observed must not read as one observed a moment ago.
3. **The stamp is offset-aware.** A naive isoformat is parsed by the browser as
   LOCAL time, which would age a fresh price by the reader's own UTC offset —
   silently, and by a different amount per reader.
4. **BOTH futures serializers carry the key.** This file exists in the same
   room as three notes recording a column that landed on one of these two dicts
   and missed the other (#1698 `market_type`, CERT-622 `external_id`, #2088
   `card_sum_reason`). A card that discloses its age on Discover but not on the
   `MORE X` rail is the reported defect, not half a fix.

The assertions are labelled the way the frontend half's are:

    SHIP     red against the parent. This is the change.
    GUARD    green against the parent, red against a named mutant.
    CONTROL  green against both.
"""

from __future__ import annotations

import inspect
from datetime import datetime, timedelta, timezone

import pytest

from app.routes import feed as feed_module
from app.routes.feed import _card_price_observed_at


NOW = datetime(2026, 9, 12, 20, 48, tzinfo=timezone.utc)
#: The specimen's own age.
SIXTY_ONE_MIN = NOW - timedelta(minutes=61)


class _Outcome:
    """An outcome on the ORM carrier: the stamp lives in `__dict__`.

    A plain object, not a MagicMock, and deliberately: the production readers
    use `__dict__.get` precisely because `getattr` on a deferred column
    lazy-loads and raises `MissingGreenlet` inside the per-item serializer
    (gotcha #42 — one unloaded column empties the entire futures pool rather
    than dropping one card). A mock answers every attribute and would make a
    `getattr` regression invisible here.
    """

    def __init__(self, last_updated):
        self.last_updated = last_updated


class _Market:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


def _orm_market(*stamps) -> _Market:
    """The carrier `_score_sports_mode_futures` holds: outcomes carry the stamp."""
    return _Market(outcomes=[_Outcome(s) for s in stamps])


def _snapshot_market(folded) -> _Market:
    """The carrier `from_plain` rebuilds: the value is folded onto the row.

    Its outcomes deliberately carry `last_updated=None` — that column is
    `OUTCOME_LOAD_ONLY_EXTRA`, loaded and deliberately NOT on the wire — so a
    reader that re-derived from them here would get `None` off every one.
    """
    return _Market(price_polled_at=folded, outcomes=[_Outcome(None), _Outcome(None)])


# ── 1. the fold, on both carriers ───────────────────────────────────────────


def test_ship_orm_carrier_serialises_the_newest_poll():
    """SHIP: the key exists at all, and it is the freshest stamp on the market."""
    older = NOW - timedelta(hours=25)
    out = _card_price_observed_at(_orm_market(older, SIXTY_ONE_MIN, older))
    assert out == SIXTY_ONE_MIN.isoformat()


def test_ship_snapshot_carrier_serialises_the_folded_value():
    """SHIP: a rehydrated market answers the same question, not `None`.

    Mutant this dies to: re-deriving from `outcomes` instead of reading the
    folded key. Discover's flagship path serves from the shared artifact, so
    that mutant leaves the age absent on exactly the reads that matter most
    while every ORM-carrier test stays green.
    """
    assert _card_price_observed_at(_snapshot_market(SIXTY_ONE_MIN)) == (
        SIXTY_ONE_MIN.isoformat()
    )


def test_guard_a_dead_leg_does_not_date_a_live_card():
    """GUARD: the fold is MAX, not MIN.

    Measured on production 2026-09-12 over the 76 futures cards a `limit=100`
    feed served: one market's fifth-ranked leg was last written 123 DAYS ago
    while its leader was 50 minutes old, and across the 76 the oldest-leg median
    (408m) was more than twice the newest-leg median (170m). Taking the oldest
    would print "123d ago" on a card whose prices are current.

    This is not `oldestSourceStamp`'s rule contradicted — that helper merges
    rows from DIFFERENT sources, where one current contributor must not vouch
    for a stale set. These legs are one market's prices from one poll of one
    venue. `heroFreshness` states it: max WITHIN a number, min ACROSS facts.
    """
    dead = NOW - timedelta(days=123)
    fresh = NOW - timedelta(minutes=50)
    assert _card_price_observed_at(_orm_market(dead, fresh)) == fresh.isoformat()


# ── 2. unknown stays unknown ────────────────────────────────────────────────


@pytest.mark.parametrize(
    "market",
    [
        pytest.param(_Market(outcomes=[]), id="no-outcomes"),
        pytest.param(_orm_market(None, None), id="outcomes-with-no-stamp"),
        pytest.param(_Market(), id="pre-this-build-snapshot-no-outcomes-key"),
        pytest.param(_snapshot_market(None), id="folded-to-none"),
    ],
)
def test_guard_an_undatable_market_serialises_none(market):
    """GUARD: `None`, never a substituted "now".

    Mutant: `or datetime.now(timezone.utc)` anywhere on this path. Every test
    above stays green — they all supply a stamp — and a market we have never
    observed starts telling readers it was priced this second, which is the one
    failure mode a freshness disclosure cannot have.
    """
    assert _card_price_observed_at(market) is None


# ── 3. the stamp is offset-aware ────────────────────────────────────────────


def test_guard_a_naive_stamp_is_serialised_with_an_offset():
    """GUARD: `_utc`, not a bare `.isoformat()`.

    The two carriers hand back stamps that differ in tzinfo — Postgres
    `TIMESTAMP WITHOUT TIME ZONE` arrives naive on one path and the snapshot
    round-trip can restore either. An isoformat with no offset is read by
    `Date.parse` in the browser as LOCAL time, so a price written a minute ago
    would read as hours old or hours in the future depending on where the reader
    is sitting — wrong by a different amount per reader, and invisible to anyone
    testing in UTC.

    Mutant: drop the `_utc(...)` wrapper. Every other test here passes a
    tz-aware datetime and stays green.
    """
    naive = SIXTY_ONE_MIN.replace(tzinfo=None)
    out = _card_price_observed_at(_orm_market(naive))
    assert out is not None
    assert out.endswith("+00:00"), out
    # And it is the SAME instant, not shifted by the fix.
    assert datetime.fromisoformat(out) == SIXTY_ONE_MIN


# ── 4. both serializers carry it ────────────────────────────────────────────


def _futures_data_blocks() -> list[str]:
    """The body of every `futures_data = {` literal in the feed route.

    Read as TEXT because the defect is one no call can see: these two dicts are
    built in two different functions on two different pools, and a fixture
    exercising one says nothing about the other. Sliced to the closing brace at
    the literal's own indentation so a block cannot bleed into the next.
    """
    source = inspect.getsource(feed_module)
    blocks: list[str] = []
    for chunk in source.split("futures_data = {")[1:]:
        # `}` at the indentation of the assignment closes the literal; every
        # nested one is deeper.
        end = chunk.find("\n        }")
        blocks.append(chunk if end == -1 else chunk[:end])
    return blocks


def test_guard_both_futures_serializers_carry_the_key():
    """GUARD: neither dict is the one that keeps quiet.

    Mutant: delete the key from EITHER block. Every unit test above is green —
    they call the helper directly — and one of the two futures surfaces silently
    goes back to serving an undated price.

    Two is asserted, not `>= 1`: if a third serializer appears this test must
    fail and be told about it, which is the only way a fourth note about a
    column landing on one dict and missing the other does not get written.
    """
    blocks = _futures_data_blocks()
    assert len(blocks) == 2, f"expected 2 futures_data literals, found {len(blocks)}"
    for block in blocks:
        assert '"price_observed_at": _card_price_observed_at(market)' in block


def test_control_the_key_is_not_resolution_date_under_a_new_name():
    """CONTROL: the two facts the issue says were confused stay distinct.

    `resolution_date` is when the question gets ANSWERED. Both must be on the
    wire and they must not be the same expression — a "fix" that aliased one to
    the other would satisfy every assertion above about presence.
    """
    for block in _futures_data_blocks():
        assert '"resolution_date": (' in block
        assert '"price_observed_at": market.resolution_date' not in block


# ── MUTATION RUN ────────────────────────────────────────────────────────────
#
# One at a time, baseline 10/10 green before and after each, so every failure is
# attributable to its own mutation.
#
#   B1  fold takes MIN instead of MAX                            KILLED (2)
#   B2  drop the `_utc(...)` wrapper                             KILLED (1)
#   B3  `or datetime.now(timezone.utc)` on the fold              KILLED (4)
#   B4  remove the key from ONE of the two serializers           KILLED (1) —
#       and 0 of the unit tests, which is why the source scan exists
#   B5  re-derive from `outcomes` instead of the folded row key  KILLED (1),
#       the snapshot carrier
#   B6  alias the key to `market.resolution_date`                KILLED (2)
