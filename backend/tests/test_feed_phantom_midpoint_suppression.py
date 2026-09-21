"""Guard: a price nobody will trade at never reaches a Discover card (#1574, UX-P011).

The pure rule is unit-tested in ``test_feed_market_quality.py``. This file drives the
REAL ``_score_futures`` so the wiring is covered too — the load_only allow-list, the
``group_type`` read, and the placement of the strip BEFORE leader selection. Every book
below is a production row read on 2026-08-07.

Both directions per gotcha #43: the phantom cards go AND the healthy cards stay.
"""

import inspect
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.routes.feed import _score_futures
from app.utils import principal_independent_cache as _pic
from app.utils.feed_market_quality import classify_fabricated_book
from app.utils.market_staleness import is_title_implied_stale
from app.utils.personalization import PersonalizationContext


class _Outcome:
    def __init__(self, id, name, prob, *, bid=None, ask=None):
        self.id = id
        self.name = name
        # Q480: the display path reads `external_id` to drop a `_yes`/`_no`
        # leg that duplicates a bare rung on the same market. None = not a
        # leg, which is the pass-through case for these doubles.
        self.external_id = None
        self.current_probability = prob
        self.probability_change_24h = 0.0
        self.opening_probability = None
        self.rank = None
        self.rank_change_24h = None
        self.team_id = None
        self.calibration_probability = None
        self.current_yes_bid = bid
        self.current_yes_ask = ask


# The instant this file's world is frozen at: midday on the day every book below
# was read off production. NOT derived from the real clock, and there is no
# branch on the clock — see ``_stable_now``.
_FROZEN_NOW = datetime(2026, 8, 7, 12, 0, 0, tzinfo=timezone.utc)


def _stable_now() -> datetime:
    """The frozen capture instant. Reads no clock and branches on nothing.

    Two previous fixes anchored to the real clock and both went red for half of
    every day, in opposite windows. Neither could have worked, because the thing
    that expires here is not an offset — it is the FIXTURE ITSELF.

    The specimens are production rows, and two of them are titled "Week of
    August 3 2026". ``app/utils/market_staleness.infer_market_real_world_end``
    reads that title as a real deadline: implied end 2026-08-03 23:59:59, plus a
    7-day grace, so the scorer starts suppressing the NVIDIA card — correctly —
    the moment the ``now`` it is handed passes **2026-08-10 23:59:59 UTC**.

    That is the whole mechanism. The "red after 12:00 UTC" symptom was the old
    anchor stepping between yesterday-noon (under the deadline) and today-noon
    (past it) — a boundary that only looked like a time-of-day rule on
    2026-08-11, and would have become red 24h/day on 2026-08-12. A fixed-offset
    anchor ("N hours old, with margin") only picks the date the suite dies.

    So the clock is removed from the test instead of tuned: seeds, comparison
    instant, and the dates written in the fixture titles all come from one
    frozen world. ``test_the_fixture_world_is_internally_consistent`` pins that
    invariant so a future edit to either the anchor or a title fails loudly and
    says why, rather than going quietly red half a day later.
    """
    return _FROZEN_NOW


class _Market:
    """A real object (not MagicMock) so ``__dict__.get(...)`` reads work."""

    def __init__(
        self, id, name, category, outcomes, *, group_type=None,
        mutually_exclusive=True,
    ):
        now = _stable_now()
        self.id = id
        self.name = name
        self.source = "polymarket"
        self.external_id = f"poly-{id}"
        self.sport_id = None
        self.sport = None
        self.category = category
        self.llm_sport_category = category
        self.market_tier = 1
        self.canonical_market_key = None
        self.group_id = None
        self.group_type = group_type
        # #7808 half two reads the venue's own exclusivity flag. The model default is
        # True; the two CUMULATIVE LADDERS below carry the production False, which is
        # the only thing keeping "up 200 at 84%" off that clause's radar.
        self.mutually_exclusive = mutually_exclusive
        self.image_url = None
        self.hook_description = None
        self.hook_generated_at = None
        self.hook_leader_at_generation = None
        self.market_metadata = {}
        self.curation_score_adj = 0
        self.volume_24h = 250000
        self.updated_at = now
        self.commence_time = now - timedelta(days=1)
        # Far out so the title-implied staleness calendar can't fire.
        self.resolution_date = now + timedelta(days=120)
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


async def _run(markets):
    # 🔴 EVERY RUN REBUILDS. `_score_futures` round-trips its candidates through
    # the process-wide `market_load` artifact, whose key is a digest of the
    # MARKET IDS alone — so a second `_run` over the same ids in the same process
    # is served the FIRST run's markets and never looks at the fixture it was
    # handed. Measured while writing #7808 half two's guard: the same market id
    # built once with `mutually_exclusive=True` and once with `False` produced
    # byte-identical cards, in whichever order the two ran, and the guard passed
    # against the defect it was written for. Two tests that differ only in a
    # column are the exact shape this file now uses, so the cache is cleared
    # rather than the ids kept artificially distinct — a fixture a test cannot
    # actually vary is a vacuous test, and nothing here wants the sharing.
    _pic.clear_shared_builds("market_load")
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
        now = _stable_now()
        ctx = PersonalizationContext()
        items = await _score_futures(_mock_db(markets), now, None, ctx)
    return items


def _ids(items):
    return {i["data"]["id"] for i in items if i["type"] == "futures"}


def _card(items, market_id):
    for i in items:
        if i["type"] == "futures" and i["data"]["id"] == market_id:
            return i["data"]
    return None


# --- specimens ---------------------------------------------------------------


def _spacex():
    # 57782305: 16 rungs, every book quoted 1c/99c -> a confident-looking 50%.
    outs = [
        _Outcome(1000 + n, f"threshold {n}", 0.5, bid=0.01, ask=0.99)
        for n in range(15)
    ]
    outs.append(_Outcome(1099, "No", 0.5))
    return _Market(
        57782305, "What will SpaceX (SPCX) hit Week of August 3 2026?",
        "economics", outs, group_type="polymarket_event",
        mutually_exclusive=False,
    )


def _oscars():
    # 58492238: five phantoms ranked ABOVE the genuinely-priced 14% leader.
    outs = [
        _Outcome(2001, "Wild Horse Nine", 0.425, bid=0.03, ask=0.82),
        _Outcome(2002, "Digger", 0.425, bid=0.04, ask=0.81),
        _Outcome(2003, "The Black Ball", 0.415, bid=0.02, ask=0.81),
        _Outcome(2004, "Dune: Part Three", 0.355, bid=0.02, ask=0.69),
        _Outcome(2005, "Michael", 0.355, bid=0.03, ask=0.68),
        _Outcome(2006, "The Odyssey", 0.14, bid=0.10, ask=0.18),
        _Outcome(2007, "UNABOMBER", 0.07, bid=0.04, ask=0.10),
        _Outcome(2008, "Being Heumann", 0.065, bid=0.03, ask=0.10),
    ]
    return _Market(
        58492238, "Oscars 2027: Best Casting Winner",
        "entertainment", outs, group_type="negrisk",
    )


def _nvidia():
    # 57782674: a genuinely well-priced CUMULATIVE ladder with ONE bad rung.
    outs = [
        _Outcome(3001, "up 200", 0.845, bid=0.81, ask=0.88),
        _Outcome(3002, "up 204", 0.735, bid=0.48, ask=0.99),   # the phantom
        _Outcome(3003, "down 196", 0.73, bid=0.70, ask=0.76),
        _Outcome(3004, "down 192", 0.465, bid=0.43, ask=0.50),
        _Outcome(3005, "up 208", 0.285, bid=0.25, ask=0.32),
        _Outcome(3006, "down 188", 0.255, bid=0.22, ask=0.29),
    ]
    return _Market(
        57782674, "What will NVIDIA (NVDA) hit Week of August 3 2026?",
        "economics", outs, group_type="polymarket_event",
        mutually_exclusive=False,
    )


def _us_open():
    """61308736 `2027 US Open Men's Singles Winner`, read off production 2026-09-21.

    The #7808 specimen: a Kalshi winner field where the two legs a reader would
    expect to lead are the only two whose stored price sits on their book's
    midpoint. Every book is the production row; the names are the production names.

    ALL 25 LEGS, NOT THE FIVE THE CARD PRINTS (#7808 half two). Half two's clause
    asks two questions of the WHOLE field — does it add up, and does hiding the
    unbid leader make it add up — so a fixture holding only the interesting five
    answers both of them differently from production: those five sum to 1.36 and
    drop to 0.62 without Mensik, where the real field sums to 1.55 and lands on
    0.81. The truncated board would have declined the repair and the guard would
    have passed against the defect. `Valentin Vacherot` carries the real row's
    NULL price and no book at all, which is also the model-price pass-through.
    """
    outs = [
        _Outcome(5001, "Jakub Mensik", 0.74, bid=0.04, ask=0.74),
        _Outcome(5002, "Jannik Sinner", 0.31, bid=0.07, ask=0.55),
        _Outcome(5003, "Carlos Alcaraz", 0.27, bid=0.07, ask=0.47),
        _Outcome(5004, "Casper Ruud", 0.03, bid=0.0, ask=0.57),
        _Outcome(5005, "Andrey Rublev", 0.01, bid=0.0, ask=0.01),
        _Outcome(5006, "Luciano Darderi", 0.01, bid=0.0, ask=0.01),
        _Outcome(5007, "Alexander Zverev", 0.01, bid=0.0, ask=0.74),
        _Outcome(5008, "Felix Auger-Aliassime", 0.01, bid=0.0, ask=0.01),
        _Outcome(5009, "Flavio Cobolli", 0.01, bid=0.0, ask=0.01),
        _Outcome(5010, "Alex de Minaur", 0.01, bid=0.0, ask=0.01),
        _Outcome(5011, "Francisco Cerundolo", 0.01, bid=0.0, ask=0.01),
        _Outcome(5012, "Novak Djokovic", 0.01, bid=0.0, ask=0.19),
        _Outcome(5013, "Daniil Medvedev", 0.01, bid=0.0, ask=0.74),
        _Outcome(5014, "Ben Shelton", 0.01, bid=0.0, ask=0.29),
        _Outcome(5015, "Taylor Fritz", 0.01, bid=0.0, ask=0.74),
        _Outcome(5016, "Arthur Fils", 0.01, bid=0.0, ask=0.74),
        _Outcome(5017, "Frances Tiafoe", 0.01, bid=0.0, ask=0.01),
        _Outcome(5018, "Rafael Jodar", 0.01, bid=0.0, ask=0.74),
        _Outcome(5019, "Lorenzo Musetti", 0.01, bid=0.0, ask=0.01),
        _Outcome(5020, "Learner Tien", 0.01, bid=0.0, ask=0.01),
        _Outcome(5021, "Alexander Bublik", 0.01, bid=0.0, ask=0.01),
        _Outcome(5022, "Brandon Nakashima", 0.01, bid=0.0, ask=0.01),
        _Outcome(5023, "Jiri Lehecka", 0.01, bid=0.0, ask=0.01),
        _Outcome(5024, "Tommy Paul", 0.01, bid=0.0, ask=0.74),
        _Outcome(5025, "Valentin Vacherot", None, bid=None, ask=None),
    ]
    return _Market(
        61308736, "2027 US Open Men's Singles Winner", "tennis", outs,
        group_type="kalshi_event",
    )


def _fed():
    # 20570794: the healthy negRisk control — a tight book that sums to ~100%.
    outs = [
        _Outcome(4001, "No change", 0.56, bid=0.55, ask=0.57),
        _Outcome(4002, "25 bps increase", 0.385, bid=0.37, ask=0.40),
        _Outcome(4003, "25 bps decrease", 0.0605, bid=0.058, ask=0.063),
    ]
    return _Market(
        20570794, "Fed decision in September?", "economics", outs,
        group_type="negrisk",
    )


def _golf():
    # No order book at all (DataGolf model price) — survives by construction.
    outs = [
        _Outcome(5001, "Ben James", 0.842),
        _Outcome(5002, "Doug Ghim", 0.746),
        _Outcome(5003, "Jordan Smith", 0.718),
    ]
    return _Market(58036836, "PGA Championship top 10?", "sports", outs)


# --- suppress ----------------------------------------------------------------


@pytest.mark.asyncio
async def test_spacex_all_fifty_percent_card_never_reaches_the_feed():
    items = await _run([_spacex(), _fed()])
    assert 57782305 not in _ids(items)


@pytest.mark.asyncio
async def test_gapped_exclusive_ladder_never_reaches_the_feed():
    # Alex ruling 2026-08-07: survivors totalling 59.5% are still a gapped partition.
    items = await _run([_oscars(), _fed()])
    assert 58492238 not in _ids(items)


# --- keep (gotcha #43: the flood is capped AND the neighbour stays populated) --


@pytest.mark.asyncio
async def test_healthy_cards_survive_alongside_the_suppressed_ones():
    items = await _run([_spacex(), _oscars(), _fed(), _golf(), _nvidia()])
    ids = _ids(items)
    assert 57782305 not in ids
    assert 58492238 not in ids
    # The whole point of the both-direction guard: the surface stays populated.
    assert 20570794 in ids, "healthy Fed ladder was suppressed"
    assert 58036836 in ids, "model-priced golf field was suppressed"
    assert 57782674 in ids, "healthy NVIDIA ladder was suppressed"


@pytest.mark.asyncio
async def test_nvidia_keeps_its_card_and_its_48c_bid_rung():
    """#7808 moved this one: `up 204` is shown now, and that is the ship.

    It used to assert the opposite. The rung quotes 0.48/0.99 — a 48c buyer — and
    the gate's clause is now "a manufactured midpoint that nobody is bidding for",
    so it survives. Nothing downstream removes it either: against this ladder
    `drop_incoherent_ladder_outcomes` (#4610) keeps 200 -> 204 -> 208 intact, so
    the card prints it monotone between its neighbours instead of gapped over it.
    The manufactured coin flips this file exists for are still refused — see the
    SpaceX and Oscars cards above, both unchanged.
    """
    items = await _run([_nvidia(), _fed()])
    card = _card(items, 57782674)
    assert card is not None
    shown = {o["name"] for o in card["top_outcomes"]}
    assert "up 200" in shown, "the real 0.845 leader was dropped"
    assert "up 204" in shown, "a rung with a 48c buyer was erased from the card"


@pytest.mark.asyncio
async def test_the_us_open_card_names_the_right_favourites():
    """#7808's reader sentence, through the real serializer.

    What production served at 390px on 2026-09-21: "Jakub Mensik 74% · Casper Ruud
    3% · Alexander Zverev 1%" — the 1st, 4th and 5th of the field, with the 2nd and
    3rd erased because their prices sit on their own books' midpoints. The card
    claims to name the most likely; it named the wrong two.

    HALF ONE put Sinner and Alcaraz back. HALF TWO took Mensik off, and the venue
    read is why: his book bids 4c, his 0.74 is one stale fill at an ask that seven
    other men in this same field are quoted at to the cent. So the card the reader
    gets names the only two legs anybody is buying.
    """
    items = await _run([_us_open(), _fed()])
    card = _card(items, 61308736)
    assert card is not None
    printed = [o["name"] for o in card["top_outcomes"]]
    assert printed[:2] == ["Jannik Sinner", "Carlos Alcaraz"]
    assert "Jakub Mensik" not in printed, (
        "the card is naming a favourite whose own book bids 4c"
    )


@pytest.mark.asyncio
async def test_the_us_open_card_is_the_one_the_old_rule_broke():
    """The mutation control for the test above: without #7808's clause the same
    board, through the same serializer, prints the reader's defective card.

    Asserted by calling the unchanged predicate rather than by reasoning about it,
    so this cannot quietly become a restatement of the fix.
    """
    from app.utils.feed_market_quality import is_fabricated_midpoint

    board = _us_open().outcomes
    old_survivors = [
        o.name
        for o in board
        if not is_fabricated_midpoint(
            o.current_probability, o.current_yes_bid, o.current_yes_ask
        )
    ]
    assert old_survivors[:2] == ["Jakub Mensik", "Casper Ruud"]
    assert "Jannik Sinner" not in old_survivors[:5]
    assert "Carlos Alcaraz" not in old_survivors[:5]


@pytest.mark.asyncio
async def test_the_us_open_field_still_adds_up_after_its_leader_leaves():
    """Half two is only allowed to hide a leg if the field it leaves ADDS UP.

    The served card is a probability claim, so this is the assertion that keeps the
    clause from being a way to delete inconvenient legs: the 24 priced legs sum to
    1.55, and the board the reader is left with sums to 0.81 — inside the band this
    module already calls definitional.

    🔴 MEASURED ON THE FIELD, NOT ON THE CARD, and the first version of this test
    got that wrong. A card carries only its `top_outcomes` — three legs — so
    summing what the card renders returned 0.61 and failed a test whose subject was
    never the three printed legs. There is no "whole field" on the card to read, so
    the survivors are taken from the shipped classifier over the same books
    `_score_futures` hands it, and the card is asserted separately to be led by one
    of them. Asserting the card's three legs sum to anything would be a claim about
    the top-3 slice, which is not a probability claim at all.
    """
    outcomes = [
        (o.current_probability, o.current_yes_bid, o.current_yes_ask)
        for o in _us_open().outcomes
    ]
    keep_mask, drop_card = classify_fabricated_book(
        outcomes, is_exclusive=False, field_is_mutually_exclusive=True
    )
    assert not drop_card
    total = sum(
        p for (p, _, _), keep in zip(outcomes, keep_mask) if keep and p is not None
    )
    assert 0.75 <= total <= 1.25, f"the surviving field sums to {total:.2f}"

    items = await _run([_us_open(), _fed()])
    card = _card(items, 61308736)
    assert card is not None
    survivors = {
        o.name
        for o, keep in zip(_us_open().outcomes, keep_mask)
        if keep
    }
    assert card["top_outcomes"][0]["name"] in survivors


#: `Pro Football: 40+ Passing Touchdowns Season` (59165029), every book the
#: production row on 2026-09-21. A NON-exclusive field: several quarterbacks can
#: each throw 40+ touchdowns in the same season, so the legs are independent and
#: their prices legitimately sum to 2.65. Mahomes at 84% with no bid is not a
#: manufactured favourite — he is the likeliest of ten things that can all happen.
_FORTY_TD_LEGS = [
    ("Patrick Mahomes", 0.84, 0.00, 0.85),
    ("Drake Maye", 0.49, 0.00, 0.81),
    ("Joe Burrow", 0.33, 0.00, 0.33),
    ("Jared Goff", 0.245, 0.17, 0.32),
    ("Brock Purdy", 0.20, 0.00, 0.85),
    ("Dak Prescott", 0.15, 0.00, 0.33),
    ("Josh Allen", 0.14, 0.07, 0.21),
    ("Justin Herbert", 0.10, 0.00, 0.85),
    ("Lamar Jackson", 0.08, 0.00, 0.08),
    ("Baker Mayfield", 0.07, 0.00, 0.81),
]


def _forty_touchdowns(*, mutually_exclusive):
    outs = [
        _Outcome(7100 + i, name, p, bid=bid, ask=ask)
        for i, (name, p, bid, ask) in enumerate(_FORTY_TD_LEGS)
    ]
    return _Market(
        59165029, "Pro Football: 40+ Passing Touchdowns Season", "sports", outs,
        group_type="kalshi_event", mutually_exclusive=mutually_exclusive,
    )


@pytest.mark.asyncio
async def test_a_field_whose_legs_can_all_happen_keeps_its_favourite():
    """Half two must not touch a field that is not a field (#7808).

    🔴 WHY THIS SPECIMEN AND NOT A LADDER. The first draft of this guard used an
    invented `Buffalo Total Wins` ladder and asserted its 100% rung survived. It
    could never have failed: a rung ladder reads as `numeric_outcome_ladder`,
    `classify_market_quality` marks it `is_ladder_or_bucket`, and Discover
    suppresses that family outright (the audit target is `ladder/bucket-rate@20=0`),
    so the card was absent from the feed for a reason that had nothing to do with
    this clause. A guard on a card the feed already refuses is green by absence.

    So it is asserted on a field that DOES reach a reader. Measured over the 1,883
    non-exclusive open fields that clear half two's other two guards: on 10 of them
    the clause would hide a leg if the exclusivity flag were ignored, on 6 the flag
    is the ONLY thing declining it, and 4 of those 6 reach a card — this one, the
    abortion-measures card, DeVonta Smith's receiving yards and Latvian relegation
    (`artifacts/d385-7808b/`). Without the flag this card would tell a reader that
    the man likeliest to throw 40 touchdowns is JARED GOFF, at 24%.
    """
    items = await _run([_forty_touchdowns(mutually_exclusive=False), _fed()])
    card = _card(items, 59165029)
    assert card is not None, "the card left the feed"
    assert [o["name"] for o in card["top_outcomes"]][0] == "Patrick Mahomes"


@pytest.mark.asyncio
async def test_that_field_is_only_spared_by_the_exclusivity_flag():
    """The other direction (gotcha #43), and the reason the guard above is not vacuous.

    The identical books with the venue's flag flipped DO get re-led, so the test
    above is pinning the flag and not some other refusal further down the pipeline.
    Both run through the real `_score_futures`, so this also proves `feed.py` reads
    the column through the snapshot round-trip rather than defaulting it.
    """
    items = await _run([_forty_touchdowns(mutually_exclusive=True), _fed()])
    card = _card(items, 59165029)
    assert card is not None
    printed = [o["name"] for o in card["top_outcomes"]]
    assert printed[0] == "Jared Goff", (
        "flipping the venue's exclusivity flag must change this card, or the "
        "guard above is passing for some other reason"
    )
    assert "Patrick Mahomes" not in printed


# --- the anchor invariant (why this file stopped going red half of every day) --


def test_the_fixture_world_is_internally_consistent():
    """The seeds, the comparison instant, and the DATES INSIDE THE TITLES must all
    come from one frozen world.

    Two specimens are titled "Week of August 3 2026" because they are production
    rows. The scorer reads that as a real deadline (implied end 2026-08-03, plus
    7 grace days), so a ``now`` past 2026-08-10 23:59:59 UTC suppresses the
    NVIDIA card for a reason that has nothing to do with phantom midpoints — and
    every assertion below it becomes a lie about a different thing.

    Pinned here, and not left to be rediscovered, because it already cost two
    fixes: both anchored to the real clock, and both were red for half of every
    day in opposite windows.
    """
    assert _stable_now() == _FROZEN_NOW

    for market in (_spacex(), _oscars(), _nvidia(), _fed(), _golf()):
        reason = is_title_implied_stale(
            market.name, market.llm_sport_category, _FROZEN_NOW
        )
        assert reason is None, (
            f"{market.name!r} has expired at the frozen anchor "
            f"({_FROZEN_NOW:%Y-%m-%d %H:%M} UTC, reason={reason}). The scorer will "
            "drop this card on a staleness rule, not on the phantom-midpoint rule "
            "these tests exist to guard. Move _FROZEN_NOW back, or re-capture the "
            "specimen with a title whose implied deadline is later."
        )


def test_the_anchor_reads_no_clock_and_branches_on_nothing():
    """The class this file was the third instance of.

    An anchor that reads the wall clock has a boundary somewhere, and a
    conditional that steps it back is what hides which side of the boundary you
    are on. Gotcha #44 (amended). Source-level so that reintroducing either
    shape fails immediately rather than at whatever hour the boundary sits.
    """
    src = inspect.getsource(_stable_now)
    body = src.split('"""')[-1]  # exclude the docstring, which discusses both
    assert "datetime.now" not in body, "the anchor must not read the wall clock"
    assert "utcnow" not in body, "the anchor must not read the wall clock"
    assert "if " not in body, "the anchor must not branch on the clock"


@pytest.mark.asyncio
async def test_phantoms_are_stripped_before_the_leader_is_chosen():
    """The defect was not only wrong numbers — the phantoms OUTRANKED the real
    prices, so the card named the wrong leader. If the strip ever moves after
    leader selection this goes red while every other test still passes."""
    nvidia = _nvidia()
    items = await _run([nvidia, _fed()])
    card = _card(items, 57782674)
    assert card is not None
    assert card["top_outcomes"][0]["name"] == "up 200"
