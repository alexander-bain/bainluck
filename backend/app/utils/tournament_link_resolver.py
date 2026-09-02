"""Bind a committed tournament fixture to the match market that prices it (Q426).

WHAT WENT WRONG, AND WHY IT WAS NOT A DATA ENTRY MISTAKE
--------------------------------------------------------

``ingest_tournament_draw.py`` ran once at the ceremony (2026-08-27T18:00Z) and
wrote 96 R128 matchups into the US Open register.  For every one of them it
recorded, at both sources::

    "status": "missing",
    "evidence": {"kind": "draw-fixture-census-absent",
                 "note": "fixture from the released draw; no match market
                          pinned at this source when the draw was ingested"}

That was **true when it was written**.  Nobody quotes a first round before
qualifying finishes, and the census said so honestly.  The defect is the tense:
``missing`` was recorded as a *fact about the fixture* when it is only a fact
about a *moment*, and nothing in the system ever asked the question again.  By
the next morning Kalshi carried all 96 main-draw matches
(``KXATPMATCH-26AUG30YIBWAL``, Wu vs Walton, among them) and the register still
said there was no market, so the R128 cards rendered with no probability on
them.  A market existed, we held it, and the page could not reach it.

The register's own drift sentinel could not catch this either, because
``diff_against_inventory`` opens with ``if block.get("status") == "missing":
continue``.  It verifies that *pinned* identities still resolve; it never asks
the inverse — whether a row we said had no market now has one.  A guard that
cannot see a population reports on it exactly like a healthy one (gotcha #53),
which is why nothing anywhere was red for a full day of a Grand Slam.

So this module makes ``missing`` a **re-testable** state.

WHY THIS IS NOT "FUZZY MATCHING AT REQUEST TIME"
-------------------------------------------------

``routes/tournaments.py`` says, correctly, that there is *no* matching on the
request path — that is the whole point of the register pattern and what makes
the page immune to the ``llm_sport_category`` contamination.  Nothing here runs
in a request.  A task resolves links on a beat and writes them down; the route
reads a pinned ``(market_id, outcome_id)`` exactly as it reads one out of the
committed file.

Nor is it curation.  The curated decisions — which fixtures exist, which two
players, which draw, which date — are committed to git and this module cannot
change any of them.  It answers one narrow mechanical question, and only for
rows the register has explicitly marked ``missing``: *given these two named
players, which market is theirs?*  A pinned identity is never overwritten,
never re-pointed, and never removed.  That asymmetry is inherited from
``diff_against_inventory`` on purpose: unambiguous and additive may be
automated, anything that changes which market backs an existing row goes to a
human.

KALSHI ONLY, AND THAT IS A CORRECTNESS DECISION
------------------------------------------------

A Kalshi match market states its own sides.  Measured on
``KXATPMATCH-26AUG19BORNAK``::

    outcome 219839305  name="Brandon Nakashima"  ext=…-BORNAK-NAK
    outcome 219839306  name="Nuno Borges"        ext=…-BORNAK-BOR

The outcome row *is* the player, named, with the ticker carrying its own player
code.  Reading that is id-anchored and needs no inference.

Polymarket's decomposed sub-market is ``Yes``/``No`` and carries no player label
anywhere in our tables — ``fetch_usopen_match_census.py`` documents the search
and the miss, and the repo's only Yes-to-competitor rule is a market-NAME parse
that is known to be wrong often enough that an inversion backstop
(``_check_and_fix_inversion``) exists to correct it.  Guessing which side of an
unlabelled binary a player is on, on a page whose entire thesis is one trusted
number, would trade a blank card for a card that is confidently backwards.  A
blank card is honest; an inverted one is a lie with a probability on it.

So Polymarket match rows stay ``missing`` here and their linkage remains a
human's (or a future ingestion-side fix that reads Gamma's ordered
``outcomes``, which is a network read and belongs in ingestion, not in a
resolver).  This module refuses rather than guesses, everywhere.

NAME CORRESPONDENCE
-------------------

Token sets, not string equality, and not substring containment.

``normalize_player_name`` collapses ``Felix Auger-Aliassime`` and ``Felix Auger
Aliassime`` to one key, which is right for a board row but wrong here: the
register calls the man ``Wu Yibing`` and Kalshi calls him ``Yibing Wu``.  Those
are the same player in a different order, and a collapsed string makes them two
people.  Comparing the *set* of name tokens makes word order irrelevant while
keeping every token load-bearing.

Substring containment is deliberately not used.  ``Wu`` is a substring of a
dozen names in a 128-draw; a rule that admits it will eventually bind the wrong
match, and a wrong bind is exactly the failure the register exists to prevent.
A shortened name (a dropped middle name) is admitted only as a strict subset,
and only when the resulting assignment is the sole possibility.

Pure.  No I/O, no clock of its own, no ORM rows — the caller passes plain dicts
and ``now``.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any, Iterable, Optional

logger = logging.getLogger(__name__)

#: The evidence kind stamped on every block this module mints.  A reader (and
#: the sentinel) can tell an auto-resolved link from a curated one by looking,
#: which is the difference between a register you can audit and one you cannot.
EVIDENCE_KIND = "auto-linked-match-market"

#: The rule that produced the link, recorded alongside it.  If the rule ever
#: changes, old links say which rule minted them.
RULE = "kalshi-outcome-name-pair/v1"

#: The same two facts for a link minted against the SCOREBOARD's pairing rather
#: than the register's (lane1/047).  Distinct strings, deliberately: an
#: authority link prices a fixture whose register pairing was withheld as
#: contradicted, and a reader auditing one of these must be able to tell at a
#: glance which question was asked.  The rule is versioned separately for the
#: same reason — it can move without moving the register path's.
AUTHORITY_EVIDENCE_KIND = "auto-linked-authority-match-market"
AUTHORITY_RULE = "espn-authority-outcome-name-pair/v1"

#: Sources this resolver is allowed to bind.  See the module docstring for why
#: this is one entry and not two.
RESOLVABLE_SOURCES = ("kalshi",)

#: Refusal codes.  Every needy fixture that does not get a link gets exactly one
#: of these, and the task reports them by name — a resolver that silently
#: resolves nothing must not read like a resolver that had nothing to do
#: (gotcha #53).
NO_CANDIDATE = "NO_CANDIDATE"
AMBIGUOUS_CANDIDATES = "AMBIGUOUS_CANDIDATES"
AMBIGUOUS_SIDES = "AMBIGUOUS_SIDES"
PLAYER_NOT_REGISTERED = "PLAYER_NOT_REGISTERED"
STALE_REMATCH = "STALE_REMATCH"

REFUSAL_CODES = (
    NO_CANDIDATE,
    AMBIGUOUS_CANDIDATES,
    AMBIGUOUS_SIDES,
    PLAYER_NOT_REGISTERED,
    STALE_REMATCH,
)

#: How far a candidate's own match date may sit from the fixture's scheduled
#: date and still be the same match.
#:
#: A day, because the two clocks disagree by construction: Kalshi embeds a
#: calendar date in the ticker (``…-26AUG30YIBWAL``) while the register stores a
#: UTC instant, and a night session in New York is the next day in UTC.
#:
#: It is a WINDOW and not a free pass. Two players meet more than once a season
#: — our own tables hold ``KXATPCHALLENGERMATCH-26JUN01WALTUN`` ("Walton vs Wu")
#: alongside this week's ``KXATPMATCH-26AUG30YIBWAL`` — so names alone cannot
#: identify a match. And the obvious substitute guard does not work: Kalshi
#: settled markets stay ``status='open'`` in our database (gotcha #33), so
#: "still open" is not evidence a match has not been played. The date is the
#: only bound that actually separates June's meeting from Sunday's.
MATCH_DATE_TOLERANCE_DAYS = 1


def name_tokens(name: Any) -> frozenset[str]:
    """The set of alphanumeric word tokens in a player name, lowercased.

    ``"Christopher O'Connell"`` → ``{"christopher", "oconnell"}``.
    ``"Alex de Minaur"``        → ``{"alex", "de", "minaur"}``.
    ``"Wu Yibing"``             → ``{"wu", "yibing"}``  (== ``"Yibing Wu"``).

    Punctuation is dropped *within* a token rather than splitting on it, so
    ``Auger-Aliassime`` stays one token and matches ``Auger Aliassime``'s two
    only under the subset rule below — never by accident.
    """
    if not isinstance(name, str):
        return frozenset()
    tokens = set()
    for raw in name.replace("-", " ").split():
        token = "".join(ch for ch in raw.lower() if ch.isalnum())
        if token:
            tokens.add(token)
    return frozenset(tokens)


def _initials_correspond(short: frozenset[str], long: frozenset[str]) -> bool:
    """Whether ``short`` is ``long``'s given names written as initials.

    The specimen: the register calls him ``J.J. Wolf`` and Kalshi calls him
    ``Jeffrey John Wolf``.  Same man, and no amount of subset logic connects
    ``{jj}`` to ``{jeffrey, john}``.

    The rule, deliberately narrow:

    * the two names must already share at least one token — in practice the
      surname.  Without this an initials rule is a wildcard, and ``{j}`` would
      correspond to every Jeffrey, Jakub and Jaime in the draw;
    * every *remaining* token on the short side must be initial-shaped (one or
      two characters).  ``Wu`` is two characters and this is exactly why the
      shared-token requirement above is not optional;
    * the short side's remaining letters, sorted, must equal the long side's
      remaining tokens' first letters, sorted.  Sorted because token sets carry
      no order, so ``J.J.`` cannot be required to arrive before ``Jeffrey``.

    Even when this fires it is not the last word: the caller still requires a
    unique bijection across both sides of the match, a single matching
    candidate, and a match date inside the window.  An initials collision
    between two players in the same draw therefore refuses rather than picks.
    """
    shared = short & long
    if not shared:
        return False
    short_rest = short - shared
    long_rest = long - shared
    if not short_rest or not long_rest:
        return False
    if any(len(token) > 2 for token in short_rest):
        return False
    short_letters = sorted("".join(sorted(short_rest)))
    long_letters = sorted(token[0] for token in long_rest)
    return short_letters == long_letters


def names_correspond(a: frozenset[str], b: frozenset[str]) -> bool:
    """Whether two token sets name the same player.

    Equal, or one a strict subset of the other (a dropped middle name), or one
    written with the other's given names as initials.  Both must be non-empty:
    an unnamed outcome corresponds to nobody, and returning True for it would
    bind every fixture to the first blank row in the pool.
    """
    if not a or not b:
        return False
    if a == b or a < b or b < a:
        return True
    return _initials_correspond(a, b) or _initials_correspond(b, a)


def _candidate_sides(
    candidate: dict[str, Any],
    player_tokens: dict[str, frozenset[str]],
) -> Optional[dict[str, dict[str, Any]]]:
    """Map this candidate's two outcomes onto the fixture's two players.

    Returns the ``sides`` map, or ``None`` if the candidate is not this
    fixture's market or the assignment is not a unique bijection.

    The bijection check is the load-bearing half.  In a draw containing both
    ``Taylor Fritz`` and ``Taylor Townsend`` a single-sided test can bind one
    outcome to two players; requiring that each outcome corresponds to exactly
    one player, and each player to exactly one outcome, refuses that instead of
    picking one.
    """
    outcomes = candidate.get("outcomes") or []
    if len(outcomes) != 2:
        return None

    # outcome index -> the entity keys it could name
    options: list[tuple[dict[str, Any], list[str]]] = []
    for outcome in outcomes:
        if not isinstance(outcome, dict):
            return None
        tokens = name_tokens(outcome.get("name"))
        matches = [
            key for key, ptokens in player_tokens.items()
            if names_correspond(tokens, ptokens)
        ]
        options.append((outcome, matches))

    # Every outcome must name exactly one player, and the two must differ.
    if any(len(matches) != 1 for _, matches in options):
        return None
    first_key = options[0][1][0]
    second_key = options[1][1][0]
    if first_key == second_key:
        return None

    sides: dict[str, dict[str, Any]] = {}
    for outcome, matches in options:
        outcome_id = outcome.get("outcome_id")
        if not isinstance(outcome_id, int) or isinstance(outcome_id, bool):
            return None
        sides[matches[0]] = {
            "outcome_id": outcome_id,
            "outcome_external_id": outcome.get("external_id"),
            "source_label": outcome.get("name"),
        }
    if len(sides) != 2:
        return None
    return sides


def _as_date(value: Any) -> Optional[date]:
    """A calendar date from an ISO string, datetime or date. None if unusable.

    Total by design: a resolver must refuse an unparseable date, never raise on
    one. A raise here would take down the whole beat for every other fixture.
    """
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str) and value:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
        except ValueError:
            return None
    return None


def _within_window(candidate_date: Any, fixture_date: Optional[date]) -> bool:
    """Whether a candidate's match date can be the fixture's.

    Fails CLOSED: an unknown date on either side is not a match. An unknown
    date is exactly when a rematch would slip through, so treating it as
    permissive would disable the one guard that separates two meetings of the
    same two players.
    """
    observed = _as_date(candidate_date)
    if observed is None or fixture_date is None:
        return False
    return abs((observed - fixture_date).days) <= MATCH_DATE_TOLERANCE_DAYS


def _match_fixture(
    candidates: Iterable[dict[str, Any]],
    player_tokens: dict[str, frozenset[str]],
    fixture_date: Optional[date],
) -> tuple[Optional[tuple[dict[str, Any], dict[str, Any]]], Optional[str]]:
    """Which of ``candidates`` is this fixture's market.

    Returns ``((candidate, sides), None)`` on a unique clean bind, or
    ``(None, <refusal code>)``.

    ONE RULE, TWO CALLERS, AND THAT IS THE POINT.  ``resolve_matchup_links``
    asks this for a fixture the register names; ``resolve_authority_links``
    asks it for a fixture the ESPN scoreboard names.  Those two differ only in
    *who named the two people* — the question "given these two players and this
    date, which market is theirs" is identical, and a second copy of it would
    be free to rot away from this one while both kept passing their own tests.
    """
    matched: list[tuple[dict[str, Any], dict[str, Any]]] = []
    saw_partial = False
    saw_out_of_window = False
    for candidate in candidates:
        sides = _candidate_sides(candidate, player_tokens)
        if sides is not None:
            if _within_window(candidate.get("match_date"), fixture_date):
                matched.append((candidate, sides))
            else:
                # The right two players, the wrong meeting. Named separately
                # because it is gotcha #33's exact shape and reads nothing like
                # an absence.
                saw_out_of_window = True
            continue
        # A candidate that names ONE of our two players but could not be
        # resolved into a clean pair is worth distinguishing from one that has
        # nothing to do with this fixture: it is the shape a near-miss takes,
        # and reporting it as NO_CANDIDATE would hide a real linkage defect
        # behind an ordinary absence.
        for outcome in candidate.get("outcomes") or []:
            if not isinstance(outcome, dict):
                continue
            tokens = name_tokens(outcome.get("name"))
            if any(
                names_correspond(tokens, ptokens)
                for ptokens in player_tokens.values()
            ):
                saw_partial = True
                break

    if len(matched) > 1:
        return None, AMBIGUOUS_CANDIDATES
    if not matched:
        if saw_out_of_window:
            return None, STALE_REMATCH
        return None, (AMBIGUOUS_SIDES if saw_partial else NO_CANDIDATE)
    return matched[0], None


def _needy_blocks(matchup: dict[str, Any], sources: Iterable[str]) -> list[dict[str, Any]]:
    """The ``missing`` source blocks on this matchup that we may try to fill."""
    allowed = set(sources)
    out = []
    for block in matchup.get("sources") or []:
        if not isinstance(block, dict):
            continue
        if block.get("status") != "missing":
            continue
        if block.get("source") not in allowed:
            continue
        out.append(block)
    return out


def resolve_matchup_links(
    register: dict[str, Any],
    candidates: list[dict[str, Any]],
    *,
    now: datetime,
    sources: Iterable[str] = RESOLVABLE_SOURCES,
) -> dict[str, Any]:
    """Resolve ``missing`` matchup source blocks against observed market rows.

    ``candidates`` are plain dicts, one per market::

        {"source": "kalshi", "market_id": int, "external_id": str,
         "name": str, "outcomes": [{"outcome_id": int, "name": str,
                                    "external_id": str}, ...]}

    Returns ``{"links": {...}, "refusals": [...], "counters": {...}}`` where
    ``links`` is keyed ``"<matchup_key>|<source>"`` and carries a ready-to-apply
    source block.  Nothing is mutated.
    """
    observed_at = now.isoformat()
    players_by_key = {
        p.get("entity_key"): p
        for p in (register.get("players") or [])
        if isinstance(p, dict)
    }

    by_source: dict[str, list[dict[str, Any]]] = {}
    for candidate in candidates:
        if isinstance(candidate, dict):
            by_source.setdefault(candidate.get("source"), []).append(candidate)

    links: dict[str, dict[str, Any]] = {}
    refusals: list[dict[str, Any]] = []
    counters: dict[str, int] = {
        "needy": 0,
        "resolved": 0,
        **{code: 0 for code in REFUSAL_CODES},
    }

    for matchup in register.get("matchups") or []:
        if not isinstance(matchup, dict):
            continue
        matchup_key = matchup.get("matchup_key")
        player_keys = matchup.get("players")
        if not isinstance(player_keys, list) or len(player_keys) != 2:
            continue

        blocks = _needy_blocks(matchup, sources)
        if not blocks:
            continue

        fixture_date = _as_date(matchup.get("scheduled_date"))

        player_tokens: dict[str, frozenset[str]] = {}
        for key in player_keys:
            player = players_by_key.get(key)
            if player is None:
                continue
            tokens = name_tokens(player.get("display_name"))
            if tokens:
                player_tokens[key] = tokens

        for block in blocks:
            counters["needy"] += 1
            source = block.get("source")

            def refuse(code: str, _key=matchup_key, _source=source) -> None:
                counters[code] += 1
                refusals.append(
                    {"matchup_key": _key, "source": _source, "reason": code}
                )

            if len(player_tokens) != 2:
                # The fixture names a player the register does not carry, or
                # carries with no usable name. Not a linkage question.
                refuse(PLAYER_NOT_REGISTERED)
                continue

            hit, refusal = _match_fixture(
                by_source.get(source, []), player_tokens, fixture_date
            )
            if hit is None:
                refuse(refusal or NO_CANDIDATE)
                continue

            candidate, sides = hit
            # The block-level `outcome_id` follows the committed register's own
            # convention: the first-listed player's side. `matchup_outcome_ids`
            # reads `sides`, not this, but `validate_source_entry` requires a
            # non-null identity on a non-missing block and a reader expects the
            # two to agree.
            lead_key = player_keys[0] if player_keys[0] in sides else next(iter(sides))
            links[f"{matchup_key}|{source}"] = {
                "source": source,
                "kind": "match",
                "market_id": candidate.get("market_id"),
                "outcome_id": sides[lead_key]["outcome_id"],
                "market_external_id": candidate.get("external_id"),
                "status": "live",
                "terminal_result": None,
                "evidence": {
                    "kind": EVIDENCE_KIND,
                    "observed_at": observed_at,
                    "rule": RULE,
                    "market_name": candidate.get("name"),
                    "note": (
                        "resolved from the source's own outcome labels; the "
                        "register recorded no market for this fixture at "
                        "ingest and one exists now"
                    ),
                },
                "sides": sides,
            }
            counters["resolved"] += 1

    return {"links": links, "refusals": refusals, "counters": counters}


def resolve_authority_links(
    competitions: Iterable[dict[str, Any]],
    candidates: list[dict[str, Any]],
    *,
    now: datetime,
    sources: Iterable[str] = RESOLVABLE_SOURCES,
) -> dict[str, Any]:
    """Resolve match markets for fixtures the SCOREBOARD names (lane1/047).

    ═══ THE CARD THAT SAID NOBODY WAS QUOTING A MATCH WE HELD A PRICE FOR ═══

    Q503 withholds a register pairing the ESPN scoreboard contradicts, and Q505
    puts the fixture back under the authority's own two names.  That row is
    correct and it is unpriceable: ``authority_match_row`` is handed no prices,
    because the only identities this page will read a price through are the
    ``(market_id, outcome_id)`` pairs the register pins — and the register, by
    construction here, names the wrong people.

    Measured on production 2026-09-02: the US Open slate carried exactly one
    authority row, ``espn:182703`` — Rafael Jodar vs Bu Yunchaokete — and it
    read *"Nobody is quoting this match yet. It is in the draw with no
    probability against it."*  We held ``KXATPMATCH-26SEP01JODYUN`` at the
    time, open, with both legs named in full (``Rafael Jodar`` 0.895 /
    ``Yunchaokete Bu`` 0.105).  The sentence was false, and it was false in the
    most expensive direction a probability product has: it told a reader the
    market was silent while quoting 90/10 one tab over.

    Q505's own docstring wrote the fix down — *"when the match market for the
    real pairing is linked, the ordinary priced row takes over"*.  This is that
    link.  Nothing here relaxes Q503's refusal: the number that was withheld
    was the one quoted for the WRONG pairing, and this one is quoted for the
    two people ESPN says are on court, by the same rule, from the same pool.

    ``competitions`` are plain dicts, one per ESPN competition::

        {"espn_competition_id": "182703",
         "scheduled_date": "2026-09-02T17:00:00+00:00",
         "players": [{"entity_key": "espn:athlete:12657",
                      "display_name": "Rafael Jodar"}, ...]}

    Returns the same shape ``resolve_matchup_links`` does, keyed
    ``"espn:<competition id>|<source>"`` — which is exactly
    ``authority_match_row``'s ``matchup_key``, so the slate's lookup is a dict
    hit on an id and never a name comparison at request time.

    THE RULE IS NOT A SECOND RULE.  ``_match_fixture`` is shared with the
    register path: same token-set correspondence, same unique bijection across
    both sides, same one-day match-date window, same five refusal codes.  What
    differs is only who named the two people, and an ESPN competitor is a
    STRONGER anchor than a register entry here, not a weaker one — it is the
    authority we already trust enough to withhold the register's pairing on.

    Pure.  No I/O and no clock of its own.
    """
    observed_at = now.isoformat()

    by_source: dict[str, list[dict[str, Any]]] = {}
    for candidate in candidates:
        if isinstance(candidate, dict):
            by_source.setdefault(candidate.get("source"), []).append(candidate)

    links: dict[str, dict[str, Any]] = {}
    refusals: list[dict[str, Any]] = []
    counters: dict[str, int] = {
        "needy": 0,
        "resolved": 0,
        **{code: 0 for code in REFUSAL_CODES},
    }

    for competition in competitions:
        if not isinstance(competition, dict):
            continue
        comp_id = competition.get("espn_competition_id")
        if not comp_id:
            continue
        players = competition.get("players")
        if not isinstance(players, list) or len(players) != 2:
            continue

        fixture_date = _as_date(competition.get("scheduled_date"))

        player_tokens: dict[str, frozenset[str]] = {}
        for player in players:
            if not isinstance(player, dict):
                continue
            key = player.get("entity_key")
            tokens = name_tokens(player.get("display_name"))
            if key and tokens:
                player_tokens[key] = tokens

        for source in sources:
            counters["needy"] += 1

            if len(player_tokens) != 2:
                # The scoreboard named a competition we cannot key on two
                # distinct identified people. Not a linkage question — and the
                # slate does not build an authority row for it either.
                counters[PLAYER_NOT_REGISTERED] += 1
                refusals.append({
                    "matchup_key": f"espn:{comp_id}",
                    "source": source,
                    "reason": PLAYER_NOT_REGISTERED,
                })
                continue

            hit, refusal = _match_fixture(
                by_source.get(source, []), player_tokens, fixture_date
            )
            if hit is None:
                code = refusal or NO_CANDIDATE
                counters[code] += 1
                refusals.append({
                    "matchup_key": f"espn:{comp_id}",
                    "source": source,
                    "reason": code,
                })
                continue

            candidate, sides = hit
            lead_key = str(players[0].get("entity_key"))
            if lead_key not in sides:
                lead_key = next(iter(sides))
            links[f"espn:{comp_id}|{source}"] = {
                "source": source,
                "kind": "match",
                "market_id": candidate.get("market_id"),
                "outcome_id": sides[lead_key]["outcome_id"],
                "market_external_id": candidate.get("external_id"),
                "status": "live",
                "terminal_result": None,
                "evidence": {
                    "kind": AUTHORITY_EVIDENCE_KIND,
                    "observed_at": observed_at,
                    "rule": AUTHORITY_RULE,
                    "market_name": candidate.get("name"),
                    "espn_competition_id": str(comp_id),
                    "note": (
                        "resolved from the source's own outcome labels against "
                        "the two players the ESPN scoreboard names for this "
                        "competition; the register's pairing for it was "
                        "withheld as contradicted"
                    ),
                },
                "sides": sides,
            }
            counters["resolved"] += 1

    return {"links": links, "refusals": refusals, "counters": counters}


def apply_resolved_links(
    register: dict[str, Any], links: dict[str, Any]
) -> tuple[dict[str, Any], int]:
    """Overlay resolved links onto a register, returning a new dict.

    ONLY replaces blocks whose status is ``missing``.  A pinned identity is
    never touched, so a stale or wrong overlay cannot move a curated row — the
    worst it can do is fail to fill a blank one, which is the state the page is
    already in without it.

    The input register is not mutated: the route holds a cached, module-level
    register dict and mutating it in place would let one request's overlay leak
    into the next (gotcha #6's shape — a shared cache must hold plain data
    nobody edits).
    """
    if not isinstance(links, dict) or not links:
        return register, 0

    applied = 0
    matchups = []
    for matchup in register.get("matchups") or []:
        if not isinstance(matchup, dict):
            matchups.append(matchup)
            continue
        matchup_key = matchup.get("matchup_key")
        blocks = matchup.get("sources") or []
        new_blocks = []
        changed = False
        for block in blocks:
            if (
                isinstance(block, dict)
                and block.get("status") == "missing"
                and f"{matchup_key}|{block.get('source')}" in links
            ):
                new_blocks.append(links[f"{matchup_key}|{block.get('source')}"])
                changed = True
                applied += 1
            else:
                new_blocks.append(block)
        if changed:
            matchup = {**matchup, "sources": new_blocks}
        matchups.append(matchup)

    if not applied:
        return register, 0
    return {**register, "matchups": matchups}, applied
