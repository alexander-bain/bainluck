"""live/059 — the outright chart draws the venue's minutes, not our hourly glance.

THE SPECIMEN. `/event/tennis/us-open-men-s-singles-winner`, the "Race to the
title" chart, measured on production 2026-09-03/04 (UTC):

    evolution market   34277822  US Open Men's Singles Winner (kalshi)
    Carlos Alcaraz     129 points over 7 days — 15 distinct values, 20 changes
    Alexander Zverev   129 points over 7 days —  8 distinct values, 16 changes
    Daniil Medvedev    129 points over 7 days —  5 distinct values, 11 changes

Alex, looking at it: *"the granularity isn't very impressive"*. He is right, and
the number of POINTS is not why. 129 points is a fine number of points. The line
looks like a staircase with five treads because of two independent quantisations
that both land on the same chart:

  * **TIME.** `futures_odds_snapshots` is a sampler — the futures poll writes one
    reading roughly every 78 minutes. Nothing that happened between two readings
    is recoverable from our own tables, and a slam's biggest moves happen inside
    a two-hour match.
  * **PRICE.** Kalshi quotes in whole cents, so on a 33-way field renormalised to
    sum to 1 the smallest representable move is 0.0083. Alcaraz's whole week is
    fifteen of those.

Both venues publish the missing resolution and both were measured for this
queue, on the specimen's own tokens, 2026-09-04 UTC:

    Polymarket CLOB   GET /prices-history?market={clob_token_id}&interval=&fidelity=
      interval=1d   fidelity=1     1,441 pts   09-03 02:12 → 09-04 02:11    89 changes
      interval=1w   fidelity=60      167 pts   08-28 03:00 → 09-04 02:13    39 changes
      interval=1m   fidelity=60      742 pts   08-04 03:00 → 09-04 02:10   161 changes
      interval=max  fidelity=60      742 pts   08-04 03:00 → 09-04 02:14   161 changes
      interval=max  fidelity=720     419 pts   2026-01-03 → 09-04 02:10   255 changes
    Kalshi            GET /markets/candlesticks?market_tickers=&period_interval=
      period_interval=1      (24h)    816 pts   09-03 02:17 → 09-04 02:16   164 changes
      period_interval=60     (31d)    733 pts   08-04 03:00 → 09-04 02:00   282 changes
      period_interval=1440  (life)     87 pts   2026-06-09 → 09-03 04:00    66 changes

🔴 **A CORRECTION THIS MODULE DEPENDS ON.** `ARTIFACT-M-20260831-S` §1–2 concluded
that CLOB retention is "~31 days at any fidelity" and that `interval=max` is
retention-bounded. That generalisation is FALSE at coarse fidelity and the
measurement above is the counter-example: `interval=max&fidelity=720` returns
419 points reaching **2026-01-03**, the market's listing, eight months back —
while `fidelity=60` on the same token stops dead at 2026-08-04. The ~31-day bound
is real for fidelity ≤ 60 and is what the S artifact actually probed. Reaching
the draw is a coarse-fidelity call, and that is why the ALL tier below is 720.

THE SHAPE. Per outcome, per venue, TWO calls — the finest tier for the window a
person scrubs and the coarsest tier for the reach nobody scrubs but everybody
notices missing:

    fine    the last day at 1-minute        (what "1D" is for)
    coarse  the whole life at 12-hourly     (what "ALL" is for)

and the venue's own hourly tier in between when the market is young enough for it
to add anything. :func:`layer_tiers` stitches them; :func:`blend_venues` turns two
venues into the ONE number the doctrine requires ("the blend is the product" —
source divergence is a data bug to fix, not a second line to draw);
:func:`compact_series` puts the result inside a point budget without losing a
move or an endpoint.

EVERYTHING HERE IS PURE. No DB, no HTTP, no clock — the callers pass `now` in.
The I/O lives in `app/tasks/futures_chart_series_fill.py`, which is what makes
the layering testable at the seam, which is the only place it can go wrong.
"""

from __future__ import annotations

import math
import re
import unicodedata
from datetime import datetime, timedelta
from typing import Iterable, Optional, Sequence

# A point is (timestamp, probability-in-0..1). Deliberately a plain tuple: this
# module is the arithmetic, and every caller already has tuples.
Point = tuple[datetime, float]


# ---------------------------------------------------------------------------
# Tier plan — the decisions, not defaults
# ---------------------------------------------------------------------------

#: Polymarket CLOB `fidelity` is MINUTES PER BUCKET. 1 is the finest the venue
#: serves (there is no sub-minute endpoint) and 720 is the only one measured to
#: outrun the ~31-day retention wall — see the correction in the module
#: docstring. Never widen without re-probing BOTH the point count and the
#: earliest timestamp: a fidelity that answers with points but not with reach is
#: the failure mode that made "ALL" mean "one week".
CLOB_FINE_FIDELITY = 1
CLOB_HOURLY_FIDELITY = 60
CLOB_COARSE_FIDELITY = 720

#: Kalshi accepts ONLY these `period_interval` values. 5 and 15 are documented
#: nowhere and return junk — an answer shaped like data (see
#: `event_chart_backfill.KALSHI_PERIOD_INTERVALS`, same rule, same reason).
KALSHI_FINE_INTERVAL = 1
KALSHI_HOURLY_INTERVAL = 60
KALSHI_COARSE_INTERVAL = 1440

#: The fine tier covers exactly the window the "1D" switch shows. Asking for more
#: minute data than the switch can display is paying for pixels that do not exist.
FINE_TIER_HOURS = 24

#: The hourly tier is skipped for a market whose life is shorter than this — the
#: fine and coarse tiers already overlap it, and a third call buys nothing.
HOURLY_TIER_MIN_LIFETIME_HOURS = 48

#: Points kept per outcome after compaction. A "Race to the title" chart is
#: ~1,000 px wide and draws up to ten lines; past this each extra point is a
#: byte in every payload and cannot become a pixel. Sized ABOVE the raw
#: `attach_competitor_history` budget of 150 because the whole point of this
#: module is that 150 was hiding the moves.
TARGET_POINTS_PER_OUTCOME = 400

#: Heartbeat floor/ceiling for compaction. The floor is the finest granularity
#: either venue publishes; the ceiling stops an eight-month-old outright from
#: drawing a line whose flat stretches have a joint every six hours.
MIN_HEARTBEAT_SECONDS = 60
MAX_HEARTBEAT_SECONDS = 12 * 3600

#: Venue blend weights. Both venues are 0.8 in `utils/aggregation.py`'s source
#: table, so they are equal here — written out rather than assumed so that
#: changing one is an edit to a table and not a discovery.
VENUE_WEIGHTS: dict[str, float] = {
    "polymarket": 1.0,
    "kalshi": 1.0,
    "captures": 1.0,
}


# ---------------------------------------------------------------------------
# Layering
# ---------------------------------------------------------------------------


#: The widest a single point may claim, whatever its tier's spacing. Without a
#: cap, the 12-hourly ALL tier would claim six hours either side of every point
#: and swallow the hourly captures that carry the series' fresh right-hand edge —
#: the chart would then end wherever the last venue fetch ended, which is the
#: staleness this whole design exists to avoid.
MAX_CLAIM_RADIUS_SECONDS = 30 * 60


def claim_radius_seconds(
    points: Sequence[Point], *, cap_s: int = MAX_CLAIM_RADIUS_SECONDS
) -> float:
    """How close another tier's point may come before it is a near-duplicate.

    Half the tier's own MEDIAN spacing, capped. Median rather than mean because a
    venue series routinely has one enormous gap (a market that did not trade for
    a week) and one gap must not redefine what "adjacent" means for the other
    four hundred points.

    A tier of fewer than two points claims nothing: it has no spacing, and a
    single point that swallowed half an hour of a finer tier would be a lone
    reading vetoing a series.
    """
    if len(points) < 2:
        return 0.0
    diffs = sorted(
        (b[0] - a[0]).total_seconds() for a, b in zip(points, points[1:])
    )
    median = diffs[len(diffs) // 2]
    return min(float(cap_s), max(0.0, median / 2.0))


def layer_tiers(tiers: Sequence[Sequence[Point]]) -> list[Point]:
    """Stitch tiers into ONE series, finest first, without gaps or duplicates.

    `tiers` is ordered by priority — finest/most-trusted first. A lower-priority
    point is dropped only when a higher-priority tier already has a point within
    that tier's own :func:`claim_radius_seconds`; everywhere else it is kept.

    🔴 **CLAIMING BY PROXIMITY, NOT BY SPAN, AND THE TEST THAT FORCED IT.** The
    first version of this had each tier claim the closed interval between its
    first and last point. That is wrong in exactly the case the layering exists
    for: a venue that went dark for six hours in the middle of its own series
    still claimed those six hours, so our captures — the tier of last resort,
    whose whole job is to fill that hole — were refused. `layer_tiers` was
    opening the gap it is named for. Proximity claiming has no outer edge to
    over-claim with: a tier holds the instants it actually reported and nothing
    else.

    Guarantees, and they are what `tests/test_futures_chart_series.py` asserts:
      * output is sorted strictly ascending by timestamp
      * no timestamp appears twice, and no two points land inside a higher tier's
        claim radius of each other
      * a coarse tier still extends the reach — backwards past a fine tier's
        first point, and forwards past its last
      * no span present in ANY input tier is absent from the output

    Each input tier must itself be sorted ascending; callers get that from
    :func:`normalize_points`.
    """
    import bisect

    claimed_ts: list[float] = []   # sorted epoch seconds of every kept point
    claimed_r: list[float] = []    # parallel: the radius that point claims
    merged: dict[datetime, float] = {}

    for tier in tiers:
        pts = list(tier)
        if not pts:
            continue
        radius = claim_radius_seconds(pts)
        kept: list[Point] = []
        for ts, value in pts:
            epoch = ts.timestamp()
            # A point is refused when it falls inside the claim of ANY already
            # kept point. Only the neighbours on either side can be the one —
            # the claim list is sorted and every radius is capped.
            i = bisect.bisect_left(claimed_ts, epoch)
            blocked = False
            for j in (i - 1, i):
                if 0 <= j < len(claimed_ts):
                    if abs(claimed_ts[j] - epoch) <= claimed_r[j]:
                        blocked = True
                        break
            if blocked:
                continue
            kept.append((ts, value))

        for ts, value in kept:
            # A duplicate inside one tier keeps its FIRST reading; the tier is
            # sorted, so first is also earliest, and a venue that repeats a
            # timestamp is repeating a bucket, not reporting a move.
            if ts in merged:
                continue
            merged[ts] = value
            epoch = ts.timestamp()
            k = bisect.bisect_left(claimed_ts, epoch)
            claimed_ts.insert(k, epoch)
            claimed_r.insert(k, radius)

    return sorted(merged.items(), key=lambda p: p[0])


def normalize_points(
    raw: Iterable[tuple[Optional[datetime], Optional[float]]],
) -> list[Point]:
    """Sort ascending, drop unusable points, collapse duplicate timestamps.

    A venue point with no timestamp or no price is not a point — it is a hole in
    the payload, and carrying it forward as a zero would draw a cliff that never
    happened. Probabilities outside [0, 1] are dropped for the same reason: a
    chart that can render 202.9% has already lost the reader (#1139).
    """
    cleaned: dict[datetime, float] = {}
    for ts, value in raw:
        if ts is None or value is None:
            continue
        try:
            p = float(value)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(p) or p < 0.0 or p > 1.0:
            continue
        cleaned.setdefault(ts, p)
    return sorted(cleaned.items(), key=lambda p: p[0])


# ---------------------------------------------------------------------------
# Question identity — WHICH question, before WHOSE roster
# ---------------------------------------------------------------------------

#: Words that name the ANSWER SHAPE and never the question. Two markets that
#: differ only in these words are the same question asked twice — "Winner" and
#: "Champion" and "Outright" are three venues' words for one thing.
#:
#: Everything NOT in here is identity-bearing, which is the whole point: this is
#: a subtraction list, not a similarity score, so a word nobody thought about
#: (`polka`, `jersey`, `sprint`) keeps two questions apart by default.
GENERIC_QUESTION_WORDS = frozenset({
    "winner", "winners", "win", "wins", "won", "champion", "champions",
    "championship", "championships", "title", "titles", "outright",
    "outrights", "tournament", "tourney", "event", "election", "elections",
    "singles", "doubles",
    # Articles and joiners. `by` is here for "By-Election", which folds to two
    # tokens; both venues spell it the same way, so dropping it is symmetric.
    "a", "an", "the", "of", "to", "and", "at", "in", "for", "on", "by",
})

#: Words that name WHAT KIND OF COMPETITOR wins, which is an answer shape and
#: not a question — "Italian Grand Prix Winner" and "Italian Grand Prix: Driver
#: Winner" are one race.
#:
#: 🔴 THE COUNTERPARTS ARE DELIBERATELY ABSENT. `constructor`, `team`,
#: `manufacturer` and `stable` are the OTHER answer to the same race and stay
#: identity-bearing, so a drivers' market can never fold into a constructors'
#: one. Never add a word here without checking that its counterpart is a word
#: this set does not contain.
COMPETITOR_ROLE_WORDS = frozenset({
    "driver", "drivers", "rider", "riders", "golfer", "golfers",
    "player", "players", "individual",
})

#: One office, two spellings. Venues name the same race differently often enough
#: that a bare string comparison loses correct pairs — Kalshi writes "Ceará
#: gubernatorial election winner?" for Polymarket's "Ceará Governor Election
#: Winner". Folded BEFORE the generic words are subtracted.
IDENTITY_SYNONYMS = {
    "gubernatorial": "governor",
    "mayoral": "mayor",
    "presidential": "president",
    "parliamentary": "parliament",
    "senatorial": "senate",
    "congressional": "congress",
}

#: Gender is fenced SEPARATELY from the tournament, because it is the one
#: qualifier that two markets can differ on while sharing every other word: the
#: men's and women's US Open titles both fold to `{us, open}`. ATP and WTA are
#: gender words wearing a tour's name.
GENDER_WORDS = {
    "men": "men", "mens": "men", "man": "men", "male": "men", "atp": "men",
    "women": "women", "womens": "women", "woman": "women", "female": "women",
    "ladies": "women", "wta": "women",
    "mixed": "mixed",
}


def _fold_question(text: str) -> list[str]:
    """A market name as ASCII lowercase tokens. Apostrophes CLOSE, not split.

    "Men's" must fold to `mens` and not to `men` + `s`: a one-letter token is
    noise in every set operation below, and the possessive is the same word.
    Handles the curly apostrophe too — Polymarket writes "Men’s", Kalshi writes
    "Men's", and a fence that reads those as different questions is a fence that
    fails on the exact pair it exists for.
    """
    decomposed = unicodedata.normalize("NFKD", text or "")
    ascii_text = "".join(c for c in decomposed if not unicodedata.combining(c))
    ascii_text = ascii_text.replace("'", "").replace("’", "")
    return [t for t in re.split(r"[^a-zA-Z0-9]+", ascii_text.lower()) if t]


def _is_year(token: str) -> bool:
    """A season stamp. One venue prints it, the other does not, always."""
    return len(token) == 4 and token.isdigit() and token[:2] in ("19", "20")


def question_identity(
    name: Optional[str], *, category: Optional[str] = None
) -> tuple[frozenset[str], Optional[str]]:
    """WHICH question a market name asks: `(identity tokens, gender or None)`.

    The tokens left after subtracting the words that describe an answer rather
    than a question, the season, and the sport category — which carries no
    information here because the caller has already fenced on it.

        "US Open Men's Singles Winner"        -> ({us, open}, "men")
        "2026 Men’s US Open Winner (Tennis)"  -> ({us, open}, "men")
        "Cincinnati Open: Winner"             -> ({cincinnati, open}, None)

    Gender comes out separately because it is the qualifier two markets can
    differ on while every other word agrees.
    """
    tokens: set[str] = set()
    gender: Optional[str] = None
    category_tokens = set(_fold_question(category or ""))
    for raw in _fold_question(name or ""):
        token = IDENTITY_SYNONYMS.get(raw, raw)
        if token in GENDER_WORDS:
            gender = GENDER_WORDS[token]
            continue
        if token in GENERIC_QUESTION_WORDS or token in COMPETITOR_ROLE_WORDS:
            continue
        if _is_year(token) or token in category_tokens:
            continue
        tokens.add(token)
    return frozenset(tokens), gender


def same_question(
    left: Optional[str], right: Optional[str], *, category: Optional[str] = None
) -> bool:
    """Do two market names ask the SAME question? The fence, and it is strict.

    🔴 **WHY THIS EXISTS (CERT-881).** Cross-venue legs used to be chosen by
    outcome-name overlap alone. Measured on production 2026-09-04, over the
    exact population the fill task nominates, that picked the WRONG event four
    times:

        Kalshi US Open Men's Singles  -> Polymarket "Cincinnati Open: Winner"
                                         (0.879, beating the real US Open's 0.826)
        Kalshi Italian Grand Prix     -> Polymarket "Spanish Grand Prix" (1.000)
        Polymarket Vuelta a Espana    -> Kalshi Vuelta POLKA DOT JERSEY (1.000)
        Polymarket Berlin/Sachsen-Anhalt/Mecklenburg state elections
                                      -> Kalshi Rhineland-Palatinate (1.000)

    A roster is not an identity. Every tournament on a tour draws from one pool
    of players, every Grand Prix from one grid, and every German state election
    from one set of parties — so overlap approaches 1.0 exactly where it is most
    wrong. `blend_venues()` then averages another event's prices into this
    event's line, and the chart is denser and false.

    EQUALITY, NOT CONTAINMENT. A candidate whose identity is a superset —
    "Vuelta a Espana: Blue And White Polka Dot Jersey" over "Vuelta a Espana" —
    is a DIFFERENT prize in the same race, and containment would admit it. The
    cost of equality is the occasional correct pair refused when two venues
    spell a race differently; that costs the chart one venue's density and never
    costs it the truth, which is the right way round for this trade.

    An empty identity on either side never matches: a name that folds to nothing
    is a name this fence cannot vouch for.
    """
    left_tokens, left_gender = question_identity(left, category=category)
    right_tokens, right_gender = question_identity(right, category=category)
    if not left_tokens or not right_tokens:
        return False
    if left_tokens != right_tokens:
        return False
    # An unstated gender is not a contradiction — "Cincinnati Open: Winner"
    # names no draw and is refused on its tokens, not on this.
    if left_gender and right_gender and left_gender != right_gender:
        return False
    return True


# ---------------------------------------------------------------------------
# Blending — one question, one number
# ---------------------------------------------------------------------------


def blend_venues(
    by_venue: dict[str, Sequence[Point]],
    *,
    weights: Optional[dict[str, float]] = None,
) -> list[Point]:
    """Collapse per-venue series into ONE line — the standing ruling, applied.

    "The blend is the product": a page shows one number per question, and two
    venues disagreeing is a data fact to average, not a second line to draw. So
    this does NOT return two series for a renderer to overlay.

    Union the timelines, carry each venue's last known value forward to every
    timestamp at or after its own first point, and take the weighted mean of the
    venues that have spoken by then. A venue is never extrapolated BACKWARDS —
    before its first point it simply is not in the average, so a market that
    listed on Kalshi in June and on Polymarket in January draws Polymarket alone
    for the months when Polymarket alone existed, and the blend from June on.

    Weights default to :data:`VENUE_WEIGHTS`; an unlisted venue weighs 1.0.
    """
    weights = weights or VENUE_WEIGHTS
    active = {name: list(pts) for name, pts in by_venue.items() if pts}
    if not active:
        return []
    if len(active) == 1:
        return list(next(iter(active.values())))

    timeline = sorted({ts for pts in active.values() for ts, _ in pts})
    cursors = {name: 0 for name in active}
    last: dict[str, Optional[float]] = {name: None for name in active}

    out: list[Point] = []
    for ts in timeline:
        for name, pts in active.items():
            i = cursors[name]
            while i < len(pts) and pts[i][0] <= ts:
                last[name] = pts[i][1]
                i += 1
            cursors[name] = i
        num = 0.0
        den = 0.0
        for name, value in last.items():
            if value is None:
                continue
            w = weights.get(name, 1.0)
            num += value * w
            den += w
        if den > 0:
            out.append((ts, num / den))
    return out


# ---------------------------------------------------------------------------
# Compaction
# ---------------------------------------------------------------------------


def heartbeat_seconds_for(
    lifetime_seconds: float,
    *,
    target_points: int = TARGET_POINTS_PER_OUTCOME,
    floor_s: int = MIN_HEARTBEAT_SECONDS,
    cap_s: int = MAX_HEARTBEAT_SECONDS,
) -> int:
    """Spacing at which a FLAT stretch still earns a point.

    Moves are always kept (see :func:`compact_series`); this only sets how often
    a line that is not moving says so. Same rule as
    `event_chart_backfill.heartbeat_seconds_for`, re-stated here on the
    `(datetime, float)` grain this module works in rather than imported across a
    task/util boundary that would drag Celery into a pure module.
    """
    if lifetime_seconds <= 0 or target_points <= 0:
        return floor_s
    raw = lifetime_seconds / target_points
    return int(max(floor_s, min(cap_s, math.ceil(raw))))


def compact_series(
    points: Sequence[Point],
    *,
    target_points: int = TARGET_POINTS_PER_OUTCOME,
) -> list[Point]:
    """Keep every move, a heartbeat while flat, and both endpoints.

    The endpoints are kept for their own sake and not as a side effect: the first
    point is the market's opening opinion and the last is where it stands now,
    and those are the two values a reader compares. A compactor that could drop
    either would be trading away the thing the chart is read for.

    Compaction is by VALUE CHANGE, never by stride. Stride-downsampling (what
    `event_concept.downsample_points` does) is what turns a 164-change day into
    a 20-change staircase — it keeps points, which is not the same as keeping
    moves.
    """
    pts = list(points)
    if len(pts) <= 2:
        return pts

    lifetime = (pts[-1][0] - pts[0][0]).total_seconds()
    heartbeat = heartbeat_seconds_for(lifetime, target_points=target_points)

    kept: list[Point] = []
    last_value: Optional[float] = None
    last_ts: Optional[datetime] = None
    for index, (ts, value) in enumerate(pts):
        is_edge = index == 0 or index == len(pts) - 1
        changed = last_value is None or value != last_value
        stale = last_ts is None or (ts - last_ts).total_seconds() >= heartbeat
        if is_edge or changed or stale:
            if kept and kept[-1][0] == ts:
                continue
            kept.append((ts, value))
            last_value = value
            last_ts = ts

    # A market that moves on almost every bucket can still overrun the budget
    # (the specimen's 1-minute day is 164 changes; a volatile final is more).
    # Thin by DROPPING THE SMALLEST MOVES, not by stride — the biggest swings,
    # which are the story, survive to the end.
    if len(kept) > target_points:
        kept = _thin_by_smallest_move(kept, target_points)
    return kept


#: The reader's own range switch, as a point budget. THE BUDGET IS ALLOCATED PER
#: BAND, and this table is why.
#:
#: Compacting one 8-month series to 400 points spends the budget where the points
#: are, and after `interval=max` there are eight months of them: measured on the
#: specimen, a flat 400-point budget left the last DAY with 37 points. That is a
#: worse "1D" than the 129-point sampled series this whole build replaces — it
#: reaches the draw and loses the match. Each band is therefore compacted against
#: its own sub-budget, so what "1D" draws is a property of the 1D allocation and
#: not a leftover of how eventful January was.
#:
#: Read as `(band upper edge in hours, points)`, finest band first; the last
#: entry's `None` edge is everything older.
RANGE_BANDS: tuple[tuple[Optional[int], int], ...] = (
    (24, 150),      # "1D" — the match, at the venue's minutes
    (168, 90),      # "1W" adds the tournament
    (720, 80),      # "1M" adds the run-up
    (None, 80),     # "ALL" adds the reach back to the draw
)


def compact_by_band(
    points: Sequence[Point],
    now: datetime,
    *,
    bands: Sequence[tuple[Optional[int], int]] = RANGE_BANDS,
) -> list[Point]:
    """Compact each range band against its own budget, then concatenate.

    Bands are half-open and measured back from `now`: the first is `(now-24h,
    now]`, the next `(now-168h, now-24h]`, and so on, with a final open-ended
    band for everything older. Each is run through :func:`compact_series`
    separately, so every band keeps its own moves and its own endpoints.

    The seam between two bands is two points a few minutes apart, which is a
    denser joint than either side — never a gap, and never a duplicate, because
    the bands partition the timeline.
    """
    pts = list(points)
    if len(pts) <= 2:
        return pts

    out: list[Point] = []
    upper: Optional[datetime] = None
    seen: set[datetime] = set()
    for edge_hours, budget in bands:
        lower = None if edge_hours is None else now - timedelta(hours=edge_hours)
        band = [
            (ts, p) for ts, p in pts
            if (lower is None or ts > lower) and (upper is None or ts <= upper)
        ]
        upper = lower
        if not band:
            continue
        for ts, p in compact_series(band, target_points=budget):
            if ts in seen:
                continue
            seen.add(ts)
            out.append((ts, p))
    out.sort(key=lambda p: p[0])
    return out


def _thin_by_smallest_move(points: list[Point], target: int) -> list[Point]:
    """Drop interior points whose removal changes the drawn line least.

    Repeatedly removes the interior point with the smallest vertical deviation
    from the straight segment between its neighbours — the same idea as
    Douglas–Peucker, run to a point BUDGET instead of to a tolerance so the
    output size is predictable. Endpoints are never candidates.
    """
    if target < 2 or len(points) <= target:
        return points
    work = list(points)
    while len(work) > target:
        best_index = 1
        best_cost = None
        for i in range(1, len(work) - 1):
            (t0, p0), (t1, p1), (t2, p2) = work[i - 1], work[i], work[i + 1]
            span = (t2 - t0).total_seconds()
            if span <= 0:
                cost = 0.0
            else:
                frac = (t1 - t0).total_seconds() / span
                cost = abs(p1 - (p0 + (p2 - p0) * frac))
            if best_cost is None or cost < best_cost:
                best_cost = cost
                best_index = i
        work.pop(best_index)
    return work


# ---------------------------------------------------------------------------
# The plan a fetcher executes
# ---------------------------------------------------------------------------


class ClobCall(tuple):
    """One `prices-history` call: ``(interval, fidelity)``."""

    __slots__ = ()

    def __new__(cls, interval: str, fidelity: int):
        return super().__new__(cls, (interval, fidelity))

    @property
    def interval(self) -> str:
        return self[0]

    @property
    def fidelity(self) -> int:
        return self[1]


class CandleCall(tuple):
    """One Kalshi candlestick call: ``(period_interval, lookback)``.

    ``lookback`` is None for "the whole life of the market" — the fetcher turns
    that into the market's own listing time, which is the only place that is
    known.
    """

    __slots__ = ()

    def __new__(cls, period_interval: int, lookback: Optional[timedelta]):
        return super().__new__(cls, (period_interval, lookback))

    @property
    def period_interval(self) -> int:
        return self[0]

    @property
    def lookback(self) -> Optional[timedelta]:
        return self[1]


def clob_calls(lifetime_hours: float) -> list[ClobCall]:
    """The CLOB calls for one outcome, FINEST FIRST — the two-call shape.

    Two calls is the floor and, for most markets, the whole plan:

      * ``interval=1d, fidelity=1``   — the last day at 1-minute, which is what
        the "1D" switch draws and the only tier that can show an in-match swing.
      * ``interval=max, fidelity=720`` — 12-hourly for the market's entire life,
        the ONLY measured way past the ~31-day retention wall (module docstring).

    A third, hourly call is added for a market old enough that the gap between
    "yesterday at 1-minute" and "eight months at 12-hourly" is a visible loss of
    the last month's shape. Below :data:`HOURLY_TIER_MIN_LIFETIME_HOURS` it buys
    nothing: the coarse tier already samples that span more finely than the
    market has moved.

    Order is priority order for :func:`layer_tiers` — finest first, always.
    """
    calls = [ClobCall("1d", CLOB_FINE_FIDELITY)]
    if lifetime_hours >= HOURLY_TIER_MIN_LIFETIME_HOURS:
        calls.append(ClobCall("1m", CLOB_HOURLY_FIDELITY))
    calls.append(ClobCall("max", CLOB_COARSE_FIDELITY))
    return calls


def candle_calls(lifetime_hours: float) -> list[CandleCall]:
    """The Kalshi candlestick calls for one outcome, FINEST FIRST.

    Mirrors :func:`clob_calls` on the venue that speaks a different dialect:
    Kalshi takes an explicit ``[start_ts, end_ts]`` and a ``period_interval`` in
    minutes, so the tiers are expressed as lookbacks instead of interval names.

    The coarse tier is 1440 (daily) rather than 720, because 720 is not in
    :data:`KALSHI_PERIOD_INTERVALS` — Kalshi does not answer with an error for an
    unsupported interval, it answers with junk, so an unlisted value is never
    sent. Measured on the specimen: ``period_interval=1440`` returns 87 points
    back to listing (2026-06-09) in ONE request.
    """
    calls = [CandleCall(KALSHI_FINE_INTERVAL, timedelta(hours=FINE_TIER_HOURS))]
    if lifetime_hours >= HOURLY_TIER_MIN_LIFETIME_HOURS:
        calls.append(CandleCall(KALSHI_HOURLY_INTERVAL, timedelta(days=31)))
    calls.append(CandleCall(KALSHI_COARSE_INTERVAL, None))
    return calls


#: 🔴 **THE KALSHI BATCH BUDGET IS A PRODUCT, NOT A PERIOD COUNT.** The
#: candlestick endpoint refuses a request whose ``tickers × periods`` exceeds
#: 10,000, and it says so in its own words — measured 2026-09-04:
#:
#:     8 tickers × 1440 one-minute periods →  400
#:     {"details": "requested candlesticks across all markets: 11520,
#:                  max candlesticks: 10000"}
#:     7 × 1440 = 10080 → 400.   6 × 1440 = 8640 → 200.
#:
#: `event_chart_backfill.KALSHI_MAX_PERIODS_PER_REQUEST = 5000` is the SINGLE
#: ticker form of the same rule and is not wrong — it is half the ceiling, for
#: one market. Carrying that constant into a batched caller silently sizes the
#: request as if the budget were per-ticker, and the whole 1-minute tier for a
#: twelve-outcome field comes back 400 while the hourly tiers succeed: a chart
#: that quietly loses exactly the resolution it was built for.
#:
#: Sized at 9,000 rather than 10,000 so a period boundary landing one candle
#: over does not turn the finest tier into a zero.
KALSHI_MAX_CANDLES_PER_REQUEST = 9000


def ticker_batches(
    tickers: Sequence[str],
    *,
    periods: int,
    max_candles: int = KALSHI_MAX_CANDLES_PER_REQUEST,
) -> list[list[str]]:
    """Split a field into groups that fit under the shared candlestick budget.

    ``periods`` is how many candles ONE ticker will produce for the window being
    requested. The group size is the budget divided by that, floored at one — a
    single ticker whose own window already exceeds the ceiling still gets its
    request, and the window chunking (``candle_windows``) is what keeps that one
    inside the limit.
    """
    if not tickers:
        return []
    per_group = max(1, int(max_candles // max(1, periods)))
    return [
        list(tickers[i:i + per_group])
        for i in range(0, len(tickers), per_group)
    ]


def series_reach_summary(points: Sequence[Point], now: datetime) -> dict:
    """Point counts per RANGE, the shape the queue asks for in the inbox note.

    Reports what each switch on the chart would actually draw from this one
    layered series, which is the honest way to state "1D → 1-minute": the client
    filters the same series, so the density at each range is a property of the
    series, not of a per-range fetch.
    """
    if not points:
        return {"total": 0, "1d": 0, "1w": 0, "1m": 0, "all": 0, "changes": 0}

    def _count(hours: Optional[int]) -> int:
        if hours is None:
            return len(points)
        cutoff = now - timedelta(hours=hours)
        return sum(1 for ts, _ in points if ts >= cutoff)

    values = [p for _, p in points]
    changes = sum(1 for i in range(1, len(values)) if values[i] != values[i - 1])
    return {
        "total": len(points),
        "1d": _count(24),
        "1w": _count(168),
        "1m": _count(720),
        "all": len(points),
        "changes": changes,
        "earliest": points[0][0].isoformat(),
        "latest": points[-1][0].isoformat(),
    }
