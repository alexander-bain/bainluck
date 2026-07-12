"""UFC adapter for the Event Concept framework — slice 3, the co-equal variant
(#999, L2-72; completed in L2-84). This is the first
`primary.kind == "co_equal_list"` domain the L2-64 components (TwoSidedTimeline +
MatchupsRail) were built for.

A UFC card has no single winner — it's a set of two-sided fights (+ props).
Verified live (2026-07-09..07-12): Kalshi carries per-fight markets with tickers
`KXUFCFIGHT-<DATE><FIGHTERS>` (e.g. KXUFCFIGHT-26JUL11MCGHOL), each with exactly 2
outcomes (fighter A / fighter B), category=mma. Fights sharing the DATE token are
one card. Model: the card's headline fight (latest commence_time) is `primary`
(rendered head-to-head via TwoSidedTimeline); every fight is a child (matchup rail).

L2-84 (B2) adds three things, all VERIFIED against real UFC 329 data:
  * Card NAMING — numbered cards read "UFC 329" (parsed from the fight's Kalshi
    `event_title`/name, which carries "UFC 329: McGregor vs. Holloway 2"); the
    "Fight Night: …" fallback stays; a bare headline-fight name is the last resort.
  * A real PROPS section — method-of-victory / round / go-the-distance / occurrence
    props from Kalshi (KXUFCMOV/MOF/ROUNDS/VICROUND/DISTANCE/OCCUR) AND Polymarket
    ("Will X win by KO or TKO?") classify into the card, tagged by prop_type.
  * DISCOVERY — `list_ufc_card_concepts()` + `derive_ufc_concept()` group open
    fight markets into card concepts (`event:ufc:<token>`) for search / typeahead /
    the sports feed (the co-equal analogue of the tennis winner-field derivation).

Pure helpers are unit-tested; build_event is exercised via the route test.
"""

from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.utils.event_matcher import player_key

# Kalshi UFC fight ticker: KXUFCFIGHT-<YYMONDD><FIGHTERS>. The <YYMONDD> date
# token identifies the card (all fights that day share it).
_UFC_TICKER_RE = re.compile(r"KXUFCFIGHT-(\d{2}[A-Z]{3}\d{2})", re.IGNORECASE)

# Any Kalshi UFC market's date token (fight OR prop): KX<UFC-PREFIX>-<YYMONDD>…
# so a prop ticket (KXUFCMOV-26MAR07HOLOLI) shares the card date-token with its
# fight. Broader than _UFC_TICKER_RE which is fight-only.
_UFC_ANY_DATE_RE = re.compile(r"KXUFC[A-Z]*-(\d{2}[A-Z]{3}\d{2})", re.IGNORECASE)

# Numbered-card label, e.g. "UFC 329" out of "UFC 329: McGregor vs. Holloway 2".
_UFC_NUMBER_RE = re.compile(r"\bUFC\s*#?\s*(\d{2,4})\b", re.IGNORECASE)

# A matchup-shaped name ("A vs B", "A def. B") — used to keep the two-sided fight
# (and its cross-source dup / negrisk bundle) OUT of the props list.
_UFC_MATCHUP_RE = re.compile(r"\s+(?:vs\.?|v\.?|def\.?|beats?)\s+", re.IGNORECASE)

# Prop TYPE grammar. Kalshi ticker prefixes are the highest-precision signal;
# name regexes catch Polymarket (hash tickers, no date token) + belt-and-braces.
# Ordered method → rounds → distance → occurrence (checked in that order).
_UFC_PROP_TICKER_TYPES = {
    "KXUFCMOV": "method",       # Method of Victory
    "KXUFCMOF": "method",       # Method of Finish
    "KXUFCROUNDS": "rounds",    # Round of Finish
    "KXUFCVICROUND": "rounds",  # Round of Victory
    "KXUFCDISTANCE": "distance",  # Go the Distance
    "KXUFCOCCUR": "occurrence",  # Will A and B fight at …?
}
_UFC_METHOD_NAME_RE = re.compile(
    r"method of (?:victory|finish)|win by|by (?:ko|tko|decision|submission|knockout)"
    r"|ko/tko|by kotko",
    re.IGNORECASE,
)
_UFC_ROUNDS_NAME_RE = re.compile(
    r"round of (?:finish|victory)|which round|o/u\s*[\d.]+\s*rounds?|\brounds?\b",
    re.IGNORECASE,
)
_UFC_DISTANCE_NAME_RE = re.compile(r"go(?:es)? the distance|the distance", re.IGNORECASE)
_UFC_OCCURRENCE_NAME_RE = re.compile(
    r"fight at|\battend\b|make weight|miss(?:es)? weight|walk ?out", re.IGNORECASE
)


def ufc_card_token(external_id: str | None) -> str | None:
    """Extract the lowercased card date-token from a Kalshi UFC fight ticker, or
    None if it isn't a fight market. e.g. "kalshi:KXUFCFIGHT-26JUN20KAPHOR" ->
    "26jun20". This is the reliable card-grouping key (no card-level market exists)."""
    if not external_id:
        return None
    m = _UFC_TICKER_RE.search(external_id)
    return m.group(1).lower() if m else None


def ufc_any_card_token(external_id: str | None) -> str | None:
    """Card date-token from ANY Kalshi UFC ticker (fight OR prop), so a
    KXUFCMOV-/KXUFCROUNDS-/… prop can be tied back to its card by shared token.
    e.g. "kalshi:KXUFCMOV-26MAR07HOLOLI" -> "26mar07"; None if not a Kalshi UFC
    ticker."""
    if not external_id:
        return None
    m = _UFC_ANY_DATE_RE.search(external_id)
    return m.group(1).lower() if m else None


def ufc_card_number(*texts: str | None) -> str | None:
    """Return the canonical numbered-card label (e.g. "UFC 329") found in any of
    the given strings (a fight's name and/or its Kalshi `event_title`), or None
    for a Fight Night / unnumbered card. Normalizes spacing → "UFC 329"."""
    for t in texts:
        if not t:
            continue
        m = _UFC_NUMBER_RE.search(t)
        if m:
            return f"UFC {m.group(1)}"
    return None


def _strip_card_prefix(name: str | None) -> str:
    """Drop a leading "UFC 329: " / "Fight Night: " so the matchup is the subtitle."""
    if not name:
        return ""
    return re.sub(
        r"^\s*(?:UFC\s*#?\s*\d{2,4}|UFC\s*Fight\s*Night|Fight\s*Night)\s*:?\s*",
        "",
        name,
        flags=re.IGNORECASE,
    ).strip()


def ufc_card_label(main_event_name: str | None, extra_titles=()) -> tuple[str, bool]:
    """Derive the card's DISPLAY name + is_major flag from the main-event fight's
    name (and any extra title strings — e.g. Kalshi event_titles of the card's
    fights). Pure + unit-tested.

    Numbered card  -> ("UFC 329: McGregor vs. Holloway 2", True)  [Major]
    Fight Night    -> ("Fight Night: Yakhyaev vs Walker", False)
    Unrecognized   -> (main_event_name, False)                    [last resort]
    """
    candidates = [main_event_name, *extra_titles]
    number = ufc_card_number(*candidates)
    subtitle = _strip_card_prefix(main_event_name) or (main_event_name or "").strip()

    if number:
        # Avoid "UFC 329: UFC 329: …" if the subtitle still carried the number.
        if subtitle and number.lower() not in subtitle.lower():
            return f"{number}: {subtitle}", True
        return (main_event_name or number), True

    is_fight_night = any(
        c and re.search(r"fight\s*night", c, re.IGNORECASE) for c in candidates
    )
    if is_fight_night:
        if subtitle:
            return f"Fight Night: {subtitle}", False
        return (main_event_name or "Fight Night"), False

    return (main_event_name or ""), False


def is_ufc_fight_market(external_id: str | None, n_outcomes: int) -> bool:
    """A real card fight: a Kalshi KXUFCFIGHT ticker with exactly two sides."""
    return ufc_card_token(external_id) is not None and n_outcomes == 2


def classify_ufc_prop(external_id: str | None, name: str | None) -> str | None:
    """Classify a UFC prop market into method | rounds | distance | occurrence,
    or None if it isn't a recognizable prop shape. Ticker prefix first (Kalshi,
    highest precision), then name regex (Polymarket + fallback). Pure/unit-tested.

    A plain fight moneyline ("A vs B") classifies as None (no prop keyword), so
    this never mis-tags a fight as a prop even before the matchup guard."""
    eid = external_id or ""
    for prefix, ptype in _UFC_PROP_TICKER_TYPES.items():
        if re.search(rf"\b{prefix}\b", eid, re.IGNORECASE) or f":{prefix}-" in eid.upper():
            return ptype
        if prefix in eid.upper():
            return ptype
    n = name or ""
    if _UFC_METHOD_NAME_RE.search(n):
        return "method"
    if _UFC_DISTANCE_NAME_RE.search(n):
        return "distance"
    if _UFC_ROUNDS_NAME_RE.search(n):
        return "rounds"
    if _UFC_OCCURRENCE_NAME_RE.search(n):
        return "occurrence"
    return None


def _name_surname_tokens(name: str | None) -> set[str]:
    """All lowercase alnum word tokens of a name (for card-surname containment)."""
    return set(re.sub(r"[^a-z0-9 ]", "", (name or "").lower()).split())


def _prop_belongs_to_card(
    name: str | None,
    external_id: str | None,
    card_number: str | None,
    card_token: str | None,
    card_surnames: set[str],
) -> bool:
    """Is this prop about THIS card? True if it names the card number, shares the
    Kalshi card date-token, or mentions one of the card's fighter surnames."""
    n = (name or "").lower()
    if card_number and card_number.lower() in n:
        return True
    if card_token and ufc_any_card_token(external_id) == card_token:
        return True
    if card_surnames and (_name_surname_tokens(name) & card_surnames):
        return True
    return False


def ufc_status(latest_commence, now) -> str:
    """upcoming / live / settled for a card from its latest fight's commence time
    (fight night spans a few hours). Conservative: no time → upcoming."""
    if latest_commence is None:
        return "upcoming"
    try:
        hours = (latest_commence - now).total_seconds() / 3600
    except TypeError:
        return "upcoming"
    if hours < -6:      # card finished (> ~6h after the main event started)
        return "settled"
    if hours <= 8:      # fight night window
        return "live"
    return "upcoming"


def derive_ufc_concept(
    external_id: str | None, name: str | None, n_outcomes: int | None = None
) -> dict | None:
    """From a single matched UFC FIGHT market, derive its card-concept descriptor
    (key/name/domain/is_major) for search + typeahead — the co-equal analogue of
    the tennis winner-field derivation. None if the market isn't a card fight.

    The KXUFCFIGHT ticker is signal enough (props/futures use other prefixes and
    yield None), so `n_outcomes` is optional: pass it to also require two-sided,
    omit it (search rows without loaded outcomes) to derive from the ticker alone.

    The label is card-level (e.g. "UFC 329: McGregor vs. Holloway 2"); multiple
    matched fights of one card collapse to one concept via the shared key."""
    token = ufc_card_token(external_id)
    if token is None or (n_outcomes is not None and n_outcomes != 2):
        return None
    label, is_major = ufc_card_label(name, ())
    return {
        "key": f"event:ufc:{token}",
        "name": label or name,
        "domain": "ufc",
        "is_major": is_major,
        "card_token": token,
    }


async def list_ufc_card_concepts(
    db: AsyncSession,
    *,
    statuses: tuple[str, ...] = ("upcoming", "live"),
    limit: int = 20,
) -> list[dict]:
    """Enumerate UFC CARD concepts (not query-driven) for the sports feed — group
    open MMA fight markets by card date-token, one descriptor per card. Returns
    lightweight dicts the feed scorer turns into candidates:

        {key, name, domain, status, start_date, is_major, fight_count,
         main_event_id, latest_commence}

    Read-only, best-effort. Mirrors _score_golf_tournaments' "pull my own data,
    emit candidates" pattern — no dependency on the request-path futures pools."""
    from datetime import datetime, timezone
    from app.models import FuturesMarket

    now = datetime.now(timezone.utc)
    rows = list(
        (
            await db.execute(
                select(
                    FuturesMarket.id,
                    FuturesMarket.external_id,
                    FuturesMarket.name,
                    FuturesMarket.commence_time,
                    FuturesMarket.market_metadata,
                ).where(
                    FuturesMarket.llm_sport_category == "mma",
                    FuturesMarket.status == "open",
                )
            )
        ).all()
    )

    # Group fight markets by card token.
    cards: dict[str, dict] = {}
    for mid, ext_id, name, commence, meta in rows:
        token = ufc_card_token(ext_id)
        if token is None:
            continue  # not a fight ticker (prop/future) — cards are keyed by fights
        c = cards.setdefault(
            token,
            {"token": token, "fights": [], "titles": []},
        )
        evt_title = (meta or {}).get("event_title") if isinstance(meta, dict) else None
        c["fights"].append({"id": mid, "name": name, "commence": commence})
        if evt_title:
            c["titles"].append(evt_title)

    concepts: list[dict] = []
    for token, c in cards.items():
        fights = c["fights"]
        if not fights:
            continue

        def _ct(f):
            return f["commence"] or datetime.min.replace(tzinfo=timezone.utc)

        fights.sort(key=_ct)
        main = fights[-1]
        latest = main["commence"]
        status = ufc_status(latest, now)
        if status not in statuses:
            continue
        label, is_major = ufc_card_label(main["name"], tuple(c["titles"]))
        concepts.append(
            {
                "key": f"event:ufc:{token}",
                "name": label or main["name"],
                "domain": "ufc",
                "status": status,
                "start_date": latest.isoformat() if latest is not None else None,
                "is_major": is_major,
                "fight_count": len(fights),
                "main_event_id": main["id"],
                "latest_commence": latest,
            }
        )

    # Marquee first (numbered majors), then soonest, then most fights.
    concepts.sort(
        key=lambda x: (
            0 if x["is_major"] else 1,
            x["latest_commence"] or datetime.max.replace(tzinfo=timezone.utc),
            -x["fight_count"],
        )
    )
    return concepts[:limit]


class UFCEventAdapter:
    domain = "ufc"

    async def build_event(self, slug: str, db: AsyncSession) -> dict | None:
        from datetime import datetime, timezone
        from app.models import FuturesMarket

        now = datetime.now(timezone.utc)
        target = re.sub(r"[^a-z0-9]", "", (slug or "").lower())
        if not target:
            return None

        q = (
            select(FuturesMarket)
            .options(selectinload(FuturesMarket.outcomes))
            .where(
                FuturesMarket.llm_sport_category == "mma",
                FuturesMarket.status == "open",
            )
        )
        markets = list((await db.execute(q)).scalars().unique().all())
        if not markets:
            return None

        # Collect this card's FIGHTS: ticker date-token == slug AND two-sided.
        fights = []
        for m in markets:
            if ufc_card_token(m.external_id) != target:
                continue
            if len(m.outcomes or []) != 2:  # a real fight is two-sided
                continue
            fights.append(m)
        if not fights:
            return None

        # Headline fight = latest commence_time (the main event caps the night).
        def _ct(m):
            return m.commence_time or datetime.min.replace(tzinfo=timezone.utc)
        fights.sort(key=_ct)
        main_event = fights[-1]
        latest_commence = main_event.commence_time

        def _fight_outcomes(m):
            outs = sorted(
                (m.outcomes or []),
                key=lambda o: float(o.current_probability or 0),
                reverse=True,
            )
            return [
                {"name": o.name, "probability": (
                    round(float(o.current_probability), 4)
                    if o.current_probability is not None else None)}
                for o in outs
            ]

        # primary = the main-event fighters (co-equal, head-to-head).
        competitors = _fight_outcomes(main_event)

        def _title_of(m):
            meta = getattr(m, "market_metadata", None)
            return (meta or {}).get("event_title") if isinstance(meta, dict) else None

        # L2-84: numbered-card naming ("UFC 329") with Fight-Night / headline
        # fallback, derived from the fights' names + Kalshi event_titles.
        card_titles = tuple(t for t in (_title_of(m) for m in fights) if t)
        card_name, is_major = ufc_card_label(main_event.name, card_titles)
        card_number = ufc_card_number(main_event.name, *card_titles)

        # Card fighter surnames — for tying name-only props (Polymarket) to the card.
        card_surnames: set[str] = set()
        for f in fights:
            for o in (f.outcomes or []):
                k = player_key(o.name)
                if k:
                    card_surnames.add(k)

        def _child(m, kind, prop_type=None):
            outs = _fight_outcomes(m)
            lead_prob = outs[0]["probability"] if outs else None
            settled = lead_prob is not None and (lead_prob >= 0.97 or lead_prob <= 0.03)
            row = {
                "market_id": m.id,
                "market_name": m.name,
                "source": m.source,  # data-only (audit); not rendered (D1)
                "kind": kind,        # "fight" | "prop" — frontend splits the rail
                "settled": settled,
                "probability": lead_prob,
                "outcomes": outs,
            }
            if prop_type:
                row["prop_type"] = prop_type
            return row

        # children = every fight on the card (matchup rail). Settled when decided.
        children = [_child(m, "fight") for m in fights]

        # L2-84: PROPS — method / rounds / distance / occurrence from Kalshi AND
        # Polymarket, tied to this card by number, shared date-token, or a card
        # fighter surname. Matchup-shaped markets are excluded (that catches the
        # cross-source fight dup AND Polymarket's bundled-negrisk shape, which is
        # a single market of 11 mixed method/round outcomes — decomposing it is
        # ingestion/A-track work, not read-side, so we leave it out here).
        fight_ids = {m.id for m in fights}
        props = []
        for m in markets:
            if m.id in fight_ids:
                continue
            if _UFC_MATCHUP_RE.search(m.name or ""):
                continue
            prop_type = classify_ufc_prop(m.external_id, m.name)
            if prop_type is None:
                continue
            if not _prop_belongs_to_card(
                m.name, m.external_id, card_number, target, card_surnames
            ):
                continue
            props.append(_child(m, "prop", prop_type))

        # Stable prop ordering: by type (method, rounds, distance, occurrence).
        _ptype_order = {"method": 0, "rounds": 1, "distance": 2, "occurrence": 3}
        props.sort(key=lambda p: (_ptype_order.get(p.get("prop_type"), 9), p["market_id"]))

        children.extend(props)

        sections = [{
            "type": "matchup",
            "label": "Fights",
            "market_ids": [m.id for m in fights],
        }]
        if props:
            sections.append({
                "type": "props",
                "label": "Props",
                "market_ids": [p["market_id"] for p in props],
            })

        return {
            "event": {
                "key": f"event:ufc:{target}",
                "domain": "ufc",
                "name": card_name or main_event.name,  # numbered/Fight-Night card
                "status": ufc_status(latest_commence, now),
                "start_date": (
                    latest_commence.isoformat() if latest_commence is not None else None
                ),
                "end_date": None,
                "venue": None,
                "location": None,
                "is_major": is_major,
            },
            "primary": {
                "kind": "co_equal_list",
                "label": "Main event",
                "competitors": competitors,
                "evolution_market_id": main_event.id,
            },
            "sections": sections,
            "children": children,
            "movers": [],
        }
