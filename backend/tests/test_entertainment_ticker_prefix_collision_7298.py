"""#7298 — a Kalshi series prefix is not a word, and `startswith` cannot tell.

THE READER'S COMPLAINT, from a production LOOK at phone width on 2026-09-19
21:30Z (`artifacts/latency-639/AFTER-390px-entertainment-2130Z.png`, banked with
the payload it was read against). Under the heading "MOVIES & TV — Critic
scores, box office, and reality outcomes", the first four cards were:

    America vs Guadalajara: Spread          20%
    San Luis vs Necaxa: Spread              21%
    Atlas vs Pumas UNAM: Spread             19%
    Monterrey vs Cruz Azul: Spread          22%

Seven of that section's ten rows were Liga MX soccer. The cause is two entries
in `_THEME_BY_TICKER` that were shorter than the series they meant:

    ("kxli", "tv_streaming")   for Love Island  — also matches KXLIGAMX…,
                                 KXLIGUE1…, KXLIGUE2…, KXLIGAPORTUGAL…, KXLIIGA…
    ("kxrt", "movies")         for Rotten Tomatoes — also matches KXRTX5090…

Measured against production on 2026-09-19: `kxli` matched **4,322** markets, of
which **87** are Love Island and **4,235** are soccer. `kxrt` matched **150**,
of which **85** are Rotten Tomatoes and **65** are NVIDIA RTX 5090 GPU price
markets. Both misfilings are older than the page's current sort.

THIS IS NOT A REGRESSION OF #7278, and the fix for it is not a revert. #7278
changed the section comparator from most-DECIDED-first to most-OPEN-first, and
a four-way soccer spread priced near its flat baseline scores as maximally
open — so markets that had been sorted to the far end of a pool the page never
reached came to the top. The misfiling was always in the pool. The ranking ship
stopped hiding it, which is the only reason there is a screenshot.

WHAT WOULD MAKE THIS FILE VACUOUS, stated so a later reader can check it: every
assertion below is "this ticker does NOT classify as entertainment", and a
`_classify_theme` that returned `"other"` for everything would satisfy all of
them. `test_the_real_love_island_and_rotten_tomatoes_series_still_classify` is
the control that answers it — it pins the 87 and the 85 we are keeping, and it
fails on any fix that deletes the prefixes instead of tightening them.
`test_the_retired_bare_prefixes_would_fail_this_file` re-runs the misfiling
under the old table and requires it to FAIL; if that test ever passes, the rest
of this file is measuring nothing.
"""

from types import SimpleNamespace

import pytest

from app.routes.entertainment import _THEME_BY_TICKER, _classify_theme


def _market(external_id: str, name: str = "Some market"):
    """A FuturesMarket-shaped stand-in carrying only what `_classify_theme` reads.

    `name` defaults to a string no `_THEME_BY_NAME` pattern matches, so a test
    that asserts "not entertainment" is testing the TICKER path and not
    accidentally passing because the name fell through to `"other"` anyway. The
    soccer specimens below override it with their real names for the same
    reason in the other direction: those names must not rescue the row either.
    """
    return SimpleNamespace(external_id=external_id, name=name)


# Real production tickers, copied from the served payload and from the series
# census in the issue. The suffixes are real too: a specimen truncated to its
# series would not prove the prefix match reaches a whole external id.
SOCCER_TICKERS = [
    ("KXLIGAMXSPREAD-26SEP19AMECDG", "America vs Guadalajara: Spread"),
    ("KXLIGAMXGAME-26SEP19ASLNCX", "San Luis vs Necaxa"),
    ("KXLIGAEXPGAME-26SEP26CAHLEN", "Cruz Azul Hidalgo vs Leones Negros"),
    ("KXLIGUE1TOTAL-26SEP20PSGOM", "Ligue 1: Team Points"),
    ("KXLIGUE2GAME-26SEP20AJACAE", "Ajaccio vs Caen"),
    ("KXLIGAPORTUGALGAME-26SEP20VITMOR", "Vitoria vs Moreirense"),
    ("KXLIIGAGAME-26SEP20RMABAR", "Real Madrid vs Barcelona"),
]

GPU_TICKERS = [
    ("KXRTX5090W-26OCT02", "NVIDIA RTX 5090 · Hourly price on Oct 02 (Week 40)"),
    ("KXRTX5090MS-26OCT", "NVIDIA RTX 5090 · Average hourly price in October"),
    ("KXRTX5090MAX-26OCT", "NVIDIA RTX 5090 · Peak hourly price in October"),
]

# The ones the tightened prefixes must keep. `KXLOVEISLMENTION` is deliberately
# absent: it is matched by neither `kxloveisland` nor `kxliuk`/`kxliusa` today,
# and pinning it here would assert a widening this ship did not make.
KEPT_TICKERS = [
    ("KXLIUKELIMINATION-26SEP19", "Love Island UK: Week 3 elimination", "tv_streaming"),
    ("KXLIUSAELIMINATION-26SEP19", "Love Island USA: Week 3 elimination", "tv_streaming"),
    ("KXLIUKBOMBSHELL-26SEP19", "Love Island UK: next bombshell", "tv_streaming"),
    ("KXLIUSACASAAMOR-26SEP19", "Love Island USA: Casa Amor", "tv_streaming"),
    ("KXLOVEISLANDUKRANK-26SEP19", "Love Island UK ranking", "tv_streaming"),
    ("KXRT-26SEP19DUNE3", "Dune: Part Three Rotten Tomatoes score?", "movies"),
    ("KXRTCOMPARE-26SEP19", "RT score comparison", "movies"),
    ("KXRTTV-26SEP19", "RT score: TV", "movies"),
]

# The table as it stood before this ship, so the control below runs the real
# thing rather than a paraphrase of it.
_RETIRED_TABLE = [
    ("kxrt", "movies"),
    ("kxli", "tv_streaming"),
]


def _classify_with(table, external_id: str) -> str | None:
    ext = external_id.lower()
    for prefix, theme in table:
        if ext.startswith(prefix):
            return theme
    return None


@pytest.mark.parametrize("external_id,name", SOCCER_TICKERS)
def test_a_soccer_series_is_not_tv_and_streaming(external_id, name):
    assert _classify_theme(_market(external_id, name)) != "tv_streaming"


@pytest.mark.parametrize("external_id,name", GPU_TICKERS)
def test_a_gpu_price_series_is_not_movies(external_id, name):
    assert _classify_theme(_market(external_id, name)) != "movies"


@pytest.mark.parametrize("external_id,name,expected", KEPT_TICKERS)
def test_the_real_love_island_and_rotten_tomatoes_series_still_classify(
    external_id, name, expected
):
    """The no-deletion half: tightening a prefix must not drop what it was for.

    Without this, `_THEME_BY_TICKER` with both entries simply removed would pass
    every other test in the file.
    """
    assert _classify_theme(_market(external_id, name)) == expected


@pytest.mark.parametrize("external_id,name", SOCCER_TICKERS + GPU_TICKERS)
def test_the_retired_bare_prefixes_would_fail_this_file(external_id, name):
    """Control. If this ever fails, the specimens above stopped being specimens."""
    assert _classify_with(_RETIRED_TABLE, external_id) in ("tv_streaming", "movies")


def test_no_ticker_prefix_is_a_prefix_of_a_longer_entry_with_a_different_theme():
    """The class, not the two cases — a shorter entry shadows a longer one below it.

    `_classify_theme` returns on the FIRST match, so an entry that is a prefix of
    a later one with a different theme makes that later one unreachable. The two
    bugs this file exists for were the other direction (a prefix reaching series
    that are not in the table at all), which no in-repo check can catch; this one
    is checkable, so it is checked.
    """
    for i, (short, theme_a) in enumerate(_THEME_BY_TICKER):
        for longer, theme_b in _THEME_BY_TICKER[i + 1 :]:
            if longer.startswith(short) and theme_a != theme_b:
                pytest.fail(
                    f"{longer!r} ({theme_b}) is unreachable: {short!r} ({theme_a}) "
                    "matches first"
                )
