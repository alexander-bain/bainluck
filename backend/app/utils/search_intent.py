"""Explicit question intent in a search query — T2-3 (#5060), ship 7 (#4461).

WHAT THIS IS FOR. A reader who types ``Patriots playoffs`` has asked a *question*,
not merely named a team. Before this module the query was one opaque string handed
to the match-class scorer, so the two extra characters could only ever make the
ranking WORSE: ``patriots`` lands the team at MC0 on an owned alias, and
``patriots playoffs`` lands it at MC3 (partial tokens) because the team owns no
name containing "playoffs". The more precisely a reader asked, the further the
answer fell.

THE RULING THIS SITS UNDER (ruling 041, narrowly amended — Alex, decision bb),
recorded here because the amendment is addendum text in T2-3's PR and never a new
ruling file:

    Ruling 041 forbids an intent classifier deciding WHO the reader means. That
    stands, whole. Identity is still resolved on owned evidence by
    `search_match_class` and by nothing here. The amendment is downstream of
    identity: once the subject is resolved on owned evidence, an EXPLICIT question
    in the query may lead the composition of that subject's results. A bare name
    still means the entity first.

So this module is deliberately NOT a classifier. It answers one question —
"did the reader literally write one of seven known question-scaffolds?" — over a
closed vocabulary, with no model, no request-time LLM, and no scoring. When the
reader did not, it returns ``None`` and every existing behaviour is untouched.
That is the whole safety argument for the ``ai`` / ``ipo`` / weather / award
controls in T2-3's acceptance: those queries match no scaffold, so they do not
reach any new code path at all.

THE SEVEN. The taxonomy is the design's own list, quoted: "next team, playoffs,
division, today, a year, N wins, make cut". It is enumerated, not generated.
``championship`` is deliberately NOT here: it appears in the design only as a rung
of the DEFAULT ordering for a bare name, never in its list of explicit terms, and
a term that cannot be typed cannot lead a composition.

WHY A NEW GRAMMAR RATHER THAN `ladder_monotonicity.parse_threshold` — MEASURED,
not assumed (2026-09-12, on this tree)::

    parse_threshold('over 8.5 wins')   -> ((0, 9), 8.5, 'dec')
    parse_threshold('at least 10 wins')-> ((0, 12), 10.0, 'dec')
    parse_threshold('10 wins')         -> None
    parse_threshold('9+ wins')         -> None

Its grammar requires a direction WORD, because it parses MARKET NAMES, where the
word is always present. Both bare forms T2-3's acceptance names return ``None``.
So the direction-word forms are DELEGATED to it — one grammar, not two, for the
half it already owns — and only the bare forms are new. Reuse where reuse is real.

WHAT A SCAFFOLD MAY NOT DO. Three refusals, each of which is a mutation target in
`test_search_intent_5060.py`:

1. **A scaffold with no subject left is not an intent.** ``playoffs`` alone
   resolves no entity, so there is nothing for the question to lead; it stays a
   generic query. This is what keeps the amendment downstream of identity.
2. **Word boundaries, never substrings.** ``division`` must not fire on
   "Divisional", ``today`` must not fire on "Todays". A substring rule here would
   re-create the exact failure family the match-class scorer was built to end —
   ``ai`` answering "1. FC K-a-i-serslautern".
3. **A bare year is only a year in a query that already has a subject AND is not
   itself the subject.** "2026" alone is not a season qualifier, and a four-digit
   run inside a name is not a year.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

from app.utils.ladder_monotonicity import parse_threshold as _parse_threshold_word

# ── The seven kinds ──────────────────────────────────────────────────────────
#
# Strings, not an Enum, because these cross to both clients in the ordered
# response and a client reads them as data. Frozen as a set so a kind added
# without a decision here fails the vocabulary test rather than silently
# shipping.
INTENT_NEXT_TEAM: Final = "next_team"
INTENT_PLAYOFFS: Final = "playoffs"
INTENT_DIVISION: Final = "division"
INTENT_TODAY: Final = "today"
INTENT_SEASON_YEAR: Final = "season_year"
INTENT_WIN_TOTAL: Final = "win_total"
INTENT_MAKE_CUT: Final = "make_cut"

INTENT_KINDS: Final[frozenset[str]] = frozenset({
    INTENT_NEXT_TEAM,
    INTENT_PLAYOFFS,
    INTENT_DIVISION,
    INTENT_TODAY,
    INTENT_SEASON_YEAR,
    INTENT_WIN_TOTAL,
    INTENT_MAKE_CUT,
})

#: A season a reader can plausibly mean. Bounded on BOTH sides deliberately: an
#: unbounded 4-digit rule reads the "1899" in a club's founding year and the
#: "2026" in a market's own name as a season qualifier. The upper bound is not a
#: clock read — a fixed pair keeps the parse deterministic under `clock_sweep`
#: (gotcha #44: a test anchor that branches on the clock is not fixed), and a
#: season beyond it is a question nobody can answer yet anyway.
SEASON_MIN: Final = 2000
SEASON_MAX: Final = 2030


@dataclass(frozen=True)
class SearchIntent:
    """One explicit question found in a query, and the subject it was asked of.

    ``subject`` is the query with the scaffold removed and nothing else removed:
    the qualifiers a reader typed (threshold, season, negation) are LIFTED into
    their own fields rather than discarded, which is the design's "keep
    season/threshold/negation/time qualifiers when stripping scaffolds". A
    qualifier dropped on the floor here becomes a wrong answer downstream that
    looks confidently right — the reader asked for 2025 and is shown 2026.
    """

    kind: str
    subject: str
    threshold: float | None = None
    season: int | None = None
    negated: bool = False


# ── Scaffold grammars ────────────────────────────────────────────────────────
#
# Every pattern is anchored with \b on both sides of the literal words. See
# refusal 2 in the module docstring: these fire on words, never on runs of
# characters inside a longer word.

_NEXT_TEAM_RE = re.compile(r"\b(?:next|new)\s+team\b", re.I)
# "playoff" and "playoffs" both, and the verb forms a reader actually types.
# `\bplayoffs?\b` alone would also serve, but naming the verbs keeps the strip
# clean: "make the playoffs" must leave "patriots", not "patriots make the".
_PLAYOFFS_RE = re.compile(
    r"\b(?:(?:to\s+)?(?:make|makes|reach|reaches|qualify\s+for)\s+(?:the\s+)?)?playoffs?\b",
    re.I,
)
_DIVISION_RE = re.compile(
    r"\b(?:(?:to\s+)?(?:win|wins|take|takes)\s+(?:the\s+)?)?division\b", re.I
)
_TODAY_RE = re.compile(r"\b(?:today|tonight)\b", re.I)
_MAKE_CUT_RE = re.compile(r"\b(?:to\s+)?(?:make|makes)\s+(?:the\s+)?cut\b", re.I)

#: The bare win-total forms — the two `parse_threshold` measurably cannot see.
#: `9+ wins` and `10 wins`. The unit word is required: a bare number is a year,
#: a jersey, or a nickname ("49ers"), never a win total.
_BARE_WIN_TOTAL_RE = re.compile(
    r"\b(?P<val>\d{1,3})\s*(?P<plus>\+)?\s+(?:regular[\s-]season\s+)?wins?\b", re.I
)
#: The direction-word forms, located here and PARSED by `parse_threshold`.
#: Located separately because that function returns a span over the string it
#: was given and we need the span in query coordinates to strip it.
_WORD_WIN_TOTAL_RE = re.compile(
    r"\b(?:over|under|at\s+least|at\s+most|more\s+than|fewer\s+than|less\s+than)"
    r"\s+\d[\d,]*(?:\.\d+)?\s*\+?\s+(?:regular[\s-]season\s+)?wins?\b",
    re.I,
)
#: The UNNUMBERED form — "Patriots wins", named in #5060's acceptance beside
#: `Patriots playoffs` and `Patriots 10 wins`. It is a win-total question whose
#: rung the reader did not state, which is a designed state and not a defect:
#: decision C answers it with "the supported threshold nearest 50%". Refusing it
#: here would send the query back to the bare-name default, where the win
#: question is third behind the team card and the game — which is precisely the
#: ordering the reader overrode by typing the word.
_BARE_WINS_RE = re.compile(r"\b(?:regular[\s-]season\s+)?wins?\b", re.I)

_SEASON_RE = re.compile(r"\b(?P<year>\d{4})\b")

#: Negation a reader types around a question. "miss the playoffs", "won't make
#: the cut", "not win the division". Captured, never stripped from meaning: an
#: intent whose negation is dropped answers the opposite question.
_NEGATION_RE = re.compile(
    r"\b(?:miss|misses|missing|not|non|won'?t|will\s+not|fail|fails|fail\s+to)\b",
    re.I,
)

#: Scaffold words that are pure question-grammar and carry no identity. Removed
#: from the subject only AFTER a scaffold has already matched, so a generic query
#: never loses a token to this list.
_RESIDUAL_SCAFFOLD_RE = re.compile(
    r"\b(?:will|does|do|is|are|the|a|an|to|of|in|for|make|makes|win|wins|"
    r"miss|misses|won'?t|not|fail|fails|reach|reaches|take|takes|qualify)\b",
    re.I,
)

#: Order matters and is a decision, not an accident. The most SPECIFIC scaffold
#: wins, so that "patriots 10 wins" is a win total rather than a bare season
#: year, and "mahomes next team" is a transfer question rather than a playoff
#: one. Each entry is (kind, pattern); the first to match the query claims it.
#: `win_total` precedes `season_year` because "10 wins" contains no year but
#: "patriots 2025 wins" contains both, and the reader's question is the wins.
#:
#: `_BARE_WINS_RE` is LAST, and that position is load-bearing rather than
#: cosmetic: "wins" is a word the division and playoff scaffolds contain
#: ("patriots win the division", "patriots to win division"). Placed earlier it
#: would claim those queries as win totals and answer the wrong question. Two
#: guard cases pin the ordering in `test_search_intent_5060.py`.
_SCAFFOLDS: Final[tuple[tuple[str, re.Pattern[str]], ...]] = (
    (INTENT_NEXT_TEAM, _NEXT_TEAM_RE),
    (INTENT_MAKE_CUT, _MAKE_CUT_RE),
    (INTENT_WIN_TOTAL, _WORD_WIN_TOTAL_RE),
    (INTENT_WIN_TOTAL, _BARE_WIN_TOTAL_RE),
    (INTENT_PLAYOFFS, _PLAYOFFS_RE),
    (INTENT_DIVISION, _DIVISION_RE),
    (INTENT_TODAY, _TODAY_RE),
    (INTENT_WIN_TOTAL, _BARE_WINS_RE),
)


def _clean(text: str) -> str:
    """Collapse the whitespace a strip leaves behind, and trim punctuation."""
    return re.sub(r"\s+", " ", text).strip(" \t\n-,.:;?!").strip()


def _season_in(query: str) -> tuple[int | None, tuple[int, int] | None]:
    """The season a reader named, and its span, or ``(None, None)``.

    Bounded by `SEASON_MIN`/`SEASON_MAX` — see their comment for why an unbounded
    4-digit rule is wrong rather than merely loose.
    """
    for m in _SEASON_RE.finditer(query):
        year = int(m.group("year"))
        if SEASON_MIN <= year <= SEASON_MAX:
            return year, m.span()
    return None, None


def _threshold_in(query: str, span: tuple[int, int], kind: str) -> float | None:
    """The win total inside an already-matched win-total span.

    The direction-word half is handed to `ladder_monotonicity.parse_threshold`
    rather than re-parsed; only the bare half is read here.
    """
    fragment = query[span[0]:span[1]]
    word = _parse_threshold_word(fragment)
    if word is not None:
        return word[1]
    bare = _BARE_WIN_TOTAL_RE.search(fragment)
    if bare is not None:
        return float(bare.group("val"))
    return None


def parse_intent(query: str | None) -> SearchIntent | None:
    """The explicit question in ``query``, or ``None`` for a generic query.

    ``None`` is the overwhelmingly common answer and is the safe one: it means
    every caller behaves exactly as it did before this module existed. A caller
    must therefore treat ``None`` as "carry on", never as an error.

    Refusal 1 from the module docstring lives here: a scaffold that consumes the
    whole query leaves no subject, and an intent with no subject is not an
    intent — there is no entity for the question to lead. ``playoffs`` typed
    alone is a generic search, and that is correct.
    """
    if not query:
        return None
    raw = query.strip()
    if not raw:
        return None

    for kind, pattern in _SCAFFOLDS:
        m = pattern.search(raw)
        if m is None:
            continue

        # ``None`` here is a designed state, not a failure: the reader named the
        # win question without naming a rung ("Patriots wins"). Decision C
        # resolves it downstream with the supported threshold nearest 50%.
        threshold = (
            _threshold_in(raw, m.span(), kind) if kind == INTENT_WIN_TOTAL else None
        )

        remainder = raw[: m.start()] + " " + raw[m.end():]

        season, season_span = _season_in(remainder)
        if season_span is not None:
            remainder = (
                remainder[: season_span[0]] + " " + remainder[season_span[1]:]
            )

        negated = _NEGATION_RE.search(raw) is not None

        subject = _clean(_RESIDUAL_SCAFFOLD_RE.sub(" ", remainder))
        if not subject:
            # Refusal 1. No subject, no intent.
            return None

        return SearchIntent(
            kind=kind,
            subject=subject,
            threshold=threshold,
            season=season,
            negated=negated,
        )

    # No scaffold, but a reader may still have named a season beside an entity
    # ("patriots 2025"). That is an explicit time qualifier and the design lists
    # "a year" among the seven, so it is an intent in its own right — but only
    # when something is left over to be the subject.
    season, season_span = _season_in(raw)
    if season is not None and season_span is not None:
        remainder = raw[: season_span[0]] + " " + raw[season_span[1]:]
        # The SAME residual strip the scaffold path uses, and for the same
        # reason: without it "2025 wins" yields the subject "wins", which names
        # no entity and so cannot satisfy refusal 1. Two paths that disagree
        # about what a subject is would be two rules.
        subject = _clean(_RESIDUAL_SCAFFOLD_RE.sub(" ", remainder))
        if subject:
            return SearchIntent(
                kind=INTENT_SEASON_YEAR,
                subject=subject,
                season=season,
                negated=_NEGATION_RE.search(raw) is not None,
            )

    return None
