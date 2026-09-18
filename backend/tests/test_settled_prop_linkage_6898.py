"""#6898 — a Kalshi prop graded before it was linked must still reach its game.

THE READER DEFECT. A finished game page serves the graded results of the prop
markets linked to it. A market whose `event_id` is NULL serves nothing, however
correctly its legs graded, so 13 settled fantasy-points results sat invisible on
the 49ers-Rams page while the same market family rendered on its twin.

WHY THE POPULATION EXISTS AT ALL. Every link pass in
`prediction_market_matching` filters `status == 'open'`, so a market that has
already settled is out of reach of the live matcher. The one settled-market
linker with no status gate — `_resolve_winners_only`'s Phase 0c — has not been
dispatched since its beat was retired 2026-07-06 (#991); that is #5111's class,
and `test_dark_repairs_are_dispatched_5111` exists because of it. What is left
is `_link_sports_props_to_events`, which runs every cycle as Phase 0-link-props
inside `_backfill_all_winners`.

THE TWO HOLES IN THAT RAIL, AND WHY EACH NEEDS ITS OWN GUARD.

1. Its scan was `^KX(NHL|NBA)` while its family map already carried five
   `KXMLB*` entries. Entries that the scan can never deliver are a silent
   no-op — the map says the rail handles baseball and it does not. That is the
   defect this file's `test_the_scan_admits_every_league_the_deriver_knows`
   pins: a league the code can derive a parent for, but the scan refuses, is
   unreachable by construction and nothing else in the suite would notice.

2. It read the game key as "everything after the first dash". MLB inning and
   period props carry a THIRD segment, so for
   `KXMLBINNINGWIN-26AUG231335STLPHI-1` it looked for a game market called
   `KXMLBGAME-26AUG231335STLPHI-1`, which does not and cannot exist. Widening
   the scan alone would therefore have linked zero of them — a fix that ships
   nothing, which is why the key reading is guarded separately from the scan.

WHAT KEEPS THE WIDENING HONEST. A prop links only where a game market carrying
the SAME game key already holds an `event_id`. That is an id-anchored
correspondence on the provider's own event ticker (ruling 048 / gotcha #32), not
a name-and-time guess, and it is what refuses the season-long families: measured
on production, every draft, HR-derby, All-Star, attendance and season-wins
family finds no sibling. The negative controls below are real such families, and
they are the half of the guard that would fail if the rail ever started matching
on anything looser than the ticker.

Specimens are production rows read 2026-09-18.
"""

import inspect
import re

import pytest

import app.tasks.kalshi as k

# ── Production specimens ────────────────────────────────────────────────────
#: The filed row: 13 graded fantasy-points legs, `event_id` NULL since
#: 2026-09-11, whose game market IS linked to the event the page renders.
NFL_PROP = "KXNFLFFPTS-26SEP10SFLAR"
NFL_GAME = "KXNFLGAME-26SEP10SFLAR"
NFL_EVENT = 14632820

#: Three-segment MLB inning prop — the shape the whole-tail read could never
#: resolve. 2,324 of these link once the key is read correctly.
MLB_PROP = "KXMLBINNINGWIN-26AUG231335STLPHI-1"
MLB_GAME = "KXMLBGAME-26AUG231335STLPHI"
MLB_EVENT = 15290967

#: Two-segment hockey prop — the population that already linked. Its behaviour
#: must not move.
NHL_PROP = "KXNHLPTS-26MAR31CARCBJ"
NHL_GAME = "KXNHLGAME-26MAR31CARCBJ"
NHL_EVENT = 15100001

#: Season-long families with no game to belong to. Measured on production at
#: 0 siblings apiece; they must stay refused however wide the scan gets.
SEASON_FAMILIES = (
    "KXNBADRAFTPICK-26-5",
    "KXNBAWINS-26-BOS",
    "KXMLBHRDERBY-26",
    "KXNFLDRAFTQB-26",
)


# ── The two pure helpers ────────────────────────────────────────────────────
def test_the_game_key_is_one_segment_not_the_whole_tail():
    """The #6898 defect, stated as the difference between two readings."""
    naive = MLB_PROP.partition("-")[2]  # what the rail used to read
    assert naive == "26AUG231335STLPHI-1"
    assert k._kalshi_game_key(MLB_PROP) == "26AUG231335STLPHI"
    # The naive reading is not merely different, it is unresolvable: no game
    # market is ever named with the trailing segment.
    assert f"KXMLBGAME-{naive}" != MLB_GAME
    assert f"KXMLBGAME-{k._kalshi_game_key(MLB_PROP)}" == MLB_GAME


@pytest.mark.parametrize("ticker", [NFL_PROP, NHL_PROP, "KXNBAPTS-26FEB19BOSGSW"])
def test_two_segment_tickers_read_identically_to_the_old_rail(ticker):
    """Inert on the population that already links — the same string, not a
    string the new code happens to also accept."""
    assert k._kalshi_game_key(ticker) == ticker.partition("-")[2]


@pytest.mark.parametrize("ticker", ["KXNHLPTS", "KXNHLPTS-", ""])
def test_a_ticker_with_no_game_key_yields_none(ticker):
    assert k._kalshi_game_key(ticker) is None


@pytest.mark.parametrize(
    "prefix,expected",
    [
        ("KXNHLPTS", "KXNHLGAME"),
        ("KXNBAREB", "KXNBAGAME"),
        ("KXMLBINNINGWIN", "KXMLBGAME"),
        ("KXMLBHIT", "KXMLBGAME"),  # was in the map, unreachable behind the scan
        ("KXNFLFFPTS", "KXNFLGAME"),
    ],
)
def test_the_parent_game_family_is_derived_from_the_league(prefix, expected):
    assert k._kalshi_game_ticker_prefix(prefix) == expected


@pytest.mark.parametrize("prefix", ["KXMLBGAME", "KXNFLGAME", "KXNHLGAME", "KXNBAGAME"])
def test_a_game_family_has_no_parent_to_borrow(prefix):
    assert k._kalshi_game_ticker_prefix(prefix) is None


@pytest.mark.parametrize("prefix", ["KXPRESPARTY", "KXHIGHNY", "KXMLSGAME", ""])
def test_a_prefix_naming_no_supported_league_has_no_parent(prefix):
    assert k._kalshi_game_ticker_prefix(prefix) is None


def test_the_scan_admits_every_league_the_deriver_knows():
    """THE DEFECT'S OWN GUARD.

    Five `KXMLB*` map entries sat behind a `^KX(NHL|NBA)` scan and linked
    nothing. Eligibility lives in two places — what the scan selects and what
    the deriver can find a parent for — and when they disagree the narrower one
    wins silently. Every other test in this file passes with the scan narrowed
    back to `^KX(NHL|NBA)`, because they drive the helpers and the loop
    directly; only this one reads the shipped SQL.
    """
    src = inspect.getsource(k._link_sports_props_to_events)
    scans = re.findall(r"external_id ~ '\^KX\(([A-Z|]+)\)", src)
    assert scans, "the candidate scan's league alternation was not found"
    for alternation in scans:
        assert set(alternation.split("|")) == set(k._KALSHI_GAME_LEAGUES), (
            f"scan admits {alternation.split('|')} but the deriver knows "
            f"{list(k._KALSHI_GAME_LEAGUES)} — the difference is unreachable"
        )


def test_every_supported_league_has_a_reporting_label():
    for league in k._KALSHI_GAME_LEAGUES:
        assert f"KX{league}GAME" in k._KALSHI_SPORT_BY_GAME_PREFIX


# ── The rail itself ─────────────────────────────────────────────────────────
class _Row:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class _Result:
    def __init__(self, rows=(), rowcount=0):
        self._rows = list(rows)
        self.rowcount = rowcount

    def fetchall(self):
        return self._rows


class _Session:
    """Routes on SQL markers; records what the rail would write."""

    def __init__(self, candidates, game_tickers):
        self._candidates = candidates
        self._game_tickers = game_tickers
        self.written: dict[int, int] = {}
        self.committed = False

    async def execute(self, stmt, params=None):
        sql = str(stmt)
        if "status = 'resolved'" in sql and "event_id IS NULL" in sql:
            return _Result(
                _Row(id=mid, external_id=ext) for mid, ext in self._candidates
            )
        if "GAME-'" in sql and "event_id IS NOT NULL" in sql:
            return _Result(
                _Row(external_id=ext, event_id=eid)
                for ext, eid in self._game_tickers.items()
            )
        if "UPDATE futures_markets fm" in sql:
            for mid, eid in zip(params["mids"], params["eids"]):
                self.written[mid] = eid
            return _Result(rowcount=len(params["mids"]))
        if "UPDATE futures_outcomes" in sql:
            return _Result(rowcount=0)
        raise AssertionError(f"unexpected statement: {sql[:120]}")

    async def commit(self):
        self.committed = True


def _install(monkeypatch, session):
    class _CM:
        async def __aenter__(self):
            return session

        async def __aexit__(self, *a):
            return False

    monkeypatch.setattr(k, "get_task_session", lambda: _CM())
    return session


GAME_TICKERS = {NFL_GAME: NFL_EVENT, MLB_GAME: MLB_EVENT, NHL_GAME: NHL_EVENT}


@pytest.mark.asyncio
async def test_the_filed_row_links_to_the_event_its_game_market_already_holds(
    monkeypatch,
):
    """`60617215` acquires 14632820 from `KXNFLGAME-26SEP10SFLAR`, not from a
    hand-picked id and not from its name."""
    s = _install(monkeypatch, _Session([(60617215, NFL_PROP)], GAME_TICKERS))
    stats = await k._link_sports_props_to_events()
    assert s.written == {60617215: NFL_EVENT}
    assert stats["total_linked"] == 1
    assert stats["by_sport"] == {"football": 1}
    assert stats["no_game_sibling"] == 0


@pytest.mark.asyncio
async def test_a_three_segment_inning_prop_links(monkeypatch):
    s = _install(monkeypatch, _Session([(1, MLB_PROP)], GAME_TICKERS))
    stats = await k._link_sports_props_to_events()
    assert s.written == {1: MLB_EVENT}
    assert stats["by_sport"] == {"baseball": 1}


@pytest.mark.asyncio
async def test_the_hockey_population_that_already_linked_still_links(monkeypatch):
    s = _install(monkeypatch, _Session([(2, NHL_PROP)], GAME_TICKERS))
    stats = await k._link_sports_props_to_events()
    assert s.written == {2: NHL_EVENT}
    assert stats["by_sport"] == {"hockey": 1}


@pytest.mark.asyncio
async def test_season_long_families_are_refused_and_counted(monkeypatch):
    """The id-anchor is the guard: no sibling ticker, no link. These must stay
    refused for the RIGHT reason — `no_game_sibling`/`no_parent_family`, not an
    empty candidate scan, which would refuse them by accident."""
    candidates = [(100 + i, t) for i, t in enumerate(SEASON_FAMILIES)]
    s = _install(monkeypatch, _Session(candidates, GAME_TICKERS))
    stats = await k._link_sports_props_to_events()
    assert s.written == {}
    assert stats["total_linked"] == 0
    assert stats["candidates"] == len(SEASON_FAMILIES)
    assert stats["no_game_sibling"] + stats["no_parent_family"] == len(SEASON_FAMILIES)


@pytest.mark.asyncio
async def test_a_prop_whose_game_is_itself_unlinked_is_left_alone(monkeypatch):
    """The parent must already hold an event. An unlinked game market is not a
    licence to invent one."""
    s = _install(monkeypatch, _Session([(3, MLB_PROP)], {NFL_GAME: NFL_EVENT}))
    stats = await k._link_sports_props_to_events()
    assert s.written == {}
    assert stats["no_game_sibling"] == 1


@pytest.mark.asyncio
async def test_the_rail_never_borrows_a_different_games_event(monkeypatch):
    """Same league, same date, different teams — the key differs, so nothing
    links. This is the mis-attachment the ±28h name match would risk."""
    other_game = "KXMLBGAME-26AUG231335TBBAL"
    s = _install(monkeypatch, _Session([(4, MLB_PROP)], {other_game: 15290956}))
    stats = await k._link_sports_props_to_events()
    assert s.written == {}
    assert stats["no_game_sibling"] == 1


@pytest.mark.asyncio
async def test_a_mixed_population_links_only_its_anchored_half(monkeypatch):
    candidates = [
        (60617215, NFL_PROP),
        (1, MLB_PROP),
        (2, NHL_PROP),
    ] + [(100 + i, t) for i, t in enumerate(SEASON_FAMILIES)]
    s = _install(monkeypatch, _Session(candidates, GAME_TICKERS))
    stats = await k._link_sports_props_to_events()
    assert s.written == {60617215: NFL_EVENT, 1: MLB_EVENT, 2: NHL_EVENT}
    assert stats["candidates"] == 3 + len(SEASON_FAMILIES)
    assert stats["planned"] == 3
    assert stats["total_linked"] == 3
    assert stats["by_sport"] == {"football": 1, "baseball": 1, "hockey": 1}
    assert s.committed is True


@pytest.mark.asyncio
async def test_writes_are_batched_rather_than_one_statement_per_row(monkeypatch):
    """~11K rows link on the first pass; one UPDATE per row is that many round
    trips inside a phase other phases' budget gates sit below."""
    candidates = [(1000 + i, MLB_PROP) for i in range(2500)]
    session = _Session(candidates, GAME_TICKERS)
    statements = []

    original = session.execute

    async def counting(stmt, params=None):
        if "UPDATE futures_markets fm" in str(stmt):
            statements.append(len(params["mids"]))
        return await original(stmt, params)

    session.execute = counting
    _install(monkeypatch, session)
    stats = await k._link_sports_props_to_events()

    assert stats["planned"] == 2500
    assert sum(statements) == 2500
    assert len(statements) <= 3, f"2,500 rows took {len(statements)} statements"
