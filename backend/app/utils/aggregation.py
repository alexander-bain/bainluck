"""
Multi-source probability aggregation engine.

Combines sportsbook consensus, prediction markets (Kalshi, Polymarket),
and statistical models (ESPN, Bain Luck Model) into a single "Bain Luck"
aggregate probability.

Algorithm: Weighted median with staleness decay and a per-source weight cap.
NO smoothing — see below.

A weighted median is outlier-resistant only under two conditions the plain
algorithm does not enforce, and #1829 is what it cost to learn that:

  1. No single source may hold enough weight to straddle the midpoint alone.
     `betting` held 42% and did exactly that, so the "median" returned the
     sportsbook's number verbatim. `MAX_SOURCE_WEIGHT_SHARE` enforces it now.
  2. A source that stopped reporting must lose influence. All three of this
     module's aggregation paths now decay stale readings — the two time-series
     paths by absolute age, the point-in-time hero by age RELATIVE to the
     freshest source on the same event.

This docstring used to claim "weighted median with staleness decay" while the
point-in-time hero — the function behind every card and every header —
implemented only the first half. The names differ by one letter
(`compute_aggregate_probability` vs `compute_aggregated_probability`), which is
how it went unnoticed. Read the constants block below before changing weights.

Source weights reflect depth and reliability:
  - Sportsbook consensus (3.0): Deep liquidity, 5-15 bookmakers
  - ESPN model (1.5): Play-by-play responsive, proprietary
  - Bain Luck Model (1.0): Statistical, principled, but simple
  - Kalshi (0.8): Regulated prediction market, thinner liquidity
  - Polymarket (0.8): Largest prediction market, good liquidity
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from app.utils.probability_eligibility import (
    ELIGIBILITY_KEY,
    EligibilityRecord,
    is_refused,
)
from app.utils.source_divergence import (
    SourceDivergence,
    assess_divergence,
)

# Base weights per source — higher = more influence on the aggregate
SOURCE_WEIGHTS: dict[str, float] = {
    "final_result": 5.0,  # Resolved game outcome from score (always correct)
    "betting": 3.0,  # Sportsbook consensus (5-15 books)
    "espn": 1.5,  # ESPN proprietary model
    "stat_model": 1.0,  # Bain Luck statistical model
    "kalshi": 0.8,  # Kalshi prediction market
    "polymarket": 0.8,  # Polymarket prediction market
    "mlb": 0.8,  # MLB Model (MLB Stats API)
}

# Staleness parameters (in seconds)
STALENESS_GRACE_PERIOD = 120  # 2 min: no penalty
STALENESS_DECAY_WINDOW = 180  # Next 3 min: linear decay to 0
MAX_STALENESS = STALENESS_GRACE_PERIOD + STALENESS_DECAY_WINDOW  # 5 min: fully stale

# ── #1829: RECENCY DECAY + WEIGHT CAP (Alex ruling 2026-08-13) ───────────────
#
# The specimen. Red Sox @ Blue Jays, event 15192596, top of the 9th, Toronto
# trailing 0-5 (final 0-7). The header read **87 - 13** while the chart's blend
# line sat at ~0. `win_probability_sources` held, home = Blue Jays:
#
#     mlb 0.001 (w 0.8) · espn 0.008 (w 1.5) · stat_model 0.001 (w 1.0)
#     betting 0.1347 (w 3.0) · kalshi 0.565 (w 0.8)
#
# Sorted, the cumulative weight crosses the 3.55 midpoint INSIDE betting's own
# 3.0 mass, so the weighted median returned `0.1347` verbatim. #240 Item 1
# switched this function mean -> median precisely to stop a stale sportsbook
# dragging the hero; it did not stop it, it made the hero EQUAL to it.
#
# Two independent faults, and Alex ruled both:
#
#   1. RECENCY. `betting` was ~17-20 minutes stale at that moment and nothing
#      could express it. Measured from `odds_snapshots`: every bookmaker had
#      PULLED the moneyline by 21:08 UTC (the game was out of reach), so
#      `_process_event_odds` collected an empty `all_home_probs` and simply
#      stopped rewriting the key — the last write was an unweighted mean over
#      the one book still quoting. mlb/espn/stat_model were seconds fresh and
#      all three said ~0. They were out-voted by a frozen number.
#
#   2. SHARE. `betting` alone held 42% of total weight (3.0 / 7.1). A weighted
#      median is outlier-resistant only when no single source can straddle the
#      midpoint by itself. This one could.
#
# THE DECAY IS RELATIVE, NOT ABSOLUTE, and that is the whole safety argument.
# Each source is aged against the FRESHEST stamped source on the same event,
# never against the wall clock. Consequences, all of them load-bearing:
#
#   - An event whose sources are ALL an hour old is unchanged. Uniform age is
#     not staleness; it is the polling cadence. Only DISAGREEMENT in age is.
#   - There is no clock in the computation at all, so gotcha #44 cannot apply:
#     no anchor to drift, no test that reads differently at 4pm.
#   - The freshest source always has multiplier 1.0, so the weights can never
#     all collapse to zero and the blend can never become undefined.
#
# MONOTONE. An entry with no `updated_at` keeps FULL weight, so an event whose
# JSONB has not yet been re-written by a stamping writer computes bit-for-bit
# what it computes today. The decay half is therefore inert until the writers
# deploy and re-poll; the cap half is live immediately. Said plainly because
# the two halves have different blast radii and only one is measurable before
# the deploy.
HERO_RELATIVE_GRACE_SECONDS = 600.0  # 10 min of age difference: no penalty
HERO_RELATIVE_DECAY_SECONDS = 1800.0  # next 30 min: linear decay to the floor
HERO_MIN_STALENESS_MULTIPLIER = 0.1  # a floor, not zero — see below

# The floor exists so decay DEMOTES a source instead of deleting it. A source at
# 10% of its base weight cannot carry a median BY VALUE — its own reading is
# never the one returned — but it CAN still decide which other source is the
# median BY POSITION, and that is not a small effect. #5542, event 15304937: an
# `mlb` arm 131 min behind the freshest sits at this floor and still holds a 30%
# post-cap share, which is enough mass below the middle to move the crossing from
# kalshi 0.99 to polymarket 0.455 — 53 points, across the favourite line.
#
# So do not read this floor as "harmless"; the earlier wording ("cannot carry a
# median") was true by value and false by position, and it is load-bearing prose
# for whoever tunes the constant next. What remains true: it still breaks ties and
# still shows up in the envelope check — and "we stopped hearing from Kalshi" is
# not the same claim as "Kalshi does not exist".

MAX_SOURCE_WEIGHT_SHARE = 0.35  # no single source may exceed this share
MIN_SOURCES_FOR_WEIGHT_CAP = 3

# WHY 0.35, DERIVED FROM THE SPECIMEN RATHER THAN PICKED. On event 15192596 the
# sources below `betting` carry a cumulative 3.3 and the four non-betting
# sources carry 4.1, so `betting` stops straddling the midpoint exactly when
#
#     3.3 >= (4.1 + B) / 2   ->   B <= 2.5   ->   share <= 2.5/6.6 = 0.379
#
# A cap of 0.40 therefore does NOT fix Alex's header — it leaves the hero at
# 0.1347 — which is worth knowing before anyone "rounds it up to a nicer
# number". 0.35 clears the bound with margin and sits just above the 1/3 that
# uniform weighting would give three sources.

# WHY THE CAP IS GATED ON THREE SOURCES, measured rather than chosen. With two
# sources a weighted median just returns whichever side holds half the weight,
# so ANY cap below 0.5 hands every two-source event to the lighter source. On
# 2026-08-13 that population was 95 scheduled + 125 recently-completed + 6 live
# events, virtually all of them `betting` + one model: capping there would flip
# hundreds of heroes away from the sportsbook with no evidence that the model
# is better, which is a different product decision than the one Alex ruled.
# With two sources there is no outlier to resist — there is a disagreement, and
# the weight table IS the tiebreak. The cap is what makes a MEDIAN honest, and
# a median needs three points before the word means anything.

# `final_result` is the graded outcome, not a forecast. It is exempt from both
# mechanisms: it cannot go stale, and capping its share would let live-market
# noise out-vote the actual result on a settled game — the exact inversion
# "settled means settled" forbids.
_UNCAPPED_SOURCES = frozenset({"final_result"})

# NO SMOOTHING (standing ruling #4, UX-P003). The blend line the chart draws used
# to run an α=0.3 exponential moving average over the per-bucket weighted median.
# That is smoothing, and smoothing HIDES real movement — the thing the chart exists
# to show. It also silently de-synced the surfaces: because the EMA lags, the last
# point of `aggregate_line` (the chart's live edge, and the web hero's live source)
# drifted away from `compute_aggregate_probability()` (the Discover card and the
# backend `hero_probability`), so one game showed two different numbers on two
# screens. Measured on production 2026-08-05 (live MLB): Giants @ Rangers card 60%
# vs chart 78%, of which +14.5 pts was attributable to the EMA alone.
#
# Staleness decay below is deliberately KEPT: that is source *weighting* (how much
# a reading counts), not smoothing (blurring the output over time).


@dataclass
class TimestampedProb:
    """A probability reading at a point in time."""

    timestamp: datetime
    home_probability: float


@dataclass
class SourceReading:
    """Latest reading from a single source, with weight."""

    source: str
    probability: float
    weight: float
    stale_seconds: float


def _staleness_weight(stale_seconds: float) -> float:
    """
    Compute weight multiplier based on staleness.

    0-2 min: 1.0 (full weight)
    2-5 min: linear decay from 1.0 to 0.0
    5+ min:  0.0 (fully dropped)
    """
    if stale_seconds <= STALENESS_GRACE_PERIOD:
        return 1.0
    elif stale_seconds >= MAX_STALENESS:
        return 0.0
    else:
        elapsed_past_grace = stale_seconds - STALENESS_GRACE_PERIOD
        return max(0.0, 1.0 - elapsed_past_grace / STALENESS_DECAY_WINDOW)


def _coerce_timestamp(raw: Any) -> Optional[datetime]:
    """Read an ``updated_at`` out of a JSONB source entry, or give up quietly.

    Anything unparseable returns ``None``, which means "no timestamp", which
    means "full weight" — the monotone default. A malformed stamp must never
    raise and must never be worse for the reader than no stamp at all.
    """
    if isinstance(raw, datetime):
        return raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return None
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    return None


def parse_source_entry(raw: Any) -> tuple[Optional[float], Optional[datetime]]:
    """Split a ``win_probability_sources`` entry into (value, updated_at).

    The column holds BOTH shapes and always has (gotcha behind #1000): a bare
    float from the older writers, or ``{"value": x, "updated_at": "..."}`` from
    the stamping ones. Every reader of this column has to handle both; this is
    the one place that decides how.
    """
    if isinstance(raw, bool):
        return None, None
    if isinstance(raw, (int, float)):
        return float(raw), None
    if isinstance(raw, dict):
        value = raw.get("value")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None, None
        return float(value), _coerce_timestamp(raw.get("updated_at"))
    return None, None


def stamp_source_reading(
    sources: Optional[dict],
    source: str,
    value: float,
    now: Optional[datetime] = None,
    eligibility: Optional[EligibilityRecord] = None,
) -> dict:
    """Write one source into ``win_probability_sources`` WITH its write time.

    Returns a new dict — callers pass the result straight into a Core
    ``update()`` (gotcha #4: ORM attribute assignment on this JSONB silently
    fails). Every other key is copied through untouched, in whatever shape it
    already had; this never rewrites a sibling.

    This is the writer half of #1829, and it is the ONLY thing that makes the
    hero's recency decay do anything. A source that does not come through here
    keeps full weight forever — correct as a default, and invisible as a bug,
    so if you add a seventh writer of this column, add it here too.

    ``eligibility`` is CU-4 (#5311): the record naming the rule that admitted
    this reading and the market it came from. Optional, and omitting it is not a
    silent downgrade — a reading with no record grades `UNVERIFIED` rather than
    `VERIFIED`, so a writer that does not pass one is VISIBLE in the census
    instead of being indistinguishable from a gated one, which is the whole
    defect this record exists to end.

    A ``None`` here never CLEARS a record a previous pass wrote. That is the same
    merge discipline the entry already has, and it matters more for this key than
    for the others: the writers run at different cadences over the same event
    (the 15-minute matcher, the 120-second poll, the WS fast lane), so a writer
    that has not yet adopted the record would otherwise strip the evidence a
    writer that has just finished stamping — and the column would oscillate
    between substantiated and not, at whichever cadence is faster.
    """
    updated = dict(sources or {})
    stamp = now or datetime.now(timezone.utc)
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)

    # MERGE into an existing dict entry, never replace it. Entries in this
    # column carry sibling keys that nothing here knows about — the seeded
    # event fixture holds `{"value": x, "home_probability": x}`, and
    # `_apply_final_pm_win_prob`'s own suite pins a `weight` key as preserved.
    # The first draft assigned a fresh two-key dict and silently dropped all of
    # them. A writer whose job is to ADD a field must not be a writer that
    # deletes fields it does not recognise.
    existing = updated.get(source)
    entry = dict(existing) if isinstance(existing, dict) else {}
    entry["value"] = value
    entry["updated_at"] = stamp.isoformat()
    if eligibility is not None:
        entry[ELIGIBILITY_KEY] = eligibility.to_entry()
    updated[source] = entry
    return updated


def source_observation_time(
    row: Any, now: Optional[datetime] = None
) -> Optional[datetime]:
    """When the VENUE was last seen quoting the price on ``row`` (#4028).

    The `updated_at` half of `stamp_source_reading` is an OBSERVATION time, and
    a writer that passes its own `now()` is asserting it observed the venue at
    that instant. A writer that merely re-read a row it already had is not, and
    the difference is the whole bug: on 2026-09-08 the 15-minute matcher
    re-stamped a Polymarket container whose outcomes had not been touched since
    the previous evening, so a settled market held the freshest stamp on an
    unstarted game, `_relative_staleness_multiplier` decayed the sportsbook
    against it (3.0 -> 0.6084 under an undecayed 0.8), and the divergence gate
    printed `Marlins 1% - 99% Mets` over the caption "18 sportsbooks".

    THE GENERAL CLAUSE, because the decay is not the thing that is wrong:
    relative recency assumes a source STOPS PUBLISHING WHEN IT STOPS KNOWING,
    and that assumption was written down nowhere. A re-stamp is only honest when
    it records a re-OBSERVATION. Ask it of any recency rule you add here: what
    does a source that is dead but still transmitting do to it?

    ``row`` is duck-typed, like everything else in this module: anything with a
    ``last_updated``, which `futures_outcomes` documents as "when did the poller
    last SEE this row" — exactly the question. Returns ``None`` when the row
    cannot answer, and ``None`` means "you have no observation time, use your
    own" — never "old". Clamped to ``now``, because a stamp in the future reads
    as the freshest thing on the event and would decay every honest source
    against a clock skew.
    """
    observed = _coerce_timestamp(getattr(row, "last_updated", None))
    if observed is None:
        return None
    reference = now or datetime.now(timezone.utc)
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=timezone.utc)
    return min(observed, reference)


def oldest_observation_time(
    rows: Any, now: Optional[datetime] = None
) -> Optional[datetime]:
    """When the venue was last seen quoting EVERY row that moved the number.

    `source_observation_time` answers the question for one row. A published
    figure is not always one row: a devigged reading is the mean of two markets
    that are FETCHED SEPARATELY and therefore age separately, so after a partial
    refresh a fresh 70% primary can be averaged with a sibling last seen two
    hours ago. Stamping that composite off the primary alone asserts the whole
    of it was observed when its freshest half was — #4028's over-claim, one
    level up, and the reason CERT-2745 refused the first cut of #5661.

    The composite is only as fresh as its STALEST contributor, so this returns
    the minimum. A single-row sequence gives exactly `source_observation_time`,
    which is why callers can pass `(outcome,)` and change nothing.

    ABSTAINS — returns ``None`` — when the sequence is empty or when ANY
    contributor cannot say when it was seen. That is deliberate and it is the
    weaker-looking half of the rule, so: `None` means "you have no observation
    time, use your own" (the contract `source_observation_time` already has),
    and the alternative — stamping the oldest KNOWN contributor — would quietly
    assert an observation time for a row that has none, which is the class of
    claim this helper exists to stop making. An unknown contributor is not an
    old one; it is an unmeasured one, and the two must not be collapsed.
    """
    rows = list(rows or ())
    if not rows:
        return None
    observed = []
    for row in rows:
        seen = source_observation_time(row, now=now)
        if seen is None:
            return None
        observed.append(seen)
    return min(observed)


def wps_numeric_sql(source: str, column: str = "win_probability_sources") -> str:
    """SQL that reads one source's numeric probability out of the JSONB.

    The Python side has ``parse_source_entry``; this is the same decision for
    the SQL side, and it exists because the naive form is both obvious and
    wrong::

        (win_probability_sources->>'betting')::float

    ``->>`` on an OBJECT member returns the object's JSON *text*, and casting
    ``{"value": 0.1347, ...}`` to float raises — so a query written that way
    does not degrade, it dies, and a nearby ``IS NOT NULL`` guard does not save
    it. This mirrors the CASE that ``source_intelligence._BETTING_CTE`` already
    proved in production.

    ``source`` is interpolated, so it must be a literal from
    ``SOURCE_WEIGHTS`` — never user input. Enforced, not merely asked for.
    """
    if source not in SOURCE_WEIGHTS:
        raise ValueError(f"unknown win-prob source for SQL interpolation: {source!r}")
    return (
        f"CASE "
        f"WHEN jsonb_typeof({column}->'{source}') = 'number' "
        f"THEN ({column}->>'{source}')::float "
        f"WHEN jsonb_typeof({column}->'{source}') = 'object' "
        f"THEN ({column}->'{source}'->>'value')::float "
        f"END"
    )


#: Statuses in which the game has NOT started. See `_relative_decay_applies`.
_PREGAME_STATUSES = frozenset({"scheduled"})


def _relative_decay_applies(status: Optional[str]) -> bool:
    """Whether relative recency decay may touch this event's weights (#1999).

    RELATIVE RECENCY IS AN IN-PLAY RULE, and #1829 never said so out loud
    because its specimen was in-play: a sportsbook frozen at 87% while a game
    it had stopped quoting went to 0-5 in the 9th. Every line of that reasoning
    assumes the sources are all watching one fast-moving truth, so that a source
    which has fallen behind the others has fallen behind the GAME.

    Before first pitch nothing is moving, and the assumption inverts. A
    sportsbook reprices a Saturday fixture a handful of times a day; Kalshi
    ticks all night. The age disagreement between them is then the pure cadence
    difference the decay's own docstring promises to ignore ("uniform age is not
    staleness; it is the polling cadence") — only measured BETWEEN two pollers
    instead of across one. Nothing has gone stale. The sportsbook's line from
    four hours ago is still the sportsbook's opinion.

    MEASURED, 2026-09-11 23:30Z, the shipped `compute_aggregate_probability`
    over real `win_probability_sources` rows on the whole -6h/+48h board:

        status       multi-source   decay moves the number   median    max
        scheduled            362                      128    12.0pt   30.0pt
        suspended             25                       14     7.8pt   43.0pt
        completed             32                        3     1.0pt    3.8pt
        live                  16                        1     0.5pt    0.5pt

    So the decay does essentially nothing on the population it was built for and
    12 points of damage on the one it was never reasoned about. `betting` — the
    3.0 source, our heaviest — sits at its 0.1 floor on 224 of those 378 events
    and is the source the decay removes from the hero in 96 of the 129 changes.

    THE SPECIMEN IS ON A MARQUEE FIXTURE. Aston Villa v Nottingham Forest
    (15297691, EPL, kickoff +14h): 18 sportsbooks say 63.4%, one Kalshi price
    says 42.5%, betting's stamp is 3.5h older, so it decays 3.0 -> 0.3 and
    production serves `hero_probability = 0.425` under `hero_probability_source
    = "blend"`. The page captions it "11 sportsbooks" while its own chart line
    sits at ~59% for three days — #240's hero-disagrees-with-chart contradiction
    rebuilt out of the decay instead of out of the mean.

    THE GATE IS PRE-GAME ONLY, WHICH IS NARROWER THAN ALL THREE CANDIDATES
    #1999 LISTED, and the third row of that table is why. Gating on
    ``status == 'live'`` — the issue's first candidate — would also stop
    decaying `suspended`, and there the decay is currently RIGHT: those 14 rows
    are finished games whose Kalshi leg has settled to 0.01/0.99, and undecaying
    them would republish the last in-play sportsbook line over a settled market
    (15308773: 0.01 -> 0.4401). Refusing the decay only where the game has not
    started leaves live, suspended, completed and voided bit-for-bit unchanged,
    so the blast radius is exactly the population whose premise fails.

    An unknown or absent status keeps decaying — the monotone default, the same
    one `effective_source_weights` gives an entry with no ``updated_at``.
    """
    return (status or "").lower() not in _PREGAME_STATUSES


def pregame_boundary(
    status: Optional[str],
    commence_time: Optional[datetime],
    now: Optional[datetime] = None,
) -> Optional[datetime]:
    """The instant before which a CHART bucket is pre-game (#4976, under #1999).

    `_relative_decay_applies` answers "is this event pre-game?" for the hero,
    which renders one instant and so can ask the event's status. The chart
    renders every instant the event has had, and only the newest of them has a
    status — so the same question is asked per bucket, of the clock:

    * the event has NOT started (``scheduled``): every bucket drawn so far is
      pre-game, including the ones after a slipped ``commence_time`` on a
      delayed start — the hero is not decaying there, so neither may the line;
    * the event HAS started: the buckets before ``commence_time`` were pre-game
      when they happened, and the in-play rule (#1829/#6461) owns the rest;
    * no ``commence_time``: ``None`` — nothing to measure a bucket against.

    THREE THINGS THIS DOES THAT #1999 COULD NOT, SAID OUT LOUD BECAUSE THE HERO
    HAS NO HISTORY AND SO NEVER HAD TO DECIDE THEM (authority review, #4976).

    1. IT IS NOT CONFINED TO ``scheduled`` EVENTS. Every started status —
       ``live``, ``completed``, ``suspended``, ``voided`` — takes the second
       branch, so the pre-kickoff SEGMENT of an already-finished chart stops
       decaying too. On the production board of 2026-09-17 that is 3,692 of
       5,965 events in the last seven days, against 2,188 ``scheduled`` ones.
       The reasoning transfers cleanly (before first pitch nothing was moving,
       whatever the event later became) but the blast radius is the whole
       history of the product's charts, not one pre-game cohort, and a review
       that reads only the ``scheduled`` specimen has not seen it.

    2. ``commence_time`` IS THE LISTED START, NOT AN EVIDENCED ONE. Alex,
       2026-09-14: "Scheduled kickoff/capture timestamps are not automatically
       actual start/finish." No column in this schema records an observed
       start, so there is nothing better to ask. The consequence is a ONE-TIME
       RECLASSIFICATION, not a steady state: a delayed fixture is expressed here
       as ``scheduled`` with a ``commence_time`` in the past (14 such rows on
       2026-09-17), and while it holds that status the whole timeline is
       pre-game; the instant it flips to ``live`` the slipped window falls back
       onto the in-play rule and those buckets are redrawn. Measured on a
       two-hour slip: 8 of 12 buckets move, the largest by 16.0pp, on one
       refresh. That is narrower than today's behaviour in BOTH states, so it is
       not a regression — but it is a real inconsistency and it is bounded only
       by the evidenced-actual-start work (#6158 / #5140 / #1833). When an
       observed start lands, this helper takes it and the inconsistency closes.

    3. THE EXEMPTION NEVER REACHES THE BUCKET THE HERO IS RENDERING (CERT-3112).
       An earlier draft gave an unknown status the started branch and argued the
       divergence was deliberate: "this bucket is earlier than the listed start"
       is a fact about the clock and does not need the status to be legible.
       That argument is sound for an event that HAS started and wrong for one
       that has not. When the listed start is still ahead of ``now`` and the
       hero is decaying — an unknown or unreadable status, ``postponed``,
       anything outside ``_PREGAME_STATUSES`` — EVERY bucket drawn so far is
       "before the listed start", so the exemption covers the newest one too,
       and the chart's right edge stops agreeing with the big number above it.
       Executed on the graded sha: betting 0.62 quoted hours ago against a fresh
       kalshi 0.36, status unknown, kickoff in an hour — hero 0.36, chart edge
       0.62, one screen, two answers. Before this helper existed both paths said
       0.36. So a started event still exempts its pre-kickoff segment (that is
       point 1, and it is the ship), and an event whose start has not arrived
       takes no chart-only exemption at all: ``None``, the in-play rule
       everywhere, bit-for-bit #1999's monotone default. The blend is the
       product — one number per question.

       Refusing outright rather than clamping to ``now`` is deliberate: a
       boundary of ``now`` would exempt the whole history and decay only the
       final bucket, which manufactures a step at the right edge — the very
       shape this ship exists to remove.
    """
    if commence_time is None:
        return None
    if not _relative_decay_applies(status):
        return max(commence_time, now) if now is not None else datetime.max.replace(
            tzinfo=commence_time.tzinfo
        )
    # The hero decays this event. If its listed start has not arrived, every
    # bucket is pre-kickoff and the exemption would cover the edge the hero
    # renders — see point 3. `now is None` cannot tell upcoming from started,
    # and the only caller passes it.
    if now is not None and commence_time > now:
        return None
    return commence_time


def _relative_staleness_multiplier(
    relative_age_seconds: float,
    floor: float = HERO_MIN_STALENESS_MULTIPLIER,
) -> float:
    """Weight multiplier for a reading that is `relative_age` older than the
    freshest reading on the same event.

    0-10 min behind:   1.0
    10-40 min behind:  linear from 1.0 down to the floor
    40+ min behind:    the floor

    ``floor`` is the terminal multiplier, and it is a parameter because the two
    surfaces that use this shape want different endings for reasons that are
    about the surface, not about recency. The HERO is one number at one instant:
    demoting a lapsed arm to 10% keeps "we stopped hearing from Kalshi" distinct
    from "Kalshi does not exist" (#1829, and #5542 on why that floor still has
    teeth by position). The CHART is an unbounded time axis: a floor there would
    carry a source that went dark at the first pitch across every remaining
    bucket of a four-hour game, which is indefinite carry-forward, so the series
    passes ``floor=0.0`` and a source that falls 40 minutes behind its peers
    leaves. Default keeps the hero bit-for-bit.
    """
    if relative_age_seconds <= HERO_RELATIVE_GRACE_SECONDS:
        return 1.0
    past_grace = relative_age_seconds - HERO_RELATIVE_GRACE_SECONDS
    if past_grace >= HERO_RELATIVE_DECAY_SECONDS:
        return floor
    decayed = 1.0 - (past_grace / HERO_RELATIVE_DECAY_SECONDS)
    return max(floor, decayed)


def cap_weight_shares(
    weights: list[float],
    exempt: Optional[list[bool]] = None,
) -> list[float]:
    """Scale down any source holding more than ``MAX_SOURCE_WEIGHT_SHARE``.

    Below ``MIN_SOURCES_FOR_WEIGHT_CAP`` contributors this is the identity
    function — see the constant's note for why that gate is not a fudge.

    SOLVED, NOT ITERATED, and the first draft of this function is why that is
    written down. Capping the largest source lowers the TOTAL, which RAISES
    every other source's share — so "cap the biggest, repeat" oscillates toward
    the answer geometrically and needs ~30 passes to land. The draft bounded the
    loop at ``len(weights) + 2``, which is plenty for the common one-source-over
    case and silently insufficient the moment two sources are over: it returned
    weights whose largest share was 0.58 against a 0.35 cap, and returned them
    without complaint. That shape is not exotic — plain ``betting`` + ``espn`` +
    one market reaches it on the SECOND pass, because capping betting is what
    pushes espn over.

    The closed form. Sort the non-exempt weights descending and suppose the top
    ``k`` end up capped at a common value ``x`` while the rest keep theirs::

        T = k*x + tail + exempt          x = c*T
        =>  x = c * (tail + exempt) / (1 - c*k)

    ``k`` is the smallest value for which ``x`` lands between the k-th weight
    (which must actually be reduced) and the (k+1)-th (which must not need to
    be). At most ``floor(1/c)`` sources can exceed the cap at once — three
    sources cannot each hold 35% — so the search is short and always succeeds.
    """
    capped = [float(w) for w in weights]
    if exempt is None:
        exempt = [False] * len(capped)
    if sum(1 for w in capped if w > 0) < MIN_SOURCES_FOR_WEIGHT_CAP:
        return capped

    cappable = [i for i in range(len(capped)) if not exempt[i] and capped[i] > 0]
    if not cappable:
        return capped
    exempt_mass = sum(capped[i] for i in range(len(capped)) if i not in set(cappable))

    order = sorted(cappable, key=lambda i: capped[i], reverse=True)
    vals = [capped[i] for i in order]
    c = MAX_SOURCE_WEIGHT_SHARE

    # `k` runs to len(vals) INCLUSIVE — capping EVERY cappable source is a real
    # solution, and it is the only one when the exempt mass is what the cap has
    # to be taken against. A 20k-case fuzz found this: with one cappable source
    # and two exempt ones the loop simply never tried k=1 and returned the
    # weights untouched, cap violated, quietly.
    for k in range(len(vals) + 1):
        if c * k >= 1.0:
            break  # unreachable at c < 1/2 with the ordering guarantee above
        x = c * (sum(vals[k:]) + exempt_mass) / (1.0 - c * k)
        reduces_the_capped = k == 0 or x <= vals[k - 1] + 1e-12
        spares_the_rest = k >= len(vals) or x >= vals[k] - 1e-12
        if reduces_the_capped and spares_the_rest:
            for j in range(k):
                capped[order[j]] = x
            return capped
    return capped


def _weighted_median(values: list[float], weights: list[float]) -> float:
    """
    Compute weighted median.

    Sort values, accumulate weights, find the value at the 50th percentile
    of cumulative weight.

    ON AN EXACT TIE THE STRADDLING PAIR IS AVERAGED (#5425), because otherwise
    the answer is decided by an implementation accident. The weighted median is
    the minimiser of ``sum(w_i * |x - x_i|)``. When the cumulative weight lands
    EXACTLY on half, every point in ``[v_i, v_j]`` minimises it equally — the
    statistic is genuinely ambiguous over that whole interval — and the loop
    below used to break the tie with ``>=``, which silently means "take the
    lower one, always".

    That is not a rounding curiosity; it is the normal shape of a two-venue
    event. Two sources at equal weight give ``cumulative == half`` at the first
    value for ANY weight (``w + w`` is exact in binary floating point and so is
    ``/2``), so kalshi-plus-polymarket ALWAYS published the lower venue. #1999
    made that shape common by switching the pre-game decay off, which is what
    turned an old latent bug into a visible one.

    In play it is worse than arbitrary: replaying the Gauff-Rybakina tape
    (event 15308901, 410 readings) through the shipped aggregator, 1,728 of
    1,728 publications were one source's value verbatim and the selection
    flipped 30 times — each flip teleporting the published number across the
    whole inter-venue spread, up to 15.5 points, WITH THE WEIGHTS UNCHANGED at
    0.8/0.8. Nothing happened in the match; the two venues merely crossed.

    MEASURED, 2026-09-12 04:55Z, this function replayed over the raw
    `win_probability_sources` of 1,639 production rows:

        population                rows   reach median   move   median   max
        board -6h/+48h             771            732     55   0.42pt  4.25pt
        live/suspended/completed   868            765      4   0.17pt  0.48pt

    Every mover is a TWO-source row. All 210 rows with three or more sources
    are bit-for-bit unchanged, because the 3.0/1.5/1.5 and capped shapes do not
    land on half exactly — so this cannot disturb the blends #1999's answered
    question showed are held by a different mechanism.

    WHAT THIS GIVES UP, SAID PLAINLY. Below the divergence threshold the hero
    may now be a number no single source stated. That is a real change: until
    now tier 1 always rendered some source's own figure. It is the right trade
    only because the alternative is not "a source's figure" but "the lower of
    two sources' figures, chosen by a comparison operator" — and because the
    invariant that a rendered probability is one a source actually stated is
    the DIVERGENCE GATE's (`utils/source_divergence.py`), scoped to pairs 40+
    points apart, which return before ever reaching this function. Inside the
    threshold the module's stated job is a blend, and the midpoint of two
    venues that agree to within a point is the blend working.

    The tie test is exact equality ON PURPOSE — no epsilon. A real tie is
    produced by IDENTICAL weights, which are bit-identical floats, so exact
    equality catches it every time; an epsilon would instead invent ties out of
    near-misses, and averaging a near-miss moves the number by up to half the
    spread when the correct answer was one endpoint. A false tie is expensive,
    a missed one merely leaves today's behaviour, so the test that cannot
    false-positive is the right one.
    """
    if not values:
        raise ValueError("Cannot compute weighted median of empty list")
    if len(values) == 1:
        return values[0]

    # Sort by value
    paired = sorted(zip(values, weights), key=lambda x: x[0])
    total_weight = sum(w for _, w in paired)
    if total_weight <= 0:
        # All weights are zero, fall back to simple median
        vals = [v for v, _ in paired]
        mid = len(vals) // 2
        return vals[mid]

    half = total_weight / 2.0
    cumulative = 0.0
    for index, (value, weight) in enumerate(paired):
        cumulative += weight
        if cumulative > half:
            return value
        if cumulative == half:
            # The optimal interval is [value, the next value that carries any
            # weight]. Zero-weight entries in between are not endpoints of it:
            # they cost nothing to move across, so averaging against one would
            # report a narrower ambiguity than the data actually has.
            #
            # The `value` default is unreachable rather than defensive, and is
            # written as a default instead of a branch so that no dead arm sits
            # here inviting a test that cannot reach it. Proof: if nothing after
            # `index` carries weight then `cumulative == total_weight`, so
            # `total_weight == total_weight / 2`, so `total_weight == 0` — which
            # returned above. It degenerates to `value` either way.
            next_value = next((v for v, w in paired[index + 1 :] if w > 0), value)
            return (value + next_value) / 2.0

    # Shouldn't reach here, but return last value as fallback
    return paired[-1][0]


def compute_aggregated_probability(
    sources: dict[str, list[TimestampedProb]],
    bucket_seconds: int = 30,
    custom_weights: Optional[dict[str, float]] = None,
    pregame_until: Optional[datetime] = None,
) -> list[TimestampedProb]:
    """
    Aggregate multiple probability sources into a single time series.

    ── #4976: RELATIVE DECAY IS AN IN-PLAY RULE HERE TOO (#1999) ────────────

    Buckets that end at or before ``pregame_until`` (see `pregame_boundary`) do
    not decay: every source that has spoken keeps its base weight, exactly as
    the hero has refused to decay a ``scheduled`` event since #1999. #6461 put
    this series on the hero's recency RULE but not on the hero's GATE, so
    before kickoff the sportsbook consensus — repriced a few times a day —
    still left the pool 40 minutes after each write and rejoined on the next,
    and a two-source weighted median is whichever source is heavier.
    Specimen, St Gallen v Sion 15305934, production payload 2026-09-17: both
    inputs flat (betting 0.562-0.608, polymarket 0.440-0.460) and the served
    pre-match line crossed the gap 45 times. ``None`` keeps every bucket on the
    in-play rule, bit-for-bit the previous behaviour.

    WHAT THE 45 ACTUALLY MEASURES, AND IT IS NOT ALL CADENCE (authority review,
    #4976). The oscillation's AMPLITUDE is the gap between the two sources, so
    the count of 5pp steps is the cadence defect multiplied by the disagreement.
    On that specimen the disagreement is #1011's question-meaning bug — stored
    sportsbook rows are home-win GIVEN NO DRAW (~0.59) against Polymarket's
    unconditional ~0.45 — and on a semantically compatible pair the same defect,
    through this same code, produces no 5pp steps at all:

        pair (flat inputs, identical cadence mismatch)   before -> after
        two-way vs three-way, 14pp apart      3 steps >=5pp, TV 0.42  ->  0, 0.0
        compatible venues, 4.0pp apart        0 steps >=5pp, TV 0.12  ->  0, 0.0
        compatible venues, 1.5pp apart        0 steps >=5pp, TV 0.045 ->  0, 0.0

    So this gate is worth a flat line rather than a 1-4 point wobble on a
    healthy fixture, and the headline number belongs to #1011/#5493. Neither of
    those closes on this change: a steady 0.59 is the same two-way number the
    hero shows, drawn without a jump. Legible is not truthful.

    AND IT DOES NOT STOP THE CHART DRAWING A VALUE NO VENUE STATED. #5425's tie
    rule averages the straddling pair on an EXACT cumulative-weight tie, and its
    own docstring notes that #1999 "made that shape common by switching the
    pre-game decay off". Doing the same here has the same effect: two venues at
    EQUAL base weight (kalshi 0.8 / polymarket 0.8) tie in every pre-game bucket
    once the decay stops differentiating them. Measured, 45 pre-game buckets,
    0.62 against 0.56:

        before   21 of 45 buckets draw the unstated midpoint, oscillating (TV 0.57)
        after    45 of 45 draw it, flat (TV 0.0)

    That is #5425 working as ruled, not fabrication — but "no value is invented"
    is a property of an UNEQUAL-weight pair (3.0 vs 0.8 cannot tie), not of this
    function, and must not be asserted of it in general.

    For each time bucket:
    1. Find the latest reading from each source (carried forward)
    2. Decay each reading's weight by how far it is behind the FRESHEST reading
       in the same bucket — relative age, never the wall clock
    3. Compute weighted median across all active sources

    No smoothing is applied (standing ruling #4) — each bucket is the honest
    weighted median of what the sources actually said in that bucket.

    ── #6461: THE DENOMINATOR USED TO CHANGE EVERY MINUTE ────────────────────

    Specimen: Red Sox @ Orioles, event 15305465, ``/api/events/15305465/history``.
    The blend line zigzagged; **29** of its 261 points moved 5+ points from the
    one before, and the worst pair moved **42.6 points in 120 seconds** —
    18:05 0.572 -> 18:07 0.146 — on a game where every individual source's own
    series was smooth. Nothing in the market had moved that far.

    The cause was this step 2, which aged each reading against the BUCKET's own
    clock: full weight for 2 minutes, linear decay, gone at 5. Measured cadences
    on that game: espn 185 s median between observations, mlb 240 s, stat_model
    282 s, betting 240 s median but a p90 of 1500 s. So every bucket weighted the
    same four sources differently from the last one purely because of when each
    poller happens to run, and betting — the heaviest source — dropped out of the
    pool entirely between writes and rejoined on the next one. A weighted median
    returns one contributor's actual value, so as the weights breathed the
    crossing point walked from "what ESPN thinks" to "what the sportsbooks and
    the stat model think", once a minute, across a 40-point disagreement.

    #6461 reported this as a membership effect. Membership is the extreme case,
    not the whole of it: replaying the served payload, only 9 of the 29 jumps
    change the eligible-source set and the other 20 happen with the set
    unchanged. Weight churn is the defect; a source hitting zero is weight churn
    that went all the way.

    THE RULE IS ALREADY RULED. #1829 settled this same question for the hero and
    the argument transfers verbatim: *uniform age is cadence, not staleness; only
    disagreement in age is staleness.* Each reading is therefore aged against the
    freshest observation in its own bucket. A source polling every four minutes
    alongside one polling every three is 60 seconds behind, not "stale", and
    keeps full weight; every source within ``HERO_RELATIVE_GRACE_SECONDS`` of the
    freshest carries its base weight, so on a healthy event the weights are
    CONSTANT across buckets and the line moves only when a source's VALUE moves.
    It also puts the chart on the same recency policy as the hero it has to agree
    with (standing ruling #1, card == hero == chart) — the T1 blending review
    named "same algorithm name, different answers" as its own finding.

    Measured on the specimen, whole game, nothing else changed: jumps >=5pp
    29 -> **3**, total variation 3.997 -> 1.643, endpoints unmoved (0.450 first,
    0.000 last). The three survivors are real and are the point of the exercise:
    17:56->17:58 is the 1-0 home run (score at 17:55:43; betting .460->.581, mlb
    .510->.632, stat_model .363->.499 all move together), 18:05->18:07 is the
    away two-run inning at 18:07:41 — where the repaired line goes straight to
    the real .264 instead of overshooting to .146 and bouncing back — and
    19:13->19:15 is genuine betting drift .253->.188. A real move still lands in
    full, in one bucket. Nothing is smoothed, averaged, delayed or invented.

    NO INDEFINITE CARRY-FORWARD, which is the reason this does not simply call
    the hero's helper on its default. The hero floors a lapsed arm at
    ``HERO_MIN_STALENESS_MULTIPLIER`` because it renders one instant; a floor on
    an unbounded time axis would carry a source that went dark in the first
    inning through every remaining bucket of the game. The series passes
    ``floor=0.0``: a source that falls ``HERO_RELATIVE_GRACE_SECONDS +
    HERO_RELATIVE_DECAY_SECONDS`` (40 min) behind its peers leaves the pool and
    its trace ends. Sources that ALL stop together are not penalised and cannot
    be — no more observations means no more buckets.

    The hazard ``_relative_staleness_multiplier`` warns about (a source that is
    dead but still transmitting re-stamps itself fresh and decays the honest
    sources against it) is inherited, and it is strictly rarer here than what it
    replaces: a transmitting-but-dead source already kept full weight under
    absolute age. This change only ever decays a source that is behind a peer
    that IS still observing, so it adds no new way for a liar to win.

    Args:
        sources: Dict mapping source key → list of timestamped probabilities
        bucket_seconds: Time bucket size in seconds (default 30s)
        custom_weights: Override default source weights

    Returns:
        Aggregated time series of probabilities
    """
    weights = custom_weights or SOURCE_WEIGHTS

    if not sources:
        return []

    # Collect all timestamps across all sources to define bucket boundaries
    all_timestamps: set[float] = set()
    for source_points in sources.values():
        for point in source_points:
            ts = point.timestamp.timestamp()
            bucket_key = int(ts // bucket_seconds) * bucket_seconds
            all_timestamps.add(bucket_key)

    if not all_timestamps:
        return []

    sorted_buckets = sorted(all_timestamps)

    # ── ONE PASS PER SOURCE, NOT ONE PER BUCKET (#6546) ──────────────────────
    #
    # The carry-forward search used to restart at each source's first point for
    # every bucket — O(buckets x points) — and recomputed
    # ``point.timestamp.timestamp()`` on every visit. On a finished NFL game
    # with four months of pre-match market history (3,009 Kalshi + 2,405
    # Polymarket points over 4,607 one-minute buckets) that is ~14 million
    # datetime conversions, measured at 1.18 s on a laptop and ~4 s of app time
    # on the dyno — for a chart the reader watches spin.
    #
    # The buckets are ascending and each source's points are sorted, so the
    # answer for bucket N+1 can only be at or after the answer for bucket N: a
    # cursor per source turns the whole scan into O(points + buckets). Epochs
    # are computed ONCE per point, which is the other half of the cost.
    #
    # This is a pure speed change and the equivalence is tested rather than
    # asserted: ``test_event_history_aggregation_is_linear_6546.py`` runs the
    # previous implementation, kept verbatim as an oracle, against this one on
    # randomised multi-source series and requires identical output.
    source_scan: dict[str, tuple[list[float], list[TimestampedProb]]] = {}
    for source_key, points in sources.items():
        ordered = sorted(points, key=lambda p: p.timestamp)
        source_scan[source_key] = (
            [p.timestamp.timestamp() for p in ordered],
            ordered,
        )
    cursors: dict[str, int] = {source_key: 0 for source_key in source_scan}

    # The bucket's timezone came from the first non-empty source, re-derived
    # inside the bucket loop. It cannot change between buckets, and there is
    # always such a source here: an all-empty `sources` produced no timestamps
    # and returned above.
    bucket_tz = None
    for pts in sources.values():
        if pts:
            bucket_tz = pts[0].timestamp.tzinfo
            break

    pregame_epoch = pregame_until.timestamp() if pregame_until is not None else None

    # For each bucket, find latest reading per source
    aggregated: list[TimestampedProb] = []

    for bucket_ts in sorted_buckets:
        bucket_time = datetime.fromtimestamp(bucket_ts, tz=bucket_tz)

        readings: list[SourceReading] = []
        limit = bucket_ts + bucket_seconds
        # #4976/#1999: a bucket wholly before kickoff is pre-game. `<=` so the
        # bucket that CONTAINS kickoff already runs the in-play rule.
        bucket_is_pregame = pregame_epoch is not None and limit <= pregame_epoch

        # Pass 1: what each source is saying in this bucket, and WHEN it said
        # it. No weighting yet — the reference the weights are measured against
        # is not known until every candidate has been collected.
        candidates: list[tuple[str, TimestampedProb, float]] = []

        for source_key, (epochs, ordered) in source_scan.items():
            # Find latest reading at or before this bucket. The cursor only
            # ever moves forward, so across all buckets each point is visited
            # once.
            index = cursors[source_key]
            while index < len(epochs) and epochs[index] <= limit:
                index += 1
            cursors[source_key] = index

            if index == 0:
                continue
            candidates.append((source_key, ordered[index - 1], epochs[index - 1]))

        if not candidates:
            continue

        # The reference is the freshest OBSERVATION in this bucket, not the
        # bucket's clock — #6461, under #1829's rule. `final_result` neither
        # sets it nor is aged by it, exactly as the hero excludes the uncapped
        # sources from its decay stamps: a graded outcome is not a forecast that
        # can fall behind, and letting it set the reference would age every live
        # source against a result.
        decay_epochs = [
            epoch
            for source_key, _point, epoch in candidates
            if source_key not in _UNCAPPED_SOURCES
        ]
        reference_epoch = max(decay_epochs) if decay_epochs else None

        # Pass 2: weight each candidate by how far behind that reference it is.
        for source_key, latest, latest_epoch in candidates:
            base_weight = weights.get(
                source_key, 0.5
            )  # Default weight for unknown sources

            if (
                reference_epoch is None
                or source_key in _UNCAPPED_SOURCES
                or bucket_is_pregame
            ):
                relative_age = 0.0
            else:
                # Cannot go negative, so there is no clamp to write: every
                # decayed source's own epoch is one of the values
                # `reference_epoch` was the max OF, and the sources excluded
                # from that max take the branch above. A clamp here would be an
                # arm no test could reach.
                relative_age = reference_epoch - latest_epoch

            # Decay to ZERO, not to the hero's floor — see the docstring: this
            # axis is unbounded, so a lapsed source must be able to leave.
            stale_mult = _relative_staleness_multiplier(relative_age, floor=0.0)
            effective_weight = base_weight * stale_mult

            # A source decayed to zero is excluded rather than admitted at zero
            # weight. Mutation-tested and it is REDUNDANT, which is worth the
            # line so nobody removes the wrong one of the two: deleting this
            # gate changes no output, because `cap_weight_shares` counts only
            # POSITIVE weights before deciding whether the #1829 share cap
            # applies, and `_weighted_median` can never return a zero-weight
            # entry (the cumulative sum does not advance at one, and the tie
            # branch skips them when choosing the interval's far end). Both
            # defences are deliberate; the one that is load-bearing is
            # `cap_weight_shares`'. Without it, a weightless arm would be enough
            # to make a two-source event look like three, switch the cap on, and
            # hand the median to the lighter source — #5542's "a dead arm
            # decides by position" with the weight taken all the way to zero.
            if effective_weight > 0:
                readings.append(
                    SourceReading(
                        source=source_key,
                        probability=latest.home_probability,
                        weight=effective_weight,
                        # The age the weight was actually derived from, so this
                        # record cannot disagree with the number beside it.
                        stale_seconds=relative_age,
                    )
                )

        if not readings:
            continue

        # Compute weighted median. The #1829 share cap applies HERE TOO, and
        # that is deliberate: the hero and this series answer the same question,
        # so a cap on one and not the other is exactly the two-verdicts-for-one-
        # rule shape that produced the 87-13-header-vs-~0-chart contradiction in
        # the first place. Since #6461 this path runs the relative rule as well,
        # so the two surfaces now share BOTH halves of #1829 rather than one
        # each — same question, same recency policy, same cap.
        values = [r.probability for r in readings]
        wts = cap_weight_shares(
            [r.weight for r in readings],
            exempt=[r.source in _UNCAPPED_SOURCES for r in readings],
        )
        raw_aggregate = _weighted_median(values, wts)

        # No smoothing (ruling #4): emit the bucket's honest weighted median.
        aggregated.append(
            TimestampedProb(
                timestamp=bucket_time,
                home_probability=round(raw_aggregate, 6),
            )
        )

    return aggregated


def compute_current_aggregate(
    source_readings: dict[str, tuple[float, datetime]],
    now: datetime,
    custom_weights: Optional[dict[str, float]] = None,
) -> Optional[float]:
    """
    Compute a single aggregate probability from current source readings.

    Simpler version of the full time-series aggregation, for use in
    real-time event serialization.

    Args:
        source_readings: Dict mapping source key → (probability, last_updated)
        now: Current time
        custom_weights: Override default source weights

    Returns:
        Aggregated probability (0-1) or None if no valid readings
    """
    weights = custom_weights or SOURCE_WEIGHTS

    values: list[float] = []
    wts: list[float] = []
    keys: list[str] = []

    for source_key, (probability, updated_at) in source_readings.items():
        base_weight = weights.get(source_key, 0.5)
        stale_seconds = (now - updated_at).total_seconds()

        stale_mult = _staleness_weight(max(0, stale_seconds))
        effective_weight = base_weight * stale_mult

        if effective_weight > 0:
            values.append(probability)
            wts.append(effective_weight)
            keys.append(source_key)

    if not values:
        return None

    # Same #1829 share cap as the other two blend paths — one rule, one verdict.
    wts = cap_weight_shares(wts, exempt=[k in _UNCAPPED_SOURCES for k in keys])
    return round(_weighted_median(values, wts), 6)


_EXCLUDE_WHEN_COMPLETED = {"kalshi", "polymarket"}


def _tier1_readings(
    event, event_status: Optional[str] = None
) -> tuple[dict[str, float], dict[str, datetime]]:
    """The ``win_probability_sources`` entries tier 1 will actually use.

    ``(values_by_source, stamps_by_source)``. A source with no parseable value is
    absent from both; a source with a value but no ``updated_at`` is in the first
    and not the second.

    Split out so that ``newest_source_reading_time`` answers "when was the hero's
    number observed?" over exactly the entries ``effective_source_weights`` feeds
    the hero, and not a second, drifting reading of the same column — the hazard
    that function's own docstring names.

    CU-4 (#5311): this is also where the read-side eligibility gate belongs, for
    that same reason. It is the ONE place that decides which stored readings
    reach the hero, the chart edge, the divergence gate and the Discover card, so
    a refusal applied here cannot be applied inconsistently across surfaces — and
    a refusal applied anywhere else would be the second opinion this function was
    extracted to prevent. See `probability_eligibility.is_refused` for why the
    gate is narrow (positive refusals only) on today's record-free population.
    """
    status = event_status or getattr(event, "status", None)
    is_finished = status in ("completed", "closed")

    wps = getattr(event, "win_probability_sources", None) or {}
    prob_readings: dict[str, float] = {}
    stamps: dict[str, datetime] = {}
    for k, v in wps.items():
        if k not in SOURCE_WEIGHTS:
            continue
        if is_finished and k in _EXCLUDE_WHEN_COMPLETED:
            continue
        if is_refused(v):
            continue
        value, updated_at = parse_source_entry(v)
        if value is None:
            continue
        prob_readings[k] = value
        if updated_at is not None:
            stamps[k] = updated_at
    return prob_readings, stamps


def newest_source_reading_time(
    event, event_status: Optional[str] = None
) -> Optional[datetime]:
    """When the freshest source behind this event's hero was observed (#3898).

    ``None`` means "cannot say", never "old": the event has no tier-1 readings at
    all, or none of the ones it has carries an ``updated_at``. Both the bare-float
    legacy shape and an unparseable stamp land here (``parse_source_entry`` /
    ``_coerce_timestamp``), so a caller may only ever use this to EARN an action,
    never to justify one by its absence.

    Tier 1 only, deliberately. ``compute_aggregate_probability`` falls through to
    ESPN and then to the opening line, and neither of those carries a time — so a
    hero resting on a fallback tier honestly has no observation time, and saying
    so is the whole point.
    """
    _, stamps = _tier1_readings(event, event_status)
    return max(stamps.values()) if stamps else None


def effective_source_weights(
    event, event_status: Optional[str] = None
) -> tuple[list[str], list[float], list[float]]:
    """The readings and the weights the hero is ABOUT to use — decayed and capped.

    Extracted so the divergence gate and the flag that reports it read the same
    numbers the value is computed from. A detector that recomputes its own
    weights is a detector that can disagree with the thing it is watching.

    Returns ``(keys, values, weights)``, index-aligned; ``([], [], [])`` when
    tier 1 has nothing.

    Thin delegate to :func:`effective_source_weights_detailed`, which also reports
    WHICH arms decayed all the way to the floor. The three-tuple shape is kept
    because a dozen call sites unpack it; only the divergence gate needs the
    fourth value, and it asks for it by name.
    """
    keys, values, weights, _floored = effective_source_weights_detailed(
        event, event_status
    )
    return keys, values, weights


def effective_source_weights_detailed(
    event, event_status: Optional[str] = None
) -> tuple[list[str], list[float], list[float], set[str]]:
    """``effective_source_weights`` plus the set of arms that hit the decay FLOOR.

    🔴 **The fourth value is the divergence gate's population filter (#5542).** An
    arm at ``HERO_MIN_STALENESS_MULTIPLIER`` has been told by our own recency rule
    that it is no longer describing this game. It must not be counted as one of
    the "sources this event rests on" when deciding whether a two-source pair is
    diverging — otherwise a dead arm switches the protection off *and* keeps
    enough post-cap mass to decide which live source is the median.

    It is computed HERE rather than by a second pass over the stamps because the
    decay lives here: a caller that re-derived "is this arm dead?" from the
    timestamps would be a detector that can disagree with the weights it gates,
    which is the exact failure this module's docstring warns about.

    "Floored" means the multiplier reached the floor, NOT merely that the weight
    is small — a source with a low BASE weight is not stale, it is just lightly
    trusted, and it keeps its vote.
    """
    prob_readings, stamps = _tier1_readings(event, event_status)

    if not prob_readings:
        return [], [], [], set()

    values = list(prob_readings.values())
    keys = list(prob_readings.keys())
    weights = [SOURCE_WEIGHTS.get(src, 0.5) for src in keys]
    floored: set[str] = set()

    # Relative recency. The reference is the freshest stamp on the event,
    # never the wall clock: uniform age is cadence, not staleness, and a
    # clock-free rule cannot drift (gotcha #44).
    #
    # ...and it is an IN-PLAY rule (#1999). Before the game starts the sources
    # are not watching one moving truth, so their age disagreement is the
    # cadence difference between two pollers rather than one of them falling
    # behind. `_relative_decay_applies` carries the measurement.
    decay_stamps = {k: t for k, t in stamps.items() if k not in _UNCAPPED_SOURCES}
    if decay_stamps and _relative_decay_applies(
        event_status or getattr(event, "status", None)
    ):
        freshest = max(decay_stamps.values())
        for i, src in enumerate(keys):
            stamp = decay_stamps.get(src)
            if stamp is None:
                continue  # unstamped keeps full weight — the monotone default
            relative_age = (freshest - stamp).total_seconds()
            if relative_age <= 0:
                continue
            multiplier = _relative_staleness_multiplier(relative_age)
            weights[i] *= multiplier
            if multiplier <= HERO_MIN_STALENESS_MULTIPLIER:
                floored.add(src)

    weights = cap_weight_shares(
        weights, exempt=[src in _UNCAPPED_SOURCES for src in keys]
    )
    return keys, values, weights, floored


def assess_event_divergence(
    event, event_status: Optional[str] = None
) -> Optional[SourceDivergence]:
    """The flag half of the divergence gate (ruling (b)) — read-only.

    Returns a verdict when this event's hero rests on exactly two sources that
    disagree past `DIVERGENCE_SPREAD_THRESHOLD`. This is the hook a sentinel or
    an audit reads to route the pair to matching as a suspected mis-link; the
    aggregator itself only needs the value.

    On the live population read 2026-08-19 this fires on 4 of 76 two-source
    events; three of the four are one class (Polymarket at 0.07 against a
    sportsbook at 0.59-0.63).

    #5542: arms at the decay floor are excluded from the gate's POPULATION — see
    `_gate_population`.
    """
    keys, values, weights, floored = effective_source_weights_detailed(
        event, event_status
    )
    if not keys:
        return None
    return assess_divergence(*_gate_population(keys, values, weights, floored))


def _gate_population(
    keys: list[str],
    values: list[float],
    weights: list[float],
    floored: set[str],
) -> tuple[dict[str, float], dict[str, float]]:
    """The readings the divergence gate governs: the arms still SPEAKING (#5542).

    🔴 **A dead arm is not an opinion, but it used to count as a source.** The gate
    governs events resting on exactly two sources; a third reading took the event
    out of its population entirely, so the protection switched off exactly as the
    disagreement got worse. Event 15304937 (live 07:07Z 2026-09-12): `mlb` 0.356
    at 131 min behind, `kalshi` 0.99, `polymarket` 0.455 — 63 points apart, gate
    silent, hero 0.455, the losing side of a game the home team had won 6-5.

    Floored arms are dropped from the POPULATION ONLY. They keep their weight in
    the blend, so this narrows *when the gate fires*, never what the median is
    made of — "we stopped hearing from Kalshi" still is not "Kalshi does not
    exist".

    🔴 **This deliberately does NOT widen the gate to the widest pair among N.**
    On a healthy triple (betting 0.10 / kalshi 0.52 / polymarket 0.55) the widest
    pair is 0.450, past the threshold, and the capped median correctly returns
    0.52 — the value the two agreeing sources support. A widest-pair gate would
    render one source alone and discard that agreement. Rejected on that specimen;
    see the SCOPE section of ``utils/source_divergence.py``.

    🔴 **THE FILTER NEVER TAKES THE POPULATION BELOW TWO, and that floor is the
    whole anti-#240 property.** A TWO-source event whose sportsbook is frozen at
    its stale pregame 65% against a live market at 5% is the case this gate was
    BUILT for — the stale arm is floored there too, and dropping it would leave
    one reading, no pair, and no gate, resurrecting exactly the 57%-hero vs
    20%-chart contradiction the module exists to prevent. So floored arms are
    dropped only while two live arms remain; otherwise every arm is governed, as
    before. (`test_the_gate_does_not_print_a_stale_pregame_line_over_a_live_one`
    is the guard that caught this, and it is why the floor is written down here
    rather than discovered again.)

    The resulting behaviour table — only the third row moves:

        2 arms, 0 floored      -> both governed          (unchanged)
        2 arms, 1 floored      -> both governed          (unchanged; anti-#240)
        3 arms, 1 floored      -> the 2 live governed    (#5542, THE FIX)
        3 arms, 2 floored      -> all 3 governed => no gate (unchanged)
        3 arms, 0 floored      -> all 3 governed => no gate (unchanged)
    """
    live = [(k, v, w) for k, v, w in zip(keys, values, weights) if k not in floored]
    if len(live) < 2:
        live = list(zip(keys, values, weights))
    return (
        {k: v for k, v, _ in live},
        {k: w for k, _, w in live},
    )


#: The three tiers ``compute_aggregate_probability_tiered`` can answer from, in
#: the order it tries them. The names are a caller-visible vocabulary, not a
#: debug string: ``TIER_OPENING`` is the one that says "this number is not a
#: blend of anything — it is the line as it was posted, and nobody has quoted it
#: since". See ``compute_aggregate_probability_tiered`` for why that is worth a
#: return value.
TIER_SOURCES = "sources"
TIER_ESPN = "espn"
TIER_OPENING = "opening"


def compute_aggregate_probability(
    event, event_status: Optional[str] = None
) -> Optional[float]:
    """Compute aggregate home win probability from all available sources.

    A thin wrapper over ``compute_aggregate_probability_tiered`` that drops the
    tier. Every existing caller reads only the number and is unchanged by the
    split — the value this returns is computed by exactly the same code that
    produced it before, because it IS that code.
    """
    return compute_aggregate_probability_tiered(event, event_status)[0]


def compute_aggregate_probability_tiered(
    event, event_status: Optional[str] = None
) -> tuple[Optional[float], Optional[str]]:
    """``(probability, tier)`` — the number AND which tier answered.

    WHY THE TIER IS A RETURN VALUE (#6694). The three tiers are not three ways
    of computing one thing; they are three different CLAIMS, and only the first
    is a blend. Tier 3 returns ``opening_home_probability`` — a record of where
    the line opened, which is a perfectly good last resort and a very bad thing
    to describe as a live consensus.

    Because the number alone cannot say which tier produced it, every caller
    that wanted to distinguish them had to re-derive the ordering from the same
    attributes this function reads — and the one caller that needed it most
    (``resolve_hero``) instead had a whole arm rendered unreachable by it: its
    ``opening`` arm sits BELOW a blend arm that Tier 3 already answers, so on
    2026-09-19 all 486 opening-only events in a two-day window were served as
    ``hero_probability_source: "blend"``, one of them (15314578, live) printing
    64% captioned as a live blend over a chart drawing 78%.

    The fix is not to copy the cascade into the caller. It is for the cascade to
    say what it did. Returning the tier keeps ONE implementation of the ordering
    and makes "was this actually a blend?" answerable without asking the
    attributes a second time and hoping the two walks agree.

    Uses SOURCE_WEIGHTS to produce a weighted average of all available
    probability readings on the event model.  Falls back through three
    tiers of decreasing richness.

    When event_status is "completed" or "closed", prediction market sources
    (Kalshi, Polymarket) are excluded — their prices go stale post-final
    and drag the aggregate away from the resolved sportsbook/ESPN values.

    Works on any object with win_probability_sources, espn_win_prob_home,
    and opening_home_probability attributes (typically an Event model).
    """
    # Tier 1: win_probability_sources JSONB (live games — multiple sources).
    # Readings, decay and cap all live in `effective_source_weights` so the
    # divergence gate below cannot drift from the value it is gating.
    keys, values, weights, floored = effective_source_weights_detailed(
        event, event_status
    )

    if keys:
        # Weighted MEDIAN (not mean) — the same outlier-resistant method the
        # time-series blend (compute_aggregated_probability → the chart's
        # aggregate_line) uses. This is the module's stated design (see the
        # docstring): a single stale/lagged source cannot drag the aggregate.
        #
        # A weighted MEAN here let a stale sportsbook "betting" reading (weight
        # 3.0) that had not caught up to the live game state pull the hero toward
        # the pre-game number (~57%) while the chart's median-based blend line
        # read the live value (~20%) on the same screen — the 57%-hero vs
        # 20%-chart contradiction (#240 Item 1). Using the median here makes the
        # point-in-time hero match the chart's blend line: one number per
        # question.
        #
        # #1829 adds the two halves the median was always missing: RECENCY
        # DECAY (a source aged against the freshest stamped source on this same
        # event) and a SHARE CAP (no single source may straddle the midpoint by
        # itself). See the constants block for the specimen and the reasoning.
        # Both are no-ops on the shapes that dominate today — an event with no
        # stamps decays nothing, an event with fewer than three sources caps
        # nothing — so this is additive to a hero, not a replacement for one.
        #
        # THE DIVERGENCE GATE (ruling (b), cycle 99). Two sources 40+ points
        # apart cannot both be describing this game, so we render one source's
        # own number rather than let a statistic arbitrate a broken pair. See
        # `utils/source_divergence.py` for the measured threshold and for why
        # "primary" is the highest EFFECTIVE weight — a base-weight primary
        # would print the stale pregame line over a live blowout, which is #240
        # rebuilt. On the 2026-08-19 population this changes 0 of 76 displayed
        # heroes and flags 4; the value it protects is the invariant that a
        # rendered probability is always a number some source actually stated.
        # #5542: the gate's population is the arms still SPEAKING — a third arm
        # decayed to the floor no longer switches the protection off. The BLEND
        # below is unchanged and still weighs every source.
        divergence = assess_divergence(
            *_gate_population(keys, values, weights, floored)
        )
        if divergence is not None:
            return round(divergence.primary_value, 6), TIER_SOURCES

        if any(w > 0 for w in weights):
            return round(_weighted_median(values, weights), 6), TIER_SOURCES

    # Tier 2: ESPN win probability (live games, single source)
    espn_prob = getattr(event, "espn_win_prob_home", None)
    if espn_prob is not None:
        return round(float(espn_prob), 6), TIER_ESPN

    # Tier 3: Opening probability (Odds API sportsbook consensus)
    opening_prob = getattr(event, "opening_home_probability", None)
    if opening_prob is not None:
        return round(float(opening_prob), 6), TIER_OPENING

    return None, None
