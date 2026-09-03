"""UX-P276 / #2789 — route-level proof that a prop card's rank badge is earned.

`tests/test_leader_order_2789.py` proves the pure helper orders rows. That is
the fix site, but it stops one step short of what a reader sees: a guard on a
helper stays green the day the route stops calling it (ux/1006's lesson — a
guard that stops one step short of the user-visible array is green on the bug).

So every test here drives the real ASGI route and asserts on the RESPONSE BODY,
which is the array `FuturesCard` stamps `1 2 3 4 5` onto.

Fixtures are real unbound `FuturesMarket` / `FuturesOutcome` ORM rows rather
than hand-rolled stand-ins, so the route reads `o.probability` — the property
alias over the `current_probability` column — exactly as it does in production.
A `SimpleNamespace` carrying a `probability` attribute would pass while proving
nothing about that indirection.

Measured on production before this shipped (2026-09-03, `/api/futures/grouped-feed`):

    shape                          markets   leader at row 1
    ?sports_only=true&limit=20        20            7
      ... of which 5 outcomes          5            0
      ... of which 2 outcomes         15            7
    ?limit=50                         50           23

and the 192-golfer "Omega European Masters - Winner" card led with a 0.09%
entrant while the true leader at 11.8% was not among the five shipped at all.
"""

from unittest.mock import MagicMock

from app.models import FuturesMarket, FuturesOutcome
from app.utils import request_cache as _rc

# --------------------------------------------------------------------------
# seeding
# --------------------------------------------------------------------------


def _market(market_id, name, priced, *, sport="golf"):
    """One unbound market whose outcomes arrive in the order `priced` gives them.

    `priced` is a list of (name, probability) in the order the unordered
    `selectinload` handed them over — i.e. the production defect, verbatim.
    """
    m = FuturesMarket(
        id=market_id,
        name=name,
        source="datagolf",
        category="championship",
        llm_sport_category=sport,
        status="open",
        group_id=None,
        group_type=None,
    )
    m.outcomes = [
        FuturesOutcome(
            id=market_id * 1000 + i,
            name=outcome_name,
            current_probability=probability,
            current_american_odds=None,
        )
        for i, (outcome_name, probability) in enumerate(priced)
    ]
    return m


def _seed(mock_db, markets):
    """Make `db.execute(...)` return `markets` from `.scalars().unique().all()`."""
    result = MagicMock()
    result.scalars.return_value.unique.return_value.all.return_value = markets
    result.scalars.return_value.all.return_value = markets
    mock_db.execute.return_value = result


class _NoRedis:
    """No cache: force the route down the BUILD path, which is the defect site.

    A cache hit would serve a hand-written body and prove nothing about the
    truncation.
    """

    async def get(self, key):
        return None

    async def setex(self, key, ttl, body):
        return True


async def _async(value):
    return value


def _install(monkeypatch):
    _rc._reset_last_good_for_tests()
    _rc._reset_inflight_for_tests()
    _rc._reset_shared_client_for_tests()
    monkeypatch.setattr(_rc, "get_shared_async_redis", lambda: _async(_NoRedis()))


def _cards(body):
    return {
        item["market"]["id"]: item["market"]
        for item in body["feed"]
        if item["type"] == "market"
    }


def _probs(card):
    return [o["probability"] for o in card["outcomes"]]


def _names(card):
    return [o["name"] for o in card["outcomes"]]


# The reported card, with the five outcomes in the order production shipped them
# and the true leader (Harry Hall, 11.79%) sitting outside the first five — which
# is why a frontend-only sort cannot fix this one.
_WINNER_AS_SHIPPED = [
    ("Yannik Paul", 0.000863),
    ("Felix Mory", 0.000496),
    ("Marco Penge", 0.007235),
    ("Todd Clements", 0.038777),
    ("Richard Sterne", 0.000174),
    ("Ryan Gerard", 0.084000),
    ("Harry Hall", 0.117902),
]


# --------------------------------------------------------------------------
# the ship
# --------------------------------------------------------------------------


async def test_the_first_row_of_a_prop_card_is_the_favourite(
    client, mock_db, monkeypatch
):
    """RED ON MASTER: row 1 is `Yannik Paul` at 0.09%.

    Asserted on the response body, which is the array the card indexes with
    `rank={index + 1}` and `isLeader={index === 0}`.
    """
    _install(monkeypatch)
    _seed(
        mock_db,
        [_market(59863411, "Omega European Masters - Winner", _WINNER_AS_SHIPPED)],
    )

    body = (await client.get("/api/futures/grouped-feed?limit=20")).json()
    card = _cards(body)[59863411]

    assert _names(card)[0] == "Harry Hall", (
        "the card stamps rank 1 and a highlighted leader on row 1, and row 1 is "
        f"{_names(card)[0]!r} at {_probs(card)[0]}"
    )
    assert _probs(card)[0] == max(_probs(card))


async def test_the_truncation_cannot_discard_the_favourite(
    client, mock_db, monkeypatch
):
    """The load-bearing half: the leader is at index 6 of 7 and must survive `[:5]`.

    This is the arm a frontend-only fix cannot satisfy — re-sorting five rows
    that were already chosen at random still shows the wrong five. On production
    the real market has 192 outcomes and ships 5.
    """
    _install(monkeypatch)
    _seed(
        mock_db,
        [_market(59863411, "Omega European Masters - Winner", _WINNER_AS_SHIPPED)],
    )

    card = _cards((await client.get("/api/futures/grouped-feed?limit=20")).json())[
        59863411
    ]

    assert len(card["outcomes"]) == 5, "the card still ships five rows"
    assert "Harry Hall" in _names(card)
    assert "Ryan Gerard" in _names(card)
    assert _names(card) == [
        "Harry Hall",
        "Ryan Gerard",
        "Todd Clements",
        "Marco Penge",
        "Yannik Paul",
    ]


async def test_every_shipped_row_outranks_every_discarded_one(
    client, mock_db, monkeypatch
):
    """The property, not the instance: truncation keeps the top five, in order.

    Stated as an invariant so it survives the fixture being re-seeded, rather
    than pinning one expected list (ux/1012's lesson #4).
    """
    _install(monkeypatch)
    _seed(
        mock_db,
        [_market(59863411, "Omega European Masters - Winner", _WINNER_AS_SHIPPED)],
    )

    card = _cards((await client.get("/api/futures/grouped-feed?limit=20")).json())[
        59863411
    ]
    shipped = _probs(card)
    dropped = sorted(p for _, p in _WINNER_AS_SHIPPED)[: len(_WINNER_AS_SHIPPED) - 5]

    assert shipped == sorted(shipped, reverse=True)
    assert min(shipped) >= max(dropped)


async def test_a_two_outcome_card_does_not_lead_with_the_long_shot(
    client, mock_db, monkeypatch
):
    """RED ON MASTER, and it is the commonest shape on `/sports`.

    8 of the 15 two-outcome tennis cards in the live capture led with the
    unlikely side. The worst read `Yes 2.4%` as the highlighted #1 above
    `No 97.6%`.

    NOTE the fixture puts the leader SECOND on purpose. #2789's own text warns
    that a two-outcome guard is green on the bug — that is true only when the
    leader happens to arrive first, which is the control below, not this.
    """
    _install(monkeypatch)
    _seed(
        mock_db,
        [
            _market(
                59559155,
                "Will Jasmine Paolini advance to the Semifinals in Women's Singles?",
                [("Yes", 0.024), ("No", 0.976)],
                sport="tennis",
            )
        ],
    )

    card = _cards((await client.get("/api/futures/grouped-feed?limit=20")).json())[
        59559155
    ]

    assert _names(card) == ["No", "Yes"]
    assert _probs(card)[0] == 0.976


async def test_an_unpriced_row_is_never_the_leader(client, mock_db, monkeypatch):
    """`Make the Cut` shipped `Oliver Lindell` (probability NULL) at row 2.

    A null must sort last rather than tie with a genuine 0.0 — it is an absence
    of a quote, not a quote of zero.
    """
    _install(monkeypatch)
    _seed(
        mock_db,
        [
            _market(
                59863415,
                "Omega European Masters - Make the Cut",
                [
                    ("Oliver Lindell", None),
                    ("Marco Penge", 0.530080),
                    ("Nobody At All", 0.0),
                    ("Marcus Kinhult", 0.570600),
                ],
            )
        ],
    )

    card = _cards((await client.get("/api/futures/grouped-feed?limit=20")).json())[
        59863415
    ]

    assert _names(card) == [
        "Marcus Kinhult",
        "Marco Penge",
        "Nobody At All",
        "Oliver Lindell",
    ]
    assert _probs(card)[0] == 0.570600


# --------------------------------------------------------------------------
# CONTROLS — each verified GREEN on the parent commit as well as on the fix.
# --------------------------------------------------------------------------


async def test_CONTROL_an_already_ordered_card_is_unchanged(
    client, mock_db, monkeypatch
):
    """Green on master too.

    Three of `FuturesCard`'s four callers already hand it a sorted list. The
    change must be a no-op for them, or this stops being a narrowing fix and
    becomes a reshuffle nobody asked for.
    """
    _install(monkeypatch)
    ordered = [("Alpha", 0.6), ("Bravo", 0.3), ("Charlie", 0.1)]
    _seed(mock_db, [_market(777, "An already ordered market", ordered)])

    card = _cards((await client.get("/api/futures/grouped-feed?limit=20")).json())[777]

    assert _names(card) == ["Alpha", "Bravo", "Charlie"]
    assert _probs(card) == [0.6, 0.3, 0.1]


async def test_CONTROL_a_two_outcome_card_that_was_already_right_stays_right(
    client, mock_db, monkeypatch
):
    """Green on master too — and this is the case #2789 warned about.

    7 of 15 live two-outcome cards led correctly by luck. Kept deliberately as a
    labelled control so a reader can see that the coincidence-correct half is
    NOT being counted as evidence for the fix.
    """
    _install(monkeypatch)
    _seed(
        mock_db,
        [
            _market(
                59559163,
                "Will Ann Li advance to the Quarterfinals in Women's Singles?",
                [("No", 0.9695), ("Yes", 0.0305)],
                sport="tennis",
            )
        ],
    )

    card = _cards((await client.get("/api/futures/grouped-feed?limit=20")).json())[
        59559163
    ]

    assert _names(card) == ["No", "Yes"]


async def test_CONTROL_the_card_still_arrives_as_an_ungrouped_market(
    client, mock_db, monkeypatch
):
    """Green on master too, and it is what stops every test above being vacuous.

    The route runs three grouping passes before the ungrouped serialization. A
    fixture that accidentally looked like a stat prop or a threshold ladder
    would never reach the code under test, and every assertion here would pass
    against an empty dict lookup rather than a card.
    """
    _install(monkeypatch)
    _seed(
        mock_db,
        [_market(59863411, "Omega European Masters - Winner", _WINNER_AS_SHIPPED)],
    )

    body = (await client.get("/api/futures/grouped-feed?limit=20")).json()

    assert [item["type"] for item in body["feed"]] == ["market"]
    assert body["total_ungrouped"] == 1
    assert body["group_counts"] == {
        "stat_prop": 0,
        "playoff_progression": 0,
        "threshold": 0,
    }
