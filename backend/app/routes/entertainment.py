"""Entertainment & culture markets API endpoint.

Serves prediction-market entertainment data from Kalshi and Polymarket,
organized into themed sections: trending hero, music (Spotify/Billboard/albums),
movies & TV (RT scores/box office/reality), cultural moments, tech & culture.

Single endpoint returns the full response consumed by the frontend.
"""

import json
import logging
import re
from collections import defaultdict
from datetime import datetime, timezone
from fastapi import APIRouter, Depends
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import FuturesMarket
from app.services import get_db
from app.utils.hook_staleness import is_hook_stale
from app.utils.cross_source_matching import (
    # #2427 — the deduping pair, not bare `clean_outcomes`: every row this file
    # builds must also lose a Polymarket `_yes`/`_no` leg that duplicates a rung
    # already on the same market. Aliased so all of this file's existing call
    # sites pass through it unchanged.
    clean_and_dedupe_outcomes as _clean_outcomes,
    find_cross_source_markets,
    group_markets_by_group_id,
    is_resolved as _is_resolved,
    source as _source,
)
from app.utils.market_staleness import (
    should_exclude_from_featured,
    unobserved_board_keys,
)
# #8083 — THE FOURTH CALLER OF ONE HELPER, never a second spelling of it.
# Same import direction `events.py` and `league_futures.py` already take;
# `futures.py` imports none of the themed routes, so this closes no loop.
from app.routes.futures import (
    _board_has_a_verdict,
    _fleet_newest_observation,
    _withheld_price_outcome_ids,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# Sub-theme classification
# ---------------------------------------------------------------------------

_THEME_BY_TICKER: list[tuple[str, str]] = [
    ("kxnetflix", "tv_streaming"),
    ("kxdisney", "tv_streaming"),
    ("kxboxoffice", "movies"),
    ("kxoscars", "awards"),
    ("kxemmys", "awards"),
    ("kxgrammys", "awards"),
    ("kxgoldenglobe", "awards"),
    ("kxspotify", "music"),
    ("kxbillboard", "music"),
    ("kxsurvivor", "tv_streaming"),
    ("kxyoutube", "social_media"),
    ("kxtiktok", "social_media"),
    ("kxtwitter", "social_media"),
    ("kxeurovision", "music"),
    ("kxrottentomatoes", "movies"),
    # `kxrt` USED TO BE BARE, and `str.startswith` has no idea a ticker ends.
    # Kalshi's Rotten Tomatoes series is the bare `KXRT-…`, but `kxrt` is also a
    # prefix of `KXRTX5090…` — 65 NVIDIA RTX 5090 GPU price markets, which this
    # page filed under MOVIES and rendered as critic-score side markets ("NVIDIA
    # RTX 5090 · Hourly price on Oct 02" sat in `movies_tv.side_markets`).
    # `KXRTCOMPARE` and `KXRTTV` are real Rotten Tomatoes series and are named
    # rather than swept, because the only thing separating them from the GPUs is
    # that we know what they are. 85 kept / 65 dropped, measured 2026-09-19.
    ("kxrt-", "movies"),
    ("kxrtcompare", "movies"),
    ("kxrttv", "movies"),
    ("kxbeastgames", "tv_streaming"),
    ("kxbachelor", "tv_streaming"),
    ("kxloveisland", "tv_streaming"),
    # Same collision, four characters and three orders of magnitude worse.
    # `kxli` was here for Love Island's real tickers (`KXLIUK…`, `KXLIUSA…`), and
    # it also matched `KXLIGAMX…`, `KXLIGUE1…`, `KXLIGUE2…`, `KXLIGAPORTUGAL…`
    # and `KXLIIGA…` — 4,235 SOCCER markets against 87 Love Island ones, every
    # one of them filed as TV & streaming. After #7278 sorted the sections
    # most-OPEN-first these stopped being buried: a four-way soccer spread sits
    # near its flat baseline, so it scores as maximally open, and Liga MX took
    # positions 1-4 of MOVIES & TV. The ranking ship did not cause this — it
    # stopped hiding it.
    ("kxliuk", "tv_streaming"),
    ("kxliusa", "tv_streaming"),
    ("kxpodcast", "social_media"),
    ("kxelon", "social_media"),
    ("kxmusk", "social_media"),
]

_THEME_BY_NAME: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\b(?:box\s*office|opening\s*weekend|domestic\s*gross|worldwide\s*gross|film|movie)\b", re.I), "movies"),
    (re.compile(r"\b(?:rotten\s*tomatoes|RT\s*score|critic\s*score|tomatometer)\b", re.I), "movies"),
    (re.compile(r"\b(?:netflix|hulu|disney\+|hbo|max|streaming|series|show|season\s*\d|episode|sitcom|reality\s*tv|survivor|bachelor|big\s*brother|beast\s*games|love\s*island)\b", re.I), "tv_streaming"),
    (re.compile(r"\b(?:spotify|billboard|hot\s*100|album|song|artist|concert|tour|grammy|music|rapper|singer|band)\b", re.I), "music"),
    (re.compile(r"\b(?:oscar|emmy|golden\s*globe|sag\s*award|tony|bafta|cannes|sundance|venice\s*film)\b", re.I), "awards"),
    (re.compile(r"\b(?:youtube|tiktok|instagram|twitter|x\.com|subscriber|follower|views|viral|mrbeast|influencer|streamer|twitch|podcast|elon|musk|tweet)\b", re.I), "social_media"),
    (re.compile(r"\b(?:celebrity|kardashian|swift|beyonc|drake|kanye|bieber|selena|rihanna|dua\s*lipa|ariana|kendrick|post\s*malone)\b", re.I), "celebrity"),
    (re.compile(r"\b(?:eurovision|super\s*bowl\s*halftime|world\s*cup\s*ceremony|royal|pope|wedding|baby|engagement|divorce)\b", re.I), "viral"),
]


_ENTERTAINMENT_EXCLUDE_RE = re.compile(
    r"\b(?:net\s*worth|stock|share\s*price|market\s*cap|IPO|revenue|"
    r"earnings|quarterly|valuation|GDP|CPI|inflation|interest\s*rate|"
    r"SpaceX|starlink|tesla\s+(?:stock|delivery|production)|"
    r"launch\s+count|rocket|satellite|orbit|"
    r"richest|billionaire|fortune|wealth|"
    r"SEC\s+investigation|antitrust|lawsuit|"
    r"company\s+stake|acquisition|acquire)\b",
    re.IGNORECASE,
)


def _classify_theme(market: FuturesMarket) -> str:
    ext = (market.external_id or "").lower()
    for prefix, theme in _THEME_BY_TICKER:
        if ext.startswith(prefix):
            return theme
    name = market.name or ""
    if _ENTERTAINMENT_EXCLUDE_RE.search(name):
        return "excluded"
    for pat, theme in _THEME_BY_NAME:
        if pat.search(name):
            return theme
    return "other"


# ---------------------------------------------------------------------------
# Kind classification — rendering hint for frontend card bodies
# ---------------------------------------------------------------------------

_KIND_BY_TICKER: list[tuple[str, str]] = [
    ("kxspotify", "spotify"),
    ("kxbillboard", "billboard"),
    ("kxboxoffice", "boxoffice"),
    ("kxrottentomatoes", "rt"),
    ("kxsurvivor", "reality"),
    ("kxbachelor", "reality"),
    ("kxbeastgames", "reality"),
    ("kxeurovision", "eurovision"),
]

_KIND_BY_NAME: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\b(?:#1\s*song|chart\s*race|spotify\s*#1|#1\s*on\s*(?:us\s*)?spotify)\b", re.I), "spotify"),
    (re.compile(r"\b(?:billboard|hot\s*100)\b", re.I), "billboard"),
    (re.compile(r"\b(?:box\s*office|opening\s*weekend|domestic\s*gross)\b", re.I), "boxoffice"),
    (re.compile(r"\b(?:rotten\s*tomatoes|tomatometer)\b", re.I), "rt"),
    (re.compile(r"\b(?:survivor|bachelor|bachelorette|beast\s*games|big\s*brother|reality)\b", re.I), "reality"),
    (re.compile(r"\b(?:eurovision)\b", re.I), "eurovision"),
]


def _classify_kind(market: FuturesMarket, outcome_count: int) -> str:
    ext = (market.external_id or "").lower()
    for prefix, kind in _KIND_BY_TICKER:
        if ext.startswith(prefix):
            return kind
    name = market.name or ""
    for pat, kind in _KIND_BY_NAME:
        if pat.search(name):
            return kind
    if outcome_count > 2:
        return "multi"
    return "binary"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _market_row(
    market: FuturesMarket,
    max_outcomes: int = 3,
    withheld_ids: frozenset[int] | set[int] = frozenset(),
) -> dict | None:
    """Enriched market row with all available fields.

    Returns None for a market this page holds no SERVABLE probability for at
    all — see the refusal below.

    ``withheld_ids`` is the caller's ``_withheld_price_outcome_ids`` union for
    this page's markets (#8083). It is a defaulted frozenset rather than a
    required argument on purpose: every one of this module's eleven call sites
    is inside a SYNC builder, and the helper is async, so the ids are computed
    once in :func:`get_entertainment` and threaded down. An omitted argument
    therefore degrades to the pre-#8083 behaviour — which is why the guard test
    asserts the wiring at the ROUTE, not just this function.
    """
    outcomes = _clean_outcomes(market.outcomes)
    outcomes = sorted(
        outcomes, key=lambda o: float(o.current_probability or 0), reverse=True
    )
    if not outcomes:
        return None
    # #6235 — A MARKET NOBODY HAS PRICED IS NOT A MARKET AT 0%.
    #
    # This is #2950's refusal, ported from `economics._market_row`, whose
    # docstring states the rule it turns on: a priced zero is DATA (the market
    # says no); a NULL is the ABSENCE of data, and only the second is grounds
    # for refusing the row. That fix landed in the sibling route alone — its
    # note records that `politics.py` and `entertainment.py` "already refuse on
    # their third line", which is the check above: it refuses a market with NO
    # OUTCOMES, never one whose outcomes carry no price. The `float(... or 0)`
    # reads below were what rendered the difference: every rung folded to 0.0
    # and the row headlined a confident `0%`.
    #
    # Those reads are GONE as of #6255 (below), which carries the same rule into
    # the ladder itself. This refusal is still load-bearing and is not subsumed
    # by it — it is what makes `priced` provably non-empty.
    #
    # Measured on production 2026-09-14, the same minute, across the three
    # dashboards that share this row shape — the already-fixed sibling is the
    # control: `/api/economics` **0 of 55** zero-probability rows,
    # `/api/entertainment` **20 of 112**, `/api/politics` **32 of 68**. The 20
    # here are the never-traded daily-chart racks: `YouTube Charts: Weekly Top
    # Song USA`, `Taylor Swift · Views on Sep 13, 2026`, `Ligue 1 Golden Boot`.
    #
    # ⚠️ THE ZEROS ARE NOT A BACKFILL HOLE, so withdrawing the card deletes no
    # alarm: of the 424 open markets in these categories with no priced outcome,
    # **420 have never held a single `futures_odds_snapshots` row**. There is no
    # price to recover and none is being hidden. `outcome_count` is unaffected;
    # a market that gets its first price returns on the next build.
    #
    # #8083 — AND A RUNG WE REFUSE TO SERVE ON ITS OWN PAGE IS NOT A RUNG HERE.
    #
    # The two refusals above turn on `current_probability IS NULL`. Withholding
    # is a SERVE-TIME decision layered on a column that stays non-null, so
    # reading the column directly bypassed it entirely and this page published
    # prices `/api/futures/{id}` withholds in the same minute: *Who will win The
    # Bachelorette Season 22* printed `Doug 93%` off a ladder whose 22 legs the
    # detail route serves as 22 nulls (`prices_withheld: 22`), and tapping the
    # card landed on "No prices in the last 30 days" with no outcomes at all.
    #
    # A withheld leg is treated as an ABSENT price, not a zero — the same
    # reading #6255 gave a NULL rung, for the same reason: we are not saying the
    # market priced it at nothing, we are saying we will not stand behind the
    # number. That makes the composition with both rails above exact rather than
    # additive, and it is why the market-level refusal now reads `priced`: a
    # market whose every priced leg is withheld holds nothing servable, so the
    # card is withdrawn rather than published with a fabricated headline.
    priced = [
        o
        for o in outcomes
        if o.current_probability is not None and o.id not in withheld_ids
    ]
    if not priced:
        return None
    # #6255 — A RUNG WE HOLD NO PRICE FOR IS NOT A RUNG AT 0%.
    #
    # The refusal above is the same rule ONE LEVEL UP. It never reached inside
    # a ladder that IS traded, so `float(... or 0)` printed a NULL rung as a
    # confident `0%` under a real leader, indistinguishable from a rung the
    # market has priced at zero — which is DATA and stays (#2950).
    #
    # ⚠️ "FEWER THAN THREE PRICED OUTCOMES" UNDERSTATES THE REACH HERE, because
    # this builder is called with `max_outcomes=8` on several sections (unlike
    # the politics twin's fixed 3). Measured on the served payload 2026-09-17
    # 14:40Z: `Harry Potter … Rotten Tomatoes` has SIX priced rungs and still
    # showed two unpriced ones in an eight-slot rack, and `Ligue 1: Team
    # Points` showed seven, of a ladder whose 71 of 72 rungs are unpriced.
    #
    # `Which movie has 2nd/3rd biggest opening weekend` is the control on the
    # other side: its `0.0` rung is genuinely priced and is untouched.
    #
    # `outcome_count` keeps reading the full list — the filter drops rungs from
    # the SLICE, never from the ladder's arity.
    top = priced[:max_outcomes]
    outcome_count = len(outcomes)
    return {
        "q": market.name,
        # #6255 — `priced[0]`, not `outcomes[0]`. Both name the leader on every
        # ladder that has one priced rung above zero, but they part when every
        # priced rung is a zero: the `or 0` made a NULL tie with a real zero and
        # the stable sort then handed the headline to whichever came first in
        # the ladder. Reading the filtered list means the number, the rungs and
        # the hook's leader are all the same object.
        "prob": round(float(priced[0].current_probability) * 100, 1),
        "src": _source(market),
        "market_id": market.id,
        "external_id": market.external_id,
        "kind": _classify_kind(market, outcome_count),
        "top_outcomes": [
            {
                "name": o.name,
                "prob": round(float(o.current_probability or 0) * 100, 1),
                "delta_24h": round(
                    float(o.probability_change_24h or 0) * 100, 1
                ),
            }
            for o in top
        ],
        "outcome_count": outcome_count,
        "volume_24h": market.volume_24h,
        "resolution_date": (
            market.resolution_date.isoformat()
            if market.resolution_date
            else None
        ),
        # Honest data-freshness signal: when these probabilities were last
        # refreshed. Daily-chart markets ("Top artist today") must not imply
        # more freshness than the data has — the frontend renders an
        # "as of <time>" label from this rather than implying live updates.
        "as_of": (
            _updated_at.isoformat()
            if (_updated_at := getattr(market, "updated_at", None))
            else None
        ),
        "image_url": market.image_url,
        # #5926: the same gate the Discover card and (since #5906) the futures
        # detail page run. This route served `market.hook_description` raw, so
        # /entertainment was the third and last unconverted call site of a rule
        # `app/utils/hook_staleness.py` has enforced since it shipped.
        #
        # WHAT A READER SAW. Every card carried five to seven lines of narrative
        # ABOVE its probabilities, and the prose was the dominant element:
        # *"As tensions rise in the Big Brother house, the impending Week 10
        # elimination has fans on edge, with alliances shifting and strategies
        # evolving."* Nothing in our data supports any of that. Another named
        # people — *"emerging favorites like Callum Turner and Edward B…"* —
        # which is verbatim the shape #5461 retired the prompt for.
        #
        # MEASURED, NOT SAMPLED (production 2026-09-13): this endpoint served a
        # hook on 69 of its 112 cards, and of the 11,444 open markets carrying a
        # hook, 0 are policy 2 and 10,629 are also past the 7-day age gate — so
        # all 69 were prose the Discover card already refused.
        #
        # NO EMPTY-SPACE QUESTION, AND THAT WAS CHECKED RATHER THAN ASSUMED: 43
        # of those 112 cards already render with no hook today, so the hookless
        # card is not a new layout, it is the majority-adjacent one the page
        # already ships. The frontend gates all six render sites on `m.hook &&`.
        #
        # `priced[0]` IS the leader here, unlike on the futures detail page.
        #
        # #6255 CORRECTED THE OBJECT THIS READS. The line above used to say
        # "this route withholds no prices, so there is no null to sink" — and
        # that premise is exactly what changed: the route now withholds unpriced
        # rungs from the slice. `priced` is the same list the rungs and the
        # headline are built from, sorted by `current_probability` above, so the
        # staleness gate cannot come to disagree with the leader the card shows.
        "hook": (
            None
            if is_hook_stale(
                hook_description=market.hook_description,
                hook_generated_at=getattr(market, "hook_generated_at", None),
                hook_leader_at_generation=getattr(
                    market, "hook_leader_at_generation", None
                ),
                current_leader_name=priced[0].name,
                current_leader_probability=float(
                    priced[0].current_probability
                ),
                market_metadata=getattr(market, "market_metadata", None),
            )
            else market.hook_description
        ),
    }


def _is_interesting(row: dict) -> bool:
    """Filter out boring markets (binary near 100%)."""
    if row["outcome_count"] <= 2 and row["prob"] > 95:
        return False
    return True


# ---------------------------------------------------------------------------
# Threshold grouping — RT scores, box office brackets
# ---------------------------------------------------------------------------

# Match: Will "Movie Title" score at least 75 on the Rotten Tomatoes Tomatometer?
# Match: "Movie Title" Rotten Tomatoes score?
# Match: "Movie Title" Opening Weekend Box Office
# Match: Movie Title — above 75
_RT_TITLE_RE = re.compile(
    r'["“](.+?)["”]\s*(?:score\s+at\s+least\s+\d+|rotten\s*tomatoes|opening\s*weekend|box\s*office)',
    re.I,
)

_GENERIC_TITLE_RE = re.compile(
    r'^(?:will\s+)?["“](.+?)["”]',
    re.I,
)

_THRESHOLD_NUM_RE = re.compile(
    r'(?:at\s+least|above|over|≥|>=)\s*(\d+)',
    re.I,
)


def _normalize_group_key(name: str) -> str | None:
    """Extract the entity name from a threshold market question."""
    m = _RT_TITLE_RE.search(name or "")
    if m:
        return m.group(1).strip().lower()
    m = _GENERIC_TITLE_RE.search(name or "")
    if m:
        return m.group(1).strip().lower()
    return None


def _extract_threshold_label(q: str) -> str:
    """Extract a short threshold label like '≥75' from a market question."""
    m = _THRESHOLD_NUM_RE.search(q)
    if m:
        return f"≥{m.group(1)}"
    return q[:30]


def _group_threshold_markets(markets: list[dict]) -> tuple[list[dict], list[dict]]:
    """Group markets that share an entity but differ by threshold."""
    by_entity: dict[str, list[dict]] = defaultdict(list)
    ungrouped = []

    for row in markets:
        key = _normalize_group_key(row["q"])
        if key:
            by_entity[key].append(row)
        else:
            ungrouped.append(row)

    groups = []
    for entity_key, rows in by_entity.items():
        if len(rows) >= 2:
            title_match = _RT_TITLE_RE.search(rows[0]["q"]) or _GENERIC_TITLE_RE.search(rows[0]["q"])
            title = title_match.group(1) if title_match else entity_key.title()
            groups.append({
                "title": title,
                "image_url": next(
                    (r["image_url"] for r in rows if r.get("image_url")), None
                ),
                "thresholds": [
                    {
                        "label": _extract_threshold_label(r["q"]),
                        "prob": r["prob"],
                        "market_id": r["market_id"],
                    }
                    for r in sorted(rows, key=lambda r: -r["prob"])
                ],
            })
        else:
            ungrouped.extend(rows)

    return groups, ungrouped


# ---------------------------------------------------------------------------
# Cross-source matching — find markets on both Kalshi & Polymarket
# ---------------------------------------------------------------------------

def _cross_source_row_fn(
    market: FuturesMarket,
    withheld_ids: frozenset[int] | set[int] = frozenset(),
) -> dict | None:
    """Build a row for cross-source matching (entertainment-specific)."""
    row = _market_row(market, withheld_ids=withheld_ids)
    if not row or not _is_interesting(row):
        return None
    row["theme"] = _classify_theme(market)
    return row


# ---------------------------------------------------------------------------
# Trending hero — pick the 5 most interesting markets
# ---------------------------------------------------------------------------

def _score_for_trending(row: dict) -> float:
    score = 0.0
    score += (50 - abs(row["prob"] - 50)) * 2
    if row.get("volume_24h"):
        score += min(row["volume_24h"] / 1000, 50)
    if row["outcome_count"] > 2:
        score += 15
    if row["kind"] not in ("binary", "multi"):
        score += 10
    if row.get("hook"):
        score += 5
    if row.get("image_url"):
        score += 3
    return score


def _decidedness(row: dict) -> float:
    """How settled this question is, 0.0 (wide open) to 1.0 (a foregone conclusion).

    DISTANCE FROM 50 IS ONLY THE BINARY ANSWER, and this page is not mostly
    binary: measured on the served payload of 2026-09-19 18:20Z, **89 of 115
    rows carry `outcome_count > 2`**. On a field of seventeen, a leader at 34.5%
    ("Big Brother Season 28 · Winner") is the most open question on the page,
    and a leader at 2.1% among five ("Who will Elon Musk back a primary against
    in 2026?") is a perfectly flat field — neither is remotely settled, yet both
    sit ~16 and ~48 points from 50. Ranking them by `abs(prob - 50)` buries the
    best questions we have, which is the same defect in the other direction.

    So the two shapes are scored separately and normalised onto one 0..1 scale
    so a single `sort` can compare them:

    * `outcome_count <= 2` — a one-sided Kalshi "Yes" contract (25 of the 115)
      or a true binary. BOTH tails are settled: 2% means "almost certainly no"
      just as 98% means "almost certainly yes". Decidedness is distance from 50.
    * `outcome_count > 2` — only the HIGH end is settled. The floor is a flat
      field (`100/n`), not zero, so the leader's lead is measured from there:
      a flat 15-way and a flat 3-way both score 0.0, and a 3-way at 97.9%
      scores 0.97 exactly like a binary at 97.9%.

    Replaces `-abs(prob - 50)` (#7278), which ranked every section
    most-DECIDED-first. Because each of the three call sites slices after
    sorting, that key did not merely order the wall — it SELECTED it out of
    pools far larger than the cap (505 movies/TV candidates for 10 side-market
    slots), dropping the open questions from the payload entirely.
    """
    prob = row["prob"]
    if row.get("outcome_count", 2) <= 2:
        return abs(prob - 50) / 50.0
    flat = 100.0 / row["outcome_count"]
    # Clamped because a leader BELOW the flat baseline (a field even wider than
    # its arity suggests, or a stale rung) is not "negatively decided" — it is
    # simply as open as a question gets.
    return max(0.0, min(1.0, (prob - flat) / (100.0 - flat)))


def _by_uncertainty(row: dict) -> tuple[float, float]:
    """Sort key for the section builders: most-open question first.

    `_score_for_trending` above already scores `(50 - abs(prob - 50))` — the
    same direction, and the within-page control for it: that section served 0 of
    5 settled rows on the payload where its siblings served 20 of 20.

    `volume_24h` breaks ties only. It is null on 49 of those 115 rows, so
    gating or weighting on it would rank most of the page on missing data; it
    orders two questions that are equally open and never lifts a settled market
    over an open one. Nulls sort last within a tie and no further.
    """
    return (_decidedness(row), -(row.get("volume_24h") or 0))


def _build_trending(all_rows: list[dict], limit: int = 5) -> list[dict]:
    """Pick top N trending markets with kind diversity."""
    scored = sorted(all_rows, key=_score_for_trending, reverse=True)
    result = []
    kind_counts: dict[str, int] = defaultdict(int)

    for row in scored:
        if len(result) >= limit:
            break
        if kind_counts[row["kind"]] >= 2:
            continue
        result.append(row)
        kind_counts[row["kind"]] += 1

    return result


# ---------------------------------------------------------------------------
# Section builders
# ---------------------------------------------------------------------------

def _build_list(
    markets: list,
    limit: int = 12,
    withheld_ids: frozenset[int] | set[int] = frozenset(),
) -> list[dict]:
    rows = []
    for m in markets:
        row = _market_row(m, withheld_ids=withheld_ids)
        if row and _is_interesting(row):
            rows.append(row)
    rows.sort(key=_by_uncertainty)
    return rows[:limit]


def _distinct_served_market_ids(*sections) -> set:
    """Every market id this payload puts on the page, counted once (#7392).

    The hero and the footer both print this count, so it has to mean what a
    reader would take it to mean: how many markets are on the page. Walking the
    served structures is what makes that true by construction rather than by a
    formula somebody has to keep in sync.

    ⚠️ IT WALKS, IT DOES NOT SUM SECTION SIZES. A `market_id` can sit at three
    depths here: a plain row (`_market_row`), a threshold group's rung
    (`_group_threshold_markets` nests them under `thresholds[]`), and a theme
    dict's inner list (`themes["music"]["album_drops"]`). A count that adds up
    `len()`s misses the grouped rungs entirely and double-counts the rows that
    two sections share. `top_outcomes` carries no `market_id`, so a ladder is
    one market however many rungs it draws.

    ⚠️ IT IS NOT A CORPUS COUNT. `themed` holds every market `_classify_theme`
    accepted — 925 of them on the 2026-09-20 07:25Z bank — and the payload
    serves 112. Only the arguments are walked, so a bucket the page stopped
    serving stops being counted the moment it stops being served.
    """
    found: set = set()

    def walk(node) -> None:
        if isinstance(node, dict):
            mid = node.get("market_id")
            if mid is not None:
                found.add(mid)
            for value in node.values():
                if isinstance(value, (dict, list)):
                    walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    for section in sections:
        walk(section)
    return found


def _build_music(
    themed: dict, withheld_ids: frozenset[int] | set[int] = frozenset()
) -> dict:
    music_markets = themed.get("music", [])
    all_rows = []
    spotify_race = []
    billboard_watch = []
    album_drops = []
    artist_streaming = []
    side_markets = []

    for m in music_markets:
        kind = _classify_kind(m, len(_clean_outcomes(m.outcomes)))
        if kind == "spotify":
            row = _market_row(m, max_outcomes=8, withheld_ids=withheld_ids)
        elif kind == "billboard":
            row = _market_row(m, max_outcomes=8, withheld_ids=withheld_ids)
        elif kind in ("multi",):
            row = _market_row(m, max_outcomes=6, withheld_ids=withheld_ids)
        else:
            row = _market_row(m, withheld_ids=withheld_ids)
        if not row or not _is_interesting(row):
            continue
        all_rows.append(row)
        if kind == "spotify":
            spotify_race.append(row)
        elif kind == "billboard":
            billboard_watch.append(row)
        else:
            name_lower = (row["q"] or "").lower()
            if any(
                w in name_lower
                for w in ["album", "first-week", "first week", "sales"]
            ):
                album_drops.append(row)
            elif any(
                w in name_lower
                for w in ["stream", "weekly", "monthly"]
            ):
                artist_streaming.append(row)
            else:
                side_markets.append(row)

    spotify_race.sort(key=lambda r: -r["prob"])
    # NO CROSS-MARKET NORMALIZATION HERE — each row keeps its own leading outcome.
    #
    # This used to divide every row by the sum of the others, in the feed's 0-1 form
    # (`> 1.05`, no `* 100`), so a market reading 86.0 was published as 0.8.  Correcting
    # the arithmetic to the 0-100 form is NOT the fix: it publishes 80.0 for that same
    # market while the market's own leading outcome still reads 86.0, and the card labels
    # the altered share with the original outcome's name.
    #
    # Normalizing across MARKETS is only meaningful when the markets partition one
    # question — which is what politics `_normalize_outcome_probs` does over the
    # candidates of a single race.  `spotify_race` is not that: membership comes from the
    # `kxspotify` ticker prefix, so it collects unrelated questions.  Today it holds a
    # cumulative-threshold release-date market ("When will Wrapped drop?", outcomes
    # 86.0/83.5/77.0, not mutually exclusive) alongside "Will Playboi Carti release BABY
    # BOI this year?" — two different questions with no shared 100% to divide.
    #
    # No surface sums these headlines either: `SpotifyRace` renders the top_outcomes of
    # ONE market, and its `< 2 outcomes` fallback renders independent cards.  So the
    # normalization had no consumer and one victim, the number itself.
    billboard_watch.sort(key=lambda r: -r["prob"])

    billboard_groups, billboard_ungrouped = _group_threshold_markets(billboard_watch)
    side_markets.extend(billboard_ungrouped)

    return {
        "count": len(music_markets),
        "spotify_race": spotify_race[:8],
        "billboard_watch": billboard_watch[:12],
        "billboard_groups": billboard_groups,
        "album_drops": album_drops[:6],
        "artist_streaming": artist_streaming[:8],
        "side_markets": side_markets[:10],
    }


def _build_movies_tv(
    themed: dict, withheld_ids: frozenset[int] | set[int] = frozenset()
) -> dict:
    movies = themed.get("movies", [])
    tv = themed.get("tv_streaming", [])
    combined = movies + tv

    rt_markets = []
    box_office = []
    reality_tv = []
    side_markets = []

    for m in combined:
        kind = _classify_kind(m, len(_clean_outcomes(m.outcomes)))
        if kind in ("rt", "boxoffice"):
            row = _market_row(m, max_outcomes=8, withheld_ids=withheld_ids)
        elif kind == "reality":
            row = _market_row(m, max_outcomes=6, withheld_ids=withheld_ids)
        else:
            row = _market_row(m, withheld_ids=withheld_ids)
        if not row or not _is_interesting(row):
            continue
        if kind == "rt":
            rt_markets.append(row)
        elif kind == "boxoffice":
            box_office.append(row)
        elif kind == "reality":
            reality_tv.append(row)
        else:
            side_markets.append(row)

    rt_groups, rt_ungrouped = _group_threshold_markets(rt_markets)
    box_groups, box_ungrouped = _group_threshold_markets(box_office)

    side_markets.extend(rt_ungrouped)
    side_markets.extend(box_ungrouped)
    side_markets.sort(key=_by_uncertainty)

    return {
        "count": len(combined),
        "rt_groups": rt_groups,
        "rt_markets": rt_markets[:12],
        # ANNOTATED — queue 333, C272/B4 zero-read census (#1620).
        # An asymmetry worth keeping, not weight worth cutting: `rt_groups` above is
        # consumed and this — its box-office counterpart, built by the same
        # `_group_threshold_markets` grouping — is not. That is the signature of a
        # heatmap that shipped for one metric and not the other, so the honest
        # disposition is "unfinished surface"; finishing it or dropping it is a product
        # call, not a plumbing cleanup.
        "box_office_groups": box_groups,
        "box_office": box_office[:12],
        "reality_tv": reality_tv[:9],
        "side_markets": side_markets[:10],
    }


def _build_cultural(
    themed: dict, withheld_ids: frozenset[int] | set[int] = frozenset()
) -> list[dict]:
    """Awards + celebrity + viral + other → cultural moments feed."""
    cultural_markets = (
        themed.get("awards", [])
        + themed.get("celebrity", [])
        + themed.get("viral", [])
        + themed.get("other", [])
    )
    rows = []
    for m in cultural_markets:
        row = _market_row(m, withheld_ids=withheld_ids)
        if row and _is_interesting(row):
            rows.append(row)
    rows.sort(key=_by_uncertainty)
    return rows[:20]


# ---------------------------------------------------------------------------
# Main endpoint
# ---------------------------------------------------------------------------

@router.get("")
async def get_entertainment_cached(db: AsyncSession = Depends(get_db)):
    """Return all entertainment market data (Redis-cached, precomputed hourly).

    Falls back to a stale cache (24h TTL) when the primary cache is cold,
    and wraps the live DB query with a 25s timeout so Heroku never kills
    the connection.
    """
    import asyncio
    from app.tasks.redis_state import get_async_redis_client

    try:
        rc = get_async_redis_client()
        cached = await rc.get("bainluck:category:entertainment")
        if cached:
            await rc.aclose()
            return json.loads(cached)
        # Primary cache miss — try stale fallback
        stale = await rc.get("bainluck:category:entertainment:stale")
        await rc.aclose()
        if stale:
            logger.info("Entertainment: serving stale cache (primary miss)")
            return json.loads(stale)
    except Exception:
        pass  # Fall through to live query

    # Live DB fallback with timeout guard
    try:
        response = await asyncio.wait_for(get_entertainment(db), timeout=25)
    except asyncio.TimeoutError:
        logger.warning("Entertainment live query timed out after 25s")
        return {"error": "timeout", "themes": {}}

    # Populate stale cache for future cold-cache resilience
    try:
        rc = get_async_redis_client()
        await rc.set(
            "bainluck:category:entertainment:stale",
            json.dumps(response, default=str),
            ex=86400,
        )
        await rc.aclose()
    except Exception:
        logger.warning("Entertainment: failed to write stale cache", exc_info=True)

    return response


async def get_entertainment(db: AsyncSession):
    """Build entertainment response from database (called by precompute task + fallback)."""
    now = datetime.now(timezone.utc)

    result = await db.execute(
        select(FuturesMarket)
        .options(selectinload(FuturesMarket.outcomes))
        .where(
            or_(
                FuturesMarket.llm_sport_category.in_(
                    ["entertainment", "culture", "social_media"]
                ),
                *[
                    FuturesMarket.external_id.ilike(f"{prefix}%")
                    for prefix, _ in _THEME_BY_TICKER
                ],
            ),
            FuturesMarket.status == "open",
        )
    )
    all_markets = list(result.scalars().unique().all())

    # Collapse Polymarket sub-markets sharing a group_id into a single
    # representative market with merged outcomes (BR62 / #487).
    all_markets = group_markets_by_group_id(all_markets)

    def _leader_prob(m):
        outcomes = sorted(
            (m.outcomes or []),
            key=lambda o: float(o.current_probability or 0),
            reverse=True,
        )
        return float(outcomes[0].current_probability) if outcomes and outcomes[0].current_probability else None

    # TWO lists, and the difference between them is the point (CERT-540).
    #
    # `featured_eligible` — survivors of `should_exclude_from_featured`. This is
    # what TRENDING reads. The predicate used to be computed twice in this
    # function, once here and once in the trending loop below; UX-P194-1 made
    # them share one list, and this is that list, with its membership unchanged.
    #
    # `spotlight_eligible` — the same survivors that also earned a theme, i.e.
    # everything this page is actually willing to RENDER in a section. This is
    # what the CROSS-SOURCE SPOTLIGHT reads. CERT-540 blocked feeding it
    # `featured_eligible`: `_classify_theme` returning `"excluded"` is this
    # page's topical rejection, and a market rejected by it was still able to
    # headline the page above the sections that had dropped it.
    #
    # ⚠️ They are deliberately NOT collapsed into one list. Narrowing trending
    # to the themed set would be a silent ranking change nobody asked for —
    # exactly the hazard UX-P214 paid for when it merged two computations and
    # gave a consumer it was not thinking about an untested dependency.
    #
    # ⚠️ A NEW GATE GOES ABOVE THE APPEND IT BELONGS TO. The coupling is
    # positional; `TestTheSpotlightIsASubsetOfWhatThePageRenders` notices.
    themed: dict[str, list] = defaultdict(list)
    featured_eligible: list = []
    spotlight_eligible: list = []
    for m in all_markets:
        exclude = should_exclude_from_featured(
            m.name, m.llm_sport_category, m.status, _leader_prob(m), now,
        )
        if exclude:
            continue
        featured_eligible.append(m)
        theme = _classify_theme(m)
        if theme == "excluded":
            continue
        spotlight_eligible.append(m)
        themed[theme].append(m)

    # #8083 — THE REFUSAL RAIL, ASKED ONCE FOR THE WHOLE PAGE.
    #
    # `_withheld_price_outcome_ids` is async and per-market; all eleven
    # `_market_row` call sites below are inside SYNC builders. So the union is
    # taken here and threaded down as a flat set — outcome ids are globally
    # unique, so one set answers for every market without a per-market mapping.
    #
    # PLACED BELOW THE SKIP, which is #7016's rule and the reason this is
    # affordable: the loop above has already dropped everything
    # `should_exclude_from_featured` rejects, and `featured_eligible` is the
    # exact superset of what reaches a builder (`spotlight_eligible` and every
    # `themed` bucket are subsets of it). A market this page never renders
    # never pays a query.
    #
    # COST. This endpoint is Redis-cached and precomputed hourly, so the bill
    # lands on the precompute task rather than on a reader — a strictly better
    # budget than the hub route that already runs this per market. Two of the
    # five arms are pure in-memory passes over `market.outcomes`, already loaded
    # by the `selectinload` above; the others screen on those same in-memory
    # columns before reaching the snapshot table. If this page ever does feel
    # it, the answer is #7016's — batch the queries across the page, never drop
    # an arm and re-open the split.
    #
    # #8102 — AND THE HELPER IS FIVE ARMS WHILE THE PAGE A READER LANDS ON IS SIX.
    #
    # `_withheld_price_outcome_ids` composes five arms. The number the reader
    # actually meets on `/futures/{id}` is that union PLUS #8011's
    # unobserved-board arm, which `get_futures_market` adds outside the helper
    # because `_format_market_detail` is sync and holds no session to read the
    # fleet stamp with. So the helper is a strict SUBSET of the detail page's
    # refusal, and #8083 — trusting it as "the" refusal — inherited the gap:
    # measured on production at 22:26Z, five of 109 served markets still
    # published a price their own detail page withheld, *Who will win The
    # Bachelorette Season 22* among them, heroing `Doug 92.5` over a ladder
    # served as 22 nulls.
    #
    # BOTH HELPERS ARE CALLED, NOT RE-SPELLED. The gate that makes the sixth arm
    # affordable lives inside `_fleet_newest_observation` itself — it returns
    # None without touching the database for any board that cannot qualify
    # (~92% of them), and the read it does make is an Index Only Scan Backward
    # measured at 0.042 ms. Re-implementing that gate here to "save" a call is
    # exactly the second spelling #6993 exists to prevent, and it would be the
    # same mistake #8083 made one level up.
    withheld_ids: set[int] = set()
    for m in featured_eligible:
        withheld_ids |= await _withheld_price_outcome_ids(db, m)
        market_outcomes = getattr(m, "outcomes", None) or []
        withheld_ids |= unobserved_board_keys(
            ((o.id, o.last_updated) for o in market_outcomes),
            board_touched_at=getattr(m, "updated_at", None),
            fleet_newest_observation=await _fleet_newest_observation(db, m),
            board_has_a_verdict=_board_has_a_verdict(market_outcomes),
        )

    # Build all enriched rows for trending scoring
    all_rows = []
    for m in featured_eligible:
        row = _market_row(m, withheld_ids=withheld_ids)
        if row and _is_interesting(row):
            all_rows.append(row)

    trending = _build_trending(all_rows)
    music = _build_music(themed, withheld_ids)
    movies_tv = _build_movies_tv(themed, withheld_ids)
    cultural_moments = _build_cultural(themed, withheld_ids)
    tech_culture_markets = _build_list(
        themed.get("social_media", []), 15, withheld_ids
    )

    # Cross-source spotlight — fed the set this page ACCEPTED, not `all_markets`
    # and not the wider trending pool. A market this page already refused to put
    # in a theme section must not reappear as its headline source disagreement.
    # UX-P194-1 / CERT-540.
    cross_source = find_cross_source_markets(
        list(spotlight_eligible),
        # #8083: `find_cross_source_markets` calls this with the market alone,
        # so the page's withheld union is bound here rather than passed.
        market_row_fn=lambda m: _cross_source_row_fn(m, withheld_ids),
    )

    themes = {
        "music": music,
        "movies_tv": movies_tv,
        # #7432: THE ONE SECTION COUNT A READER SEES NAMES THE ROWS IT SITS OVER.
        #
        # It was `len(themed["social_media"])` — the raw `_classify_theme`
        # bucket, filled above by the loop that only applies
        # `should_exclude_from_featured`. `_market_row` and `_is_interesting`
        # run inside `_build_list`, AFTER that append and BEFORE the `[:15]`,
        # so the bucket length is a PRE-GATE pool: it counts rows this route
        # itself then refuses for reading settled, stale or uninteresting.
        # That is #6978's defect exactly ("those heroes were `len(all_markets)`,
        # the PRE-GATE pool, so they called rows active that the route had
        # already dropped"), not #7423's invented literal. Measured on the
        # served bank 2026-09-20 13:47Z: **49** printed over **15** rendered.
        #
        # ⚠️ TWO SURFACES, NOT ONE. #7392's note above says this is rendered in
        # a single place; that is true of the web page and not of the field.
        # `frontend/app/entertainment/page.tsx:1301` draws it over 15 rows and
        # `ios/.../Views/EntertainmentView.swift:630` draws it over
        # `markets.prefix(10)`, so the app read 49 over 10. Deriving the number
        # here is what repairs both; a `data.markets.length` on the web would
        # have left the app over-claiming.
        #
        # ⚠️ `len(tech_culture_markets)`, NOT the `15` limit beside it. The list
        # is short whenever the gate leaves fewer than 15 survivors, and a label
        # that reads the cap would then over-claim again on exactly the thin
        # days it matters. `TestTheCountIsTheServedListNotTheCapAndNotTheBucket`
        # is the arm that holds both halves of that.
        "tech_culture": {
            "count": len(tech_culture_markets),
            "markets": tech_culture_markets,
        },
    }

    # #7392: THE HERO COUNTS THE MARKETS THIS PAYLOAD PUTS ON THE PAGE.
    #
    # It used to be `sum(len(v) for v in themed.values())` — every bucket
    # `_classify_theme` accepted, whether or not the payload serves it. Measured
    # on the served bank 2026-09-20 07:25Z that printed **925** over a page that
    # renders **112** distinct markets, and it printed it twice (the hero and the
    # footer read this one key).
    #
    # The rule is #6978's, which repaired `/politics` and `/economics`: the hero
    # names what a reader can reach. That issue recorded this route as unaffected
    # by its own defect and was right to — those heroes were `len(all_markets)`,
    # the PRE-GATE pool, so they called rows "active" that the route had already
    # dropped for reading settled or stale. This total counted no dropped row.
    # The over-claim here is section EXPOSURE, which is a different gap, and the
    # sibling fix left it standing.
    #
    # ⚠️ NOT `sum(t["count"] for t in themes.values()) + len(cultural_moments)`,
    # which is where this fix first landed and is wrong by 4.3x. It reads a
    # section's `count` as the page's own published accounting — true of exactly
    # one section. `frontend/app/entertainment/page.tsx` renders `.count` in a
    # single place (line 1301, `TechCultureSidebar`); `music.count` (254) and
    # `movies_tv.count` (149) are published to NO reader, and those sections
    # render 34 and 41 rows. That formula printed 473 and 403 of them were
    # neither rendered nor named. `TestTheBucketCountFormulaIsRefused` is the arm
    # that keeps it from coming back.
    #
    # ⚠️ NOR a new `count` on `cultural_moments`: 472 printed beside 20 reachable
    # rows restates the same over-claim in a new field, which is what #6978
    # refused on `/economics`.
    #
    # DISTINCT, because the page is allowed to show one market twice and the
    # reader still reaches one market: `side_markets` appears under both music
    # and movies_tv, and `trending` and `cross_source` re-surface section rows
    # (measured: 89 across the theme sections, 109 with the cultural feed —
    # one overlap — and 112 with trending and cross-source).
    #
    # ⚠️ A NEW SERVED LIST MUST BE ADDED TO THIS CALL. The coupling is by
    # argument, not by reading the returned dict, and that is deliberate: this
    # runs before the `return` so it cannot count a key the payload drops.
    # `TestEveryServedListReachesTheCount` walks the response and fails on any
    # market-bearing list the count never saw.
    total = len(
        _distinct_served_market_ids(
            trending, cross_source, themes, cultural_moments
        )
    )

    return {
        "total_markets": total,
        "updated_at": now.isoformat(),
        "trending": trending,
        "cross_source": cross_source,
        "themes": themes,
        "cultural_moments": cultural_moments,
        "by_source": {
            "kalshi": sum(
                1
                for m in all_markets
                if _source(m) == "kalshi" and not _is_resolved(m)
            ),
            "polymarket": sum(
                1
                for m in all_markets
                if _source(m) == "polymarket" and not _is_resolved(m)
            ),
        },
    }
