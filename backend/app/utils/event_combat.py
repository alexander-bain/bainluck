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
from app.utils.name_normalization import clean_slug
from app.utils.settledness import price_converged, settled_under_assigned_state

# ---------------------------------------------------------------------------
# Shared (domain-agnostic) grammar — the same for every combat sport.
# ---------------------------------------------------------------------------

# A Kalshi card date-token (`YYMONDD`, e.g. "26jul18"), lowercased. Used to make the
# resolver tolerant of a HUMAN slug (L2-113): a pretty URL like
# `ufc-329-mcgregor-vs-holloway-26jul18` still resolves because the date-token — the
# real card identity — is extracted from it (the headliner prefix is decorative).
_DATE_TOKEN_RE = re.compile(r"\d{2}[a-z]{3}\d{2}")


def card_slug(card_name: str | None, token: str) -> str:
    """Human, URL-safe card slug: `<clean headliner>-<date-token>` (L2-113), so a
    combat card URL reads `.../ufc-329-mcgregor-vs-holloway-2-26jul18` instead of the
    cryptic bare token. Falls back to the bare token when there's no name to slug.
    The trailing token keeps the slug self-resolving (see `_DATE_TOKEN_RE`)."""
    base = clean_slug(card_name or "")
    return f"{base}-{token}" if base else token

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


#: A fight night's bouts run back to back — measured spacing on production
#: 2026-09-04 is 15-30 minutes between bouts, and the longest real gap inside one
#: card (prelims → main card) is under three hours. Two groups of bouts on
#: ADJACENT UTC dates that are closer together than this are one card that
#: crossed midnight, not two cards.
ROLLOVER_MAX_GAP_HOURS = 4

#: `YYMONDD` back to a date, for the adjacency half of the same test.
_TOKEN_RE = re.compile(r"^(\d{2})([a-z]{3})(\d{2})$")


def token_date(token: str | None):
    """The calendar date a card date-token names, or None if it isn't one.

    The inverse of `event_commence_token`, and it exists for one caller:
    deciding whether two tokens are ADJACENT days. Nothing else may infer a
    date from a token — a Kalshi ticker's date is the card's local date and its
    `commence_time` is the resolution date (gotcha #14), so the two disagree
    routinely and only the adjacency question is safe to ask of the string.
    """
    from datetime import date

    if not token:
        return None
    m = _TOKEN_RE.match(token.strip().lower())
    if not m:
        return None
    yy, mon, dd = m.groups()
    try:
        return date(2000 + int(yy), _MONTHS.index(mon) + 1, int(dd))
    except (ValueError, IndexError):
        return None


def fold_rollover_tokens(
    token_span: dict[str, tuple],
    *,
    max_gap_hours: int = ROLLOVER_MAX_GAP_HOURS,
) -> dict[str, str]:
    """Map every card date-token to the token that SURVIVES it.

    ux/1070 item 2 / #1712 shape 1. A card is grouped by a UTC calendar date,
    and a US fight night does not respect one: the Sept 19 card ran
    22:15→03:15 UTC, so its prelims minted `event:ufc:26sep19` (6 fights) and
    its main card — including the main event, Pantoja vs Van — minted
    `event:ufc:26sep20` (7 fights). Alex saw the result as "six UFC cards
    scattered" on one page. Measured on production 2026-09-04, four of the
    eleven UFC concepts were the spillover halves of cards already listed:
    26sep06 (1 fight, 2h55 after 26sep05's last), 26sep13 (3, 15 min),
    26sep20 (7, 30 min) and 26sep23 (2, 20 min).

    `token_span` is ``{token: (earliest_commence, latest_commence)}`` over every
    bout the token holds, from BOTH sources — the fold has to be computed once
    over the union or the Kalshi half and the events half could disagree about
    which card a bout belongs to.

    A day-later token folds into its predecessor when BOTH hold:

    * the two tokens name ADJACENT calendar days, and
    * the later group's first bout is within ``max_gap_hours`` of the earlier
      group's last bout.

    Adjacency alone would merge any two consecutive nights; contiguity alone
    would merge a late US card into an Asian afternoon card on the same date.
    Folds chain (a card spanning three tokens collapses onto the first), and a
    token with no predecessor to fold into maps to itself — so the return value
    is total and callers never need a `.get(token, token)`.
    """
    from datetime import timedelta

    survivor: dict[str, str] = {t: t for t in token_span}
    dated = [
        (token_date(t), t)
        for t in token_span
        if token_date(t) is not None and all(token_span[t])
    ]
    dated.sort()
    by_date = {d: t for d, t in dated}
    gap = timedelta(hours=max_gap_hours)

    for day, token in dated:
        previous = by_date.get(day - timedelta(days=1))
        if previous is None:
            continue
        earlier_last = token_span[previous][1]
        later_first = token_span[token][0]
        try:
            if later_first - earlier_last > gap or later_first < earlier_last:
                continue
        except TypeError:  # naive/aware mix — never fold on an unanswerable test
            continue
        # Chase the chain so three tokens of one long night land on the first.
        root = survivor[previous]
        while survivor[root] != root:
            root = survivor[root]
        survivor[token] = root

    return survivor


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


def fight_child_settled(lead_prob: float | None, card_settled: bool) -> bool:
    """Is this fight/prop child settled? (#1803, second reachable instance.)

    Two independent signals, OR-ed — and the order of the argument list is the
    point: the card's ASSIGNED status comes first because it is authoritative,
    and the price test is a fallback inference for a card still in play.

    The price test alone — "converged to >=0.97 or <=0.03, so the fight must be
    over" — was the only settled signal a futures-sourced fight ever got. It
    fails on exactly the fights it most needs to grade: MEASURED on production
    v3790, `event:ufc:26aug08` (Fight Night: Gamrot vs Salkilld, fought
    2026-08-09, card status `settled`) still rendered "Johns vs Rosas" at
    0.54/0.44 and a KO prop at 0.505/0.495. Both are coin-flips — the furthest a
    price can be from convergence — so the markets that resolved LEAST cleanly
    were the ones that kept looking live.

    `or`, never a replacement: a card in play has `card_settled` False and the
    price test decides exactly as it always did, so this can only ever make a
    child MORE settled, never less. An in-play fight is unreachable by the new
    term.

    UX-P069: the shape now lives in `app.utils.settledness`, which is where the
    other five adapters reach it. `card_settled` is a genuinely ASSIGNED term
    (`combat_status` off the card's authoritative commence time), not a second
    price test — that distinction is what the authority's docstring is about.
    Behaviour here is unchanged; this call site is the reference one.
    """
    return settled_under_assigned_state(
        inferred=price_converged(lead_prob), assigned_settled=card_settled
    )


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
    rows: list | None = None,
) -> list[dict]:
    """Enumerate CARD concepts (not query-driven) for the sports feed — group open
    fight markets by card date-token, one descriptor per card. Returns lightweight
    dicts the feed scorer turns into candidates:

        {key, name, domain, status, start_date, is_major, fight_count,
         main_event_id, latest_commence}

    Read-only, best-effort. Mirrors _score_golf_tournaments' "pull my own data,
    emit candidates" pattern — no dependency on the request-path futures pools.

    `rows` is LAT-P094's accelerator: the concept tier reads every source's open
    markets in one scan and hands each lister its slice, because this read alone
    visited 50,749 rows to emit 168 and ran once per source. Passing nothing
    keeps the standalone read — the /event adapters and the suites use it."""
    from datetime import datetime, timezone

    from app.utils.event_concept_population import (
        COMBAT_PROJECTION,
        select_open_markets,
    )

    now = datetime.now(timezone.utc)
    if rows is None:
        rows = await select_open_markets(db, cfg.llm_category, COMBAT_PROJECTION)

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

    # #1712 shape 1 / ux/1070 item 2: collapse a card that crossed midnight UTC
    # back into ONE card. Computed over both sources' times together (see
    # `fold_rollover_tokens`) and applied to both dicts, so a Kalshi fight and
    # the events row for the same bout cannot end up on different cards.
    _spans: dict[str, tuple] = {}
    for token, card in cards.items():
        times = sorted(f["commence"] for f in card["fights"] if f["commence"])
        if times:
            _spans[token] = (times[0], times[-1])
    for token, group in event_bouts.items():
        times = sorted(e.commence_time for e in group if e.commence_time)
        if not times:
            continue
        first, last = times[0], times[-1]
        if token in _spans:
            first = min(first, _spans[token][0])
            last = max(last, _spans[token][1])
        _spans[token] = (first, last)
    _survivor = fold_rollover_tokens(_spans)
    if any(t != s for t, s in _survivor.items()):
        folded_cards: dict[str, dict] = {}
        for token, card in cards.items():
            keep = _survivor.get(token, token)
            target = folded_cards.setdefault(
                keep, {"token": keep, "fights": [], "titles": []}
            )
            target["fights"].extend(card["fights"])
            target["titles"].extend(card["titles"])
        cards = folded_cards
        folded_bouts: dict[str, list] = {}
        for token, group in event_bouts.items():
            folded_bouts.setdefault(_survivor.get(token, token), []).extend(group)
        for group in folded_bouts.values():
            group.sort(key=lambda e: e.commence_time)
        event_bouts = folded_bouts

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
    concepts = concepts[:limit]
    await _attach_headline_bouts(db, concepts)
    return concepts


async def _attach_headline_bouts(db: AsyncSession, concepts: list[dict]) -> None:
    """Give each card its MAIN EVENT: two fighters, two numbers.

    ux/1070 item 2. A fight card was shipping the shape of an outright race —
    one name and one percentage, drawn from `_resolve_concept_leader`, which
    reads the card's whole competitor list and returns its top entry. On a
    field of 30 cyclists that is the favourite. On a card of ten two-sided
    fights it is *the most lopsided fight on the card*, and it is routinely not
    even in the bout the card is named after: measured on production
    2026-09-04, `event:ufc:26sep10` was titled "Alexandre Pantoja vs Joshua Van"
    and led with "Tai Tuivasa 84%", who is in a different fight.

    A bout is the GAME archetype — two participants, two numbers, a date — so
    the card carries its main event as one, and the renderer stops borrowing
    the outright hero. Both sides come from the SAME two-sided market, so they
    are one market's own pair and cannot be assembled from two sources into a
    sum that is not 100 (#2582's class).

    One batched read for every card in the page, best-effort: a card whose main
    event has no priced market simply has no `headline_bout` and falls back to
    exactly what it rendered before.
    """
    main_ids = [c["main_event_id"] for c in concepts if c.get("main_event_id")]
    if not main_ids:
        return

    from app.models import FuturesMarket

    try:
        markets = list(
            (
                await db.execute(
                    select(FuturesMarket)
                    .options(selectinload(FuturesMarket.outcomes))
                    .where(FuturesMarket.id.in_(main_ids))
                )
            )
            .scalars()
            .unique()
            .all()
        )
    except Exception:  # a hero is never worth failing the tier for
        return

    by_id = {m.id: m for m in markets}
    for concept in concepts:
        market = by_id.get(concept.get("main_event_id"))
        outcomes = list(getattr(market, "outcomes", None) or [])
        if len(outcomes) != 2:
            continue  # not a two-sided bout — leave the card as it was
        outcomes.sort(key=lambda o: float(o.current_probability or 0), reverse=True)
        competitors = [
            {
                "name": o.name,
                "probability": (
                    round(float(o.current_probability), 4)
                    if o.current_probability is not None
                    else None
                ),
            }
            for o in outcomes
        ]
        if not all(c["name"] and c["probability"] is not None for c in competitors):
            continue  # half a bout is not a bout
        concept["headline_bout"] = {
            "competitors": competitors,
            "commence_time": (
                market.commence_time.isoformat() if market.commence_time else None
            ),
        }


class CombatEventAdapter:
    """Event-concept adapter for a combat sport (co_equal_list). One instance per
    sport, parameterized by a CombatSportConfig; `self.domain` keys the registry."""

    def __init__(self, cfg: CombatSportConfig):
        self.cfg = cfg
        self.domain = cfg.domain

    def _folded_card_tokens(self, target: str, markets, bouts_by_token) -> set[str]:
        """Every date-token that belongs to the card the slug names.

        One token in the ordinary case; two when the card crossed midnight UTC
        (#1712 shape 1). Either half of a folded card resolves to the whole of
        it, so the pre-fold link keeps working.
        """
        spans: dict[str, tuple] = {}

        def _widen(token, when):
            if token is None or when is None:
                return
            first, last = spans.get(token, (when, when))
            spans[token] = (min(first, when), max(last, when))

        for m in markets:
            if len(m.outcomes or []) != 2:
                continue
            _widen(card_token(self.cfg, m.external_id), m.commence_time)
        for token, group in bouts_by_token.items():
            for bout in group:
                _widen(token, bout.commence_time)

        survivor = fold_rollover_tokens(spans)
        root = survivor.get(target, target)
        tokens = {t for t, s in survivor.items() if s == root}
        tokens.add(target)
        return tokens

    async def build_event(self, slug: str, db: AsyncSession) -> dict | None:
        from datetime import datetime, timezone

        from app.models import FuturesMarket

        cfg = self.cfg
        now = datetime.now(timezone.utc)
        target = re.sub(r"[^a-z0-9]", "", (slug or "").lower())
        if not target:
            return None
        # L2-113: accept a human slug (`ufc-329-mcgregor-vs-holloway-26jul18`) by
        # extracting the card date-token — the real identity — from it. A bare token
        # ("26jul18") already IS the token, so this is a no-op for legacy links.
        _tok = _DATE_TOKEN_RE.search(target)
        if _tok:
            target = _tok.group(0)

        q = (
            select(FuturesMarket)
            .options(selectinload(FuturesMarket.outcomes))
            .where(
                FuturesMarket.llm_sport_category == cfg.llm_category,
                FuturesMarket.status == "open",
            )
        )
        markets = list((await db.execute(q)).scalars().unique().all())

        # Betting-odds-first schedule (events table): the authoritative fight-start
        # time (overrides Kalshi's close date, gotcha #14) and the sole source for a
        # card that Kalshi hasn't listed yet (T-5, before it floods).
        bouts_by_token = await _list_event_bouts(cfg, db, now)

        # #1712 shape 1: this page is grouped by the SAME token the feed card is,
        # so it folds a midnight-crossing card the same way — computed here from
        # the same two sources rather than passed in, because the two callers
        # never share a request. Without this the feed would offer one card of 13
        # fights and the page behind it would answer with the 6 that happened
        # before midnight; a stale link to the spillover token resolves onto the
        # whole card instead of half of it.
        card_tokens = self._folded_card_tokens(target, markets, bouts_by_token)

        # Collect this card's Kalshi FIGHTS: ticker date-token on the card AND
        # two-sided.
        fights = []
        for m in markets:
            if card_token(cfg, m.external_id) not in card_tokens:
                continue
            if len(m.outcomes or []) != 2:  # a real fight is two-sided
                continue
            fights.append(m)

        bouts = sorted(
            (b for t in card_tokens for b in bouts_by_token.get(t, [])),
            key=lambda e: e.commence_time,
        )

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

        # #1803, second reachable instance — found by censusing the class rather
        # than trusting its golf-shaped scoping. The card's ASSIGNED status is
        # computed below for `event.status`; it is hoisted here because `_child`
        # needs it to floor its own settled inference. Same authority, one call.
        card_settled = combat_status(authoritative_commence, now) == "settled"

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
            # #1803: assigned card status first, price inference as the fallback.
            # Pure + unit-tested in `fight_child_settled` (this builder is a large
            # async closure, so the policy lives outside it — ruling 005).
            settled = fight_child_settled(lead_prob, card_settled)
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
                # L2-113: pretty, self-resolving URL slug (headliner + date-token).
                "slug": card_slug(card_name or main_event.name, target),
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
                # L2-113: pretty, self-resolving URL slug (headliner + date-token).
                "slug": card_slug(card_name or headline, target),
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
