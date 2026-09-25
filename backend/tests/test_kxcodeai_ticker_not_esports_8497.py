"""#8497 — Kalshi's AI coding series are not Call of Duty; a wealth tax is not WTA tennis.

THE READER'S COMPLAINT (lane1b idle walk, 2026-09-25 00:2xZ, `GET /api/hub/esports`):
"Top Coding AI this month (DeepSWE)" (`KXCODEAI-26SEP30`) is listed on the
esports hub. The other open row, "Which AI company will have the best coding
model at the end of 2026?" (`KXCODINGMODEL-26DEC`), is also stored as esports.

Same mechanism as #7042. The bare Call of Duty stem `kxcod` claims every
KXCOD* series by `startswith`. Step 1 of `_categorize_kalshi_market` is
authoritative, so the venue's `Science and Technology`/`AI` was never read.

THE VENUE READ, not our mirror (Kalshi `/series`, all 14,378 series, 2026-09-25):
seven series start KXCOD. Five are `Sports`/`Esports` and are the controls
below. Two are AI. Running the same read over every non-`Sports` series the
ticker map claims found one more stem collision, KXWTAX "Wealth tax"
(`Politics`), claimed by `kxwta`. It has 0 stored rows, so it is latent.

WHAT WOULD MAKE THIS FILE VACUOUS: a matcher that answered None for everything.
The COD and WTA controls fail on that, and the strawman re-runs the specimens
without the carve-out and requires the old wrong answers.
"""

import pytest

import app.utils.sport_keys as sport_keys
from app.tasks.kalshi import _categorize_kalshi_market
from app.utils.sport_keys import get_sport_key_from_ticker

#: (ticker, served name, venue category, venue tag, expected cascade answer)
NOT_A_SPORT = [
    (
        "KXCODEAI-26SEP30",
        "Top Coding AI this month (DeepSWE)",
        "Science and Technology",
        "AI",
        "tech",
    ),
    (
        "KXCODINGMODEL-26DEC",
        "Which AI company will have the best coding model at the end of 2026?",
        "Science and Technology",
        "AI",
        "tech",
    ),
    ("KXWTAX-26", "Will a wealth tax pass?", "Politics", "Growth", "politics"),
]

#: Every venue series under the two stems that IS the sport (2026-09-25 read).
COD_CONTROLS = [
    "KXCOD-26",
    "KXCODGAME-26SEP27BOSOPT",
    "KXCODMAP-26SEP27BOSOPT",
    "KXCODSPREAD-26SEP27BOSOPT",
    "KXCODTOTALMAPS-26SEP27BOSOPT",
]
WTA_CONTROLS = [
    "KXWTA-26",
    "KXWTAMATCH-26SEP27SWIZHE",
    "KXWTAGAME-26SEP27SWIZHE",
    "KXWTATOURNWIN-26",
    "KXWTAGRANDSLAM-26",
    "KXWTAFINALS-26",
    "KXWTADOUBLES-26SEP27",
    "KXWTASETWINNER-26SEP27SWIZHE",
]


@pytest.mark.parametrize("ticker,_name,_cat,_tag,_want", NOT_A_SPORT)
def test_the_ai_and_tax_series_are_not_claimed_by_a_sport(ticker, _name, _cat, _tag, _want):
    assert get_sport_key_from_ticker(ticker) is None


@pytest.mark.parametrize("ticker", COD_CONTROLS)
def test_every_call_of_duty_series_is_still_esports(ticker):
    assert get_sport_key_from_ticker(ticker) == "esports"


@pytest.mark.parametrize("ticker", WTA_CONTROLS)
def test_every_wta_series_is_still_wta(ticker):
    assert get_sport_key_from_ticker(ticker) == "tennis_wta"


@pytest.mark.parametrize("ticker,name,category,tag,want", NOT_A_SPORT)
def test_the_cascade_files_them_under_the_venues_topic(ticker, name, category, tag, want):
    got = _categorize_kalshi_market(
        name,
        category,
        event_ticker=ticker,
        series_tag=tag,
        series_category=category,
    )
    assert got == want


def test_a_call_of_duty_series_still_answers_esports_through_the_cascade():
    """Control for the cascade arm: step 1 still answers for the real sport."""
    got = _categorize_kalshi_market(
        "Call of Duty League Championship Winner",
        "Sports",
        event_ticker="KXCOD-26",
        series_tag="Esports",
        series_category="Sports",
    )
    assert got == "esports"


def test_the_old_matcher_would_fail_this_file(monkeypatch):
    """Strawman: without the carve-out the specimens answer the old sports."""
    monkeypatch.setattr(sport_keys, "KALSHI_TICKER_PREFIXES_NOT_A_SPORT", frozenset())
    assert sport_keys.get_sport_key_from_ticker("KXCODEAI-26SEP30") == "esports"
    assert sport_keys.get_sport_key_from_ticker("KXCODINGMODEL-26DEC") == "esports"
    assert sport_keys.get_sport_key_from_ticker("KXWTAX-26") == "tennis_wta"


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
async def test_the_bulk_ticker_sweep_does_not_restamp_them(monkeypatch):
    """`fix-sport-categories` sweeps `LIKE 'kxcod%'` and `LIKE 'kxwta%'`;
    without the carve-out it would stamp esports / tennis back onto them."""
    from app.routes import admin_matching

    monkeypatch.setattr(admin_matching, "_check_admin_secret", lambda *a, **k: None)
    db = _RecordingDb()
    await admin_matching.fix_sport_categories(request=None, secret="x", db=db)

    for stem in ("kxcod%", "kxwta%"):
        hits = [p for _, p in db.statements if p.get("pattern") == stem]
        assert len(hits) == 1, stem
    for carved in ("kxcodeai%", "kxcodingmodel%", "kxwtax%"):
        assert all(carved in p.values() for _, p in db.statements), carved
