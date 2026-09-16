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
"""

from __future__ import annotations

import re
from typing import Iterable, Mapping, Optional, Sequence

from app.utils.kalshi_display_names import apply_name_repairs, repair_truncated_names

#: The fields of a `/game-markets` row a reader actually reads. `market_name`
#: titles the card, `outcome_name` labels the row. Nothing else in the payload is
#: prose, and the underscore-prefixed keys are machine handles that must not move.
_TEXT_FIELDS = ("market_name", "outcome_name")

#: How a market name joins its two sides. Kalshi writes `A vs B`, Polymarket
#: sometimes `A at B`; everything after the first colon is the venue's
#: threshold/period/prop subject and is never a club.
_SIDE_SPLIT_RE = re.compile(r"\s+(?:vs\.?|at)\s+", re.IGNORECASE)


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


__all__ = ["build_page_repairs", "matchup_sides", "repair_club_names"]
