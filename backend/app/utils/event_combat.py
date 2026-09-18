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
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.utils.event_matcher import player_key
from app.utils.feed_market_quality import bout_price_is_supported
from app.utils.futures_market_snapshot import concept_price_observed_at_iso
from app.utils.graded_card import rendered_duel_percents
from app.utils.name_normalization import clean_slug, strip_diacritics
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
    number_re: re.Pattern | None = (
        None  # numbered-card pattern (MMA); None = unnumbered
    )
    number_label: str = ""  # prefix for a numbered card, e.g. "UFC" → "UFC 329"
    strip_re: re.Pattern | None = None  # leading card-prefix to strip from a subtitle
    fight_night_re: re.Pattern | None = (
        None  # "Fight Night" detection (MMA); None = off
    )
    fight_night_label: str = "Fight Night"
    # Sports.key(s) of the schedule (events table) source: scheduled bouts (Odds API/
    # ESPN/StatPal) that surface a card BEFORE Kalshi lists it, and whose fight-start
    # time is authoritative over Kalshi's resolution/close date (gotcha #14). Empty
    # disables the events-table source. MMA spans two keys (mma_ufc +
    # mma_mixed_martial_arts); boxing is ("boxing_boxing",).
    events_sport_keys: tuple[str, ...] = ()
    # #5603/#2602: what a card's CHIP may assert, by the evidence behind it —
    # see :func:`card_sport_label`. `domain` is OUR routing token and is never a
    # claim a source made; these are. All empty (the default, and boxing) = this
    # sport says nothing and every renderer keeps printing the domain.
    promotion_label: str = ""  # a venue's own series/title proves it, e.g. "UFC"
    schedule_label: str = ""  # all the schedule source asserts, e.g. "MMA"
    generic_label: str = ""  # a venue names some OTHER promotion, e.g. "Combat"


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
    promotion_label: str = "",
    schedule_label: str = "",
    generic_label: str = "",
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
        promotion_label=promotion_label,
        schedule_label=schedule_label,
        generic_label=generic_label,
    )


# ---------------------------------------------------------------------------
# Pure helpers (per-domain via cfg) — unit-tested.
# ---------------------------------------------------------------------------


# Lowercase 3-letter month abbreviations — locale-independent (strftime("%b") is
# locale-dependent). Used to build a card date-token from an events-table bout's
# commence_time that ALIGNS with the Kalshi ticker token (`YYMONDD`, e.g. 26JUL18).
_MONTHS = (
    "jan",
    "feb",
    "mar",
    "apr",
    "may",
    "jun",
    "jul",
    "aug",
    "sep",
    "oct",
    "nov",
    "dec",
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
        return (
            f"{commence.year % 100:02d}{_MONTHS[commence.month - 1]}{commence.day:02d}"
        )
    except (AttributeError, IndexError, TypeError):
        return None


#: A fight night's bouts run back to back — measured spacing on production
#: 2026-09-04 is 15-30 minutes between bouts, and the longest real gap inside one
#: card (prelims → main card) is under three hours. Two groups of bouts on
#: ADJACENT UTC dates that are closer together than this are one card that
#: crossed midnight, not two cards.
ROLLOVER_MAX_GAP_HOURS = 4

#: `YYMONDD` back to a date, for the adjacency half of the same test, plus the
#: optional promotion suffix a venue-scoped card token carries (`venue_card_token`
#: mints `26sep26ufcfightnight`). The suffix is captured rather than tolerated so
#: the fold can refuse to cross between two promotions — see `token_scope`.
_TOKEN_RE = re.compile(r"^(\d{2})([a-z]{3})(\d{2})([a-z0-9]*)$")


def token_scope(token: str | None) -> str:
    """The promotion suffix of a venue-scoped card token, or "" for a bare one.

    #2602 follow-up (codex Brief15). `fold_rollover_tokens` asks its adjacency
    question of scoped tokens too, and must only ever ask it against a token of
    the SAME scope: a scoped card never folds into another promotion's night,
    and never into a bare date token — that join is a cross-source identity
    claim and needs bout evidence, not an adjacent date.

    A bare Kalshi-ticker token returns "", so the legacy population shares one
    scope and its fold behaviour is unchanged.
    """
    m = _TOKEN_RE.match((token or "").strip().lower())
    return m.group(4) if m else ""


def token_date(token: str | None):
    """The calendar date a card date-token names, or None if it isn't one.

    The inverse of `event_commence_token`, and it exists for one caller:
    deciding whether two tokens are ADJACENT days. Nothing else may infer a
    date from a token — a Kalshi ticker's date is the card's local date and its
    `commence_time` is the resolution date (gotcha #14), so the two disagree
    routinely and only the adjacency question is safe to ask of the string.

    #2602 follow-up: a venue-scoped token (`26sep26ufcfightnight`) names a date
    just as a bare one does, and answering ``None`` for it filtered every scoped
    card out of `fold_rollover_tokens` — so a venue card crossing UTC midnight
    split and could never fold back. The date is read from the leading
    `YYMONDD`; the promotion suffix is `token_scope`'s to answer, and the fold
    needs both.
    """
    from datetime import date

    if not token:
        return None
    m = _TOKEN_RE.match(token.strip().lower())
    if not m:
        return None
    yy, mon, dd = m.groups()[:3]
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
    # #2602 follow-up: keyed on (SCOPE, date), not date alone. Two promotions can
    # run the same night — Power Slap 23 and a UFC Fight Night both minted a
    # 26 Sep token — and a date-only key keeps just one of them, so the next day's
    # spillover would fold into whichever happened to survive the dict build.
    # Scoping also refuses the bare<->scoped join outright: that is a cross-source
    # identity claim, and an adjacent date is not evidence for it.
    by_date = {(token_scope(t), d): t for d, t in dated}
    gap = timedelta(hours=max_gap_hours)

    for day, token in dated:
        previous = by_date.get((token_scope(token), day - timedelta(days=1)))
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


def card_span_by_token(
    venue_times: dict[str, list],
    fight_times: dict[str, list],
) -> dict[str, tuple]:
    """``{token: (first, last)}`` for :func:`fold_rollover_tokens`, with each
    token's span on ONE time scale — never a blend of two.

    #2602. The fold asks "did this card cross midnight?", which is a question
    about fight STARTS. A venue market's ``commence_time`` is not one: Kalshi's
    is the close/resolution stamp (gotcha #14), measured ~3-4 h LATER than the
    bout it prices. Widening a token's span with both sources therefore pushed
    the earlier token's end PAST the later token's first bout, and the fold's
    own overlap guard (``later_first < earlier_last``) then refused exactly the
    card it was written for.

    Measured on production 2026-09-17, UFC 331: its 13 Kalshi tickers all carry
    the token ``26sep19`` while closing 02:00-07:20Z on Sep 20, so the blended
    span for ``26sep19`` ran to 07:20Z on the 20th — past ``26sep20``'s first
    bout at 00:15Z. `/hub/mma` served the one card twice, as "331: Van vs
    Pantoja · Sat, Sep 19 · 12 fights" beside "van vs Pantoja · Sun, Sep 20".

    So fight-start times REPLACE venue times for any token that has them, and a
    token with no scheduled bout keeps its venue span — which is all it has, and
    is self-consistent, because every ticker of one card shares the same shift.
    """
    spans: dict[str, tuple] = {}
    for source in (venue_times, fight_times):
        for token, times in source.items():
            if token is None:
                continue
            known = sorted(t for t in times if t is not None)
            if known:
                spans[token] = (known[0], known[-1])
    return spans


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


# ---------------------------------------------------------------------------
# Venue-sourced card identity (#2602) — a card token for a row with no ticker.
# ---------------------------------------------------------------------------

#: A venue bout title: ``"<promotion>: <A> vs. <B> (<weight class>, <segment>)"``.
#: Polymarket writes this shape for every combat bout it lists, and the promotion
#: is everything before the FIRST colon.
_VENUE_TITLE_RE = re.compile(r"^\s*([^:]{2,}?)\s*:\s*(\S.*?)\s*$")

#: A trailing "(Bantamweight, Main Card)" — the venue's own annotation on a
#: matchup, never part of a fighter's name.
_TRAILING_PAREN_RE = re.compile(r"\s*\([^()]*\)\s*$")


def venue_card_promotion(name: str | None) -> str | None:
    """The PROMOTION a venue bout title names, or None if it isn't a bout title.

    Two conditions, both required: a colon with something before it, and a
    MATCHUP after it. The second is what keeps the card's own props out —
    "O/U 2.5 Rounds" and "Will Theo Haig win in Round 3?" carry no colon at all,
    and a title that does carry one but no "A vs B" is not a bout either.
    """
    m = _VENUE_TITLE_RE.match(name or "")
    if not m:
        return None
    promo, matchup = m.group(1).strip(), m.group(2)
    if not promo or not _MATCHUP_RE.search(matchup):
        return None
    return promo


def venue_fight_start(meta):
    """The venue's OWN fixture instant for this row (tz-aware UTC), or None.

    Delegates to the matcher's parser rather than re-spelling the ISO read —
    :func:`app.tasks.prediction_market_matching._parse_venue_game_start` exists
    so a second reader can ask this of a metadata dict without a second parse,
    and its docstring says so. Lazily imported: `event_combat` is on the serve
    path and must not pull a task module in at import time.
    """
    from app.tasks.prediction_market_matching import _parse_venue_game_start

    return _parse_venue_game_start(meta)


def venue_card_token(cfg: CombatSportConfig, name: str | None, meta) -> str | None:
    """Card token for a venue bout row that carries no card FIGHT ticker.

    #2602. Kalshi stamps a card's identity into its ticker (`KXUFCFIGHT-26SEP19…`)
    and :func:`card_token` reads it; Polymarket has no ticker, so every one of its
    bouts produced ``None`` and **no venue-only card could form at all**. Measured
    on production 2026-09-17: 115 open MMA markets from Polymarket, **zero** with a
    card ticker, hiding three real cards we already hold rows for — UFC Fight Night
    26 Sep (11 bouts), Dana White's Contender Series 22 Sep (5), Power Slap 23
    18 Sep (1).

    The identity is the PAIR — the promotion the title names, and the venue's own
    fight date:

    * The date alone is wrong, and #4093 already proved it insufficient. The events
      table carries "Darren Till vs Yoel Romero" on 2026-09-26, a different
      promotion entirely; a date-only key swallows it into the UFC Fight Night card.
    * The promotion alone is generic — "UFC Fight Night" recurs every few weeks.

    The date comes from ``venue_game_start`` and never from ``commence_time``,
    which for a Polymarket row is Gamma's ``startDate`` — the LISTING stamp. All
    28 open MMA rows that carry both disagree: the 11 bouts of the 26 Sep card are
    stamped ``commence_time 2026-09-12 22:00``, two weeks early, so a token built
    from it scatters one card across the wrong day and the card never forms.

    **A NUMBERED card unifies onto the bare date token.** "UFC 331" is globally
    unique on its date and is exactly what the ticker path already keys, so the
    scoped token would mint a SECOND card beside the Kalshi one. The 22 open
    Polymarket "UFC 331" rows carry no ``venue_game_start`` today, so this arm is
    unreachable on current data — it is here because the arm that repairs that
    (#6758) would otherwise split a live card the day it lands.
    """
    token = event_commence_token(venue_fight_start(meta))
    if token is None:
        return None
    promo = venue_card_promotion(name)
    if promo is None:
        return None
    if card_number(cfg, promo) is not None:
        return token
    slug = re.sub(r"[^a-z0-9]", "", strip_diacritics(promo).lower())
    return f"{token}{slug}" if slug else None


def venue_bout_group(meta) -> str | None:
    """The venue's own EVENT id for this bout, so one bout counts once.

    Polymarket publishes a bout as an event-level parent row plus its
    condition-id children, and both can be named as the matchup — `61241595`
    and `61278158` are one DWCS fight. Both carry
    ``market_metadata['polymarket_event_id']``, so it is the dedupe key.
    """
    if not isinstance(meta, dict):
        return None
    raw = meta.get("polymarket_event_id")
    return str(raw) if raw not in (None, "") else None


def title_bout_sides(name: str | None) -> tuple[str, str] | None:
    """The two fighters a venue bout title names, as DISPLAY strings.

    "UFC Fight Night: Norma Dumont vs. Ailin Perez (Women's Bantamweight,
    Prelims)" -> ``("Norma Dumont", "Ailin Perez")``. The trailing parenthetical
    is the venue's annotation, not part of the second fighter's name.
    """
    m = _VENUE_TITLE_RE.match(name or "")
    if not m:
        return None
    parts = _MATCHUP_RE.split(m.group(2))
    if len(parts) != 2:
        return None
    sides = tuple(_TRAILING_PAREN_RE.sub("", p).strip() for p in parts)
    if not all(sides) or _fighter_identity(sides[0]) == _fighter_identity(sides[1]):
        return None
    return sides


def venue_bout_is_priced(name: str | None, outcome_names) -> bool:
    """Are these two outcomes the two FIGHTERS this bout's title names?

    The gate that stops a prop pair being served as a fight. A venue bout row is
    two-sided far more often than it is a moneyline: `61241597` is titled
    "Dana White's Contender Series: Norbert Növényi Jr. vs. Theo Haig" and its two
    outcomes are **"Haig in Round 3" and "Növényi Jr. in Round 2"** — two props on
    the bout, summing to nothing in particular. Counting outcomes would render
    them as the fighters' win probabilities.

    So the test is EXACT folded-name equality against the titled pair, never
    surname containment (:func:`player_key` matches both of those props to both
    fighters). Strictness fails in the safe direction: a refused pair renders as
    a bout with no prices, which is what the reader sees today anyway.
    """
    sides = title_bout_sides(name)
    if sides is None:
        return False
    got = {_fighter_identity(n) for n in outcome_names if n and str(n).strip()}
    return len(got) == 2 and got == {_fighter_identity(s) for s in sides}


def printable_probabilities(sides) -> list[float | None]:
    """The numbers these outcomes may print — one per side, in order (#6777).

    ``sides`` is an iterable of ``(probability, yes_bid, yes_ask)`` triples, the
    shape :func:`app.utils.feed_market_quality.bout_price_is_supported` takes.
    Returns the rounded value per side, or ``None`` for a side that may print no
    number, so a caller substitutes this for the
    ``round(float(p), 4) if p is not None else None`` expression it used to carry
    and nothing else about it changes.

    WHAT A READER SAW. The Power Slap 23 Discover card led with **Brandon Wilson
    50% / Brian Ellis 49.5%** off ``bid 0.0200 / ask 0.9900`` and
    ``bid 0.0100 / ask 0.9800`` (outcomes 229923170 / 229923171, production
    2026-09-17). A quote that wide locates no price at all.

    THE RULE IS NOT REDERIVED HERE, AND NEITHER IS THE QUANTIFIER. Authority owns
    both under codex's owner split for #6777: ``bout_price_is_supported`` is the
    bout-shaped call-site policy over #5247's ``is_empty_book_midpoint``, and one
    refused side refuses the pair. This module is the INTEGRATION half — where the
    question gets asked and what falls when the answer is no — so the concept path
    grows no second copy of a price rule and cannot drift from the shared one.

    🔴 ANY IS RIGHT FOR A BOUT AND WRONG FOR A LADDER, WHICH IS WHY THE PAIR RULE
    IS SCOPED TO A TWO-SIDED SET. A bout is one question with two sides: refusing
    Wilson while keeping Ellis leaves the card leading "Brian Ellis 49.5%", whose
    complement is precisely the number we just refused (#5333's defect, and
    #1860's before it). A ladder is the opposite — its rungs are separate
    questions, and dropping every rung because one has an empty book would destroy
    honest ones. ``_fight_outcomes`` serves BOTH shapes on this page: a main event
    (two sides) and method/round/distance props, which can carry more. So the pair
    rule fires only on a two-sided set, and a longer set is returned exactly as it
    is served today. No ladder policy is invented here — the concept path has never
    had one, and inventing one would be a ship nobody ruled.

    WITHHOLDING, NEVER REWRITING (gotcha #21). Nothing stored moves; the builder
    declines to publish. A rescaled or inferred price would be a number we
    invented, and ``calibration_probability`` coalesces to stored values (gotcha
    #144 / ruling 103), so an invented price becomes a forecast we are graded on.

    SETTLED NEEDS NO CARVE-OUT HERE, and that is the shared predicate's property
    rather than an omission: a graded side carries 0 or 1, a whole
    midpoint-tolerance away from any book this rule can reach, so condition 3 fails
    and the result is kept. ``futures_unsupported_price`` needs an explicit
    ``resolution_source`` exemption because it reads a trade column; this reads
    three columns of one write and cannot mistake a settlement for a quote.

    The refusal lands in a shape this module already ships and already renders:
    ``{"name": ..., "probability": None}`` is what an unpriced venue bout emits
    today, and :func:`venue_bout_is_priced`'s docstring says why that is the safe
    direction — "a refused pair renders as a bout with no prices, which is what the
    reader sees today anyway". The card keeps its bouts, its page and its fighters'
    names; it loses only the number it could not stand up.
    """
    triples = [tuple(s) for s in sides]
    values = [
        None if probability is None else round(float(probability), 4)
        for probability, _bid, _ask in triples
    ]
    if len(triples) == 2 and not bout_price_is_supported(triples):
        return [None] * len(triples)
    return values


# ---------------------------------------------------------------------------
# #6816 — the two whole percents a PROVEN bout prints, decided once, here.
# ---------------------------------------------------------------------------

#: The additive wire field. The SAME name and meaning the feed already serves on a
#: card's outcome rows (`feed._apply_card_percents`, #2060/#2088): the whole percent
#: the server rendered for this row under the card rule, never one independent
#: rounding per side. Optional on the wire — a payload cached before this shipped
#: does not carry it, and a consumer falls back WHOLE to what it printed before.
DISPLAY_PERCENT_FIELD = "rendered_percent"

#: Outcome names that are an ANSWER, not a fighter. A two-row market carrying one
#: of these is a claim, a draw leg or a ladder rung, and is never a bout's pair.
_NOT_A_FIGHTER = frozenset(
    {
        "yes",
        "no",
        "draw",
        "tie",
        "no contest",
        "nc",
        "over",
        "under",
        "other",
        "neither",
        "field",
    }
)

#: Words that make a row a PROP PHRASE rather than a person's name. Containment
#: alone is the trap `venue_bout_is_priced` documents: "Haig in Round 3" contains
#: the titled "Haig", and so would pass for the fighter. A name carries none of
#: these and no digits; a row that does is refused.
_PROP_PHRASE_WORDS = frozenset(
    {
        "in",
        "by",
        "round",
        "rounds",
        "ko",
        "tko",
        "decision",
        "submission",
        "distance",
        "points",
        "wins",
        "win",
        "to",
        "or",
        "and",
        "method",
        "finish",
        "stoppage",
    }
)

#: `FuturesMarket.market_type` values a proven bout may carry. NULL is admitted
#: because the shape backfill has not reached every row (`market_shape`'s own
#: header: the column was 100% NULL at census) — an ASSIGNED shape that is not a
#: duel is a refusal; an unassigned one is no evidence either way.
_BOUT_MARKET_TYPES = frozenset({None, "duel"})


# ---------------------------------------------------------------------------
# #6816 (Brief 22A) — the SETTLEMENT CONTRACT is the proof a pair is one question.
# ---------------------------------------------------------------------------
#
# Two rows, matching names and a sum near one are SHAPE and ARITHMETIC evidence.
# They say the rows are the two fighters; they do not say what the venue pays
# when neither fighter wins. That is the missing term, and it is not a corner
# case: a fight CAN end in a draw or a no contest, and "mutually exclusive" —
# at most one side resolves Yes — is satisfied by a rule that pays BOTH sides
# nothing on a draw. Under such a rule the two quotes are not complements: the
# draw's probability lives in the gap between them, can sit below a point, and
# a pair normalised across the band would round that third result into one
# fighter's number. Neither can a near-one sum stand in for the rule — two
# separate quotes can sum near one by coincidence.
#
# So a family's two rows may only print as ONE decision when its settlement
# contract makes the pair EXHAUSTIVE — in every way the bout can end, the two
# contracts pay out summing to the whole. That rule is not inferable from the
# row: the ingest stores no rules text, ``futures_markets.mutually_exclusive``
# DEFAULTS TO TRUE at ingest (`kalshi_api.KalshiEvent`) and in the column, and
# the shape classifier's own ``exhaustive`` verdict for a two-name duel is that
# flag read back (`market_shape._outcome_relation`: ``bool(mutually_exclusive)``).
# So it is established OUT OF BAND, from the venue's published rules, and
# recorded here per (source, fight-winner series) with the words the venue used.
#
# THE PRODUCT CONVENTIONS THIS APPLIES (existing, not new policy):
#   * Queue 299 / C119 (`precompute_calibration.EXCLUSIVITY_EVIDENCE_RULE_TEXT`,
#     `market_exclusivity_is_proved`): a pair is only ever normalised on POSITIVE
#     exclusivity evidence; the default-true `mutually_exclusive` column "is not
#     evidence"; a market that loses candidacy is not dropped — it keeps its raw
#     price. This registry is that rule at the bout-display seam.
#   * `tournament_match.threshold_labels`: a two-sided pair whose tie is a PUSH
#     (a void / refund) "does not sum to the whole and cannot be normalized into
#     a split" — the card is dropped rather than printing a number "whose meaning
#     we would be guessing". So a void / refund draw rule is a REFUSAL here, not
#     a licence; it would need its own reading, and no third win probability is
#     ever invented for it.
#   * `settled_hero.resolve_settled_hero`: the product's own drawn two-sided
#     event settles 0.5 / 0.5 with ``result="draw"`` — the pair still sums to
#     the whole. A venue rule that settles a draw the same way is the one rule
#     under which two fighter contracts ARE a complement pair in every state.
#
# WHAT IS RECORDED FOR KALSHI ``KXUFCFIGHT`` (three read-only public GETs,
# 2026-09-17 ~6:37 pm PT, verbatim bytes preserved under
# ``artifacts/other-model-combat-pair-display-execution/revision-a/kalshi-reads/``):
#   GET /trade-api/v2/series/KXUFCFIGHT — ``product_metadata.important_info``
#   (id ``UFC-RULES4``), and GET /trade-api/v2/markets?series_ticker=KXUFCFIGHT
#   &status=open — ``rules_secondary`` on all 24 open markets (the 12 bouts of
#   the 2026-09-19 card, ``KXUFCFIGHT-26SEP19…``), both quoted below. A tie or
#   no contest settles each fighter's contract at 0.50, so the pair pays
#   (1, 0), (0, 1) or (0.5, 0.5): the whole, in every result.
#
#   WHAT IS PROVED IS THE RESULT STATES, AND ONLY THOSE — a win either way, a
#   draw, a no contest. Cancellation is NOT one of them and is deliberately
#   outside this registry (authority/446, reviewing these same bytes). The
#   market-level wording is broader than the series text: "If the fight is
#   cancelled OR RESCHEDULED TO OVER TWO WEEKS AWAY, the market will resolve to
#   a fair price in accordance with the rules." Two independent fair prices are
#   not a promise that the pair pays the whole, so by this registry's own
#   standard the evidence for that state is absent and it refuses. An earlier
#   draft of this comment said `card_is_called_off` covered it; it does not —
#   that helper is card-scoped and requires EVERY bout to be off, so a single
#   bout pulled from a card that goes ahead walks past it. The per-bout gate is
#   `_bout_will_be_fought` in `CombatEventAdapter`.
#   GET /trade-api/v2/events/KXUFCFIGHT-26SEP19TSARUF confirms the flag and the
#   rule are different things: the event is ``mutually_exclusive: true`` AND
#   settles a draw 50/50 — the flag never carried the draw rule.
#
# NOT RECORDED — and therefore on the independent-display fallback, printing
# exactly what it printed before #6816: ``KXBOXING`` (its rule was not read; a
# boxing draw is live and its rule may differ) and every Polymarket bout (the
# venue branch's proof was `venue_bout_is_priced`, which is participant
# mapping, not a settlement contract). Adding a family here requires the
# venue's published rule, quoted, with the endpoint and the read date.


@dataclass(frozen=True)
class BoutSettlementContract:
    """How one fight-winner series pays out when the bout has no winner."""

    source: str  #: `FuturesMarket.source` the rule belongs to ("kalshi")
    series: str  #: the fight-winner ticker series ("KXUFCFIGHT")
    draw_rule: str  #: one line, our words: what each contract pays on a draw / NC
    rule_id: str  #: the venue's own identifier for the rule text
    read_at: str  #: ISO-8601 UTC instant of the read
    endpoints: tuple[str, ...]  #: the public URLs read, verbatim bytes kept
    verbatim: tuple[str, ...]  #: the venue's sentences, exactly as served

    @property
    def pair_sums_to_one(self) -> bool:
        """Every settlement state pays the two contracts a total of 1.00.

        Recorded as a derived property rather than a flag so a future entry
        cannot be marked complementary without writing down WHY: the rule must
        settle a draw / no contest as a half to EACH side. A void / refund rule,
        or a both-sides-No rule, is recorded but never pairs.
        """
        return self.draw_rule.startswith("each side settles at 0.50")


#: Established venue rules, keyed by (source, fight-winner series). READ-ONLY at
#: runtime. Every entry quotes the venue; none is inferred from a row.
COMPLEMENTARY_BOUT_CONTRACTS: dict[tuple[str, str], BoutSettlementContract] = {
    ("kalshi", "KXUFCFIGHT"): BoutSettlementContract(
        source="kalshi",
        series="KXUFCFIGHT",
        draw_rule=(
            "each side settles at 0.50 on a draw / no contest, so the pair pays "
            "the whole in every result"
        ),
        rule_id="UFC-RULES4",
        read_at="2026-09-18T01:37:23Z",
        endpoints=(
            "https://api.elections.kalshi.com/trade-api/v2/series/KXUFCFIGHT",
            "https://api.elections.kalshi.com/trade-api/v2/markets"
            "?series_ticker=KXUFCFIGHT&status=open&limit=40",
            "https://api.elections.kalshi.com/trade-api/v2/events/"
            "KXUFCFIGHT-26SEP19TSARUF",
        ),
        verbatim=(
            # series.product_metadata.important_info.markdown (id UFC-RULES4)
            "If the following fight ends in a draw or no contest, the market "
            "will resolve to 50/50. If the fight is cancelled, the market will "
            "resolve to a fair price for each fighter in accordance with the "
            "rules.",
            # markets[*].rules_secondary, identical clause on all 24 open markets
            "If the fight is declared a tie or no contest, the market will "
            "resolve to 50/50 for both fighters. If the fight is cancelled or "
            "rescheduled to over two weeks away, the market will resolve to a "
            "fair price in accordance with the rules.",
        ),
    ),
}

#: ``<SERIES>-<YYMONDD>…`` — the series token a ticker carries ahead of its card
#: date, with or without a ``kalshi:`` prefix (both spellings exist in the
#: column: `card_token`'s docstring shows the prefixed form, the ingest writes
#: the bare event ticker).
_TICKER_SERIES_RE = re.compile(r"(?:^|:)([A-Za-z]+)-\d{2}[A-Za-z]{3}\d{2}")


def ticker_series(external_id: str | None) -> str | None:
    """The ticker series ahead of a card date-token, uppercased, or None.

    ``"kalshi:KXUFCFIGHT-26SEP19TSARUF"`` and ``"KXUFCFIGHT-26SEP19TSARUF"`` are
    both ``"KXUFCFIGHT"``; a venue id (``"0x…"``) or a bare title is None.
    """
    if not external_id:
        return None
    m = _TICKER_SERIES_RE.search(external_id)
    return m.group(1).upper() if m else None


def bout_settlement_contract(market) -> BoutSettlementContract | None:
    """The established settlement contract for this row's family, or None.

    Read off the row in hand — its ``source`` and the series its ``external_id``
    carries — against `COMPLEMENTARY_BOUT_CONTRACTS`. None means "no venue rule
    is on record for this family", which is a refusal, never a default.
    """
    source = getattr(market, "source", None)
    series = ticker_series(getattr(market, "external_id", None))
    if not isinstance(source, str) or series is None:
        return None
    return COMPLEMENTARY_BOUT_CONTRACTS.get((source.lower(), series))


def _ticker_title_sides(name: str | None) -> tuple[str, str] | None:
    """The two sides a TICKER bout's title names, or None.

    :func:`title_bout_sides` is the venue grammar and requires the promotion
    prefix ("UFC Fight Night: A vs. B"). A ticker row is titled both ways —
    "331: Tsarukyan vs Ruffy" and a bare "Jones vs Gane" — so the prefix is
    optional here and everything else is that function's rule.
    """
    text = (name or "").strip()
    if ":" in text:
        text = text.split(":", 1)[1]
    parts = _MATCHUP_RE.split(_TRAILING_PAREN_RE.sub("", text).strip())
    if len(parts) != 2:
        return None
    first, second = (p.strip() for p in parts)
    if not first or not second:
        return None
    if _fighter_identity(first) == _fighter_identity(second):
        return None
    return first, second


def bout_sides_are_its_titled_fighters(name: str | None, outcome_names) -> bool:
    """Do these two outcome rows name the two fighters the bout's TITLE names?

    The participant-mapping half of "is this pair two sides of one question".
    A Kalshi fight row is titled by SURNAME ("331: Tsarukyan vs Ruffy") and its
    outcomes carry full names ("Arman Tsarukyan"), so this cannot be
    :func:`venue_bout_is_priced`'s exact equality — that rule is right for a
    venue row, whose title spells both fighters out, and would refuse every
    ticker bout. Here each titled side must be CONTAINED, as whole folded words,
    in exactly one outcome, and the two sides must land on two different rows.

    Strict in the safe direction: an unparseable title, a generic answer
    ("Yes", "Draw", "No Contest"), a prop phrase that merely CONTAINS a fighter
    ("Haig in Round 3"), a side that matches both rows (two fighters
    sharing the only word the title gives) or neither — all False, and a False
    here costs nothing but the pair treatment: the bout prints exactly what it
    printed before.
    """
    sides = _ticker_title_sides(name)
    if sides is None:
        return False
    rows = [_fighter_identity(n) for n in outcome_names]
    if len(rows) != 2 or not all(rows) or rows[0] == rows[1]:
        return False
    if any(r in _NOT_A_FIGHTER for r in rows):
        return False
    row_tokens = [set(r.split()) for r in rows]
    for tokens in row_tokens:
        if tokens & _PROP_PHRASE_WORDS or any(ch.isdigit() for t in tokens for ch in t):
            return False
    landed: list[int] = []
    for side in sides:
        # A bare number in a title is the rematch ordinal ("McGregor vs
        # Holloway 2"), not part of anybody's name.
        side_tokens = {t for t in _fighter_identity(side).split() if not t.isdigit()}
        if not side_tokens:
            return False
        hits = [i for i, tokens in enumerate(row_tokens) if side_tokens <= tokens]
        if len(hits) != 1:
            return False
        landed.append(hits[0])
    return sorted(landed) == [0, 1]


def ticker_bout_is_one_question(cfg: CombatSportConfig, market) -> bool:
    """Is this ticker row a bout whose two rows are two sides of ONE question?

    The issue's hypothesis ("these are two legs of one complementary question")
    is checked, not assumed. Two rows, or a sum near one, prove nothing — a prop
    pair under a matchup title is two rows (`venue_bout_is_priced`'s specimen)
    and independent binaries can sum to anything (gotcha #23). What is required,
    all of it read off the row already in hand (no new query):

    1. STABLE IDENTITY — the external id is this sport's FIGHT-WINNER series
       (`card_token`: ``KXUFCFIGHT-…``), not a method/round/distance series,
       which share the card's date token but not this prefix.
    2. SETTLEMENT CONTRACT — the row's (source, series) has a venue rule on
       record under which the two contracts pay the whole in EVERY result,
       draw and no contest included (`bout_settlement_contract`,
       `BoutSettlementContract.pair_sums_to_one`). This is the term shape and
       arithmetic cannot supply. Mutually exclusive is not it: "at most one
       side wins" is true of a rule that pays neither side on a draw, and the
       ``mutually_exclusive`` flag is default-true at ingest besides. A family
       with no rule on record is refused — missing provenance is not proof —
       and prints exactly what it printed before.
    3. ARITY — exactly two outcome rows.
    4. MARKET TYPE — an assigned shape other than ``duel``, or a flag that
       AFFIRMATIVELY says ``mutually_exclusive=False``, is contrary evidence
       and refuses. Neither a True flag nor an absent one is evidence FOR.
    5. PARTICIPANTS — the two rows ARE the two fighters the title names
       (:func:`bout_sides_are_its_titled_fighters`).

    The band in `graded_card` is then arithmetic on a pair already established
    to be one question — it removes a stale or wide quote's vig symmetrically.
    It is NOT a substitute for term 2: a third result can be priced under a
    point and still sit inside it, which is why the contract is required first.
    """
    if card_token(cfg, getattr(market, "external_id", None)) is None:
        return False
    contract = bout_settlement_contract(market)
    if contract is None or not contract.pair_sums_to_one:
        return False
    outcomes = list(getattr(market, "outcomes", None) or [])
    if len(outcomes) != 2:
        return False
    if getattr(market, "mutually_exclusive", None) is False:
        return False
    if getattr(market, "market_type", None) not in _BOUT_MARKET_TYPES:
        return False
    return bout_sides_are_its_titled_fighters(
        getattr(market, "name", None), [getattr(o, "name", None) for o in outcomes]
    )


def with_bout_display_percents(
    outcomes: list[dict], *, one_question: bool
) -> list[dict]:
    """Stamp a bout's two served rows with the whole percents they print (#6816).

    WHAT A READER SAW. `event:ufc:26sep19`, production 2026-09-17: **Arman
    Tsarukyan 74% / Mauricio Ruffy 28%**. The quotes are 0.735 / 0.275 — a
    half-cent grid, so BOTH sides sit on a rounding boundary and both round up.
    Three more bouts on the card did the same.

    THIS ADDS NO PROBABILITY POLICY. ``probability`` is returned untouched, at
    the precision it arrived with — nothing stored, charted, graded or settled
    moves, and no winner is inferred from these integers. The percents are
    `graded_card.rendered_duel_percents`, the contract three runtimes already
    share (`contracts/rendered_percent.json`): same band, same normalize →
    round the favourite once → derive the other, and outside the band each side
    rounds on its own exactly as before. `printable_probabilities` is NOT made a
    normaliser — it is shared with prop ladders and owns price support only.

    PRICE SUPPORT COMES FIRST, structurally: this runs on the OUTPUT of
    `printable_probabilities`, so a withheld leg arrives here as ``None`` and the
    pair is served as ``None`` / ``None``. No complement resurrects a refused
    side, because a percent is only ever written beside a probability that was
    already allowed to print.

    BOTH OR NEITHER. The two integers are one decision. A pair that is not a
    proven, fully priced two-sided bout gets ``None`` on both rows — never one
    served value beside a locally derived one (#2279's defect). ``None`` is
    "checked, makes no claim"; an absent key is "built before this shipped".
    Both mean the consumer prints what it always printed.
    """
    rows = [dict(o) for o in outcomes]
    percents: list[int | None] = [None] * len(rows)
    if one_question and len(rows) == 2:
        first, second = rows[0].get("probability"), rows[1].get("probability")
        if first is not None and second is not None:
            served = rendered_duel_percents(first, second)
            if all(p is not None for p in served):
                percents = served
    for row, percent in zip(rows, percents):
        row[DISPLAY_PERCENT_FIELD] = percent
    return rows


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
    subtitle = (
        _strip_card_prefix(cfg, main_event_name) or (main_event_name or "").strip()
    )

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
        if (
            re.search(rf"\b{prefix}\b", eid, re.IGNORECASE)
            or f":{prefix}-" in eid.upper()
        ):
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


#: How long after the main event's start a card is still under way. A main
#: event plus its decision, the belt and the interview runs a couple of hours;
#: six is generous and is the arm that was never wrong.
_COMBAT_CARD_RUN_HOURS = 6.0


def combat_status(latest_commence, now, earliest_commence=None) -> str:
    """upcoming / live / settled for a fight card, from its OWN first and last bouts.

    The card wears the same pulsing red `● LIVE` pill a football match at 67'
    wears (`TemporalBadge`, discover/shared.tsx), so "live" is a claim a reader
    can check by looking for a fight. The old rule opened that window a fixed
    EIGHT HOURS before the card's LATEST bout — an approximation of "the prelims
    must have started by now" that is only ever as good as the spread between the
    first bout and the last.

    Censused on production (2026-09-10, every combat card commencing in
    [-10d, +30d]) that spread is not reliable, and on the card that filed #4505 it
    is zero: `event:ufc:26sep10` carries **ten bouts all stamped
    2026-09-10 00:00:00+00**, so `latest - 8h` put the live pill on it at 16:00Z
    the day before — the issue caught it badged Live at 21:57Z on 09-09, two hours
    before its own served start. Cards with real times were not served by the
    approximation either: 09-09 ran 00:12 → 05:20, so the pill lit 52 minutes
    early there too.

    So the window is the card: **live from the first bout** until
    ``_COMBAT_CARD_RUN_HOURS`` after the last. With no first bout known,
    ``earliest_commence`` defaults to the latest, which under-claims (the pill
    waits for the main event) rather than claiming a fight that has not happened
    — the same direction as this function's standing "no time → upcoming".

    The trailing arm is unchanged and is what keeps this honest in the other
    direction: a card is not dropped as finished the moment its main event starts.
    """
    if latest_commence is None:
        return "upcoming"
    first = earliest_commence if earliest_commence is not None else latest_commence
    try:
        hours_to_last = (latest_commence - now).total_seconds() / 3600
        hours_to_first = (first - now).total_seconds() / 3600
    except TypeError:
        return "upcoming"
    # A first bout later than the last is bad data, never a schedule: fall back
    # to the pair's true order rather than opening a window that cannot close.
    if hours_to_first > hours_to_last:
        hours_to_first = hours_to_last
    if hours_to_last < -_COMBAT_CARD_RUN_HOURS:
        return "settled"  # card finished (> ~6h after the main event started)
    if hours_to_first <= 0:  # the first bout is under way or already fought
        return "live"
    return "upcoming"


#: Bout statuses that mean the fight is NOT going to be fought. Deliberately a
#: deny-list over an allow-list: `events.status` is an open vocabulary written by
#: several providers, and an unknown value must count as a real bout (today's
#: behaviour) rather than silently vanish from the card's window.
_BOUT_CALLED_OFF = frozenset(
    {"suspended", "postponed", "cancelled", "canceled", "abandoned"}
)


def _bout_going_ahead(bout) -> bool:
    """Is this bout still going to be fought? (Deny-list — see `_BOUT_CALLED_OFF`.)"""
    return (getattr(bout, "status", None) or "").strip().lower() not in _BOUT_CALLED_OFF


def card_is_called_off(bouts) -> bool:
    """Every bout on this card has been called off — the night is not happening.

    CERT-2727. Distinct from "this card has no bouts": a card we simply have no
    rows for is unknown, while a card whose every row is suspended/cancelled is
    known to be off. Only the second may never wear the live pill.
    """
    rows = [b for b in bouts if getattr(b, "commence_time", None) is not None]
    return bool(rows) and not any(_bout_going_ahead(b) for b in rows)


def card_status_from_bouts(bouts, now, *, fallback_first=None, fallback_last=None):
    """The card's status — THE sanctioned entry point for all three serve paths.

    CERT-2727 blocked the first spelling of #5603 because the all-called-off case
    was handled at the span helper, which each adapter was then free to override
    with its own fallback (and one of them did, by design, for Kalshi-only cards).
    So the rule lives here instead, ahead of any fallback, and the three call
    sites — the concept lister and both adapter envelopes — share it. An adapter
    cannot reinstate a live pill on a card that is off without deleting this call.

    ``fallback_*`` is the pair to use when we hold no bout rows of our own (a
    Kalshi-only card): unknown, not off, so it classifies exactly as before.
    """
    if card_is_called_off(bouts):
        # Terminal, so it drops out of the upcoming/live surfaces. NOT routed
        # through `combat_status`: there is no time arithmetic that can make
        # "nothing will be fought" produce a live window.
        return "settled"
    first, last = card_status_span(bouts)
    if last is None:
        first, last = fallback_first, fallback_last
    return combat_status(last, now, first)


def card_status_span(bouts):
    """The ``(first, last)`` commence pair that decides a card's LIVE window.

    #5603. `combat_status` opens the pill at the card's first bout (#4505), and
    the callers were handing it ``bouts[0]`` — the earliest row in the token,
    whatever state it is in. The token is a DATE (`event_commence_token`), so
    every bout sharing a calendar day shares a card, and on 2026-09-12 three
    suspended bouts from other promotions (01:25Z, 02:30Z, 10:00Z) sat in front
    of the UFC card proper (16:00Z → 23:45Z). `earliest` came out 01:25Z and
    "Fight Night: Silva vs Delgado" served ``status=live`` with a ``start_date``
    of 23:45Z — the pill lit **ten hours** before anything could happen, on a day
    when production carried ZERO live combat bouts.

    A card's window is the span of the fights that ACTUALLY HAPPEN, so a bout
    that has been called off is not in it. Note what is deliberately still in it:
    ``completed``/``closed`` bouts. Filtering down to "scheduled or live" is the
    tempting spelling and it is wrong in the other direction — once the prelims
    finish, the earliest surviving bout is in the future, and the card would drop
    to ``upcoming`` while the main card is on air. A false negative bought with a
    false positive is not a repair.

    Scope: this fixes a span set by a bout that will not be fought. It does NOT
    fix same-day cross-promotion grouping — a *completed* early bout from another
    promotion still shares the token and still drags the window back. That is the
    date-token key itself (#5602, lane1/D35) and is not touched here.

    Returns ``(None, None)`` when no bout is going ahead — either there are no
    usable rows at all, or every one of them has been called off. A card with no
    surviving bout has no live window to describe, so it gets no span; deciding
    what such a card IS belongs to :func:`card_status_from_bouts`, not here.

    CERT-2727: this used to fall back to the FULL span when everything was called
    off, on the docstringed reasoning that "that card is past its main event
    anyway and `combat_status`'s trailing arm still settles it". That was an
    assertion, not a measurement, and it is false for the ~6h the trailing arm
    keeps open: two suspended bouts probed at 18:00Z came back ``live``. An
    all-called-off card is precisely the one that can never be live.
    """
    rows = [b for b in bouts if getattr(b, "commence_time", None) is not None]
    going_ahead = [b for b in rows if _bout_going_ahead(b)]
    if not going_ahead:
        return None, None
    times = [b.commence_time for b in going_ahead]
    # min/max, not [0]/[-1]: the callers' sorts are total orders over the FULL
    # list, and dropping rows out of the middle must not make the pair depend on
    # which ones happened to be dropped.
    return min(times), max(times)


def _fighter_identity(name: str | None) -> str:
    """A competitor's full name folded for equality — diacritics stripped, case
    and punctuation dropped, whitespace collapsed.

    Used ONLY to decide whether two rows name the same person
    (:func:`card_rows_are_not_a_schedule`); never a display string, and never a
    cross-source match key — for that, spellings genuinely differ and
    :func:`player_key` is the right tool.
    """
    folded = strip_diacritics((name or "").strip()).lower()
    folded = re.sub(r"[^a-z0-9 ]", " ", folded)
    return " ".join(folded.split())


def card_rows_are_not_a_schedule(bouts) -> bool:
    """True when a card's OWN bout rows prove they are not a schedule (#4485/#4821).

    Two independent contradictions, required TOGETHER:

    1. **A fighter is booked twice.** Some competitor appears in two or more of
       the card's bouts. Nobody fights twice on one card, so at least one of
       those rows is not a booking (#4560 — Makhachev vs Morales *and* vs Prates,
       created two minutes apart).
    2. **Every bout is stamped at one instant.** All bouts share a single
       ``commence_time``, which is a placeholder where a schedule should be — a
       card's fights run over hours.

    **The conjunction is the whole point, and each clause alone is measurably
    unsafe.** Censused on production 2026-09-17 over every upcoming MMA and
    boxing card (30 cards, 139 bout rows):

    * *Stacked alone* would suppress **tonight's real boxing card** — four bouts
      all stamped ``22:00``, ``d+0``. A promotion that stamps its whole card at
      the broadcast time is not lying about anything.
    * *Double-booked alone* would suppress a **real 12-bout boxing card two days
      out**, where exactly one fighter (Joe Howarth) carries a duplicate row.
      One dirty row does not make the card fictional.
    * *Together* they matched **3 cards of 30, every one of them MMA and ≥106
      days out* — 2027-01-01, 2027-04-25, 2027-08-01. Every card inside 106 days
      was untouched.

    That distance is an OUTCOME of the predicate, never an input to it:
    contamination is not a function of distance (a 17-day card is contaminated
    while a 101-day card is roster-clean), so no day count is tuned here and
    none should be added. A card that is genuinely scheduled far out keeps its
    slot; a card whose rows contradict themselves loses it however near it is.

    Deliberately narrow in two more ways. It reads only the events-table roster,
    so a card the venue actually lists is never judged by it; and it needs two
    bouts, because a lone row cannot contradict itself.

    Identity is the FULL folded name, not :func:`player_key`'s surname, and the
    match must cross two bouts. Suppression's dangerous direction is the false
    POSITIVE, and a surname key has two of them: "Anderson Silva vs Thiago
    Silva" double-books itself inside one bout, and two unrelated Silvas on one
    stacked card book each other. Both are real MMA shapes. A duplicate row is
    the same provider echoing itself, so it repeats the name verbatim — all
    three live specimens match on the full name ("Islam Makhachev", "Sean
    Strickland", "Magomed Ankalaev"), and nothing is bought by looking looser.
    """
    rows = [b for b in (bouts or []) if getattr(b, "commence_time", None) is not None]
    if len(rows) < 2:
        return False

    if len({b.commence_time for b in rows}) != 1:
        return False

    seen: set[str] = set()
    for b in rows:
        # Per-bout set first: the two corners of ONE bout are never a double
        # booking, however their names normalize.
        corners = {
            key
            for key in (
                _fighter_identity(b.home_team_name),
                _fighter_identity(b.away_team_name),
            )
            if key
        }
        if corners & seen:
            return True
        seen |= corners
    return False


def card_sport_label(
    cfg: CombatSportConfig, *, ticker_fights: int, venue_promotions=()
) -> str | None:
    """The chip a card may print, decided by EVIDENCE and never by our adapter.

    #5603. Every surface that shows a card prints ``domain.upper()``, and this
    engine's MMA domain is ``ufc`` — so a Power Slap card, a Contender Series
    card and a bare sportsbook row off the umbrella ``mma_mixed_martial_arts``
    key all wear a "UFC" chip that no source ever asserted. ``domain`` is OUR
    routing token (it keys the adapter registry, the event URL and the card
    gradient); this is the separate, weaker thing a reader is allowed to be
    told. Three tiers, strongest evidence first:

    1. **A venue's own fight SERIES lists the card** (``ticker_fights`` — the
       count of rows whose ticker matched ``cfg.fight_re``, e.g. Kalshi
       ``KXUFCFIGHT-…``). The venue put the card in its UFC series, and the
       card's displayed name is derived from exactly those rows in every caller
       — so the evidence is about the card the reader is looking at, not about
       a foreign row that shares its date. -> ``cfg.promotion_label``.
    2. **A venue TITLES the bouts** (:func:`venue_card_promotion`): the
       promotion label only when EVERY title names it ("UFC Fight Night: A vs
       B"); any other named promotion -> ``cfg.generic_label``. The card's NAME
       already prints the venue's own words ("Power Slap 23"), so the chip must
       not add a claim the title did not make. On today's data a venue card's
       token carries its promotion slug (:func:`venue_card_token`), so one card
       holds one promotion and the mixed arm is unreachable through
       :func:`list_card_concepts` — it is the policy, kept total on purpose,
       and it is reachable directly (the /event adapter hands us whatever the
       card's rows carry).
    3. **Schedule rows only**: the source's sport key says mixed martial arts
       and nothing at all about who promotes it -> ``cfg.schedule_label``.
       ``events_sport_keys`` spans ``mma_ufc`` AND ``mma_mixed_martial_arts``
       and the Odds API files non-UFC bouts under both, so the key is not
       promotion evidence either.

    ``None`` when the config declares no labels (boxing, whose domain IS its
    sport): nothing is emitted and every renderer behaves exactly as before.

    This is a DISPLAY claim and nothing else — not a key, not a score, not a
    membership test. It does not certify that every bout grouped under the card
    belongs to the promotion it names (that is #5602's, and a card can still
    sweep in a foreign bout by date); it certifies only what the card itself may
    be called. "MMA" on a real UFC card is true; "UFC" on somebody else's card
    is not — so every doubt resolves downward.
    """
    if not cfg.promotion_label:
        return None
    if ticker_fights:
        return cfg.promotion_label
    promos = [p for p in (venue_promotions or ()) if p]
    if promos:
        named = re.compile(rf"^\s*{re.escape(cfg.promotion_label)}\b", re.IGNORECASE)
        if all(named.match(p) for p in promos):
            return cfg.promotion_label
        return cfg.generic_label or None
    return cfg.schedule_label or None


def bout_order_key(ev):
    """Total order over one card's bouts: `(commence_time, id)`.

    `commence_time` ALONE is not a total order over a fight card, and on most
    cards it is not an order at all. Measured on production 2026-09-10 over every
    combat card in `_list_event_bouts`' window, **7 of 18 cards carry two or more
    bouts at their latest commence**, and on `event:ufc:26sep10` the tie is total:
    all ten fights are stamped `2026-09-10 00:00:00+00`. A sort on the tied key is
    stable with respect to its INPUT, and the input is a query with no tiebreak —
    so `bouts[-1]` was whichever row Postgres happened to return last.

    See :func:`main_bout_of` for what that cost a reader.
    """
    return (ev.commence_time, ev.id)


def main_bout_of(bouts):
    """The card's MAIN EVENT — one determination, for every consumer (#4555).

    The latest bout by commence caps the night; among bouts that SHARE that
    commence, the first one we ever saw. `None` for an empty list.

    **Why this function exists rather than `bouts[-1]`.** Three consumers derived
    the main event independently — `list_card_concepts` for the card's NAME,
    `_build_events_envelope` for its `primary`, and the feed's cached envelope for
    the hero — and all three spelled it `bouts[-1]` over a commence-only sort. On
    a totally tied card that is an undefined row, so the three disagreed with each
    other and with themselves between requests. `event:ufc:26sep10` served three
    different names in one evening — "Renato Moicano vs Brian Ortega" (21:57Z),
    "Mauricio Ruffy vs Arman Tsarukyan" (00:15Z), "Alonzo Menifield vs Iwo
    Baraniewski" (00:26Z) — while its hero showed a fourth pair. Ten fights, one
    card, and the reader could not refresh twice and read the same headline.

    **Why the FIRST row of a tie and not the last.** A main event is announced and
    priced weeks before its undercard, and the rows say so: Sep 10's three oldest
    were created Aug 6 (Pantoja/Van, Tuivasa/Despaigne, Ruffy/Tsarukyan) and the
    remaining seven arrived in a single Sep 1 batch. Oldest-first names that card
    "Alexandre Pantoja vs Joshua Van" — the flyweight title fight, and the pair
    the envelope's own hero was already carrying. Newest-first would name it after
    the last prelim ingested.

    **What this does NOT claim.** The pick is stable and self-consistent, not
    authoritative: creation order is a proxy, and on a card whose bouts were all
    ingested in one batch it decides nothing in particular. A real card-name
    source has to come from the venue, which is #4485 and an ingest ship. The
    property shipped here is that the card stops contradicting itself.
    """
    bouts = list(bouts)
    if not bouts:
        return None
    latest = max(b.commence_time for b in bouts)
    return min((b for b in bouts if b.commence_time == latest), key=lambda b: b.id)


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

    # Sort each card's bouts ascending by commence, id — a TOTAL order, so the
    # fight list is the same list on every request even when a whole card shares
    # one placeholder commence (`bout_order_key`). Self-contained (not reliant on
    # the query's ORDER BY, which has no tiebreak either).
    for group in bouts.values():
        group.sort(key=bout_order_key)
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

    plus `sport_label` (#5603) for a config that declares one — the chip, by
    evidence; see :func:`card_sport_label`. Absent, never null, when the sport
    has nothing to say, so a presence test is the renderer's whole question.

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
        promo = None
        group = mid
        if token is None:
            # #2602: no card ticker — this is a venue (Polymarket) row, whose
            # card identity is the promotion its title names plus the venue's
            # OWN fight date. Its `commence_time` is the LISTING stamp and is
            # replaced here, or the card dates itself two weeks early.
            token = venue_card_token(cfg, name, meta)
            if token is None:
                continue  # a prop/future, or a row the venue gives no fixture for
            promo = venue_card_promotion(name)
            commence = venue_fight_start(meta)
            group = venue_bout_group(meta) or mid
        c = cards.setdefault(
            token,
            {"token": token, "fights": [], "titles": [], "promotions": [], "ticker": 0},
        )
        evt_title = (meta or {}).get("event_title") if isinstance(meta, dict) else None
        c["fights"].append(
            {
                "id": mid,
                "name": name,
                "commence": commence,
                "group": group,
                "venue": promo is not None,
            }
        )
        if promo is None:
            c["ticker"] += 1
        else:
            c["promotions"].append(promo)
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
    # back into ONE card. Computed over both sources (see `card_span_by_token`
    # for why the venue's clock never widens a scheduled token) and applied to
    # both dicts, so a Kalshi fight and the events row for the same bout cannot
    # end up on different cards.
    _spans = card_span_by_token(
        {t: [f["commence"] for f in c["fights"]] for t, c in cards.items()},
        {t: [e.commence_time for e in group] for t, group in event_bouts.items()},
    )
    _survivor = fold_rollover_tokens(_spans)
    if any(t != s for t, s in _survivor.items()):
        folded_cards: dict[str, dict] = {}
        for token, card in cards.items():
            keep = _survivor.get(token, token)
            target = folded_cards.setdefault(
                keep,
                {
                    "token": keep,
                    "fights": [],
                    "titles": [],
                    "promotions": [],
                    "ticker": 0,
                },
            )
            target["fights"].extend(card["fights"])
            target["titles"].extend(card["titles"])
            target["promotions"].extend(card["promotions"])
            target["ticker"] += card["ticker"]
        cards = folded_cards
        folded_bouts: dict[str, list] = {}
        for token, group in event_bouts.items():
            folded_bouts.setdefault(_survivor.get(token, token), []).extend(group)
        for group in folded_bouts.values():
            group.sort(key=bout_order_key)
        event_bouts = folded_bouts

    concepts: list[dict] = []
    # The main event's start, carried forward from the scan that already read
    # it. `_attach_headline_bouts` needs it and must not re-read
    # `futures_markets` to get it — see the note in that function.
    main_event_commence: dict[int, Any] = {}
    for token in set(cards) | set(event_bouts):
        kalshi = cards.get(token)
        bouts = event_bouts.get(token) or []

        # Authoritative schedule: prefer the events-table fight time; fall back to
        # the Kalshi main-event commence only when no scheduled bout exists.
        if bouts:
            # Tie-invariant: every bout in a tied max group carries the same
            # commence, so this is the latest time whichever row sorts last.
            latest = bouts[-1].commence_time  # _list_event_bouts sorts ascending
            earliest = bouts[0].commence_time
        elif kalshi and kalshi["fights"]:
            kalshi["fights"].sort(key=_ct)
            latest = kalshi["fights"][-1]["commence"]
            earliest = kalshi["fights"][0]["commence"]
        else:
            continue

        # #4485/#4821: a card whose OWN rows prove they are not a schedule is not
        # a card. Gated on the events-only branch — a card the venue lists
        # (`kalshi["fights"]`) has corroboration this predicate cannot overrule,
        # and all three live specimens are events-only. See
        # `card_rows_are_not_a_schedule` for the census and for why each of its
        # two clauses is unsafe alone.
        if not (kalshi and kalshi["fights"]) and card_rows_are_not_a_schedule(bouts):
            continue

        # #4505: the live window opens at THIS card's first bout, never at a fixed
        # lead on its last — see `combat_status`. #5603: the pair that decides the
        # STATUS skips bouts that have been called off (`card_status_span`); the
        # pair that DESCRIBES the card — `start_date`, the sort key, `fight_count`,
        # the rendered bout list — is untouched, so a suspended bout still shows.
        # CERT-2727: and a card whose bouts are ALL called off can never be live.
        status = card_status_from_bouts(
            bouts, now, fallback_first=earliest, fallback_last=latest
        )
        if status not in statuses:
            continue

        # Name/numbering: Kalshi carries the numbered-card label ("UFC 329") and
        # event_titles; events rows only carry fighter names, so an events-only card
        # falls through to its headline bout ("Du Plessis vs Usman", is_major=False).
        if kalshi and kalshi["fights"] and not kalshi["ticker"]:
            # #2602: a VENUE-only card. Its name is the promotion the venue's own
            # titles carry ("UFC Fight Night", "Power Slap 23") — provider
            # identity, not the refused `_concept_headline` heuristic of naming a
            # card after one of its bouts. There is no main-event signal to pick
            # one with: every bout of the card shares a single `venue_game_start`,
            # so a "latest bout" tiebreak would name the card after whichever row
            # sorted last. `fight_count` counts BOUTS, not rows — the venue
            # publishes a bout as a parent row plus condition-id children and both
            # can be named as the matchup (`venue_bout_group`).
            kalshi["fights"].sort(key=_ct)
            main_id = None
            fight_count = len({f["group"] for f in kalshi["fights"]})
            name = max(set(kalshi["promotions"]), key=kalshi["promotions"].count)
            is_major = False
        elif kalshi and kalshi["fights"]:
            kalshi["fights"].sort(key=_ct)
            # #2602: on a card a NUMBERED venue row unified onto (see
            # `venue_card_token`), the main event is picked from the TICKER
            # fights. A venue parent row carries the matchup in its title and no
            # moneyline under it, so letting it win the tiebreak would cost the
            # card the headline bout the Kalshi market can actually price.
            main = [f for f in kalshi["fights"] if not f["venue"]][-1]
            label, is_major = card_label(cfg, main["name"], tuple(kalshi["titles"]))
            main_id = main["id"]
            main_event_commence[main_id] = main["commence"]
            fight_count = len({f["group"] for f in kalshi["fights"]})
            name = label or main["name"]
        else:
            # ONE main-event determination, shared with `_build_events_envelope`
            # so the card's NAME and its hero cannot name different fights
            # (#4555). Never `bouts[-1]` — see `main_bout_of`.
            main_bout = main_bout_of(bouts)
            headline = f"{main_bout.home_team_name} vs {main_bout.away_team_name}"
            label, is_major = card_label(cfg, headline, ())
            main_id = None
            fight_count = len(bouts)
            name = label or headline

        # #5603: the chip, from THIS card's own evidence. Absent for a config
        # that declares no labels (boxing) so an older renderer and every other
        # domain are untouched; `domain` stays the routing token it always was.
        _sport_label = card_sport_label(
            cfg,
            ticker_fights=(kalshi or {}).get("ticker", 0),
            venue_promotions=(kalshi or {}).get("promotions", ()),
        )
        concepts.append(
            {
                "key": f"event:{cfg.domain}:{token}",
                "name": name,
                "domain": cfg.domain,
                **({"sport_label": _sport_label} if _sport_label else {}),
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
    await _attach_headline_bouts(db, concepts, main_event_commence)
    return concepts


async def _attach_headline_bouts(
    db: AsyncSession,
    concepts: list[dict],
    commence_by_market: dict[int, Any] | None = None,
) -> None:
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

    That read is of `futures_outcomes`, NOT `futures_markets`, and the
    distinction is load-bearing rather than stylistic. LAT-P094 collapsed the
    concept tier's three 50,749-row scans of `futures_markets` into one and
    guards the count at exactly one (`test_feed_concept_single_scan.py`); the
    obvious spelling of this function — re-select the main-event markets with
    `selectinload(outcomes)` — makes it two and turns that guard red. The two
    fields it wants are the outcome name and price, which live in the child
    table under an indexed `market_id`, and the third (`commence_time`) is
    already in the caller's hand from the same scan. So the market row is never
    needed twice: `commence_by_market` carries it forward instead.
    """
    main_ids = [c["main_event_id"] for c in concepts if c.get("main_event_id")]
    if not main_ids:
        return

    from app.models import FuturesOutcome

    try:
        outcome_rows = list(
            (
                await db.execute(
                    select(
                        FuturesOutcome.market_id,
                        FuturesOutcome.name,
                        FuturesOutcome.current_probability,
                        # #6777: the book columns decide whether that probability
                        # may be printed. Two more columns on the SAME read of the
                        # SAME child table — the scan the docstring above guards is
                        # of `futures_markets`, and this is not one. No settlement
                        # column is needed: see `printable_probabilities`.
                        FuturesOutcome.current_yes_bid,
                        FuturesOutcome.current_yes_ask,
                    ).where(FuturesOutcome.market_id.in_(main_ids))
                )
            ).all()
        )
    except Exception:  # a hero is never worth failing the tier for
        return

    by_market: dict[int, list] = {}
    for market_id, name, probability, yes_bid, yes_ask in outcome_rows:
        by_market.setdefault(market_id, []).append(
            (name, probability, yes_bid, yes_ask)
        )

    commence_by_market = commence_by_market or {}
    for concept in concepts:
        main_id = concept.get("main_event_id")
        outcomes = list(by_market.get(main_id) or [])
        if len(outcomes) != 2:
            continue  # not a two-sided bout — leave the card as it was
        outcomes.sort(key=lambda o: float(o[1] or 0), reverse=True)
        # #6777. Numeric(7,6) arrives as Decimal, and a Decimal is not JSON — the
        # float() inside `printable_probabilities` is the serialisation, not a
        # rounding preference. This is a main event, so it is always the pair.
        printable = printable_probabilities(
            (probability, yes_bid, yes_ask)
            for _name, probability, yes_bid, yes_ask in outcomes
        )
        competitors = [
            {"name": row[0], "probability": p}
            for row, p in zip(outcomes, printable)
        ]
        if not all(c["name"] and c["probability"] is not None for c in competitors):
            # "half a bout is not a bout" — and since #6777 that also means a bout
            # whose price the book refutes attaches no headline at all, rather
            # than attaching a nameless one.
            continue
        commence = commence_by_market.get(main_id)
        concept["headline_bout"] = {
            "competitors": competitors,
            "commence_time": commence.isoformat() if commence else None,
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
        # The feed lister and this page MUST fold identically (see the caller's
        # note), so both build their spans through the one helper — including
        # its rule that a venue close time never widens a scheduled token.
        venue_times: dict[str, list] = {}
        for m in markets:
            token = card_token(self.cfg, m.external_id)
            if token is not None:
                # A Kalshi row's `commence_time` is its CLOSE stamp, and only a
                # two-sided row is a fight — the filter this branch has always had.
                if len(m.outcomes or []) == 2:
                    venue_times.setdefault(token, []).append(m.commence_time)
                continue
            # #2602 follow-up: a venue-scoped card folds on the page exactly as it
            # folds in the feed, or a card the feed serves once opens a page
            # holding half of it. Two differences from the ticker branch, both
            # deliberate: the time is the venue's OWN fight start (its
            # `commence_time` is Gamma's listing stamp, measured two weeks early
            # on all 28 rows that carry both), and there is NO outcome-count
            # filter — most venue bouts carry no moneyline, and `list_card_concepts`
            # does not filter them either, so filtering here would make the two
            # callers disagree about which bouts date the card.
            meta = getattr(m, "market_metadata", None)
            token = venue_card_token(self.cfg, getattr(m, "name", None), meta)
            if token is not None:
                venue_times.setdefault(token, []).append(venue_fight_start(meta))

        survivor = fold_rollover_tokens(
            card_span_by_token(
                venue_times,
                {
                    token: [b.commence_time for b in group]
                    for token, group in bouts_by_token.items()
                },
            )
        )
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
        # #2602: the token is the date AND EVERYTHING AFTER IT, not the date
        # alone. A venue card's token carries its promotion as a suffix
        # (`26sep26ufcfightnight`), and `card_slug` puts the token last, so the
        # tail from the date is exactly the token. For every legacy slug — a bare
        # token, or `ufc-329-mcgregor-vs-holloway-26jul18` — the tail IS the
        # match, so this is a no-op there.
        _tok = _DATE_TOKEN_RE.search(target)
        if _tok:
            target = target[_tok.start() :]

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
        venue_bouts = []
        for m in markets:
            if card_token(cfg, m.external_id) in card_tokens:
                if len(m.outcomes or []) != 2:  # a real fight is two-sided
                    continue
                fights.append(m)
            elif (
                venue_card_token(cfg, m.name, getattr(m, "market_metadata", None))
                in card_tokens
            ):
                # #2602: a venue bout of this card. NOT filtered on outcome count
                # here — most carry none, and the ones that carry two often carry
                # two PROPS (`venue_bout_is_priced`). The envelope decides what
                # can be priced; the card still lists the bout either way.
                venue_bouts.append(m)

        bouts = sorted(
            (b for t in card_tokens for b in bouts_by_token.get(t, [])),
            key=bout_order_key,
        )

        if not fights:
            # No Kalshi markets for this card — resolve from the schedule alone.
            #
            # #6733: and refuse the same rows `list_card_concepts` refuses. The
            # two layers read the same roster and must reach the same verdict,
            # or a card suppressed from the feed keeps its page: after #4485
            # shipped, `/api/event/event:ufc:27jan01` still served seven
            # rumoured bouts as a real card (Strickland and Chimaev each booked
            # twice, every bout stamped one instant) while the feed had stopped
            # listing it. Gated on the SAME events-only branch and with the SAME
            # predicate — a card the venue lists has corroboration this cannot
            # overrule, so the `fights` path below is untouched. `None` is the
            # adapter's "no such card": `build_and_cache` writes the negative
            # marker and the route 404s, exactly as for an unknown token.
            # #2602: a card the VENUE lists and Kalshi does not. Preferred over
            # the schedule envelope because it is the corroborated source — the
            # venue is publishing this card, which is the same standing the
            # `fights` path has and which `card_rows_are_not_a_schedule` exists
            # to defer to.
            if venue_bouts:
                return self._build_venue_envelope(target, venue_bouts, now)
            if bouts and not card_rows_are_not_a_schedule(bouts):
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
        # #4505: the card's own first bout opens the live window. Kalshi-only cards
        # have no scheduled first bout, so this is None there and `combat_status`
        # falls back to the main event — under-claiming, never early.
        first_commence = bouts[0].commence_time if bouts else fights[0].commence_time
        # #5603: the STATUS pair skips bouts that have been called off, so the page
        # behind the card agrees with the card about whether the night is on.
        # `authoritative_commence` still carries `start_date` — display unchanged.
        card_status_value = card_status_from_bouts(
            bouts,
            now,
            fallback_first=first_commence,
            fallback_last=authoritative_commence,
        )

        # #1803, second reachable instance — found by censusing the class rather
        # than trusting its golf-shaped scoping. The card's ASSIGNED status is
        # reused below for `event.status`; it is hoisted here because `_child`
        # needs it to floor its own settled inference. Same authority, one call.
        #
        # CERT-2727: "terminal" and "settled" part company for an all-called-off
        # card. It is terminal — nothing will be fought, so it may not wear the
        # live pill — but nothing WAS fought either, so no child may inherit an
        # assigned-settled floor from it. #1803's term is "the card's fights are
        # done", and here they are off. Children fall back to the price test
        # exactly as they do for a card in play, which can only ever make a child
        # LESS settled — the direction #1803's docstring says is safe.
        card_settled = card_status_value == "settled" and not card_is_called_off(bouts)

        # #6816 / authority/446. The settlement contract on record proves the pair
        # is exhaustive over the bout's RESULT states — win, draw, no contest.
        # It proves nothing about a bout that is never fought: Kalshi's own
        # market-level wording is broader than the series text, and says a
        # cancelled or >2-week-rescheduled fight "will resolve to a fair price in
        # accordance with the rules" — two independent fair prices, which is not
        # a promise that the two contracts pay the whole. By this patch's own
        # standard that is absent evidence, so it REFUSES rather than normalises.
        #
        # `card_is_called_off` cannot carry this: it is card-scoped and demands
        # that EVERY bout be off (its own docstring), so the ordinary case — one
        # bout pulled for a missed weight or an injury on a card that goes ahead —
        # walks straight past it. This is per-bout, off the row already in hand:
        # a fight market carries `event_id` to its bout (measured on production
        # 2026-09-18: `KXUFCFIGHT-26APR04BARGAT` -> event 15151124), and `bouts`
        # is the adapter's own list of those rows.
        #
        # An unknown bout is NOT a called-off bout — no link, or a link to a row
        # outside this card, reads as "going ahead" and prints exactly what it
        # printed before. That is `_BOUT_CALLED_OFF`'s deny-list stance, kept
        # here for the same reason: `events.status` is an open vocabulary.
        bouts_by_id = {b.id: b for b in bouts}

        def _bout_will_be_fought(m) -> bool:
            bout_row = bouts_by_id.get(getattr(m, "event_id", None))
            return bout_row is None or _bout_going_ahead(bout_row)

        def _fight_outcomes(m, *, bout=False):
            outs = sorted(
                (m.outcomes or []),
                key=lambda o: float(o.current_probability or 0),
                reverse=True,
            )
            # #6777: a price the book refutes is withheld, not printed, and on a
            # two-sided bout the pair falls together. The sort above is
            # deliberately left on the STORED value, so a withheld row keeps its
            # place rather than sinking to the bottom of its own bout.
            printable = printable_probabilities(
                (o.current_probability, o.current_yes_bid, o.current_yes_ask)
                for o in outs
            )
            served = [
                {"name": o.name, "probability": p}
                for o, p in zip(outs, printable)
            ]
            if not bout:
                # A prop (method / round / distance) — its rows are separate
                # questions. Served exactly as before: no field, no pairing.
                return served
            # #6816: a FIGHT's two rows print as one decision. After price
            # support (the percents are taken from `printable`, so a withheld
            # leg stays withheld) and only for a pair proven to be one question.
            return with_bout_display_percents(
                served,
                one_question=(
                    ticker_bout_is_one_question(cfg, m) and _bout_will_be_fought(m)
                ),
            )

        # primary = the main-event fighters (co-equal, head-to-head).
        competitors = _fight_outcomes(main_event, bout=True)

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
            for o in f.outcomes or []:
                k = player_key(o.name)
                if k:
                    card_surnames.add(k)

        def _child(m, kind, prop_type=None):
            outs = _fight_outcomes(m, bout=kind == "fight")
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
        props.sort(
            key=lambda p: (_ptype_order.get(p.get("prop_type"), 9), p["market_id"])
        )

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

        # #5603: the page's chip, from the SAME evidence and the SAME helper the
        # feed card uses, so the card a reader taps and the page behind it can
        # never disagree about what this card may be called. The ticker fights
        # are this card's own (`card_tokens`) and they are what named it above.
        _sport_label = card_sport_label(
            cfg,
            ticker_fights=len(fights),
            venue_promotions=[
                p for p in (venue_card_promotion(m.name) for m in venue_bouts) if p
            ],
        )

        return {
            "event": {
                "key": f"event:{cfg.domain}:{target}",
                # L2-113: pretty, self-resolving URL slug (headliner + date-token).
                "slug": card_slug(card_name or main_event.name, target),
                "domain": cfg.domain,
                **({"sport_label": _sport_label} if _sport_label else {}),
                "name": card_name or main_event.name,  # numbered/Fight-Night card
                "status": card_status_value,
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
                # #5778 — see `event_cycling`. #5809: a fight card renders a
                # BOUT — both fighters, both percentages — so both prices are
                # displayed and the mark must speak for the OLDER of the two.
                # `_fight_outcomes` applies no name filter, so the displayed set
                # is the market's own outcomes; it is still routed through the
                # concept helper, because what differs from a futures card here
                # is the LEG COUNT (2, never 3) and that must come from one rule.
                "price_observed_at": concept_price_observed_at_iso(
                    main_event.outcomes or [], "co_equal_list", len(competitors)
                ),
            },
            "sections": sections,
            "children": children,
            "movers": [],
        }

    def _build_venue_envelope(self, target: str, rows: list, now) -> dict:
        """Card page for a card only the VENUE lists (#2602).

        The third envelope, beside the Kalshi one and the schedule one, and it
        exists because neither of those can reach a Polymarket-only card: Kalshi's
        keys on a ticker these rows do not have, and the schedule's keys on the
        events table, which holds no row for them.

        **Prices are conditional and the condition is strict.** A venue bout is
        published as an event-level parent row plus condition-id children, and
        only one of those is ever the moneyline. Measured on production
        2026-09-17, of the 19 open MMA rows named as bouts exactly **2** carry a
        genuine two-sided fighter-named market; the rest carry nothing, one
        unrelated prop, or — `61241597` — two props ("Haig in Round 3" /
        "Növényi Jr. in Round 2") under a matchup title. So a bout shows prices
        only when its outcomes ARE the two fighters its title names
        (:func:`venue_bout_is_priced`), and otherwise shows the two fighters with
        ``probability: None``.

        That null is the honest answer and not a degradation to be hidden: we do
        not hold the price. The venue does publish one for most of these bouts and
        our scan cannot currently reach it (#6758) — when that lands, the same
        rows start pricing here with no change to this function.

        **No main event is claimed from nothing.** Every bout of a venue card
        shares one ``venue_game_start``, so there is no time signal to rank them
        by. The pick is the venue's own segment annotation ("Main Card" ahead of
        "Prelims") and then the first row we ever saw — stable and
        self-consistent, the same standing :func:`main_bout_of` documents for
        itself, and explicitly not authoritative.
        """
        cfg = self.cfg

        def _meta_of(m):
            return getattr(m, "market_metadata", None)

        # One bout per venue event id: the parent row and its condition-id child
        # are the same fight. Prefer whichever of them can actually be priced.
        by_group: dict[str, Any] = {}
        for m in rows:
            key = venue_bout_group(_meta_of(m)) or f"market:{m.id}"
            current = by_group.get(key)
            if current is None or (
                venue_bout_is_priced(m.name, [o.name for o in (m.outcomes or [])])
                and not venue_bout_is_priced(
                    current.name, [o.name for o in (current.outcomes or [])]
                )
            ):
                by_group[key] = m

        def _segment_rank(m) -> int:
            return 0 if "main card" in (m.name or "").lower() else 1

        bouts = sorted(by_group.values(), key=lambda m: (_segment_rank(m), m.id))

        starts = [
            s for s in (venue_fight_start(_meta_of(m)) for m in bouts) if s is not None
        ]
        earliest = min(starts) if starts else None
        latest = max(starts) if starts else None
        # CERT-2727: through the shared entry point, never `combat_status`
        # directly — an adapter that calls it directly is one that can put the
        # live pill back on a card that is off. We hold no bout ROWS for a
        # venue-only card (the venue's markets are not `events` rows, and their
        # `commence_time` is the listing stamp), so the bout list is empty and
        # the venue's own fight times are the FALLBACK pair — which is exactly
        # what that argument documents itself as: unknown, not off.
        card_status_value = card_status_from_bouts(
            [], now, fallback_first=earliest, fallback_last=latest
        )

        promotions = [p for p in (venue_card_promotion(m.name) for m in bouts) if p]
        card_name = max(set(promotions), key=promotions.count) if promotions else target

        def _competitors(m):
            sides = title_bout_sides(m.name)
            if sides is None:
                return []
            outs = list(m.outcomes or [])
            if not venue_bout_is_priced(m.name, [o.name for o in outs]):
                # The two fighters, no numbers. Never a price we cannot stand up.
                return with_bout_display_percents(
                    [{"name": s, "probability": None} for s in sides],
                    one_question=False,
                )
            # #6777 — see `printable_probabilities`. This is the branch the Power
            # Slap 23 specimen renders through, and `venue_bout_is_priced` above
            # has already established that these two outcomes ARE the two
            # fighters, so the pair rule is on exactly the shape it is for.
            printable = printable_probabilities(
                (o.current_probability, o.current_yes_bid, o.current_yes_ask)
                for o in outs
            )
            priced = [
                {"name": o.name, "probability": p} for o, p in zip(outs, printable)
            ]
            # #6816 / Brief 22A: `venue_bout_is_priced` proves the two rows are
            # the two fighters — participant mapping — and NOT what the venue
            # pays when neither wins. A venue bout prints as one decision only
            # once its family's settlement rule is on record in
            # `COMPLEMENTARY_BOUT_CONTRACTS`; no Polymarket rule has been read,
            # so this is None today and the pair prints exactly as before.
            contract = bout_settlement_contract(m)
            return with_bout_display_percents(
                sorted(
                    priced,
                    key=lambda o: (
                        o["probability"] if o["probability"] is not None else -1.0
                    ),
                    reverse=True,
                ),
                one_question=contract is not None and contract.pair_sums_to_one,
            )

        def _bout_label(m) -> str:
            """The matchup, without the promotion the card is already named."""
            match = _VENUE_TITLE_RE.match(m.name or "")
            return (match.group(2) if match else (m.name or "")).strip()

        def _child(m):
            outs = _competitors(m)
            lead = outs[0]["probability"] if outs else None
            return {
                "market_id": m.id,
                "market_name": _bout_label(m),
                "source": m.source,  # data-only (audit); not rendered (D1)
                "kind": "fight",
                "settled": fight_child_settled(lead, card_status_value == "settled"),
                "probability": lead,
                "outcomes": outs,
            }

        children = [_child(m) for m in bouts]
        main_bout = bouts[0] if bouts else None
        main_competitors = _competitors(main_bout) if main_bout else []
        main_priced = main_bout is not None and venue_bout_is_priced(
            main_bout.name, [o.name for o in (main_bout.outcomes or [])]
        )

        # #5603: no ticker here by construction — this branch exists BECAUSE
        # Kalshi lists no fight for the card — so the chip rests on the venue's
        # own titles, which are also what `card_name` above was taken from.
        # "Power Slap 23" is the specimen: named by the venue, chipped "Combat".
        _sport_label = card_sport_label(
            cfg, ticker_fights=0, venue_promotions=promotions
        )

        return {
            "event": {
                "key": f"event:{cfg.domain}:{target}",
                "slug": card_slug(card_name, target),
                "domain": cfg.domain,
                **({"sport_label": _sport_label} if _sport_label else {}),
                "name": card_name,
                "status": card_status_value,
                "start_date": earliest.isoformat() if earliest is not None else None,
                "end_date": None,
                "venue": None,
                "location": None,
                "is_major": False,
            },
            "primary": {
                "kind": "co_equal_list",
                "label": "Main event",
                "competitors": main_competitors,
                # Only a bout we can price has a history worth charting.
                "evolution_market_id": main_bout.id if main_priced else None,
                "price_observed_at": (
                    concept_price_observed_at_iso(
                        main_bout.outcomes or [],
                        "co_equal_list",
                        len(main_competitors),
                    )
                    if main_priced
                    else None
                ),
            },
            "sections": [
                {
                    "type": "matchup",
                    "label": "Fights",
                    "market_ids": [m.id for m in bouts],
                }
            ],
            "children": children,
            "movers": [],
        }

    def _build_events_envelope(self, target: str, bouts: list, now) -> dict:
        """Pre-Kalshi envelope for a card that exists only in the events table
        (betting-odds-first). Same co_equal_list shape as the Kalshi path, but
        probabilities come from the aggregated event win-prob (Odds API/ESPN) and
        there is no futures market to chart — so `evolution_market_id` is None and
        the frontend renders the two-sided split bar without a history timeline.

        `bouts` are Event ORM rows for this card (sorted ascending by
        `bout_order_key`, a TOTAL order — a commence-only sort leaves the list,
        and the main event picked out of it, undefined on a tied card),
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
                    {
                        "name": ev.away_team_name,
                        "probability": round(1.0 - home_prob, 4),
                    },
                ]
            else:
                pair = [
                    {"name": ev.home_team_name, "probability": None},
                    {"name": ev.away_team_name, "probability": None},
                ]
            # #6816: this pair is a complement BY CONSTRUCTION (`p`, `1 - p`)
            # and still printed 74 / 27 off 0.735 / 0.265 — floats that sum to
            # one are not integers that sum to a hundred. No settlement contract
            # is in question here: there is ONE probability shown two ways, not
            # two venue contracts, so no third result can be rounded into it.
            return with_bout_display_percents(
                sorted(
                    pair,
                    key=lambda o: (
                        o["probability"] if o["probability"] is not None else -1.0
                    ),
                    reverse=True,
                ),
                one_question=True,
            )

        # The SAME determination `list_card_concepts` names the card after, so the
        # envelope's `primary` and the card's title cannot be two different fights
        # (#4555). Never `bouts[-1]` — see `main_bout_of`.
        main_bout = main_bout_of(bouts)
        latest_commence = main_bout.commence_time
        # #4505: this envelope's card is events-only, so its first bout is known —
        # `bouts` is sorted ascending by `bout_order_key`. #5603: the pair handed to
        # `combat_status` skips bouts that have been called off; `latest_commence`
        # still names the main event for `start_date`.
        # CERT-2727: and an all-called-off card is terminal, never live.
        first_commence = bouts[0].commence_time if bouts else None
        card_status_value = card_status_from_bouts(
            bouts, now, fallback_first=first_commence, fallback_last=latest_commence
        )

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

        # #5603: schedule rows and nothing else — the sport key says mixed
        # martial arts and names no promoter, so neither may this card.
        _sport_label = card_sport_label(cfg, ticker_fights=0, venue_promotions=())

        return {
            "event": {
                "key": f"event:{cfg.domain}:{target}",
                # L2-113: pretty, self-resolving URL slug (headliner + date-token).
                "slug": card_slug(card_name or headline, target),
                "domain": cfg.domain,
                **({"sport_label": _sport_label} if _sport_label else {}),
                "name": card_name or headline,
                "status": card_status_value,
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
                # #5778 — and no futures market is no price to date either. Null
                # rather than absent, so this envelope answers the key the way
                # the other eight sites do (#2088: null is "checked"; absent is
                # "built before this shipped").
                "price_observed_at": None,
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
