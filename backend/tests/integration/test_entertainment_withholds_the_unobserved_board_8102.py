"""#8102 — /entertainment carries #8011's unobserved-board arm, not just five.

WHAT A READER SAW. After #8083 shipped, `/entertainment` still heroed
**Doug 92.5%** for *Who will win The Bachelorette Season 22?* while
`/api/futures/1154050` served `prices_withheld: 22`, every leg `null`, in the
same minute — outcome rows last moved 2026-03-19. Tapping the card landed on
"No prices in the last 30 days" with no outcomes at all.

WHY #8083 DID NOT REACH IT. `_withheld_price_outcome_ids` composes FIVE arms.
The refusal a reader actually meets on the detail page is that union PLUS
#8011's unobserved-board arm, which `get_futures_market` adds outside the
helper because `_format_market_detail` is sync and holds no session to read the
fleet stamp with. The helper is therefore a strict SUBSET of the detail page's
refusal, and #8083 inherited the gap. Measured over the full served population
at 22:26Z: 5 of 109 markets still republished a withheld price, 15 outcome rows.

WHAT THIS FILE PINS. The sixth arm is wired AT THE ROUTE, decided by the real
`unobserved_board_keys`, and every absence it causes is known to be its doing:
the five-arm helper is mocked to withhold NOTHING throughout, so anything that
disappears here disappeared because the board is unobserved and for no other
reason.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.routes import entertainment as entertainment_module

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Mocks — the shared idiom from the #8083 file
# ---------------------------------------------------------------------------


class _MockScalars:
    def __init__(self, items):
        self._items = items

    def all(self):
        return self._items

    def first(self):
        return self._items[0] if self._items else None

    def unique(self):
        return self


class _MockResult:
    def __init__(self, items):
        self._items = items

    def scalars(self):
        return _MockScalars(self._items)

    def all(self):
        return self._items

    def first(self):
        return self._items[0] if self._items else None


NOW = datetime.now(timezone.utc)

#: Comfortably past `BOARD_UNOBSERVED_DAYS` (30) on BOTH clauses the arm tests —
#: the leg stamps and the parent's poller stamp — because either alone is
#: measured unsound and the arm requires both.
DEAD_AGE = timedelta(days=190)


def _outcome(outcome_id, name, probability, last_updated):
    return SimpleNamespace(
        id=outcome_id,
        name=name,
        current_probability=probability,
        probability_change_24h=0,
        rank=1,
        # Ungraded on purpose: a board carrying a verdict is a RESULT and the
        # arm exempts it by design, so a graded fake would make every
        # assertion below pass for the wrong reason.
        is_winner=None,
        resolution_source=None,
        last_updated=last_updated,
    )


def _market(*, market_id, name, outcomes, updated_at):
    """Three outcomes, so `_is_interesting` does not drop the card for arity.

    `updated_at` is the parent poller stamp the arm's second clause reads; it
    is a parameter rather than NOW because the two clauses must be moved
    together to change the verdict.
    """
    return SimpleNamespace(
        id=market_id,
        name=name,
        external_id=f"mock{market_id}",
        source="kalshi",
        category="news",
        llm_sport_category="entertainment",
        outcomes=outcomes,
        market_metadata=None,
        resolution_date=NOW + timedelta(days=30),
        updated_at=updated_at,
        volume_24h=1000,
        image_url=None,
        hook_description=None,
        status="open",
    )


# ---------------------------------------------------------------------------
# The fixture — an unobserved board and a live control
# ---------------------------------------------------------------------------

DEAD_ID = 800
DEAD_LEGS_NAMES = ("Doug", "Shane", "Lew")

LIVE_ID = 810
LIVE_LEG_NAMES = ("Live leader", "Live second", "Live third")


def _dead_board(age=DEAD_AGE):
    stamp = NOW - age
    return _market(
        market_id=DEAD_ID,
        name="Who will win the reality series this season?",
        outcomes=[
            _outcome(8001, "Doug", 0.93, stamp),
            _outcome(8002, "Shane", 0.05, stamp),
            _outcome(8003, "Lew", 0.02, stamp),
        ],
        updated_at=stamp,
    )


def _live_board():
    return _market(
        market_id=LIVE_ID,
        name="Will the festival announce its lineup by November?",
        outcomes=[
            _outcome(8101, "Live leader", 0.55, NOW),
            _outcome(8102, "Live second", 0.30, NOW),
            _outcome(8103, "Live third", 0.15, NOW),
        ],
        updated_at=NOW,
    )


def _install(monkeypatch, *, fleet):
    """Five arms withhold NOTHING; the fleet stamp is the only lever.

    Returns the list of market ids the fleet read was asked about, so a route
    that asked for one market and reused the answer for the page would not
    satisfy the wiring assertion below.
    """
    asked = []

    async def _no_five_arm_refusal(db, market):
        return set()

    async def _fleet(db, market):
        asked.append(market.id)
        return fleet

    monkeypatch.setattr(
        entertainment_module, "_withheld_price_outcome_ids", _no_five_arm_refusal
    )
    monkeypatch.setattr(
        entertainment_module, "_fleet_newest_observation", _fleet
    )
    return asked


async def _payload(client, mock_db, markets):
    mock_db.execute.return_value = _MockResult(markets)
    resp = await client.get("/api/entertainment")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "themes" in body, (
        "the route fell through to its timeout/error shape, so every assertion "
        f"below would be vacuously true: {body}"
    )
    return body


def _all_rows(payload):
    found = []

    def _walk(node):
        if isinstance(node, dict):
            if node.get("market_id") is not None and isinstance(
                node.get("top_outcomes"), list
            ):
                found.append(node)
            for value in node.values():
                _walk(value)
        elif isinstance(node, list):
            for value in node:
                _walk(value)

    _walk(payload)
    return found


def _published_leg_names(payload, market_id):
    names = set()
    for row in _all_rows(payload):
        if row.get("market_id") == market_id:
            for leg in row.get("top_outcomes") or []:
                if leg.get("prob") is not None:
                    names.add(leg.get("name"))
    return names


# ---------------------------------------------------------------------------


class TestTheFixtureLandsWhereItClaims:
    """Without this, an absence below could just mean the card never rendered."""

    async def test_the_live_control_is_published_in_full(
        self, client, mock_db, monkeypatch
    ):
        _install(monkeypatch, fleet=NOW)
        payload = await _payload(client, mock_db, [_dead_board(), _live_board()])
        assert _published_leg_names(payload, LIVE_ID) == set(LIVE_LEG_NAMES), (
            "the control board is fresh and nothing withholds it, so the page "
            "must publish all three of its legs — if it does not, this fixture "
            "cannot prove anything about the dead board beside it"
        )


class TestAnUnobservedBoardIsNotRepublished:

    async def test_no_leg_of_the_dead_board_is_published(
        self, client, mock_db, monkeypatch
    ):
        _install(monkeypatch, fleet=NOW)
        payload = await _payload(client, mock_db, [_dead_board(), _live_board()])
        assert _published_leg_names(payload, DEAD_ID) == set(), (
            "every leg of this board was last observed 190 days before the "
            "fleet's newest observation, so /futures/{id} serves them as null; "
            "the page must not print a price for any of them"
        )

    async def test_the_card_is_withdrawn_entirely(
        self, client, mock_db, monkeypatch
    ):
        _install(monkeypatch, fleet=NOW)
        payload = await _payload(client, mock_db, [_dead_board(), _live_board()])
        ids = {row.get("market_id") for row in _all_rows(payload)}
        assert DEAD_ID not in ids, (
            "nothing on this board is servable, so there is no honest headline "
            "to print and the card must be withdrawn rather than published off "
            "a fabricated one"
        )

    async def test_the_live_control_survives_alongside_it(
        self, client, mock_db, monkeypatch
    ):
        _install(monkeypatch, fleet=NOW)
        payload = await _payload(client, mock_db, [_dead_board(), _live_board()])
        assert _published_leg_names(payload, LIVE_ID) == set(LIVE_LEG_NAMES), (
            "withdrawing the dead board must not empty the page — this is the "
            "arm that separates a fix from a page-emptying"
        )


class TestTheGuardCanFail:
    """Anti-vacuity: the numbers above are absent because of THIS arm."""

    async def test_with_no_fleet_reference_the_same_board_is_published(
        self, client, mock_db, monkeypatch
    ):
        # `unobserved_board_keys` withholds nothing when the fleet stamp is
        # None — the documented outage behaviour. The fixture is byte-identical
        # to the one withdrawn above, so if this republished set were empty the
        # assertions above would be passing for some other reason.
        _install(monkeypatch, fleet=None)
        payload = await _payload(client, mock_db, [_dead_board(), _live_board()])
        assert _published_leg_names(payload, DEAD_ID) == set(DEAD_LEGS_NAMES), (
            "with no fleet reference nothing is unobserved, so the identical "
            "board must publish all three legs — proving the withdrawal above "
            "is this arm's doing and not the fixture's"
        )

    async def test_a_freshly_observed_board_is_published(
        self, client, mock_db, monkeypatch
    ):
        # The other direction: keep the fleet reference, move only the board's
        # own stamps inside the window.
        _install(monkeypatch, fleet=NOW)
        payload = await _payload(
            client, mock_db, [_dead_board(age=timedelta(days=1)), _live_board()]
        )
        assert _published_leg_names(payload, DEAD_ID) == set(DEAD_LEGS_NAMES), (
            "observed yesterday is not unobserved; the arm must withhold "
            "nothing on a board inside the window"
        )


class TestTheRouteAsksPerMarketAndNotOnce:

    async def test_the_fleet_reference_is_read_for_every_market(
        self, client, mock_db, monkeypatch
    ):
        asked = _install(monkeypatch, fleet=NOW)
        await _payload(client, mock_db, [_dead_board(), _live_board()])
        assert set(asked) == {DEAD_ID, LIVE_ID}, (
            "the arm is decided per board, so the route must ask about each "
            f"market the page considers; it asked about {asked}"
        )
