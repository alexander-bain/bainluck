"""Awards-ceremony adapter for the Event Concept framework — L2-87 (B6).

An awards ceremony (Oscars / Emmys / Grammys / Tonys) IS an event concept whose
children are N CO-EQUAL category winners (Best Picture, Best Director, …) with no
single "overall winner" — design §6. It fits the SAME event-group primitive as a
UFC card (`primary.kind == "co_equal_list"`): the difference is the co-equal list
is CATEGORIES (each a multi-nominee market), not two-sided fights.

Data reality (verified live 2026-07-12): every award category is its own Kalshi
market whose ticker encodes ceremony + category + edition, e.g.
``KXOSCARPIC-27`` (Best Picture, 2027 Oscars, 34 nominee outcomes),
``KXEMMYDSERIES-26SEP14`` (Outstanding Drama Series, 2026 Emmys),
``KXTONYAWARDS-26BM`` (Best Musical), ``KXGRAMAOTY`` (Album of the Year).
Nomination markets (``KXOSCARNOM*``, ``KXEMMYNOMS*``, ``KXGRAMMYNOM*``) and
novelty markets ("Who will attend the Oscars?") ride along as props.

The adapter is a small per-ceremony config over generic, unit-tested helpers plus a
`build_event` that emits the same envelope the /event page already renders — so
categories render as co-equal children (MatchupsRail) with a nominations/props
section (EventProps) and NO frontend change. The marquee category (Best Picture /
Drama Series / Album of the Year / Best Musical) becomes the head-to-head hero
(TwoSidedTimeline), mirroring a card's "main event".

Honest v1 limitations (design §6 said "fast-follow", so this is deliberately thin):
  * Award resolution dates on Kalshi are placeholders (Dec 31), so event status is
    approximate — a graded winner or a price-settled leader flips it to "settled",
    otherwise "upcoming". This only toggles the settled path chart.
  * MatchupsRail shows the top-2 nominees per category (no "+N more"); a 10-nominee
    Best Picture shows its two frontrunners. A richer awards section is a later,
    additive frontend change.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

# Raw price at/above which a SETTLED marquee nominee is the crowned winner during
# the is_winner grading-lag window (parity with tennis/f1 — display-only, never
# authoritative, gotcha #21).
_WON_PRICE_THRESHOLD = 0.97

# A category winner market names an award category. Nomination + novelty markets
# are excluded from this by the checks in `classify_market`.
_CATEGORY_NAME_RE = re.compile(
    r"\bbest\b|\baward for\b|\bwinner\b|\boutstanding\b", re.IGNORECASE
)

# Leading boilerplate stripped so a category card reads "Best Picture", not
# "Oscar winner: Best Picture". Applied in order; a leading edition year is
# stripped first.
_CATEGORY_STRIP = [
    re.compile(r"^\d{4}\s+", re.IGNORECASE),
    re.compile(r"^oscar winner:\s*", re.IGNORECASE),
    re.compile(r"^oscar (?:nominations for|nominees:)\s*", re.IGNORECASE),
    re.compile(r"^oscar for\s*", re.IGNORECASE),
    re.compile(r"^emmy award for\s*", re.IGNORECASE),
    re.compile(r"^emmy nominations:\s*", re.IGNORECASE),
    re.compile(r"^grammy winner:\s*", re.IGNORECASE),
    re.compile(r"^grammy (?:nominations for)\s*", re.IGNORECASE),
    re.compile(r"^tony award for\s*", re.IGNORECASE),
]


@dataclass(frozen=True)
class AwardsCeremonyConfig:
    """Everything that distinguishes one awards ceremony from another."""

    slug: str  # canonical URL slug, e.g. "oscars"
    display: str  # human ceremony name, e.g. "The Oscars"
    ticker: str  # Kalshi ticker stem matched (substring) in external_id, e.g. "KXOSCAR"
    marquee_re: re.Pattern  # matches the marquee category NAME (Best Picture, …)
    aliases: tuple[str, ...] = field(default_factory=tuple)  # extra slug spellings


CEREMONIES: dict[str, AwardsCeremonyConfig] = {
    "oscars": AwardsCeremonyConfig(
        slug="oscars",
        display="The Oscars",
        ticker="KXOSCAR",
        marquee_re=re.compile(r"best picture", re.IGNORECASE),
        aliases=("oscar", "academy-awards", "academy-award", "the-oscars"),
    ),
    "emmys": AwardsCeremonyConfig(
        slug="emmys",
        display="The Emmys",
        ticker="KXEMMY",  # excludes KXSPORTSEMMY (different ceremony) — not a substring
        marquee_re=re.compile(r"drama series", re.IGNORECASE),
        aliases=("emmy", "the-emmys"),
    ),
    "grammys": AwardsCeremonyConfig(
        slug="grammys",
        display="The Grammys",
        ticker="KXGRAM",
        marquee_re=re.compile(r"album of the year", re.IGNORECASE),
        aliases=("grammy", "the-grammys"),
    ),
    "tonys": AwardsCeremonyConfig(
        slug="tonys",
        display="The Tony Awards",
        ticker="KXTONYAWARDS",
        marquee_re=re.compile(r"best musical", re.IGNORECASE),
        aliases=("tony", "tony-awards", "the-tonys"),
    ),
}

# slug (canonical + alias) -> config, built once.
_BY_SLUG: dict[str, AwardsCeremonyConfig] = {}
for _cfg in CEREMONIES.values():
    _BY_SLUG[_cfg.slug] = _cfg
    for _a in _cfg.aliases:
        _BY_SLUG[_a] = _cfg


# ---------------------------------------------------------------------------
# Pure helpers — unit-tested.
# ---------------------------------------------------------------------------


def parse_awards_slug(slug: str) -> tuple[AwardsCeremonyConfig | None, int | None]:
    """Parse an awards slug into (ceremony_config, edition_year_2digit | None).

    "oscars" -> (oscars, None); "oscars-2027" -> (oscars, 27);
    "oscars-27" -> (oscars, 27); "academy-awards-2027" -> (oscars, 27)."""
    s = (slug or "").strip().lower()
    if not s:
        return None, None
    year: int | None = None
    m = re.search(r"-(20\d\d|\d{2})$", s)
    if m:
        raw = m.group(1)
        year = int(raw) % 100
        s = s[: m.start()]
    cfg = _BY_SLUG.get(s)
    return cfg, year


def edition_year(external_id: str | None, resolution_date=None) -> int | None:
    """The 2-digit ceremony edition year for a market.

    The Kalshi ticker carries it as the first ``-NN`` group
    (``KXOSCARPIC-27`` -> 27; ``KXEMMYDSERIES-26SEP14`` -> 26;
    ``KXEMMYNOMS-26-DS`` -> 26). A 2-digit token is only accepted as an edition
    year when it's PLAUSIBLE (2020s–2040s) — Grammy tickers end in a Kalshi series
    id (``KXGRAMAOTY-69``), not a year, so an implausible token falls through to
    the resolution date's year (2027) instead of yielding "The Grammys 2069"."""
    m = re.search(r"-(\d{2})(?!\d)", external_id or "")
    if m:
        yr = int(m.group(1))
        if 20 <= yr <= 45:  # a real ceremony edition year, not a series id
            return yr
    if resolution_date is not None:
        try:
            return resolution_date.year % 100
        except (AttributeError, TypeError):
            return None
    return None


def classify_market(external_id: str | None, name: str | None) -> str:
    """Classify an award market: "category" (a co-equal winner category),
    "nominations" (who gets nominated), or "novelty" (attendance/most-wins/etc.).

    Nominations win first (ticker "NOM" or name says nomination/nominee); then a
    real award category by name; anything else is a novelty prop."""
    eid = (external_id or "").upper()
    n = (name or "").lower()
    if "NOM" in eid or "nomination" in n or "nominee" in n:
        return "nominations"
    if _CATEGORY_NAME_RE.search(name or ""):
        return "category"
    return "novelty"


def clean_category_label(name: str | None) -> str:
    """Strip ceremony boilerplate so a card reads the bare category.

    "Oscar winner: Best Picture" -> "Best Picture";
    "Emmy Award for Drama Series" -> "Drama Series";
    "2026 Oscar for Best Music (Original Score)?" -> "Best Music (Original Score)"."""
    s = (name or "").strip()
    if not s:
        return name or ""
    s = s.rstrip("?").strip()
    for pat in _CATEGORY_STRIP:
        new = pat.sub("", s).strip()
        if new != s:
            s = new
    return s or (name or "")


class AwardsEventAdapter:
    """Event-concept adapter for awards ceremonies (co_equal_list). Resolves
    ``event:awards:<ceremony>[-<year>]`` into the generic envelope, grouping the
    ceremony's category markets by edition and rendering them as co-equal children
    plus a nominations/props section."""

    domain = "awards"

    async def build_event(self, slug: str, db: AsyncSession) -> dict | None:
        from datetime import datetime, timezone

        from app.models import FuturesMarket
        from app.utils.outcome_display import (
            is_field_outcome,
            is_placeholder_outcome_name,
            normalize_display_probs,
        )

        cfg, want_year = parse_awards_slug(slug)
        if cfg is None:
            return None

        now = datetime.now(timezone.utc)

        # All of this ceremony's markets. The KX ticker stem is unambiguous, so
        # match on it directly (no llm_sport_category filter needed) — this also
        # catches any mis-categorized ones.
        q = (
            select(FuturesMarket)
            .options(selectinload(FuturesMarket.outcomes))
            .where(
                FuturesMarket.status == "open",
                FuturesMarket.external_id.ilike(f"%{cfg.ticker}%"),
            )
        )
        markets = list((await db.execute(q)).scalars().unique().all())
        if not markets:
            return None

        def _real_count(m) -> int:
            return sum(
                1
                for o in (m.outcomes or [])
                if o.name
                and not is_field_outcome(o.name)
                and not is_placeholder_outcome_name(o.name)
            )

        # Classify + tag each market with its edition year.
        tagged = []
        for m in markets:
            # Defensive: a foreign ticker that happens to contain the stem but
            # isn't this ceremony (none known today) still classifies harmlessly.
            kind = classify_market(m.external_id, m.name)
            yr = edition_year(m.external_id, getattr(m, "resolution_date", None))
            tagged.append((m, kind, yr))

        winner_cats_all = [t for t in tagged if t[1] == "category" and _real_count(t[0]) >= 2]
        if not winner_cats_all:
            return None

        # Pick the edition. If the slug named a year, use it. Otherwise prefer the
        # LATEST edition that has a real field (>=3 winner categories); if none does,
        # fall back to the latest edition present (honest gap for thin ceremonies).
        years_present = sorted(
            {t[2] for t in winner_cats_all if t[2] is not None}, reverse=True
        )
        chosen_year: int | None
        if want_year is not None:
            chosen_year = want_year
        else:
            rich = [
                y
                for y in years_present
                if sum(1 for t in winner_cats_all if t[2] == y) >= 3
            ]
            chosen_year = (rich or years_present or [None])[0]

        def _in_edition(t) -> bool:
            # When no edition year could be parsed for a ceremony (e.g. Grammys via
            # a null resolution date), don't filter it out.
            return chosen_year is None or t[2] == chosen_year or t[2] is None

        winner_cats = [t[0] for t in winner_cats_all if _in_edition(t)]
        if not winner_cats:
            return None

        nominations = [t[0] for t in tagged if t[1] == "nominations" and _in_edition(t)]
        novelties = [t[0] for t in tagged if t[1] == "novelty" and _in_edition(t)]

        # Marquee = the ceremony's headline category (Best Picture, …); else the
        # richest field. It becomes the head-to-head hero AND stays in the category
        # rail (parity with a card's main event).
        marquee = next(
            (m for m in winner_cats if cfg.marquee_re.search(m.name or "")), None
        )
        if marquee is None:
            marquee = max(winner_cats, key=_real_count)

        def _outcomes(m, limit=8):
            outs = sorted(
                (m.outcomes or []),
                key=lambda o: float(o.current_probability or 0),
                reverse=True,
            )
            real = [
                o
                for o in outs
                if o.name
                and not is_field_outcome(o.name)
                and not is_placeholder_outcome_name(o.name)
            ]
            return real[:limit]

        # Marquee competitors (the hero head-to-head + settled crown).
        competitors = []
        for o in _outcomes(marquee, limit=40):
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

        # Event status (approximate — Kalshi award dates are placeholders). Settled
        # if a nominee is graded, the marquee leader is price-settled, or the
        # resolution date is genuinely in the past.
        marquee_top = max((c["probability"] or -1) for c in competitors) if competitors else -1
        marquee_res = getattr(marquee, "resolution_date", None)
        event_status = "upcoming"
        if any(c["won"] for c in competitors):
            event_status = "settled"
        elif marquee_res is not None:
            try:
                if marquee_res < now:
                    event_status = "settled"
            except TypeError:
                pass
        if event_status != "settled" and marquee_top >= _WON_PRICE_THRESHOLD:
            event_status = "settled"

        # Crown the price-settled marquee leader during the grading-lag window
        # (read the RAW price before normalize dilutes it — parity with tennis/f1).
        if event_status == "settled" and not any(c["won"] for c in competitors):
            top = max(competitors, key=lambda c: (c["probability"] or -1), default=None)
            if top is not None and (top["probability"] or 0) >= _WON_PRICE_THRESHOLD:
                top["won"] = True

        normalize_display_probs(competitors)
        competitors.sort(key=lambda c: (c["probability"] or -1), reverse=True)

        def _child(m, *, kind=None, prop_type=None):
            outs = _outcomes(m)
            lead_prob = (
                round(float(outs[0].current_probability), 4)
                if outs and outs[0].current_probability is not None
                else None
            )
            settled = lead_prob is not None and (lead_prob >= 0.97 or lead_prob <= 0.03)
            row = {
                "market_id": m.id,
                "market_name": clean_category_label(m.name),
                "source": m.source,  # data-only (audit); not rendered
                "settled": settled,
                "probability": lead_prob,
                "outcomes": [
                    {
                        "name": o.name,
                        "probability": (
                            round(float(o.current_probability), 4)
                            if o.current_probability is not None
                            else None
                        ),
                    }
                    for o in outs
                ],
            }
            if kind:
                row["kind"] = kind
            if prop_type:
                row["prop_type"] = prop_type
            return row

        # Children: every winner category (co-equal list) + nominations + novelties
        # as props. Categories sort by leader probability (most-decided first reads
        # like a real ballot); marquee floats to the front.
        cat_children = [_child(m) for m in winner_cats]
        cat_children.sort(
            key=lambda c: (c["market_id"] != marquee.id, -(c["probability"] or 0))
        )
        nom_children = [_child(m, kind="prop", prop_type="nominations") for m in nominations]
        nov_children = [_child(m, kind="prop", prop_type="occurrence") for m in novelties]
        children = cat_children + nom_children + nov_children

        sections = [
            {
                "type": "categories",
                "label": "Categories",
                "market_ids": [c["market_id"] for c in cat_children],
            }
        ]
        prop_ids = [c["market_id"] for c in nom_children + nov_children]
        if prop_ids:
            sections.append({"type": "props", "label": "Nominations & props", "market_ids": prop_ids})

        year_suffix = f"-20{chosen_year:02d}" if chosen_year is not None else ""
        return {
            "event": {
                "key": f"event:awards:{cfg.slug}{year_suffix}",
                "domain": "awards",
                "name": (
                    f"{cfg.display} 20{chosen_year:02d}"
                    if chosen_year is not None
                    else cfg.display
                ),
                "status": event_status,
                "start_date": None,
                "end_date": (marquee_res.isoformat() if marquee_res is not None else None),
                "venue": None,
                "location": None,
                "is_major": True,  # award ceremonies are marquee cultural events
            },
            "primary": {
                "kind": "co_equal_list",
                "label": clean_category_label(marquee.name),
                "competitors": competitors,
                "evolution_market_id": marquee.id,
            },
            "sections": sections,
            "children": children,
            "movers": [],
        }
