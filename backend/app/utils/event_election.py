"""Election adapter for the Event Concept framework — L2-89 (B6, civic proof).

An election night IS an event concept whose children are N CO-EQUAL races with no
single "overall winner" — the civic sibling of an awards ceremony (design §6). It
fits the SAME event-group primitive as a UFC card / awards ceremony
(`primary.kind == "co_equal_list"`): the co-equal list is RACES (each a
multi-candidate winner market), and the marquee race is the head-to-head hero.

Data reality (verified live 2026-07-12) — the honest shape of "2026 midterms":
The genuine GENERAL-election head-to-head races currently on Kalshi are the
governor winner markets (``KXGOVCA-26`` "California Governor winner?", 25
candidates; ``KXGOVAK-26`` Alaska, 16). Senate coverage is almost entirely PRIMARY
nominee markets (``KXSENATEOHSR-26`` "Ohio Republican Senate nominee?"), House
coverage is seat-count forecasts (``KXHOUSEWINSTATE-FLD`` "How many House seats
will Democrats win in Florida?"), and there are NO chamber-control markets yet.
Novelties (government-shutdown length ``KXGOVT*``, turnout, popular-vote margin,
who-will-testify, congressional trades/pay, member expulsions) ride the same
prefixes and MUST be excluded.

So this v1 leads with the real governor RACES (co-equal children) and surfaces the
primaries + seat forecasts as clearly-secondary PROPS — honest about the thin
general-race coverage rather than dressing up primaries as head-to-heads. It emits
the same envelope the /event page already renders (co_equal_list → TwoSidedTimeline
marquee + MatchupsRail races + EventProps), so NO frontend change is required.

Honest v1 limitations (fast-follow, per the "ship + honest gap note" pattern):
  * General Senate/House head-to-heads and chamber-control markets are not listed
    on Kalshi yet — when they appear they classify as ``*_race`` / ``control`` and
    fold in automatically (the marquee prefers control when present).
  * Kalshi resolution dates on these are placeholders, so status is approximate
    (upcoming unless a race is graded/price-settled).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

# Raw price at/above which a SETTLED marquee candidate is the crowned winner during
# the is_winner grading-lag window (parity with awards/tennis — display-only).
_WON_PRICE_THRESHOLD = 0.97

# Ticker stems whose markets this adapter considers (governor / senate / house /
# congress). ``kxgovt`` (government-shutdown) is a FALSE friend of ``kxgov`` and is
# excluded in classification, not here.
_TICKER_STEMS = ("kxgov", "kxsenate", "kxhouse", "kxcongress")

# Government (shutdown/etc.) — a false friend of "governor". `KXGOVT...`.
_GOVT_RE = re.compile(r"^(?:kalshi:)?kxgovt", re.I)

# Novelty markets that ride the election prefixes but are NOT races.
_NOVELTY_NAME_RE = re.compile(
    r"\bturnout\b|\bmargin\s+of\s+victory\b|\bpopular\s+vote\b|\bshutdown\b"
    r"|\btestif\w+|\bbiggest\s+returns?\b|\btrades?\b|\bsalar(?:y|ies)\b"
    r"|\bpay\s+increase\b|\bexpel\w*|\bexpuls\w*|\bemergency\b"
    r"|\bproof\s+of\s+citizenship\b|\battend\b",
    re.I,
)

_PRIMARY_RE = re.compile(r"\b(?:primary|primaries|nominee|nomination)\b", re.I)
_SEATS_RE = re.compile(r"how\s+many\b.*\bseats\b|\bseats\s+will\b", re.I)
_CONTROL_RE = re.compile(
    r"\b(?:control|majority|which\s+party)\b.*\b(?:senate|house|congress)\b"
    r"|\b(?:senate|house|congress)\b.*\b(?:control|majority)\b",
    re.I,
)
# A general-election winner race ("... Governor winner?", "... Senate general").
_WINNER_RE = re.compile(r"\bwinner\b|\bwho\s+will\s+win\b|\bgeneral\s+election\b", re.I)
# Leadership contests ("Senate Democratic Leader election") are intra-caucus, not a
# midterm race — and carry a 28 edition. Excluded by name too for safety.
_LEADERSHIP_RE = re.compile(r"\bleader\s+election\b|\bcaucus\b|\bwhip\b", re.I)


@dataclass(frozen=True)
class ElectionConfig:
    """One election "edition" — the co-equal analogue of an awards ceremony."""

    slug: str  # canonical URL slug, e.g. "2026-midterms"
    display: str  # human name, e.g. "2026 Midterm Elections"
    edition: int  # 2-digit edition year matched in tickers (26)
    aliases: tuple[str, ...] = field(default_factory=tuple)


ELECTIONS: dict[str, ElectionConfig] = {
    "2026-midterms": ElectionConfig(
        slug="2026-midterms",
        display="2026 Midterm Elections",
        edition=26,
        aliases=("2026", "midterms", "midterms-2026", "us-midterms-2026"),
    ),
}

# slug (canonical + alias) -> config, built once.
_BY_SLUG: dict[str, ElectionConfig] = {}
for _cfg in ELECTIONS.values():
    _BY_SLUG[_cfg.slug] = _cfg
    for _a in _cfg.aliases:
        _BY_SLUG[_a] = _cfg


# ---------------------------------------------------------------------------
# Pure helpers — unit-tested.
# ---------------------------------------------------------------------------


def parse_election_slug(slug: str) -> ElectionConfig | None:
    """Resolve an election slug (canonical or alias) to its config, else None.

    "2026-midterms" / "midterms" / "2026" -> the 2026 midterms config."""
    s = (slug or "").strip().lower()
    return _BY_SLUG.get(s)


def election_edition_year(external_id: str | None) -> int | None:
    """The 2-digit election edition year from a Kalshi ticker.

    ``KXGOVCA-26`` -> 26; ``KXSENATEOHSR-26`` -> 26; ``KXPRESNOMD-28`` -> 28.
    Only a plausible token (2020s–2040s) is accepted as an edition year."""
    m = re.search(r"-(\d{2})(?!\d)", external_id or "")
    if m:
        yr = int(m.group(1))
        if 20 <= yr <= 45:
            return yr
    return None


def classify_election_market(external_id: str | None, name: str | None) -> str:
    """Classify an election market. Returns one of:

      "governor_race" | "senate_race" | "house_race"  — general-election head-to-heads
      "control"                                         — chamber control (Senate/House)
      "primary"                                         — a primary / nominee contest
      "seat_forecast"                                   — "how many seats will party win"
      "novelty"                                         — shutdown/turnout/margin/etc.
      "other"                                           — election-adjacent, unclassified

    Order matters: novelties and the govt-shutdown false-friend are filtered first so
    they never masquerade as races; primaries win before general-race detection so a
    "Republican Senate nominee?" is never surfaced as a head-to-head."""
    eid = (external_id or "").lower()
    n = name or ""

    if _GOVT_RE.search(eid) or _NOVELTY_NAME_RE.search(n):
        return "novelty"
    if _LEADERSHIP_RE.search(n):
        return "novelty"
    if _CONTROL_RE.search(n):
        return "control"
    if _PRIMARY_RE.search(n):
        return "primary"
    if eid.startswith(("kxhouse", "kalshi:kxhouse")) and _SEATS_RE.search(n):
        return "seat_forecast"
    if eid.startswith(("kxgov", "kalshi:kxgov")) and _WINNER_RE.search(n):
        # kxgovt already filtered above, so this is a real Governor race.
        return "governor_race"
    if eid.startswith(("kxsenate", "kalshi:kxsenate")) and _WINNER_RE.search(n):
        return "senate_race"
    if eid.startswith(("kxhouse", "kalshi:kxhouse")) and _WINNER_RE.search(n):
        return "house_race"
    return "other"


def is_race(kind: str) -> bool:
    """A co-equal general-election race (rendered as a main race card)."""
    return kind in ("governor_race", "senate_race", "house_race", "control")


def clean_race_label(name: str | None) -> str:
    """Strip trailing question marks / person-vs-party parenthetical noise so a race
    card reads cleanly: "California Governor winner?" -> "California Governor";
    "Alaska Governor winner? (Person)" -> "Alaska Governor"."""
    s = (name or "").strip()
    if not s:
        return name or ""
    s = re.sub(r"\s*\((?:person|party)\)\s*$", "", s, flags=re.I)
    s = s.rstrip("?").strip()
    s = re.sub(r"\s+winner$", "", s, flags=re.I).strip()
    return s or (name or "")


def derive_election_concept(
    external_id: str | None, name: str | None = None
) -> dict | None:
    """Map an election MARKET to its election event concept, or None if not a
    midterm race. The discovery-entry helper (search/typeahead + breadcrumb),
    mirroring ``derive_awards_concept``. Only a genuine race/control/primary of the
    matched edition surfaces the concept — novelties and other-edition (2028 pres)
    markets return None."""
    kind = classify_election_market(external_id, name)
    if kind == "novelty" or kind == "other":
        return None
    yr = election_edition_year(external_id)
    for cfg in ELECTIONS.values():
        if yr is not None and yr != cfg.edition:
            continue
        return {
            "key": f"event:election:{cfg.slug}",
            "name": cfg.display,
            "domain": "election",
        }
    return None


class ElectionEventAdapter:
    """Event-concept adapter for elections (co_equal_list). Resolves
    ``event:election:<slug>`` into the generic envelope: governor (and, when they
    appear, senate/house/control) RACES as co-equal children, primaries + seat
    forecasts as a props section."""

    domain = "election"

    async def build_event(self, slug: str, db: AsyncSession) -> dict | None:
        from datetime import datetime, timezone

        from app.models import FuturesMarket
        from app.utils.outcome_display import (
            is_field_outcome,
            is_placeholder_outcome_name,
            normalize_display_probs,
        )

        cfg = parse_election_slug(slug)
        if cfg is None:
            return None

        now = datetime.now(timezone.utc)

        # All markets on the election ticker stems. The stems are unambiguous enough
        # that no llm_sport_category filter is needed; classification below drops the
        # govt-shutdown false friend and novelties.
        q = (
            select(FuturesMarket)
            .options(selectinload(FuturesMarket.outcomes))
            .where(
                FuturesMarket.status == "open",
                or_(
                    *[
                        FuturesMarket.external_id.ilike(f"%{stem}%")
                        for stem in _TICKER_STEMS
                    ]
                ),
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

        # Classify + edition-tag. Keep only this edition (drops 2028 pres nominees,
        # 28 leadership contests, etc.); markets with no parseable year are kept
        # (honest — better to show than silently drop).
        tagged = []
        for m in markets:
            kind = classify_election_market(m.external_id, m.name)
            yr = election_edition_year(m.external_id)
            if yr is not None and yr != cfg.edition:
                continue
            tagged.append((m, kind))

        races = [t for t in tagged if is_race(t[1]) and _real_count(t[0]) >= 2]
        if not races:
            return None  # no genuine races → no page (honest, never a stub)

        primaries = [t[0] for t in tagged if t[1] == "primary" and _real_count(t[0]) >= 2]
        seat_forecasts = [
            t[0] for t in tagged if t[1] == "seat_forecast" and _real_count(t[0]) >= 2
        ]

        # Marquee: a chamber-control market is the natural headline (co-equal
        # GOP/Dem); else the richest race (most candidates — e.g. CA Governor).
        marquee = next((t[0] for t in races if t[1] == "control"), None)
        if marquee is None:
            marquee = max((t[0] for t in races), key=_real_count)

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

        # Status (approximate — Kalshi election dates are placeholders). Settled if a
        # candidate is graded or the marquee leader is price-settled.
        marquee_top = max((c["probability"] or -1) for c in competitors) if competitors else -1
        event_status = "upcoming"
        if any(c["won"] for c in competitors):
            event_status = "settled"
        elif marquee_top >= _WON_PRICE_THRESHOLD:
            event_status = "settled"

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
                "market_name": clean_race_label(m.name),
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

        # Children: every race (co-equal list) + primaries + seat forecasts as props.
        # Races sort by leader probability (most-decided first); marquee floats front.
        race_markets = [t[0] for t in races]
        race_children = [_child(m) for m in race_markets]
        race_children.sort(
            key=lambda c: (c["market_id"] != marquee.id, -(c["probability"] or 0))
        )
        primary_children = [
            _child(m, kind="prop", prop_type="primary") for m in primaries
        ]
        seat_children = [
            _child(m, kind="prop", prop_type="seats") for m in seat_forecasts
        ]
        children = race_children + primary_children + seat_children

        sections = [
            {
                "type": "races",
                "label": "Races",
                "market_ids": [c["market_id"] for c in race_children],
            }
        ]
        prop_ids = [c["market_id"] for c in primary_children + seat_children]
        if prop_ids:
            sections.append(
                {"type": "props", "label": "Primaries & forecasts", "market_ids": prop_ids}
            )

        return {
            "event": {
                "key": f"event:election:{cfg.slug}",
                "domain": "election",
                "name": cfg.display,
                "status": event_status,
                "start_date": None,
                "end_date": None,
                "venue": None,
                "location": None,
                "is_major": True,  # a national election night is a marquee civic event
            },
            "primary": {
                "kind": "co_equal_list",
                "label": clean_race_label(marquee.name),
                "competitors": competitors,
                "evolution_market_id": marquee.id,
            },
            "sections": sections,
            "children": children,
            "movers": [],
        }
