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

    def __init__(self, last_updated, current_probability=None):
        self.last_updated = last_updated
        #: #5809 — the fold now picks the legs the CARD PRINTS, so a leg without
        #: a probability is no longer a complete specimen. Left settable rather
        #: than always derived because two tests below turn on rank explicitly.
        self.current_probability = current_probability


class _SnapshotOutcome:
    """An outcome on the WIRE carrier: the observation is a derived int second.

    `price_observed_epoch` and NO `last_updated` — that column is
    `OUTCOME_LOAD_ONLY_EXTRA`, loaded and deliberately not carried, so a rebuilt
    leg genuinely does not have the attribute. Spelled as a separate class
    rather than a flag on `_Outcome` because "has one and it is `None`" and "does
    not have it at all" are different objects and only the second is what
    `from_plain` produces.
    """

    def __init__(self, epoch, current_probability=None):
        self.price_observed_epoch = epoch
        self.current_probability = current_probability


def _printed(*stamps) -> list:
    """THE LEGS THE CARD PRINTS, on the ORM carrier (#5809 completed).

    The helper's argument is no longer a market — it is `card_outcomes[:3]`, the
    same list the serializer builds `top_outcomes_data` from. The window is the
    CALLER's, because only the caller knows it: the printed legs are the top
    three of a filtered list, and no rule applied to a market reproduces that
    set. `test_the_serializers_pass_the_printed_legs` in
    `test_card_displayed_price_age_5809` is where that binding is asserted
    against the route; here the fold is tested over the set it is handed.

    Positional order is still rank-descending, so a fixture reads the way a card
    does even though nothing in the fold sorts any more.
    """
    return [
        _Outcome(stamp, current_probability=0.9 - i / 100)
        for i, stamp in enumerate(stamps)
    ]


def _printed_from_wire(*stamps) -> list:
    """The same legs as they come back off the shared artifact.

    Whole UTC seconds, because that is what the wire carries and what the ORM
    path is truncated to as well — the two carriers must not disagree by a
    microsecond, or the cached feed is a different feed from the direct one.
    """
    return [
        _SnapshotOutcome(
            None if stamp is None else int(stamp.timestamp()),
            current_probability=0.9 - i / 100,
        )
        for i, stamp in enumerate(stamps)
    ]


# ── 1. the fold, on both carriers ───────────────────────────────────────────


def test_ship_orm_carrier_serialises_the_age_of_the_displayed_prices():
    """SHIP: the key exists at all, and it dates the prices the card prints.

    Was `..._serialises_the_newest_poll`, asserting `MAX` over every leg, until
    #5809 measured what that does on a card whose leader is stale: one live card
    in 38 served a stamp newer than EVERY price it displayed, and the 30-minute
    threshold meant the mark drew NOTHING. The rule is now `MIN` over the legs
    the card prints — the only claim all three of them support.
    """
    older = NOW - timedelta(hours=25)
    out = _card_price_observed_at(_printed(older, SIXTY_ONE_MIN, older))
    assert out == older.isoformat()


def test_ship_snapshot_carrier_serialises_the_same_instant():
    """SHIP: a rehydrated card answers the same question, not `None`.

    Mutant this dies to: reading `last_updated` off the legs instead of the
    derived second. Discover's flagship path serves from the shared artifact and
    a rebuilt leg does not HAVE that attribute, so that mutant leaves the age
    absent on exactly the reads that matter most while every ORM-carrier test
    stays green.
    """
    assert _card_price_observed_at(_printed_from_wire(SIXTY_ONE_MIN)) == (
        SIXTY_ONE_MIN.isoformat()
    )


def test_control_the_two_carriers_return_the_identical_string():
    """CONTROL: the cached feed is the same feed, to the character.

    Not implied by the two tests above passing — each could be right about its
    own carrier and disagree in the last digit, which is how a snapshot path
    becomes "a DIFFERENT feed, not a cheaper one". Whole-second truncation on
    BOTH sides is what makes this hold, and this is the assertion that would
    notice it being applied to only one.
    """
    stamps = (NOW - timedelta(hours=25), SIXTY_ONE_MIN, NOW - timedelta(minutes=4))

    assert _card_price_observed_at(_printed(*stamps)) == _card_price_observed_at(
        _printed_from_wire(*stamps)
    )


def test_guard_a_dead_leg_the_card_does_not_show_does_not_date_it():
    """GUARD: the dead leg is excluded by the printed WINDOW, not by `MAX`.

    Measured on production 2026-09-12 over the 76 futures cards a `limit=100`
    feed served: one market's FIFTH-ranked leg was last written 123 DAYS ago
    while its leader was 50 minutes old, and across the 76 the oldest-leg median
    (408m) was more than twice the newest-leg median (170m). Printing "123d ago"
    on a card whose displayed prices are current would be its own defect.

    That measurement is why this guard survives #5809 unchanged in substance —
    and why the fixture changed twice. The leg is FIFTH, so a card that prints
    three never shows it. The original two-leg fixture could not tell "the
    window excluded it" from "`MAX` outvoted it"; and now the window is not the
    fold's at all, so the exclusion is expressed the way production expresses
    it — the fifth leg is simply not in the list handed over.

    Not `oldestSourceStamp` contradicted, then or now — `heroFreshness` states
    the shared rule: max WITHIN a number, min ACROSS facts. #5809 only corrected
    which legs are the facts.
    """
    dead = NOW - timedelta(days=123)
    fresh = NOW - timedelta(minutes=50)
    card = _printed(fresh, fresh, fresh, fresh, dead)[:3]

    assert _card_price_observed_at(card) == fresh.isoformat()


def test_guard_a_dead_leg_the_card_DOES_show_dates_it():
    """The other side of the window, which is the point rather than symmetry.

    If the reader can SEE a price we last observed 123 days ago, saying so is
    the disclosure working. The rule this file shipped hid exactly that, and it
    is the reason #5809 exists.
    """
    dead = NOW - timedelta(days=123)
    fresh = NOW - timedelta(minutes=50)
    card = _printed(fresh, dead, fresh, fresh, fresh)[:3]

    assert _card_price_observed_at(card) == dead.isoformat()


# ── 2. unknown stays unknown ────────────────────────────────────────────────


@pytest.mark.parametrize(
    "market",
    [
        pytest.param([], id="no-printed-legs"),
        pytest.param(_printed(None, None), id="printed-legs-with-no-stamp"),
        pytest.param(_printed_from_wire(None), id="wire-leg-carrying-none"),
        pytest.param([object()], id="a-carrier-with-neither-column"),
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
    out = _card_price_observed_at(_printed(naive))
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
        assert (
            '"price_observed_at": _card_price_observed_at(printed_outcomes)' in block
        )


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
