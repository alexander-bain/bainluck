"""One match's own page — the match-winner market, and the questions under it.

═══ WHAT THIS SHIPS (UX-P149) ═══

Alex asked, of the match props lane1 measured in Q426: *"Will those flow into
the event page for each match, and will they look good?"*  Lane1's note
(``NOTE-TO-UX-FROM-LANE1-Q426.md``) made the routing call — **match props
belong on the match's own surface, grouped under the match-winner market** —
and then named the blocker that made the surface a ux call rather than theirs:

    **There is no per-match surface to route them to.**  Tennis matches have no
    ``events`` row; zero exist for any registered matchup.

The note offered two ways out: (a) a match detail view under the tournament hub
keyed on ``matchup_key``, or (b) real ``events`` rows for tennis matches.  This
module is **(a)**, and the reason is not that (b) is hard.  It is that (b) is a
matching-layer job whose failure mode is a wrong absorption (gotcha #32,
ruling 048), taken on to reuse a page that would then have to be taught tennis
anyway.  A matchup key is an identity the register already owns, committed
offline against evidence.  Routing on it needs no new identity decisions at
all, which is why the surface can ship today and the ingestion question stays
lane1's.

═══ THE GROUPING IS AN ID, NOT A MATCH ═══

Polymarket puts every prop for a match in the same ``group_id`` as its
match-winner market.  The register pins that market's ``market_id``; the route
reads its ``group_id`` and loads the group.  There is no name matching, no time
window and no fuzzy lookup anywhere on this path — the same posture as the
register itself.

**The event container is excluded by an id equality, not by a market_type.**
Every Polymarket event carries a synthetic parent whose ``external_id`` is the
event id and whose outcomes are the condition ids of its own members — it is
every prop in the group, again, as one field market.  Rendering it would print
the whole page twice.  It is identified as ``group_id == "polymarket:" +
external_id``, which is exact.  ``market_type == 'field'`` was the first draft
and is wrong for a reason worth writing down: ``market_type`` is assigned by a
backfill classifier, one market in the measured corpus carries ``unshaped``,
and a genuine multi-outcome prop (an Exact Score market) is *also* a field.

═══ THE ONE THING HERE THAT IS INFERRED, AND WHAT BOUNDS IT ═══

A Polymarket sub-market stores two outcomes named ``Yes`` and ``No``.  Which
player is ``Yes`` is **not stored anywhere**: ``futures_outcomes`` carries the
literal word, the external id carries ``…_yes``, and the label the source
printed is dropped at ingestion.  The register solves this for the match-winner
market by pinning ``sides`` offline against the source's own ordered labels.
It cannot solve it for the props — ~12 per match across 96 matches is not a
thing anyone should hand-review, which is lane1's third reason for keeping them
off the register in the first place.

So attribution is derived from the market's own title, under a rule that is
**measured rather than assumed**:

    ``_yes`` is the player named FIRST in that market's own title.

Measured 2026-08-28 against the 28 live matchups the committed register pins —
the one market class where the answer is independently known, because the
register established it offline from the source's ordered labels:
**28 of 28, zero violations.**  ``tests/test_tournament_match.py`` replays that
measurement against a committed fixture of the real titles, so the day
Polymarket flips the convention the register's own pins turn red.

Three things bound it, because a number under the wrong player's name is the
worst defect this page can ship:

1. **It reads the PROP's own title, never the winner market's.**  Of 73 prop
   titles measured, **5 name the players in the opposite order to the winner
   market** — every one a Set Handicap, where Polymarket puts the favoured side
   first.  Inheriting the order would have mis-attributed all five.
2. **It refuses rather than guesses.**  Both registered players must appear as
   whole words, at distinct positions, on tokens that are not shared between
   them.  Anything else yields no card and a counted reason.
3. **A handicap must have the minus on the first-named side**, or it is
   refused.  Measured: 24 handicap markets, 0 anomalies — the guard is for the
   25th.

Everything else on the page needs no attribution at all: an Over/Under is a
question about the match, not about a player, and 128 of the 206 prop markets
in the measured corpus are Over/Unders.

Pure logic — every input is a plain dict, so the whole page is testable without
a database.
"""

from __future__ import annotations

import logging
import math
import re
import unicodedata
from datetime import datetime
from typing import Any, Optional

from app.utils.tournament_board import (
    freshest_observation,
    governing_age_hours,
    price_state,
)
from app.utils.tournament_register import TournamentRegister
from app.utils.tournament_slate import build_match_row, normalize_pair

logger = logging.getLogger(__name__)

#: Bounds the sibling scan. A Polymarket tennis event carries ~12 sub-markets;
#: the cap is here so a source that starts listing hundreds cannot silently turn
#: one page request into an unbounded read.
MAX_PROPS_PER_MATCH = 60

#: Families, in the order they appear on the page. Nearest the match's own
#: question first: who wins a set, then by how much, then how long it runs.
FAMILY_ORDER = ("set_winner", "handicap", "total", "other")

#: The words the SOURCE stores for a side. None of them may reach a reader —
#: they are the structural vocabulary of a market, not an answer anyone can
#: act on, and printing one is the register's first refusal ("never print
#: Yes/No") one market class along.
_SOURCE_SIDE_WORDS = frozenset({"yes", "no", "over", "under"})


# ───────────────────────── name attribution ─────────────────────────

_WORD_RE = re.compile(r"[a-z]+")


def _fold(text: str) -> str:
    """Lowercase, accent-stripped ASCII — ``Semenistaja`` and ``Semenistaja``.

    The corpus carries Kalieva, Valdmannova, Semenistaja, Bolkvadze and
    Auger-Aliassime.  A comparison that is not fold-insensitive fails on the
    first accented spelling and, because the rule REFUSES on a miss, it fails
    safely but silently — the prop simply never renders.  Folding is what keeps
    the refusal a signal rather than the normal case.
    """
    decomposed = unicodedata.normalize("NFKD", text or "")
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch)).lower()


#: Words a market title uses about ITSELF. Stripped from a player's tokens
#: before any search, so the structural vocabulary of a title can never be
#: mistaken for a name — the price of accepting two-letter surnames.
_TITLE_STOPWORDS = frozenset({
    "vs", "ou", "set", "sets", "game", "games", "match", "total", "winner",
    "handicap", "spread", "score", "exact", "over", "under", "and", "the",
})


def name_tokens(*names: Optional[str]) -> set[str]:
    """Whole-word alphabetic tokens of 2+ characters, folded, minus title words.

    TWO CHARACTERS, NOT THREE, AND THE REASON IS MEASURED.  A three-character
    floor looks safe and drops real players: ``Yeon-Woo Ku`` yields only
    ``yeon`` and ``woo``, neither of which appears in Polymarket's
    ``Set 1 Winner: Ku vs Hunter``, so four live questions on that match were
    refused for having a short surname.  ``Ku``, ``Hon`` and ``Wu`` are all in
    the measured corpus.

    What makes two safe is the stop-word strip rather than the length: the
    collision a short token risks is with the title's OWN vocabulary (``vs``,
    ``set``, ``o/u``), and those are removed by name.  A shared token between
    the two players is removed separately, upstream, so it can only ever cause
    a refusal.
    """
    out: set[str] = set()
    for name in names:
        if not name:
            continue
        out.update(
            token
            for token in _WORD_RE.findall(_fold(name))
            if len(token) >= 2 and token not in _TITLE_STOPWORDS
        )
    return out


def _first_token_position(folded_title: str, tokens: set[str]) -> Optional[int]:
    """Earliest whole-word occurrence of any token, or ``None``."""
    best: Optional[int] = None
    for token in tokens:
        for hit in re.finditer(rf"\b{re.escape(token)}\b", folded_title):
            if best is None or hit.start() < best:
                best = hit.start()
            break
    return best


def attribute_yes_side(
    title: str, players: list[dict[str, Any]]
) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """``(yes_entity_key, no_entity_key, refusal_reason)`` for one prop title.

    ``players`` is two dicts carrying ``entity_key`` plus any spellings to
    match on (``display_name``, ``source_label``).  Exactly one of the first
    two return values is populated, or the third is.

    THE SHARED-TOKEN STEP IS THE ONE THAT MATTERS.  Two players in one match
    can share a token — a compound surname, a common given name — and a token
    that belongs to both cannot decide between them.  Removing the intersection
    before searching means a shared token can only ever cause a REFUSAL, never
    a wrong answer.  Without it, ``Maria Sanchez`` vs ``Ana Sanchez`` resolves
    to whichever ``sanchez`` the title happens to print first.
    """
    if len(players) != 2:
        return None, None, "NOT_A_PAIR"

    folded = _fold(title)
    token_sets = [
        name_tokens(player.get("display_name"), player.get("source_label"))
        for player in players
    ]
    shared = token_sets[0] & token_sets[1]
    distinct = [tokens - shared for tokens in token_sets]
    if not distinct[0] or not distinct[1]:
        return None, None, "NO_DISTINGUISHING_NAME"

    positions = [_first_token_position(folded, tokens) for tokens in distinct]
    if positions[0] is None or positions[1] is None:
        return None, None, "PLAYER_NOT_IN_TITLE"
    if positions[0] == positions[1]:
        return None, None, "AMBIGUOUS_TITLE_ORDER"

    first, second = (0, 1) if positions[0] < positions[1] else (1, 0)
    return (
        str(players[first].get("entity_key")),
        str(players[second].get("entity_key")),
        None,
    )


# ───────────────────────── question shapes ─────────────────────────

#: ``Set 1 Winner: Dougaz vs Guerrieri``
_SET_WINNER_RE = re.compile(r"^\s*set\s+(\d+)\s+winner\b", re.I)
#: ``Dougaz vs. Guerrieri: Set 1 Games O/U 10.5``
_SET_GAMES_RE = re.compile(r"\bset\s+(\d+)\s+(?:games\s+)?o/u\s+(\d+(?:\.\d+)?)\s*$", re.I)
#: ``Aziz Dougaz vs. Andrea Guerrieri: Total Sets O/U 2.5``
_TOTAL_SETS_RE = re.compile(r"\btotal\s+sets:?\s+o/u\s+(\d+(?:\.\d+)?)\s*$", re.I)
#: ``Dougaz vs. Guerrieri: Match O/U 22.5`` — the total GAMES ladder.
#:
#: The noun is inferred and this is where it is written down.  Polymarket's
#: label says "Match", not "Games".  The measured strikes are 21.5 / 22.5 /
#: 23.5 on best-of-three qualifying matches, sitting beside an explicit
#: ``Total Sets O/U 2.5`` and an explicit ``Set 1 Games O/U 9.5``; the only
#: quantity in a best-of-three tennis match with that magnitude is games.
_MATCH_TOTAL_RE = re.compile(r"\bmatch\s+o/u\s+(\d+(?:\.\d+)?)\s*$", re.I)
#: ``Set Handicap: Dougaz (-1.5) vs Guerrieri (+1.5)`` / ``Game Spread: …``
_HANDICAP_RE = re.compile(
    r"^\s*(set\s+handicap|game\s+spread)\s*:\s*"
    r"(?P<a>.+?)\s*\(\s*(?P<aline>[-+]?\d+(?:\.\d+)?)\s*\)\s*"
    r"vs\.?\s*(?P<b>.+?)\s*\(\s*(?P<bline>[-+]?\d+(?:\.\d+)?)\s*\)\s*$",
    re.I,
)


def _plural(count: float, unit: str) -> str:
    return unit if abs(count - 1) < 1e-9 else f"{unit}s"


def threshold_labels(line: float, unit: str) -> Optional[tuple[str, str]]:
    """``(over_label, under_label)`` for a half-integer line, else ``None``.

    ``22.5`` becomes "More than 22 games" / "22 games or fewer", which is exact
    — a whole number of games cannot land on the line — and reads as English
    rather than as a betting line.

    A NON-HALF LINE IS REFUSED, and that is a correctness refusal rather than a
    copy one.  On an integer line the two outcomes are not complements: the tie
    is a push, ``push_void_capable`` says so on every one of these markets, and
    a pair that does not sum to the whole cannot be normalized into a split.
    Measured across the corpus: every line is a half.  The branch exists for
    the first one that is not, and it drops the card instead of printing a
    number whose meaning we would be guessing.
    """
    if not math.isfinite(line):
        return None
    floor = math.floor(line)
    if abs(line - floor - 0.5) > 1e-9:
        return None
    return (
        f"More than {floor} {_plural(floor, unit)}",
        f"{floor} {_plural(floor, unit)} or fewer",
    )


def handicap_label(name: str, line: float, unit: str) -> str:
    """"Dougaz by 2 sets or more" / "Dougaz wins more games"."""
    steps = math.ceil(line)
    if steps <= 1:
        return f"{name} wins more {unit}s"
    return f"{name} by {steps} {_plural(steps, unit)} or more"


def classify_prop(name: str) -> dict[str, Any]:
    """One market title -> the question it asks, in the reader's words.

    Returns ``{"family", "question", "sort", "line", "unit", "kind"}``.
    ``kind`` is ``duel`` (two named players), ``threshold`` (over/under) or
    ``handicap``; ``other`` falls through carrying the source's own title,
    which is honest and occasionally clumsy — the alternative is a page that
    silently omits a question because we had not written a sentence for it.
    """
    title = name or ""

    match = _SET_WINNER_RE.search(title)
    if match:
        number = int(match.group(1))
        return {
            "family": "set_winner",
            "kind": "duel",
            "question": f"Who wins set {number}",
            "sort": (0, number),
            "line": None,
            "unit": None,
        }

    match = _HANDICAP_RE.search(title)
    if match:
        unit = "set" if match.group(1).lower().startswith("set") else "game"
        return {
            "family": "handicap",
            "kind": "handicap",
            "question": f"Winning margin, in {unit}s",
            "sort": (1, 0 if unit == "set" else 1),
            "line": float(match.group("aline")),
            "unit": unit,
        }

    match = _MATCH_TOTAL_RE.search(title)
    if match:
        return {
            "family": "total",
            "kind": "threshold",
            "question": "Total games in the match",
            "sort": (2, 0),
            "line": float(match.group(1)),
            "unit": "game",
        }

    match = _TOTAL_SETS_RE.search(title)
    if match:
        return {
            "family": "total",
            "kind": "threshold",
            "question": "Total sets in the match",
            "sort": (2, 1),
            "line": float(match.group(1)),
            "unit": "set",
        }

    match = _SET_GAMES_RE.search(title)
    if match:
        number = int(match.group(1))
        return {
            "family": "total",
            "kind": "threshold",
            "question": f"Games in set {number}",
            "sort": (2, 2 + number),
            "line": float(match.group(2)),
            "unit": "game",
        }

    return {
        "family": "other",
        "kind": "other",
        "question": title,
        "sort": (3, 0),
        "line": None,
        "unit": None,
    }


# ───────────────────────── assembly ─────────────────────────


def _outcome_by_suffix(outcomes: list[dict[str, Any]], suffix: str) -> Optional[dict[str, Any]]:
    """The ``…_yes`` / ``…_no`` leg, chosen by EXTERNAL ID, not by ``name``.

    ``name`` is the word Polymarket printed and it varies by market shape —
    ``Yes``/``No`` on a sub-market, ``Over``/``Under`` on a threshold.  The
    external id suffix is the source's own structural marker and it is the same
    thing the register pins its own sides on, so both surfaces agree about
    which leg is which for exactly one reason.
    """
    for outcome in outcomes:
        external = str(outcome.get("external_id") or "")
        if external.endswith(f"_{suffix}"):
            return outcome
    return None


def _answer(
    label: str,
    entity_key: Optional[str],
    probability: Optional[float],
    opening: Optional[float],
    loaded: dict[str, Any],
    now: datetime,
) -> dict[str, Any]:
    observed = loaded.get("observed_at")
    observed = observed if isinstance(observed, datetime) else None
    age = (now - observed).total_seconds() / 3600.0 if observed else None
    state = price_state(age)
    return {
        "label": label,
        "entity_key": entity_key,
        "probability": round(probability, 6) if probability is not None else None,
        # WHAT THE MARKET THOUGHT BEFORE THE MATCH — the only number this page
        # may print once the match is decided.
        #
        # A prop market does not reliably settle: measured on the Fearnley /
        # Rodionov specimen, the match-winner market read 0.05% (settled) while
        # "Who wins set 1" still read the pre-match 62.5% hours after the set
        # had been played and won by the other man. Printing that current
        # number under a finished match is a live-looking question with a
        # stale answer, which is the exact failure `price_state` exists to
        # prevent and which no amount of muting makes true.
        #
        # The opening quote is guaranteed to pre-date the match — the same
        # argument `_prematch_by_pair` makes for the results section — so a
        # decided match's props are presented as the SCRIPT, not as questions.
        "opening_probability": round(opening, 6) if opening is not None else None,
        # ITS OWN freshness, never the card's (UX-P135). A card whose leader
        # refreshed an hour ago and whose other side is a day old must not
        # render either of them as live.
        "probability_is_live": state == "live" and probability is not None,
        "observed_at": observed.isoformat() if observed else None,
        "age_hours": round(age, 2) if age is not None else None,
        "price_state": state,
    }


def build_prop(
    market: dict[str, Any],
    *,
    players: list[dict[str, Any]],
    prices: dict[int, dict[str, Any]],
    now: datetime,
) -> tuple[Optional[dict[str, Any]], Optional[str]]:
    """One sibling market -> one rendered question, or a named refusal.

    ``market`` is ``{"market_id", "name", "outcomes": [{"outcome_id",
    "external_id", "name"}]}`` — a plain dict, loaded by the route.

    A TWO-SIDED QUOTE GOES THROUGH ``normalize_pair`` OR IT DOES NOT RENDER.
    These are independent binaries exactly as the match itself is (gotcha #23),
    so the same refusal applies for the same reason: ``0.90 + 0.60`` is two
    stale readings, and dividing them by 1.5 yields a 60/40 that has no
    referent and looks precisely like a real one.  An UNPRICED market is not
    that failure and still renders — lane1's caveat is that some legs are
    untradeable and ``#1578`` refuses a fabricated midpoint, so a prop can
    legitimately sit unpriced beside a priced sibling.
    """
    shape = classify_prop(str(market.get("name") or ""))
    outcomes = [o for o in (market.get("outcomes") or []) if isinstance(o, dict)]
    if len(outcomes) != 2:
        # A multi-outcome prop (an Exact Score field) is a real market shape and
        # a real future card; it is named as unsupported rather than silently
        # skipped, so the count that reaches the report is the truth.
        return None, "NOT_TWO_SIDED"

    yes = _outcome_by_suffix(outcomes, "yes")
    no = _outcome_by_suffix(outcomes, "no")
    if yes is None or no is None:
        return None, "NO_YES_NO_LEGS"

    yes_loaded = prices.get(yes.get("outcome_id")) or {}
    no_loaded = prices.get(no.get("outcome_id")) or {}
    raw_yes = yes_loaded.get("probability")
    raw_no = no_loaded.get("probability")
    raw_yes = float(raw_yes) if isinstance(raw_yes, (int, float)) else None
    raw_no = float(raw_no) if isinstance(raw_no, (int, float)) else None
    yes_p, no_p, raw_sum, coherent = normalize_pair(raw_yes, raw_no)

    # The opening pair is normalized on its OWN sum, never the current one —
    # each has its own overround, and mixing bases makes the difference an
    # artifact of the two sums rather than of the market moving (the slate
    # makes the same argument about the same two numbers).
    open_raw_yes = yes_loaded.get("opening_probability")
    open_raw_no = no_loaded.get("opening_probability")
    open_raw_yes = float(open_raw_yes) if isinstance(open_raw_yes, (int, float)) else None
    open_raw_no = float(open_raw_no) if isinstance(open_raw_no, (int, float)) else None
    open_yes, open_no, open_sum, open_coherent = normalize_pair(open_raw_yes, open_raw_no)

    yes_key: Optional[str] = None
    no_key: Optional[str] = None
    note: Optional[str] = None

    if shape["kind"] == "duel":
        yes_key, no_key, refusal = attribute_yes_side(str(market.get("name") or ""), players)
        if refusal is not None:
            return None, refusal
        yes_label = _display_name(players, yes_key)
        no_label = _display_name(players, no_key)

    elif shape["kind"] == "handicap":
        yes_key, no_key, refusal = attribute_yes_side(str(market.get("name") or ""), players)
        if refusal is not None:
            return None, refusal
        line = shape["line"]
        # THE MINUS MUST BE ON THE FIRST-NAMED SIDE, or the card is refused.
        # `_yes` is the first-named player and the affirmative sentence we are
        # about to write says they win BY the line. If the title ever puts the
        # plus first, that sentence inverts the market. Measured 24/24 today;
        # this guard is for the 25th.
        if line is None or line >= 0:
            return None, "HANDICAP_SIDE_UNCLEAR"
        yes_label = handicap_label(_display_name(players, yes_key), abs(line), shape["unit"])
        # The complement of "A by 2 sets or more" is every other result — B
        # winning, or A winning by one. Naming it exhaustively takes a clause
        # per format; "Anything else" is short, plain and always true.
        no_label = "Anything else"
        no_key = None

    elif shape["kind"] == "threshold":
        labels = threshold_labels(shape["line"], shape["unit"])
        if labels is None:
            return None, "NON_HALF_LINE"
        yes_label, no_label = labels

    else:
        # AN UNRECOGNISED FAMILY RENDERS ONLY IF ITS SIDES ARE READABLE.
        #
        # The seam matters: omitting a question because nobody has written a
        # sentence for it is how a page becomes quietly incomplete, so an
        # unknown market falls through here carrying the source's own title
        # and its own side labels.
        #
        # But the source's side labels are usually `Yes`/`No` or
        # `Over`/`Under`, and those are exactly the words the plain-language
        # ruling bans — a bare `Yes 53%` under a question is the failure the
        # register's first refusal exists to prevent, one market class along.
        # So a card whose sides are the source's structural words is REFUSED
        # and counted, and only a market that labels its own sides in English
        # gets the fallback.
        yes_label = str(yes.get("name") or "")
        no_label = str(no.get("name") or "")
        if {yes_label.strip().lower(), no_label.strip().lower()} & _SOURCE_SIDE_WORDS:
            return None, "UNREADABLE_SIDES"
        note = "Shown as the market words it."

    answers = [
        _answer(yes_label, yes_key, yes_p, open_yes, yes_loaded, now),
        _answer(no_label, no_key, no_p, open_no, no_loaded, now),
    ]

    times = [
        loaded.get("observed_at")
        for loaded in (yes_loaded, no_loaded)
        if isinstance(loaded.get("observed_at"), datetime)
    ]
    # A card with one leg never observed is as old as that leg — `None` in the
    # list is what makes `governing_age_hours` return None, so it is fed the
    # full pair rather than the survivors.
    both_times: list[Optional[datetime]] = [
        loaded.get("observed_at") if isinstance(loaded.get("observed_at"), datetime) else None
        for loaded in (yes_loaded, no_loaded)
    ]
    age = governing_age_hours(both_times, now)
    state = price_state(age)
    newest = freshest_observation(both_times)
    freshest_age = (now - newest).total_seconds() / 3600.0 if newest else None
    stale = [a["label"] for a in answers if a["probability"] is not None and a["price_state"] != "live"]

    return {
        "key": f"m{market.get('market_id')}",
        "market_id": market.get("market_id"),
        # Always a list, on every card, so a client never has to know whether
        # it is holding a rung or a ladder to say where a number came from.
        "market_ids": [market.get("market_id")],
        "family": shape["family"],
        "kind": shape["kind"],
        "question": shape["question"],
        "line": shape["line"],
        "unit": shape["unit"],
        "sort": list(shape["sort"]),
        "source_title": market.get("name"),
        "note": note,
        "answers": answers,
        # The honesty fields, same names and same meanings as a slate row's, so
        # the two halves of this page cannot word one admission two ways.
        "coherent": coherent,
        "raw_sum": raw_sum,
        # The script's own coherence. A decided match prints the opening pair,
        # so it needs its own verdict — an opening pair that does not sum is
        # refused for the same reason a current one is.
        "opening_coherent": open_coherent,
        "opening_raw_sum": open_sum,
        "probability_is_live": state == "live" and coherent,
        # `unpriced` is decided by whether there is a NUMBER, not by whether
        # there is a timestamp. An outcome whose snapshots stopped carrying a
        # probability keeps its last observation time, and reading liveness off
        # that alone would paint a card with nothing on it as live — gotcha
        # #53's shape, an absence taken for an answer.
        "price_state": (
            "unpriced" if raw_yes is None and raw_no is None else (state if times else "unpriced")
        ),
        "observed_at": min(times).isoformat() if age is not None and times else None,
        "age_hours": round(age, 2) if age is not None else None,
        "freshest_observed_at": newest.isoformat() if newest else None,
        "freshest_age_hours": round(freshest_age, 2) if freshest_age is not None else None,
        "stale_answers": stale,
        "mixed_freshness": 0 < len(stale) < len([a for a in answers if a["probability"] is not None]),
    }, None


def _display_name(players: list[dict[str, Any]], entity_key: Optional[str]) -> str:
    for player in players:
        if player.get("entity_key") == entity_key:
            return str(player.get("display_name") or entity_key or "")
    return str(entity_key or "")


def group_ladders(props: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Three strikes on one question become ONE card, not three.

    ``Match O/U 21.5``, ``22.5`` and ``23.5`` are the same question asked at
    three heights.  Rendered as three cards they are the ladder/bucket shape
    the Discover audit holds at ``ladder/bucket-rate@20=0``, and they are
    unreadable besides — the reader has to hold three near-identical titles in
    their head to see one monotone curve.  Rendered as one card with three
    rungs, the curve IS the card.

    A ladder shows only its "More than" rungs.  Each rung's complement is a
    real, separately-quoted number, but printing six rows to say what three say
    is the redundancy ruling 6 deleted from the match list.  A single-strike
    question keeps both sides, because there is no curve to read and the second
    number is the answer to the other half of the question.
    """
    by_question: dict[str, list[dict[str, Any]]] = {}
    for prop in props:
        by_question.setdefault(prop["question"], []).append(prop)

    out: list[dict[str, Any]] = []
    for question, members in by_question.items():
        if len(members) == 1 or members[0]["kind"] != "threshold":
            out.extend(members)
            continue
        rungs = sorted(members, key=lambda p: (p["line"] if p["line"] is not None else 0))
        first = rungs[0]
        out.append({
            **first,
            "key": f"ladder:{question}",
            "kind": "ladder",
            "market_id": None,
            "market_ids": [rung["market_id"] for rung in rungs],
            "line": None,
            "source_title": None,
            # The over rung of each strike, in ascending line order. Ascending
            # so the probabilities fall down the card, which is what monotone
            # looks like when you read top to bottom.
            "answers": [rung["answers"][0] for rung in rungs],
            "coherent": all(rung["coherent"] for rung in rungs),
            "raw_sum": None,
            "opening_coherent": all(rung["opening_coherent"] for rung in rungs),
            "opening_raw_sum": None,
            "probability_is_live": all(rung["probability_is_live"] for rung in rungs),
            "price_state": _worst_state([rung["price_state"] for rung in rungs]),
            "age_hours": max(
                (rung["age_hours"] for rung in rungs if rung["age_hours"] is not None),
                default=None,
            ),
            "stale_answers": [
                answer["label"]
                for rung in rungs
                for answer in [rung["answers"][0]]
                if answer["probability"] is not None and answer["price_state"] != "live"
            ],
        })
    out.sort(key=lambda p: (tuple(p["sort"]), p["question"]))
    return out


_STATE_RANK = {"live": 0, "stale": 1, "dark": 2, "unpriced": 3}


def _worst_state(states: list[str]) -> str:
    return max(states, key=lambda s: _STATE_RANK.get(s, 9)) if states else "unpriced"


def build_match_detail(
    register: dict[str, Any],
    matchup_key: str,
    *,
    prop_markets: list[dict[str, Any]],
    prices: dict[int, dict[str, Any]],
    result: Optional[dict[str, Any]],
    now: datetime,
) -> Optional[dict[str, Any]]:
    """The whole match page, or ``None`` when the register does not hold it.

    ``None`` is a 404 and never a nearest-match. The register's whole posture
    is that a slug does not infer (ruling 031's disease, #1793); a matchup key
    does not infer either, and answering a mistyped key with a plausible other
    match is the same defect one level down.
    """
    reg = TournamentRegister(register)
    matchup = next(
        (m for m in reg.matchups if str(m.get("matchup_key")) == matchup_key), None
    )
    if matchup is None:
        return None

    # `cutoff=None`: a page ABOUT one fixture is not a claim the fixture is
    # upcoming. See `build_match_row`.
    row, refusal = build_match_row(reg, matchup, prices=prices, now=now, cutoff=None)
    if row is None:
        # The register holds the matchup but it cannot be rendered as a match —
        # an unmapped side, an unregistered player. Honest 404 over a half page
        # assembled from whatever loaded.
        logger.warning("match detail %s unrenderable: %s", matchup_key, refusal)
        return None

    players = []
    entity_keys = matchup.get("players") or []
    live_block = next(
        (
            b for b in (matchup.get("sources") or [])
            if isinstance(b, dict) and b.get("status") == "live"
        ),
        None,
    )
    sides = (live_block or {}).get("sides") or {}
    for entity_key in entity_keys:
        player = reg.by_entity.get(entity_key) or {}
        players.append({
            "entity_key": entity_key,
            "display_name": player.get("display_name") or entity_key,
            # The SOURCE's own spelling of this player, pinned by the register.
            # Fed to the attribution rule beside our display name because the
            # market titles are written in the source's spelling, not ours.
            "source_label": (sides.get(entity_key) or {}).get("source_label"),
        })

    props: list[dict[str, Any]] = []
    dropped: dict[str, int] = {}
    for market in prop_markets[:MAX_PROPS_PER_MATCH]:
        prop, reason = build_prop(market, players=players, prices=prices, now=now)
        if prop is None:
            reason = reason or "UNKNOWN"
            dropped[reason] = dropped.get(reason, 0) + 1
            continue
        props.append(prop)

    over_cap = max(0, len(prop_markets) - MAX_PROPS_PER_MATCH)
    if over_cap:
        # NO SILENT CAPS. A truncated page reads as "this is everything".
        dropped["OVER_CAP"] = over_cap

    cards = group_ladders(props)

    if dropped:
        logger.info(
            "match detail %s dropped %s of %s sibling markets: %s",
            matchup_key, sum(dropped.values()), len(prop_markets), dropped,
        )

    return {
        "tournament": reg.tournament,
        "season": reg.season,
        "matchup_key": matchup_key,
        "match": row,
        # ESPN's verdict, joined by the register on the player pair, when the
        # match is decided. `None` for an upcoming one — never an empty score.
        "result": result,
        # SETTLED MEANS SETTLED (standing Alex ruling). A decided match's props
        # are not open questions and must not be presented as any: the client
        # reads `opening_probability` and titles the section as the script,
        # because a prop market does not reliably settle and its CURRENT number
        # can still be the pre-match one hours after the answer is known.
        # Decided is ESPN's verdict, not a clock comparison — a match that is
        # merely late is still on.
        "decided": result is not None,
        "props": cards,
        "props_count": len(cards),
        "props_markets": len(props),
        # Named reasons, never a silent short list. `build_slate` publishes the
        # same field for the same reason.
        "props_dropped": dict(sorted(dropped.items())),
        "generated_at": now.isoformat(),
    }
