"""LAT-P192 — the golf tournament detail route reads market sources ONCE.

Why this file exists
--------------------
``GET /api/golf/tournaments/{slug}`` built the SAME ``market_id -> source`` map
three separate times, from three separate round trips, in one request::

    placement grid     SELECT id, source FROM futures_markets WHERE id IN (...)
    round markets      SELECT id, source FROM futures_markets WHERE id IN (...)
    related futures    SELECT id, source FROM futures_markets WHERE id IN (...)

Every one of those id sets is a subset of the tournament's own ``market_ids``,
and two of them genuinely OVERLAP: a ``round_leader`` market is in the placement
set (it is listed in the placement ``type`` tuple) *and* in ``round_market_kinds``,
so its source row was fetched twice.

Sizing, honestly
----------------
This is round trips, not the dominant cost. The sibling
``test_golf_tournament_cache_reuse.py`` records the production measurement this
route was ranked on (2026-09-01, ``x-timing-split``, median of 5):

===================================  ========================================
``/api/golf/tournaments/us-open``    2,076 ms wall / 1,556 ms app / **q=19**
``/api/golf/tournaments/the-masters``  1,795 ms wall / 1,391 ms app / **q=18**
===================================  ========================================

``app`` dominates ``db`` on every slug, so removing two of nineteen queries is a
small, attributable cut and is not claimed as more than that. What makes it worth
committing is that it is *free*: the three maps are read only through
``.get(<mid>)`` keyed by ids from their own group, so one whole-tournament map is
set-equivalent at every read site, with no behaviour to trade away.

Like its siblings this asserts the WIRING, not wall-clock — a timing assertion on
CI hardware is flaky and proves nothing about production (LAT-P005).

What the detectors must survive
-------------------------------
P191a: *a detector must not pass on the absence it is supposed to catch.* The
count assertion below is ``== 1``, never ``<= 1``: a route that early-exits, 404s,
or never reaches the three blocks issues ZERO such selects, and ``<= 1`` would
wave that through as a pass. ``test_the_fixture_really_exercises_all_three_blocks``
pins the fixture itself, so the ``== 1`` can never become true by the blocks
quietly ceasing to run.
"""

from __future__ import annotations

import inspect

import pytest
from sqlalchemy.dialects import postgresql

from app.routes import golf as golf_route

# One market per arm, so all three source-map call sites are on the path.
# `End of Round 1 Leader` is deliberately present: `round_leader` is claimed by
# BOTH the placement block and `round_market_kinds`, which is the overlap that
# made two of the three round trips redundant with each other.
_MARKETS: list[tuple[int, str]] = [
    (101, "2026 Masters Winner"),                     # winner
    (102, "Masters Top 5 Finish"),                    # top_5        -> placement
    (103, "Masters Make the Cut"),                    # make_cut     -> placement
    (104, "End of Round 1 Leader"),                   # round_leader -> placement AND round
    (105, "Round 2 Top 5"),                           # round_top    -> round
    (106, "Will there be a playoff at the Masters?"),  # other        -> related futures
]

_MASTERS = {
    "name": "The Masters",
    "slug": "masters",
    "key": "masters",
    "is_major": True,
    "is_womens": False,
    "start_date": "2026-04-09T00:00:00+00:00",
    "end_date": "2026-04-12T00:00:00+00:00",
    "venue": "Augusta National",
    "location": "Augusta, GA",
    "schedule_status": "upcoming",
    "commence_time": "2026-04-09T00:00:00+00:00",
    "resolution_date": "2026-04-12T00:00:00+00:00",
    "golfers": [{"name": "Scottie Scheffler", "win_prob": 18.4, "sources": ["datagolf"]}],
    "market_ids": [mid for mid, _ in _MARKETS],
    "market_names": [name for _, name in _MARKETS],
    "market_sources": ["datagolf", "kalshi"],
    "h2h_matchups": [],
}


def _listing():
    """A minimally-valid `get_golf()`-shaped payload carrying `_MASTERS`."""
    return {
        "tournaments": [dict(_MASTERS)],
        "biggest_movers": [],
        "upcoming_events": [],
        "current_event": None,
        "total_tournaments": 1,
        "total_golfers": 1,
        "pga_schedule": [],
    }


def _compiled(statement) -> str:
    """Render an executed statement as SQL text, or '' if it is not renderable."""
    try:
        return str(statement.compile(dialect=postgresql.dialect()))
    except Exception:  # pragma: no cover - text()/DDL/etc, never the shape we count
        return ""


def _source_map_selects(mock_db) -> list:
    """Every `SELECT futures_markets.id, futures_markets.source` statement issued."""
    found = []
    for call in mock_db.execute.call_args_list:
        if not call.args:
            continue
        sql = " ".join(_compiled(call.args[0]).split())
        if sql.startswith(
            "SELECT futures_markets.id, futures_markets.source "
            "FROM futures_markets"
        ):
            found.append(call.args[0])
    return found


def _in_list(statement) -> set[int]:
    """The ids a source-map select actually asks for.

    `render_postcompile` is what expands the `IN (__[POSTCOMPILE_id_1])` token
    into real binds; without it the params dict holds the unexpanded list and
    this reads as one opaque value rather than the population.
    """
    compiled = statement.compile(
        dialect=postgresql.dialect(), compile_kwargs={"render_postcompile": True}
    )
    return {v for v in compiled.params.values() if isinstance(v, int)}


@pytest.fixture
async def _detail(client, mock_db, monkeypatch):
    """Drive the detail route over `_MASTERS` and hand back (response, mock_db)."""

    async def _build(db):
        return _listing()

    monkeypatch.setattr(golf_route, "get_golf", _build)
    resp = await client.get("/api/golf/tournaments/masters")
    return resp, mock_db


class TestTheSourceMapIsFetchedOncePerRequest:
    """The ship: one `id -> source` round trip per request, not three."""

    async def test_exactly_one_source_map_query_is_issued(self, _detail):
        resp, mock_db = _detail

        assert resp.status_code == 200, resp.text

        selects = _source_map_selects(mock_db)
        assert len(selects) == 1, (
            f"the detail route issued {len(selects)} "
            "`SELECT id, source FROM futures_markets` round trips in ONE request; "
            "the placement grid, the round markets and the related futures must "
            "share a single whole-tournament map (LAT-P192). "
            "NB this asserts `== 1`, not `<= 1`: zero means the request never "
            "reached the three blocks and the guard would otherwise pass on the "
            "very absence it exists to catch (P191a). "
            f"statements={[_in_list(s) for s in selects]}"
        )

    async def test_the_one_query_asks_for_every_block_s_markets(self, _detail):
        """Economy is only half of it — the shared map must cover all three blocks.

        Collapsing three round trips into one is a regression, not a fix, if the
        surviving query asks for a SUBSET: a block whose ids fell out would read
        `.get(mid)` as `None` and silently lose its source attribution (DataGolf
        preference on the placement grid, cross-source dedup on the related
        cards). Assert the population, not just the count — the id set is what a
        wrong-population edit would change while the count stayed at 1.
        """
        resp, mock_db = _detail
        assert resp.status_code == 200, resp.text

        selects = _source_map_selects(mock_db)
        assert len(selects) == 1, f"expected one source-map select, got {len(selects)}"

        asked = _in_list(selects[0])
        expected = {mid for mid, _ in _MARKETS}
        missing = expected - asked
        assert not missing, (
            f"the shared source map does not cover {sorted(missing)}; those markets "
            "would resolve to no source at their read site. The map is keyed off the "
            "tournament's whole `market_ids`, which is a superset of all three "
            f"blocks' ids. asked={sorted(asked)}"
        )

    async def test_the_fixture_really_exercises_all_three_blocks(self, _detail):
        """Non-vacuity, from the other side (P191a).

        The `== 1` above is only meaningful if a request over this fixture would
        have issued THREE selects under the old wiring. Each block is entered off
        a group that `_tournament_market_type` must actually produce, so pin the
        classification of the fixture's own market names rather than trusting the
        comment beside them.
        """
        types = {
            name: golf_route._tournament_market_type(name)[0] for _, name in _MARKETS
        }

        placement = {"top_5", "top_10", "top_20", "top_40", "make_cut", "round_leader"}
        assert placement & set(types.values()), (
            f"no placement market in the fixture; block 1 never runs: {types}"
        )
        assert {"round_top", "round_leader"} & set(types.values()), (
            f"no round market in the fixture; block 2 never runs: {types}"
        )
        assert "other" in types.values(), (
            f"no related-futures market in the fixture; block 3 never runs: {types}"
        )
        assert types["End of Round 1 Leader"] == "round_leader", (
            "the overlap case regressed: `round_leader` is what put the SAME market "
            "id in two of the three id sets, which is why they were redundant with "
            "each other and not merely adjacent"
        )

    async def test_every_read_site_still_resolves_its_own_markets(self, _detail):
        """Equivalence, not just economy.

        One map for the whole tournament is a SUPERSET of each block's old map.
        That is only safe because every read is a `.get(<mid>)` keyed by an id
        from that block's own group — never an iteration, a `len`, or a
        `.values()` over the map, any of which a superset would change. Assert
        that property on the source, since a future edit that starts iterating
        one of these maps would be silently wrong rather than red.
        """
        code = inspect.getsource(golf_route.get_golf_tournament)
        for name in ("mid_to_source", "rt_src", "other_mid_to_source"):
            assert f"{name}.get(" in code, (
                f"`{name}` is gone or renamed; re-derive this guard against the "
                "current read sites rather than deleting it"
            )
            for line in code.splitlines():
                stripped = line.lstrip()
                if stripped.startswith("#") or name not in stripped:
                    continue
                bad = (
                    f"for {name}",
                    f"in {name}:",
                    f"len({name})",
                    f"{name}.values(",
                    f"{name}.items(",
                    f"{name}.keys(",
                )
                assert not any(b in stripped for b in bad), (
                    f"`{name}` is now read in a way a whole-tournament superset "
                    f"would change: {stripped!r}. The single shared map is only "
                    "equivalent under keyed `.get()` reads (LAT-P192)."
                )

    async def test_a_tournament_with_no_such_markets_pays_nothing(
        self, client, mock_db, monkeypatch
    ):
        """The lazy half.

        Hoisting the query unconditionally to the top of the route would ADD a
        round trip to every tournament that has none of the three groups — today
        those requests issue zero. Sharing the map must not cost the empty case.
        """
        empty = dict(_MASTERS, market_ids=[], market_names=[])

        async def _build(db):
            return {**_listing(), "tournaments": [empty]}

        monkeypatch.setattr(golf_route, "get_golf", _build)
        resp = await client.get("/api/golf/tournaments/masters")

        assert resp.status_code == 200, resp.text
        assert _source_map_selects(mock_db) == [], (
            "a tournament with no placement, round or related markets paid for a "
            "source-map query it cannot use; the shared map must stay lazy"
        )
