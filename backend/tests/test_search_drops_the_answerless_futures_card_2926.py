"""#2926 — a futures card with nothing to say stops taking a slot on /search.

WHAT A READER SAW. `https://bainluck.com/search?q=Europa League` at 390px,
2026-09-13 23:33Z (`artifacts/lane1b-226/europa-league-390.png`). The whole
FUTURES & MARKETS section is three cards whose entire body is the words *"No
outcomes available"* over a freshness pip:

    SOCCER · Championship
    UEFA Europa League: League Phase Most Clean Sheets (Club)
                    No outcomes available
                                                            5d ago

and the ANSWERS card above it prints the literal string `0 outcomes` where the
probability goes, on two of its four rows — one of them market_tier 1, "UEFA
Europa League: League Phase Winner". Alex read the same defect on `?q=rockies`
on 2026-09-09, where every one of the only ANSWERS card's five rows said
`0 outcomes`, and the specimen that opened the issue was `?q=Thun`.

THE POPULATION, measured on production 2026-09-13 over the 37,483 `status='open'`
futures markets, and the second row is the one that decides the predicate:

    zero rows in futures_outcomes                    11,547  (11,539 polymarket)
    rows present, EVERY row a placeholder name            4

WHY THE PREDICATE IS THE FORMATTED LIST AND NOT A ROW COUNT. #2926's own
reproduce SQL asks `NOT EXISTS (futures_outcomes)`. On today's data that is
11,547 of 11,551 — so this is a robustness argument, not a volume one, and it is
made honestly: the extra four are worth almost nothing and the reason to ask the
other question is that a row count answers about the DATABASE while the defect
is about the CARD. Measured across the real row shapes (this is what the route
does today, not what it is assumed to do):

    zero rows .......................................... empty card
    every row a placeholder name ....................... empty card
    rows with no `current_probability` ................. NOT empty — the card
        draws the names with no percentage beside them, which is a different
        defect and deliberately out of this fix's reach
    rows priced off an empty book (bid .01 / ask .99) ... NOT empty — the card
        draws the price

So the set of things that can empty the list is whatever the builder drops, and
the builder is the only honest place to ask. Specimen 60505523 ("UEFA Europa
League: League Phase Most Clean Sheets") is the proof that the two questions
differ: it holds ONE row in the database and `/api/futures/60505523` serves zero.

AND THE SPECIMEN CARRIES A SECOND DEFECT, filed separately rather than fixed
here: its row is named **"AZ"** — AZ Alkmaar, a real Eredivisie club — and
`_BARE_CODE_RE` (`^[A-Z]{1,2}$`, #993 L2-43, written for the Ballon d'Or's
anonymized codes) eats it. Suppressing the card is right either way (the reader
gets nothing from it today), but the card is not the alarm; the issue is.

WHAT THE FIX MUST NOT COST, and the reason a third of this file exists: the same
deduped list feeds the EVENT CONCEPT lane, which derives tournament-page links
from market NAMES and never reads a price. A concept must still be reachable
through a market with no outcomes, or a render fix has quietly deleted
navigation on a different surface.
"""

from __future__ import annotations

import inspect
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.models import FuturesMarket, FuturesOutcome, Sport
from app.routes import events as events_route
from app.routes.events import search_events

SOCCER = Sport(id=11, key="soccer_uefa_europa_league", name="Europa League",
               group="Soccer", active=True)

NOW = datetime(2026, 9, 13, 23, 33, tzinfo=timezone.utc)
FIVE_DAYS_AGO = NOW - timedelta(days=5)

#: The production rows, verbatim (read 2026-09-13 23:33Z).
ANSWERABLE = 59693545          # "Europa League Champion" — 5 real outcomes
EMPTY_WINNER = 60505538        # tier 1, ZERO outcome rows
PLACEHOLDER_ONLY = 60505523    # ONE row, named "AZ" — serves zero
EMPTY_GOALS = 60505525         # ZERO outcome rows
EMPTY_BELGIUM = 59516560       # ZERO outcome rows, the `0 outcomes` ANSWERS row


def _outcome(oid, name, prob, *, bid=None, ask=None):
    return FuturesOutcome(
        id=oid,
        market_id=0,
        external_id=f"0x{oid:064x}",
        name=name,
        current_probability=prob,
        current_american_odds=-110,
        current_yes_bid=bid,
        current_yes_ask=ask,
        probability_change_24h=None,
        rank=1,
        is_winner=False,
        last_updated=FIVE_DAYS_AGO,
    )


def _market(mid, name, outcomes, *, tier=5, volume=1000.0, sport=SOCCER,
            source="polymarket", canonical_market_key=None):
    m = FuturesMarket(
        id=mid,
        source=source,
        external_id=str(mid),
        sport_id=sport.id,
        name=name,
        category="soccer",
        llm_sport_category="soccer",
        market_tier=tier,
        market_type="championship",
        canonical_market_key=canonical_market_key,
        mutually_exclusive=True,
        status="open",
        group_id=f"{source}:{mid}",
        resolution_date=NOW + timedelta(days=200),
        volume_24h=volume,
        created_at=FIVE_DAYS_AGO,
        updated_at=FIVE_DAYS_AGO,
    )
    for o in outcomes:
        o.market_id = mid
    m.outcomes = outcomes
    m.sport = sport
    return m


def _answerable_market():
    """`Europa League Champion` — the one card on that page with an answer."""
    return _market(
        ANSWERABLE,
        "Europa League Champion",
        [
            _outcome(1, "Anderlecht", 0.39),
            _outcome(2, "Aston Villa", 0.21),
            _outcome(3, "AS Roma", 0.14),
            _outcome(4, "Real Betis", 0.09),
            _outcome(5, "Lyon", 0.07),
        ],
        tier=1,
        volume=50000.0,
    )


def _zero_row_markets():
    """The three that hold no `futures_outcomes` row at all."""
    return [
        _market(EMPTY_WINNER, "UEFA Europa League: League Phase Winner", [], tier=1,
                volume=40000.0),
        _market(EMPTY_GOALS, "UEFA Europa League: League Phase Most Goals (Club)", []),
        _market(EMPTY_BELGIUM,
                "Belgium Pro League: Team to qualify for the 2027-28 UEFA Europa League",
                []),
    ]


def _placeholder_only_market():
    """60505523, exactly as production holds it: one row, and it serves zero.

    The row-count guard #2926 proposed keeps this card. See the module docstring
    for the second defect riding on it ("AZ" is a real club).
    """
    return _market(
        PLACEHOLDER_ONLY,
        "UEFA Europa League: League Phase Most Clean Sheets (Club)",
        [_outcome(9, "AZ", 0.495, bid=0.0100, ask=0.9900)],
    )


def _all_empty():
    return [*_zero_row_markets(), _placeholder_only_market()]


# ---------------------------------------------------------------------------
# the predicate itself, on the real row shapes
# ---------------------------------------------------------------------------


def test_a_market_with_no_outcome_rows_has_no_answer():
    for m in _zero_row_markets():
        assert events_route._futures_search_has_answer(m) is False, m.name


def test_the_one_row_specimen_has_no_answer_although_it_has_a_row():
    """🔴 The arm a `NOT EXISTS (futures_outcomes)` guard fails.

    60505523 has one row in the database. Asked the row-count question it is a
    market with outcomes; asked what its card draws, it is a blank.
    """
    m = _placeholder_only_market()
    assert len(m.outcomes) == 1, "the specimen must keep its database row"
    assert events_route._futures_search_has_answer(m) is False


def test_a_market_with_real_prices_has_an_answer():
    assert events_route._futures_search_has_answer(_answerable_market()) is True


def test_an_unpriced_row_is_not_swept_up_by_this_fix():
    """REACH, NOT PURITY. A market whose rows carry no `current_probability`
    still draws its names — a row with no percentage beside it is a different
    defect with a different honest answer, and a suppression rule that reached
    it would delete markets a reader can still read.
    """
    m = _market(1, "UEFA Europa League: Top Scorer",
                [_outcome(9, "Anderlecht", None), _outcome(10, "AS Roma", None)])
    assert events_route._futures_search_has_answer(m) is True


def test_an_empty_book_that_still_carries_a_price_is_not_swept_up_either():
    m = _market(2, "UEFA Europa League: Winner",
                [_outcome(11, "Anderlecht", 0.495, bid=0.01, ask=0.99),
                 _outcome(12, "AS Roma", 0.495, bid=0.01, ask=0.99)])
    assert events_route._futures_search_has_answer(m) is True


def test_the_predicate_asks_the_limit_the_surface_draws():
    """/search draws 5 and /typeahead draws 3; the slice runs before the field
    drop, so the question has to carry the caller's own limit."""
    sig = inspect.signature(events_route._futures_search_has_answer)
    assert "limit" in sig.parameters
    assert sig.parameters["limit"].default == 5


# ---------------------------------------------------------------------------
# the route, driven for real
# ---------------------------------------------------------------------------


def _mock_db(futures_rows):
    db = AsyncMock()

    def make_result(rows):
        r = MagicMock()
        r.scalars.return_value.unique.return_value.all.return_value = rows
        r.scalars.return_value.all.return_value = rows
        r.fetchall.return_value = []
        r.all.return_value = []
        r.scalar.return_value = 0
        r.scalar_one_or_none.return_value = None
        return r

    async def execute(stmt, *a, **k):
        s = str(stmt).lower()
        if "count(" in s:
            return make_result([])
        if "futures_markets" in s:
            return make_result(futures_rows)
        return make_result([])

    db.execute = AsyncMock(side_effect=execute)
    db.begin_nested = AsyncMock(
        return_value=MagicMock(commit=AsyncMock(), rollback=AsyncMock())
    )
    return db


async def _payload(futures_rows, q="europa league"):
    """Drive the real route, as `test_search_twin_fold_5513` does."""
    rc = MagicMock()
    rc.get.return_value = None  # always a cache MISS, so the route does the work

    with (
        patch("app.tasks.redis_state.get_redis_client", return_value=rc),
        patch("app.routes.events._load_gei_percentiles", new=AsyncMock(return_value={})),
        patch("app.routes.events._build_team_lookup", new=AsyncMock(return_value={})),
        patch(
            "app.routes.events.folded_probability_sources_batch",
            new=AsyncMock(return_value={}),
        ),
        patch("app.routes.events._record_trending", new=MagicMock()),
    ):
        return await search_events(
            request=MagicMock(),
            response=MagicMock(),
            q=q,
            db=_mock_db(futures_rows),
            sport=None,
            tags=None,
            page=1,
            per_page=25,
            days_back=30,
            include_upcoming=True,
            debug_timing=False,
            current_user=None,
        )


def _card_ids(payload):
    return [f["id"] for f in payload["futures"]]


def _family_member_ids(payload):
    ids = []
    for fam in payload.get("futures_families") or []:
        h = fam.get("headline")
        if h:
            ids.append(h["id"])
        ids.extend(m["id"] for m in (fam.get("members") or []))
    return ids


@pytest.mark.asyncio
async def test_the_production_page_serves_only_the_card_that_has_an_answer():
    """🔴 THE SHIP. The `?q=Europa League` page, in miniature."""
    payload = await _payload([_answerable_market(), *_all_empty()])

    assert _card_ids(payload) == [ANSWERABLE], (
        "search served a futures card with nothing in it — this is the "
        "production bug: three cards reading 'No outcomes available' took the "
        "whole FUTURES & MARKETS section"
    )


@pytest.mark.asyncio
async def test_no_served_card_is_empty_whatever_the_page_holds():
    """The property, not the specimen: never a card the reader cannot read."""
    payload = await _payload([_answerable_market(), *_all_empty()])
    for card in payload["futures"]:
        assert card["top_outcomes"], f"empty card served: {card['name']!r}"
        assert card["outcome_count"] > 0, (
            f"{card['name']!r} would print the literal string '0 outcomes' "
            "where the probability goes (notice 34 / D102)"
        )


@pytest.mark.asyncio
async def test_the_answers_card_stops_printing_zero_outcomes_as_a_row():
    """The families half — the ANSWERS card Alex read five blank rows in."""
    payload = await _payload([_answerable_market(), *_all_empty()])
    served = set(_family_member_ids(payload))
    for empty in (EMPTY_WINNER, EMPTY_GOALS, EMPTY_BELGIUM, PLACEHOLDER_ONLY):
        assert empty not in served, (
            f"market {empty} is a family row whose probability column prints "
            "'0 outcomes'"
        )


@pytest.mark.asyncio
async def test_a_family_counts_only_markets_a_reader_could_open():
    """`+N more markets below` must not promise blanks (#2646's contract)."""
    payload = await _payload([_answerable_market(), *_all_empty()])
    for fam in payload.get("futures_families") or []:
        shown = 1 if fam.get("headline") else 0
        shown += len(fam.get("members") or [])
        assert fam["member_count"] >= shown
        assert fam["member_count"] <= 1, (
            "the four answerless markets are still being counted into the "
            "family's total, so '+N more markets below' promises N blanks"
        )


@pytest.mark.asyncio
async def test_the_harness_really_can_serve_the_defect():
    """NOT A STRAWMAN. If the plant could never reach the page, every assertion
    above would pass against a route that had not been fixed.

    So: hand the route the same five markets with real prices on them and watch
    all five arrive as cards. The only difference from the ship test is the
    outcome rows — which is exactly the variable under test.
    """
    rows = [_answerable_market()]
    for i, m in enumerate(_all_empty()):
        rows.append(_market(m.id, m.name, [_outcome(500 + i, "Anderlecht", 0.42)]))
    payload = await _payload(rows)

    assert len(_card_ids(payload)) == 5, (
        "the plant cannot reach the futures bucket at all, so the ship test "
        "above proves nothing"
    )


@pytest.mark.asyncio
async def test_an_empty_market_does_not_shadow_its_answerable_twin():
    """The pairing the 11,539 empty Polymarket rows make likely.

    Dedup runs on the volume-reranked list, so the empty row can be the one that
    wins a shared key. Filtering AFTER dedup would then drop both and hide a
    market with real prices behind a blank one.
    """
    key = "soccer::championship:2027"
    empty = _market(70000001, "Europa League Winner", [], volume=90000.0,
                    canonical_market_key=key)
    priced = _market(
        70000002, "Europa League Winner?",
        [_outcome(31, "Anderlecht", 0.39), _outcome(32, "AS Roma", 0.22)],
        volume=10.0, source="kalshi", canonical_market_key=key,
    )
    assert events_route._normalize_futures_dedup_key(empty) == \
        events_route._normalize_futures_dedup_key(priced), (
        "the two specimens must actually collide, or this test is vacuous"
    )

    payload = await _payload([empty, priced])
    assert _card_ids(payload) == [70000002], (
        "the empty row spent the dedup key and took its answerable twin down "
        "with it"
    )


def test_a_concept_is_still_reachable_through_an_answerless_market():
    """WHAT THE FIX MUST NOT COST.

    Event concepts are derived from market NAMES — `derive_soccer_concept` and
    its siblings never read a price — so the concept lane keeps the full deduped
    set. A tournament page must not become unreachable because its winner market
    has no prices today.
    """
    src = inspect.getsource(events_route.search_events)
    assert "for _m in deduped_futures:" in src, (
        "the event-concept lane was switched to the answerable set — a "
        "tournament page is now unreachable whenever its winner market is "
        "unpriced, which is a recall loss wearing a render fix's clothes"
    )
    assert "for _m in answerable_futures:" not in src


# ---------------------------------------------------------------------------
# /typeahead deliberately does NOT take this predicate
# ---------------------------------------------------------------------------


def test_typeahead_is_deliberately_not_filtered():
    """The default in this file is one predicate on both surfaces —
    `_futures_open_now`'s own comment records /search keeping a defect for three
    cycles after /typeahead's twin was fixed. This is the exception, and it is
    pinned so nobody "finishes the job" without reading why.

    #2926 is prose standing where a number belongs: a card whose whole body
    reads "No outcomes available", a family row printing the literal string
    `0 outcomes`. Both of Alex's specimens are that. A dropdown row renders its
    market's NAME, with an answer beside it when there is one — a row without
    one is a title, which is honest navigation and claims nothing false, and
    suppressing it deletes the only path to that market.

    And #4723's pool contract in `tests/integration/test_search_recall_contract`
    is a deploy-blocking statement in the other direction: `_typeahead_pool_seeds`
    seeds outcome-less rows ON PURPOSE, and its Korpatsch control exists to catch
    a pool key that becomes a filter.
    """
    ta = inspect.getsource(events_route.typeahead_search)
    pool = ta[ta.index("futures_pool = []"):]
    pool = pool[: pool.index("event_concept_pool = []")]
    assert "_futures_search_has_answer" not in pool, (
        "the /search predicate was extended into the typeahead pool — that "
        "overrules #4723's deliberately outcome-less pool corpus and deletes "
        "the only navigation path to 11,547 markets. If it is the right call, "
        "it is a decision on #2926 with the recall gate re-argued, not a "
        "consistency tidy-up"
    )
    assert "#2926 STOPS AT /search" in pool, (
        "the reason it stops here must stay next to the code that stops"
    )


# ---------------------------------------------------------------------------
# the route really adopted it
# ---------------------------------------------------------------------------


def test_every_display_consumer_reads_the_answerable_set():
    src = inspect.getsource(events_route.search_events)
    code = "\n".join(
        line for line in src.splitlines() if not line.lstrip().startswith("#")
    )
    assert "futures_markets = answerable_futures[:_SEARCH_FUTURES_PAGE]" in code, (
        "the flat `futures` bucket is sliced off the unfiltered list again"
    )
    assert "_compose_futures_families(\n        answerable_futures," in code, (
        "families are composed from the unfiltered list again — the ANSWERS "
        "card goes back to printing '0 outcomes' rows"
    )
    assert "futures_markets = deduped_futures[" not in code


def test_the_promoted_headline_contender_must_also_have_an_answer():
    """This lane inserts a row ABOVE markets that earned their slot, so an
    answerless promotion is the defect in its worst form."""
    src = inspect.getsource(events_route.search_events)
    code = "\n".join(
        line for line in src.splitlines() if not line.lstrip().startswith("#")
    )
    block = code[code.index("_headline_rows = ["):]
    block = block[: block.index("promote_headline_contenders")]
    assert "_futures_search_has_answer(m)" in block
