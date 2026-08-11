"""LAT-P038/#1769 — the futures dedup key must identify a MARKET, not a category.

`president` returned exactly one market on production v3778 while **461 open,
unresolved markets matched the query**, across 182 distinct `group_id`s — Peru,
Brazil, Colombia, France, the 2028 party market, the midterms. So did `election`,
`presidential` and `presidential election`. Three passes, identical every time.

Two defects compounded, and these tests pin both.

**The key was a CATEGORY.** `_normalize_futures_dedup_key` short-circuited on
`FuturesMarket.canonical_market_key`, which `compute_canonical_market_key` builds
as `{sport}:{league}:{category}:{season}` — a taxonomy for counting cross-source
cohorts in calibration, with nothing in it that names a market. Counted in
production 2026-08-11 over open, unresolved markets: **20,818 carry a key and
there are 387 distinct values**; seven of those cover 14,765 markets;
`soccer::championship:2026` alone holds **8,475 markets with 8,452 distinct
names**. The trailing-year strip then merged separate election cycles on top.

**Dedup ran after `LIMIT 20`.** One collapsing key ate the window and the page
was left holding what survived, never refilling from rank 21+. The ordering is by
(tier, rank, market_tier, volume), so the highest-volume rows are the most likely
to share a coarse key: the two defects reinforced each other.

Measured over the REAL compiled predicate against production, 46 gold queries:
page rows **275 -> 348**, market-gold recall **46/51 -> 47/51** (one gain on
`election`, zero losses).
"""

from __future__ import annotations

import inspect
import re

import pytest

from app.routes import events as events_route

DEDUP_SRC = inspect.getsource(events_route._normalize_futures_dedup_key)
SEARCH_SRC = inspect.getsource(events_route.search_events)
SEARCH_CODE = "\n".join(
    line for line in SEARCH_SRC.splitlines() if not line.lstrip().startswith("#")
)


class _Market:
    """The three attributes the dedup key reads."""

    def __init__(self, name, canonical_market_key=None, market_tier=1):
        self.name = name
        self.canonical_market_key = canonical_market_key
        self.market_tier = market_tier


def key(name, ckey=None, tier=1):
    return events_route._normalize_futures_dedup_key(_Market(name, ckey, tier))


# --- the defect itself -------------------------------------------------------


def test_one_canonical_key_does_not_collapse_distinct_markets():
    """The `president` page, in miniature.

    Every one of these is a real open market that shared
    `politics:US:championship:2027` or `politics::championship:2027` in
    production, and every one is a different question.
    """
    names = [
        "Presidential Election Winner 2028",
        "Peru Presidential election winner?",
        "Brazil Presidential election winner?",
        "Colombian presidential election first round winner?",
        "2028 Presidential Election winner? (Party)",
        "France Presidential Election Winner",
    ]
    keys = {key(n, "politics:US:championship:2027") for n in names}
    assert len(keys) == len(names), (
        "markets sharing a canonical key collapsed to one search row — this is "
        "#1769: 461 open markets behind a single result"
    )


def test_the_canonical_key_is_not_consulted_at_all():
    """Same name, different canonical keys — the key must not change.

    A dedup identity that varies with a taxonomy field is not an identity. This
    is the mutation-visible half: reinstating the short-circuit splits this pair.
    """
    assert key("Peru Presidential election winner?", "politics:PE:championship:2026") == \
        key("Peru Presidential election winner?", "politics::other:2031")
    assert key("Oscar winner: Best Picture", None) == \
        key("Oscar winner: Best Picture", "entertainment:AWARDS:championship:2026")


def test_the_six_oscar_categories_are_six_rows():
    """Measured live: one canonical key held all six, so `oscars` showed one."""
    ckey = "entertainment:AWARDS:championship:2026"
    names = [
        "Oscar winner: Best Picture",
        "Oscar winner: Best Actor",
        "Oscar winner: Best Actress",
        "Oscar winner: Best Director",
        "Oscar winner: Best Supporting Actor",
        "Oscar winner: Best Supporting Actress",
    ]
    assert len({key(n, ckey) for n in names}) == 6


def test_a_market_and_a_players_next_team_are_not_the_same_question():
    """`celtics` collapsed nine NBA markets onto one row, including this pair."""
    ckey = "basketball:NBA:championship:2026"
    assert key("NBA: 2027 Champion", ckey) != key("NBA: LeBron James Next Team", ckey)


# --- what the key must still merge -------------------------------------------


def test_the_docstrings_own_example_still_merges():
    """"2026 NBA Champion" and "NBA Championship Winner" -> same key.

    This is the cross-source merge the canonical short-circuit was nominally
    there for, and it is the name path's job. Across all 46 gold queries the
    canonical arm was the ONLY thing merging exactly two pairs, both this shape;
    `_fold_dedup_punctuation` recovers both.
    """
    assert key("2026 NBA Champion") == key("NBA Championship Winner")
    assert key("NBA: 2027 Champion") == key("NBA Championship Winner")
    assert key("NHL: 2027 Champion") == key("NHL Championship Winner")


def test_matchup_order_still_does_not_matter():
    assert key("76ers vs. Celtics") == key("Celtics vs 76ers")
    assert key("Red Sox @ Yankees") == key("Yankees vs Red Sox")


def test_the_tier_still_separates_a_prop_from_a_championship():
    assert key("NBA Championship Winner", tier=1) != key("NBA Championship Winner", tier=3)


# --- the fold must SEPARATE, never delete ------------------------------------


def test_punctuation_becomes_a_space_so_decimals_survive():
    """Deleting punctuation maps "O/U 5.5" and "O/U 55" both onto `ou 55`.

    That would merge two different prop lines into one row — the same class of
    silent deletion this whole queue is fixing, introduced by the fix. A space
    keeps `5 5` and `55` apart.
    """
    assert key("Total Games O/U 5.5") != key("Total Games O/U 55")
    assert key("Team Total Over 2.5") != key("Team Total Over 25")


def test_the_fold_is_idempotent_and_whitespace_stable():
    assert key("NBA:  2027   Champion") == key("NBA: 2027 Champion")
    assert key("  Oscar winner: Best Picture  ") == key("Oscar winner: Best Picture")


# --- source oracles: the shape cannot silently come back ---------------------


def test_the_dedup_key_reads_no_taxonomy_field():
    """A behavioural test can be satisfied by a narrower short-circuit; this
    pins the rule itself. `canonical_market_key` is a CATEGORY by construction
    (`compute_canonical_market_key`), so no amount of qualifying makes it an
    identity."""
    assert "canonical_market_key" not in DEDUP_SRC.split('"""')[-1], (
        "the canonical short-circuit is back in _normalize_futures_dedup_key"
    )


def test_the_fold_uses_a_separator_not_an_empty_replacement():
    fold_src = inspect.getsource(events_route._fold_dedup_punctuation)
    body = fold_src.split('"""')[-1]
    assert re.search(r'sub\(\s*r?"\[\^a-z0-9\]\+"\s*,\s*" "', body), (
        "punctuation must be replaced with a SPACE — an empty replacement merges "
        "5.5 into 55"
    )


# --- defect 1b: the window cannot be starved ---------------------------------


def test_the_window_and_page_are_named_constants():
    assert events_route._SEARCH_FUTURES_PAGE == 10
    assert events_route._SEARCH_FUTURES_WINDOW == 20
    assert events_route._SEARCH_FUTURES_REFILL > 0
    assert events_route._SEARCH_FUTURES_WINDOW > events_route._SEARCH_FUTURES_PAGE, (
        "the window IS the page's only dedup headroom"
    )
    assert ".limit(20)" not in SEARCH_CODE, (
        "the futures window went back to a bare literal — the relationship "
        "between window and page becomes invisible again"
    )


def test_the_refill_is_bounded_and_deadline_aware():
    """It must pay only on an OBSERVED collapse, and never make the answer late.

    Measured over the 46-query gold set with the key fixed, this fires zero
    times — every saturated window now yields a full page. It exists for the
    failure MODE, not for today's cause, so it must not become a second
    unconditional query.
    """
    assert "_SEARCH_FUTURES_REFILL" in SEARCH_CODE
    refill = SEARCH_CODE[SEARCH_CODE.index("len(deduped_futures) < _SEARCH_FUTURES_PAGE"):]
    refill = refill[: refill.index("futures_markets = deduped_futures")]
    assert "len(futures_markets_raw) >= _SEARCH_FUTURES_WINDOW" in refill, (
        "the refill must require a SATURATED window — otherwise it re-queries "
        "for pages that are short because the corpus is short"
    )
    assert "time.monotonic() < _deadline" in refill, "refill must respect the deadline"
    assert ".offset(_SEARCH_FUTURES_WINDOW)" in refill, (
        "the refill must start after the window, or it re-fetches rows we have"
    )
    assert "while " not in refill, "one refill, never a loop"


def test_the_response_reports_a_collapse_it_could_not_fix():
    """A client cannot compute this: a correct one-row answer (`tush push`) and a
    collapsed one-row answer are the same response from outside. The candidate
    count lives only in the request, so the server has to say so."""
    assert '"futures_collapse"' in SEARCH_CODE
    collapse = SEARCH_CODE[SEARCH_CODE.index("_futures_collapsed = ("):]
    collapse = collapse[: collapse.index(")\n", collapse.index("_SEARCH_FUTURES_PAGE"))]
    assert "len(futures_markets_raw) >= _SEARCH_FUTURES_WINDOW" in collapse
    assert "len(futures_markets) < _SEARCH_FUTURES_PAGE" in collapse
    assert 'if _futures_collapsed else {}' in SEARCH_CODE, (
        "the key must be additive-when-true, like `degraded` — a key that is "
        "always present teaches readers to ignore it"
    )


@pytest.mark.parametrize(
    "name,ckey",
    [
        ("Will Wisconsin disenfranchise any voter for betting on elections?", "politics::championship:2027"),
        ("California Governor Election Winner", "politics:US:championship:2026"),
        ("Los Angeles mayoral election: first round winner", "politics::championship:2026"),
    ],
)
def test_every_election_market_keeps_its_own_row(name, ckey):
    """Regression net for the `election` probe, which GAINED its gold market
    (0 -> 1) when the collapse was removed: 112897 was being outranked by a row
    that had swallowed the whole page."""
    assert key(name, ckey) != key("Presidential Election Winner 2028", ckey)
