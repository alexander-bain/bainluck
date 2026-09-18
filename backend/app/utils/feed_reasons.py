"""
Template-based reason generation for the unified feed.

Generates 1-line explanations for why a feed item is interesting.
Returns empty string when the card UI already tells the story — avoids
repeating scores, odds, or team names visible on the card.
"""

import re
from datetime import datetime, timezone
from typing import Mapping, NamedTuple, Optional

from app.utils.graded_card import rendered_percent
from app.utils.highlights import CLOSE_MATCHUP_MIN, select_live_claim
from app.utils.outcome_display_names import (
    display_outcome_name,
    display_outcome_names,
)

#: Words about our own machinery — the ordering of our leaderboard, the number of
#: rows we hold for a question, whether our sources agree with each other. None of
#: them is a thing that happened in the world, so none of them may reach a reader
#: (#4133, #4160; notice 34). Two standing rulings say the same thing from two
#: directions: attribution is BY NAME in the source mark, never an anonymous count
#: (D91), and source divergence is a data bug to fix, not a feature to show.
#:
#: This tuple is the ban list, not a description of one: the guard in
#: `tests/test_feed_reasons_serve_no_diagnostics_4160.py` drives every branch of
#: the three generators below and fails on any output that matches it, so a new
#: branch cannot reintroduce the class. `feed_quality_debug.WHY_NOW_MARKERS` — the
#: vocabulary that CREDITS a card with having explained itself — is asserted
#: disjoint from it by the same test.
DIAGNOSTIC_PHRASES: tuple[str, ...] = (
    "ranking change",
    "tracked by",
    "sources disagree",
    "sources tracking",
    "multi-source",
    "across 2 sources",
)

#: The same ban, for the shapes that carry a live count instead of a fixed word.
DIAGNOSTIC_PHRASE_RE = re.compile(
    r"\b\d+\s+sources?\b|\bacross\s+\d+\s+sources?\b", re.IGNORECASE
)


# ── A DURATION IS NOT A CALENDAR WORD (D1 clause a, #4805) ───────────────────
#
# The two resolution rungs used to render as "resolves this week" and "resolves
# this month". Their predicate is a DURATION — `days_until <= 7` and
# `<= 30` in `futures_highlights.py` — so a calendar word was right only for the
# cards whose window happened not to cross a boundary. Measured on the served
# `GET /api/feed?limit=250`, 2026-09-10 14:39Z, over every card that fired a
# clause, classified in the reader's own zone (America/New_York and
# America/Los_Angeles agree):
#
#   - "resolves this month": 16 cards, 6 resolve in OCTOBER. "Online Sportsbook
#     Ad Spend in September … resolves this month" is the sharpest: the title
#     names one month and the caption means another.
#   - "resolves this week": 8 cards, 7 resolve NEXT week. Read on a Thursday,
#     five Netflix questions closing the following Tuesday all claimed this one.
#
# THE DATE IS NOT NAMED HERE, AND THAT IS THE OLDER RULING, NOT A SHORTCUT. The
# comment above `BinaryCardCopy` states it: the card already prints its own
# "Resolves <date>" chip, the chip renders the instant in the READER's timezone,
# and this module only has UTC. The BEFORE LOOK for #4805 is that comment coming
# true — the Brazil card's chip read "Resolves Oct 3, 2026" while the wire
# carried `2026-10-04T00:00Z`, so a date emitted here would have sat two lines
# above the chip and disagreed with it by a day.
#
# Making the PREDICATE match the words was refused for the same reason: a
# calendar boundary is a fact about the reader's zone, not ours. `Anthropic
# market share this week` closes `2026-09-14T03:59Z` — Monday in UTC, Sunday
# ("Closes Sep 13", its own chip) for every US reader. Whichever way this module
# computed the boundary it would be wrong for somebody.
#
# So the words are made to match the predicate, which is the one statement that
# is true in every timezone at every hour: a duration. The chip still owns the
# date, and these two strings no longer contradict it.
#
#: The 30d headline is a THREE-WAY handshake, not a literal: it is compared by
#: `generate_futures_context_summary` below, it is duplicated by
#: `futures_highlights.PRIMARY_REASON_LABELS` (whose value reaches the same
#: parameter via `headline or primary_reason` in `routes/feed.py`), and it is a
#: member of `feed_market_quality._GENERIC_HEADLINES`. All three import or are
#: tested against these names — `test_resolution_copy_is_a_duration_4805.py`
#: asserts the join, because a producer and a consumer that agree on a
#: vocabulary with nothing testing it is exactly how #4695 happened.
RESOLVING_WITHIN_WEEK_HEADLINE = "Resolving within a week"
RESOLVING_WITHIN_MONTH_HEADLINE = "Resolving within a month"


def contains_diagnostic_phrase(text: str | None) -> bool:
    """True when a served string talks about our pipeline instead of the world."""
    lowered = (text or "").lower()
    if any(phrase in lowered for phrase in DIAGNOSTIC_PHRASES):
        return True
    return bool(DIAGNOSTIC_PHRASE_RE.search(lowered))


#: Words that measure a price against a BASELINE. Naming one is allowed; naming
#: one without saying when it was taken is not (D1 clause a, #4066).
BASELINE_PHRASES: tuple[str, ...] = ("opening", "from open", "since open")

#: The only dated baseline this codebase composes: `format_baseline_date` renders
#: "Mar 4" / "Mar 4, 2025", always behind the word "since".
_DATED_BASELINE_RE = re.compile(
    r"\bsince\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{1,2}\b",
    re.IGNORECASE,
)


def claims_undated_baseline(text: str | None) -> bool:
    """True when a served string measures against a baseline it will not date.

    D1 clause a (#4066): a move "from opening" is context and always carries its
    date; it is never the headline reason. An undated one is not a fact about
    this morning — the opening it cites may be a year old, and on the market that
    prompted this it was, with the card resolving in 2030.

    This is a SEPARATE predicate from `contains_diagnostic_phrase`, not a few
    more entries in `DIAGNOSTIC_PHRASES`, because the two ban different things
    and one of them is conditional. "Sources disagree" is never sayable; "up 27.0
    points since Mar 4" is sayable and good, and differs from the banned string
    only by carrying the date. A ban list of fixed substrings cannot express
    "unless you also say when", which is why the #4160 guard — which imports the
    fallback label table and drives the composed `headline or primary_reason`
    expression, so it looked at "Well off its opening price" on every run —
    passed it every time. The guard's REACH was right and its PREDICATE was
    short.
    """
    lowered = (text or "").lower()
    if not any(phrase in lowered for phrase in BASELINE_PHRASES):
        return False
    return not _DATED_BASELINE_RE.search(lowered)


def _side_label(name: str) -> str:
    """Make binary Yes/No outcome labels read naturally in movement text."""
    if name.strip().lower() in {"yes", "no"}:
        return f"{name.strip()} side"
    return name


_MONTH_DAY_RE = re.compile(
    r"^(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
    r"\s+\d{1,2}(?:,\s*\d{4})?$",
    re.IGNORECASE,
)
_NUMERIC_OR_THRESHOLD_RE = re.compile(
    r"^(?:[<>]=?|[+\-]|\u2191|\u2193)?\$?\d+(?:[\.,]\d+)?\s*(?:%|bps|bp|k|m|b|t|x)?$",
    re.IGNORECASE,
)


def _weak_outcome_label(name: str | None) -> bool:
    """Return true when an outcome label needs the market title for context."""
    label = (name or "").strip()
    if not label:
        return True
    lower = label.lower()
    if lower in {"yes", "no", "no change"}:
        return False
    if _MONTH_DAY_RE.match(label):
        return True
    if _NUMERIC_OR_THRESHOLD_RE.match(label):
        return True
    if re.fullmatch(r"\d+(?:\s*\([^)]+\))?", label):
        return True
    return False


#: #6470 — the preposition whose elision this module knows how to repay. The
#: display rule (`market_display_name`) deletes one of six words; only this one
#: makes the outcome a DEADLINE, which is the only claim the level clause below
#: is licensed to make. "on"/"at" name a point rather than a bound and would
#: turn "40% by December 31" into a different, unmeasured sentence, so they are
#: left silent exactly as today.
DEADLINE_PREPOSITION = "by"


def _date_outcome_label(name: str | None) -> str | None:
    """The label when it is a bare calendar date, else ``None``.

    The POSITIVE half of the `_MONTH_DAY_RE` arm of :func:`_weak_outcome_label`,
    and deliberately the same pattern rather than a second one: this function
    may only speak about labels that function refuses, so sharing the regex is
    what makes "names a date" and "is unnameable as a subject" the same set.
    """
    label = (name or "").strip()
    if not label or not _MONTH_DAY_RE.match(label):
        return None
    return label


def deadline_level_label(
    leader_name: str | None,
    *,
    leader_is_ladder_rung: bool = False,
    deadline_preposition: str | None,
) -> str | None:
    """The dated label a level clause may be built on, or ``None``.

    THE GATE, lifted out of :func:`leader_deadline_clause` so there is exactly
    one of it. Two callers now need the same permission and they need it at
    different points in the pipeline: the field templates want the finished
    sentence, and `compose_binary_card_copy` wants only the LABEL, because it
    already holds the percent it must print (see its own note). Restating these
    three conditions beside the composer would have been a second gate, and the
    whole safety argument of #6470 is that there is one.
    """
    if leader_is_ladder_rung:
        return None
    if deadline_preposition != DEADLINE_PREPOSITION:
        return None
    return _date_outcome_label(leader_name)


def leader_deadline_clause(
    leader_name: str | None,
    pct: int | None,
    *,
    deadline_preposition: str | None,
) -> str:
    """`60% chance by December 31, 2026` — the LEVEL of a dated leg, or "".

    #6470. Six of the sixty cards on production page one (2026-09-15) arrived
    with no caption at all — `reason`, `headline`, `card_sum_reason` and
    `hook_description` all empty, so both clients' `firstMeaningful([...])` chain
    had nothing to print. Every one was a Polymarket deadline board whose leading
    leg is a bare date, and every one died at :func:`_weak_outcome_label`: the
    label "December 31" cannot be the SUBJECT of a sentence, because standing
    alone it does not say whether the market means *by* that date or *during* it.

    🔴 THE REFUSAL IT REPLACES WAS CORRECT AND IS UNCHANGED. #4640 is right that
    "December 31 leads at 27%" is a false claim, and nothing here reopens it.
    This clause is a LEVEL, not a comparative: it names one leg's own price and
    asserts nothing about any other leg, so it is true whatever the rest of the
    board is doing — which matters, because these boards are not all coherent.
    Alito's rungs (measured the same morning: Sep 30 · Dec 31 · Feb 28 · Mar 31 ·
    Jun 30 2027 · Jul 15, priced 0.6% · 5.5% · 0.6% · 0.2% · 31.5% · 0.1%) are
    NOT monotonic in the date under any year assignment, so a sentence ranking
    them would be printing a broken board as news. "31.5% chance by June 30,
    2027" restates the row the card already draws and stays true regardless.

    THE MISSING WORD COMES FROM THE VENUE, NEVER FROM THE LABEL.
    ``deadline_preposition`` is :func:`market_display_name.elided_trailing_preposition`
    — the word the display rule DELETED from the title. Polymarket publishes the
    group template as the market name ("Anthropic IPO by __?") and its members
    fill the slot, so that "by" is the venue's own statement that the legs are
    deadlines. #3513 strips it to stop the card asking a holed question, which
    left the reader with "Anthropic IPO?" and no deadline anywhere on the card;
    this puts the word back where it is true — bound to the date it governs.
    Where the title never carried it, we cannot know the leg is a bound, and the
    caption stays empty exactly as today.
    """
    if pct is None:
        return ""
    label = deadline_level_label(
        leader_name, deadline_preposition=deadline_preposition
    )
    if label is None:
        return ""
    return f"{pct}% chance {DEADLINE_PREPOSITION} {label}"


def _deadline_fallback(
    leader_name: str | None,
    leader_probability: Optional[float],
    rendered_leader_percent: Optional[int],
    *,
    leader_is_ladder_rung: bool,
    leader_deadline_preposition: str | None,
) -> str:
    """The level clause a generator prints INSTEAD of falling silent, or "".

    One composition point for all three generators, for the reason
    :func:`leader_standing_clause` is one: the headline, the reason and the
    context summary are near-copies maintained by hand, and three chances to
    widen this gate is three chances to print a deadline the venue never
    asserted.

    ``leader_is_ladder_rung`` still wins. A proven cumulative ladder (#4640) is
    refused here as well as above — its rungs nest, so the loosest is dearest by
    arithmetic and a level clause would hand the reader the same non-contest with
    a preposition in front of it.
    """
    if leader_is_ladder_rung or leader_probability is None:
        return ""
    return leader_deadline_clause(
        leader_name,
        _display_pct(leader_probability, rendered_leader_percent),
        deadline_preposition=leader_deadline_preposition,
    )


def _leader_is_unnameable(name: str | None, is_ladder_rung: bool) -> bool:
    """Should this leader label be replaced by the market's own title?

    Two independent reasons, unioned here so every template asks one question.

    `_weak_outcome_label` is about the LABEL: "Above 5K" alone tells the reader
    nothing, so the sentence borrows the market title for context.

    `is_ladder_rung` (#4640) is about the SET the label came from. On a
    cumulative ladder every rung is a strict subset of every looser one, so the
    highest-priced rung is the loosest one by arithmetic — "Above 116 (69%)"
    outprices "Above 120 (45%)" for the same reason "heads or tails" outprices
    "heads". Naming it a *favorite* claims a contest that does not exist: there
    is nothing for the rungs to be winning. The label may be perfectly specific
    and the price perfectly coherent and the sentence is still a category error,
    which is why this cannot be a spelling test on the label.

    Deliberately NOT a wider `_weak_outcome_label`: band sets ("29,900 to
    29,999.99", "Exactly 3.64%") are mutually exclusive, so their favorite is
    real and their lead changes are real news. The two populations are separated
    by `cumulative_outcome_ladder`, on the outcome SET — see
    `routes/feed.py::_leader_is_ladder_rung`.
    """
    return is_ladder_rung or _weak_outcome_label(name)


def _short_market_name(market_name: str | None, max_len: int = 58) -> str:
    """Shorten a market title for use as the SUBJECT of a composed sentence.

    #4056 — the cut lands on a word boundary, never inside a token. It used to be
    `name[: max_len - 3]`, a bare character count, and two of the forty cards served
    on 2026-09-09 cut immediately after a digit:

        "Canadian Team to Win the Stanley Cup® Before the 2030-3...: 42% chance"
        "Will Utah Mammoth advance to the Second Round of the 20...: 49% chance"

    The market is *Before the 2030-31 Season*. The string says **2030-3**. That is not
    a formatting blemish — the card states a value the market does not, which is a
    truth defect, and `humanize_binary_outcome_name` already refuses to chop rather
    than emit a cut-down label (`_MAX_LABEL_CHARS`, #3491). This is the weaker version
    of that same rule: shorter and vague beats shorter and false.

    Cutting on whole words covers the mid-number case and the plain mid-word case with
    one rule, so there is no separate digit predicate to keep in step with a date
    format nobody has seen yet.
    """
    name = (market_name or "").strip()
    name = re.sub(r"\s*\?\s*$", "", name)
    if len(name) <= max_len:
        return name
    window = name[: max_len - 3]
    cut = window.rstrip()
    # Back up to the last whole word, unless the very first word already overruns
    # the window — then there is no boundary to find and a hard cut is all there is.
    if not name[len(window) : len(window) + 1].isspace():
        boundary = window.rfind(" ")
        if boundary > 0:
            cut = window[:boundary].rstrip()
        else:
            # A single token wider than the window. Cut it, but never leave a
            # truncated number behind: drop the trailing partial digit run.
            cut = re.sub(r"\d+$", "", cut).rstrip()
    return (cut or window.rstrip()) + "..."


# ── Yes/No outcome humanization (BR49) ──────────────────────────────

# Subjects too vague to use as a standalone label
_GENERIC_SUBJECTS = {"there", "it", "the", "a", "an", "this", "that", "any"}

# Strip these suffixes when building a short label from the full market name
_TRAILING_NOISE_RE = re.compile(
    r"\s*\b(?:before|by|in|during|after|on)\b\s+\d{4}.*$",
    re.IGNORECASE,
)
# Remove trailing question mark
_TRAILING_QM_RE = re.compile(r"\s*\?\s*$")

# The widest label a feed card can show without wrapping past its hero. A
# manufactured label that needs more room than this is refused outright (#3491),
# never cut down to fit — see `humanize_binary_outcome_name` Strategy 2.
_MAX_LABEL_CHARS = 40


def humanize_binary_outcome_name(
    outcome_name: str,
    market_name: str | None,
) -> str:
    """Replace generic 'Yes'/'No' outcome names with a meaningful label.

    Kalshi binary markets have outcomes literally named 'Yes' and 'No'.
    For questions like 'Will Anthropic IPO first?', showing '69% Yes' is
    meaningless — the user needs to see 'Anthropic' or at least the gist
    of the question.

    Rules:
    1. If outcome_name is not 'Yes' or 'No', return it unchanged.
    2. Try to extract the subject from 'Will <subject> <verb> ...?' patterns.
    3. Fall back to a shortened version of the market name (strip year
       suffixes and question marks) so the card still reads naturally.
    4. If that fallback does not fit in `_MAX_LABEL_CHARS` for BOTH sides of
       the pair, return the bare side word instead of cutting it down — a
       label that has to be chopped is the question echoed back, and the card
       already prints the question directly below it (#3491).

    Only used for feed card display — never mutates the underlying data.
    """
    # #4151 — a venue slug is not "Yes"/"No", so it used to fall straight
    # through this function and be SPOKEN in the sentence: `claude-fable-5.1-max
    # leads at 68%`. Resolved here rather than at the call site because the
    # sentence and the outcome ROW are humanized on two separate paths, and if
    # only one of them learned the display name the card would state a name it
    # does not print one line below — the #4146 defect, rebuilt.
    if outcome_name:
        displayed = display_outcome_name(outcome_name, market_name)
        if displayed != outcome_name:
            return displayed

    if not outcome_name or outcome_name.strip().lower() not in {"yes", "no"}:
        return outcome_name

    if not market_name:
        return outcome_name

    is_yes = outcome_name.strip().lower() == "yes"

    # --- Strategy 1: Extract subject from "Will <subject> <verb>...?" ---
    m = re.match(
        r"^Will\s+(.+?)\s+"
        r"(?:IPO|be |win |reach |hit |make |get |have |lose |beat |sign |step |"
        r"qualify|advance|clinch|resign|announce|release|launch|drop|pass|"
        r"exceed|fall |go |become |receive |host |return |default|remain |stay )",
        market_name,
        re.IGNORECASE,
    )
    if m:
        subject = m.group(1).strip()
        # Skip overly generic subjects
        first_word = subject.split()[0].lower() if subject else ""
        if first_word not in _GENERIC_SUBJECTS and len(subject) <= 40:
            if not is_yes:
                return f"Not {subject}"
            return subject

    # --- Strategy 2: Shorten the market name into a label ---
    label = _TRAILING_QM_RE.sub("", market_name)
    label = _TRAILING_NOISE_RE.sub("", label)
    # Strip leading "Will " for brevity
    label = re.sub(r"^Will\s+", "", label, flags=re.IGNORECASE).strip()

    # #3517 — LENGTH WAS A PROXY FOR REDUNDANCY, AND THIS IS WHERE THE TWO COME
    # APART. #3491 (below) refuses a label that does not FIT, on the reasoning
    # that a chopped label is the question echoed back. A label that fits is
    # echoed back just the same; it is only shorter. Found on the live feed
    # 2026-09-08 20:25Z, `GET /api/feed?limit=30`, two cards on page one:
    #
    #   'China x Philippines military clash moved up 37.5 points from opening
    #    in China x Philippines military clash before 2027?'
    #   'China invade Taiwan by end of 2026 (4%) leads
    #    Will China invade Taiwan by end of 2026?'
    #
    # The same words twice in one sentence, and the same words again as the
    # hero above the title. Neither label is chopped: 33 and 34 characters.
    #
    # 🔴 THIS TEST IS TRUE FOR EVERY LABEL STRATEGY 2 CAN BUILD, and that is not
    # a reason to drop it for a bare `return`. Strategy 2 constructs its label by
    # DELETING A SUFFIX from the question — a trailing `?`, a date clause, a
    # leading auxiliary — so its output is always a prefix of what the card
    # prints directly below it, and the branch has no way to add information.
    # Stating the property instead of assuming it means that if the label
    # construction ever grows a step that genuinely rewrites the question rather
    # than trimming it, that label ships, and this file does not have to be
    # re-derived to find out why it may.
    #
    # The gate stays PAIR-WIDE for the reason #3491 gives below: `label` is the
    # single string both sides are built from, so both sides collapse together
    # and `("No", "Yes")` stays the canonical pair the web hero recognises.
    if _restates_market_question(label, market_name):
        return "Yes" if is_yes else "No"

    neg_label = f"Not: {label}"

    # #3491 — A LABEL THAT DOES NOT FIT IS NOT A LABEL, IT IS THE QUESTION
    # ECHOED BACK. Strategy 2 used to force a fit by cutting at 40 characters,
    # but the card prints `data.name` DIRECTLY BELOW this label, so the cut
    # string was never a summary of the question — it was the question again,
    # chopped mid-word, one line above itself:
    #
    #   40%
    #   Canadian Team to Win the Stanley Cup®...     <- this label
    #   Canadian Team to Win the Stanley Cup® Before the 2030-31 Season
    #
    # Measured on production 2026-09-06 over every 11th open `container_member`
    # market (n=977): the Yes label was a chopped echo for 41.1% of them and the
    # No label for 48.2%. Strategy 1's extractions are untouched — `Will
    # Anthropic IPO first?` still labels its sides `Anthropic` / `Not Anthropic`.
    #
    # This extends UX-P239's ruling to its affirmative mirror. That ruling
    # (see `_negates_market_question` below) already holds that once a label
    # merely restates the question, "the bare side word is the ONLY honest
    # subject" — and `_answering_side_label` already prints exactly that in the
    # copy. It was never applied to the outcome NAMES, which is the string the
    # card hero renders, so `context_summary` read `No leads at 75%` while the
    # hero above it still read `No: SpaceX (SPCX) finish week of Sept...`.
    #
    # 🔴 THE TEST IS PAIR-WIDE, NOT PER-SIDE, and a per-side cap would be wrong
    # in two ways. Both are about the two sides being rendered ADJACENTLY:
    #   1. Labelling one side as a phrase and the other as a bare word is
    #      incoherent in the outcome rows — `the Boston Red Sox win 100 or more`
    #      sitting above `No`.
    #   2. `frontend/lib/discover/heroOutcome.ts` (UX-P238) flips a card's hero
    #      off a No-side leader only when it can see the pair as a negation. It
    #      recognises the canonical `("No", "Yes")` pair explicitly, and
    #      otherwise needs its `NEGATION_PREFIX` to match — a regex whose
    #      trailing `\s+` is load-bearing ("Norway", "No. 1 seed") and which a
    #      BARE "No" therefore cannot match. Collapsing one side only would
    #      strand `("No", "<38-char affirmative>")`: not canonical, not
    #      prefix-matchable, so the hero would silently stop flipping and the
    #      card would print the negation of its own question as its headline —
    #      the exact defect UX-P238 exists to prevent. 11.0% of Strategy-2
    #      markets sit in that 36-40 char band, so this is not hypothetical.
    # Gating both sides on the LONGER of the two keeps the pair canonical.
    if len(neg_label) > _MAX_LABEL_CHARS:
        return "Yes" if is_yes else "No"

    if not is_yes:
        # Preserve side semantics. Returning the bare topic makes "No" cards
        # read like the positive side for binary markets such as Top 5/Top 10.
        return neg_label

    return label


def humanize_outcome_names_for_feed(
    top_outcomes: list[dict],
    market_name: str | None,
) -> list[dict]:
    """Post-process a list of outcome dicts, humanizing Yes/No names.

    Returns a NEW list (does not mutate the input). Only applies
    humanization when ALL outcomes are Yes/No (i.e., a true binary market).
    Multi-outcome markets with named choices are left untouched.

    #4151 — EXCEPT that "a named choice" was doing a lot of work in that last
    sentence. A field market whose names are venue slugs reaches the early
    return below and its rows print `claude-fable-5.1-max`, so venue slugs are
    resolved FIRST, before the all-binary test that would otherwise skip them.
    """
    if not top_outcomes:
        return top_outcomes

    # #4151 — before the binary gate: a slug market is by definition not binary.
    top_outcomes = display_outcome_names(top_outcomes, market_name)

    # Only humanize if every outcome is Yes or No
    all_binary = all(
        (o.get("name") or "").strip().lower() in {"yes", "no"} for o in top_outcomes
    )
    if not all_binary:
        return top_outcomes

    return [
        {**o, "name": humanize_binary_outcome_name(o["name"], market_name)}
        for o in top_outcomes
    ]


def _point_change(value: float) -> float:
    """Convert a probability delta to percentage points for display."""
    return round(abs(value) * 100, 1)


def _is_printable_move(value: Optional[float]) -> bool:
    """#6952 — a delta that prints as `0 points` is not a move, and never leads.

    Every dated-move rung below gated on `is not None`, which is a question
    about whether we HAVE a number, not about whether anything happened. Two
    2027 Stanley Cup cards on production 2026-09-18 read

        Down 0 points since Sep 18 — now 41% chance

    and the row behind them has `current_probability == opening_probability`
    exactly (0.415000 / 0.415000, `opening_captured_at` 11:29Z, 81 minutes
    before the shot) — not a rounding artifact, a market that opened this
    morning and has not traded. Three wrong claims came out of one missing
    guard: a move that did not happen, a direction ("Down" is simply the `else`
    of `> 0`, so a zero always falls DOWN), and a "since" measured against
    today.

    Refusing the rung is the whole fix: the rows fall through to #4056's empty
    caption, which is what a card with nothing to say is supposed to render.
    The test is what the reader would SEE — `_point_change`'s rounded value, so
    a real 0.1-point move still prints — not a new interestingness threshold.

    ⚠️ SCOPED TO THE FOUR DATED-`since` RUNGS, DELIBERATELY. The five
    `*_movement_24h` rungs print the same false sentence from the same shape,
    but two of them (`generate_futures_reason`'s major/moderate pair) answer a
    failed inner test with a VAGUER claim — "Big odds movement in X" — so
    guarding the inner test there would trade a false number for a false
    sentence with no number in it. Those rungs are also gated by a scorer
    threshold rather than by presence, and the measurement found no specimen:
    scanning `reason`, `headline` and `context_summary` across
    `/api/feed?limit=100` on 2026-09-18, all three `0 points` hits are `since`
    rungs and none is a `today` rung. Fixing those properly means falling the
    whole branch through, which is its own ship.
    """
    return value is not None and _point_change(value) != 0


def _underdog_sentence(winner: str, pct: int) -> str:
    """"{winner} won as a {pct}% underdog", with the article the number takes.

    The article follows how the percent is SAID, not how it is spelled: "a 44%"
    but "an 18%". Eight, eleven and eighteen are the three readings that open on
    a vowel, and every hundred built on them inherits it ("an 81%"), so the test
    is the leading digits rather than the value.

    Split out of the one f-string that prints this sentence because #6477 gives
    that sentence a second caller, and its specimen — Valencia at a printed 18 —
    is exactly a case the old literal got wrong.
    """
    article = "an" if str(int(pct)).startswith(("8", "11", "18")) else "a"
    return f"{winner} won as {article} {pct}% underdog"


def _display_pct(probability: float, printed: Optional[int] = None) -> int:
    """The whole percent a SENTENCE states about `probability`. (#4146)

    ``printed`` is the percent the card's own row shows, when the caller has it.
    That is the number the sentence has to state, because it is the number the
    reader can see three millimetres away — and on a complement pair it is
    DERIVED (`100 - leader`, #2060's rule) rather than rounded from this
    probability at all, so no rounding of the raw value can reproduce it.

    Without a printed percent, fall back to `rendered_percent`: the shared
    implementation of this decision (ruling 021), driven through
    `contracts/rendered_percent.json` in all three runtimes. **Never `round()`**
    — Python's built-in is banker's rounding, so `round(70.5)` is 70 while the
    card, web and native all print 71. Eleven of forty-five cards on production
    Discover stated a percent their own card did not print, every one of them on
    a .5 boundary, because this module derived its own.
    """
    if printed is not None:
        return int(printed)
    # `or 0` would be wrong here: 0% is a real percent and None is "no price",
    # and the two must not collapse (the contract's first row says so).
    value = rendered_percent(probability)
    return 0 if value is None else value


def _normalized_copy_tokens(text: str | None) -> list[str]:
    return re.findall(r"[a-z0-9]+", (text or "").lower())


def _copy_repeats_market_name(copy: str | None, market_name: str | None) -> bool:
    copy_tokens = _normalized_copy_tokens(copy)
    name_tokens = _normalized_copy_tokens(market_name)
    if not copy_tokens or not name_tokens:
        return False
    prefix_len = min(len(name_tokens), 8)
    return copy_tokens[:prefix_len] == name_tokens[:prefix_len]


# ── The negation label never becomes the subject of "leads at" (UX-P239) ──────
#
# `humanize_binary_outcome_name` above MANUFACTURES the No-side label by
# restating the market's own question behind a negation marker, and truncating
# it to 40 characters. Fed back into this module's copy templates as
# `leader_name`, that produces a sentence whose grammatical subject is a
# truncated double negative, and readers take the percentage as the answer to
# the question rather than to its negation. Measured on the live feed
# 2026-08-31 21:5xZ, `GET /api/feed?limit=60`, both of the two-outcome futures
# cards that were leading on the No side:
#
#   59934328  Will "Onslaught" score at least 80 on the Tomatometer?  (Yes 26%)
#             context_summary: 'No: "Onslaught" score at least 80 on ... leads at 74%'
#   57792416  Will Neuralink's valuation hit (HIGH) $47.5B by Aug 31? (Yes 27.5%)
#             context_summary: 'Not Neuralink's valuation leads at 72%'
#
# The precedent is already in the tree: `routes/feed.py` carries a note
# preferring "Anthropic leads at 69%" over "Yes leads at 69%" — a bare side word
# is a poor subject. This is the mirror case, and it resolves the other way: once
# the label is a negation of the question, the bare side word is the ONLY honest
# subject, because every longer form restates the question it is negating.
#
# 🔴 THE RULE IS PAIR-RELATIVE, and a bare prefix regex would be wrong. The Fed's
# real outcome row is "No change", which `/^no\b/` matches. Requiring the text
# after the marker to RESTATE THE MARKET NAME is what keeps "No change" — whose
# question is about a rate decision, not about "change" — from being rewritten.
# The restatement test is the guard; the prefix alone is not. This mirrors
# `frontend/lib/discover/heroOutcome.ts`, which makes the same distinction
# against the SIBLING outcome; here the question itself is the counterpart,
# because that is what the label was manufactured from.

_NEGATION_PREFIX_RE = re.compile(r"^\s*(?:no|not)\s*[:\-–—]?\s+", re.IGNORECASE)

# Below this many characters a restatement is too short to be evidence of one.
_MIN_RESTATEMENT_CHARS = 4

# Stripped before comparing a restatement against the question it restates.
#
# 🔴 CERT-624: THIS CAME OFF THE QUESTION ONLY, AND THAT WAS THE BUG.
# `humanize_binary_outcome_name`'s Strategy 2 removes a leading "Will " and
# nothing else, so a question opening with any OTHER auxiliary keeps it in the
# manufactured label: `"Does Alcaraz reach the semifinals?"` becomes
# `"Not: Does Alcaraz reach the semifinals"`. Stripping the word from one side
# of an equality then GUARANTEES the two token lists cannot align, so the
# predicate returned False and the label reached the reader whole —
# `Not: Does Alcaraz reach the semifinals leads at 72%`. That title is checked
# in at `scripts/populate_tournament_props.py:468`; every positive specimen in
# the guard happened to open with "Will", which is why the suite stayed green.
# The word must come off BOTH sides or NEITHER.
_LEADING_INTERROGATIVE_RE = re.compile(
    r"^(?:will|would|does|do|did|is|are|was|were|can|could|should|has|have|had)\b",
    re.IGNORECASE,
)

# `humanize_binary_outcome_name` marks a label it had to shorten by ending it
# with this; see `_negates_market_question` for why that matters.
_TRUNCATION_MARKER = "..."


def _comparable_tokens(text: str | None) -> list[str]:
    """Tokens of `text` with a leading interrogative auxiliary dropped.

    Applied to the label and the question through the SAME function, so the two
    sides cannot be normalised differently again.
    """
    stripped = (text or "").strip()
    tokens = _normalized_copy_tokens(stripped)
    if tokens and _LEADING_INTERROGATIVE_RE.match(stripped):
        return tokens[1:]
    return tokens


def _negates_market_question(label: str | None, market_name: str | None) -> bool:
    """True when `label` reads as an explicit negation of the market's question."""
    text = (label or "").strip()
    if not text or not (market_name or "").strip():
        return False

    marker = _NEGATION_PREFIX_RE.match(text)
    if not marker:
        return False

    restatement = text[marker.end() :].strip()
    if len(restatement) < _MIN_RESTATEMENT_CHARS:
        return False

    restatement_tokens = _comparable_tokens(restatement)
    question_tokens = _comparable_tokens(market_name)
    if not restatement_tokens or not question_tokens:
        return False

    # Only the LABEL is ever shortened; the question arrives whole. Compare over
    # the overlap, so a label carrying fewer tokens than its question still
    # counts as restating it.
    overlap = min(len(restatement_tokens), len(question_tokens))

    # The 40-character cut lands mid-WORD, not on a token boundary, so a label
    # ending in the marker has an unreliable FINAL token — "September" arrives
    # as "septe". Everything before it must still match exactly; only that last
    # token is allowed to merely OPEN the word it was cut from.
    if restatement.endswith(_TRUNCATION_MARKER):
        head = overlap - 1
        if restatement_tokens[:head] != question_tokens[:head]:
            return False
        return question_tokens[head].startswith(restatement_tokens[head])

    return restatement_tokens[:overlap] == question_tokens[:overlap]


def _restates_market_question(label: str | None, market_name: str | None) -> bool:
    """True when `label` says only what the market's own question already says.

    The affirmative mirror of `_negates_market_question`: no negation marker to
    strip, the same token comparison over the same normalisation, so the two
    predicates cannot drift apart on how a question is read.

    🔴 SCOPED TO MANUFACTURED LABELS BY ITS CALLER, NOT BY ITSELF. A genuine
    Strategy 1 extraction is also a prefix of its question — `Anthropic` of
    `Will Anthropic IPO first?` — and must survive, because it keeps the
    question's PREDICATE out of the label and so still says something the title
    beneath it does not. Strategy 1 returns before this is reached; calling this
    on its output would collapse every one of them.
    """
    label_tokens = _comparable_tokens(label)
    question_tokens = _comparable_tokens(market_name)
    if not label_tokens or not question_tokens:
        return False

    # Only the LABEL is ever shortened; the question arrives whole.
    overlap = min(len(label_tokens), len(question_tokens))
    return label_tokens[:overlap] == question_tokens[:overlap]


def _answering_side_label(label: str | None, market_name: str | None) -> str | None:
    """Collapse a negation-of-the-question label to the bare side word it means.

    Every other label is returned untouched — this never rewrites a real
    outcome name, only the restatement this module manufactured.
    """
    if _negates_market_question(label, market_name):
        return "No"
    return label


# ── A MOVEMENT REASON NAMES THE DAY IT IS MEASURED FROM (D1 clause a, #4066) ──
#
# "moved up 37.5 points from opening" was item 10 of the twenty served on
# production 2026-09-08 21:07Z. It is accurate and it is not news: opening may be
# this morning or it may be eleven months ago, and the sentence does not say
# which, so a reader takes it for today's move. The rule from the D1 brief is
# that a movement claim carries a baseline the reader can place on a calendar,
# and that a lifetime move is CONTEXT — dated, and never the line a card leads
# with when something more recent exists.
#
# `futures_outcomes.opening_captured_at` is that date and is already on the row
# the feed has loaded: 93,037 of the 106,976 top-5 outcomes of open markets carry
# it (87%, measured on production 2026-09-08). The 13% that do not get no
# movement sentence at all rather than an undated one.

_MONTH_ABBR = (
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
)


#: How old a lifetime baseline may be and still read as the card's NEWS.
#:
#: D1 clause (a), #4066, verbatim: "'From opening' becomes context and always
#: carries its date; it is never the headline reason." The dated-and-demoted
#: branch below already runs after every time-anchored signal, so a card only
#: reaches it when nothing has happened lately — and then it led its caption
#: with the move anyway, because the move was the only sentence it had.
#:
#: Seven days is the horizon the module already uses for "soon" elsewhere
#: (`resolving_soon_7d`), so a move is news for exactly as long as a resolution
#: is imminent. Measured on the served page 2026-09-16: of the eight dated
#: baselines in `/api/feed?limit=60`, seven were older than 30 days and five
#: cited one day, Feb 19 — a bulk capture date, i.e. when we first saw the
#: outcome, not a day anything happened to it. The two at the very top of page
#: one read "Down 22.5 points since Feb 3" and "Down 7.7 points since Feb 19".
_LIFETIME_MOVE_NEWS_HORIZON_DAYS = 7


def _baseline_is_older_than_news(
    when: Optional[datetime],
    now: Optional[datetime] = None,
) -> bool:
    """Is this baseline too old for its move to be stated as today's news?

    Same naive-is-UTC reading as :func:`format_baseline_date`, and deliberately
    a separate function from it: that one answers "what day is this" and is
    used by branches that are already anchored to a recent instant, while this
    answers "may the caption LEAD with it". A baseline we cannot date at all is
    not old — it is unsayable, and the caller drops the clause entirely.
    """
    if when is None:
        return False
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    reference = now or datetime.now(timezone.utc)
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=timezone.utc)
    return (reference - when).days > _LIFETIME_MOVE_NEWS_HORIZON_DAYS


def format_baseline_date(
    when: Optional[datetime],
    now: Optional[datetime] = None,
) -> Optional[str]:
    """Render a baseline instant as a date, or None when there is no instant.

    "Sep 4" inside the current calendar year, "Sep 4, 2025" outside it — the
    year is what stops a reader reading an eleven-month-old baseline as this
    week's. Naive datetimes are read as UTC, which is how every writer in
    `tasks/` stores them.
    """
    if when is None:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    reference = now or datetime.now(timezone.utc)
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=timezone.utc)
    label = f"{_MONTH_ABBR[when.month - 1]} {when.day}"
    if when.year != reference.year:
        return f"{label}, {when.year}"
    return label


# ── A YES/NO QUESTION IS NOT A RACE (D1 clause b, #4066) ─────────────────────
#
# Items 8 and 10 of the same twenty, verbatim:
#
#   'China invade Taiwan by end of 2026 (4%) leads Will China invade Taiwan by
#    end of 2026?'
#   'China x Philippines military clash moved up 37.5 points from opening in
#    China x Philippines military clash before 2027?'
#
# Both markets serve exactly ONE outcome (`outcome_count: 1`), named for the
# question with its interrogative stripped. Fed to the field templates below,
# the single entrant is announced as leading a race against itself. Nothing
# leads when there is nothing to lead, and the reader is told a percentage
# without being told what it is the percentage OF.
#
# The affirmative probability IS the answer to the question, so a binary card
# states it and never uses the verb "leads".
#
# 🔴 THE RESOLUTION CONDITION IS DELIBERATELY NOT REPEATED IN THIS COPY. The
# card already prints its own "Resolves <date>" chip
# (`frontend/components/discover/utils.ts` -> `formatResolvesLabel`), and that
# chip renders the instant in the READER's timezone while this module would
# render it in UTC. `Will China invade Taiwan by end of 2026?` carries
# `resolution_date` 2026-12-31T00:00Z and its chip reads "Resolves Dec 30,
# 2026", so a second date emitted here would sit beside the first and disagree
# with it. The question, the probability and the deadline all reach the reader;
# they reach it from the two places that each own one.


class BinaryCardCopy(NamedTuple):
    """The three display strings for a yes/no card, composed together.

    One composer rather than three parallel ladders: the headline, the reason
    and the context summary have to agree about which signal the card is here
    for, and they drifted apart the last three times they were written
    separately.
    """

    reason: str
    headline: str
    context_summary: str


def binary_affirmative_outcome(outcomes: list[dict]) -> Optional[dict]:
    """The AFFIRMATIVE outcome dict when these outcomes are a yes/no question.

    Returns None for a genuine field — every market for which the "leads"
    templates are the right ones. Two shapes count as a yes/no question:

    * ONE outcome: the market carries only the affirmative side, so its
      probability is the answer to the question (both live specimens above).
    * TWO outcomes literally named Yes and No: the affirmative is the "Yes"
      row, whichever of the pair happens to be ahead.

    Takes the RAW outcome dicts, i.e. before `humanize_binary_outcome_name`
    rewrites a bare "Yes" into a restatement of the question — after that
    rewrite the pair is no longer recognisable as yes/no.

    #4758 — the ROW, not just its probability. `compose_binary_card_copy`
    composes every one of its sentences against the affirmative side, so a
    caller that needs a second fact about that side (its opening price, its
    move) must be able to reach the same row this function already identifies,
    rather than re-deriving "which one is the affirmative" beside it and
    drifting.
    """
    usable = [
        outcome
        for outcome in (outcomes or [])
        if isinstance(outcome, dict) and outcome.get("probability") is not None
    ]
    if len(usable) == 1 and len(outcomes or []) == 1:
        return usable[0]
    if len(usable) == 2:
        by_side = {
            (outcome.get("name") or "").strip().lower(): outcome for outcome in usable
        }
        if set(by_side) == {"yes", "no"}:
            return by_side["yes"]
    return None


def binary_affirmative_probability(outcomes: list[dict]) -> Optional[float]:
    """The AFFIRMATIVE probability when these outcomes are a yes/no question.

    The probability half of `binary_affirmative_outcome`; see it for which
    shapes count as a yes/no question and why the raw names are what it reads.
    """
    affirmative = binary_affirmative_outcome(outcomes)
    if affirmative is None:
        return None
    return float(affirmative["probability"])


def _points(value: float) -> str:
    """ "37.5 points" / "1 point" — never "1.0 points"."""
    magnitude = _point_change(value)
    if magnitude == int(magnitude):
        magnitude = int(magnitude)
    return f"{magnitude} point{'' if magnitude == 1 else 's'}"


def compose_binary_card_copy(
    *,
    market_name: Optional[str],
    highlight_reasons: list[str],
    affirmative_probability: float,
    rendered_affirmative_percent: Optional[int] = None,
    top_mover_change: Optional[float] = None,
    top_surprise_change: Optional[float] = None,
    top_surprise_opened_at: Optional[datetime] = None,
    deadline_label: Optional[str] = None,
    now: Optional[datetime] = None,
) -> BinaryCardCopy:
    """Compose a yes/no card's three strings, freshest real signal first.

    The order below IS the editorial rule: what moved, then what is about to
    resolve, then — only if nothing else is true — a dated lifetime move, then
    the deadline this leg is a bound on, then nothing. A lifetime move never
    outranks a live one and never appears undated.

    ``deadline_label`` is :func:`deadline_level_label`'s verdict — the bare date
    this single leg is a bound on, or None. Defaults to None so a caller that
    does not know stays byte-identical, which is every caller of a genuine
    Yes/No pair.
    """
    reasons = set(highlight_reasons or [])
    if "stale_past_resolution" in reasons:
        return BinaryCardCopy("", "", "")

    pct = _display_pct(affirmative_probability, rendered_affirmative_percent)
    answer = f"{pct}% chance"
    title = _short_market_name(market_name) if market_name else ""

    def composed(headline: str, context: str) -> BinaryCardCopy:
        reason = f"{title}: {context}" if title else context
        return BinaryCardCopy(reason, headline, context)

    moved_today = (
        "major_movement_24h" in reasons or "moderate_movement_24h" in reasons
    ) and top_mover_change is not None
    if moved_today:
        direction = "Up" if top_mover_change > 0 else "Down"
        return composed(
            f"{direction} {_points(top_mover_change)} today",
            f"{direction} {_points(top_mover_change)} today — now {answer}",
        )

    if "resolving_soon_7d" in reasons:
        return composed(
            RESOLVING_WITHIN_WEEK_HEADLINE, f"{answer}, resolving within a week"
        )
    if "resolving_soon_30d" in reasons:
        return composed(
            RESOLVING_WITHIN_MONTH_HEADLINE, f"{answer}, resolves within a month"
        )

    since = format_baseline_date(top_surprise_opened_at, now=now)
    if since and _is_printable_move(top_surprise_change):
        direction = "Up" if top_surprise_change > 0 else "Down"
        move = f"{direction} {_points(top_surprise_change)} since {since}"
        # D1 clause (a), #4066: a move measured from seven months ago is not why
        # the card is here this morning. Past the news horizon the caption stops
        # ASSERTING the move and states the standing answer first, keeping the
        # move — still dated, never dropped — behind it as context. Inside the
        # horizon nothing changes: "Down 5 points since Sep 10 — now 58% chance"
        # is a sentence about this week and leads exactly as it did.
        #
        # 🔴 THE HEADLINE IS BYTE-IDENTICAL IN BOTH ARMS, AND THAT IS LOAD-BEARING,
        # not a stylistic choice. `routes/feed.py` feeds the headline to
        # `explanation_score_rank`, where `has_specific_explanation` decides
        # between the card's raw score and a 93/80/60 cap — so a headline that
        # changed here would move the card's ORDER as well as its words. The
        # reader-visible string on a binary card is the CONTEXT slot (measured
        # on production 2026-09-16: the Taiwan card renders "Down 7.7 points
        # since Feb 19 — now 4% chance" and nothing else), so reordering the
        # context alone is the whole ship and the ranking input never moves.
        if _baseline_is_older_than_news(top_surprise_opened_at, now=now):
            context = f"{answer}, {move[0].lower()}{move[1:]}"
        else:
            context = f"{move} — now {answer}"
        return composed(move, context)

    # #4056 — nothing about the world is true of this market right now: it has not
    # moved, it is not resolving, and it has no dated lifetime move. The rung that
    # used to sit here was `composed(answer, answer)`, which put "42% chance" in the
    # headline and the context, and "<title>: 42% chance" in the reason — the card's
    # own number restated as prose, directly beneath a hero already printing it in
    # 48pt, above a title already asking the question.
    #
    # Standing notice 34: a reader sees the number and at most one short caption, and
    # "if a number cannot be shown honestly, leave the space empty". A bare "42%
    # chance" above a 42% hero IS the empty case, wearing text.
    #
    # Empty is a supported state on both clients and needs no client change (measured
    # 2026-09-09): web's `feedContextSnippet` returns "" and all three render sites in
    # `FuturesCard.tsx` are `{contextSnippet && (…)}`; iOS's `contextText` returns nil
    # and the row is `if let contextText { … }` inside a VStack, which emits no spacing
    # for an absent child. The precedent is fourteen lines up — `stale_past_resolution`
    # returns this exact value.
    #
    # This does NOT blank the headline outright: `routes/feed.py` composes it as
    # `generate_futures_headline(...) or highlight_result.primary_reason`, so the card
    # falls through to a curated signal label (`PRIMARY_REASON_LABELS`) and says
    # nothing only when there is no signal to name either. That is the design's own
    # honest terminal, not a new one.
    #
    # 🟢 #6470 REMAINDER — EXCEPT WHEN THE BOARD COLLAPSED TO ONE DATED RUNG, where
    # something about the world IS true and sayable. #6470 gave every deadline board
    # a level clause, but only on the FIELD path: a Polymarket deadline board whose
    # sibling rungs have all expired arrives here with exactly ONE outcome, which
    # `binary_affirmative_outcome` reads as a yes/no question, so the generators
    # short-circuit into this composer above the level clause and the sentence is
    # never consulted. Measured on production 2026-09-16 (v4612 `154be569`), three of
    # #6470's own six cards were still blank for this reason and no other — 113013
    # `NATO x Russia military clash by...?`, 113016 `Will Ukraine recapture Crimean
    # territory by...?`, 114077 `European country agrees to give Ukraine security
    # guarantee by...?` — each serving `reason: ''` / `headline: null` while
    # `/api/admin/discover-quality/trace/{id}`, which does NOT drop expired rungs,
    # composed "27% chance by December 31" for the same market in the same minute.
    #
    # 🔴 THE PERCENT IS THIS COMPOSER'S OWN `answer`, NOT A PRE-RENDERED CLAUSE.
    # The field path builds its clause off `leader_probability`/`rendered_leader_percent`
    # and this path off the AFFIRMATIVE's; on a one-leg board they are the same row, so
    # handing the finished string across would agree today and drift the moment those two
    # bases diverge. Taking only the LABEL and reusing `answer` makes the caption and the
    # hero one number by construction rather than by coincidence.
    #
    # The refusals are unchanged and are all upstream of the label: `stale_past_resolution`
    # returns fourteen lines above, a proven cumulative ladder (#4640) and a title that
    # elided no "by" both yield no label at all, and a genuine Yes/No pair has no date to
    # be a bound on. This can only speak where #6470 already ruled the sentence true.
    if deadline_label:
        level = f"{answer} {DEADLINE_PREPOSITION} {deadline_label}"
        return composed(level, level)
    return BinaryCardCopy("", "", "")


class LiveClaim(NamedTuple):
    """One supported claim about a live card, with the sentence that states it.

    The type travels WITH the sentence because two different slots need two
    different things from the same decision: the caption needs the words, and
    the ladder in `generate_event_reason` needs to know which rung the claim
    belongs on. Recomputing the type from the string afterwards — sniffing for
    the word "leading" — is how the pill and the caption drifted apart before.
    """

    claim_type: str
    sentence: str


def compose_live_claim(
    *,
    home_team: str,
    away_team: str,
    status: str,
    home_probability: Optional[float],
    away_probability: Optional[float],
    opening_home_prob: Optional[float],
    home_score: Optional[int],
    away_score: Optional[int],
) -> Optional[LiveClaim]:
    """The one supported claim this live card may make, or None. (T10-1, #5439)

    `select_live_claim` decides WHETHER and WHICH; this decides how to say it.
    Splitting them that way is deliberate: the eligibility rules are about
    evidence and belong beside the tri-state determinations in `highlights.py`,
    and a renderer must not be able to create a claim by writing a sentence for
    it. Returns None when nothing is supported — ruling 146, suppress the
    sentence, never the card.

    Callers: `generate_event_reason` (the `reason` field) and `routes/feed.py`
    (the `headline` field, which is what the web caption chain actually renders
    on a live card — see #4596).
    """
    claim = select_live_claim(
        status=status,
        opening_home_prob=opening_home_prob,
        current_home_prob=home_probability,
        home_score=home_score,
        away_score=away_score,
    )
    if claim is None:
        return None

    # #4580 — this sentence says *leading*, so the scoreboard decides it. The
    # `"favorite_switched" in reasons` co-gate is GONE (T10-1): whether the
    # market has come round to the underdog is a different question from whether
    # the underdog is ahead, and holding a true field sentence hostage to a price
    # event is #4580's confusion run backwards. On a live card the underdog is
    # often ahead long before the price crosses over, and those cards used to
    # fall through to "Tight game".
    #
    # The baseline is now NAMED. "Boston leading as underdog" makes the reader
    # take our word for the word "underdog"; "Boston leading after starting at
    # 38%" hands them the number the claim rests on, and it is the number the
    # card is not otherwise showing (the odds bar carries the LIVE price, not the
    # pre-game one).
    #
    # Wording: "leading", not "leads". The subject is a team name and our
    # subject-verb agreement is only decidable from `team_id`, which the feed
    # does not have here (#4700 — "Los Angeles Dodgers leads at 30%" went to page
    # one). A participle is correct for every name we serve. And "starting at",
    # not "opening at": `claims_undated_baseline` bans the word "opening" without
    # a date, rightly — but this baseline is the kickoff of a game the card says
    # is LIVE, so the instant is not in doubt and the sentence should not borrow
    # a phrase that means it is.
    if claim == "underdog_lead":
        underdog = away_team if opening_home_prob > 0.5 else home_team
        underdog_opening = (
            opening_home_prob if opening_home_prob < 0.5 else 1 - opening_home_prob
        )
        return LiveClaim(
            "underdog_lead",
            f"{underdog} leading after starting at {_display_pct(underdog_opening)}%",
        )

    # T10-1 — a MOVEMENT claim states its endpoints. "Milwaukee Brewers odds
    # shifted 42%" is a delta with nothing to hang it on: a reader cannot tell
    # 8%->50% from 50%->92%, and those are opposite stories. Naming both numbers
    # also keeps the sentence honestly about the price, which is the one thing
    # this evidence is about.
    change = home_probability - opening_home_prob
    if change > 0:
        mover, was, now_prob = home_team, opening_home_prob, home_probability
    else:
        mover = away_team
        was = 1 - opening_home_prob
        now_prob = (
            away_probability if away_probability is not None else 1 - home_probability
        )
    return LiveClaim(
        "movement",
        f"{mover} chance rose from {_display_pct(was)}% to {_display_pct(now_prob)}%",
    )


def generate_event_reason(
    home_team: str,
    away_team: str,
    status: str,
    highlight_reasons: list[str],
    home_probability: Optional[float] = None,
    away_probability: Optional[float] = None,
    opening_home_prob: Optional[float] = None,
    home_score: Optional[int] = None,
    away_score: Optional[int] = None,
    event_tags: Optional[list[str]] = None,
    prematch_percents: Optional[Mapping[str, Optional[int]]] = None,
) -> str:
    """
    Generate a one-line explanation for why an event is interesting.

    Returns a human-readable reason string for the feed card, or empty
    string when the card's visual elements (score, odds bar, badges)
    already convey the information.

    ``prematch_percents`` is ``{"home": int|None, "away": int|None}`` — the two
    whole percents the FINISHED card prints in its own "Pre-match" row, already
    resolved through the pre-match ladder and already rounded once as a duel by
    `graded_card.duel_percents_by_side`. It is the authority for any sentence
    that restates a pre-game number; see the settled block below for why nothing
    here may re-derive them. Keyed rather than a pair because the caller is in
    another module and a transposed side reads as a true sentence about the
    wrong team.
    """
    reasons = set(highlight_reasons)

    # ── Finished events ──────────────────────────────────────────
    # Card shows: score (winner bolded) + opening odds bar + "Opened X/Y".
    # Only add text for genuinely insightful context.
    if status in ("completed", "closed"):
        if "upset" in reasons:
            if (
                home_score is not None
                and away_score is not None
                and opening_home_prob is not None
            ):
                # #6181 — THE SENTENCE STATES THE NUMBER THE CARD PRINTS, AND
                # #5567 — IT NAMES WHO IT IS ABOUT.
                #
                # Served on production 2026-09-14 over event 14637256 (Cowboys
                # 20-28 Giants) as "Won as 39% underdog" directly beneath the
                # card's own row reading `62% · Pre-match · 38%`. One team, one
                # pre-game chance, two numbers, two lines apart.
                #
                # TWO INDEPENDENT CAUSES, AND THE SPECIMEN SAT ON BOTH:
                #
                # 1. The wrong rung. The card's row is `prematch_odds`, the
                #    per-team reading resolved through Alex's ladder — Kalshi,
                #    then Polymarket, then the books (`utils/prematch_reading`).
                #    That row said kalshi 0.385. This branch read `Event.opening_*`
                #    — the books median, 0.3908 — because `feed_scoring`'s note
                #    kept `opening_odds` for "the highlight/upset logic ... none
                #    of them are asking this question". This sentence IS asking
                #    it, and the card answers it three millimetres away.
                #
                # 2. The wrong rounding, and this half is load-bearing: swapping
                #    to the ladder alone does NOT fix it. `rendered_percent(0.385)`
                #    is 39, while the card derives the underdog's side as
                #    `100 - leader` = 38. No rounding of the raw value can
                #    reproduce a derived percent — which is exactly what
                #    `_display_pct`'s `printed` parameter was added for (#4146),
                #    and why this branch takes the card's percent rather than a
                #    probability it would have to round for itself.
                #
                # So the percents are handed in already resolved and already
                # rounded, and the probability below is a fallback only, for the
                # caller that holds an opening and no reading.
                # #6204 — THE SCOREBOARD DECIDES "WON", AND THE BOARD DECIDES
                # "UNDERDOG". THIS SENTENCE MAKES TWO CLAIMS AND USED TO CHECK
                # NEITHER.
                #
                # Served on production 2026-09-14 over event 15307167 (Örebro SK
                # 1-1 Nordic United FC, `status=completed`) as "Nordic United FC
                # won as a 56% underdog", above the card's own `1 - 1` and its
                # own pre-match row reading `44% · Pre-match · 56%`. Wrong three
                # ways in one line: they did not win, nobody did, and 56% is the
                # HIGHER of the two numbers the card prints.
                #
                # 1. THE DRAW. The winner was chosen by `if home > away / else`,
                #    and a bare `else` swallows equality — so every level final
                #    declared the away team the winner. The `upset` tag that
                #    admits this sentence is set in `highlights.py` off
                #    `favorite_switched`, a PRICE-derived flag; the scoreboard
                #    was read only to pick a side, never to ask whether there
                #    was a winner to pick. That is exactly #4580, whose note
                #    sits forty lines below this one for the LIVE sentence:
                #    "this sentence says *leading*, so the scoreboard decides
                #    it, not the price". This one says *won*.
                #
                #    A draw returns "" rather than "Upset result", per #4640:
                #    the bare string is the same false claim with the number
                #    removed. The card already says it three ways — the Final
                #    chip, the level score, and each side's pre-game percent.
                #
                # 2. THE WORD "UNDERDOG" is #6187's rule, and its helper is in
                #    this file: a comparative may only be printed when the
                #    reader can SEE it on the board. Tested on the PRINTED
                #    percents, not the probabilities — #6187 measured that exact
                #    ties at full precision are real, so a probability-gap test
                #    would still pass a card printing `50% · Pre-match · 50%`
                #    (event 15304229 did, live, that same read).
                #
                #    Read as: the pre-match leader is the side that LOST, and
                #    the winner is the runner-up beneath it. `lead_is_printable`
                #    fails to today's copy when either percent is unknown, so
                #    the `opening`-only caller below keeps its wording verbatim.
                printed = prematch_percents or {}
                if home_score > away_score:
                    winner = home_team
                    winner_opening_prob = opening_home_prob
                    winner_printed = printed.get("home")
                    loser_printed = printed.get("away")
                elif away_score > home_score:
                    winner = away_team
                    winner_opening_prob = 1 - opening_home_prob
                    winner_printed = printed.get("away")
                    loser_printed = printed.get("home")
                else:
                    return ""
                if not lead_is_printable(loser_printed, winner_printed):
                    return ""
                pct = _display_pct(winner_opening_prob, winner_printed)
                return _underdog_sentence(winner, pct)
            return "Upset result"
        # #6477 — A FINISHED UPSET WHOSE PRICE NEVER MOVED IS STILL AN UPSET.
        #
        # The branch above is the only settled sentence this card can carry, and
        # it is admitted by `"upset"` — which `highlights.py` appends only behind
        # `favorite_switched`, a PRICE event comparing the live aggregate against
        # `opening_favorite`. On a FINISHED game that aggregate is not free to
        # disagree: `compute_aggregate_probability` drops
        # `_EXCLUDE_WHEN_COMPLETED = {"kalshi", "polymarket"}` once the status is
        # final, so an event whose only speaker is a prediction market falls past
        # Tier 1 and Tier 2 to Tier 3 — `opening_home_probability`, the very
        # number `opening_favorite` was derived from. The gate is then asking
        # whether the opening price switched away from itself. It cannot, ever,
        # for that whole population, however large the upset.
        #
        # Served on production 2026-09-16 04:1xZ, card 11 of 60 at 390px: event
        # 15305823, Alavés 0 - 1 Valencia (La Liga, `status=completed`,
        # `discover_marquee_final`), `win_probability_sources` holding polymarket
        # 0.0005 and nothing else, aggregate 0.7618 == opening 0.7618. No switch,
        # no `"upset"`, `reason: ""` — a hole two cards below "Baltimore Orioles
        # won as a 44% underdog", which is the same sentence on an event that
        # happened to keep a sportsbook. 55 of the 151 decided upsets in the
        # seven days to 2026-09-16 sit in this class, 38 of them
        # prediction-market-only: the gate, not the fixture.
        #
        # THE SENTENCE NEVER NEEDED THE PRICE. It reads the SCOREBOARD against
        # the PRE-GAME BOARD, and whether a price moved in between is a different
        # question that already has its own two answers — the chip (#6279) and
        # the movement line (#4094), both deliberately withheld here. So this
        # branch asks only what the sentence actually claims: who won, and were
        # they beneath the other side on the board this card prints.
        #
        # IT FAILS CLOSED WHERE THE BRANCH ABOVE FAILS OPEN, and that asymmetry
        # is the point. `lead_is_printable` returns True when either percent is
        # None — #6187's "the unknown case must not become a guess" convention,
        # which exists to keep the `"upset"` caller's wording verbatim. Inherited
        # here it would print "won as a 76% underdog" over every unprinted
        # favourite that ever won, because in this branch nothing else
        # establishes the word: there is no price event standing behind it. So
        # both percents must be KNOWN and the winner's strictly lower — every
        # word then checkable against the two numbers the card draws three
        # millimetres below the sentence.
        #
        # AND IT TAKES A MAGNITUDE BAR, WHICH THE BRANCH ABOVE DOES NOT, because
        # the two branches are admitted by different evidence and may honestly
        # hold different bars: that one has a real price swing standing behind
        # the word, this one has only the gap between two printed numbers.
        # Measured over the same seven days, 24 of the 55 denied upsets have the
        # winner between 40% and 48% — which is #2753's open complaint, verbatim
        # ("Won as 48% underdog"), and shipping it here would manufacture that
        # class on a population that is currently silent.
        #
        # The bar is NOT a new constant. `CLOSE_MATCHUP_MIN` is where
        # `highlights.py` stops calling a board close, and this module already
        # has the word it uses for boards inside it — "Tight game", forty lines
        # down. A side the system itself classifies as half of a close matchup
        # is not an underdog, so the sentence declines and the card keeps the
        # two percents it was already printing. 31 of the 55 clear it; the
        # specimen, at a printed 18, clears it easily. Whether the branch ABOVE
        # should inherit the same bar is #2753's question, on #2753's surface
        # (the chip), and is deliberately not answered here.
        #
        # Nothing above this line moves. The `"upset"` block returns on all four
        # of its paths, so a card captioned today is captioned identically here.
        if (
            home_score is not None
            and away_score is not None
            and home_score != away_score
            and prematch_percents
        ):
            if home_score > away_score:
                settled_winner = home_team
                winner_pct = prematch_percents.get("home")
                loser_pct = prematch_percents.get("away")
            else:
                settled_winner = away_team
                winner_pct = prematch_percents.get("away")
                loser_pct = prematch_percents.get("home")
            if (
                winner_pct is not None
                and loser_pct is not None
                and lead_is_printable(loser_pct, winner_pct)
                and int(winner_pct) < CLOSE_MATCHUP_MIN * 100
            ):
                return _underdog_sentence(settled_winner, int(winner_pct))
        # #4094 — NO INTRA-GAME MOVEMENT SENTENCE ON A FINAL CARD.
        #
        # This block used to answer `major_prob_swing` with "{team} odds shifted
        # {n}% during the game" before it reached the return below. That sentence
        # is the scoreboard restated: a game opens near 50/50 and ends at 100/0,
        # so a finished game has a major swing by construction and the number is
        # guaranteed, not newsworthy. Served on production 2026-09-08 as "San
        # Francisco Giants odds shifted 27% during the game" over a 4-5 final the
        # same card already printed.
        #
        # The upset branch above is the settled sentence that DOES earn its line,
        # because it reads the result against the pre-game number rather than
        # against the final one. Everything else falls through to the card UI,
        # which already says it three ways: the Final chip, the score with the
        # winner bolded, and each side's dimmed pre-game percentage.
        return ""

    # ── Live events ──────────────────────────────────────────────
    if status == "live":
        # #4580 — this sentence says *leading*, so the scoreboard decides it,
        # not the price. It used to return on `favorite_switched` alone — a
        # price-derived flag — while `home_score`/`away_score` sat unread in
        # this very signature, and told a reader the underdog was leading the
        # NFL opener at 0-0. Same determination as the capsule, one function.
        #
        # The old `return "Underdog leading"` fallback is deliberately gone: it
        # fired when `opening_home_prob` was None, which is precisely when we
        # cannot name an underdog OR check the field. Falling through reaches
        # the price sentence below, which is true from what we do have.
        # T10-1 (#5439) — WHICH claim this card may make is now one decision,
        # taken by `select_live_claim` and rendered by `compose_live_claim`, and
        # the label ladder in `highlights.py` answers from the same
        # determination. Two ladders reading the same rows and reaching their
        # own conclusions is how a card ends up with a pill and a caption
        # describing different events (#4596).
        #
        # The selector's own order (field fact before price fact) is preserved
        # below; the two arms it does not govern — "Virtually even" and "Tight
        # game" — sit between them exactly where they always did. Those describe
        # the STATE the card is already showing and claim no event.
        claim = compose_live_claim(
            home_team=home_team,
            away_team=away_team,
            status=status,
            home_probability=home_probability,
            away_probability=away_probability,
            opening_home_prob=opening_home_prob,
            home_score=home_score,
            away_score=away_score,
        )

        if claim is not None and claim.claim_type == "underdog_lead":
            return claim.sentence

        if "very_close" in reasons:
            return "Virtually even"

        if "close_matchup" in reasons:
            return "Tight game"

        if claim is not None and claim.claim_type == "movement":
            return claim.sentence

        # Generic live — LIVE badge is sufficient
        return ""

    # ── Upcoming/scheduled events ────────────────────────────────
    if "major_prob_swing" in reasons:
        if opening_home_prob is not None and home_probability is not None:
            change = home_probability - opening_home_prob
            direction_team = home_team if change > 0 else away_team
            pct_change = abs(round(change * 100))
            return f"{direction_team} odds shifted {pct_change}% since open"
        return ""

    if "starting_soon" in reasons and "close_matchup" in reasons:
        return "Starting soon \u2014 close matchup"

    if "starting_very_soon" in reasons:
        return "Starting in under an hour"

    if "starting_soon" in reasons:
        return "Starting soon"

    # ── Tag-based context (LLM enrichment) ─────────────────────────
    # These add a story angle when no odds-based reason was found.
    tags = set(event_tags or [])
    _TAG_REASONS: list[tuple[str, str]] = [
        ("narrative:historic_rivalry", "Historic rivalry"),
        ("narrative:rivalry", "Rivalry game"),
        ("stakes:elimination", "Elimination game"),
        ("stakes:clinch", "Clinch scenario"),
        ("stakes:title_defense", "Title defense"),
        ("narrative:cinderella", "Cinderella story"),
        ("narrative:revenge_game", "Revenge game"),
        ("narrative:rematch", "Postseason rematch"),
        ("narrative:farewell_tour", "Farewell tour"),
        ("narrative:comeback", "Comeback story"),
        ("stakes:record_chase", "Record chase"),
        ("stakes:must_win", "Must-win game"),
        ("audience:national_interest", "National interest"),
        ("narrative:david_vs_goliath", "David vs. Goliath"),
    ]
    for tag, label in _TAG_REASONS:
        if tag in tags:
            return label

    # Fallback — the card shows teams and odds, no need for text
    return ""


# ── Subject-verb agreement for the leader templates (#4700) ───────────────────
#
# "Los Angeles Dodgers leads at 30%" was slots 1 and 2 of the morning page. A
# plural team name takes a plural verb; the templates hard-coded the singular.
#
# DO NOT DECIDE THIS ON SPELLING. The census on #4700 shows the orthographic
# rule ("ends in s -> plural") wrong in BOTH directions on lines we serve today:
#
#   `Layne Riggs leads at 29%`                          a person; singular is RIGHT
#   `No new Director of Legislative Affairs leads ...`  an abstract; singular is RIGHT
#   `Miami Heat` / `Utah Jazz` / `Tampa Bay Lightning`  teams; singular is RIGHT
#
# So spelling is consulted ONLY once the caller has told us the subject is a
# team, on data (`FuturesOutcome.team_id`) rather than on the string. Within
# team names the orthography is then safe and correct: the singular-verb
# nicknames (Heat, Jazz, Magic, Wild, Lightning, Thunder, Avalanche) are exactly
# the ones that do not end in "s".
#
# FAIL SINGULAR. `leader_is_team` defaults to False, so any caller that cannot
# prove team-ness keeps today's wording verbatim. That is deliberate: `team_id`
# is populated on only 3 of 45 served leader outcomes (measured on #4700), so
# the unknown case is the COMMON one and it must not become a guess.
#
# ── #6550: THE LAST TOKEN OF A PROVEN TEAM IS NOT ALWAYS A NICKNAME ───────────
#
# Production `/sports`, 2026-09-16 12:30Z, two cards on ONE screen:
#
#   `Texas (10%) lead College Football National Championship Winner`   wrong
#   `Texas Tech (36%) leads College Football Big 12 Championship …`    right
#
# and Discover served `Texas lead at 10%` for the same market. The
# `leader_is_team` gate above is doing its job — outcome 834 carries
# `team_id` — but the paragraph it guards assumes the printed subject ENDS IN
# THE NICKNAME. In college and several pro markets the venue prints the bare
# school or city and never the nickname at all, so the trailing-`s` test reads
# a PLACE NAME as a plural: `Texas`, `Indianapolis`, `New Orleans`,
# `Las Vegas`, `St. Louis`, `Dallas`, `Memphis`, `Rutgers`, `Leeds`,
# `Olympiacos`. Measured on production: 66 rows over 16 (printed, team) pairs
# of open markets, `Las Vegas Aces` among them at 0.87 — page-one leaders, not
# a tail. `Ole Miss` escaped only by luck, because the `ss` guard below happens
# to catch it.
#
# THE ANSWER IS STILL NOT A WORD LIST. No place-name dictionary, no orthography
# for the new arm either: the signal is already in hand, because a proven team
# has a `teams.name` and the printed name can be compared against it.
#
#   `Texas` is a strict prefix of `Texas Longhorns`   -> nickname stripped
#   `Los Angeles Dodgers` EQUALS `Los Angeles Dodgers` -> nickname printed
#
# A stripped nickname leaves a place, and a place takes the singular; an equal
# name is the case #4700 measured and keeps its rule unchanged. `teams.location`
# is NOT the signal — authority/383 measured it polluted (`North Texas` carries
# location `Chelsea`, `East Texas A&M Lions` carries `Duke`).
#
# FAIL TO TODAY'S WORDING, not to singular. `leader_team_name` defaults to None,
# so a caller that cannot name the team gets #4700's rule verbatim. This arm can
# therefore only ever turn a wrong "lead" into "leads"; it can never take the
# plural away from `Los Angeles Dodgers`, which is the regression that would
# undo #4700.

#: Plural team nicknames that do not end in "s". `Sox` is the whole set in the
#: leagues we carry (Red Sox, White Sox).
_PLURAL_TEAM_NICKNAMES_WITHOUT_S = ("sox",)


def _printed_name_omits_nickname(
    leader_name: str, leader_team_name: Optional[str]
) -> bool:
    """Is the printed subject the team's name with its NICKNAME stripped? (#6550)

    True only for a strict prefix ending on a word boundary — `Texas` within
    `Texas Longhorns`, never `Texas` within a hypothetical `Texasville FC`. An
    equal name is False: the nickname IS printed, so #4700's rule decides.

    False whenever the team name is unknown, which is what keeps this arm unable
    to change any line #4700 already gets right.
    """
    if not leader_team_name:
        return False
    printed = " ".join(leader_name.split()).casefold()
    full = " ".join(leader_team_name.split()).casefold()
    if not printed:
        return False
    return full.startswith(printed + " ")


def leader_agreement_verb(
    leader_name: Optional[str],
    leader_is_team: bool = False,
    leader_team_name: Optional[str] = None,
) -> str:
    """"lead" or "leads" for `{leader_name} <verb> at {pct}%` (#4700, #6550).

    Returns the singular unless the caller has PROVEN the subject is a team and
    the team's PRINTED name ends in a plural nickname. See the block comment
    above for why spelling alone is not consulted, and why a printed name that
    stops short of the nickname is a place rather than a plural.
    """
    if not leader_is_team or not leader_name:
        return "leads"
    tokens = leader_name.split()
    if not tokens:
        return "leads"
    nickname = tokens[-1].lower()
    if nickname in _PLURAL_TEAM_NICKNAMES_WITHOUT_S:
        return "lead"
    # #6550: asked BEFORE the orthographic test, which is the only test it is
    # correcting. Asked AFTER the nickname list above so a printed plural
    # nickname keeps its verb even if it were ever also a prefix of a longer
    # stored name — the list is the stronger evidence of the two.
    if _printed_name_omits_nickname(leader_name, leader_team_name):
        return "leads"
    # "ss" guards a hypothetical singular nickname; "s" alone is the plural.
    if nickname.endswith("s") and not nickname.endswith("ss"):
        return "lead"
    return "leads"


# ── A LEAD IS CLAIMED ONLY WHEN THE PRINTED BOARD CAN SHOW IT (#6187) ─────────
#
# Production page one, 2026-09-14 17:40Z: SEVEN of eighty-five field cards. Three
# verbatim, each above its own printed rows:
#
#   'Canterbury-Bankstown Bulldogs (49%) now leads'    rows: 49% · 49% · 49%
#   'MOUZ leads at 22%; resolves within a week'        rows: 22% · 22% · 22%
#   'Jordan leads at 9%'                               rows:  9% ·  9% ·  8%
#
# The caption names a leader at a number its runner-up also shows. Nothing on the
# card supports the verb: the reader's eye goes from "leads at 22%" straight to
# two more rows reading 22%.
#
# 🔴 THIS IS OFTEN NOT A ROUNDING ARTEFACT AT ALL, AND THAT IS WHY THE TEST IS ON
# THE PRINTED PERCENTS. Jordan is a real 0.9pp lead (0.0925 vs 0.0889) that rounds
# away. But the Bulldogs, MOUZ and the S&P band are ties at FULL PRECISION —
# 0.49/0.49/0.49, 0.2171/0.2171/0.2171, 0.1604/0.1604 — four of the seven. There
# the "leader" is whichever row the descending sort happened to emit first, and
# the sentence is not merely imprecise, it is arbitrary. A gap test on the
# probabilities would have to pick an epsilon and would still pass the Jordan
# card; the printed board is the thing the reader can actually check, so the
# printed board is what decides whether the claim may be made.
#
# ** THE REMEDY IS TO DROP THE COMPARATIVE, NOT TO ADD PRECISION. ** A decimal in
# the caption ("Jordan leads at 9.3%") makes the caption disagree with the board
# in the other direction — #6181's defect with the operands swapped. The board is
# already ranked, so rank 1 still reads first without the word.
#
# The `leader_change` branches do not merely drop the verb, they do not speak at
# all: "New favorite" IS the comparative, and #4640 settled the shape of that
# refusal for cumulative ladders one branch above ("Falling through rather than
# returning the bare 'New favorite in {market}' is the point: that string is the
# same false claim with the number removed"). A tie is the same false claim.


def lead_is_printable(
    rendered_leader_percent: Optional[int] = None,
    rendered_runner_up_percent: Optional[int] = None,
) -> bool:
    """May this card's copy use a comparative — "leads", "New favorite"? (#6187)

    True when the leader's printed percent is strictly greater than the highest
    printed percent among the rows beneath it, i.e. when a reader checking the
    board can see the lead the sentence asserts.

    FAIL TO TODAY'S COPY. Either percent unknown returns True, so a caller that
    has not been taught to pass the runner-up keeps its wording verbatim. Same
    convention as `leader_agreement_verb`'s `leader_is_team`, and for the same
    reason: the unknown case must not become a guess. Because that default is
    silent, the adoption of the route call sites is asserted structurally in
    `test_card_sentence_states_the_printed_percent_4146.py` — an unadopted call
    site is a live defect here, not a latent one.
    """
    if rendered_leader_percent is None or rendered_runner_up_percent is None:
        return True
    return int(rendered_leader_percent) > int(rendered_runner_up_percent)


def movement_subject_is_printable(
    subject_name: Optional[str],
    subject_is_printed: Optional[bool] = None,
) -> bool:
    """May a movement sentence take `subject_name` as its subject? (#6219)

    True when the card prints a row for that outcome, i.e. when a reader who
    follows the sentence can find the thing it is about. A movement sentence is
    the only copy in this module that names an outcome and then says nothing
    about where it now stands — it reports a CHANGE, never a LEVEL — so it is
    the only copy that can be left pointing at a row the card does not draw.

    Measured on production 2026-09-14 (#6219): three of the twenty-one ladder
    cards serving a movement sentence named an outcome collapsed into the
    "Field and remaining outcomes" row. `National Rugby League Champion` led
    with "Canberra Raiders down 46.5 points since Feb 19" above a board of
    Bulldogs 49 / Cowboys 49 / Rabbitohs 49 / Panthers 41; Canberra is rank 8 at
    3%. `Korea KBO Champion` named SSG Landers — rank 10 of 10, the single least
    likely outcome in the market.

    The selector makes this the NORMAL case rather than an edge one:
    `_biggest_move_from_opening` picks the largest absolute move over every
    outcome, and in a championship field the biggest lifetime move is almost
    always a collapsed former favourite — which is near 0% precisely BECAUSE it
    collapsed, and therefore is exactly the outcome that cannot be in the top
    four the card draws.

    FAIL TO TODAY'S COPY, the same convention as `lead_is_printable` above and
    for the same reason: `None` means the caller has not been taught to say
    which rows it prints, and the unknown case must not become a guess. Only an
    explicit `False` silences a branch. Because that default is silent, route
    adoption is asserted structurally in the #6219 guard rather than left latent.
    """
    if subject_is_printed is None:
        return True
    if not (subject_name or "").strip():
        return False
    return bool(subject_is_printed)


def leader_standing_clause(
    leader_name: str, pct: int, *, verb: str, lead_is_visible: bool
) -> str:
    """`MOUZ leads at 22%` — or `MOUZ at 22%` when the board cannot show a lead.

    One composer for the clause rather than the five f-strings it replaces. The
    headline, the reason and the context summary all state this same standing,
    and they are near-copies maintained by hand, so six independent chances to
    keep the comparative is six chances to reintroduce #6187.
    """
    if lead_is_visible:
        return f"{leader_name} {verb} at {pct}%"
    return f"{leader_name} at {pct}%"


def generate_futures_reason(
    market_name: str,
    highlight_reasons: list[str],
    top_mover_name: Optional[str] = None,
    top_mover_change: Optional[float] = None,
    top_surprise_name: Optional[str] = None,
    top_surprise_change: Optional[float] = None,
    leader_name: Optional[str] = None,
    leader_probability: Optional[float] = None,
    rendered_leader_percent: Optional[int] = None,
    # #6187: the highest percent PRINTED beneath the leader. Defaults None so an
    # uninformed caller keeps the comparative verbatim — see `lead_is_printable`.
    rendered_runner_up_percent: Optional[int] = None,
    # #6219: does the card DRAW a row for the outcome the movement sentence
    # names? Defaults None so an uninformed caller keeps its wording verbatim —
    # see `movement_subject_is_printable`.
    top_surprise_is_printed: Optional[bool] = None,
    top_mover_is_printed: Optional[bool] = None,
    # #4700: proven team-ness of `leader_name`, for subject-verb agreement.
    # Defaults False so an uninformed caller keeps the singular verbatim.
    leader_is_team: bool = False,
    # #6550: the team's FULL stored name (`teams.name`), so the verb can tell a
    # printed nickname from a printed place. Defaults None so an uninformed
    # caller keeps #4700's wording verbatim — see `leader_agreement_verb`.
    leader_team_name: Optional[str] = None,
    # #4640: is `leader_name` a rung of ONE cumulative ladder? Defaults False so
    # an uninformed caller's copy is unchanged unless nestedness is proven.
    leader_is_ladder_rung: bool = False,
    # #6470: the preposition the display rule elided from the title
    # (`market_display_name.elided_trailing_preposition`). Defaults None so an
    # uninformed caller stays silent exactly as before — see
    # `leader_deadline_clause`.
    leader_deadline_preposition: Optional[str] = None,
    source_count: int = 1,
    affirmative_probability: Optional[float] = None,
    rendered_affirmative_percent: Optional[int] = None,
    top_surprise_opened_at: Optional[datetime] = None,
    now: Optional[datetime] = None,
) -> str:
    """
    Generate a one-line explanation for why a futures market is interesting.

    Returns a human-readable reason string for the feed card.
    """
    reasons = set(highlight_reasons)
    # #4700: resolved once, above every branch, so no template can disagree with
    # another about the same subject.
    _verb = leader_agreement_verb(leader_name, leader_is_team, leader_team_name)
    # #4640: likewise resolved once — see `_leader_is_unnameable`.
    _no_leader_subject = _leader_is_unnameable(leader_name, leader_is_ladder_rung)
    # #6470: resolved once beside the refusal it answers, so a template can
    # never print the level clause without having consulted that refusal.
    _deadline = _deadline_fallback(
        leader_name,
        leader_probability,
        rendered_leader_percent,
        leader_is_ladder_rung=leader_is_ladder_rung,
        leader_deadline_preposition=leader_deadline_preposition,
    )
    # #6187: and likewise — may any template below use a comparative at all?
    _lead_visible = lead_is_printable(
        rendered_leader_percent, rendered_runner_up_percent
    )
    # #6219: and likewise — may a movement template name its subject at all?
    # Resolved from the names AS RECEIVED, above the `_answering_side_label`
    # rewrite below, because the caller decided printedness against the raw
    # outcome rows and a rewritten label would no longer match them.
    _surprise_sayable = movement_subject_is_printable(
        top_surprise_name, top_surprise_is_printed
    )
    _mover_sayable = movement_subject_is_printable(top_mover_name, top_mover_is_printed)

    # A yes/no question never reaches the field templates below — it has no
    # field. See `compose_binary_card_copy`.
    if affirmative_probability is not None:
        return compose_binary_card_copy(
            market_name=market_name,
            highlight_reasons=highlight_reasons,
            affirmative_probability=affirmative_probability,
            rendered_affirmative_percent=rendered_affirmative_percent,
            top_mover_change=top_mover_change,
            top_surprise_change=top_surprise_change,
            top_surprise_opened_at=top_surprise_opened_at,
            deadline_label=deadline_level_label(
                leader_name,
                leader_is_ladder_rung=leader_is_ladder_rung,
                deadline_preposition=leader_deadline_preposition,
            ),
            now=now,
        ).reason

    # Once, before any branch reads them: a label that merely negates the
    # market's own question can never be this sentence's subject. Applied to
    # every outcome-label input rather than to the nine f-strings below, so a
    # tenth template cannot reintroduce the defect.
    leader_name = _answering_side_label(leader_name, market_name)
    top_mover_name = _answering_side_label(top_mover_name, market_name)
    top_surprise_name = _answering_side_label(top_surprise_name, market_name)

    if "stale_past_resolution" in reasons:
        return ""

    # Leader change (most interesting)
    #
    # #4640 — on a cumulative ladder there is no favorite to change, so this
    # branch does not speak at all and the next real signal does. Falling
    # through rather than returning the bare "New favorite in {market}" is the
    # point: that string is the same false claim with the number removed.
    #
    # #6187 — and a tie is that same false claim a third time. "New favorite" IS
    # the comparative, so a board whose top rows print the same percent gets no
    # verb-less variant here; it falls through to the next signal it can support.
    if "leader_change" in reasons and not leader_is_ladder_rung and _lead_visible:
        if leader_name and leader_probability is not None:
            pct = _display_pct(leader_probability, rendered_leader_percent)
            return f"New favorite: {leader_name} ({pct}%) now {_verb} {market_name}"
        return f"New favorite in {market_name}"

    # (No `source_divergence` branch. Removed with the rest of DIAGNOSTIC_PHRASES
    # — the standing ruling is "the blend is the product": divergence between our
    # sources is a data bug to fix, not news to print. A card that reaches here on
    # divergence alone falls to the leader sentence below and says what it knows.)

    # Major movement
    if "major_movement_24h" in reasons:
        if top_mover_name and top_mover_change is not None and _mover_sayable:
            if _weak_outcome_label(top_mover_name):
                return f"Big odds movement in {market_name}"
            direction = "up" if top_mover_change > 0 else "down"
            pts = _points(top_mover_change)
            return f"{_side_label(top_mover_name)} moved {direction} {pts} today in {market_name}"
        return f"Big odds movement in {market_name}"

    # (No `rank_shakeup` branch. "Multiple ranking changes" described the ordering
    # of our own leaderboard, and the honest replacement is not available here:
    # `rank_shakeup` fires on two rank changes BELOW the top, and `leader_change`
    # — the one development a reader could restate — is its own branch above. So
    # the card falls through to a movement or leader sentence it can support.)

    # Moderate movement
    if "moderate_movement_24h" in reasons:
        if top_mover_name and top_mover_change is not None and _mover_sayable:
            if _weak_outcome_label(top_mover_name):
                return f"Odds shifting in {market_name}"
            direction = "up" if top_mover_change > 0 else "down"
            pts = _points(top_mover_change)
            return f"{_side_label(top_mover_name)} odds shifted {direction} {pts} today in {market_name}"
        return f"Odds shifting in {market_name}"

    # Resolving soon
    if "resolving_soon_7d" in reasons:
        if leader_name and leader_probability is not None:
            if _no_leader_subject:
                return f"{market_name} resolving within a week"
            pct = _display_pct(leader_probability, rendered_leader_percent)
            clause = leader_standing_clause(
                leader_name, pct, verb=_verb, lead_is_visible=_lead_visible
            )
            return f"{market_name} resolving soon, {clause}"
        return f"{market_name} resolving within a week"
    if "resolving_soon_30d" in reasons:
        if leader_name and leader_probability is not None:
            if _no_leader_subject:
                return f"{market_name} resolves within a month"
            pct = _display_pct(leader_probability, rendered_leader_percent)
            clause = leader_standing_clause(
                leader_name, pct, verb=_verb, lead_is_visible=_lead_visible
            )
            return f"{market_name} resolves within a month, {clause}"
        return f"{market_name} resolving within a month"

    # Lifetime move, DATED and DEMOTED (D1 clause a, #4066).
    #
    # This used to sit two branches above `rank_shakeup`, so "moved up 37.5
    # points from opening" beat a rank shakeup, a resolution inside the week and
    # every other live signal to the front of the card — an undated number of
    # unknown age presented as the morning's news. It now runs after every
    # signal that is anchored to a time, and it only speaks when it can name the
    # day it is measured from; an outcome with no `opening_captured_at` says
    # nothing here rather than saying "from opening".
    # #6219 — `_surprise_sayable` gates the WHOLE block, so an unprintable
    # subject falls through to the leader sentence below rather than taking the
    # weak-label arm's market-level paraphrase. The two cases look alike and are
    # not: a WEAK LABEL ("Above 120") is a row the card DOES draw whose name
    # simply does not read as a subject without the title, so "<market> has
    # shifted" still points the reader at something they can find. An
    # UNPRINTABLE subject is not on the board at all, and a market-level "has
    # shifted since Feb 19" would keep the unfollowable claim and merely drop
    # the name from it — the shape #4640 and #6187 both refused. Falling through
    # gives the card a sentence about a row it actually draws.
    since_opening = format_baseline_date(top_surprise_opened_at, now=now)
    if (
        since_opening
        and _is_printable_move(top_surprise_change)
        and _surprise_sayable
        and ("major_surprise" in reasons or "moderate_surprise" in reasons)
    ):
        if not _weak_outcome_label(top_surprise_name):
            direction = "up" if top_surprise_change > 0 else "down"
            pts = _points(top_surprise_change)
            return (
                f"{_side_label(top_surprise_name)} is {direction} {pts} "
                f"since {since_opening} in {market_name}"
            )
        return f"{market_name} has shifted since {since_opening}"

    # (No `multi_source` branch. How many rows we hold for a question is a count
    # of our inventory, and which venues carry it is attribution — D91 puts that
    # in the source mark, BY NAME. With the count gone the branch said exactly
    # what the fallback below says, so it is the fallback.)

    # Fallback
    #
    # #4056 — both rungs below returned `market_name` VERBATIM. On the Alito card that
    # made all three sentence slots the same string:
    #
    #     name     : 'Will Samuel Alito announce his retirement by...?'
    #     headline : 'Will Samuel Alito announce his retirement by...'
    #     reason   : 'Will Samuel Alito announce his retirement by...?'
    #     ctx      : 'Will Samuel Alito announce his retirement by...'
    #
    # — the card printing the same chopped phrase twice with nothing between them. The
    # `...` there is upstream, in the stored name, so trimming our own chop would not
    # have touched it; returning the name AT ALL is the defect. Empty instead, which
    # both clients render as absent (see the note in `compose_binary_card_copy`).
    if leader_name and leader_probability is not None:
        if _no_leader_subject:
            # #6470 — the label cannot be a SUBJECT, but where the venue's own
            # title said "by <blank>" it can still be a DEADLINE, and the level
            # clause is the true sentence this rung was always owed. Empty
            # whenever that word is absent, i.e. every case that reached here
            # before.
            return _deadline
        pct = _display_pct(leader_probability, rendered_leader_percent)
        # #6187 — the only leader template whose subject is followed by the
        # market rather than by a percent, so it takes "in" where the others
        # simply drop the verb. `leader_standing_clause` deliberately does not
        # cover this shape: folding two grammars into one helper is how the
        # sentence would come back reading "Jordan (9%) Which countries will…".
        if _lead_visible:
            return f"{leader_name} ({pct}%) {_verb} {market_name}"
        return f"{leader_name} ({pct}%) in {market_name}"

    return ""


def generate_futures_headline(
    highlight_reasons: list[str],
    top_mover_name: Optional[str] = None,
    top_mover_change: Optional[float] = None,
    top_surprise_name: Optional[str] = None,
    top_surprise_change: Optional[float] = None,
    leader_name: Optional[str] = None,
    leader_probability: Optional[float] = None,
    rendered_leader_percent: Optional[int] = None,
    # #6187: see `generate_futures_reason`. Defaults None -> comparative kept.
    rendered_runner_up_percent: Optional[int] = None,
    # #6219: see `generate_futures_reason`. Defaults None -> wording kept.
    top_surprise_is_printed: Optional[bool] = None,
    top_mover_is_printed: Optional[bool] = None,
    # #4700: proven team-ness of `leader_name`, for subject-verb agreement.
    # Defaults False so an uninformed caller keeps the singular verbatim.
    leader_is_team: bool = False,
    # #6550: the team's FULL stored name (`teams.name`), so the verb can tell a
    # printed nickname from a printed place. Defaults None so an uninformed
    # caller keeps #4700's wording verbatim — see `leader_agreement_verb`.
    leader_team_name: Optional[str] = None,
    # #4640: see `generate_futures_reason`. Defaults False -> copy unchanged.
    leader_is_ladder_rung: bool = False,
    # #6470: the preposition the display rule elided from the title
    # (`market_display_name.elided_trailing_preposition`). Defaults None so an
    # uninformed caller stays silent exactly as before — see
    # `leader_deadline_clause`.
    leader_deadline_preposition: Optional[str] = None,
    source_count: int = 1,
    market_name: Optional[str] = None,
    affirmative_probability: Optional[float] = None,
    rendered_affirmative_percent: Optional[int] = None,
    top_surprise_opened_at: Optional[datetime] = None,
    now: Optional[datetime] = None,
) -> str:
    """Generate compact, specific card text for futures Discover cards."""
    reasons = set(highlight_reasons)
    # #4700: resolved once, above every branch (see `generate_futures_reason`).
    _verb = leader_agreement_verb(leader_name, leader_is_team, leader_team_name)
    # #4640: likewise resolved once — see `_leader_is_unnameable`.
    _no_leader_subject = _leader_is_unnameable(leader_name, leader_is_ladder_rung)
    # #6470: resolved once beside the refusal it answers, so a template can
    # never print the level clause without having consulted that refusal.
    _deadline = _deadline_fallback(
        leader_name,
        leader_probability,
        rendered_leader_percent,
        leader_is_ladder_rung=leader_is_ladder_rung,
        leader_deadline_preposition=leader_deadline_preposition,
    )
    # #6187: likewise — see `generate_futures_reason`.
    _lead_visible = lead_is_printable(
        rendered_leader_percent, rendered_runner_up_percent
    )
    # #6219: likewise — see `generate_futures_reason`.
    _surprise_sayable = movement_subject_is_printable(
        top_surprise_name, top_surprise_is_printed
    )
    _mover_sayable = movement_subject_is_printable(top_mover_name, top_mover_is_printed)

    if affirmative_probability is not None:
        return compose_binary_card_copy(
            market_name=market_name,
            highlight_reasons=highlight_reasons,
            affirmative_probability=affirmative_probability,
            rendered_affirmative_percent=rendered_affirmative_percent,
            top_mover_change=top_mover_change,
            top_surprise_change=top_surprise_change,
            top_surprise_opened_at=top_surprise_opened_at,
            deadline_label=deadline_level_label(
                leader_name,
                leader_is_ladder_rung=leader_is_ladder_rung,
                deadline_preposition=leader_deadline_preposition,
            ),
            now=now,
        ).headline

    # Same single point as the other two generators. `market_name` is optional
    # here, and `_answering_side_label` is a no-op without it — a headline with
    # no question to negate is left exactly as it renders today.
    leader_name = _answering_side_label(leader_name, market_name)
    top_mover_name = _answering_side_label(top_mover_name, market_name)
    top_surprise_name = _answering_side_label(top_surprise_name, market_name)

    if "stale_past_resolution" in reasons:
        return ""

    # #4640 — a cumulative ladder has no favorite to change; fall through to the
    # next real signal rather than emit the claim with the subject removed.
    # #6187 — nor does a board whose top rows print the same percent; see the
    # matching branch in `generate_futures_reason`.
    if "leader_change" in reasons and not leader_is_ladder_rung and _lead_visible:
        if leader_name and leader_probability is not None:
            return f"New favorite: {leader_name} ({_display_pct(leader_probability, rendered_leader_percent)}%)"
        return "New favorite"

    # (No `source_divergence` branch — see `generate_futures_reason`.)

    if (
        "major_movement_24h" in reasons
        and top_mover_name
        and top_mover_change is not None
        and _mover_sayable
    ):
        direction = "up" if top_mover_change > 0 else "down"
        if _weak_outcome_label(top_mover_name) and market_name:
            return f"{_short_market_name(market_name)} odds {direction} {_points(top_mover_change)}"
        return f"{_side_label(top_mover_name)} {direction} {_points(top_mover_change)} today"

    # (No `rank_shakeup` branch — see `generate_futures_reason`.)

    if (
        "moderate_movement_24h" in reasons
        and top_mover_name
        and top_mover_change is not None
        and _mover_sayable
    ):
        direction = "up" if top_mover_change > 0 else "down"
        if _weak_outcome_label(top_mover_name) and market_name:
            return f"{_short_market_name(market_name)} odds {direction} {_points(top_mover_change)}"
        return f"{_side_label(top_mover_name)} {direction} {_points(top_mover_change)} today"

    if "resolving_soon_7d" in reasons:
        if leader_name and leader_probability is not None:
            if _no_leader_subject and market_name:
                return f"{_short_market_name(market_name)} resolving soon"
            clause = leader_standing_clause(
                leader_name,
                _display_pct(leader_probability, rendered_leader_percent),
                verb=_verb,
                lead_is_visible=_lead_visible,
            )
            return f"Resolving soon: {clause}"
        return "Resolving soon"

    if "resolving_soon_30d" in reasons:
        if leader_name and leader_probability is not None:
            if _no_leader_subject and market_name:
                return f"{_short_market_name(market_name)} resolves within a month"
            # #6187 — the one leader headline that carries the verb WITHOUT a
            # percent, so dropping the verb alone would leave "MOUZ; resolves
            # within a month", a subject with nothing said about it. The tie
            # form states the standing the reader can check instead.
            if _lead_visible:
                return f"{leader_name} {_verb}; resolves within a month"
            pct = _display_pct(leader_probability, rendered_leader_percent)
            return f"{leader_name} at {pct}%; resolves within a month"
        return RESOLVING_WITHIN_MONTH_HEADLINE

    # Lifetime move — same demotion and same dating rule as
    # `generate_futures_reason`; see the comment there. #6219 gates this block
    # for the same reason and in the same place: this generator produced the
    # string the reader actually read on the NRL card ("Canberra Raiders down
    # 46.5 points since Feb 19"), so a fix that reached only the `reason` slot
    # would have left the defect on screen.
    since_opening = format_baseline_date(top_surprise_opened_at, now=now)
    if (
        since_opening
        and top_surprise_name
        and _is_printable_move(top_surprise_change)
        and _surprise_sayable
        and ("major_surprise" in reasons or "moderate_surprise" in reasons)
    ):
        direction = "up" if top_surprise_change > 0 else "down"
        if _weak_outcome_label(top_surprise_name) and market_name:
            return f"{_short_market_name(market_name)} shifted since {since_opening}"
        subject = _side_label(top_surprise_name)
        move = f"{direction} {_points(top_surprise_change)} since {since_opening}"
        # #6482's rule, arriving on the multi-outcome board. That ship stated
        # clause (a) of #4066 — "'from opening' is context, never the headline
        # reason" — and fixed the BINARY card only, because a binary card's
        # reader-visible slot is `context_summary` and its headline could be
        # left byte-identical. Here the headline IS the slot the reader reads
        # (`generate_futures_context_summary` returns it verbatim once the
        # leader's name already appears in it), so the same defect needed the
        # same clause in a different place. Measured on production 2026-09-16,
        # v4612, in the SERVED feed: 'Democratic Party up 15 points since
        # Feb 19' over a Senate board printing 55/45, and '5 or more up 40
        # points since Feb 19' over one printing 52/26 — neither number said in
        # the caption above it. (Those are the board's own percents. The admin
        # trace reports the pre-normalization 0.545/0.57 for the same two rows,
        # and quoting THOSE here would restate #6181 in a comment: the percent
        # this branch prints is the one `_display_pct` takes from the card.)
        # Feb 19 is the bulk `opening_captured_at` date covering 57,122
        # outcomes — the day we first saw the row, not a day anything happened
        # to it.
        #
        # Past the horizon the standing goes first and the move keeps its date
        # behind it; inside it nothing changes and the move still leads. The
        # move is never dropped, exactly as in `compose_binary_card_copy`.
        #
        # The standing is composed through exactly the call the leader terminal
        # at the bottom of this generator makes, so this rung inherits both of
        # that terminal's refusals rather than restating them. They work
        # differently and the difference is load-bearing: `_no_leader_subject`
        # (#4640) REFUSES — a cumulative ladder rung has no favorite to be, so
        # the card keeps today's string rather than gaining a false one — while
        # `_lead_visible` (#6187) merely drops the comparative, so a tied board
        # says "5 or more at 52%" and never "leads at". Neither can be lost to
        # a hand-copied f-string here, which is why there isn't one.
        if _baseline_is_older_than_news(top_surprise_opened_at, now=now) and (
            leader_name
            and leader_probability is not None
            and not _no_leader_subject
        ):
            standing = leader_standing_clause(
                leader_name,
                _display_pct(leader_probability, rendered_leader_percent),
                verb=_verb,
                lead_is_visible=_lead_visible,
            )
            # The mover is usually the leader itself (both live specimens), and
            # then repeating the name would read "Democratic Party leads at
            # 55%, Democratic Party up 15 points". Elided on a normalized
            # compare because `_side_label` may have suffixed the subject.
            if subject.strip().lower() == leader_name.strip().lower():
                return f"{standing}, {move}"
            return f"{standing}, {subject} {move}"
        return f"{subject} {move}"

    # (No `multi_source` branch — see `generate_futures_reason`. "Tracked by 2
    # sources" held the HEADLINE slot on four of the first twenty cards the
    # morning this shipped.)

    if leader_name and leader_probability is not None:
        if _no_leader_subject and market_name:
            # #4056 — this rung returned the title, chopped, with nothing appended:
            # the question echoed back as its own answer. The card already prints the
            # title one line up, so the headline slot said nothing twice. Every OTHER
            # `_short_market_name` call in this module uses the title as the SUBJECT
            # of a clause that adds a fact ("… odds up 5 points", "… resolving soon");
            # this one had no clause. Falls through to the empty terminal below, and
            # from there to `primary_reason` in `routes/feed.py`.
            #
            # #6470 — unless the venue's title named a deadline, in which case the
            # clause this rung was missing exists after all. Still empty for
            # every name that carried no "by <blank>".
            return _deadline
        return leader_standing_clause(
            leader_name,
            _display_pct(leader_probability, rendered_leader_percent),
            verb=_verb,
            lead_is_visible=_lead_visible,
        )

    return ""


def generate_futures_context_summary(
    *,
    headline: Optional[str],
    highlight_reasons: list[str],
    market_name: Optional[str] = None,
    leader_name: Optional[str] = None,
    leader_probability: Optional[float] = None,
    rendered_leader_percent: Optional[int] = None,
    # #6187: see `generate_futures_reason`. Defaults None -> comparative kept.
    rendered_runner_up_percent: Optional[int] = None,
    # #4700: see `generate_futures_reason`. Defaults False -> singular verbatim.
    leader_is_team: bool = False,
    # #6550: see `generate_futures_reason`. Defaults None -> #4700's rule.
    leader_team_name: Optional[str] = None,
    # #4640: see `generate_futures_reason`. Defaults False -> copy unchanged.
    leader_is_ladder_rung: bool = False,
    # #6470: the preposition the display rule elided from the title
    # (`market_display_name.elided_trailing_preposition`). Defaults None so an
    # uninformed caller stays silent exactly as before — see
    # `leader_deadline_clause`.
    leader_deadline_preposition: Optional[str] = None,
    source_count: int = 1,
    affirmative_probability: Optional[float] = None,
    rendered_affirmative_percent: Optional[int] = None,
    top_mover_change: Optional[float] = None,
    top_surprise_change: Optional[float] = None,
    top_surprise_opened_at: Optional[datetime] = None,
    now: Optional[datetime] = None,
) -> str:
    """Generate short visible context copy for Discover cards.

    This is intentionally tighter than the full reason and avoids using long
    LLM hook paragraphs as the on-card snippet. Full hooks remain available for
    "See more" expansion.
    """
    headline = (headline or "").strip()
    reasons = set(highlight_reasons)
    # #4700: resolved once, above every branch (see `generate_futures_reason`).
    _verb = leader_agreement_verb(leader_name, leader_is_team, leader_team_name)
    # #6187: likewise — see `generate_futures_reason`.
    _lead_visible = lead_is_printable(
        rendered_leader_percent, rendered_runner_up_percent
    )

    # This is the string the web card prints under its title, so it is where the
    # binary-as-race defect was actually READ ("China invade Taiwan by end of
    # 2026 leads at 4%", production 2026-09-08). It composes from the same place
    # as the headline it sits beneath.
    if affirmative_probability is not None:
        return compose_binary_card_copy(
            market_name=market_name,
            highlight_reasons=highlight_reasons,
            affirmative_probability=affirmative_probability,
            rendered_affirmative_percent=rendered_affirmative_percent,
            top_mover_change=top_mover_change,
            top_surprise_change=top_surprise_change,
            top_surprise_opened_at=top_surprise_opened_at,
            deadline_label=deadline_level_label(
                leader_name,
                leader_is_ladder_rung=leader_is_ladder_rung,
                deadline_preposition=leader_deadline_preposition,
            ),
            now=now,
        ).context_summary

    # Same single point as `generate_futures_reason`, and before the closure
    # below captures it.
    leader_name = _answering_side_label(leader_name, market_name)

    if "stale_past_resolution" in reasons:
        return ""

    def leader_clause() -> str:
        if _copy_repeats_market_name(leader_name, market_name):
            return ""
        # #4640 — the single gate for this generator: every leader sentence it
        # can emit is composed here, so a ladder rung is refused once. #6187
        # rides the same gate: one place to drop the comparative, and the
        # "resolves within a week/month" suffixes below inherit it.
        #
        # #6470 rides it too, on the far side: where the label is unnameable but
        # the venue's title elided a "by", the level clause replaces the silence
        # and the suffixes append to it ("60% chance by December 31, 2026;
        # resolves within a month"). Every other unnameable leader is as empty
        # as it was.
        if _leader_is_unnameable(leader_name, leader_is_ladder_rung):
            return _deadline_fallback(
                leader_name,
                leader_probability,
                rendered_leader_percent,
                leader_is_ladder_rung=leader_is_ladder_rung,
                leader_deadline_preposition=leader_deadline_preposition,
            )
        if leader_name and leader_probability is not None:
            return leader_standing_clause(
                leader_name,
                _display_pct(leader_probability, rendered_leader_percent),
                verb=_verb,
                lead_is_visible=_lead_visible,
            )
        return ""

    leader = leader_clause()

    if "resolving_soon_7d" in reasons:
        return (
            f"{leader}; resolves within a week"
            if leader
            else "Resolves within a week"
        )
    if (
        "resolving_soon_30d" in reasons
        and headline == RESOLVING_WITHIN_MONTH_HEADLINE
    ):
        return (
            f"{leader}; resolves within a month"
            if leader
            else "Resolves within a month"
        )
    # (No `multi_source` clause. The headline it keyed on — `startswith("Tracked
    # by")` — is no longer emitted, and " across N sources" is the same inventory
    # count that D91 puts in the source mark by name.)

    if headline:
        if _copy_repeats_market_name(headline, market_name):
            # (No divergence / source-count rungs here either: when the headline
            # only restates the question, the honest answer is the leader or the
            # resolution window, never a number about our own rows.)
            if "resolving_soon_7d" in reasons:
                return "Resolves within a week"
            if "resolving_soon_30d" in reasons:
                return "Resolves within a month"
            if leader:
                return leader
            # #5329 — the last rung, and it has to be NON-EMPTY. Returning ""
            # here does not suppress the echo, it promotes it: the caption
            # chain is `firstMeaningful([context_summary, headline, reason,
            # hook_description])` on both clients, so an empty context summary
            # hands the same restated question back through the next link.
            #
            # Reached when the outcome label was too weak to name (so the
            # headline used the market as context) AND there is no leader
            # clause to swap in, because the leader is that same weak label.
            # One page-one bundle row in eighteen: the reader saw "Russia x
            # Ukraine ceasefire agreement by...?" and then, directly beneath
            # it, "Russia x Ukraine ceasefire agreement by... shifted since
            # May 14".
            #
            # Composed from the timestamp, not sliced off the headline: the
            # name in there has already been through `_short_market_name`, so
            # a string strip leaves its ellipsis behind.
            since_opening = format_baseline_date(top_surprise_opened_at, now=now)
            if (
                since_opening
                and _is_printable_move(top_surprise_change)
                and ("major_surprise" in reasons or "moderate_surprise" in reasons)
            ):
                return f"Shifted since {since_opening}"
        if leader and len(headline) < 80:
            lower_headline = headline.lower()
            lower_leader = leader_name.lower() if leader_name else ""
            if lower_leader and lower_leader not in lower_headline:
                return f"{headline}; {leader}"
        return headline

    return leader
