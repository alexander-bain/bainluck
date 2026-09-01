"""Cycling adapter for the Event Concept framework — The Tour (Queue #223 Item 3).

A Grand Tour (Tour de France / Giro / Vuelta) is a winner-field event, structurally
the F1-Grand-Prix shape: the General Classification (GC) winner market is the primary
field; the per-stage winner markets, the team classification, and any jersey props
fold in as children. Verified live via the census (2026-07-21): Kalshi carries
"Tour de France Winner" (id 55686927, 184 riders, Pogačar 94.5% favorite),
"Tour de France Team Winner", and per-stage "Tour de France: Stage N Winner"
markets, all ``llm_sport_category == "cycling"``. Polymarket carries no TdF markets.

Config-driven because market titles carry no year ("Tour de France Winner"), while
the concept slug does ("tour-de-france-2026"). Editions are disambiguated by matching
the slug's year against the market ``resolution_date`` year, so a 2027 slug never
resolves 2026 markets. The soccer coherence gate is ported so a broken/stale field
(the "Peru 47%" class) never crowns a nonsense GC leader.

#2482 (LAT-P182): the config names race FAMILIES, never editions. It used to hold a
hand-written dict of year-stamped slugs (``vuelta-2026`` and friends), and because the
edition guard also requires the resolution to be ahead of ``now``, those two conditions
became jointly unsatisfiable the moment the configured year ran out — every cycling
concept left Discover and could not come back until a human edited this file. An
edition is now DERIVED from the market's own ``resolution_date`` year, so a new race
year needs no config entry, no calendar maintenance and no January scramble.

Pure helpers are unit-tested; build_event is exercised via the route test.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import lru_cache

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.utils.settledness import settled_under_assigned_state
from app.utils.winner_field_selection import prefer_graded_winner_field

# --- Name gates -------------------------------------------------------------
_WINNER_RE = re.compile(r"\b(winner|to win|champion)\b", re.IGNORECASE)
_STAGE_RE = re.compile(r"\bstage\s*\d+", re.IGNORECASE)
_TEAM_RE = re.compile(r"\bteam\b", re.IGNORECASE)
# Secondary classifications / jersey props (green=points, polka dot=KOM/mountains,
# white=young rider). Folded in as props, NOT the GC winner field.
_JERSEY_RE = re.compile(
    r"\b(green\s+jersey|points\s+classification|polka|mountains?\s+classification|"
    r"king\s+of\s+the\s+mountains?|white\s+jersey|young\s+rider|most\s+aggressive)\b",
    re.IGNORECASE,
)
# Any secondary-classification token that disqualifies a market from being the
# OVERALL GC winner field. Critical: without this, "Green Jersey Winner" / "Points
# Classification Winner" pass the winner gate and a fresher sprinter market can be
# crowned the GC leader (the live bug: Mads Pedersen shown as GC leader over Pogačar).
# Excludes the secondary jerseys/classifications but NOT "General Classification".
_NON_GC_RE = re.compile(
    r"\b(green\s+jersey|polka\s*dot|white\s+jersey|points|sprints?|intermediate|"
    r"mountains?|king\s+of\s+the\s+mountain|young\s+rider|combativity|"
    r"most\s+aggressive|super[\s-]?combativity)\b",
    re.IGNORECASE,
)

# L2-83 parity: raw price at/above which a SETTLED GC-winner outcome is the crowned
# winner during the is_winner grading-lag window. Display-only; never authoritative
# (gotcha #21). Mirrors the F1/tennis adapters.
_WON_PRICE_THRESHOLD = 0.97

# Coherence gate (ported from event_soccer — the "Peru 47%" fix).
_MIN_FIELD_SPREAD_RATIO = 0.10
_FIELD_SUM_MIN = 0.70
_FIELD_SUM_MAX = 1.60


@dataclass(frozen=True)
class CyclingRaceConfig:
    """One EDITION of a race — always year-stamped. Derived, never hand-written."""

    slug: str
    display: str
    name_re: re.Pattern
    aliases: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class CyclingRaceFamily:
    """A race that recurs every year. Carries no year and never needs editing.

    #2482: this is the whole repair. The old config listed editions, so the
    calendar had a fuse in it; a family has none. ``stem`` and ``alias_stems``
    are year-less slug roots — every one of them resolves both bare
    (``tdf`` -> the edition in play) and year-stamped (``tdf-2027``)."""

    stem: str
    display: str  # year-less; the edition appends its year
    name_re: re.Pattern
    alias_stems: tuple[str, ...] = field(default_factory=tuple)


# The three Grand Tours. `name_re` matches the year-less market title
# ("Vuelta a Espana Winner"); the edition's year comes from the market's own
# `resolution_date`. Add a race here; never add a year.
CYCLING_RACE_FAMILIES: dict[str, CyclingRaceFamily] = {
    "tour-de-france": CyclingRaceFamily(
        stem="tour-de-france",
        display="Tour de France",
        name_re=re.compile(r"tour\s+de\s+france", re.IGNORECASE),
        alias_stems=("tdf", "le-tour"),
    ),
    "giro": CyclingRaceFamily(
        stem="giro",
        display="Giro d'Italia",
        name_re=re.compile(r"giro\s*(d[’']?\s*italia)?", re.IGNORECASE),
        alias_stems=("giro-ditalia",),
    ),
    "vuelta": CyclingRaceFamily(
        stem="vuelta",
        display="Vuelta a España",
        name_re=re.compile(r"vuelta(\s+a\s+espa)?", re.IGNORECASE),
        alias_stems=("vuelta-a-espana", "la-vuelta"),
    ),
}

# 🔴 THE STEMS ARE LOAD-BEARING, NOT COSMETIC. `app/config/majors_calendar.yaml`
# already declares `event:cycling:giro-2027` and `event:cycling:tour-de-france-2027`
# as expected concept surfaces, and `tasks/horizon_sentinel` page-checks each one
# against `GET /api/event/{concept_key}`. `edition_config` must therefore produce
# `giro-<year>` and `tour-de-france-<year>` — NOT the Competition Register's
# standing slugs (`giro-ditalia`, `vuelta-a-espana`), which name the competition
# rather than the edition. Measured pre-repair: both 2027 keys resolved to None,
# so the page 404'd and the sentinel would have escalated
# IN-PROGRESS-WITHOUT-PAGE (P0) in May 2027 for a page no data could produce.
# `test_cycling_rolling_editions.py` binds this by reading the yaml.

#: Year-less slug root -> family. Every stem and every alias stem.
_BY_STEM: dict[str, CyclingRaceFamily] = {}
for _fam in CYCLING_RACE_FAMILIES.values():
    _BY_STEM[_fam.stem] = _fam
    for _a in _fam.alias_stems:
        _BY_STEM.setdefault(_a, _fam)

#: A slug's trailing edition year, if it carries one. Anchored so the stem is
#: everything before it — `vuelta-a-espana-2027` splits at the LAST group.
_SLUG_EDITION_RE = re.compile(r"(?P<stem>.+?)-(?P<year>20\d{2})$")


@lru_cache(maxsize=256)
def edition_config(stem: str, year: int) -> CyclingRaceConfig | None:
    """The config for one edition of one family. Pure; memoized because the
    (family, year) space is tiny and every call site rebuilds the same handful.

    Bounded on purpose — the year is regex-constrained to `20\\d{2}`, so the
    space is 3 families x 100 years, but an explicit `maxsize` keeps this from
    being one more unbounded module-global on a hot path."""
    fam = CYCLING_RACE_FAMILIES.get(stem)
    if fam is None:
        return None
    return CyclingRaceConfig(
        slug=f"{fam.stem}-{year}",
        display=f"{fam.display} {year}",
        name_re=fam.name_re,
        aliases=tuple(f"{a}-{year}" for a in (fam.stem, *fam.alias_stems)),
    )


def parse_cycling_slug(
    slug: str, *, now: datetime | None = None
) -> CyclingRaceConfig | None:
    """Resolve a slug (canonical or alias, year-stamped or bare) to an edition.

    #2482: a year-stamped slug resolves to THAT edition for any year, so
    `/event/event:cycling:tour-de-france-2031` works the day Kalshi lists it. A
    BARE slug (`tdf`, `vuelta`) resolves to the edition currently in play — the
    calendar year of `now` — rather than to a frozen 2026. `now` is a test seam;
    production passes nothing."""
    if not slug:
        return None
    s = slug.strip().lower()
    m = _SLUG_EDITION_RE.fullmatch(s)
    stem, year = (m.group("stem"), int(m.group("year"))) if m else (s, None)
    if stem not in _BY_STEM:
        return None
    if year is None:
        year = (now or datetime.now(timezone.utc)).year
    return edition_config(_BY_STEM[stem].stem, year)


def _slug_year(slug: str) -> int | None:
    m = re.search(r"(20\d{2})", slug or "")
    return int(m.group(1)) if m else None


def is_gc_winner_field_market(name: str | None, race_re: re.Pattern | None = None) -> bool:
    """True for the overall GC winner field — a winner market for the race that is
    NOT a per-stage winner, NOT the team classification, and NOT a secondary jersey /
    points / mountains / young-rider classification (those are props, and one of them
    being fresher must never be crowned the GC leader)."""
    n = name or ""
    if race_re is not None and not race_re.search(n):
        return False
    if not _WINNER_RE.search(n):
        return False
    if _STAGE_RE.search(n) or _TEAM_RE.search(n):
        return False
    if _JERSEY_RE.search(n) or _NON_GC_RE.search(n):
        return False
    return True


def is_stage_market(name: str | None) -> bool:
    return bool(_STAGE_RE.search(name or ""))


def is_team_classification_market(name: str | None) -> bool:
    n = name or ""
    return bool(_TEAM_RE.search(n)) and not _STAGE_RE.search(n)


def is_cycling_jersey_prop(name: str | None) -> bool:
    """A secondary classification / jersey market (green/points, polka-dot/mountains,
    white/young-rider, most-aggressive) — surfaced as a prop child, never the GC."""
    n = name or ""
    return bool(_JERSEY_RE.search(n) or _NON_GC_RE.search(n))


def _stage_number(name: str | None) -> int:
    m = re.search(r"stage\s*(\d+)", name or "", re.IGNORECASE)
    return int(m.group(1)) if m else 9999


# --- Coherence gate (ported from event_soccer) ------------------------------
def _real_outcomes(m) -> list:
    from app.utils.outcome_display import is_field_outcome, is_placeholder_outcome_name

    return [
        o
        for o in (m.outcomes or [])
        if o.name
        and not is_field_outcome(o.name)
        and not is_placeholder_outcome_name(o.name)
        and o.current_probability is not None
    ]


def _field_has_real_spread(real: list) -> bool:
    probs = [float(o.current_probability) for o in real if o.current_probability is not None]
    if len(probs) < 2:
        return False
    mx, mn = max(probs), min(probs)
    if mx <= 0:
        return False
    return (mx - mn) / mx >= _MIN_FIELD_SPREAD_RATIO


def _field_is_coherent(real: list) -> bool:
    total = sum(float(o.current_probability) for o in real if o.current_probability is not None)
    return _FIELD_SUM_MIN <= total <= _FIELD_SUM_MAX


def _select_gc_field(candidates: list):
    """Pick the GC winner market. Among candidates whose real field has genuine spread
    AND a coherent ~100% sum, prefer the LARGEST real field (the GC is the whole
    peloton — 184 riders — vs a handful in any stray secondary market), tie-broken by
    freshness. Falls back to the richest real field if none pass the coherence gate
    (Kalshi 184-way independent binaries can sum past the coherence band, gotcha #23 —
    the real GC must never be dropped to an empty page for that). A field with <2 real
    outcomes never qualifies.

    #1177 settled-concept invariant: a graded market (authoritative is_winner rows)
    among the coherent candidates OVERRIDES the freshest/widest ungraded pick — a
    settled Grand Tour's crown must come from the graded winner market, not whichever
    field polled last. Returns (market, real_outcomes)."""
    best = None
    best_key = None  # (n_real, freshness)
    best_real: list = []
    fallback = None
    fallback_real: list = []
    coherent: list = []
    for m in candidates:
        real = _real_outcomes(m)
        if len(real) < 2:
            continue
        # Track a richest-real fallback regardless of gate.
        if len(real) > len(fallback_real):
            fallback, fallback_real = m, real
        if not _field_has_real_spread(real) or not _field_is_coherent(real):
            continue
        freshness = max(
            (o.last_updated for o in real if getattr(o, "last_updated", None) is not None),
            default=datetime.min.replace(tzinfo=timezone.utc),
        )
        coherent.append((m, real, freshness))
        key = (len(real), freshness)
        if best is None or key > best_key:
            best, best_key, best_real = m, key, real
    if best is not None:
        return prefer_graded_winner_field(best, best_real, coherent)
    return fallback, fallback_real


def concept_date_window(slug: str, resolution_date):
    """(start_iso, end_iso) for the concept envelope's date range.

    Queue #249 Item 4a: PREFER the majors-calendar entry (the real race window —
    TdF is Jul 4–26 2026) over the Kalshi GC market's ``resolution_date``, which is
    the market CLOSE/settle date (Aug 9), not the race window (gotcha #14). Without
    this the page header reads "Aug 9 – Aug 9". Falls back to the resolution_date
    (start == end) when no calendar entry exists. Pure + defensive."""
    res_iso = resolution_date.isoformat() if resolution_date is not None else None
    start_iso = end_iso = res_iso
    try:
        from app.utils.majors_calendar import (
            _as_utc_date,
            calendar_entry_by_concept_key,
        )

        entry = calendar_entry_by_concept_key().get(f"event:cycling:{slug}")
        if entry:
            s = _as_utc_date(entry.get("start"))
            e = _as_utc_date(entry.get("end"))
            if s is not None:
                start_iso = s.isoformat()
            if e is not None:
                end_iso = e.isoformat()
    except Exception:
        pass
    return start_iso, end_iso


def stage_graded_winner(outcomes) -> str | None:
    """Graded winner NAME for a cycling sub-market child (stage / classification),
    or None when unsettled. Queue #249 Item 4c — the golf by-round graded contract
    ported to cycling stages.

    ``is_winner`` is authoritative (Kalshi settled markets stay ``status='open'``,
    gotcha #33, so the grade — not status — is the settle signal). During the
    Kalshi grading lag a leader priced at/above ``_WON_PRICE_THRESHOLD`` is a
    display-only crown (L2-83 parity; gotcha #21 — never authoritative). Expects an
    already field/placeholder-filtered outcome list. Pure — unit-tested."""
    real = [o for o in (outcomes or []) if getattr(o, "name", None)]
    for o in real:
        if bool(getattr(o, "is_winner", False)):
            return o.name
    priced = [o for o in real if getattr(o, "current_probability", None) is not None]
    if priced:
        top = max(priced, key=lambda o: float(o.current_probability))
        if float(top.current_probability) >= _WON_PRICE_THRESHOLD:
            return top.name
    return None


def cycling_status(status: str | None, resolution_date, now) -> str:
    """upcoming / live / settled. A Grand Tour runs ~3 weeks, so the 'live' window is
    wide: within 25 days before resolution_date (Kalshi resolution is race-end/close;
    gotcha #14) counts as in progress."""
    if (status or "").lower() in ("resolved", "closed", "settled", "final"):
        return "settled"
    if resolution_date is not None:
        try:
            if resolution_date < now:
                return "settled"
            days = (resolution_date - now).total_seconds() / 86400
            if days <= 25:  # a 3-week grand tour is "in progress"
                return "live"
        except TypeError:
            pass
    return "upcoming"


def derive_cycling_concept(
    external_id: str | None,
    name: str | None,
    llm_sport_category: str | None,
    *,
    now: datetime | None = None,
) -> dict | None:
    """Discovery-entry helper for search wiring: map a cycling GC-winner market to
    its concept. Returns {key, name, domain} or None.

    #2482: a market TITLE carries no year ("Tour de France Winner"), so the only
    honest edition to name from a name alone is the one in play — the calendar
    year of `now`. It used to name a hardcoded 2026 forever, which up-linked every
    future search hit to a dead concept page. `now` is a test seam.

    FOLLOW-UP `CYCLING-UPLINK-USE-RESOLUTION-DATE`: both call sites
    (`routes/events.py` search, `concept_links.market_concept_key`) hold the whole
    market row and could pass its `resolution_date` instead, which would also be
    right for a market listed in one year and resolving in the next. Deliberately
    not done here — it widens the diff onto a route file for an edge the rolling
    year already handles in the common case."""
    if (llm_sport_category or "").lower() != "cycling":
        return None
    n = name or ""
    year = (now or datetime.now(timezone.utc)).year
    for fam in CYCLING_RACE_FAMILIES.values():
        if fam.name_re.search(n) and is_gc_winner_field_market(n, fam.name_re):
            cfg = edition_config(fam.stem, year)
            if cfg is None:  # unreachable; the stem came from the registry
                return None
            return {"key": f"event:cycling:{cfg.slug}", "name": cfg.display, "domain": "cycling"}
    return None


async def list_cycling_concepts(
    db: AsyncSession,
    *,
    statuses: tuple[str, ...] = ("upcoming", "live"),
    limit: int = 10,
    rows: list | None = None,
) -> list[dict]:
    """Enumerate cycling Grand-Tour concepts for the sports feed (the winner-field
    analogue of list_f1_gp_concepts). Returns lightweight dicts the feed scorer turns
    into concept cards linking to /event/{key}. Read-only, best-effort.

    `rows` is LAT-P094's accelerator — the concept tier reads every source's open
    markets in one scan instead of one per source; see
    `event_concept_population.prefetch_open_markets`. Passing nothing keeps the
    standalone read."""
    from app.utils.event_concept_population import (
        CYCLING_PROJECTION,
        select_open_markets,
    )

    now = datetime.now(timezone.utc)
    if rows is None:
        rows = await select_open_markets(db, "cycling", CYCLING_PROJECTION)

    per_race: dict[str, dict] = {}
    for name, status, res in rows:
        for fam in CYCLING_RACE_FAMILIES.values():
            if not fam.name_re.search(name or ""):
                continue
            # #2482 — THE REPAIR. The edition used to be looked UP in a
            # hand-written per-year config, and a market whose resolution year had
            # no entry was silently dropped. It is now DERIVED from the market's
            # own resolution year, so grouping is still strictly per edition (a
            # 2027 market never joins the 2026 card) but no year can be missing.
            # A date-less market falls to the current year, which is what the old
            # code did with it too — it bypassed the guard entirely.
            cfg = edition_config(fam.stem, res.year if res is not None else now.year)
            if cfg is None:  # unreachable; the stem came from the registry
                break
            g = per_race.setdefault(
                cfg.slug, {"cfg": cfg, "markets": 0, "resolution": res, "status": status}
            )
            g["markets"] += 1
            if res is not None and (g["resolution"] is None or res < g["resolution"]):
                g["resolution"] = res
            break

    concepts: list[dict] = []
    for slug, g in per_race.items():
        cfg = g["cfg"]
        res = g["resolution"]
        status = cycling_status(g["status"], res, now)
        if status not in statuses:
            continue
        concepts.append(
            {
                "key": f"event:cycling:{slug}",
                "name": cfg.display,
                "domain": "cycling",
                "status": status,
                "start_date": res.isoformat() if res is not None else None,
                "is_major": True,  # Grand Tours are majors
                "entry_count": g["markets"],
                "latest_commence": res,
            }
        )
    concepts.sort(
        key=lambda x: (x["latest_commence"] or datetime.max.replace(tzinfo=timezone.utc))
    )
    return concepts[:limit]


class CyclingEventAdapter:
    domain = "cycling"

    async def build_event(self, slug: str, db: AsyncSession) -> dict | None:
        from app.models import FuturesMarket
        from app.utils.outcome_display import (
            is_field_outcome,
            is_placeholder_outcome_name,
            normalize_display_probs,
        )

        cfg = parse_cycling_slug(slug)
        if cfg is None:
            return None
        now = datetime.now(timezone.utc)
        slug_year = _slug_year(cfg.slug)

        q = (
            select(FuturesMarket)
            .options(selectinload(FuturesMarket.outcomes))
            .where(
                FuturesMarket.llm_sport_category == "cycling",
                FuturesMarket.status == "open",
            )
        )
        all_markets = list((await db.execute(q)).scalars().unique().all())

        # Filter to this race + edition.
        markets = []
        for m in all_markets:
            if not cfg.name_re.search(m.name or ""):
                continue
            if (
                slug_year is not None
                and m.resolution_date is not None
                and m.resolution_date.year != slug_year
            ):
                continue
            markets.append(m)
        if not markets:
            return None

        gc_candidates = [m for m in markets if is_gc_winner_field_market(m.name, cfg.name_re)]
        # #1177: also consider RESOLVED/CLOSED GC winner markets. On settlement the
        # poly/kalshi GC market flips off status='open' while carrying the graded
        # is_winner rows, so an open-only scan sees only the ungraded field and the
        # settled crown would depend on which field polled last. The edition guard
        # (slug_year vs resolution_date, null-date allowed) keeps prior-edition GC
        # markets out. Children (stages/props) stay open-only below.
        graded_q = (
            select(FuturesMarket)
            .options(selectinload(FuturesMarket.outcomes))
            .where(
                FuturesMarket.llm_sport_category == "cycling",
                FuturesMarket.status.in_(["resolved", "closed", "settled"]),
            )
        )
        seen_ids = {m.id for m in gc_candidates}
        for m in (await db.execute(graded_q)).scalars().unique().all():
            if m.id in seen_ids or not cfg.name_re.search(m.name or ""):
                continue
            if (
                slug_year is not None
                and m.resolution_date is not None
                and m.resolution_date.year != slug_year
            ):
                continue
            if is_gc_winner_field_market(m.name, cfg.name_re):
                gc_candidates.append(m)
        winner, real_outcomes = _select_gc_field(gc_candidates)
        if winner is None:
            return None

        event_status = cycling_status(winner.status, winner.resolution_date, now)

        competitors = []
        for o in real_outcomes:
            competitors.append(
                {
                    "name": o.name,
                    "probability": (
                        round(float(o.current_probability), 4)
                        if o.current_probability is not None
                        else None
                    ),
                    "won": bool(getattr(o, "is_winner", False)),
                }
            )
        # Crown the price-settled GC winner during the grading-lag window (read RAW
        # price before normalize dilutes a dominant leader). Display-only (gotcha #21).
        if event_status == "settled" and not any(c["won"] for c in competitors):
            top = max(competitors, key=lambda c: (c["probability"] or -1), default=None)
            if top is not None and (top["probability"] or 0) >= _WON_PRICE_THRESHOLD:
                top["won"] = True

        # Normalize ONLY a coherent (~mutually-exclusive) field. A Kalshi grand-tour
        # GC market lists 184 riders as INDEPENDENT YES/NO binaries whose YES prices
        # sum to ~2.8x (heavy overround, gotcha #23); normalizing that would dilute a
        # near-lock favorite (Pogačar 94.5% -> a false 34%). When the raw field sums
        # far past 100% the raw YES price IS the honest per-rider win probability —
        # keep it (Alex: "the blend is the product — one number per question").
        _raw_sum = sum(c["probability"] for c in competitors if c["probability"] is not None)
        if _raw_sum <= _FIELD_SUM_MAX:
            normalize_display_probs(competitors)
        competitors.sort(key=lambda c: (c["probability"] or -1), reverse=True)

        # Children = stages (in order), team classification, jersey props.
        def _child(m, prop_type):
            outs = sorted(
                (m.outcomes or []),
                key=lambda o: float(o.current_probability or 0),
                reverse=True,
            )
            outs = [
                o
                for o in outs
                if o.name
                and not is_field_outcome(o.name)
                and not is_placeholder_outcome_name(o.name)
            ]
            lead = outs[0] if outs else None
            lead_prob = (
                float(lead.current_probability)
                if lead and lead.current_probability is not None
                else None
            )
            # #249 Item 4c: emit the graded contract so the frontend can render a
            # settled stage/classification as WHAT HIT (the golf by-round pattern).
            graded = stage_graded_winner(outs)
            # #1803, same class as golf's round ceiling and combat's price test:
            # a stage's own grade is the ONLY settled signal here, so a concluded
            # grand tour carrying one ungraded stage renders that stage live
            # forever. `or`, never a replacement — the race's assigned status can
            # only add settledness, so a stage mid-race decides exactly as before.
            #
            # UX-P069 (Alex item 4c): this was the one leg fixed by a TRANSCRIBED
            # expression rather than a shared path, and its test transcribed it
            # too — so only an `inspect.getsource` assert bound the source. It now
            # calls `settled_under_assigned_state`, the same authority the other
            # four adapters use. `cycling_status` is a genuinely ASSIGNED term
            # (source status + resolution date), not a second price test.
            #
            # LATENT, NOT MEASURED, and recorded as such: every settled cycling
            # concept 404s in production today (`tour-de-france-2026`, `giro-2026`
            # both 404 on v3792), so unlike golf and combat this leg has no
            # production specimen and is proven by unit test only. It is fixed here
            # rather than filed because the Vuelta concludes 2026-09-13 and makes
            # it reachable — a dated fuse on a one-line guard is not worth a ticket.
            return {
                "market_id": m.id,
                "market_name": m.name,
                "kind": "prop",
                "prop_type": prop_type,
                "source": m.source,  # data-only (audit); not rendered
                "probability": round(lead_prob, 4) if lead_prob is not None else None,
                "settled": settled_under_assigned_state(
                    inferred=graded is not None,
                    assigned_settled=event_status == "settled",
                ),
                "graded_winner": graded,
                "outcomes": [
                    {
                        "name": o.name,
                        "probability": (
                            round(float(o.current_probability), 4)
                            if o.current_probability is not None
                            else None
                        ),
                    }
                    for o in outs[:4]
                ],
            }

        stage_markets = sorted(
            [m for m in markets if m.id != winner.id and is_stage_market(m.name)],
            key=lambda m: _stage_number(m.name),
        )
        team_markets = [
            m
            for m in markets
            if m.id != winner.id and is_team_classification_market(m.name)
        ]
        jersey_markets = [
            m for m in markets if m.id != winner.id and is_cycling_jersey_prop(m.name)
        ]

        children, stage_ids, class_ids = [], [], []
        for m in stage_markets:
            children.append(_child(m, "stage"))
            stage_ids.append(m.id)
        for m in team_markets:
            children.append(_child(m, "team"))
            class_ids.append(m.id)
        for m in jersey_markets:
            children.append(_child(m, "jersey"))
            class_ids.append(m.id)

        sections = [
            {"type": "winner", "label": "General Classification", "market_ids": [winner.id]}
        ]
        if stage_ids:
            sections.append({"type": "prop", "label": "Stages", "market_ids": stage_ids})
        if class_ids:
            sections.append(
                {"type": "prop", "label": "Classifications & jerseys", "market_ids": class_ids}
            )

        # #249 Item 4a: the envelope date range comes from the majors calendar (the
        # real race window, Jul 4–26) when present, NOT the Kalshi GC resolution/
        # close date (Aug 9 — gotcha #14, which made the header read "Aug 9 – Aug 9").
        start_iso, end_iso = concept_date_window(cfg.slug, winner.resolution_date)
        envelope = {
            "event": {
                "key": f"event:cycling:{cfg.slug}",
                "domain": "cycling",
                "name": cfg.display,
                "status": event_status,
                "start_date": start_iso,
                "end_date": end_iso,
                "venue": None,
                "location": None,
                "is_major": True,
            },
            "primary": {
                "kind": "winner_field",
                "label": "General Classification",
                "competitors": competitors,
                "evolution_market_id": winner.id,
            },
            "sections": sections,
            "children": children,
            "movers": [],
        }

        # Shared per-competitor history (one fetch); best-effort.
        # #249 Item 4b: a Grand Tour's GC futures opens weeks out AND its near-static
        # field is collapsed to one keeper per rider by snapshot retention, so the
        # default 7-day window misses the surviving keeper entirely (empty chart).
        # Use a wide race-length window so the keeper is in range, and pass
        # extend_to_now so a single collapsed keeper still draws an honest flat line.
        try:
            from app.utils.event_concept import attach_competitor_history

            await attach_competitor_history(
                db, winner.id, competitors, hours=2160, extend_to_now=now
            )
        except Exception:
            pass

        return envelope
