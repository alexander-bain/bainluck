"""#10165 — the search dropdown stops offering a Polymarket game container.

THE DEFECT, SEEN ON PRODUCTION (2026-10-02 04:45Z, 390px, typing `yankees`).
The dropdown's sixth row read

    New York Yankees vs. Tampa Bay Rays — O/U 6.5 54% · New York Yankees 46%

and tapping it opened `/futures/63612402` as a ranked "field" of unrelated
questions (a runs total, the moneyline, NRFI, four spreads). The row is the
Polymarket EVENT row for ALDS game 1:

    external_id 1113712   group_id polymarket:1113712   event_id 15322539
    mutually_exclusive false   9 outcomes, each keyed on a sub-market's
    condition_id, and each sub-market already its own row on the same group

`/search?q=yankees` withheld it the same minute (#8375, linked arm). The
dropdown never asked. These tests drive the real `typeahead_search` route with
the specimen and a real board in its ranked pool; the control re-runs the same
route with the container read stubbed empty, so the first test measures the
fix and not the rig.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.models import FuturesMarket, FuturesOutcome
from app.routes import events as ev

GROUP = "polymarket:1113712"
CONTAINER_ID = 63612402
EVENT_ID = 15322539
ALCS_BOARD_ID = 61380825

#: The specimen's nine legs as stored on production: (leg name, price,
#: sub-market row id). Each leg's external id is that sub-market's condition id.
LEGS = [
    ("O/U 6.5", 0.540, 63617434),
    ("New York Yankees", 0.455, 63612403),
    ("NRFI", 0.445, 63624776),
    ("O/U 7.5", 0.415, 63617437),
    ("Spread -1.5", 0.355, 63617433),
    ("O/U 8.5", 0.345, 63617438),
    ("Spread -1.5", 0.315, 63617436),
    ("Spread -2.5", 0.255, 63617435),
    ("Spread -2.5", 0.215, 63624779),
]


def _cond(row_id: int) -> str:
    return f"0x{row_id:064x}"


def _outcome(id, name, p, external_id):
    return FuturesOutcome(
        id=id, name=name, current_probability=p, external_id=external_id
    )


def _container() -> FuturesMarket:
    m = FuturesMarket(
        id=CONTAINER_ID,
        source="polymarket",
        external_id="1113712",
        name="New York Yankees vs. Tampa Bay Rays",
        category="championship",
        market_type="field",
        market_tier=5,
        llm_sport_category="baseball",
        group_id=GROUP,
        event_id=EVENT_ID,
        mutually_exclusive=False,
        status="open",
    )
    m.outcomes = [
        _outcome(9000 + i, name, p, _cond(row))
        for i, (name, p, row) in enumerate(LEGS)
    ]
    return m


def _alcs_board() -> FuturesMarket:
    """A real question in the same pool. Yes/No legs whose ids name no row."""
    m = FuturesMarket(
        id=ALCS_BOARD_ID,
        source="polymarket",
        external_id="0xalcs",
        name="Will New York Yankees advance to the ALCS in the 2026 MLB Playoffs?",
        category="championship",
        market_type="container_member",
        market_tier=5,
        llm_sport_category="baseball",
        group_id="polymarket:999001",
        event_id=None,
        mutually_exclusive=False,
        status="open",
    )
    m.outcomes = [
        _outcome(9100, "Yes", 0.54, "0xalcs"),
        _outcome(9101, "No", 0.46, "0xalcs_side1"),
    ]
    return m


#: What `uq_futures_source_external` answers for the container's legs:
#: (id, group_id, external_id), every sub-market on the specimen's own group.
SIBLING_ROWS = [(row, GROUP, _cond(row)) for _, _, row in LEGS]


def _empty_result(rows=()):
    r = MagicMock()
    r.scalars.return_value.all.return_value = []
    r.scalars.return_value.unique.return_value.all.return_value = []
    r.fetchall.return_value = []
    r.all.return_value = list(rows)
    r.scalar.return_value = 0
    r.scalar_one_or_none.return_value = None
    r.first.return_value = None
    r.mappings.return_value.all.return_value = []
    return r


def _db(container_reads: list):
    db = AsyncMock()
    db.begin_nested = AsyncMock(return_value=AsyncMock())

    async def execute(stmt, *a, **k):
        sql = str(stmt).lower()
        # The container read: polymarket rows whose external id is one of the
        # candidates' legs (`_search_container_parent_ids`).
        if (
            "futures_markets.external_id in" in sql
            and "futures_outcomes" not in sql
            and sql.lstrip().startswith("select futures_markets.id, futures_markets.group_id, futures_markets.external_id")
        ):
            container_reads.append(sql)
            return _empty_result(SIBLING_ROWS)
        return _empty_result()

    db.execute = AsyncMock(side_effect=execute)
    return db


async def _typeahead(container_reads: list) -> dict:
    rc = MagicMock()
    rc.get.return_value = None
    request = MagicMock()
    request.headers = {}
    pool = [_container(), _alcs_board()]
    with (
        patch("app.tasks.redis_state.get_redis_client", return_value=rc),
        patch("app.routes.events._record_trending", new=MagicMock()),
        patch(
            "app.routes.events._apply_search_statement_timeout", new=AsyncMock()
        ),
        patch(
            "app.routes.events._rerank_search_futures",
            side_effect=lambda rows, *a, **k: list(pool),
        ),
    ):
        return await ev.typeahead_search(
            q="yankees",
            debug_evidence=False,
            debug_timing=False,
            db=_db(container_reads),
            request=request,
        )


def _futures_ids(payload: dict) -> list:
    return [
        s.get("market_id")
        for s in payload["suggestions"]
        if s.get("type") == "futures"
    ]


@pytest.mark.asyncio
async def test_the_dropdown_withholds_the_alds_container_and_keeps_the_board():
    """🔴 THE SHIP: `yankees` no longer offers 63612402; the real board stays."""
    reads: list = []
    payload = await _typeahead(reads)
    ids = _futures_ids(payload)
    assert CONTAINER_ID not in ids
    assert ALCS_BOARD_ID in ids, "a real question in the same pool must survive"
    assert reads, "the verdict came from the container read, not a short-circuit"


@pytest.mark.asyncio
async def test_control_without_the_container_read_the_specimen_reaches_the_dropdown():
    """The same route with the read stubbed empty serves the container — so the
    test above measures the withholding, not a rig that drops the row anyway."""
    reads: list = []
    with patch(
        "app.routes.events._search_container_parent_ids",
        new=AsyncMock(return_value=set()),
    ):
        payload = await _typeahead(reads)
    ids = _futures_ids(payload)
    assert CONTAINER_ID in ids
    assert ALCS_BOARD_ID in ids
    row = next(s for s in payload["suggestions"] if s.get("market_id") == CONTAINER_ID)
    # The production row's answer: the first two legs of two different questions.
    assert [o["name"] for o in row["top_outcomes"]][:2] == ["O/U 6.5", "New York Yankees"]


@pytest.mark.asyncio
async def test_a_failed_container_read_ships_the_dropdown_unfiltered():
    """Fail-open, the helper's contract on /search: a timed-out read returns the
    empty set and the dropdown is the pre-fix dropdown, never an error."""
    reads: list = []
    with patch(
        "app.routes.events._is_query_timeout", return_value=True
    ), patch.object(ev, "_search_container_parents_among", side_effect=AssertionError):
        original = ev._search_container_parent_ids

        async def timing_out(db, markets, deadline):
            db.execute = AsyncMock(side_effect=RuntimeError("canceling statement"))
            return await original(db, markets, deadline)

        with patch("app.routes.events._search_container_parent_ids", new=timing_out):
            payload = await _typeahead(reads)
    assert CONTAINER_ID in _futures_ids(payload)


def test_the_dropdown_asks_before_the_dedup_key():
    """Withheld before `_admit_search_future`, so the container can never claim
    a dedup key a real row would otherwise take (#8852's ordering)."""
    src = Path(ev.__file__).read_text()
    body = src[src.index("async def typeahead_search("):]
    body = body[: body.index("\n@router.")]
    loop = body[body.index("for market in ta_futures_ranked:"):]
    head = loop[: loop.index("if not _admit_search_future(")]
    assert "if market.id in _ta_container_ids:\n            continue" in head
    before_loop = body[: body.index("for market in ta_futures_ranked:")]
    assert "_search_container_parent_ids(\n        db, ta_futures_ranked, _ta_deadline\n    )" in before_loop
