"""#8664 page half: a game container's market page names the side each leg prices.

THE DEFECT, SEEN ON PRODUCTION (2026-09-25 20:26Z, 390px, `/futures/62357974`,
"Counter-Strike: Infinite vs SAW (BO3) - Leon.bet Masters Group D"). The hero
read "100%  Map 1 Rounds Handicap: SAW (-3.5) vs Infinite (+3.5)" and All
Outcomes listed thirteen QUESTIONS as answers: "Match Winner <1%", "Map 2 Winner
<1%", "O/U 2.5 Games <1%". Each leg is priced at the sibling sub-market's
``outcome_prices[0]``, which the sibling row stores as ``{condition_id}_yes``.
Measured on production the same minute: all 13 legs equal that side exactly.
"Match Winner <1%" is Infinite at <1%; SAW was at 99.95% on row 62357977.

The fix serves each such leg as "<side> — <question>". Prices and ids stay as
they were, so the chart (keyed on outcome id) still draws the same line.

🔴 THE CONTROLS ARE THE POINT. "The labels changed" is also satisfied by a
relabel that fires on every Polymarket board, or one that reads the side by row
position. So: a Yes/No sibling's leg keeps its question; a board with one leg
that names no row is not a container and nothing on it moves; a one-winner board
and a non-Polymarket board are never read; the side is picked by ``_yes`` id even
when the ``_no`` row comes first; the parent's own row never counts as a sibling;
and a board with no map serves exactly the names it did before.
"""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.routes import futures as futures_routes
from app.routes.futures import (
    _format_market_detail,
    _game_container_leg_sides,
    _leg_side_label,
    get_futures_market,
)

GROUP = "polymarket:1127014"
CONTAINER_ID = 62357974
STAMP = datetime(2026, 9, 25, 20, 20, tzinfo=timezone.utc)

#: Four of the specimen's legs, as production stored them (external ids shortened).
MATCH, OU, MAP2_HCP, YESNO = "0x2227", "0x6aa5", "0x1cee", "0x9999"
SIBLINGS = {
    # leg external id: (sibling row id, [(side external id, side name)])
    MATCH: (62357977, [(f"{MATCH}_yes", "Infinite"), (f"{MATCH}_no", "SAW")]),
    OU: (62357978, [(f"{OU}_yes", "Over"), (f"{OU}_no", "Under")]),
    MAP2_HCP: (62372259, [(f"{MAP2_HCP}_yes", "SAW"), (f"{MAP2_HCP}_no", "Infinite")]),
}


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


def _board(legs, *, source="polymarket", mutually_exclusive=False, group_id=GROUP):
    return SimpleNamespace(
        id=CONTAINER_ID,
        name="Counter-Strike: Infinite vs SAW (BO3) - Leon.bet Masters Group D",
        description=None,
        category="esports",
        source=source,
        external_id="1127014",
        status="open",
        sport=None,
        sport_id=None,
        event_id=None,
        market_type=None,
        market_tier=3,
        llm_sport_category="esports",
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
        outcomes=[_outcome(i + 1, ext, name, p) for i, (ext, name, p) in enumerate(legs)],
    )


def _specimen():
    return _board(
        [
            (MATCH, "Match Winner", 0.0005),
            (OU, "O/U 2.5 Games", 0.0005),
            (MAP2_HCP, "Map 2 Rounds Handicap: SAW (-3.5) vs Infinite (+3.5)", 0.0005),
        ]
    )


def _rows(siblings):
    """The read's shape: ``(sibling id, sibling external id, side external id, side name)``."""
    return [
        (sid, ext, side_ext, side_name)
        for ext, (sid, sides) in siblings.items()
        for side_ext, side_name in sides
    ]


class _Db:
    """Answers each ``execute`` from a script and counts the calls."""

    def __init__(self, *results):
        self.results = list(results)
        self.calls = 0

    async def execute(self, _stmt):
        self.calls += 1
        result = self.results.pop(0)
        return SimpleNamespace(
            all=lambda: result, scalar_one_or_none=lambda: result
        )


# ── the side map ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_the_specimen_legs_name_the_side_they_price():
    """🔴 THE SHIP: every leg is a two-sided sibling, and each gets its ``_yes`` side."""
    db = _Db(_rows(SIBLINGS))
    assert await _game_container_leg_sides(db, _specimen()) == {
        MATCH: "Infinite",
        OU: "Over",
        MAP2_HCP: "SAW",
    }


@pytest.mark.asyncio
async def test_the_side_is_read_by_id_not_by_row_order():
    """The ``_no`` row first must not flip "Infinite" to "SAW" (insertion-order bet)."""
    flipped = {ext: (sid, list(reversed(sides))) for ext, (sid, sides) in SIBLINGS.items()}
    assert (await _game_container_leg_sides(_Db(_rows(flipped)), _specimen()))[MATCH] == "Infinite"


@pytest.mark.asyncio
async def test_a_yes_no_siblings_leg_keeps_its_question():
    """For a Yes/No sub-market the question IS the label of its YES price."""
    board = _board(
        [(MATCH, "Match Winner", 0.0005), (YESNO, "Will SAW win 2-0?", 0.4)]
    )
    siblings = dict(SIBLINGS, **{YESNO: (62400000, [(f"{YESNO}_yes", "Yes"), (f"{YESNO}_no", "No")])})
    sides = await _game_container_leg_sides(_Db(_rows(siblings)), board)
    assert sides == {MATCH: "Infinite", OU: "Over", MAP2_HCP: "SAW"}
    assert YESNO not in sides


@pytest.mark.asyncio
async def test_a_leg_that_names_no_row_means_no_container_and_nothing_moves():
    """#8669's board test: every leg must be another row. One orphan leg keeps the board as is."""
    board = _board(
        [(MATCH, "Match Winner", 0.0005), ("0xorphan", "Map 5 Winner", 0.3)]
    )
    assert await _game_container_leg_sides(_Db(_rows(SIBLINGS)), board) == {}


@pytest.mark.asyncio
async def test_the_parent_itself_is_never_its_own_sibling():
    board = _board([(MATCH, "Match Winner", 0.0005)])
    own = {MATCH: (CONTAINER_ID, SIBLINGS[MATCH][1])}
    assert await _game_container_leg_sides(_Db(_rows(own)), board) == {}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "board",
    [
        _board([(MATCH, "Norway", 0.4)], mutually_exclusive=True),
        _board([(MATCH, "Match Winner", 0.4)], source="kalshi"),
        _board([(MATCH, "Match Winner", 0.4)], group_id=None),
        _board([(None, "Match Winner", 0.4)]),
    ],
    ids=["one-winner", "not-polymarket", "no-group", "leg-without-id"],
)
async def test_a_non_candidate_board_is_never_read(board):
    db = _Db()
    assert await _game_container_leg_sides(db, board) == {}
    assert db.calls == 0


def test_the_label_puts_the_side_first():
    assert _leg_side_label("Infinite", "Match Winner") == "Infinite — Match Winner"


# ── the served payload ──────────────────────────────────────────────────────


def _served_names(payload):
    return {o["id"]: o["name"] for o in payload["outcomes"]}


def test_the_formatter_serves_the_side_and_keeps_price_and_id():
    board = _specimen()
    payload = _format_market_detail(
        board, [], set(), leg_sides={MATCH: "Infinite", OU: "Over", MAP2_HCP: "SAW"}
    )
    by_id = {o["id"]: o for o in payload["outcomes"]}
    assert by_id[1]["name"] == "Infinite — Match Winner"
    assert by_id[2]["name"] == "Over — O/U 2.5 Games"
    assert by_id[3]["name"] == "SAW — Map 2 Rounds Handicap: SAW (-3.5) vs Infinite (+3.5)"
    control = {o["id"]: o for o in _format_market_detail(_specimen(), [], set())["outcomes"]}
    assert {i: o["probability"] for i, o in by_id.items()} == {
        i: o["probability"] for i, o in control.items()
    }


def test_no_map_serves_the_names_it_always_did():
    """Control: the same board with no map is byte-for-byte the old payload."""
    assert _format_market_detail(_specimen(), [], set()) == _format_market_detail(
        _specimen(), [], set(), leg_sides={}
    )
    assert set(_served_names(_format_market_detail(_specimen(), [], set())).values()) == {
        "Match Winner",
        "O/U 2.5 Games",
        "Map 2 Rounds Handicap: SAW (-3.5) vs Infinite (+3.5)",
    }


@pytest.mark.asyncio
async def test_the_route_serves_the_relabelled_specimen(monkeypatch):
    """End to end through `get_futures_market`: the market read, then the sibling read."""

    async def _no_sources(*_a, **_k):
        return [], []

    async def _nothing_withheld(*_a, **_k):
        return set()

    async def _no_fleet(*_a, **_k):
        return None

    monkeypatch.setattr(futures_routes, "_load_market_sources", _no_sources)
    monkeypatch.setattr(futures_routes, "_withheld_price_outcome_ids", _nothing_withheld)
    monkeypatch.setattr(futures_routes, "_fleet_newest_observation", _no_fleet)
    # The third read is #8892's lead-leg read; no sibling carries an understanding.
    db = _Db(_specimen(), _rows(SIBLINGS), [])
    payload = await get_futures_market(CONTAINER_ID, db=db)
    assert set(_served_names(payload).values()) == {
        "Infinite — Match Winner",
        "Over — O/U 2.5 Games",
        "SAW — Map 2 Rounds Handicap: SAW (-3.5) vs Infinite (+3.5)",
    }


# ── the chart legend (`/history`) ───────────────────────────────────────────


class _HistoryResult:
    def __init__(self, value=None, rows=()):
        self._value = value
        self._rows = list(rows)

    def scalar_one_or_none(self):
        return self._value

    def scalars(self):
        return self

    def unique(self):
        return self

    def all(self):
        return list(self._rows)


class _HistorySession:
    """The market, an empty withheld-set read, then snapshots (the last repeats)."""

    def __init__(self, *results):
        self._results = list(results)
        self.calls = 0

    async def execute(self, _stmt):
        self.calls += 1
        return self._results[min(self.calls - 1, len(self._results) - 1)]


@pytest.mark.asyncio
async def test_the_chart_legend_names_the_same_side_as_the_rows(monkeypatch):
    """The Probability Trend legend read "Map 1 Rounds Handicap: …" above the same
    mislabelled rows. It uses the same map, so the legend and the rows agree."""
    from datetime import timedelta

    board = _specimen()
    # Kalshi here only so the history route skips its Polymarket venue-history
    # seam. The side map is patched, and its own arms are tested above.
    board.source = "kalshi"
    now = datetime.now(timezone.utc)
    snaps = [
        SimpleNamespace(
            outcome_id=o.id,
            bookmaker="kalshi",
            probability=0.5,
            yes_bid=0.49,
            yes_ask=0.51,
            last_price=0.5,
            captured_at=now - timedelta(hours=h),
        )
        for o in board.outcomes
        for h in (6, 4, 2)
    ]
    snaps.sort(key=lambda s: s.captured_at)

    async def _sides(_db, _market):
        return {MATCH: "Infinite"}

    monkeypatch.setattr(futures_routes, "_game_container_leg_sides", _sides)
    payload = await futures_routes.get_futures_history(
        CONTAINER_ID,
        outcome_id=None,
        hours=168,
        top_n=10,
        champion=None,
        db=_HistorySession(
            _HistoryResult(value=board), _HistoryResult(rows=()), _HistoryResult(rows=snaps)
        ),
    )
    names = {entry["outcome_id"]: entry["name"] for entry in payload["outcomes"]}
    assert names[1] == "Infinite — Match Winner"
    assert names[2] == "O/U 2.5 Games"
