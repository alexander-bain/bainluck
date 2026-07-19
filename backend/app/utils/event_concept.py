"""Generic Event Concept framework — slice 1 (#999).

An "event concept" is a real-world competition (golf tournament, tennis slam,
UFC card, F1 GP, awards ceremony) that owns a set of markets across sources. This
module is the DOMAIN-PARAMETERIZED core: a small adapter interface + registry +
event-key parsing. Each domain provides an adapter that returns the SAME generic
envelope, so `/api/event/{key}` + the `/event/[key]` page render any domain.

Slice 1 ships the GOLF adapter, which delegates to the existing, proven
`routes/golf.py` tournament-detail aggregation (golf.py stays untouched — the
parity bar) and maps its output into the generic envelope. Tennis / UFC / F1 /
awards adapters (design §5, §6) are future slices: each implements
`build_event()` to produce the same envelope shape documented below.

Envelope shape (domain-agnostic — every adapter returns this):
    {
      "event":   {key, domain, name, status, start_date, end_date, venue,
                  location, is_major},
      "primary": {kind, label, competitors, evolution_market_id}
                 # kind flexes: "winner_field" (golf/tennis/F1-championship —
                 # a leaderboard/field) | "co_equal_list" (UFC card, awards
                 # categories — no single overall winner). Design §3.4 / §5 / §6.
      "sections": [...]   # market groups (winner / top-N / props), ordered
      "children": [...]   # matchup / prop / progression child markets
      "movers":   [...]   # biggest 24h movers within the event
    }

ELIMINATION FROM STRUCTURE (#210 — Alex's ruling; the bracketed-Container contract):
    A `winner_field` competitor in a BRACKETED container (knockout / group→knockout
    tournament) carries an `eliminated` envelope:
        "eliminated": {"out": bool, "round": str | None}
    `out` is TRUE only from STRUCTURE — a settled knockout loss, or a group-stage
    non-advancer (played out, no upcoming game while the tournament continues).
    PRICE NEVER DECIDES: a 0% competitor pre-kickoff is a longshot, not eliminated.
    `round` records the round the competitor exited in ("Semifinal", "Group Stage",
    …), or null when not derivable. The soccer World Cup adapter is the reference
    implementation (`event_soccer.compute_nation_elimination` + build_event); other
    bracketed adapters (tennis/F1/UFC brackets) converge on this same shape as they
    gain settled-result structure. Frontend `isEliminatedCompetitor` accepts both
    this shape and a legacy boolean (pre-#210 cached envelopes).
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Protocol, runtime_checkable

from sqlalchemy.ext.asyncio import AsyncSession


def parse_event_key(key: str) -> tuple[str, str]:
    """Parse an event key into (domain, slug).

    Canonical form: ``event:<domain>:<slug>`` (e.g. ``event:golf:2026-masters``,
    ``event:tennis:wimbledon-2026``). Also tolerates ``<domain>:<slug>``. A bare
    slug is treated as golf (parity convenience for slice 1). The slug may itself
    contain hyphens; only the domain segment is split off.
    """
    parts = key.split(":")
    if len(parts) >= 3 and parts[0] == "event":
        return parts[1], ":".join(parts[2:])
    if len(parts) == 2:
        return parts[0], parts[1]
    return "golf", key


@runtime_checkable
class EventConceptAdapter(Protocol):
    """A per-domain adapter. Implement `domain` + `build_event`.

    `build_event(slug, db)` returns the generic envelope (see module docstring)
    for the event, or None if the event doesn't exist. Future domains (tennis,
    ufc, f1, awards) add an adapter and register it — no route/frontend change.
    """

    domain: str

    async def build_event(self, slug: str, db: AsyncSession) -> dict | None: ...


_ADAPTERS: dict[str, EventConceptAdapter] = {}


def register_adapter(adapter: EventConceptAdapter) -> None:
    _ADAPTERS[adapter.domain] = adapter


def get_adapter(domain: str) -> EventConceptAdapter | None:
    return _ADAPTERS.get(domain)


def registered_domains() -> list[str]:
    return sorted(_ADAPTERS.keys())


# Transactional-only fields that must NEVER ship on the concept-page wire.
# L2-48 thesis / L2-118: the blend is the product; American odds are a betting
# artifact we deliberately strip. Golf competitors pick `american_odds` up from
# routes/golf.py's shared tournament builder — harmless (nothing renders it) but
# dead weight and a latent leak risk if a future renderer naively maps
# competitor fields. Strip it at the envelope boundary so every adapter's
# competitor payload is clean, not just golf's.
_WIRE_LEAK_COMPETITOR_FIELDS = ("american_odds",)


def strip_competitor_wire_leaks(envelope: dict | None) -> dict | None:
    """Remove transactional-only fields from the concept-page competitor payload.

    Mutates `envelope["primary"]["competitors"]` in place (each is a fresh
    per-request dict) and returns the envelope for chaining. No-op when there is
    no competitor list.
    """
    if not envelope:
        return envelope
    competitors = (envelope.get("primary") or {}).get("competitors") or []
    for competitor in competitors:
        if isinstance(competitor, dict):
            for field in _WIRE_LEAK_COMPETITOR_FIELDS:
                competitor.pop(field, None)
    return envelope


# ---------------------------------------------------------------------------
# Golf adapter — the reference implementation (delegates to routes/golf.py).
# ---------------------------------------------------------------------------

def _golf_status(tournament: dict, now: datetime | None = None) -> str:
    """Normalize golf's schedule_status into upcoming/live/settled.

    L2-66: DataGolf's schedule reports "in-progress" (HYPHEN) while this only
    matched "in_progress" (underscore) — so a live tournament never flipped the
    event page into LIVE mode. Normalize hyphens→underscores so both forms work.

    L2-124 (#202): fall back to the schedule DATES when schedule_status is absent
    or non-terminal. Without this, a finished tournament whose status never
    flipped to "completed" (e.g. a past-dated BMW card) returns "upcoming" and
    leaks into the competition hub's UPCOMING rail — the hub lister classifies
    purely on this function, it does NOT run _filter_stale_tournaments. Fail-open:
    only a PARSEABLE, clearly-past date demotes to "settled"; a missing or
    unparseable date stays "upcoming" so a real card is never hidden by a bad date
    field. Grace windows mirror _filter_stale_tournaments (routes/golf.py). We do
    NOT trust resolution_date here alone — it can carry a FUTURE Kalshi close-time
    artifact (gotcha #14); it is only consulted when no start/end date exists.
    """
    raw = (tournament.get("schedule_status") or "").lower().replace("-", "_")
    if raw in ("in_progress", "live", "active"):
        return "live"
    if raw in ("completed", "closed", "resolved", "final", "settled"):
        return "settled"

    now_date = (now or datetime.now(timezone.utc)).date()
    end_date = tournament.get("end_date")
    # Mirror the hub card's own start signal: `start_date or commence_time`. The
    # finished DP-World-Tour cards that leaked (BMW International Open, US Senior
    # Open) carry NO schedule start_date — their date lives in commence_time — so
    # a start_date-only check missed them and they fell through to a FUTURE Kalshi
    # resolution_date (gotcha #14) and stayed "upcoming". For an upcoming event a
    # Kalshi commence/close time is in the future, so it never false-settles.
    start_date = tournament.get("start_date") or tournament.get("commence_time")
    resolution_date = tournament.get("resolution_date")
    if end_date:
        try:
            if datetime.fromisoformat(end_date).date() < now_date - timedelta(days=1):
                return "settled"
        except (ValueError, TypeError):
            pass
    elif start_date:
        try:
            if datetime.fromisoformat(start_date).date() < now_date - timedelta(days=7):
                return "settled"
        except (ValueError, TypeError):
            pass
    elif resolution_date:
        try:
            if datetime.fromisoformat(resolution_date).date() < now_date - timedelta(days=7):
                return "settled"
        except (ValueError, TypeError):
            pass
    return "upcoming"


def _golf_leaderboard_has_live_rows(leaderboard: list[dict] | None) -> bool:
    """True if the stored leaderboard proves play is underway.

    #144: DataGolf's get-schedule `status` does NOT reliably flip to
    "in-progress" during play (it stayed absent through Scottish Open round 1),
    so `_golf_status` alone left live tournaments stuck at "upcoming". A stored
    leaderboard row carrying an in-play signal (a position, a thru value, or a
    round/total score) is authoritative proof of play. Requiring an in-play
    signal (not just a non-empty list) guards against a pre-tournament field
    dump being read as live.
    """
    for e in leaderboard or []:
        if (
            e.get("position")
            or e.get("thru")
            or e.get("total_score") is not None
            or e.get("today_score") is not None
        ):
            return True
    return False


def _golf_within_play_window(
    start_date: str | None,
    end_date: str | None,
    now: datetime,
) -> bool:
    """True if `now` falls within [start, end+1d] (1-day tail grace for tz skew).

    Returns False when either date is missing — the caller falls back to a
    leaderboard-freshness check so a missing schedule date never blocks live.
    """
    try:
        s = datetime.fromisoformat(start_date).date() if start_date else None
        e = datetime.fromisoformat(end_date).date() if end_date else None
    except (ValueError, TypeError):
        return False
    if s is None or e is None:
        return False
    return s <= now.date() <= (e + timedelta(days=1))


def _golf_leaderboard_is_fresh(
    updated_at: str | None,
    now: datetime,
    *,
    max_age_hours: float = 12.0,
) -> bool:
    """True if the leaderboard was updated within `max_age_hours` of `now`.

    Used only as the fallback live gate when schedule dates are missing, so a
    stale final leaderboard from a finished tournament is not read as live.
    """
    if not updated_at:
        return False
    try:
        ts = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
    except (ValueError, TypeError, AttributeError):
        return False
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return (now - ts).total_seconds() <= max_age_hours * 3600


def _norm_player_name(s: str | None) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def _ascii_player_name(s: str | None) -> str:
    """Diacritic-stripped normalized name ("Ludvig Åberg" -> "ludvig aberg").

    The concept-page competitor name (Kalshi/Polymarket display) and the
    evolution-market outcome name (raw DataGolf) frequently differ only by
    accents, so an exact ``_norm_player_name`` join silently drops the sparkline
    for those golfers. (#191)
    """
    import unicodedata

    norm = _norm_player_name(s)
    return "".join(
        ch for ch in unicodedata.normalize("NFKD", norm)
        if not unicodedata.combining(ch)
    )


_NAME_SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}


def _last_first_initial_key(s: str | None) -> str | None:
    """"lastname|f" key (diacritic-stripped) to bridge nickname/first-name
    variants like "Matthew Fitzpatrick" (DataGolf) vs "Matt Fitzpatrick"
    (Kalshi). Returns None for single-token names. Used only as an
    ambiguity-guarded last-resort join. (#191)
    """
    ascii_name = re.sub(r"[.'`]", "", _ascii_player_name(s))
    toks = [t for t in ascii_name.split() if t not in _NAME_SUFFIXES]
    if len(toks) < 2:
        return None
    return f"{toks[-1]}|{toks[0][0]}"


def fuse_golf_live(
    competitors: list[dict],
    leaderboard: list[dict] | None,
    updated_at: str | None,
) -> str | None:
    """Fuse the stored DataGolf live leaderboard (position / score-to-par / thru /
    round) into golf competitors, matched by name (dg_id isn't carried on the
    winner-field golfers). Mutates `competitors` in place; returns the `as_of`
    timestamp for the freshness chip. Competitors without a leaderboard match keep
    their probability-only shape (graceful — never fabricate a position/thru).

    Pure (no DB / no network) so it's unit-tested and safe on the request path;
    the caller reads the STORED leaderboard, never re-polling DataGolf. L2-66.
    """
    by_name = {
        _norm_player_name(e.get("name")): e
        for e in (leaderboard or [])
        if e.get("name")
    }
    for c in competitors:
        entry = by_name.get(_norm_player_name(c.get("name")))
        if not entry:
            continue
        c["position"] = entry.get("position")
        c["score_to_par"] = entry.get("total_score")
        c["today_score"] = entry.get("today_score")
        c["thru"] = entry.get("thru")
        c["current_round"] = entry.get("current_round")
    return updated_at


def golf_live_deltas(
    competitors: list[dict],
    baseline_by_name: dict[str, float],
) -> None:
    """Set `prob_delta_live` (win-probability POINTS moved) on each live golf
    competitor — the "who's charging" number that /api/golf/leaderboard shows
    (L2-69). `competitor.probability` (0–1) IS the DataGolf live win prob
    (verified: prob*100 == DataGolf win_prob), so the move vs the day's baseline
    is source-consistent. Baseline precedence: the day's start-of-day snapshot
    win% (rounds ≥2, passed in by name); else the pre-tournament
    `opening_probability` already on the competitor (round 1 ≈ pre-tournament,
    matching the leaderboard endpoint's round-1 branch). No baseline at all → no
    field set (never fabricate a delta). Pure; mutates in place.
    """
    for c in competitors:
        cur = c.get("probability")
        if not isinstance(cur, (int, float)):
            continue
        base = baseline_by_name.get(_norm_player_name(c.get("name")))
        if base is None:
            op = c.get("opening_probability")
            base = op * 100 if isinstance(op, (int, float)) else None
        if base is None:
            continue
        c["prob_delta_live"] = round(cur * 100 - base, 1)


def downsample_points(points: list, target: int = 25) -> list:
    """Stride-downsample a time-ordered list to at most `target` items, always
    keeping the first and last. Pure — unit-tested. Keeps sparklines/charts light
    (a live-major outcome can have 200–500 raw snapshots). L2-71."""
    n = len(points)
    if target < 2 or n <= target:
        return list(points)
    step = (n - 1) / (target - 1)
    idxs = sorted({round(i * step) for i in range(target)})
    return [points[i] for i in idxs]


async def attach_competitor_history(
    db,
    evolution_market_id,
    competitors: list[dict],
    *,
    hours: int = 168,
    top_n: int = 40,
    target_points: int = 25,
) -> None:
    """Attach a compact, downsampled probability series to the TOP-N competitors
    of a winner-field event (L2-71), so the leaderboard sparklines + the
    RaceToTitleChart draw from the envelope in one fetch (dropping two separate
    /api/futures/{id}/history client calls — this is net LESS DB work).

    Bounded on purpose: only the top-N competitors by current probability get a
    series (that's all the UI renders — leaderboard top ~20 + chart top ~10), and
    each series is downsampled to ~target_points, so a 156-golfer field never
    bloats the payload. Read-only, best-effort (never raises); competitors without
    snapshots are simply left without a series (no sparkline — never fabricated).

    Mutates matched competitors in place: sets `outcome_id` and
    `history: [{"timestamp", "probability"}]` (probability as a 0–1 float).
    """
    if not evolution_market_id or not competitors:
        return
    from datetime import datetime, timedelta, timezone
    from sqlalchemy import select
    from app.models import FuturesOutcome, FuturesOddsSnapshot

    # Top-N outcomes by current probability — the only ones the UI draws.
    out_rows = (
        await db.execute(
            select(
                FuturesOutcome.id,
                FuturesOutcome.name,
                FuturesOutcome.current_probability,
            )
            .where(FuturesOutcome.market_id == evolution_market_id)
            .order_by(FuturesOutcome.current_probability.desc().nulls_last())
            .limit(top_n)
        )
    ).all()
    if not out_rows:
        return
    id_to_name = {r[0]: r[1] for r in out_rows}
    outcome_ids = list(id_to_name.keys())

    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    snap_rows = (
        await db.execute(
            select(
                FuturesOddsSnapshot.outcome_id,
                FuturesOddsSnapshot.captured_at,
                FuturesOddsSnapshot.probability,
            )
            .where(
                FuturesOddsSnapshot.outcome_id.in_(outcome_ids),
                FuturesOddsSnapshot.captured_at >= cutoff,
            )
            .order_by(FuturesOddsSnapshot.outcome_id, FuturesOddsSnapshot.captured_at)
        )
    ).all()
    if not snap_rows:
        return

    # Group by outcome → consensus (mean across bookmakers) per captured_at.
    series_by_outcome: dict[int, list[tuple]] = {}
    cur_oid = None
    cur_ts = None
    cur_vals: list[float] = []
    ordered: list[tuple] = []

    def _flush():
        if cur_oid is not None and cur_ts is not None and cur_vals:
            ordered.append((cur_ts, sum(cur_vals) / len(cur_vals)))

    for oid, ts, prob in snap_rows:
        if oid != cur_oid:
            _flush()
            if cur_oid is not None:
                series_by_outcome[cur_oid] = ordered
            cur_oid, ordered, cur_ts, cur_vals = oid, [], None, []
        if ts != cur_ts:
            _flush()
            cur_ts, cur_vals = ts, []
        if prob is not None:
            cur_vals.append(float(prob))
    _flush()
    if cur_oid is not None:
        series_by_outcome[cur_oid] = ordered

    # Build three lookups so a competitor whose display name differs from the
    # evolution-market outcome name only by accents or a first-name nickname
    # still gets its sparkline (#191): exact-normalized, diacritic-stripped, and
    # an ambiguity-guarded last-name+first-initial bridge.
    hist_full: dict[str, dict] = {}
    hist_ascii: dict[str, dict] = {}
    hist_li: dict[str, dict] = {}
    hist_li_ambiguous: set[str] = set()
    for oid, pts in series_by_outcome.items():
        if len(pts) < 2:
            continue
        ds = downsample_points(pts, target_points)
        entry = {
            "outcome_id": oid,
            "history": [
                {"timestamp": ts.isoformat(), "probability": round(p, 4)}
                for ts, p in ds
            ],
        }
        name = id_to_name.get(oid)
        hist_full[_norm_player_name(name)] = entry
        hist_ascii.setdefault(_ascii_player_name(name), entry)
        li = _last_first_initial_key(name)
        if li:
            if li in hist_li:
                hist_li_ambiguous.add(li)
            hist_li[li] = entry

    # Only bridge by last-name+initial when it's unambiguous on BOTH sides.
    comp_li_counts: dict[str, int] = {}
    for c in competitors:
        li = _last_first_initial_key(c.get("name"))
        if li:
            comp_li_counts[li] = comp_li_counts.get(li, 0) + 1

    for c in competitors:
        name = c.get("name")
        entry = hist_full.get(_norm_player_name(name)) or hist_ascii.get(
            _ascii_player_name(name)
        )
        if not entry:
            li = _last_first_initial_key(name)
            if li and li not in hist_li_ambiguous and comp_li_counts.get(li) == 1:
                entry = hist_li.get(li)
        if entry:
            c["outcome_id"] = entry["outcome_id"]
            c["history"] = entry["history"]

    _reconcile_history_to_blend(competitors)


def _reconcile_history_to_blend(competitors: list[dict]) -> None:
    """#213 / #199 one-number reconciliation. Mutates each competitor's `history`
    so its final point equals the blend the leaderboard shows next to it.

    The history series comes from a SINGLE market — `evolution_market_id`, chosen
    as the snapshot-richest winner market (for a major, the long-lived odds_api
    futures, whose raw per-outcome probabilities carry the full bookmaker overround
    and sum well above 1). The leaderboard "Win" column, by contrast, shows the
    field-renormalized cross-source BLEND (`competitor["probability"]`) — the
    house's honest number ("the blend is the product"). Left as-is they diverge on
    the SAME page (The Open: Scheffler 24.5% on the Race chart vs 12.3% on the
    leaderboard).

    Anchor each competitor's series to its blend by scaling the whole series by
    `blend / last_raw`. This preserves the movement/trend shape from the richest
    snapshot source while guaranteeing the chart's current value == the leaderboard
    value for every competitor — one question, one number, fixed at the payload so
    no renderer can diverge again. For F1/tennis the leaderboard prob IS this same
    raw series' current point, so the factor is ~1.0 (a no-op); the reconciliation
    only bites the golf blend-vs-evolution-market mismatch.
    """
    for c in competitors:
        hist = c.get("history")
        blend = c.get("probability")
        if not hist or not isinstance(blend, (int, float)) or blend <= 0:
            continue
        last_raw = None
        for pt in reversed(hist):
            p = pt.get("probability")
            if p is not None:
                last_raw = p
                break
        if not last_raw or last_raw <= 0:
            continue
        factor = blend / last_raw
        if abs(factor - 1.0) < 1e-6:
            continue
        c["history"] = [
            {
                "timestamp": pt["timestamp"],
                "probability": (
                    round(pt["probability"] * factor, 4)
                    if pt.get("probability") is not None else None
                ),
            }
            for pt in hist
        ]


def _clean_prop_label(market_name: str | None, tournament_name: str | None) -> str:
    """Strip the tournament-name prefix off a prop market name so the PropsSection
    row reads as the question itself ("The Open Championship: Playoff" -> "Playoff").
    Falls back to the raw name (or "Prop") when there is nothing to strip."""
    name = (market_name or "").strip()
    tn = (tournament_name or "").strip()
    if tn and name.lower().startswith(tn.lower()):
        rest = name[len(tn):].lstrip(" :–-").strip()
        if rest:
            name = rest
    return name or "Prop"


# A multi-outcome family reads as a flat placeholder (not a real book) — the #199
# wide-spread/no-trade capture signature — when the whole field agrees. "Agrees" is
# tested two ways because the captured placeholders are not always perfectly tied:
# The Open's R2 leaders were all exactly 0.24 (0pp spread) but R3 spanned ~1pp
# (0.29–0.30). An ABSOLUTE floor alone (0.5pp) missed R3; a RELATIVE test —
# (max-min)/max — catches both (R2 0%, R3 3.3%) while a genuine field's favorites
# tower over its longshots (R1: 59% relative spread), so neither trips on real books.
_DEGENERATE_TIED_EPS = 0.005   # absolute: <=0.5pp across the field
_DEGENERATE_FLAT_RATIO = 0.10  # relative: (max-min)/max <= 10% => the field agrees


def _is_degenerate_placeholder(outs: list[dict]) -> bool:
    """True when a MULTI-outcome prop family carries NO honest price — the #199
    wide-spread/no-trade capture class: every outcome's `opening_probability` is null
    AND the live probabilities are either all null or a near-flat placeholder where
    the whole field agrees. Such a family must render an honest pending state ("Opens
    after Round N" / "no market yet"), never the fabricated flat and never an arbitrary
    crowned "leader".

    Restricted to families with ≥2 outcomes — the degeneracy signature is agreement
    ACROSS a field. A single-outcome prop (a lone binary "Yes", or a one-golfer test
    row) has no field to agree, so a real-but-opening-less single price renders
    normally (falls through to the usual leader path). A single real opening OR a real
    spread in the live probabilities also means the book is priced → False."""
    if len(outs) < 2:
        return False  # no field to be "tied" across — not the placeholder signature
    if any(isinstance(o.get("opening_probability"), (int, float)) for o in outs):
        return False  # a real opening mark exists → the family is priced
    currents = [o.get("probability") for o in outs if isinstance(o.get("probability"), (int, float))]
    if not currents:
        return True  # nothing priced at all → no market yet
    mx, mn = max(currents), min(currents)
    if mx <= 0:
        return True  # a field of zeros is not a real book
    spread = mx - mn
    return spread <= _DEGENERATE_TIED_EPS or (spread / mx) <= _DEGENERATE_FLAT_RATIO


# ---------------------------------------------------------------------------
# Prop archetype classification (Alex's ruling, The Open 2026: "the divergence
# box is still just a wall of numbers … some rows have a probability but not a
# name"). Every prop family is one of three SHAPES, and the shape decides the
# visual: a BINARY is one question (Playoff? Albatross?) → divergence bar; a
# LADDER's outcomes are threshold rungs ("Under 63.5", "Exactly 2 strokes",
# "1+ holes-in-one") → the QuantityGroup heat ladder Alex likes; a FIELD's
# outcomes are named entities (Top American Golfer, Region to Win — or an Emmy
# category's nominees) → named top-N mini-race, NEVER a number without a name.
# Shape-based (not name-regex) so the same classification carries to any future
# prop-heavy event: majors, award shows, elections.
# ---------------------------------------------------------------------------

_LADDER_OUTCOME_RE = re.compile(r"^\s*(?:under|over|exactly)\b|^\s*\d+\s*\+", re.IGNORECASE)
_BINARY_OUTCOME_RE = re.compile(r"^\s*(?:yes|no)\s*$", re.IGNORECASE)

# Outcome-slice caps: a field shows its top contenders (3 of possibly 150+); a
# ladder shows its rungs (families run 3–10).
_FIELD_OUTCOME_CAP = 3
_LADDER_OUTCOME_CAP = 8


def classify_prop_kind(outcomes: list[dict]) -> str:
    """The prop family's shape: ``binary`` | ``ladder`` | ``field``.

    Pure + shape-based: a single outcome or an all-Yes/No family is binary; a
    family whose names are mostly anchored threshold labels ("Under 67.5",
    "Exactly 2 strokes", "2+ holes-in-one") is a ladder; anything else — named
    entities — is a field. Anchored patterns matter: "R1: Alex Fitzpatrick under
    70.5 strokes" carries a name FIRST, so it stays a field (the name is the
    information; a ladder of unrelated golfers would be dishonest)."""
    named = [str(o.get("name") or "") for o in (outcomes or []) if o.get("name")]
    if len(named) <= 1:
        return "binary"
    if all(_BINARY_OUTCOME_RE.match(n) for n in named):
        return "binary"
    ladderish = sum(1 for n in named if _LADDER_OUTCOME_RE.search(n))
    if ladderish >= max(2, int(round(0.7 * len(named)))):
        return "ladder"
    return "field"


def _prop_outcome_slice(outcomes: list[dict], kind: str) -> list[dict]:
    """Top priced outcomes for the props section — {name, probability,
    opening_probability} only (probability-only rule; no odds, no source names).
    Field → top 3 by probability; ladder → up to 8 rungs. Empty for binary (its
    single number already rides the mark's current/pregame fields)."""
    if kind == "binary":
        return []
    priced = [
        o for o in (outcomes or [])
        if isinstance(o.get("probability"), (int, float)) and o.get("name")
    ]
    priced.sort(key=lambda o: o["probability"], reverse=True)
    cap = _LADDER_OUTCOME_CAP if kind == "ladder" else _FIELD_OUTCOME_CAP
    out = []
    for o in priced[:cap]:
        opening = o.get("opening_probability")
        out.append(
            {
                "name": o.get("name"),
                "probability": o.get("probability"),
                "opening_probability": opening if isinstance(opening, (int, float)) else None,
            }
        )
    return out


def build_golf_props_script(
    children: list[dict],
    tournament_name: str | None,
    status: str,
) -> list[dict]:
    """Map golf concept prop children into the PropMark contract the shared
    PropsSection renders under the FIELD hero (THE SCRIPT → THE DIVERGENCE).

    One mark per prop, tracking its current-favorite outcome: `pregame_mark` = that
    outcome's opening probability (routes/golf.py now emits `opening_probability`
    per outcome), `current` = its live probability. Both endpoints of the arc
    describe the SAME outcome, so the divergence is meaningful. Field-shaped round
    props ("Round 1 Leader") name the current pick; binary/threshold props ("Playoff",
    "Hole-in-One") read as the question. Sorted biggest opening→current mover first
    so the strongest story leads (THE SCRIPT keeps this order; THE DIVERGENCE re-ranks
    client-side).

    L2-123 / #199 honesty: a degenerate prop family (no opening, all-tied flat or
    null live probabilities — the wide-spread/no-trade capture class) does NOT get a
    fabricated flat and is NOT crowned with an arbitrary "leader". It emits a mark
    carrying `pending_label` ("Opens after Round N" for a not-yet-live round leader,
    "No market yet" otherwise) that PropsSection renders as the design's quiet pending
    state. Rendering whatever #199 leaves in the store — nulled placeholders show the
    honest label instead of vanishing (never blank) or lying (never fake flats).

    Suppressed once settled — a concluded field shows the champion, not stale prop
    marks (settled-means-settled); grading field-shaped props is a separate backend
    (#887 / L2-121 Item 3), so WHAT HIT is intentionally deferred here. Pure —
    unit-tested. Returns [] when nothing usable, so the frontend gates the mount on
    presence and falls back to the plain props rendering otherwise.
    """
    if (status or "").lower() == "settled":
        return []
    marks: list[dict] = []
    for c in children or []:
        outs = c.get("outcomes") or []
        if not outs:
            continue  # null/empty child — nothing to render (Item 3 territory)
        mid = c.get("market_id")
        base = _clean_prop_label(c.get("market_name") or c.get("name"), tournament_name)
        # Settled-means-settled (The Open 2026 p0): a concluded round's leader
        # market is graded upstream (routes/golf sets `settled`/`graded_winner`
        # from is_winner once the round ends; Kalshi leaves status='open',
        # gotcha #33, so is_winner is the round-complete signal — not status).
        # It renders as WHAT HIT: the graded round leader, with NO live losers
        # and NO divergence. Takes precedence over the live-leader path below so
        # a completed round can never show live odds on an in-progress event.
        if c.get("settled"):
            winner = c.get("graded_winner")
            if not winner:
                # A completed round's Top-N projection ("Round 1 Top 10
                # Finishers") — the round is over (inferred from the round
                # leaders) but this market carries no single gradeable winner.
                # Settled-means-settled: it must not show live odds, and we
                # can't grade a Top-N field here (that's the deferred #887 /
                # L2-121 Item 3 backend), so suppress it rather than lie.
                continue
            marks.append(
                {
                    "key": mid,
                    "market_id": mid,
                    "label": f"{base}: {winner}",
                    "question": base,
                    "kind": None,  # graded row, not a live card/bar
                    "outcomes": [],
                    "pregame_mark": None,
                    "current": None,
                    "graded_result": "hit",
                    "graded_label": f"{winner} led",
                    "pending_label": None,
                    "settled": True,
                }
            )
            continue
        # #199 degenerate family → honest pending row (no fake flat, no false leader).
        if _is_degenerate_placeholder(outs):
            rnd = c.get("round")
            if c.get("prop_type") == "round" and isinstance(rnd, int) and rnd > 1:
                pending = f"Opens after Round {rnd - 1}"
            else:
                pending = "No market yet"
            marks.append(
                {
                    "key": mid,
                    "market_id": mid,
                    "label": base,
                    "question": base,
                    "kind": classify_prop_kind(outs),
                    "outcomes": [],
                    "pregame_mark": None,
                    "current": None,
                    "graded_result": None,
                    "graded_label": None,
                    "pending_label": pending,
                    "settled": False,
                }
            )
            continue
        leader = None
        best = -1.0
        for o in outs:
            p = o.get("probability")
            if isinstance(p, (int, float)) and p > best:
                best = p
                leader = o
        if leader is None or not isinstance(leader.get("probability"), (int, float)):
            continue
        kind = classify_prop_kind(outs)
        if c.get("prop_type") == "round" and leader.get("name"):
            label = f"{base}: {leader['name']}"
        elif kind == "field" and leader.get("name"):
            # A field mark's number belongs to a NAME — a probability without one
            # is the "Top Asian/Oceanic golfer has a probability but not a name"
            # bug (Alex, The Open 2026). The legacy label carries the favorite;
            # the visual renderer uses `question` + `outcomes` instead.
            label = f"{base}: {leader['name']}"
        else:
            label = base
        opening = leader.get("opening_probability")
        marks.append(
            {
                "key": mid,
                "market_id": mid,
                "label": label,
                "question": base,
                "kind": kind,
                "outcomes": _prop_outcome_slice(outs, kind),
                "pregame_mark": opening if isinstance(opening, (int, float)) else None,
                "current": leader.get("probability"),
                "graded_result": None,
                "graded_label": None,
                "pending_label": None,
                "settled": False,
            }
        )

    def _movement(m: dict) -> float:
        pg, cur = m.get("pregame_mark"), m.get("current")
        if isinstance(pg, (int, float)) and isinstance(cur, (int, float)):
            return abs(cur - pg)
        return -1.0

    # Stable sort: biggest mover first; no-movement marks (incl. pending) sink but
    # keep order, so real prop stories lead and honest-pending rows trail.
    marks.sort(key=_movement, reverse=True)
    return marks


def golf_detail_to_envelope(key: str, slug: str, data: dict) -> dict:
    """Map get_golf_tournament()'s output into the generic event envelope.

    Pure — unit-tested. Preserves the golf data (parity) under generic keys so the
    frontend renders domain-agnostically."""
    t = data.get("tournament", {}) or {}

    # L2-89: forward round-scoped groups (round leaders + Round-N Top-M projections)
    # as PROP children so the concept page's props section renders them. Previously
    # `round_top_groups` was dropped from the envelope entirely, so the round-leader
    # and per-round families were invisible on /event/<key> even though the bespoke
    # golf page rendered them. Each group is already {market_id, outcomes:[{name,
    # probability}]}, compatible with EventConceptChild; a round-qualified label
    # disambiguates the cards (EventProps does not group by round).
    def _round_child_label(g: dict) -> str:
        rnd = g.get("round")
        if g.get("kind") == "leader":
            return f"Round {rnd} Leader" if rnd else "Round Leader"
        tn = g.get("top_n")
        base = f"Top {tn} Finishers" if tn else "Top Finishers"
        return f"Round {rnd}: {base}" if rnd else base

    round_children = [
        {
            "market_id": g.get("market_id"),
            "market_name": _round_child_label(g),
            "outcomes": g.get("outcomes", []),
            "kind": "prop",
            "prop_type": "round",
            # L2-123: carry the round number so build_golf_props_script can label a
            # degenerate (not-yet-live) round-leader family "Opens after Round N-1".
            "round": g.get("round"),
            # The Open 2026 p0: a concluded round's leader market is graded
            # upstream (routes/golf sets these once is_winner lands). Carry the
            # signal so the props body renders WHAT HIT — the round leader,
            # graded — instead of a live divergence with stale losers.
            "settled": bool(g.get("settled")),
            "graded_winner": g.get("graded_winner"),
        }
        for g in (data.get("round_top_groups") or [])
    ]
    # L2-123 Item 3: drop pure-junk related-futures rows (no name AND no outcomes) so
    # they never render as an empty matchup/prop row. Keep anything with a name OR
    # outcomes — a thin but real market still surfaces.
    related = [
        rf
        for rf in (data.get("related_futures") or [])
        if (rf.get("name") or rf.get("market_name")) or (rf.get("outcomes"))
    ]
    children = related + round_children

    # L2-121: the shared PropsSection body (THE SCRIPT → THE DIVERGENCE) for the
    # FIELD hero. Built from the prop children's opening→current marks; empty when
    # settled or when no usable marks exist (the frontend then falls back to the
    # plain props rendering). Disjoint from the finish-position ladder, which reads
    # `sections`/competitor fields — no double-render.
    props_script = build_golf_props_script(children, t.get("name"), _golf_status(t))

    return {
        "event": {
            "key": key if key.startswith("event:") else f"event:golf:{slug}",
            # L2-113: URL slug (golf's is already clean, e.g. "the-open-championship").
            "slug": slug,
            "domain": "golf",
            "name": t.get("name"),
            "status": _golf_status(t),
            "start_date": t.get("start_date"),
            "end_date": t.get("end_date"),
            "venue": t.get("venue"),
            "location": t.get("location"),
            "is_major": bool(t.get("is_major", False)),
            # L2-66: freshness stamp for the live leaderboard; set by build_event
            # when live data is fused (None otherwise).
            "as_of": None,
        },
        "primary": {
            "kind": "winner_field",  # golf is always a winner-field (leaderboard)
            "label": "Winner",
            "competitors": data.get("golfers", []) or [],
            "evolution_market_id": data.get("evolution_market_id"),
        },
        "sections": data.get("markets", []) or [],
        "children": children,
        "props_script": props_script,
        "movers": data.get("biggest_movers", []) or [],
    }


class GolfEventAdapter:
    domain = "golf"

    async def build_event(self, slug: str, db: AsyncSession) -> dict | None:
        # Lazy import — golf.py pulls a large dependency graph; importing at call
        # time keeps this module (and the route) cheap and circular-import safe.
        from fastapi import HTTPException
        from app.routes.golf import get_golf_tournament

        try:
            data = await get_golf_tournament(slug=slug, db=db)
        except HTTPException as exc:
            if exc.status_code == 404:
                return None
            raise
        key = f"event:golf:{slug}"
        envelope = golf_detail_to_envelope(key, slug, data)
        tournament = data.get("tournament", {}) or {}

        # Belt-and-braces live detection + fused leaderboard (#144, extends L2-66).
        # The schedule-string path (`_golf_status`) leaves live tournaments stuck
        # at "upcoming" because DataGolf's get-schedule `status` does not flip to
        # "in-progress" during play. So: unless the tournament is already SETTLED,
        # read the STORED leaderboard once and treat live in-play rows within the
        # play window (or, if schedule dates are missing, a fresh leaderboard) as
        # authoritative proof of play → flip status to LIVE and fuse. Read-only DB
        # (PK lookup on the win market) — NEVER re-poll DataGolf on the request path.
        if envelope["event"]["status"] != "settled":
            # L2-125: the live-leaderboard flip must read the market that actually
            # CARRIES the leaderboard. The DataGolf in-play poll writes
            # market_metadata["leaderboard"] onto the DATAGOLF win market, but
            # evolution_market_id is picked by snapshot richness — for majors that
            # is the long-lived odds_api winner futures market (open for months),
            # which never receives a leaderboard. The two diverge, so a PK lookup on
            # evolution_market_id alone left The Open stuck on "upcoming" 8h into
            # round 1 with the leaders already through 16 holes. Scan every
            # winner-group market and use the one with a live leaderboard (freshest
            # wins), keeping evolution_market_id only as a fallback candidate.
            candidate_ids: list[int] = []
            evo_id = data.get("evolution_market_id")
            if evo_id:
                candidate_ids.append(evo_id)
            for grp in data.get("markets") or []:
                if grp.get("type") == "winner":
                    for mid in grp.get("market_ids") or []:
                        if mid and mid not in candidate_ids:
                            candidate_ids.append(mid)
            if candidate_ids:
                try:
                    from sqlalchemy import select
                    from app.models import FuturesMarket

                    rows = (
                        await db.execute(
                            select(
                                FuturesMarket.external_id,
                                FuturesMarket.market_metadata,
                            ).where(FuturesMarket.id.in_(candidate_ids))
                        )
                    ).all()
                    # Pick the winner market carrying a live leaderboard; ISO
                    # timestamps sort lexically so the freshest stamp wins ties.
                    ext_id = None
                    leaderboard: list = []
                    updated_at = None
                    best_ts = None
                    for r_ext, r_meta in rows:
                        m = r_meta or {}
                        lb = m.get("leaderboard") or []
                        if not _golf_leaderboard_has_live_rows(lb):
                            continue
                        ts = m.get("leaderboard_updated_at")
                        if best_ts is None or (ts and ts > best_ts):
                            best_ts = ts
                            ext_id = r_ext
                            leaderboard = lb
                            updated_at = ts
                    now = datetime.now(timezone.utc)
                    if _golf_leaderboard_has_live_rows(leaderboard) and (
                        _golf_within_play_window(
                            tournament.get("start_date"),
                            tournament.get("end_date"),
                            now,
                        )
                        or _golf_leaderboard_is_fresh(updated_at, now)
                    ):
                        envelope["event"]["status"] = "live"
                        as_of = fuse_golf_live(
                            envelope["primary"]["competitors"],
                            leaderboard,
                            updated_at,
                        )
                        envelope["event"]["as_of"] = as_of
                        envelope["event"]["live_mode"] = "golf_leaderboard"

                        # L2-69: the true in-play win-prob delta ("who's charging").
                        # Baseline = the day's start-of-day snapshot (rounds ≥2,
                        # matching /api/golf/leaderboard); round 1 falls back to
                        # opening_probability inside golf_live_deltas. Best-effort.
                        baseline_by_name: dict[str, float] = {}
                        try:
                            rounds = [
                                e.get("current_round")
                                for e in leaderboard
                                if e.get("current_round")
                            ]
                            cur_round = max(rounds) if rounds else None
                            tour = (
                                ext_id.split(":")[1]
                                if isinstance(ext_id, str)
                                and ext_id.startswith("datagolf:")
                                and len(ext_id.split(":")) >= 2
                                else None
                            )
                            if cur_round and cur_round >= 2 and tour:
                                from app.models.models import GolfLeaderboardSnapshot
                                from zoneinfo import ZoneInfo

                                today_start = now.astimezone(
                                    ZoneInfo("America/New_York")
                                ).replace(hour=0, minute=0, second=0, microsecond=0)
                                snap = (
                                    await db.execute(
                                        select(GolfLeaderboardSnapshot).where(
                                            GolfLeaderboardSnapshot.tour == tour,
                                            GolfLeaderboardSnapshot.snapshot_date
                                            == today_start,
                                            GolfLeaderboardSnapshot.snapshot_type
                                            == "start_of_day",
                                        )
                                    )
                                ).scalar_one_or_none()
                                if snap and snap.data:
                                    for entry in snap.data:
                                        nm = entry.get("player_name")
                                        wp = entry.get("win_prob")
                                        if nm and wp is not None:
                                            baseline_by_name[_norm_player_name(nm)] = wp
                            golf_live_deltas(
                                envelope["primary"]["competitors"], baseline_by_name
                            )
                        except Exception:
                            pass
                except Exception:
                    # Live fusion is best-effort — a failure must not 500 the page;
                    # it just renders probability-only (honest degrade).
                    pass

        # L2-71: attach compact per-competitor history to the top competitors so
        # the leaderboard sparklines + RaceToTitleChart read from the envelope in
        # one fetch (drops two separate /api/futures history client calls — net
        # less DB work). Best-effort; runs pre-tournament + live.
        try:
            await attach_competitor_history(
                db,
                data.get("evolution_market_id"),
                envelope["primary"]["competitors"],
            )
        except Exception:
            pass

        # Live AI commentary box — THE OPEN CHAMPIONSHIP only, LIVE only (same-day
        # feature 2026-07-19). The request path NEVER calls OpenAI: the background
        # task app.tasks.golf_commentary generates and caches the blurb in Redis;
        # here we only READ that key and attach it. Double-gated on status==live
        # (this envelope's own status AND the writer's), so it never shows on a
        # settled/upcoming page. Best-effort: any failure → no box.
        try:
            from app.utils.golf_commentary import (
                is_open_championship,
                commentary_redis_key,
            )

            if envelope["event"]["status"] == "live" and is_open_championship(
                slug, envelope["event"].get("name")
            ):
                from app.tasks.redis_state import get_redis_client

                rc = get_redis_client()
                raw = rc.get(commentary_redis_key(slug))
                if raw:
                    import json as _json

                    parsed = _json.loads(
                        raw.decode() if isinstance(raw, bytes) else raw
                    )
                    text = (parsed or {}).get("text")
                    if text:
                        envelope["commentary"] = {
                            "text": text,
                            "generated_at": parsed.get("generated_at"),
                            "as_of": parsed.get("as_of"),
                        }
        except Exception:
            pass

        return envelope


register_adapter(GolfEventAdapter())


async def list_golf_tournament_concepts(
    db,
    *,
    statuses: tuple[str, ...] = ("upcoming", "live"),
    limit: int = 20,
) -> list[dict]:
    """Enumerate upcoming/live GOLF tournament concepts for the /hub/golf rail
    (L2-87 B6) — the winner-field analogue of `list_ufc_card_concepts`. Reuses the
    proven `get_golf()` aggregation + DataGolf schedule enrichment (parity), so the
    slug each concept emits is EXACTLY what `GolfEventAdapter`/`get_golf_tournament`
    resolve — both key off `clean_slug(name)`, which `get_golf` already computes as
    `t["slug"]`. Read-only, best-effort.

    Returns lightweight dicts the hub links to `/event/{key}`:
        {key, name, domain, status, start_date, is_major, entry_count}
    """
    from app.routes.golf import get_golf

    try:
        data = await get_golf(db=db)
    except Exception:
        return []

    concepts: list[dict] = []
    for t in data.get("tournaments") or []:
        name = t.get("name")
        slug = t.get("slug")
        # Skip the "other_<id>" catch-all buckets — they aren't real tournaments.
        if not name or not slug or str(t.get("key", "")).startswith("other_"):
            continue
        status = _golf_status(t)
        if status not in statuses:
            continue
        concepts.append(
            {
                "key": f"event:golf:{slug}",
                "name": name,
                "domain": "golf",
                "status": status,
                "start_date": t.get("start_date") or t.get("commence_time"),
                "is_major": bool(t.get("is_major")),
                "entry_count": len(t.get("golfers") or []),
            }
        )

    # Majors first, then soonest start (the imminent major is the interesting one).
    concepts.sort(key=lambda c: (0 if c["is_major"] else 1, c.get("start_date") or "9999"))
    return concepts[:limit]


# Tennis adapter (slice 2, #999) — separate module; registered here so the
# registry stays the single hub. Its DB work is lazy-imported inside build_event.
from app.utils.event_tennis import TennisEventAdapter  # noqa: E402

register_adapter(TennisEventAdapter())

# F1 (winner-field) + UFC (co_equal_list) adapters — slices 3/4 (#999 L2-72).
# Boxing (co_equal_list) — L2-86 (B5): same combat engine as UFC, config-only.
from app.utils.event_boxing import BoxingEventAdapter  # noqa: E402
from app.utils.event_f1 import F1EventAdapter  # noqa: E402
from app.utils.event_ufc import UFCEventAdapter  # noqa: E402

register_adapter(F1EventAdapter())
register_adapter(UFCEventAdapter())
register_adapter(BoxingEventAdapter())

# Awards (co_equal_list) — L2-87 (B6): the framework's non-sports proof (design §6).
# Categories are the co-equal children; the marquee category is the head-to-head hero.
from app.utils.event_awards import AwardsEventAdapter  # noqa: E402

register_adapter(AwardsEventAdapter())

# Elections (co_equal_list) — L2-89 (B6): the framework's civic proof (design §6).
# An election night's races are the co-equal children; the marquee race (chamber
# control when it appears, else the richest governor race) is the head-to-head hero.
from app.utils.event_election import ElectionEventAdapter  # noqa: E402

register_adapter(ElectionEventAdapter())

# Soccer tournaments (winner_field) — #205 (World Cup Emergency Assembly). The
# trophy winner field is the primary block (national teams); the remaining bracket
# GAMES (from the events table) are the duel children. First adapter to fuse the
# futures + events data planes.
from app.utils.event_soccer import SoccerEventAdapter  # noqa: E402

register_adapter(SoccerEventAdapter())
