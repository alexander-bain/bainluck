"""#10165 page half (backend): `/api/futures/{id}` names the game a container belongs to.

THE DEFECT, SEEN ON PRODUCTION (2026-10-02 04:45Z, 390px, `/futures/63612402`).
"New York Yankees vs. Tampa Bay Rays": hero "46% · New York Yankees — New York
Yankees", Games This Week printed all three ALDS games at that one price, and
All Outcomes ranked nine legs of nine DIFFERENT questions (a runs total, the
moneyline, NRFI, four spreads) as one field. The row is Polymarket event
1113712's EVENT row (`event_id` 15322539, `mutually_exclusive` false), and every
leg is another row on `polymarket:1113712`.

The route now serves `container_of_event_id` = 15322539 for that row and `None`
for every other board; ux's page redirects on it (the paired half, ux note
FROM-ux-0507Z-10165-render-half-needs-container-flag, notice 46). The test is
search's #8375 linked arm, imported — so the page and the search box agree.

🔴 THE CONTROLS ARE THE POINT. "The flag serves" is also satisfied by a flag on
every Polymarket board. So: an unlinked container, a one-winner board, a Kalshi
board, a board with one leg that names no row, and a leg on ANOTHER group are
all `None`; and a non-candidate issues no read at all.
"""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.routes import futures as futures_routes
from app.routes.futures import _game_container_of_event_id, get_futures_market

GROUP = "polymarket:1113712"
CONTAINER_ID = 63612402
EVENT_ID = 15322539
STAMP = datetime(2026, 10, 2, 4, 45, tzinfo=timezone.utc)

#: The specimen's nine legs as production stored them: (name, price, sibling row id).
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


def _outcome(oid, external_id, name, prob):
    return SimpleNamespace(
        id=oid,
        name=name,
        external_id=external_id,
        current_probability=prob,
        current_american_odds=None,
        rank=None,
        rank_change_24h=None,
        probability_change_24h=None,
        opening_probability=None,
        opening_american_odds=None,
        is_winner=None,
        resolution_source=None,
        last_updated=STAMP,
        price_changed_at=STAMP,
        team_id=None,
    )


def _board(
    legs=None,
    *,
    source="polymarket",
    mutually_exclusive=False,
    group_id=GROUP,
    event_id=EVENT_ID,
):
    legs = LEGS if legs is None else legs
    return SimpleNamespace(
        id=CONTAINER_ID,
        name="New York Yankees vs. Tampa Bay Rays",
        description=None,
        category="championship",
        source=source,
        external_id="1113712",
        status="open",
        sport=None,
        sport_id=None,
        event_id=event_id,
        market_type="field",
        market_tier=5,
        llm_sport_category="baseball",
        mutually_exclusive=mutually_exclusive,
        commence_time=None,
        resolution_date=None,
        created_at=None,
        updated_at=None,
        group_id=group_id,
        canonical_market_key=None,
        hook_description=None,
        image_url=None,
        category_tags=[],
        market_metadata=None,
        outcomes=[
            _outcome(9000 + i, _cond(row), name, p)
            for i, (name, p, row) in enumerate(legs)
        ],
    )


def _sibling_rows(group=GROUP, legs=LEGS):
    """The read's shape: ``(id, group_id, external_id)``."""
    return [(row, group, _cond(row)) for _, _, row in legs]


class _Db:
    """Answers each ``execute`` from a script and counts the calls."""

    def __init__(self, *results):
        self.results = list(results)
        self.calls = 0

    async def execute(self, _stmt):
        self.calls += 1
        result = self.results.pop(0)
        return SimpleNamespace(all=lambda: result, scalar_one_or_none=lambda: result)


# ── the verdict ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_the_alds_container_names_its_game():
    """🔴 THE SHIP: every leg is another row on its own group, and the board is linked."""
    db = _Db(_sibling_rows())
    assert await _game_container_of_event_id(db, _board()) == EVENT_ID
    assert db.calls == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "board",
    [
        _board(event_id=None),  # unlinked: no game to send the reader to
        _board(mutually_exclusive=True),  # a one-winner board is a real question
        _board(mutually_exclusive=None),  # unknown is not False
        _board(source="kalshi"),
        _board(group_id=None),
        _board(legs=[]),
    ],
    ids=["unlinked", "one-winner", "null-exclusivity", "kalshi", "no-group", "no-legs"],
)
async def test_a_non_candidate_is_never_read_and_names_nothing(board):
    db = _Db()
    assert await _game_container_of_event_id(db, board) is None
    assert db.calls == 0


@pytest.mark.asyncio
async def test_a_leg_that_names_no_row_is_not_a_container():
    """If one sub-market was never written as a row, the board is its only home."""
    db = _Db(_sibling_rows()[1:])
    assert await _game_container_of_event_id(db, _board()) is None


@pytest.mark.asyncio
async def test_a_leg_on_another_group_does_not_count():
    db = _Db(_sibling_rows(group="polymarket:999"))
    assert await _game_container_of_event_id(db, _board()) is None


@pytest.mark.asyncio
async def test_a_leg_that_names_the_board_itself_does_not_count():
    rows = [(CONTAINER_ID, GROUP, _cond(LEGS[0][2]))] + _sibling_rows()[1:]
    assert await _game_container_of_event_id(_Db(rows), _board()) is None


# ── the route ───────────────────────────────────────────────────────────────


def _stub_reads(monkeypatch):
    async def _no_sources(*_a, **_k):
        return [], []

    async def _nothing_withheld(*_a, **_k):
        return set()

    async def _no_fleet(*_a, **_k):
        return None

    async def _no_sides(*_a, **_k):
        return {}

    monkeypatch.setattr(futures_routes, "_load_market_sources", _no_sources)
    monkeypatch.setattr(futures_routes, "_withheld_price_outcome_ids", _nothing_withheld)
    monkeypatch.setattr(futures_routes, "_fleet_newest_observation", _no_fleet)
    monkeypatch.setattr(futures_routes, "_game_container_leg_sides", _no_sides)


@pytest.mark.asyncio
async def test_the_route_serves_the_game_for_the_specimen(monkeypatch):
    """End to end through `get_futures_market`: the market read, then the leg read."""
    _stub_reads(monkeypatch)
    db = _Db(_board(), _sibling_rows())
    payload = await get_futures_market(CONTAINER_ID, db=db)
    assert payload["container_of_event_id"] == EVENT_ID
    # Additive: the ladder the page drew before is still served, untouched.
    assert len(payload["outcomes"]) == len(LEGS)


@pytest.mark.asyncio
async def test_the_route_serves_none_for_a_real_board(monkeypatch):
    """The key is always present, so a client reads one shape."""
    _stub_reads(monkeypatch)
    db = _Db(_board(mutually_exclusive=True))
    payload = await get_futures_market(CONTAINER_ID, db=db)
    assert "container_of_event_id" in payload
    assert payload["container_of_event_id"] is None
    assert db.calls == 1  # the market read only
