"""#11234 — Spanish municipal elections are not Valorant.

THE READER'S DEFECT (#2169 post-apply reader check, 2026-10-18, 390px):
`/futures/35418786` ("Most kills on a single map at Masters London 2026?")
lists "Valladolid municipal election winner?" and "Valencia municipal election
winner?" under **More Esports**. The served feed with `tags=["sport:esports"]`
returns both as `esports`, grouped `kalshi:KXVALLADOLIDCOUNCIL-27MAY23` and
`kalshi:KXVALENCIACOUNCIL-27MAY23`.

Same mechanism as #7042 / #8497. The legacy esports stem `kxval` claims every
KXVAL* series by `startswith`, so KXVALLADOLIDCOUNCIL and KXVALENCIACOUNCIL
answer esports at step 1 of `_categorize_kalshi_market`, which is authoritative,
and `_resolve_series_tag_result` never asks the venue. Both Kalshi category
writers (the poll upsert and `backfill_settled_gap_creation`) make exactly
those two calls, so the fix is at the shared accessor, not at either writer.

The specimens are the event tickers from the served group ids, not guessed
market suffixes. No venue `/series` read was taken for this ship, so the
controls below are the Valorant series this repo registers by name plus the
bare legacy alias, not a census of every KXVAL* series on Kalshi.

WHAT WOULD MAKE THIS FILE VACUOUS: a matcher that answered None for everything,
or a deleted `kxval` stem. The esports controls fail on both, and the strawman
re-runs the specimens without the carve-out and requires the old wrong answer.
"""

import pytest

import app.tasks.kalshi as kalshi_module
import app.utils.sport_keys as sport_keys
from app.tasks.kalshi import _categorize_kalshi_market, _resolve_series_tag_result
from app.utils.sport_keys import (
    get_sport_key_from_ticker,
    is_kalshi_game_level_ticker,
)

#: (served event ticker, served name, series ticker)
ELECTIONS = [
    (
        "KXVALLADOLIDCOUNCIL-27MAY23",
        "Valladolid municipal election winner?",
        "KXVALLADOLIDCOUNCIL",
    ),
    (
        "KXVALENCIACOUNCIL-27MAY23",
        "Valencia municipal election winner?",
        "KXVALENCIACOUNCIL",
    ),
]

#: Genuine esports through the same stem family: every Valorant prefix the two
#: maps register, the bare legacy alias, and a sibling esports futures series.
ESPORTS_CONTROLS = [
    "KXVALORANTGAME-26OCT18TEAMATEAMB",
    "KXVALORANTMAP-26OCT18TEAMATEAMB",
    "KXVALORANTTOTALMAPS-26OCT18TEAMATEAMB",
    "KXVALORANT-26WIN",
    "KXVALORANTMASTERSFINALS-26WIN",
    "KXVALORANTGAMETEAM-26",
    "KXEWCVALORANT-26",
    "KXVAL-26WIN",
    "KXLOLWORLDS-26WIN",
]


@pytest.mark.parametrize("ticker,_name,_series", ELECTIONS)
def test_the_council_series_are_not_claimed_by_esports(ticker, _name, _series):
    assert get_sport_key_from_ticker(ticker) is None


@pytest.mark.parametrize("ticker", ESPORTS_CONTROLS)
def test_genuine_valorant_and_esports_series_are_still_esports(ticker):
    assert get_sport_key_from_ticker(ticker) == "esports"


def test_another_councils_series_was_never_esports():
    """Adjacent family control: a council series outside the VAL stem is
    unmapped before and after, so the carve-out is about the stem, not the word."""
    assert get_sport_key_from_ticker("KXMADRIDCOUNCIL-27MAY23") is None


def test_game_vs_futures_precedence_is_unchanged_for_valorant():
    """A Valorant game leg is still game-level; the series futures is not."""
    assert is_kalshi_game_level_ticker("KXVALORANTGAME-26OCT18TEAMATEAMB")
    assert not is_kalshi_game_level_ticker("KXVALORANTMASTERSFINALS-26WIN")


def test_the_old_matcher_would_fail_this_file(monkeypatch):
    """Strawman: without the carve-out both specimens answer esports again."""
    monkeypatch.setattr(sport_keys, "KALSHI_TICKER_PREFIXES_NOT_A_SPORT", frozenset())
    for ticker, _name, _series in ELECTIONS:
        assert sport_keys.get_sport_key_from_ticker(ticker) == "esports"


# ── the writer's two calls, in the order both writers make them ──────────────


class _FakeService:
    def __init__(self, metadata):
        self.metadata = metadata
        self.calls = []

    async def get_series_metadata(self, series_ticker):
        self.calls.append(series_ticker)
        return self.metadata.get(series_ticker)


@pytest.fixture
def _fresh_series_caches(monkeypatch):
    monkeypatch.setattr(kalshi_module, "_SERIES_TAG_CACHE", {})
    monkeypatch.setattr(kalshi_module, "_SERIES_CATEGORY_CACHE", {})
    monkeypatch.setattr(kalshi_module, "_SERIES_TAG_FAILURE_UNTIL", {})


@pytest.mark.asyncio
@pytest.mark.parametrize("venue_category", ["Elections", "Politics"])
@pytest.mark.parametrize("ticker,name,series", ELECTIONS)
async def test_the_writer_asks_the_venue_and_files_them_under_politics(
    _fresh_series_caches, ticker, name, series, venue_category
):
    """Before: the map hit short-circuited the series fetch and step 1
    answered esports. Now the venue is asked and its topic decides."""
    service = _FakeService(
        {series: {"ticker": series, "tags": [], "category": venue_category}}
    )
    meta = await _resolve_series_tag_result(service, ticker)
    assert service.calls == [series]
    assert meta.resolved
    got = _categorize_kalshi_market(
        name,
        venue_category,
        event_ticker=ticker,
        series_tag=meta.tag,
        series_category=meta.category,
        series_evidence_unresolved=not meta.resolved,
    )
    assert got == "politics"


@pytest.mark.parametrize("ticker,name,_series", ELECTIONS)
def test_an_unanswered_venue_still_never_writes_esports(ticker, name, _series):
    """A 429 on the series read leaves only the event category and the name;
    neither says esports, and step 1 no longer does either."""
    got = _categorize_kalshi_market(
        name,
        "Elections",
        event_ticker=ticker,
        series_tag=None,
        series_category=None,
        series_evidence_unresolved=True,
    )
    assert got != "esports"


@pytest.mark.asyncio
async def test_a_valorant_series_still_costs_no_venue_call(_fresh_series_caches):
    service = _FakeService({})
    result = await _resolve_series_tag_result(
        service, "KXVALORANTGAME-26OCT18TEAMATEAMB"
    )
    assert result.not_asked
    assert service.calls == []


def test_a_valorant_series_still_answers_esports_through_the_cascade():
    """Control for the cascade arm: step 1 still answers for the real sport,
    even against a non-sport venue category."""
    got = _categorize_kalshi_market(
        "Valorant Masters Finals winner?",
        "Elections",
        event_ticker="KXVALORANTMASTERSFINALS-26WIN",
        series_tag=None,
        series_category="Elections",
    )
    assert got == "esports"


# ── the admin sweep must not undo it ─────────────────────────────────────────


class _Result:
    rowcount = 0


class _RecordingDb:
    def __init__(self):
        self.statements = []

    async def execute(self, stmt, params=None):
        self.statements.append((str(stmt), dict(params or {})))
        return _Result()

    async def commit(self):
        pass


@pytest.mark.asyncio
async def test_the_bulk_ticker_sweep_does_not_restamp_them_esports(monkeypatch):
    """`fix-sport-categories` sweeps `LIKE 'kxval%'`; without the carve-out it
    would write esports back onto both council series after any repair."""
    from app.routes import admin_matching

    monkeypatch.setattr(admin_matching, "_check_admin_secret", lambda *a, **k: None)
    db = _RecordingDb()
    await admin_matching.fix_sport_categories(request=None, secret="x", db=db)

    kxval = [(sql, p) for sql, p in db.statements if p.get("pattern") == "kxval%"]
    assert len(kxval) == 1
    sql, params = kxval[0]
    assert "NOT LIKE" in sql
    for carved in ("kxvalladolidcouncil%", "kxvalenciacouncil%"):
        assert carved in params.values()
        assert all(carved in p.values() for _, p in db.statements), carved
