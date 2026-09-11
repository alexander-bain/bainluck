"""T2-1 (#5058): the two season answers a team card carries, as pure logic.

WHAT A READER GETS. Type ``Patriots`` and the team row itself already says
``10+ regular-season wins: 47% · Make Playoffs: 49%`` — both answers, no click.
That is ship 7 (#4461) and the friend's ten-second task; this module is the half
that decides WHICH number those two sentences carry, and refuses to invent one.

THE TWO ANSWERS COME FROM DIFFERENT PLACES ON PURPOSE.

``make_playoffs``
    Lifted from the championship grid's own cell — the SAME
    ``merged_probability`` ``/api/playoffs/{slug}`` prints. Alex's standing
    ruling is that the blend is the product: one number per question. A second
    computation here, however careful, would be a second number for a question
    that already has one, and the day the two disagreed the reader would meet
    both on the same screen.

``season_wins``
    Elected out of the venue's own threshold ladder
    (``KX<LEAGUE>WINS-<season><code>``, one market per team, rungs named
    ``"10+ wins"``). The grid has no wins column, so there is nothing to reuse
    and this module does the electing — under the rules in
    :func:`pick_wins_rung`.

WHY SUBJECT RESOLUTION IS BY NAME AND NOT BY ``futures_outcomes.team_id``.
Measured on production 2026-09-11 against ``Pro Football Playoff Qualifiers``
(market 62679): of 32 outcomes, 8 carry no ``team_id`` at all and 4 carry the
WRONG one — ``Houston`` -> Houston Cougars (NCAAF), ``Carolina`` -> North
Carolina Tar Heels (NCAAF), ``Miami`` -> Miami Hurricanes (NCAAF), and
``Los Angeles C`` -> the Rams, which the Rams' own row also claims. Building a
reader-facing answer on that column would have printed the Chargers' season on
the Rams' card. The column is a hint, not an identity (#5119).

So membership is decided the way notice 40 requires: the venue's own structure
first (the ticker series says which league and which season), then a resolution
into OUR canonical name set that is REQUIRED TO BE UNIQUE. Two candidates or
none both mean "no answer" — never a best guess. Inside one league that rule is
strong: ``"Los Angeles C"`` prefixes exactly one of the NBA's thirty names, and
``"New York"`` prefixes exactly one.

PURE: no I/O, no ORM, no clock. Everything here takes data and returns data, so
the electing rules are testable without a database and without a live venue.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

__all__ = [
    "MAKE_PLAYOFFS_KEY",
    "SEASON_WINS_KEY",
    "SETTLEMENT_FLOOR",
    "SETTLEMENT_CEILING",
    "normalize_team_key",
    "parse_wins_ticker",
    "parse_wins_subject",
    "parse_wins_rung",
    "resolve_subject_to_team",
    "pick_wins_rung",
    "format_wins_label",
    "build_wins_answer",
    "build_playoff_answer",
    "order_answers",
]

#: The two answer keys a team card can carry. Ordered by
#: :func:`order_answers`; the wins answer leads because it is the one the
#: reader cannot get anywhere else on the site.
SEASON_WINS_KEY = "season_wins"
MAKE_PLAYOFFS_KEY = "make_playoffs"

#: A rung outside this band is not an answer, it is a settled market wearing a
#: price. A ladder whose every rung reads 1%/99% is the settlement tell (the
#: same one that makes a "live" outcome print an impossible number), and a
#: ``1+ wins: 100%`` line is worth no pixels even when it is true.
SETTLEMENT_FLOOR = 0.05
SETTLEMENT_CEILING = 0.95

#: ``KXNFLWINS-27NE`` -> series ``KXNFLWINS``, season ``27``, code ``NE``.
#: Kalshi writes the season as two digits with no separator before the team
#: code, which is why this is a parse and not a split.
_WINS_TICKER_RE = re.compile(r"^(?P<series>KX[A-Z]+WINS)-(?P<season>\d{2})(?P<code>[A-Z0-9]+)$")

#: ``Pro Football: New England Total Wins`` -> ``New England``. The competition
#: prefix is Kalshi's, not ours, and it is never part of the subject.
_WINS_SUBJECT_RE = re.compile(r"^(?:[^:]+:\s*)?(?P<subject>.+?)\s+Total\s+Wins\s*$", re.IGNORECASE)

#: ``10+ wins`` -> 10. Deliberately STRICT about the ``+``: the top rung of an
#: NFL ladder is named ``17 wins`` (17 is the whole season, so "17+" would be
#: odd), and on a different market ``9 wins`` could mean exactly nine. Reading
#: the bare form as a threshold would be reading a convention we have not
#: checked. Dropping it costs nothing — a maximum rung prices at 1% and can
#: never be the rung nearest 50%.
_WINS_RUNG_RE = re.compile(r"^(?P<n>\d+)\+\s*wins$", re.IGNORECASE)


def normalize_team_key(name: str | None) -> str:
    """Fold a team name to the key both sides of the projection agree on.

    Accents and punctuation vary between our team table and a venue's market
    name for the same club, and neither spelling is wrong. Case, accents,
    punctuation and repeated whitespace all fold away; nothing else does.
    """
    if not name:
        return ""
    decomposed = unicodedata.normalize("NFKD", str(name))
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    lowered = stripped.casefold()
    cleaned = re.sub(r"[^a-z0-9]+", " ", lowered)
    return cleaned.strip()


def parse_wins_ticker(external_id: str | None) -> tuple[str, str, str] | None:
    """``(series, season, team_code)`` for a Kalshi season-wins market ticker.

    ``None`` for anything that is not one. This is the FIRST of the two signals
    notice 40 requires: it is the venue's own structure saying "this market is
    the 2027 NFL season-wins question for the team Kalshi calls NE".
    """
    if not external_id:
        return None
    match = _WINS_TICKER_RE.match(str(external_id).strip())
    if not match:
        return None
    return match.group("series"), match.group("season"), match.group("code")


def parse_wins_subject(market_name: str | None) -> str | None:
    """The team-shaped part of a season-wins market name, or ``None``."""
    if not market_name:
        return None
    match = _WINS_SUBJECT_RE.match(str(market_name).strip())
    if not match:
        return None
    subject = match.group("subject").strip()
    return subject or None


def parse_wins_rung(outcome_name: str | None) -> int | None:
    """``"10+ wins"`` -> ``10``. ``None`` for any other outcome name."""
    if not outcome_name:
        return None
    match = _WINS_RUNG_RE.match(str(outcome_name).strip())
    if not match:
        return None
    return int(match.group("n"))


def resolve_subject_to_team(
    subject: str | None,
    teams: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Resolve a venue's subject string to exactly one of OUR league teams.

    ``teams`` are the league's own rows (``name`` at minimum) — the grid's team
    list, so the candidate set is closed at thirty-odd names and a stray college
    namesake is not even in the room.

    Two passes, both requiring UNIQUENESS:

    1. exact folded-name equality;
    2. folded prefix — ``"New England"`` reaches ``"New England Patriots"`` and
       ``"Los Angeles C"`` reaches the Clippers and nothing else.

    A prefix that fits two teams, or none, returns ``None``. That is the whole
    guard: an ambiguous subject produces no answer rather than a plausible one,
    which is the difference between a card that is sometimes empty and a card
    that is sometimes lying.
    """
    key = normalize_team_key(subject)
    if not key:
        return None

    exact = [t for t in teams if normalize_team_key(t.get("name")) == key]
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        return None

    # Whole-word prefix first: "New England" -> "New England Patriots".
    word_prefixed = [
        t for t in teams
        if (normalize_team_key(t.get("name")) or "\0").startswith(key + " ")
    ]
    if len(word_prefixed) == 1:
        return word_prefixed[0]
    if len(word_prefixed) > 1:
        return None

    # Then PARTIAL prefix, because the venue's own disambiguator is a single
    # letter with no space after it: Kalshi writes the two Los Angeles clubs as
    # "Los Angeles C" and "Los Angeles R", and a word-boundary rule reaches
    # neither. Looser, and still refuses to choose: bare "Los Angeles" fits both
    # and therefore answers nothing.
    partly_prefixed = [
        t for t in teams
        if (normalize_team_key(t.get("name")) or "\0").startswith(key)
    ]
    if len(partly_prefixed) == 1:
        return partly_prefixed[0]
    return None


def pick_wins_rung(rungs: list[tuple[int, float]]) -> tuple[int, float] | None:
    """Elect the one rung of a wins ladder the card will show.

    ``rungs`` is ``[(threshold, probability), ...]`` in any order.

    Four rules:

    * **The ladder must run the right way.** Its lowest threshold must not price
      below its highest: "1 or more wins" cannot be less likely than "16 or
      more". A ladder that fails this is inverted or garbage as a whole, and no
      rung of it is worth printing.
    * **Nearest 50%, inside the settlement band.** The rung a reader learns the
      most from is the one the market is least sure about — decision C's
      "supported threshold nearest 50%".
    * **Ties go to the LOWER threshold**, i.e. to the rung above 50%. With
      ``9+`` at 55% and ``10+`` at 45% both five points away, "9+ wins: 55%" is
      the sentence a person reads more easily than its mirror image.
    * **The elected rung must be locally coherent**: the rung one threshold
      below it must not price lower, and the rung one above must not price
      higher. This, and not whole-ladder monotonicity, is the guard that
      matches the claim — the card says one sentence about one rung, and what
      contradicts "10+ wins: 46%" is "11+ wins: 52%", not a wobble between the
      15+ and 16+ rungs nobody is being shown.

    🔴 WHY NOT WHOLE-LADDER MONOTONICITY, which was the first rule written here.
    Measured against production 2026-09-11, all 33 open ``KXNFLWINS-27*``
    ladders: only **8** are monotone end to end, but **33 of 33** are coherent
    around the rung this elects. The violations are concentrated in the tail —
    thirteen of the twenty-five have a maximum violation of two points or less,
    and the typical offender is a pair like ``15+ 3%`` / ``16+ 7%``, which is
    bid-ask noise on a rung nobody trades. Refusing on that would have cost the
    reader twenty-five of thirty-two NFL teams to protect them from a number
    they were never going to see. The tail wobble is real and is filed as its
    own defect (#5121); it is not a reason to withhold the mid-ladder answer.

    Returns ``None`` for an empty, inverted, locally incoherent or fully-settled
    ladder.
    """
    priced = [(int(t), float(p)) for t, p in rungs if p is not None]
    if not priced:
        return None

    ordered = sorted(priced, key=lambda tp: tp[0])
    if ordered[0][1] < ordered[-1][1]:
        return None

    live = [
        (t, p) for t, p in ordered
        if SETTLEMENT_FLOOR <= p <= SETTLEMENT_CEILING
    ]
    if not live:
        return None

    # 🔴 The distance is ROUNDED before it is compared. `abs(0.55 - 0.5)` and
    # `abs(0.45 - 0.5)` are not equal in binary floating point, so an unrounded
    # key silently decides a "tie" by whichever way the last bit fell — and the
    # tie-break below, which exists to make that choice deliberately, would
    # never run.
    chosen = min(live, key=lambda tp: (round(abs(tp[1] - 0.5), 6), tp[0]))

    at = ordered.index(chosen)
    if at > 0 and ordered[at - 1][1] < chosen[1]:
        return None
    if at < len(ordered) - 1 and ordered[at + 1][1] > chosen[1]:
        return None
    return chosen


def format_wins_label(threshold: int) -> str:
    """``10`` -> ``"10+ regular-season wins"`` (Alex's ruling aa, 2026-09-09).

    "regular-season" is load-bearing and not decoration: the ladder settles on
    the regular season alone, and a reader who assumes playoff wins count is
    reading a different question than the one the market answers.
    """
    return f"{int(threshold)}+ regular-season wins"


def build_wins_answer(
    *,
    threshold: int,
    probability: float,
    season: str | None,
    market_id: int | None,
    outcome_id: int | None,
    source: str | None,
    market_name: str | None,
    observed_at: str | None,
) -> dict[str, Any]:
    """The wire shape of the wins answer.

    Every field a consumer needs to trace the sentence back to the row it came
    from travels with it — subject and season are the family's identity,
    ``market_id``/``outcome_id`` are the provenance, ``observed_at`` is when the
    venue last moved the price. Deliberately NOT the projection's own write
    time: a cached number labelled with the moment it was cached is a lie about
    freshness (decision D).
    """
    return {
        "key": SEASON_WINS_KEY,
        "label": format_wins_label(threshold),
        "probability": round(float(probability), 4),
        "threshold": int(threshold),
        "season": season,
        "market_id": market_id,
        "outcome_id": outcome_id,
        "observed_at": observed_at,
        "sources": [
            {
                "source": source,
                "probability": round(float(probability), 4),
                "market_name": market_name,
            }
        ],
    }


def build_playoff_answer(
    cell: dict[str, Any] | None,
    *,
    label: str,
    season: str | None,
) -> dict[str, Any] | None:
    """The wire shape of the playoff answer, from a grid ``make_playoffs`` cell.

    ``state`` is the grid's own vocabulary and the reason this reads it rather
    than the probability alone: a ``settled`` or ``missing`` cell is a terminal
    state, not a number to print beside a live one. Only ``live`` becomes an
    answer; everything else is an honest absence.
    """
    if not isinstance(cell, dict):
        return None
    if cell.get("state") != "live":
        return None
    probability = cell.get("merged_probability")
    if probability is None:
        return None
    try:
        value = float(probability)
    except (TypeError, ValueError):
        return None
    if not 0.0 <= value <= 1.0:
        return None
    sources = [
        {
            "source": s.get("source"),
            "probability": s.get("probability"),
            "market_name": s.get("market_name"),
        }
        for s in (cell.get("sources") or [])
        if isinstance(s, dict)
    ]
    return {
        "key": MAKE_PLAYOFFS_KEY,
        "label": label,
        "probability": round(value, 4),
        "season": season,
        "sources": sources,
    }


#: Reading order on the card. The wins answer leads: it is the fact no other
#: surface of the product carries, and Alex's own example sentence puts it
#: first ("9+ regular-season wins: X% · Make playoffs: Y%").
_ANSWER_ORDER = (SEASON_WINS_KEY, MAKE_PLAYOFFS_KEY)


def order_answers(answers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Sort answers into reading order, dropping anything unrecognised.

    Unrecognised keys are DROPPED rather than appended: this list is rendered
    into a fixed two-fact line on a dropdown row, and a third unplanned fact
    would silently change what a reader sees without anyone deciding it should.
    """
    by_key = {a.get("key"): a for a in answers if isinstance(a, dict)}
    return [by_key[k] for k in _ANSWER_ORDER if k in by_key]
