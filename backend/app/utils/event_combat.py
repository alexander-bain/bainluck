"""Generic COMBAT-SPORT engine for the Event Concept framework — L2-86 (B5).

This is the domain-parameterized core behind UFC (MMA) and boxing card pages: both
are `primary.kind == "co_equal_list"` competitions — a set of two-sided fights on a
card (identified by a Kalshi date-token) plus method / round / distance / occurrence
props. The two differ only in constants:

    * the fight ticker prefix (KXUFCFIGHT vs KXBOXING),
    * the prop ticker → type map (KXUFCMOV… vs KXBOXINGMOV…),
    * the `llm_sport_category` + `domain`,
    * whether cards are NUMBERED ("UFC 329" — MMA yes, boxing no).

Everything else — card grouping by date-token, main-event selection, prop
classification, the co_equal_list envelope — is identical. So a new combat sport is
one `CombatSportConfig` + a thin module (see `event_boxing.py`); the UFC module
(`event_ufc.py`) is now itself a thin config over this engine.

The card_token/card_label/classify/derive helpers are pure and unit-tested (per
domain); `build_event` is exercised via the route test (per domain).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.utils.event_matcher import player_key

# ---------------------------------------------------------------------------
# Shared (domain-agnostic) grammar — the same for every combat sport.
# ---------------------------------------------------------------------------

# A matchup-shaped name ("A vs B", "A def. B") — used to keep the two-sided fight
# (and its cross-source dup / negrisk bundle) OUT of the props list.
_MATCHUP_RE = re.compile(r"\s+(?:vs\.?|v\.?|def\.?|beats?)\s+", re.IGNORECASE)

# Prop-TYPE name grammar (Polymarket hash tickers + belt-and-braces for Kalshi).
# Checked method → distance → rounds → occurrence, matching the original UFC order.
_METHOD_NAME_RE = re.compile(
    r"method of (?:victory|finish)|win by|by (?:ko|tko|decision|submission|knockout)"
    r"|ko/tko|by kotko",
    re.IGNORECASE,
)
_ROUNDS_NAME_RE = re.compile(
    r"round of (?:finish|victory)|which round|o/u\s*[\d.]+\s*rounds?|\brounds?\b",
    re.IGNORECASE,
)
_DISTANCE_NAME_RE = re.compile(r"go(?:es)? the distance|the distance", re.IGNORECASE)
_OCCURRENCE_NAME_RE = re.compile(
    r"fight at|\battend\b|make weight|miss(?:es)? weight|walk ?out", re.IGNORECASE
)


@dataclass(frozen=True)
class CombatSportConfig:
    """Everything that distinguishes one combat sport from another. Build via
    :func:`make_combat_config` (compiles the date-token regexes from the prefixes)."""

    domain: str  # event-key domain, e.g. "ufc" | "boxing"
    llm_category: str  # FuturesMarket.llm_sport_category filter, e.g. "mma" | "boxing"
    fight_re: re.Pattern  # matches a card FIGHT ticker → captures the date-token
    any_date_re: re.Pattern  # matches ANY ticker (fight OR prop) → date-token
    prop_ticker_types: dict  # {ticker-prefix: prop_type}
    number_re: re.Pattern | None = None  # numbered-card pattern (MMA); None = unnumbered
    number_label: str = ""  # prefix for a numbered card, e.g. "UFC" → "UFC 329"
    strip_re: re.Pattern | None = None  # leading card-prefix to strip from a subtitle
    fight_night_re: re.Pattern | None = None  # "Fight Night" detection (MMA); None = off
    fight_night_label: str = "Fight Night"
    # Sports.key(s) of the schedule (events table) source: scheduled bouts (Odds API/
    # ESPN/StatPal) that surface a card BEFORE Kalshi lists it, and whose fight-start
    # time is authoritative over Kalshi's resolution/close date (gotcha #14). Empty
    # disables the events-table source. MMA spans two keys (mma_ufc +
    # mma_mixed_martial_arts); boxing is ("boxing_boxing",).
    events_sport_keys: tuple[str, ...] = ()


def make_combat_config(
    *,
    domain: str,
    llm_category: str,
    fight_prefix: str,
    any_prefix: str,
    prop_ticker_types: dict,
    number_re: re.Pattern | None = None,
    number_label: str = "",
    strip_re: re.Pattern | None = None,
    fight_night_re: re.Pattern | None = None,
    fight_night_label: str = "Fight Night",
    events_sport_keys: tuple[str, ...] = (),
) -> CombatSportConfig:
    """Build a config, compiling the `<PREFIX>-<YYMONDD>` date-token regexes.

    `fight_prefix` matches a card fight ticker (e.g. "KXUFCFIGHT" / "KXBOXING");
    `any_prefix` matches fight OR prop tickers (e.g. "KXUFC" / "KXBOXING") so a prop
    shares its card's date-token — `<any_prefix>[A-Z]*-<YYMONDD>`.
    """
    return CombatSportConfig(
        domain=domain,
        llm_category=llm_category,
        fight_re=re.compile(
            rf"{re.escape(fight_prefix)}-(\d{{2}}[A-Z]{{3}}\d{{2}})", re.IGNORECASE
        ),
        any_date_re=re.compile(
            rf"{re.escape(any_prefix)}[A-Z]*-(\d{{2}}[A-Z]{{3}}\d{{2}})", re.IGNORECASE
        ),
        prop_ticker_types=prop_ticker_types,
        number_re=number_re,
        number_label=number_label,
        strip_re=strip_re,
        fight_night_re=fight_night_re,
        fight_night_label=fight_night_label,
        events_sport_keys=events_sport_keys,
    )


# ---------------------------------------------------------------------------
# Pure helpers (per-domain via cfg) — unit-tested.
# ---------------------------------------------------------------------------


# Lowercase 3-letter month abbreviations — locale-independent (strftime("%b") is
# locale-dependent). Used to build a card date-token from an events-table bout's
# commence_time that ALIGNS with the Kalshi ticker token (`YYMONDD`, e.g. 26JUL18).
_MONTHS = (
    "jan", "feb", "mar", "apr", "may", "jun",
    "jul", "aug", "sep", "oct", "nov", "dec",
)


def event_commence_token(commence) -> str | None:
    """Card date-token from an events-table bout's commence_time, matching the
    Kalshi fight-ticker token format (`YYMONDD` lowercased), so an events-sourced
    card and a Kalshi-sourced card for the same date UNIFY on one key rather than
    duplicating. e.g. 2026-07-18T22:00Z -> "26jul18". None if no time.

    Uses the stored (UTC) date components — validated against live data (the
    Du Plessis/Usman card: commence 2026-07-18T22:00Z, Kalshi ticker KX…-26JUL18)."""
    if commence is None:
        return None
    try:
        return f"{commence.year % 100:02d}{_MONTHS[commence.month - 1]}{commence.day:02d}"
    except (AttributeError, IndexError, TypeError):
        return None


def card_token(cfg: CombatSportConfig, external_id: str | None) -> str | None:
    """Lowercased card date-token from a card FIGHT ticker, or None if it isn't a
    fight market. e.g. (UFC) "kalshi:KXUFCFIGHT-26JUN20KAPHOR" -> "26jun20";
    (boxing) "KXBOXING-26JUL04MASONBELL" -> "26jul04"."""
    if not external_id:
        return None
    m = cfg.fight_re.search(external_id)
    return m.group(1).lower() if m else None


def any_card_token(cfg: CombatSportConfig, external_id: str | None) -> str | None:
    """Card date-token from ANY ticker (fight OR prop), so a prop can be tied back
    to its card by shared token. None if not a ticker of this sport."""
    if not external_id:
        return None
    m = cfg.any_date_re.search(external_id)
    return m.group(1).lower() if m else None


def card_number(cfg: CombatSportConfig, *texts: str | None) -> str | None:
    """Canonical numbered-card label (e.g. "UFC 329") from any text, or None for an
    unnumbered card (or a sport with no numbering, i.e. cfg.number_re is None)."""
    if cfg.number_re is None:
        return None
    for t in texts:
        if not t:
            continue
        m = cfg.number_re.search(t)
        if m:
            return f"{cfg.number_label} {m.group(1)}"
    return None


def _strip_card_prefix(cfg: CombatSportConfig, name: str | None) -> str:
    """Drop a leading numbered/"Fight Night" card prefix so the matchup is the
    subtitle. No-op (just trims) for a sport without a strip pattern."""
    if not name:
        return ""
    if cfg.strip_re is None:
        return name.strip()
    return cfg.strip_re.sub("", name).strip()


def card_label(
    cfg: CombatSportConfig, main_event_name: str | None, extra_titles=()
) -> tuple[str, bool]:
    """Derive the card's DISPLAY name + is_major flag from the main-event fight's
    name (and any extra title strings). Pure + unit-tested.

    Numbered card  -> ("UFC 329: McGregor vs. Holloway 2", True)  [Major]
    Fight Night    -> ("Fight Night: Yakhyaev vs Walker", False)
    Unnumbered     -> (main_event_name, False)   [boxing / last resort]
    """
    candidates = [main_event_name, *extra_titles]
    number = card_number(cfg, *candidates)
    subtitle = _strip_card_prefix(cfg, main_event_name) or (main_event_name or "").strip()

    if number:
        # Avoid "UFC 329: UFC 329: …" if the subtitle still carried the number.
        if subtitle and number.lower() not in subtitle.lower():
            return f"{number}: {subtitle}", True
        return (main_event_name or number), True

    is_fight_night = cfg.fight_night_re is not None and any(
        c and cfg.fight_night_re.search(c) for c in candidates
    )
    if is_fight_night:
        if subtitle:
            return f"{cfg.fight_night_label}: {subtitle}", False
        return (main_event_name or cfg.fight_night_label), False

    return (main_event_name or ""), False


def is_fight_market(
    cfg: CombatSportConfig, external_id: str | None, n_outcomes: int
) -> bool:
    """A real card fight: a card-fight ticker with exactly two sides."""
    return card_token(cfg, external_id) is not None and n_outcomes == 2


def classify_prop(
    cfg: CombatSportConfig, external_id: str | None, name: str | None
) -> str | None:
    """Classify a prop into method | rounds | distance | occurrence, or None if it
    isn't a recognizable prop shape. Ticker prefix first (Kalshi, highest
    precision), then name regex (Polymarket + fallback). A plain fight moneyline
    ("A vs B") classifies as None."""
    eid = external_id or ""
    for prefix, ptype in cfg.prop_ticker_types.items():
        if re.search(rf"\b{prefix}\b", eid, re.IGNORECASE) or f":{prefix}-" in eid.upper():
            return ptype
        if prefix in eid.upper():
            return ptype
    n = name or ""
    if _METHOD_NAME_RE.search(n):
        return "method"
    if _DISTANCE_NAME_RE.search(n):
        return "distance"
    if _ROUNDS_NAME_RE.search(n):
        return "rounds"
    if _OCCURRENCE_NAME_RE.search(n):
        return "occurrence"
    return None


def _name_surname_tokens(name: str | None) -> set[str]:
    """All lowercase alnum word tokens of a name (for card-surname containment)."""
    return set(re.sub(r"[^a-z0-9 ]", "", (name or "").lower()).split())


def _prop_belongs_to_card(
    cfg: CombatSportConfig,
    name: str | None,
    external_id: str | None,
    card_number_: str | None,
    card_token_: str | None,
    card_surnames: set[str],
) -> bool:
    """Is this prop about THIS card? True if it names the card number, shares the
    card date-token, or mentions one of the card's fighter surnames."""
    n = (name or "").lower()
    if card_number_ and card_number_.lower() in n:
        return True
    if card_token_ and any_card_token(cfg, external_id) == card_token_:
        return True
    if card_surnames and (_name_surname_tokens(name) & card_surnames):
        return True
    return False


def combat_status(latest_commence, now) -> str:
    """upcoming / live / settled for a card from its latest fight's commence time
    (fight night spans a few hours). Conservative: no time → upcoming."""
    if latest_commence is None:
        return "upcoming"
    try:
        hours = (latest_commence - now).total_seconds() / 3600
    except TypeError:
        return "upcoming"
    if hours < -6:  # card finished (> ~6h after the main event started)
        return "settled"
    if hours <= 8:  # fight night window
        return "live"
    return "upcoming"


def derive_concept(
    cfg: CombatSportConfig,
    external_id: str | None,
    name: str | None,
    n_outcomes: int | None = None,
) -> dict | None:
    """From a single matched card FIGHT market, derive its card-concept descriptor
    (key/name/domain/is_major) for search + typeahead. None if the market isn't a
    card fight. The fight ticker is signal enough, so `n_outcomes` is optional."""
    token = card_token(cfg, external_id)
    if token is None or (n_outcomes is not None and n_outcomes != 2):
        return None
    label, is_major = card_label(cfg, name, ())
    return {
        "key": f"event:{cfg.domain}:{token}",
        "name": label or name,
        "domain": cfg.domain,
        "is_major": is_major,
        "card_token": token,
    }


async def _list_event_bouts(
    cfg: CombatSportConfig, db: AsyncSession, now, *, since_hours: int = 36
):
    """Betting-odds-first schedule source: scheduled/live bouts from the EVENTS
    table for this combat sport, grouped by card date-token (aligned with the
    Kalshi ticker token via :func:`event_commence_token`). Returns
    ``{token: [Event, ...]}`` (each list sorted by commence_time). Empty when the
    sport has no ``events_sport_key``.

    This is the T-5 source: the Odds API schedules a card (and prices the fights)
    days before Kalshi lists it, and the events-table ``commence_time`` is the real
    fight-start signal — unlike Kalshi's ``commence_time`` (resolution/close date,
    gotcha #14). Only bouts commencing within ``[now - since_hours, ∞)`` so a card
    that finished last night still resolves while genuinely old cards defer to the
    Kalshi path. Read-only, best-effort."""
    if not cfg.events_sport_keys:
        return {}

    from datetime import timedelta

    from app.models import Event, Sport

    floor = now - timedelta(hours=since_hours)
    events = list(
        (
            await db.execute(
                select(Event)
                .join(Sport, Event.sport_id == Sport.id)
                .where(
                    Sport.key.in_(cfg.events_sport_keys),
                    Event.commence_time.isnot(None),
                    Event.commence_time >= floor,
                )
                .order_by(Event.commence_time)
            )
        )
        .scalars()
        .all()
    )

    bouts: dict[str, list] = {}
    for ev in events:
        # Degenerate single-fighter rows (home == away) aren't a real bout — the
        # merge task folds them into the two-sided event (gotcha: combat merge).
        home = (ev.home_team_name or "").strip()
        away = (ev.away_team_name or "").strip()
        if not home or not away or home.lower() == away.lower():
            continue
        token = event_commence_token(ev.commence_time)
        if token is None:
            continue
        bouts.setdefault(token, []).append(ev)

    # Sort each card's bouts ascending by commence — the main event (latest) caps
    # the night. Self-contained (not reliant on the query's ORDER BY).
    for group in bouts.values():
        group.sort(key=lambda e: e.commence_time)
    return bouts


async def list_card_concepts(
    cfg: CombatSportConfig,
    db: AsyncSession,
    *,
    statuses: tuple[str, ...] = ("upcoming", "live"),
    limit: int = 20,
) -> list[dict]:
    """Enumerate CARD concepts (not query-driven) for the sports feed — group open
    fight markets by card date-token, one descriptor per card. Returns lightweight
    dicts the feed scorer turns into candidates:

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
                    FuturesMarket.llm_sport_category == cfg.llm_category,
                    FuturesMarket.status == "open",
                )
            )
        ).all()
    )

    # Group fight markets by card token.
    cards: dict[str, dict] = {}
    for mid, ext_id, name, commence, meta in rows:
        token = card_token(cfg, ext_id)
        if token is None:
            continue  # not a fight ticker (prop/future) — cards are keyed by fights
        c = cards.setdefault(token, {"token": token, "fights": [], "titles": []})
        evt_title = (meta or {}).get("event_title") if isinstance(meta, dict) else None
        c["fights"].append({"id": mid, "name": name, "commence": commence})
        if evt_title:
            c["titles"].append(evt_title)

    # Betting-odds-first schedule source: scheduled bouts from the events table.
    # It surfaces a card days before Kalshi lists it, and its commence_time is the
    # authoritative fight-start — Kalshi's is the resolution/close date (gotcha #14),
    # which otherwise leaves a live card reading "upcoming" long after it ends.
    event_bouts = await _list_event_bouts(cfg, db, now)

    def _ct(f):
        return f["commence"] or datetime.min.replace(tzinfo=timezone.utc)

    concepts: list[dict] = []
    for token in set(cards) | set(event_bouts):
        kalshi = cards.get(token)
        bouts = event_bouts.get(token) or []

        # Authoritative schedule: prefer the events-table fight time; fall back to
        # the Kalshi main-event commence only when no scheduled bout exists.
        if bouts:
            latest = bouts[-1].commence_time  # _list_event_bouts sorts ascending
        elif kalshi and kalshi["fights"]:
            kalshi["fights"].sort(key=_ct)
            latest = kalshi["fights"][-1]["commence"]
        else:
            continue

        status = combat_status(latest, now)
        if status not in statuses:
            continue

        # Name/numbering: Kalshi carries the numbered-card label ("UFC 329") and
        # event_titles; events rows only carry fighter names, so an events-only card
        # falls through to its headline bout ("Du Plessis vs Usman", is_major=False).
        if kalshi and kalshi["fights"]:
            kalshi["fights"].sort(key=_ct)
            main = kalshi["fights"][-1]
            label, is_major = card_label(cfg, main["name"], tuple(kalshi["titles"]))
            main_id = main["id"]
            fight_count = len(kalshi["fights"])
            name = label or main["name"]
        else:
            main_bout = bouts[-1]
            headline = f"{main_bout.home_team_name} vs {main_bout.away_team_name}"
            label, is_major = card_label(cfg, headline, ())
            main_id = None
            fight_count = len(bouts)
            name = label or headline

        concepts.append(
            {
                "key": f"event:{cfg.domain}:{token}",
                "name": name,
                "domain": cfg.domain,
                "status": status,
                "start_date": latest.isoformat() if latest is not None else None,
                "is_major": is_major,
                "fight_count": fight_count,
                "main_event_id": main_id,
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


class CombatEventAdapter:
    """Event-concept adapter for a combat sport (co_equal_list). One instance per
    sport, parameterized by a CombatSportConfig; `self.domain` keys the registry."""

    def __init__(self, cfg: CombatSportConfig):
        self.cfg = cfg
        self.domain = cfg.domain

    async def build_event(self, slug: str, db: AsyncSession) -> dict | None:
        from datetime import datetime, timezone

        from app.models import FuturesMarket

        cfg = self.cfg
        now = datetime.now(timezone.utc)
        target = re.sub(r"[^a-z0-9]", "", (slug or "").lower())
        if not target:
            return None

        q = (
            select(FuturesMarket)
            .options(selectinload(FuturesMarket.outcomes))
            .where(
                FuturesMarket.llm_sport_category == cfg.llm_category,
                FuturesMarket.status == "open",
            )
        )
        markets = list((await db.execute(q)).scalars().unique().all())

        # Collect this card's Kalshi FIGHTS: ticker date-token == slug AND two-sided.
        fights = []
        for m in markets:
            if card_token(cfg, m.external_id) != target:
                continue
            if len(m.outcomes or []) != 2:  # a real fight is two-sided
                continue
            fights.append(m)

        # Betting-odds-first schedule (events table): the authoritative fight-start
        # time (overrides Kalshi's close date, gotcha #14) and the sole source for a
        # card that Kalshi hasn't listed yet (T-5, before it floods).
        bouts = (await _list_event_bouts(cfg, db, now)).get(target) or []

        if not fights:
            # No Kalshi markets for this card — resolve from the schedule alone.
            if bouts:
                return self._build_events_envelope(target, bouts, now)
            return None

        # Headline fight = latest commence_time (the main event caps the night).
        def _ct(m):
            return m.commence_time or datetime.min.replace(tzinfo=timezone.utc)

        fights.sort(key=_ct)
        main_event = fights[-1]
        latest_commence = main_event.commence_time

        # Prefer the events-table fight time for the card's schedule + status — a
        # Kalshi-only commence is the resolution/close date and would leave a card
        # that already fought reading "upcoming" for days (gotcha #14).
        authoritative_commence = bouts[-1].commence_time if bouts else latest_commence

        def _fight_outcomes(m):
            outs = sorted(
                (m.outcomes or []),
                key=lambda o: float(o.current_probability or 0),
                reverse=True,
            )
            return [
                {
                    "name": o.name,
                    "probability": (
                        round(float(o.current_probability), 4)
                        if o.current_probability is not None
                        else None
                    ),
                }
                for o in outs
            ]

        # primary = the main-event fighters (co-equal, head-to-head).
        competitors = _fight_outcomes(main_event)

        def _title_of(m):
            meta = getattr(m, "market_metadata", None)
            return (meta or {}).get("event_title") if isinstance(meta, dict) else None

        # Numbered-card naming ("UFC 329") with Fight-Night / headline fallback,
        # derived from the fights' names + Kalshi event_titles. Boxing (unnumbered)
        # falls straight through to the headline-bout name.
        card_titles = tuple(t for t in (_title_of(m) for m in fights) if t)
        card_name, is_major = card_label(cfg, main_event.name, card_titles)
        card_number_ = card_number(cfg, main_event.name, *card_titles)

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
                "kind": kind,  # "fight" | "prop" — frontend splits the rail
                "settled": settled,
                "probability": lead_prob,
                "outcomes": outs,
            }
            if prop_type:
                row["prop_type"] = prop_type
            return row

        # children = every fight on the card (matchup rail). Settled when decided.
        children = [_child(m, "fight") for m in fights]

        # PROPS — method / rounds / distance / occurrence from Kalshi AND Polymarket,
        # tied to this card by number, shared date-token, or a card fighter surname.
        # Matchup-shaped markets are excluded (cross-source fight dup + the
        # bundled-negrisk shape).
        fight_ids = {m.id for m in fights}
        props = []
        for m in markets:
            if m.id in fight_ids:
                continue
            if _MATCHUP_RE.search(m.name or ""):
                continue
            prop_type = classify_prop(cfg, m.external_id, m.name)
            if prop_type is None:
                continue
            if not _prop_belongs_to_card(
                cfg, m.name, m.external_id, card_number_, target, card_surnames
            ):
                continue
            props.append(_child(m, "prop", prop_type))

        # Stable prop ordering: by type (method, rounds, distance, occurrence).
        _ptype_order = {"method": 0, "rounds": 1, "distance": 2, "occurrence": 3}
        props.sort(key=lambda p: (_ptype_order.get(p.get("prop_type"), 9), p["market_id"]))

        children.extend(props)

        sections = [
            {
                "type": "matchup",
                "label": "Fights",
                "market_ids": [m.id for m in fights],
            }
        ]
        if props:
            sections.append(
                {
                    "type": "props",
                    "label": "Props",
                    "market_ids": [p["market_id"] for p in props],
                }
            )

        return {
            "event": {
                "key": f"event:{cfg.domain}:{target}",
                "domain": cfg.domain,
                "name": card_name or main_event.name,  # numbered/Fight-Night card
                "status": combat_status(authoritative_commence, now),
                "start_date": (
                    authoritative_commence.isoformat()
                    if authoritative_commence is not None
                    else None
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

    def _build_events_envelope(self, target: str, bouts: list, now) -> dict:
        """Pre-Kalshi envelope for a card that exists only in the events table
        (betting-odds-first). Same co_equal_list shape as the Kalshi path, but
        probabilities come from the aggregated event win-prob (Odds API/ESPN) and
        there is no futures market to chart — so `evolution_market_id` is None and
        the frontend renders the two-sided split bar without a history timeline.

        `bouts` are Event ORM rows for this card (sorted ascending by commence),
        home/away_team_name = the two fighters. `market_id` on children carries the
        Event PK purely as a stable render key — NOT a FuturesMarket id."""
        from app.utils.aggregation import compute_aggregate_probability

        cfg = self.cfg

        def _competitors(ev):
            home_prob = compute_aggregate_probability(ev, ev.status)
            if home_prob is not None:
                home_prob = max(0.0, min(1.0, float(home_prob)))
                pair = [
                    {"name": ev.home_team_name, "probability": round(home_prob, 4)},
                    {"name": ev.away_team_name, "probability": round(1.0 - home_prob, 4)},
                ]
            else:
                pair = [
                    {"name": ev.home_team_name, "probability": None},
                    {"name": ev.away_team_name, "probability": None},
                ]
            return sorted(
                pair,
                key=lambda o: o["probability"] if o["probability"] is not None else -1.0,
                reverse=True,
            )

        main_bout = bouts[-1]  # latest commence caps the night
        latest_commence = main_bout.commence_time

        def _child(ev):
            outs = _competitors(ev)
            lead_prob = outs[0]["probability"] if outs else None
            return {
                "market_id": ev.id,  # Event PK — render key only, not a futures id
                "market_name": f"{ev.home_team_name} vs {ev.away_team_name}",
                "source": "events",  # data-only (audit); not rendered
                "kind": "fight",
                "settled": ev.status in ("completed", "closed"),
                "probability": lead_prob,
                "outcomes": outs,
            }

        children = [_child(ev) for ev in bouts]
        headline = f"{main_bout.home_team_name} vs {main_bout.away_team_name}"
        card_name, is_major = card_label(cfg, headline, ())

        return {
            "event": {
                "key": f"event:{cfg.domain}:{target}",
                "domain": cfg.domain,
                "name": card_name or headline,
                "status": combat_status(latest_commence, now),
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
                "competitors": _competitors(main_bout),
                "evolution_market_id": None,  # no futures market yet → no timeline
            },
            "sections": [
                {
                    "type": "matchup",
                    "label": "Fights",
                    "market_ids": [ev.id for ev in bouts],
                }
            ],
            "children": children,
            "movers": [],
        }
