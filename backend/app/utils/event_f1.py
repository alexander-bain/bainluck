"""F1 / motorsports adapter for the Event Concept framework — slice 4 (#999, L2-72).

A Grand Prix is a winner-field event (like golf/tennis): the race-winner market
is the primary field; qualifying / sprint / podium / constructor / top-N markets
for the same GP fold in as children. Verified live (2026-07-09): Kalshi carries
"<GP> Winner" (e.g. KXF1RACE-BRIGP26) plus per-GP quali/sprint/podium markets,
category=motorsports; Polymarket adds "<GP>: Driver Winner".

Pure helpers are unit-tested; build_event is exercised via the route test.
"""

from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.utils.futures_market_snapshot import price_observed_at_iso

# Tokens stripped when deriving the GP name from a market title.
_F1_STOPWORDS = {
    "grand", "prix", "race", "main", "winner", "session", "the", "driver",
    "sprint", "qualifying", "pole", "position", "podium", "finishers", "top",
    "constructor", "fastest", "lap", "formula", "2024", "2025", "2026", "2027",
    "gp", "f1",
}

# A sub-market (not the main race winner) — used to prefer the real GP winner.
_F1_SUBMARKET_RE = re.compile(
    r"\b(sprint|qualifying|pole|podium|constructor|fastest|top\s*\d|q[123])\b",
    re.IGNORECASE,
)
_F1_WINNER_RE = re.compile(r"\b(winner|to win)\b", re.IGNORECASE)

# L2-83: raw price at/above which a SETTLED race-winner outcome is the crowned
# winner during the is_winner grading-lag window. Display-only; never authoritative
# (gotcha #21). Mirrors the tennis adapter.
_WON_PRICE_THRESHOLD = 0.97


def is_gp_winner_market(name: str | None) -> bool:
    """True for the main-race GP winner field (not a sprint/quali/pole sub-market)."""
    n = name or ""
    return bool(_F1_WINNER_RE.search(n)) and not _F1_SUBMARKET_RE.search(n)


def gp_tokens(name: str | None) -> set[str]:
    """Distinctive Grand Prix name tokens (drops the generic F1 scaffolding).

    "British Grand Prix Winner" -> {"british"};
    "Austrian Grand Prix Main Race: Podium Finishers" -> {"austrian"}."""
    raw = re.sub(r"[^a-z0-9\s]", " ", (name or "").lower())
    return {t for t in raw.split() if len(t) >= 4 and t not in _F1_STOPWORDS}


def shares_gp(name: str | None, tokens: set[str]) -> bool:
    if not tokens:
        return False
    return bool(gp_tokens(name) & tokens)


#: How long before lights-out a Grand Prix counts as under way, and how long
#: after. The anchor is the winner market's `resolution_date`, which the census
#: of 60 production GP-winner rows (2026-09-09) shows is the RACE START and not
#: an end-of-day placeholder: Monza 13:00Z = 15:00 CEST lights-out, Silverstone
#: 14:00Z = 15:00 BST, Montreal 20:00Z = 16:00 EDT, and 0 of 60 rows sat at
#: midnight or 23:59. A race plus its podium runs ~3h, so the window either side
#: of that anchor is a real race-day window and nothing wider.
_F1_LIGHTS_OUT_LEAD_HOURS = 4.0
_F1_RACE_RUN_HOURS = 3.0


def f1_status(status: str | None, resolution_date, now) -> str:
    """upcoming / live / settled for a Grand Prix, from its status + race time.

    "live" is a claim the reader can check, not a proximity band. The card wears
    the same pulsing red `● LIVE` pill the Champions League match at 67' wears
    (`TemporalBadge`, discover/shared.tsx) and the concept's own page prints
    `LIVE` directly above its date line — so on 2026-09-09 the Italian Grand Prix
    page read "LIVE" over "Sep 13 – Sep 13", four days out, because the old band
    called any race within 4 DAYS live. It also paid the +35 `_score_event_concept`
    live bonus, the largest term in that function, which is what carried the card
    onto page one on the strength of the thing that was false.

    So the window is the race, not the week: from `_F1_LIGHTS_OUT_LEAD_HOURS`
    before the anchor until `_F1_RACE_RUN_HOURS` after it. Race-weekend proximity
    still ranks the card — `_score_event_concept` pays +15/+10 for a race three or
    seven days out — it just no longer tells the reader the race is happening.

    The trailing arm is the same fix seen from the other side: the old rule flipped
    the card to "settled" the instant the anchor passed, so a race that had just
    gone green was dropped from the feed as finished. A venue grade
    (resolved/closed/settled/final) is still authoritative the moment it lands and
    overrides both arms. Conservative: no time → upcoming."""
    if (status or "").lower() in ("resolved", "closed", "settled", "final"):
        return "settled"
    if resolution_date is not None:
        try:
            hours = (resolution_date - now).total_seconds() / 3600
        except TypeError:
            return "upcoming"
        if hours < -_F1_RACE_RUN_HOURS:
            return "settled"
        if hours <= _F1_LIGHTS_OUT_LEAD_HOURS:
            return "live"
    return "upcoming"


async def list_f1_gp_concepts(
    db: AsyncSession,
    *,
    statuses: tuple[str, ...] = ("upcoming", "live"),
    limit: int = 20,
    rows: list | None = None,
) -> list[dict]:
    """Enumerate F1 Grand Prix concepts for the sports feed (L2-86 B5) — the
    winner-field analogue of `list_ufc_card_concepts`. Groups open motorsports
    markets by their distinctive GP token (british / austrian / …), anchoring each
    GP on its main-race winner market. Returns lightweight dicts the feed scorer
    turns into candidates linking to `/event/{key}`:

        {key, name, domain, status, start_date, is_major, entry_count,
         latest_commence}

    Read-only, best-effort. Uses `resolution_date` (the race time) as the event
    time — `commence_time` is the market-open date, not the race (gotcha #14).

    `rows` is LAT-P094's accelerator — the concept tier reads every source's
    open markets in one scan instead of one per source; see
    `event_concept_population.prefetch_open_markets`. Passing nothing keeps the
    standalone read."""
    from datetime import datetime, timezone

    from app.utils.event_concept_population import F1_PROJECTION, select_open_markets
    from app.utils.name_normalization import clean_slug

    now = datetime.now(timezone.utc)
    if rows is None:
        rows = await select_open_markets(db, "motorsports", F1_PROJECTION)

    # Anchor each GP on its main-race winner market; group by distinctive GP token.
    # The lister is F1-Grand-Prix-scoped: require "grand prix" in the name. This
    # both matches the product ask and guards against non-race "winner" markets that
    # are miscategorized as motorsports (e.g. the World Cup KXWCGROUPPTS "Any Group
    # Winner…" market) leaking a nonsense concept onto the feed — `is_gp_winner_market`
    # stays untouched (the /event adapter still resolves NASCAR/MotoGP by slug).
    groups: dict[frozenset, dict] = {}
    for _mid, name, status, res in rows:
        if "grand prix" not in (name or "").lower():
            continue
        if not is_gp_winner_market(name):
            continue
        toks = frozenset(gp_tokens(name))
        if not toks:
            continue
        g = groups.get(toks)
        if g is None:
            slug = clean_slug(name or "")
            if not slug:
                continue
            groups[toks] = {
                "name": name,
                "slug": slug,
                "status": status,
                "resolution": res,
                "markets": 0,
            }
        elif res is not None and (g["resolution"] is None or res < g["resolution"]):
            # Prefer the soonest-resolving winner market's race time as the anchor.
            g["resolution"] = res

    # Count all weekend markets per GP (winner + quali/sprint/podium/…) as a size
    # proxy — the analogue of a card's fight_count.
    for _mid, name, _status, _res in rows:
        toks_n = gp_tokens(name)
        for toks, g in groups.items():
            if toks & toks_n:
                g["markets"] += 1

    concepts: list[dict] = []
    for _toks, g in groups.items():
        res = g["resolution"]
        status = f1_status(g["status"], res, now)
        if status not in statuses:
            continue
        concepts.append(
            {
                "key": f"event:f1:{g['slug']}",
                "name": g["name"],
                "domain": "f1",
                "status": status,
                "start_date": res.isoformat() if res is not None else None,
                "is_major": False,
                "entry_count": g["markets"],
                "latest_commence": res,
            }
        )

    # Soonest race first (the imminent GP is the interesting one).
    concepts.sort(
        key=lambda x: (
            x["latest_commence"] or datetime.max.replace(tzinfo=timezone.utc)
        )
    )
    return concepts[:limit]


class F1EventAdapter:
    domain = "f1"

    async def build_event(self, slug: str, db: AsyncSession) -> dict | None:
        from datetime import datetime, timezone
        from app.models import FuturesMarket
        from app.utils.name_normalization import clean_slug
        from app.utils.outcome_display import (
            is_field_outcome,
            is_placeholder_outcome_name,
            normalize_display_probs,
        )

        now = datetime.now(timezone.utc)
        q = (
            select(FuturesMarket)
            .options(selectinload(FuturesMarket.outcomes))
            .where(
                FuturesMarket.llm_sport_category == "motorsports",
                FuturesMarket.status == "open",
            )
        )
        markets = list((await db.execute(q)).scalars().unique().all())
        if not markets:
            return None

        # Resolve the GP winner market: exact clean_slug OR GP-token subset, richest
        # field wins (mirrors tennis L2-65). Only main-race winners are candidates —
        # sprint/quali/pole are children, never the primary.
        slug_tokens = {t for t in slug.split("-") if len(t) >= 4 and t not in _F1_STOPWORDS}

        def _real_count(m) -> int:
            return sum(
                1 for o in (m.outcomes or [])
                if o.name and not is_field_outcome(o.name)
                and not is_placeholder_outcome_name(o.name)
            )

        candidates = []
        for m in markets:
            if not is_gp_winner_market(m.name):
                continue
            exact = clean_slug(m.name or "") == slug
            subset = bool(slug_tokens) and slug_tokens <= gp_tokens(m.name)
            if exact or subset:
                candidates.append(m)
        winner = max(candidates, key=_real_count) if candidates else None
        if winner is None:
            return None

        canonical_slug = clean_slug(winner.name or "") or slug

        # L2-83: compute the status once — reused by the settled crown and envelope.
        event_status = f1_status(winner.status, winner.resolution_date, now)

        competitors = []
        for o in winner.outcomes or []:
            if is_field_outcome(o.name) or is_placeholder_outcome_name(o.name):
                continue
            competitors.append({
                "name": o.name,
                "probability": (
                    round(float(o.current_probability), 4)
                    if o.current_probability is not None else None
                ),
                # L2-83: authoritative graded winner (parity with tennis). Absent
                # before Lane-1 grades a settled race; the price-settled crown below
                # fills the grading-lag window.
                "won": bool(getattr(o, "is_winner", False)),
            })

        # L2-83: crown the price-settled winner during the grading-lag window (same
        # rationale as tennis) — read the RAW price BEFORE normalize dilutes a
        # dominant leader below the frontend's >=0.9 crown threshold. Display-only.
        if event_status == "settled" and not any(c["won"] for c in competitors):
            top = max(competitors, key=lambda c: (c["probability"] or -1), default=None)
            if top is not None and (top["probability"] or 0) >= _WON_PRICE_THRESHOLD:
                top["won"] = True

        normalize_display_probs(competitors)
        competitors.sort(key=lambda c: (c["probability"] or -1), reverse=True)

        # Children = other markets for this GP (quali/sprint/podium/constructor/top-N).
        tokens = gp_tokens(winner.name)
        children, section_ids = [], []
        for m in markets:
            if m.id == winner.id or not shares_gp(m.name, tokens):
                continue
            outs = sorted(
                (m.outcomes or []),
                key=lambda o: float(o.current_probability or 0),
                reverse=True,
            )
            lead = outs[0] if outs else None
            lead_prob = (
                float(lead.current_probability)
                if lead and lead.current_probability is not None else None
            )
            children.append({
                "market_id": m.id,
                "market_name": m.name,
                "source": m.source,  # data-only (audit); not rendered (D1)
                "probability": round(lead_prob, 4) if lead_prob is not None else None,
                "outcomes": [
                    {"name": o.name, "probability": (
                        round(float(o.current_probability), 4)
                        if o.current_probability is not None else None)}
                    for o in outs[:4]
                ],
            })
            section_ids.append(m.id)

        sections = [{"type": "winner", "label": "Race winner", "market_ids": [winner.id]}]
        if section_ids:
            sections.append({"type": "prop", "label": "Weekend markets", "market_ids": section_ids})

        # L2-83: a GP is a one-day event — its resolution_date IS the race time, the
        # only reliable event-time proxy (commence_time is the market-open date, not
        # the race — gotcha #14). Populate start_date from it so the L2-78 countdown
        # chip ("Starts in N days") renders for an UPCOMING GP; without a start_date
        # daysUntilStart() returns null and the chip never shows. No effect on a live
        # (≤4d) or settled race — countdownLabel() suppresses those.
        race_iso = (
            winner.resolution_date.isoformat()
            if winner.resolution_date is not None else None
        )
        envelope = {
            "event": {
                "key": f"event:f1:{canonical_slug}",
                "domain": "f1",
                "name": winner.name,
                "status": event_status,
                "start_date": race_iso,
                "end_date": race_iso,
                "venue": None,
                "location": None,
                "is_major": False,
            },
            "primary": {
                "kind": "winner_field",
                "label": "Race winner",
                "competitors": competitors,
                "evolution_market_id": winner.id,
                # #5778 — see `event_cycling`. Every concept adapter carries the
                # age or the contract has drifted; a reader gets no say in which
                # domain their card came from.
                "price_observed_at": price_observed_at_iso(winner),
            },
            "sections": sections,
            "children": children,
            "movers": [],
        }

        # L2-71 shared per-competitor history (one fetch); best-effort.
        try:
            from app.utils.event_concept import attach_competitor_history
            await attach_competitor_history(db, winner.id, competitors)
        except Exception:
            pass

        return envelope
