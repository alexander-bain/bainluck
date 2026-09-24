"""#7042 — the Producers Guild of America's awards are not golf.

THE READER'S COMPLAINT (shopper 0033, 2026-09-24 01:23Z, `/hub/golf` at 390px):
the lead card under "Upcoming tournaments" was "PGA Award for Best Televised or
Streamed Motion Picture?" — one of seven open KXPGAAWARDS markets badged golf.

The cause is step 1 of `_categorize_kalshi_market`: the bare `kxpga` stem (#949)
claims every KXPGA* series by `startswith`, and step 1 is documented as
authoritative, so neither the venue's series tag nor its `Entertainment`
category was ever consulted.

WHY AN EXCLUSION AND NOT A STEM DELETION, measured on production 2026-09-24:
57 (series, category, status) groups under KXPGA*, every one golf, and all but
KXPGAAWARDS genuinely golf. Most of them (KXPGA3BALL 1,354 rows, KXPGAROUNDSCORE,
KXPGATIGER, KXPGARYDER, …) have no longer registered prefix, so deleting `kxpga`
would strip golf from ~40 series to fix one. The GOLF_CONTROLS below are drawn
from that census and fail on the deletion.

WHAT WOULD MAKE THIS FILE VACUOUS: a `get_sport_key_from_ticker` that returned
None for everything passes the awards assertions. The golf and baseball
controls answer that, and `test_the_old_matcher_would_fail_this_file` re-runs the
specimen without the exclusion and requires it to answer golf.
"""

import pytest

import app.utils.sport_keys as sport_keys
from app.tasks import kalshi as kalshi_module
from app.tasks.kalshi import _categorize_kalshi_market, _resolve_series_tag_result
from app.utils.sport_keys import (
    KALSHI_FUTURES_TICKER_TO_SPORT_KEY,
    KALSHI_TICKER_PREFIXES_NOT_A_SPORT,
    KALSHI_TICKER_TO_SPORT_KEY,
    get_sport_key_from_ticker,
)

#: The seven open rows, by the market suffixes the issue quotes; the names are
#: the served titles.
AWARDS = [
    ("KXPGAAWARDS-26-PIC", "PGA Award for Best Theatrical Motion Picture?"),
    ("KXPGAAWARDS-26-DOC", "PGA Award for Best Documentary Motion Picture?"),
    ("KXPGAAWARDS-26-ANI", "PGA Award for Best Animated Theatrical Motion Picture?"),
    ("KXPGAAWARDS-26-DRA", "PGA Award for Best Television - Drama?"),
    ("KXPGAAWARDS-26-COM", "PGA Award for Best Television - Comedy?"),
    ("KXPGAAWARDS-26-LIM", "PGA Award for Best Limited or Anthology Series?"),
    ("KXPGAAWARDS-26-TEL", "PGA Award for Best Televised or Streamed Motion Picture?"),
]

#: Real KXPGA* series from the 2026-09-24 census. The first group reaches golf
#: ONLY through the bare stem — they are what a stem deletion would break.
GOLF_CONTROLS = [
    "KXPGA3BALL-26SEP20",
    "KXPGAROUNDSCORE-26SEP20",
    "KXPGATIGER-26",
    "KXPGARYDER-27",
    "KXPGACURRY-26",
    "KXPGAFUTURE-26",
    "KXPGARETURN-26",
    "KXPGACOMPETE-26",
    # Registered explicitly (#949's list):
    "KXPGATOUR-26TOUR",
    "KXPGAMAKECUT-26SEP20",
    "KXPGATOP10-26SEP20",
    "KXPGAH2H-26SEP20",
    "KXPGAWINNINGSCORE-26SEP20",
    # And the sibling tour the stem must not reach at all:
    "KXLPGATOUR-26",
]


@pytest.mark.parametrize("ticker,_name", AWARDS)
def test_the_producers_guild_awards_are_not_claimed_by_a_sport(ticker, _name):
    assert get_sport_key_from_ticker(ticker) is None


@pytest.mark.parametrize("ticker", GOLF_CONTROLS)
def test_every_real_golf_series_is_still_golf(ticker):
    assert get_sport_key_from_ticker(ticker) == "golf"


def test_kxmlbcba_is_unchanged():
    """The row that refutes the wider fix (#7042): the venue files it under
    Entertainment and it is genuinely baseball."""
    assert get_sport_key_from_ticker("KXMLBCBA-26DEC02") == "baseball_mlb"


@pytest.mark.parametrize("ticker,name", AWARDS)
def test_the_cascade_files_the_awards_under_the_venues_topic(ticker, name):
    """End to end through step 1 → 1b → 2: the name rule may still read "PGA"
    as golf, and #7012's topic demotion hands the row to entertainment."""
    event_ticker = ticker.rsplit("-", 1)[0]
    got = _categorize_kalshi_market(
        name,
        "Entertainment",
        event_ticker=event_ticker,
        series_tag=None,
        series_category="Entertainment",
    )
    assert got == "entertainment"


def test_a_golf_ticker_still_wins_over_an_entertainment_category():
    """Control for the cascade test: step 1 still answers for real golf."""
    got = _categorize_kalshi_market(
        "Tiger Woods to return in 2026?",
        "Entertainment",
        event_ticker="KXPGATIGER-26",
        series_category="Entertainment",
    )
    assert got == "golf"


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
async def test_the_venue_is_asked_about_the_awards_series(_fresh_series_caches):
    """Before: a map hit short-circuited the fetch, so the venue's
    `Entertainment` was never read. Now the series is asked about."""
    service = _FakeService(
        {"KXPGAAWARDS": {"ticker": "KXPGAAWARDS", "tags": [], "category": "Entertainment"}}
    )
    result = await _resolve_series_tag_result(service, "KXPGAAWARDS-26")
    assert service.calls == ["KXPGAAWARDS"]
    assert result.category == "Entertainment"
    assert result.tag is None


@pytest.mark.asyncio
async def test_a_golf_series_still_costs_no_venue_call(_fresh_series_caches):
    service = _FakeService({})
    result = await _resolve_series_tag_result(service, "KXPGA3BALL-26SEP20")
    assert result.not_asked
    assert service.calls == []


# ── the property, not the rows ───────────────────────────────────────────────


@pytest.mark.parametrize("entry", sorted(KALSHI_TICKER_PREFIXES_NOT_A_SPORT))
def test_every_exclusion_shadows_a_real_sport_prefix(entry):
    """An entry is only here because a SHORTER sport prefix would otherwise
    claim it. One that nothing claims is dead weight; one that is itself a
    registered key contradicts the map it sits beside."""
    registered = {**KALSHI_TICKER_TO_SPORT_KEY, **KALSHI_FUTURES_TICKER_TO_SPORT_KEY}
    assert entry == entry.lower()
    assert entry not in registered
    shadowed = [p for p in registered if entry.startswith(p) and p != entry]
    assert shadowed, f"{entry!r} overrules no sport prefix — remove it"


@pytest.mark.parametrize("entry", sorted(KALSHI_TICKER_PREFIXES_NOT_A_SPORT))
def test_no_exclusion_swallows_a_registered_sport_prefix(entry):
    """The inverse hazard: an exclusion that is a prefix of a registered sport
    series would silently un-badge that whole series — a stem deletion wearing
    a different name."""
    registered = {**KALSHI_TICKER_TO_SPORT_KEY, **KALSHI_FUTURES_TICKER_TO_SPORT_KEY}
    swallowed = [p for p in registered if p.startswith(entry)]
    assert swallowed == []


def test_the_old_matcher_would_fail_this_file(monkeypatch):
    """Strawman: without the exclusion the specimen answers golf again."""
    monkeypatch.setattr(sport_keys, "KALSHI_TICKER_PREFIXES_NOT_A_SPORT", frozenset())
    assert sport_keys.get_sport_key_from_ticker("KXPGAAWARDS-26-PIC") == "golf"


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
async def test_the_bulk_ticker_sweep_does_not_restamp_the_awards_golf(monkeypatch):
    """`POST /prediction-markets/fix-sport-categories` sweeps `LIKE 'kxpga%'`;
    without the carve-out it would write golf back onto every repaired row."""
    from app.routes import admin_matching

    monkeypatch.setattr(admin_matching, "_check_admin_secret", lambda *a, **k: None)
    db = _RecordingDb()
    await admin_matching.fix_sport_categories(request=None, secret="x", db=db)

    kxpga = [(sql, p) for sql, p in db.statements if p.get("pattern") == "kxpga%"]
    assert len(kxpga) == 1
    sql, params = kxpga[0]
    assert "NOT LIKE" in sql
    assert "kxpgaawards%" in params.values()
    # Every statement carries it, so no longer or shorter prefix can reach it.
    assert all("kxpgaawards%" in p.values() for _, p in db.statements)
