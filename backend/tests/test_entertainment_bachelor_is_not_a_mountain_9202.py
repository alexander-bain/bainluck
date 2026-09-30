"""#9202 — Mt. Bachelor is a ski resort, and `startswith("kxbachelor")` cannot tell.

THE READER'S COMPLAINT, from a production LOOK at phone width on 2026-09-27
20:12Z (`artifacts/lane1b-2010Z/ent-390-realitytv-BEFORE.png`). Under MOVIES &
TV → Reality TV, the second card, between "What will be said during Episode 41
of Big Brother?" and "Big Brother Season 28 · 2nd place", was:

    When will Mt. Bachelor open for the 26/27 winter season?   (KXBACHELOROPEN-27)

It is #7298's collision with a third prefix. `kxbachelor` sat bare in both
`_THEME_BY_TICKER` and `_KIND_BY_TICKER`, and the name fallback would have
caught it anyway: `\\bbachelor\\b` matches "Mt. Bachelor". The census of every
Kalshi `KXBACHELOR*` series on 2026-09-27: `KXBACHELORETTE`,
`KXBACHELORETTEELIMINATION`, `KXBACHELORETTEFIR` (the show) and
`KXBACHELOROPEN` (the mountain). The mountain's 20 sibling ski-opening series
are all stored as weather; only it was filed entertainment upstream.

WHAT WOULD MAKE THIS FILE VACUOUS: a classifier that refuses everything passes
every "not reality" assertion. `test_the_bachelorette_still_reads_as_reality_tv`
is the control, and `test_the_retired_bare_prefix_would_fail_this_file` re-runs
the specimen under the old table and requires it to misfile.
"""

import re
from types import SimpleNamespace

import pytest

from app.routes.entertainment import (
    _KIND_BY_NAME,
    _KIND_BY_TICKER,
    _THEME_BY_TICKER,
    _classify_kind,
    _classify_theme,
)

SPECIMEN = (
    "KXBACHELOROPEN-27",
    "When will Mt. Bachelor open for the 26/27 winter season?",
)

# Real production rows (ids 1154050, 16756427, 1234346 and the resolved FIR
# series), with their real names.
BACHELORETTE = [
    ("KXBACHELORETTE-27JAN01", "Who will win The Bachelorette Season 22?"),
    ("KXBACHELORETTEELIMINATION-26JUL01", "Which participants will be eliminated in Episode 1 of The Bachelorette?"),
    ("KXBACHELORETTEFIR-26JUL01", 'Who will receive the "First Impression Rose" on The Bachelorette?'),
    ("KXBROADCASTBACHELORETTE-27JAN01", "The Bachelorette S22: Will ABC air an episode in 2026?"),
    ("228429", "Bachelorette Season 22 Winner"),
]


def _m(external_id: str, name: str):
    return SimpleNamespace(external_id=external_id, name=name)


def test_mt_bachelor_is_refused_by_the_page():
    theme = _classify_theme(_m(*SPECIMEN))
    assert theme == "excluded", theme


def test_mt_bachelor_is_not_a_reality_card():
    assert _classify_kind(_m(*SPECIMEN), 5) != "reality"


@pytest.mark.parametrize(
    "external_id,name",
    [
        ("KXBIGSKYOPEN-27", "When will Big Sky open for the 26/27 winter season?"),
        ("KXALTAOPEN-27", "When will Alta open for the 26/27 winter season?"),
        ("KXBRECKOPEN-27", "When will Breckenridge Ski Resort open for the 26/27 winter season?"),
    ],
)
def test_a_ski_season_opening_is_refused_whatever_the_resort_sounds_like(external_id, name):
    # "Big Sky" is also a TV show; a sibling misfiled upstream the way Mt.
    # Bachelor was must not reach a section either.
    assert _classify_theme(_m(external_id, name)) == "excluded"


@pytest.mark.parametrize("name", ["Mt. Bachelor snowfall this winter", "Mount Bachelor snowfall this winter", "Mt Bachelor snowfall this winter"])
def test_the_name_fallback_reads_the_mountain_as_no_show(name):
    m = _m("0xabc", name)
    assert _classify_theme(m) != "tv_streaming"
    assert _classify_kind(m, 2) != "reality"


@pytest.mark.parametrize("external_id,name", BACHELORETTE)
def test_the_bachelorette_still_reads_as_reality_tv(external_id, name):
    m = _m(external_id, name)
    assert _classify_theme(m) == "tv_streaming"
    assert _classify_kind(m, 6) == "reality"


def test_a_bare_the_bachelor_series_and_name_still_read_as_reality_tv():
    m = _m("KXBACHELOR-27JAN01", "Who will win The Bachelor Season 30?")
    assert _classify_theme(m) == "tv_streaming"
    assert _classify_kind(m, 6) == "reality"
    by_name = _m("0xabc", "Who will win The Bachelor Season 30?")
    assert _classify_theme(by_name) == "tv_streaming"
    assert _classify_kind(by_name, 6) == "reality"


def test_no_ticker_prefix_is_the_bare_stem():
    for table in (_THEME_BY_TICKER, _KIND_BY_TICKER):
        assert "kxbachelor" not in [p for p, _ in table]


def test_the_retired_bare_prefix_would_fail_this_file():
    ext, name = SPECIMEN
    old_ticker = [("kxbachelor", "reality")]
    assert any(ext.lower().startswith(p) for p, _ in old_ticker)
    old_name = re.compile(r"\b(?:survivor|bachelor|bachelorette|beast\s*games|big\s*brother|reality)\b", re.I)
    assert old_name.search(name)
    # and the live name table no longer matches it
    assert not any(p.search(name) and k == "reality" for p, k in _KIND_BY_NAME)
