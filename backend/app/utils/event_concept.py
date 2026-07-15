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

def _golf_status(tournament: dict) -> str:
    """Normalize golf's schedule_status into upcoming/live/settled.

    L2-66: DataGolf's schedule reports "in-progress" (HYPHEN) while this only
    matched "in_progress" (underscore) — so a live tournament never flipped the
    event page into LIVE mode. Normalize hyphens→underscores so both forms work.
    """
    raw = (tournament.get("schedule_status") or "").lower().replace("-", "_")
    if raw in ("in_progress", "live", "active"):
        return "live"
    if raw in ("completed", "closed", "resolved", "final", "settled"):
        return "settled"
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
        leader = None
        best = -1.0
        for o in outs:
            p = o.get("probability")
            if isinstance(p, (int, float)) and p > best:
                best = p
                leader = o
        if leader is None or not isinstance(leader.get("probability"), (int, float)):
            continue
        mid = c.get("market_id")
        base = _clean_prop_label(c.get("market_name") or c.get("name"), tournament_name)
        if c.get("prop_type") == "round" and leader.get("name"):
            label = f"{base}: {leader['name']}"
        else:
            label = base
        opening = leader.get("opening_probability")
        marks.append(
            {
                "key": mid,
                "market_id": mid,
                "label": label,
                "pregame_mark": opening if isinstance(opening, (int, float)) else None,
                "current": leader.get("probability"),
                "graded_result": None,
                "graded_label": None,
            }
        )

    def _movement(m: dict) -> float:
        pg, cur = m.get("pregame_mark"), m.get("current")
        if isinstance(pg, (int, float)) and isinstance(cur, (int, float)):
            return abs(cur - pg)
        return -1.0

    # Stable sort: biggest mover first; no-movement marks sink but keep order.
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
        }
        for g in (data.get("round_top_groups") or [])
    ]
    children = (data.get("related_futures") or []) + round_children

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
            evo_id = data.get("evolution_market_id")
            if evo_id:
                try:
                    from sqlalchemy import select
                    from app.models import FuturesMarket

                    row = (
                        await db.execute(
                            select(
                                FuturesMarket.external_id,
                                FuturesMarket.market_metadata,
                            ).where(FuturesMarket.id == evo_id)
                        )
                    ).first()
                    ext_id = row[0] if row else None
                    meta = (row[1] if row else None) or {}
                    leaderboard = meta.get("leaderboard") or []
                    updated_at = meta.get("leaderboard_updated_at")
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
