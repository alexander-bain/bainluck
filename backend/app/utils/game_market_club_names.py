"""The event page stops naming a club that does not exist (#6447).

WHAT A READER SAW
=================

``/events/14632820`` — Los Angeles Rams 27-7 San Francisco 49ers — spelled both
clubs correctly in its hero and then, in every market card beneath it::

    San Francisco vs Los Angeles R: 3rd Quarter Both Teams to Score
    San Francisco vs Los Angeles R: 1st Los Angeles R Touchdown
    Los Angeles R scores first TD                               Won

One screen, two vocabularies. Measured whole-population on production
2026-09-15: **11,328 event-attached markets across 1,206 event pages** carry a
side ending in a lone 1-3 capital run, this week's `scheduled` NFL fixtures
among them (``Green Bay vs New York J: 1st Half Spread``).

THE VENUE IS FAITHFUL AND THE REPAIR ALREADY EXISTED
====================================================

Kalshi's own title for ``KXNFLFIRSTTD-26SEP10SFLAR`` really is ``San Francisco
vs Los Angeles R: First Touchdown`` — read against the venue's API (standing
notice 26), so our stored row is right and this is a DISPLAY question, not an
ingest one.

:mod:`app.utils.kalshi_display_names` is the module written for it (#2060 item
3): it reads the nickname off the TICKER, which is gotcha #16's standing
preference, and abstains when two city siblings cannot be separated. Its only
callers were ``routes/admin_judgments.py`` and ``routes/admin_label_pass.py``.
Nothing a reader can see had ever called it. This module is the wiring, and it
adds exactly two things the admin callers did not need.

ONE: THE MAP IS POOLED PER PAGE, WHICH IS THE CRITERION #5181 SET
==================================================================

#5181 (ux, ``075336322``) repaired the Additional Markets card title and wrote
down the rule that governs this one::

    Keying on "do we recognise the sides?" would leave the page mixing venue
    names and ours card by card; keying on shape gives a reader one vocabulary
    per page.

That objection is real and a per-market repair would earn it: the ticker parser
resolves ``KXNFLSPREAD-26SEP14GBNYJ`` and does not resolve
``KXNFLTD-26SEP20GBNYJ``, so one page would print "New York Jets" on its spread
card and "New York J" on its touchdown card. Pooling every market's repairs into
ONE map for the page, then applying that map to every row, removes it. Measured
on two independent production samples of event-attached truncated rows:

===================  ===============  ========  ==================  =======  =========
sample               truncated sides  repaired  pages fully fixed   partial  conflicts
===================  ===============  ========  ==================  =======  =========
400 rows, newest     448              388       47                  0        0
500 rows, oldest     525              495       111                 0        0
===================  ===============  ========  ==================  =======  =========

Zero partial pages on 158 repaired pages, and zero markets on a page disagreeing
about what a truncated name expands to. A page is repaired whole or left exactly
as the venue sent it — J-League, Belgian youth soccer, cricket and tennis
doubles resolve nothing and are untouched.

TWO: OUR OWN ANCHORED ROW IS A REFUSAL LOCK, NEVER A SOURCE
============================================================

``Real Sociedad B`` matches the truncation SHAPE and is a real club — the
reserve side. It survives today only because no ticker code resolves it, which
is luck rather than a rule. So the event's own ``home_team_name`` /
``away_team_name`` — the names an authority (ESPN, StatPal) put on the row — veto
a rewrite of any string they use verbatim.

Deliberately one-way. They are NOT used to SUPPLY a name: ``kalshi_display_names``
refuses the event link for that on the record (a market whose ``event_id`` points
at the wrong day would import a matching bug as a display fix, #2057), and our own
short form can differ from the venue's long one (``LA Galaxy`` against ``Los
Angeles Galaxy``) so requiring agreement would refuse valid repairs. A lock that
can only ever leave text alone cannot invent a name.

WHY SERVE-TIME AND NOT THE STORED ROW
=====================================

The stored ``name`` stays the venue's. Our mirror stays faithful, no backfill
runs, every predicate that reads that column is unchanged — including
``_market_name_names``, which matches a market to an event BY the stored text —
and history is repaired the moment the page is built rather than for rows a
sweep happened to reach. Web and native both render ``market_name`` and
``outcome_name`` off this payload, so one repair here serves both tiers.

THE EVENT PAGE WAS NOT THE ONLY SCREEN (#6447 residual)
=======================================================

Measured on production 2026-09-16, the morning the page repair went live: a
reader who searches ``Jets`` is handed a card titled ``GB Packers vs NY Jets``
whose two options read ``Green Bay`` and ``New York J``. One card, two
vocabularies — the same defect, on the surface a reader reaches FIRST.

The page repair could not reach it. It runs inside ``_build_game_markets`` and
rewrites ``market_name``/``outcome_name``; the search and typeahead payloads are
a different shape assembled by a different formatter, so the fix was complete
for the screen it was measured on and silent everywhere else.

Reader-side count, twenty club queries, before the search half::

    distinct futures cards inspected                  187
    cards printing a club that does not exist           6   (all Week-3 NFL)

:func:`repair_card_club_names` is that half. It shares this module's engine and
its refusal rules; what it does NOT share is the pool, and the reason is written
on the function.
"""

from __future__ import annotations

import re
from typing import Iterable, Mapping, Optional, Sequence

from app.utils.kalshi_display_names import (
    apply_name_repairs,
    repair_outcome_name_by_ticker,
    repair_truncated_names,
)

#: The fields of a `/game-markets` row a reader actually reads. `market_name`
#: titles the card, `outcome_name` labels the row. Nothing else in the payload is
#: prose, and the underscore-prefixed keys are machine handles that must not move.
_TEXT_FIELDS = ("market_name", "outcome_name")

#: How a market name joins its two sides. Kalshi writes `A vs B`, Polymarket
#: sometimes `A at B`; everything after the first colon is the venue's
#: threshold/period/prop subject and is never a club.
_SIDE_SPLIT_RE = re.compile(r"\s+(?:vs\.?|at)\s+", re.IGNORECASE)

#: A side that ends in a lone capital letter — the venue's width truncation.
#: Used only as the CHEAP PRE-TEST on the search paths (see
#: :func:`any_truncated_side`); it never decides a repair, which is always the
#: ticker's job.
_LONE_TRAILING_CAPITAL_RE = re.compile(r"\S+ [A-Z]$")

#: `(title field, id field)` for the two served CARD shapes. `/search` futures
#: cards title themselves ``name`` and key on ``id``; the typeahead's dropdown
#: rows title themselves ``text`` and key on ``market_id``. Nothing else about
#: the question differs, so one engine serves both rather than two that drift.
SEARCH_CARD_FIELDS = ("name", "id")
TYPEAHEAD_CARD_FIELDS = ("text", "market_id")


def _uncompose_a_name_that_already_names_the_club(shipped: str, full: str) -> str:
    """`Los Angeles` + `LA Galaxy` is `LA Galaxy`, not `Los Angeles LA Galaxy`.

    MEASURED, NOT ANTICIPATED — 12 real rows in the two production samples, and
    the reason this function exists rather than a comment saying it cannot
    happen. ``kalshi_display_names`` composes ``city + nickname`` on the premise
    that the ticker's map holds bare nicknames (``lad`` -> ``Dodgers``). Some
    entries hold a WHOLE club name instead: ``lag`` -> ``LA Galaxy``. Composing
    those gives a string no one has ever called the club, and until this ship
    nothing reader-facing called that module, so nobody had to notice.

    The tell is a repeat: the nickname's own tokens overlap the city's, or its
    first token is the city's initials (``LA`` for ``Los Angeles``). When the
    nickname stands alone as a name — two tokens or more — it IS the answer and
    the city is dropped. When it does not, the repair is refused and the venue's
    truncation ships, which is this module's failure direction everywhere else.

    Fixed here rather than in ``kalshi_display_names`` on purpose: that function
    has two admin callers and a pinned suite of its own (#2060), and a reader
    surface is not the place to widen someone else's blast radius mid-launch.
    The shared root is recorded on issue 6447.
    """
    city = shipped.rsplit(" ", 1)[0].strip()
    nickname = full[len(city) :].strip() if full.startswith(city) else ""
    if not city or not nickname:
        return full

    city_tokens = {token.lower() for token in city.split()}
    nick_tokens = nickname.split()
    initials = "".join(word[0] for word in city.split() if word).upper()

    repeats = bool(city_tokens & {token.lower() for token in nick_tokens}) or (
        bool(nick_tokens) and nick_tokens[0].upper() == initials
    )
    if not repeats:
        return full
    return nickname if len(nick_tokens) >= 2 else shipped


def matchup_sides(market_name: Optional[str]) -> list[str]:
    """The club strings in a market name's head, before the colon.

    The truncated club is often ONLY in the title — ``Green Bay vs New York J:
    2nd Half Total`` has outcomes ``Over``/``Under``, so reading the outcome
    names alone (which is all the admin callers had) finds nothing to repair and
    the title keeps the name that does not exist.
    """
    if not market_name:
        return []
    head = str(market_name).split(":", 1)[0]
    return [part.strip() for part in _SIDE_SPLIT_RE.split(head) if part.strip()]


def build_page_repairs(
    rows: Iterable[Mapping],
    ticker_by_market_id: Mapping[int, Optional[str]],
    *,
    protected_names: Sequence[Optional[str]] = (),
) -> dict[str, str]:
    """One truncated-name -> full-name map for a whole event page.

    Pooled across every market on the page (see the module docstring), and
    vetoed by ``protected_names`` — the event's own anchored club names.

    A key that two markets expand DIFFERENTLY is dropped rather than resolved.
    Measured zero times on 158 repaired pages, so this is a guard against a
    future ticker-map change and not a live case; a page that starts
    contradicting itself keeps the venue's text instead of picking a winner.
    """
    protected = {
        str(name).strip() for name in protected_names if name and str(name).strip()
    }

    pooled: dict[str, str] = {}
    contradicted: set[str] = set()
    for row in rows:
        ticker = ticker_by_market_id.get(row.get("_market_id"))
        if not ticker:
            continue
        candidates = [
            *matchup_sides(row.get("market_name")),
            *([row["outcome_name"]] if row.get("outcome_name") else []),
        ]
        for shipped, composed in repair_truncated_names(ticker, candidates).items():
            full = _uncompose_a_name_that_already_names_the_club(shipped, composed)
            if shipped in protected or shipped == full:
                continue
            if shipped in pooled and pooled[shipped] != full:
                contradicted.add(shipped)
            pooled[shipped] = full

    for shipped in contradicted:
        pooled.pop(shipped, None)
    return pooled


def repair_club_names(
    buckets: Iterable[Optional[Iterable[Mapping]]],
    ticker_by_market_id: Mapping[int, Optional[str]],
    *,
    protected_names: Sequence[Optional[str]] = (),
) -> int:
    """Complete every truncated club on one page's rows, in place.

    Returns the number of FIELDS rewritten, which is what a guard test and a
    log line can both assert on. Mutates the row dicts because the payload's
    shape must not change: the frontend and both native clients read these two
    keys and nothing announces a repair happened.

    Call it BEFORE anything derived from these strings is composed — on
    ``/game-markets`` that means before ``props_script``, whose ``key`` is
    ``f"{market_name}|{outcome_name}"`` and would otherwise name the truncated
    row while its label named the repaired one.
    """
    rows = [row for bucket in buckets if bucket for row in bucket]
    if not rows:
        return 0

    repairs = build_page_repairs(
        rows, ticker_by_market_id, protected_names=protected_names
    )
    if not repairs:
        return 0

    changed = 0
    for row in rows:
        for field in _TEXT_FIELDS:
            before = row.get(field)
            if not isinstance(before, str) or not before:
                continue
            after = apply_name_repairs(before, repairs)
            if after != before:
                row[field] = after
                changed += 1
    return changed


def _card_rows(
    cards: Iterable[Mapping], title_field: str, id_field: str
) -> list[dict]:
    """A card's title and its outcome labels as ``build_page_repairs`` rows.

    A card is one market, so every row it yields carries that market's id and
    the pooling engine reaches the same ticker for all of them. The title is
    emitted ONCE rather than beside every outcome: ``build_page_repairs`` splits
    it into sides on every row it appears on, and a five-outcome card would pay
    for that five times for one identical answer.
    """
    rows: list[dict] = []
    for card in cards:
        if not isinstance(card, Mapping):
            continue
        market_id = card.get(id_field)
        rows.append({"_market_id": market_id, "market_name": card.get(title_field)})
        for outcome in card.get("top_outcomes") or []:
            if isinstance(outcome, Mapping) and outcome.get("name"):
                rows.append(
                    {"_market_id": market_id, "outcome_name": outcome["name"]}
                )
    return rows


def any_truncated_side(cards: Iterable[Mapping], *, title_field: str) -> bool:
    """Could anything on these cards be a width truncation? Pure string work.

    The search paths need this because their veto is not free. On the event page
    the protected names are already loaded — they are the event being rendered.
    A search response mixes markets from many events and none of them is loaded
    (the futures query eager-loads ``sport`` and ``outcomes``, never ``event``),
    so honouring the same veto costs one keyed read of ``events``.

    Measured on production 2026-09-16, twenty club queries: **6 of 187 distinct
    futures cards** carry a truncated side. This predicate is what keeps the
    other 181 — and every non-sport query, which is most of them — paying
    nothing at all on the hottest path in the API.

    Deliberately over-inclusive. It answers "is there anything shaped like a
    truncation here", and `Real Sociedad B` answers yes; the ticker then
    resolves nothing and no repair is made. A false yes costs one indexed query.
    A false no would be a silent hole, so the shape is the loose half on purpose.
    """
    for card in cards:
        if not isinstance(card, Mapping):
            continue
        sides = list(matchup_sides(card.get(title_field)))
        sides.extend(
            outcome["name"]
            for outcome in card.get("top_outcomes") or []
            if isinstance(outcome, Mapping) and isinstance(outcome.get("name"), str)
        )
        if any(_LONE_TRAILING_CAPITAL_RE.search(side or "") for side in sides):
            return True
    return False


def repair_card_club_names(
    cards: Iterable[Mapping],
    ticker_by_market_id: Mapping[int, Optional[str]],
    *,
    title_field: str,
    id_field: str,
    protected_names: Sequence[Optional[str]] = (),
) -> int:
    """Complete every truncated club on one RESPONSE's cards, in place.

    The sibling of :func:`repair_club_names` for the two search surfaces, and
    the reason it is a separate entry point rather than a flag: the payload
    shape differs (``name``/``text`` + ``top_outcomes[].name`` against
    ``market_name``/``outcome_name``) and, more importantly, so does the POOL.

    WHY THE POOL IS THE WHOLE RESPONSE
    ==================================

    #5181's criterion is one vocabulary per screen, and on a results page the
    screen is the response, not the card. Searching ``Jets`` can return both
    ``GB Packers vs NY Jets`` and ``NY Jets vs Detroit``; if one ticker resolves
    and the other does not, per-card pooling prints the club two ways in one
    list — exactly the objection the event-page version was built to avoid, one
    level up. So the map is built across every card and then applied to every
    card.

    The risk that buys is one card inheriting another's expansion for an
    identical shipped string. ``build_page_repairs`` already answers it: a key
    two markets expand DIFFERENTLY is dropped rather than resolved, and a key is
    the whole truncated side including its city, so two clubs colliding on one
    key is a contradiction and leaves the venue's text. That guard was a
    future-proofing measure on the event page (zero occurrences on 158 pages);
    here it is load-bearing, because the pool really does span leagues.

    Returns the number of FIELDS rewritten, which is what a guard test and a log
    line can both assert on. The cards are mutated in place because the search
    response hands the SAME dict to more than one bucket — ``futures`` and
    ``futures_families`` both hold ``_formatted_by_id[m.id]`` — and rebuilding
    would repair one bucket and not the other.
    """
    cards = [card for card in cards if isinstance(card, Mapping)]
    if not cards:
        return 0

    repairs = build_page_repairs(
        _card_rows(cards, title_field, id_field),
        ticker_by_market_id,
        protected_names=protected_names,
    )
    if not repairs:
        return 0

    changed = 0
    for card in cards:
        title = card.get(title_field)
        if isinstance(title, str) and title:
            after = apply_name_repairs(title, repairs)
            if after != title:
                card[title_field] = after
                changed += 1
        for outcome in card.get("top_outcomes") or []:
            if not isinstance(outcome, Mapping):
                continue
            before = outcome.get("name")
            if not isinstance(before, str) or not before:
                continue
            after = apply_name_repairs(before, repairs)
            if after != before:
                outcome["name"] = after
                changed += 1
    return changed


def repair_field_outcome_name(
    outcome_external_id: Optional[str],
    shipped_name: Optional[str],
) -> Optional[str]:
    """One rung of a championship FIELD, reader-side (#6479).

    ``("KXSB-27-LAR", "Los Angeles R")`` → ``"Los Angeles Rams"``; ``None`` when
    the name ships unchanged, which is the common case and what every caller
    must treat as "print what Kalshi sent".

    The engine is :func:`kalshi_display_names.repair_outcome_name_by_ticker` and
    the whole correspondence argument lives on it. This is the reader-side half,
    and it exists for one reason the engine deliberately does not carry.

    WHY THIS IS NOT THE ENGINE CALLED DIRECTLY
    ==========================================

    ``_uncompose_a_name_that_already_names_the_club`` — the ``LA Galaxy`` class.
    The engine composes ``city + nickname`` on the premise that the ticker map
    holds bare nicknames (``lad`` -> ``Dodgers``), and **101 of that map's
    values are whole club names that already carry the city**: ``lv_wnba`` ->
    ``Las Vegas Aces``, ``chi_mls`` -> ``Chicago Fire``, ``ind_wnba`` ->
    ``Indiana Fever``. Composing those gives ``Las Vegas Las Vegas Aces``, a
    string no one has ever called the club. Championship fields are exactly
    where those leagues' boards live, so this is the population, not a corner.

    The game-market path met the class first and the fix is measured there (12
    real rows in two production samples). It is reused rather than re-derived,
    and it stays out of ``kalshi_display_names`` for the reason written on it:
    that module has two admin callers and a pinned suite of its own (#2060), and
    a reader surface is not the place to widen someone else's blast radius.

    NO POOL, AND THAT IS THE DIFFERENCE FROM ITS SIBLING
    ====================================================

    :func:`repair_club_names` pools a whole page because #5181's criterion is one
    vocabulary per screen, and because a MARKET ticker resolves some of a
    screen's rows and not others — one card would say "New York Jets" and its
    neighbour "New York J".

    A field cannot have that problem. Every rung carries its OWN id-anchored
    ticker, so resolution is per-row by construction and a rung that resolves
    never depends on a sibling that did not. There is nothing to pool, and
    pooling would only add a way for one rung to rename another.
    """
    if not outcome_external_id or not shipped_name:
        return None
    full = repair_outcome_name_by_ticker(outcome_external_id, shipped_name)
    if not full:
        return None
    shipped = str(shipped_name)
    full = _uncompose_a_name_that_already_names_the_club(shipped, full)
    return full if full != shipped else None


__all__ = [
    "SEARCH_CARD_FIELDS",
    "TYPEAHEAD_CARD_FIELDS",
    "any_truncated_side",
    "build_page_repairs",
    "matchup_sides",
    "repair_card_club_names",
    "repair_club_names",
    "repair_field_outcome_name",
]
