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
  * Category completion is independent: only that category's assigned status or
    authoritative outcome grade settles it. The adapter has no authoritative
    full-ceremony completion signal, so the parent phase stays unknown. Prices
    and resolution deadlines never announce a result or complete the ceremony.
    The placeholder is NEVER published as the ceremony date (`ceremony_end_date`).
  * A result is announced only by an independent settlement: the venue's own
    settled answer, never a grade inferred from the market's price, the clock or a
    guess (`is_result_grade`). Each child serves its `result` (state, the kind of
    evidence and the settling venue) so a withheld price crown, a retracted grade
    and plain silence are not one state (#5349). The organizer's own winners list
    is not read here; a venue settlement is labelled as one.
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

from app.utils.futures_market_snapshot import concept_price_observed_at_iso

from app.utils.resolution_authority import PRICE_DERIVED_SOURCES, is_authoritative
from app.utils.settledness import (
    market_assigned_settled,
    settled_under_assigned_state,
)
from app.utils.settlement_display import RETRACTED_SOURCE

# Day-of-year on which a Kalshi award market resolves when the ceremony has no
# published date: the exchange's end-of-year backstop, not a schedule (gotcha #14)
# or a ceremony-completion signal.
_PLACEHOLDER_RESOLUTION_DAY = (12, 31)

# #5349: a category's served `result`. The values are contract strings read by
# tests and later readers, so they are named once here.
RESULT_ANNOUNCED = "announced"  # an independent settlement names its winner(s)
RESULT_CLOSED = "closed"  # its own assigned state is settled; no result evidence
RESULT_PENDING = "pending"  # still open; no result evidence
EVIDENCE_VENUE_SETTLEMENT = "venue_settlement"
EVIDENCE_UNCONFIRMED_GRADE = "unconfirmed_grade"  # a winner flag we do not count
EVIDENCE_RETRACTED_GRADE = "retracted_grade"  # grades withdrawn as unknowable
EVIDENCE_NONE = "none"


# Known settling venues for each independent authoritative resolution_source.
# A listing provider on `market.source` (or a provider that disagrees with the
# settlement source) is never presented as the settling authority (#5349).
_SETTLING_VENUES_BY_RESOLUTION_SOURCE: dict[str, frozenset[str]] = {
    "api_settlement": frozenset({"kalshi", "polymarket"}),
    "clob_authoritative": frozenset({"polymarket"}),
    "clob_field_repair": frozenset({"polymarket"}),
    "clob_never_graded": frozenset({"polymarket"}),
    "clob_ordinal": frozenset({"polymarket"}),
}


def _has_outcome_name(outcome) -> bool:
    """True when `outcome.name` is a non-blank string a reader can display."""
    name = getattr(outcome, "name", None)
    return isinstance(name, str) and bool(name.strip())


def is_result_grade(outcome) -> bool:
    """True when this outcome's stored grade may name an award result (#5349).

    Only an independent settlement on a named outcome qualifies: the venue's own
    settled answer (`resolution_authority.is_authoritative`, tier 3) that was not
    inferred from the market's own price (`PRICE_DERIVED_SOURCES`). A price crown
    (`clean_resolution`), a clock rule (`date_passed`), a guess, a retraction, a
    missing source, or a missing/blank outcome name is a stored flag, not an
    announcement. A row missing any required attribute fails closed."""
    if not _has_outcome_name(outcome):
        return False
    if not bool(getattr(outcome, "is_winner", False)):
        return False
    source = getattr(outcome, "resolution_source", None)
    return is_authoritative(source) and source not in PRICE_DERIVED_SOURCES


def _settling_venue(market, result_outcomes) -> str | None:
    """Return the verified settling venue, or None when provenance is uncertain.

    A listing provider on `market.source` must not be presented as the settling
    authority unless every qualifying result grade's `resolution_source` belongs
    to that venue's independent settlement channel."""
    raw = getattr(market, "source", None)
    if not isinstance(raw, str) or not raw.strip():
        return None
    venue = raw.strip().lower()
    for o in result_outcomes:
        res_source = getattr(o, "resolution_source", None)
        allowed = _SETTLING_VENUES_BY_RESOLUTION_SOURCE.get(res_source, frozenset())
        if venue not in allowed:
            return None
    return venue


def category_result(market, *, settled: bool) -> dict:
    """The served `result` of one award category or prop market (#5349).

    `announced` when at least one of its own named outcomes carries a result
    grade, and then `venue` names the settling venue when verified (or None when
    uncertain). Otherwise `closed` when its own assigned state is settled, else
    `pending`, naming the evidence that exists without counting it. Reads only
    this market's own rows: never a sibling, the ceremony, a price or a date."""
    rows = getattr(market, "outcomes", None) or []
    result_rows = [o for o in rows if is_result_grade(o)]
    if result_rows:
        return {
            "state": RESULT_ANNOUNCED,
            "evidence_kind": EVIDENCE_VENUE_SETTLEMENT,
            "venue": _settling_venue(market, result_rows),
        }
    if any(bool(getattr(o, "is_winner", False)) for o in rows):
        evidence = EVIDENCE_UNCONFIRMED_GRADE
    elif any(getattr(o, "resolution_source", None) == RETRACTED_SOURCE for o in rows):
        evidence = EVIDENCE_RETRACTED_GRADE
    else:
        evidence = EVIDENCE_NONE
    return {
        "state": RESULT_CLOSED if settled else RESULT_PENDING,
        "evidence_kind": evidence,
        "venue": None,
    }

# A category winner market names an award category. Nomination + novelty markets
# are excluded from this by the checks in `classify_market`.
_CATEGORY_NAME_RE = re.compile(
    r"\bbest\b|\baward for\b|\bwinner\b|\boutstanding\b", re.IGNORECASE
)

# A question asking whether someone GETS nominated ("Will X be nominated for Best
# Actress?") is a nomination market even though it names a "Best" category (#11336).
# Verb-phrase only: an adjectival "a nominated film" / "most-nominated" or a post-noun
# "a film nominated for X" in a winner question stays a winner category, so a bare
# "nominated for" counts only when it opens the title. \b keeps "denominated" out.
_NOMINATED_RE = re.compile(
    r"\b(?:be|get|gets|got|is|are)\s+(?:[a-z]+-)?nominated\b|^\s*nominated\s+for\b",
    re.IGNORECASE,
)
# The same verb phrase inside a "that/which" relative clause describes a noun ("a film
# that is nominated for 10+ Oscars win Best Picture?"), so it is removed before the check.
_RELATIVE_NOMINATED_RE = re.compile(
    r"\b(?:that|which)\s+(?:be|get|gets|got|is|are)\s+(?:[a-z]+-)?nominated\b",
    re.IGNORECASE,
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


def ceremony_end_date(resolution_date) -> str | None:
    """The ceremony date to publish for an awards concept, or None when the only
    date we hold is the exchange's year-end backstop.

    A market's resolution date is a deadline, not a schedule, and for awards it is
    usually the former: measured on production 2026-09-01, the marquee markets for
    the Oscars 2027, the Grammys 2027 and the Tonys 2026 all carry the SAME instant
    (12-31T15:00:00Z), while the Emmys — a ceremony with a genuinely published date
    — carry 09-14T14:00:00Z. Three unrelated ceremonies sharing one instant is a
    default, not a date, so December 31 is never published as a ceremony date.

    Publishing it is not a harmless approximation: the awards header renders this
    field verbatim as the event's date, so the backstop reached readers as a flat
    "Dec 31" on three of the four award pages. Returning None renders nothing,
    which is what we actually know.

    A deadline also cannot establish completion in `build_event`: the result of
    one category, or the exchange's resolve-by instant, says nothing authoritative
    about whether every award in the ceremony has been announced."""
    if resolution_date is None:
        return None
    try:
        if (resolution_date.month, resolution_date.day) == _PLACEHOLDER_RESOLUTION_DAY:
            return None
        return resolution_date.isoformat()
    except (AttributeError, TypeError):
        return None


def classify_market(external_id: str | None, name: str | None) -> str:
    """Classify an award market: "category" (a co-equal winner category),
    "nominations" (who gets nominated), or "novelty" (attendance/most-wins/etc.).

    Nominations win first (ticker "NOM" or name says nomination/nominee, or asks
    whether someone gets nominated); then a real award category by name; anything
    else is a novelty prop."""
    eid = (external_id or "").upper()
    n = (name or "").lower()
    if ("NOM" in eid or "nomination" in n or "nominee" in n
            or _NOMINATED_RE.search(_RELATIVE_NOMINATED_RE.sub(" ", n))):
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


def derive_awards_concept(
    external_id: str | None, name: str | None = None
) -> dict | None:
    """Map an awards MARKET to its ceremony event concept, or None if not an award.

    L2-88 discovery-entry helper (the co-equal analogue of `derive_ufc_concept`):
    search/typeahead and the futures-detail breadcrumb call this to surface a matched
    Oscar/Emmy/Tony/Grammy category market as a first-class ``event:awards:<ceremony>``
    row / "Part of:" link. Matches the unambiguous Kalshi ticker stem in external_id
    (``KXOSCARPIC-27`` → oscars); falls back to a ceremony keyword in the market name
    (``"Oscar winner: Best Picture"`` → oscars) when the ticker is absent. Returns the
    BARE ceremony slug (no edition), which the adapter resolves to the latest rich
    edition — so the link is never dead even for an older-edition market."""
    eid = (external_id or "").upper()
    for cfg in CEREMONIES.values():
        if cfg.ticker.upper() in eid:
            return {"key": f"event:awards:{cfg.slug}", "name": cfg.display, "domain": "awards"}
    # Name fallback: category/novelty markets carry the ceremony word ("Oscar",
    # "Emmy Award", "Grammy", "Tony Award"). Keyed off the display stem, longest
    # first so "Tony Award" wins before a bare "tony" substring elsewhere.
    n = (name or "").lower()
    _NAME_STEMS = (
        ("academy award", "oscars"),
        ("oscar", "oscars"),
        ("emmy", "emmys"),
        ("grammy", "grammys"),
        ("tony award", "tonys"),
    )
    for stem, slug in _NAME_STEMS:
        if stem in n:
            cfg = CEREMONIES.get(slug)
            if cfg is not None:
                return {"key": f"event:awards:{cfg.slug}", "name": cfg.display, "domain": "awards"}
    return None


class AwardsEventAdapter:
    """Event-concept adapter for awards ceremonies (co_equal_list). Resolves
    ``event:awards:<ceremony>[-<year>]`` into the generic envelope, grouping the
    ceremony's category markets by edition and rendering them as co-equal children
    plus a nominations/props section."""

    domain = "awards"

    async def build_event(self, slug: str, db: AsyncSession) -> dict | None:
        from app.models import FuturesMarket
        from app.utils.outcome_display import (
            is_field_outcome,
            is_placeholder_outcome_name,
            normalize_display_probs,
        )

        cfg, want_year = parse_awards_slug(slug)
        if cfg is None:
            return None

        # All of this ceremony's markets. The KX ticker stem is unambiguous, so
        # match on it directly (no llm_sport_category filter needed) — this also
        # catches any mis-categorized ones.
        #
        # #7979: settled editions are INCLUDED. An `status == "open"` filter here
        # deleted the page at the exact moment the ceremony became a result: the
        # 2026 Emmys are 55 markets, every one of them `resolved` and none `open`,
        # so the query returned nothing, `build_event` returned None, and the route
        # 404'd into a reader-facing "Event not found" (HTTP 200, so no health
        # counter saw it). Same predicate as `SoccerEventAdapter`, whose settled
        # World Cup 2026 concept serves today. The edition gate below (`_in_edition`
        # on the 2-digit year) is what keeps a prior edition out, not the status.
        q = (
            select(FuturesMarket)
            .options(selectinload(FuturesMarket.outcomes))
            .where(
                FuturesMarket.status.in_(["open", "resolved", "closed", "settled"]),
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
                if _has_outcome_name(o)
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
                if _has_outcome_name(o)
                and not is_field_outcome(o.name)
                and not is_placeholder_outcome_name(o.name)
            ]
            displayed = real[:limit]
            # #5349: price-ranked previews can omit the actual winner. Keep every
            # named result grade (`is_result_grade`) from the FULL category, even
            # when its price is absent or it was outside the nominee/field preview.
            displayed.extend(
                o
                for o in (m.outcomes or [])
                if is_result_grade(o)
                and not any(o is shown for shown in displayed)
            )
            return displayed

        # Marquee competitors (the hero head-to-head + settled crown).
        # #5809: bound to a name so the price-age fold below runs over the SAME
        # rows the card displays: `_outcomes` limits the ungraded nominee preview
        # to40 and preserves authoritative winners outside that preview. The full
        # `marquee.outcomes` can still rank ungraded rows no reader sees.
        marquee_outcomes = _outcomes(marquee, limit=40)
        competitors = []
        for o in marquee_outcomes:
            competitors.append(
                {
                    "name": o.name,
                    "probability": (
                        round(float(o.current_probability), 4)
                        if o.current_probability is not None
                        else None
                    ),
                    "won": is_result_grade(o),
                }
            )

        # #5349: this adapter holds category markets, not a complete authoritative
        # ceremony roster/calendar. Even every currently known category being
        # graded cannot prove the whole ceremony finished. The existing unknown
        # envelope phase makes no upcoming/live/completed claim at the reader.
        event_status = "unknown"
        marquee_res = getattr(marquee, "resolution_date", None)

        normalize_display_probs(competitors)
        competitors.sort(key=lambda c: (c["probability"] or -1), reverse=True)

        def _child(m, *, kind=None, prop_type=None):
            outs = _outcomes(m)
            lead_prob = (
                round(float(outs[0].current_probability), 4)
                if outs and outs[0].current_probability is not None
                else None
            )
            # #5349: own assigned state dominates; another category's grade and
            # this category's price cannot announce its result. Read all outcomes,
            # not the preview, so an actual winner beyond the slice still settles.
            settled = settled_under_assigned_state(
                inferred=False,
                assigned_settled=market_assigned_settled(m),
            )
            # #5349: a winner is named only by an independent settlement; a price
            # crown or other stored flag leaves the category unannounced.
            winners = [
                o.name
                for o in (m.outcomes or [])
                if o.name and is_result_grade(o)
            ]
            row = {
                "market_id": m.id,
                "market_name": clean_category_label(m.name),
                "source": m.source,  # data-only (audit); not rendered
                "settled": settled,
                "graded_winner": winners[0] if len(winners) == 1 else None,
                "result": category_result(m, settled=settled),
                "probability": lead_prob,
                "outcomes": [
                    {
                        "name": o.name,
                        "won": is_result_grade(o),
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
        nov_children = [
            _child(m, kind="prop", prop_type="occurrence") for m in novelties
        ]
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
            sections.append(
                {
                    "type": "props",
                    "label": "Nominations & props",
                    "market_ids": prop_ids,
                }
            )

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
                "end_date": ceremony_end_date(marquee_res),
                "venue": None,
                "location": None,
                "is_major": True,  # award ceremonies are marquee cultural events
            },
            "primary": {
                "kind": "co_equal_list",
                "label": clean_category_label(marquee.name),
                "competitors": competitors,
                "evolution_market_id": marquee.id,
                # #5778 — see `event_cycling`. #5809: over the DISPLAYED rows
                # (`marquee_outcomes`), never the market, and with this card's
                # own leg count — an awards `co_equal_list` is a bout only when
                # the category came down to two nominees.
                "price_observed_at": concept_price_observed_at_iso(
                    marquee_outcomes, "co_equal_list", len(competitors)
                ),
            },
            "sections": sections,
            "children": children,
            "movers": [],
        }
