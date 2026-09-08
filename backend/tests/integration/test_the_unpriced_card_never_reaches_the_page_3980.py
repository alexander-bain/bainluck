"""#3980 follow-up — the drop through the REAL route, and the filter that makes it safe.

CERT-2284 granted #3980's token and named this file as the owed nonblocking
follow-up, `3980-REAL-ROUTE-PAYLOAD-GUARD`: "add a real `build_league` response
test covering removed, partly priced, and settled cards".

WHY IT WAS OWED. Every one of the nine tests in
`tests/test_an_unpriced_card_is_not_admitted_3980.py` calls `_drawable_sections`
directly; not one goes through `build_league`. The helper is therefore proved and
the WIRING is not. Delete the `is_unpriced_card` call from the route, or hand it
the wrong `now`, and all nine stay green while the Flyweight card walks back onto
`/sport/boxing/boxing`. A guard that cannot see its own ship removed is the class
this repo keeps re-learning, so this file asserts the served PAYLOAD instead.

AND ONE CLAIM THE UNIT FILE MAKES ABOUT A SHAPE THIS ROUTE CANNOT PRODUCE.
`is_unpriced_card` tests settled FIRST, reading `status` off the section row, so
that a finished market keeps its receipts under "settled means settled". At this
surface that branch is unreachable, twice over:

  * `build_league` never serializes `status`. The `market_data` literal in
    `league_futures.py` carries `resolution_date` and no `status` key at all, so
    `_is_settled`'s authoritative path can never fire on a real route row.
  * `_league_scope_filters` already excludes every settled row before one could
    arrive — `status == "open"` AND `resolution_date IS NULL OR >= now`.

That is NOT a defect in the ship: nothing settled is dropped because nothing
settled is present. But it means the retention promise here rests on the QUERY,
not on the predicate, and `test_a_settled_card_keeps_its_receipts` proves its
`status="resolved"` half against a row production cannot hand it. So the settled
coverage the cert asked for is written below as what it honestly is — a guard on
the filter. If someone relaxes `status == "open"`, settled rows start reaching a
predicate that cannot see the field it reads, the drop begins deleting receipts,
and Part 3 goes red to say so before the page does.
"""

from __future__ import annotations

import os
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy import select
from sqlalchemy.dialects import sqlite as sqlite_dialect

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.models import FuturesMarket  # noqa: E402
from app.routes import league_futures as lf  # noqa: E402

NOW = datetime(2026, 9, 8, 19, 0, tzinfo=timezone.utc)

#: `/sport/boxing/boxing` is the page in the issue; `boxing_boxing` is its key.
SPORT_KEY = "boxing_boxing"
CATEGORY = "boxing"


# ---------------------------------------------------------------------------
# Part 1 — the payload, through the real route
# ---------------------------------------------------------------------------


def _outcome(oid: int, name: str, prob):
    """One leg. `prob=None` is the priceless em-dash the issue is about."""
    return SimpleNamespace(
        id=oid,
        name=name,
        current_probability=prob,
        opening_probability=None,
        probability_change_24h=0,
        rank=1,
        team_id=None,
        is_winner=False,
        resolution_source=None,
    )


def _market(*, market_id: int, name: str, prices):
    """A title-family boxing row, priced exactly as `prices` says.

    Mid-band prices on purpose where there ARE prices: `build_league` skips a
    leader >=97% and every all-pinned ladder, and a specimen that vanished down
    THOSE paths would prove nothing about this one.
    """
    return SimpleNamespace(
        id=market_id,
        name=name,
        source="kalshi",
        external_id=f"EXT-{market_id}",
        category="championship",
        llm_sport_category=CATEGORY,
        llm_league=None,
        market_tier=1,
        status="open",
        event_id=None,
        outcomes=[
            _outcome(market_id * 100 + i, f"Fighter {i}", p)
            for i, p in enumerate(prices)
        ],
        # Future-dated, like the real Flyweight card (2027-01-01). A past date
        # would be excluded by the pool query and could never reach the drop.
        resolution_date=NOW + timedelta(days=115),
        canonical_market_key=None,
        group_id=None,
    )


#: The production specimen, reduced to what decides it. Ten returned legs, every
#: one priceless — `outcome_count` 19 is irrelevant to the predicate and is left
#: off deliberately, so the test cannot pass for the wrong reason.
FLYWEIGHT = _market(
    market_id=2951398, name="WBC Flyweight Title on January 1, 2027", prices=[None] * 10
)
#: Jai Opetaia at 60% with five em-dashes under him. One priced leg is enough:
#: the card answers its question and the unpriced legs beneath a real number are
#: #3617(b) working as designed.
CRUISERWEIGHT = _market(
    market_id=2951400, name="WBC Cruiserweight Title", prices=[0.60] + [None] * 9
)
WELTERWEIGHT = _market(
    market_id=2951397, name="WBC Welterweight Title", prices=[0.93] + [None] * 9
)
HEAVYWEIGHT = _market(
    market_id=2951423, name="WBC Heavyweight Title", prices=[0.5] * 10
)


def _scalars_result(items):
    result = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = items
    scalars.unique.return_value = scalars
    result.scalars.return_value = scalars
    return result


def _serve_pool(mock_db, items):
    """Answer the futures-pool query with `items`, everything after it empty.

    The harness cannot evaluate a WHERE clause — it hands back this whole
    population for any statement — which is exactly why the pool query's own
    settled exclusion is tested in Part 3 over a real table instead of here.
    """
    pool, empty = _scalars_result(list(items)), _scalars_result([])
    calls = {"n": 0}

    def _execute(*_args, **_kwargs):
        calls["n"] += 1
        return pool if calls["n"] == 1 else empty

    mock_db.execute.side_effect = _execute


def _served_ids(body: dict) -> list[int]:
    return [row["id"] for rows in body.get("sections", {}).values() for row in rows]


def _served_names(body: dict) -> list[str]:
    return [row["name"] for rows in body.get("sections", {}).values() for row in rows]


class TestTheCardComesOffThePage:
    async def test_the_flyweight_card_is_not_served(self, client, mock_db):
        """The ship, at the surface a reader actually gets.

        RED with the route's `is_unpriced_card` call removed — which is the whole
        reason this file exists, since the unit file stays green through that.
        """
        _serve_pool(mock_db, [FLYWEIGHT])

        body = (await client.get(f"/api/leagues/{SPORT_KEY}")).json()

        assert 2951398 not in _served_ids(body), (
            "the all-priceless card reached the payload; it draws six names, six "
            f"em-dashes and a `+13 more`. sections="
            f"{ {k: len(v) for k, v in body.get('sections', {}).items()} }"
        )

    async def test_a_partly_priced_card_is_still_served(self, client, mock_db):
        """Retention. A remedy that also deletes the priced cards is not a remedy."""
        _serve_pool(mock_db, [CRUISERWEIGHT])

        body = (await client.get(f"/api/leagues/{SPORT_KEY}")).json()

        assert 2951400 in _served_ids(body), (
            "Opetaia at 60% answers his card's question; the nine em-dashes under "
            "him are #3617(b) working, not an absence"
        )

    async def test_the_real_boxing_section_loses_exactly_one_row(self, client, mock_db):
        """The whole section as production served it, in order.

        Order is asserted because a filter that reorders a ranked rail is a
        different bug arriving with the fix.
        """
        _serve_pool(mock_db, [HEAVYWEIGHT, FLYWEIGHT, CRUISERWEIGHT, WELTERWEIGHT])

        body = (await client.get(f"/api/leagues/{SPORT_KEY}")).json()

        assert _served_ids(body) == [2951423, 2951400, 2951397]

    async def test_the_envelope_stops_claiming_the_card_was_shown(
        self, client, mock_db
    ):
        """`shown + dropped == total`, declared per served section.

        `shown` exceeding what `sections` holds is the arithmetic impossibility
        that started this family of issues (ruling 025 clause 3): a swallow that
        counts is detection, a swallow that doesn't is concealment.

        The dropped card is declared under `dropped`, NOT under a key of its own:
        the served envelope names `no_outcomes` separately and folds the unpriced
        count into `dropped` alongside the price skip. Asserted as the balance
        rather than as a key, because the balance is the property a reader can be
        harmed by and the key name is not.
        """
        _serve_pool(mock_db, [HEAVYWEIGHT, FLYWEIGHT])

        body = (await client.get(f"/api/leagues/{SPORT_KEY}")).json()
        counts = body.get("section_counts", {})
        served_per_section = {
            name: len(rows) for name, rows in body.get("sections", {}).items()
        }

        assert served_per_section, f"nothing was served at all; body keys={list(body)}"

        for name, n_served in served_per_section.items():
            c = counts.get(name, {})
            assert c.get("shown") == n_served, (
                f"section {name!r} claims shown={c.get('shown')} over {n_served} "
                f"served rows — the over-claim #3964 and #3980 both close; "
                f"section_counts={counts}"
            )
            assert c.get("shown", 0) + c.get("dropped", 0) == c.get(
                "total"
            ), f"section {name!r} does not balance: {c}"
            assert c.get("dropped", 0) >= 1, (
                "the Flyweight card came off and must be ACCOUNTED for, never "
                f"silently absent; section_counts={counts}"
            )


class TestTheWiringItself:
    """The half the unit file structurally cannot reach."""

    async def test_the_route_hands_the_predicate_a_real_now(self, client, mock_db):
        """`now` must be the request's clock, not a default or a None.

        `_is_settled` compares `resolution_date` against it, so a route passing
        the wrong `now` would mis-sort settled from live silently. Asserted by
        observing that a future-dated priceless card is dropped (live, so
        unpriced) while the call is made at all — a `now` of None raises inside
        the comparison and this reddens rather than 500-ing quietly.
        """
        _serve_pool(mock_db, [FLYWEIGHT])

        response = await client.get(f"/api/leagues/{SPORT_KEY}")

        assert response.status_code == 200, response.text
        assert 2951398 not in _served_ids(response.json())

    async def test_one_bad_row_does_not_zero_the_section(self, client, mock_db):
        """gotcha #42 — one item's fate must never decide another's."""
        _serve_pool(mock_db, [FLYWEIGHT, HEAVYWEIGHT])

        body = (await client.get(f"/api/leagues/{SPORT_KEY}")).json()

        assert "WBC Heavyweight Title" in _served_names(body)


# ---------------------------------------------------------------------------
# Part 3 — the settled exclusion, as a real statement over a real table
# ---------------------------------------------------------------------------
#
# Compiled with literal binds and executed over sqlite for the reason
# `test_league_tournament_winners_2698.py` gives: the route's mocked-db harness
# hands back its whole fixture population for any `futures_markets` statement and
# cannot evaluate a WHERE clause, so a filter test built on it would pass just as
# happily with the filter deleted.

_COLUMNS = (
    "id",
    "external_id",
    "name",
    "status",
    "resolution_date",
    "llm_sport_category",
    "llm_league",
    "market_tier",
    "event_id",
)

PAST = (NOW - timedelta(days=3)).isoformat()
SOON = (NOW + timedelta(days=20)).isoformat()

#: id, name, status, resolution_date — every way a boxing title row can be
#: settled or live, otherwise identical.
#:
#: The names all carry `WBC` deliberately. Boxing's scope clause is not just the
#: category: it also demands a sanctioned ticker or title string
#: (`KXBOXING%`, `KXWBC%`, `%Boxing%`, `%WBC%`, `%WBA%`, `%IBF%`, `%WBO%`) and
#: rejects `% at %`. A row that failed THAT clause would be excluded for the
#: wrong reason and this file would report a settled exclusion it never proved.
LIVE_ROW = "WBC Flyweight Title, live and future dated"
SCOPE_ROWS = [
    (1, LIVE_ROW, "open", SOON),
    (2, "WBC Cruiserweight Title, settled by status", "settled", SOON),
    (3, "WBC Welterweight Title, resolved by status", "resolved", SOON),
    (4, "WBC Heavyweight Title, closed by status", "closed", SOON),
    (5, "WBC Bantamweight Title, live but already past its date", "open", PAST),
]


@pytest.fixture()
def table():
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE futures_markets ("
        "id INTEGER PRIMARY KEY, external_id TEXT, name TEXT, status TEXT, "
        "resolution_date TEXT, llm_sport_category TEXT, llm_league TEXT, "
        "market_tier INTEGER, event_id INTEGER)"
    )
    conn.executemany(
        f"INSERT INTO futures_markets ({','.join(_COLUMNS)}) "
        f"VALUES ({','.join('?' * len(_COLUMNS))})",
        [
            (mid, f"EXT-{mid}", name, status, date, CATEGORY, None, 1, None)
            for mid, name, status, date in SCOPE_ROWS
        ],
    )
    conn.commit()
    try:
        yield conn
    finally:
        conn.close()


def _selected(conn) -> set[str]:
    """Run the REAL scope clause over the table and return what it selected."""
    statement = select(FuturesMarket.name).where(
        *lf._league_scope_filters(SPORT_KEY, NOW)
    )
    sql = str(
        statement.compile(
            dialect=sqlite_dialect.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )
    return {name for (name,) in conn.execute(sql).fetchall()}


class TestWhySettledNeverMeetsTheDrop:
    """The dependency the retention promise actually rests on at this surface."""

    def test_no_settled_row_reaches_the_route_at_all(self, table):
        """Both exclusions, stated as one fact about the served population.

        This is the settled coverage CERT-2284 asked for, written where the
        behaviour lives. `is_unpriced_card`'s settled branch cannot protect a
        route row — `build_league` does not serialize `status` — so what keeps a
        finished market's receipts here is this clause and nothing else.
        """
        selected = _selected(table)

        assert selected == {LIVE_ROW}, (
            "a settled row entered the pool. The unpriced drop downstream reads "
            "`status` off a section row that never carries it, so such a row "
            "would be dropped as priceless and its receipts deleted, against "
            "'settled means settled'. Re-home the settled test before relaxing "
            f"this filter. selected={sorted(selected)}"
        )

    def test_the_past_dated_row_is_the_one_that_would_have_been_safe(self, table):
        """The half that IS serialized, kept honest.

        `resolution_date` DOES travel in the payload, so had a past-dated row
        reached `_drawable_sections` the predicate would have caught it. It never
        arrives — the same clause excludes it — which is why the unit file's
        `by_date` case is also unreachable here, harmlessly.
        """
        assert "WBC Bantamweight Title, live but already past its date" not in (
            _selected(table)
        )
