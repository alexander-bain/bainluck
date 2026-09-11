"""
Template-based reason generation for the unified feed.

Generates 1-line explanations for why a feed item is interesting.
Returns empty string when the card UI already tells the story — avoids
repeating scores, odds, or team names visible on the card.
"""

import re
from datetime import datetime, timezone
from typing import NamedTuple, Optional

from app.utils.graded_card import rendered_percent
from app.utils.highlights import underdog_leads
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
    now: Optional[datetime] = None,
) -> BinaryCardCopy:
    """Compose a yes/no card's three strings, freshest real signal first.

    The order below IS the editorial rule: what moved, then what is about to
    resolve, then — only if nothing else is true — a dated lifetime move, then
    the bare probability. A lifetime move never outranks a live one and never
    appears undated.
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
    if since and top_surprise_change is not None:
        direction = "Up" if top_surprise_change > 0 else "Down"
        return composed(
            f"{direction} {_points(top_surprise_change)} since {since}",
            f"{direction} {_points(top_surprise_change)} since {since} — now {answer}",
        )

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
    return BinaryCardCopy("", "", "")


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
) -> str:
    """
    Generate a one-line explanation for why an event is interesting.

    Returns a human-readable reason string for the feed card, or empty
    string when the card's visual elements (score, odds bar, badges)
    already convey the information.
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
                if home_score > away_score:
                    winner_opening_prob = opening_home_prob
                else:
                    winner_opening_prob = 1 - opening_home_prob
                pct = _display_pct(winner_opening_prob)
                return f"Won as {pct}% underdog"
            return "Upset result"
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
        if (
            "favorite_switched" in reasons
            and underdog_leads(opening_home_prob, home_score, away_score) is True
        ):
            underdog = away_team if opening_home_prob > 0.5 else home_team
            return f"{underdog} leading as underdog"

        if "very_close" in reasons:
            return "Virtually even"

        if "close_matchup" in reasons:
            return "Tight game"

        if "major_prob_swing" in reasons:
            if opening_home_prob is not None and home_probability is not None:
                change = home_probability - opening_home_prob
                direction_team = home_team if change > 0 else away_team
                pct_change = abs(round(change * 100))
                return f"{direction_team} odds shifted {pct_change}%"
            return ""

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

#: Plural team nicknames that do not end in "s". `Sox` is the whole set in the
#: leagues we carry (Red Sox, White Sox).
_PLURAL_TEAM_NICKNAMES_WITHOUT_S = ("sox",)


def leader_agreement_verb(
    leader_name: Optional[str], leader_is_team: bool = False
) -> str:
    """"lead" or "leads" for `{leader_name} <verb> at {pct}%` (#4700).

    Returns the singular unless the caller has PROVEN the subject is a team and
    the team's nickname is plural. See the block comment above for why spelling
    alone is not consulted.
    """
    if not leader_is_team or not leader_name:
        return "leads"
    tokens = leader_name.split()
    if not tokens:
        return "leads"
    nickname = tokens[-1].lower()
    if nickname in _PLURAL_TEAM_NICKNAMES_WITHOUT_S:
        return "lead"
    # "ss" guards a hypothetical singular nickname; "s" alone is the plural.
    if nickname.endswith("s") and not nickname.endswith("ss"):
        return "lead"
    return "leads"


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
    # #4700: proven team-ness of `leader_name`, for subject-verb agreement.
    # Defaults False so an uninformed caller keeps the singular verbatim.
    leader_is_team: bool = False,
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
    _verb = leader_agreement_verb(leader_name, leader_is_team)

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
    if "leader_change" in reasons:
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
        if top_mover_name and top_mover_change is not None:
            if _weak_outcome_label(top_mover_name):
                return f"Big odds movement in {market_name}"
            direction = "up" if top_mover_change > 0 else "down"
            pct = _point_change(top_mover_change)
            return f"{_side_label(top_mover_name)} moved {direction} {pct} points today in {market_name}"
        return f"Big odds movement in {market_name}"

    # (No `rank_shakeup` branch. "Multiple ranking changes" described the ordering
    # of our own leaderboard, and the honest replacement is not available here:
    # `rank_shakeup` fires on two rank changes BELOW the top, and `leader_change`
    # — the one development a reader could restate — is its own branch above. So
    # the card falls through to a movement or leader sentence it can support.)

    # Moderate movement
    if "moderate_movement_24h" in reasons:
        if top_mover_name and top_mover_change is not None:
            if _weak_outcome_label(top_mover_name):
                return f"Odds shifting in {market_name}"
            direction = "up" if top_mover_change > 0 else "down"
            pct = _point_change(top_mover_change)
            return f"{_side_label(top_mover_name)} odds shifted {direction} {pct} points today in {market_name}"
        return f"Odds shifting in {market_name}"

    # Resolving soon
    if "resolving_soon_7d" in reasons:
        if leader_name and leader_probability is not None:
            if _weak_outcome_label(leader_name):
                return f"{market_name} resolving within a week"
            pct = _display_pct(leader_probability, rendered_leader_percent)
            return f"{market_name} resolving soon, {leader_name} {_verb} at {pct}%"
        return f"{market_name} resolving within a week"
    if "resolving_soon_30d" in reasons:
        if leader_name and leader_probability is not None:
            if _weak_outcome_label(leader_name):
                return f"{market_name} resolves within a month"
            pct = _display_pct(leader_probability, rendered_leader_percent)
            return (
                f"{market_name} resolves within a month, "
                f"{leader_name} {_verb} at {pct}%"
            )
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
    since_opening = format_baseline_date(top_surprise_opened_at, now=now)
    if (
        since_opening
        and top_surprise_change is not None
        and ("major_surprise" in reasons or "moderate_surprise" in reasons)
    ):
        if not _weak_outcome_label(top_surprise_name):
            direction = "up" if top_surprise_change > 0 else "down"
            pct = _point_change(top_surprise_change)
            return (
                f"{_side_label(top_surprise_name)} is {direction} {pct} points "
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
        if _weak_outcome_label(leader_name):
            return ""
        pct = _display_pct(leader_probability, rendered_leader_percent)
        return f"{leader_name} ({pct}%) {_verb} {market_name}"

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
    # #4700: proven team-ness of `leader_name`, for subject-verb agreement.
    # Defaults False so an uninformed caller keeps the singular verbatim.
    leader_is_team: bool = False,
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
    _verb = leader_agreement_verb(leader_name, leader_is_team)

    if affirmative_probability is not None:
        return compose_binary_card_copy(
            market_name=market_name,
            highlight_reasons=highlight_reasons,
            affirmative_probability=affirmative_probability,
            rendered_affirmative_percent=rendered_affirmative_percent,
            top_mover_change=top_mover_change,
            top_surprise_change=top_surprise_change,
            top_surprise_opened_at=top_surprise_opened_at,
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

    if "leader_change" in reasons:
        if leader_name and leader_probability is not None:
            return f"New favorite: {leader_name} ({_display_pct(leader_probability, rendered_leader_percent)}%)"
        return "New favorite"

    # (No `source_divergence` branch — see `generate_futures_reason`.)

    if (
        "major_movement_24h" in reasons
        and top_mover_name
        and top_mover_change is not None
    ):
        direction = "up" if top_mover_change > 0 else "down"
        if _weak_outcome_label(top_mover_name) and market_name:
            return f"{_short_market_name(market_name)} odds {direction} {_point_change(top_mover_change)} points"
        return f"{_side_label(top_mover_name)} {direction} {_point_change(top_mover_change)} points today"

    # (No `rank_shakeup` branch — see `generate_futures_reason`.)

    if (
        "moderate_movement_24h" in reasons
        and top_mover_name
        and top_mover_change is not None
    ):
        direction = "up" if top_mover_change > 0 else "down"
        if _weak_outcome_label(top_mover_name) and market_name:
            return f"{_short_market_name(market_name)} odds {direction} {_point_change(top_mover_change)} points"
        return f"{_side_label(top_mover_name)} {direction} {_point_change(top_mover_change)} points today"

    if "resolving_soon_7d" in reasons:
        if leader_name and leader_probability is not None:
            if _weak_outcome_label(leader_name) and market_name:
                return f"{_short_market_name(market_name)} resolving soon"
            return f"Resolving soon: {leader_name} {_verb} at {_display_pct(leader_probability, rendered_leader_percent)}%"
        return "Resolving soon"

    if "resolving_soon_30d" in reasons:
        if leader_name and leader_probability is not None:
            if _weak_outcome_label(leader_name) and market_name:
                return f"{_short_market_name(market_name)} resolves within a month"
            return f"{leader_name} {_verb}; resolves within a month"
        return RESOLVING_WITHIN_MONTH_HEADLINE

    # Lifetime move — same demotion and same dating rule as
    # `generate_futures_reason`; see the comment there.
    since_opening = format_baseline_date(top_surprise_opened_at, now=now)
    if (
        since_opening
        and top_surprise_name
        and top_surprise_change is not None
        and ("major_surprise" in reasons or "moderate_surprise" in reasons)
    ):
        direction = "up" if top_surprise_change > 0 else "down"
        if _weak_outcome_label(top_surprise_name) and market_name:
            return f"{_short_market_name(market_name)} shifted since {since_opening}"
        return (
            f"{_side_label(top_surprise_name)} {direction} "
            f"{_point_change(top_surprise_change)} points since {since_opening}"
        )

    # (No `multi_source` branch — see `generate_futures_reason`. "Tracked by 2
    # sources" held the HEADLINE slot on four of the first twenty cards the
    # morning this shipped.)

    if leader_name and leader_probability is not None:
        if _weak_outcome_label(leader_name) and market_name:
            # #4056 — this rung returned the title, chopped, with nothing appended:
            # the question echoed back as its own answer. The card already prints the
            # title one line up, so the headline slot said nothing twice. Every OTHER
            # `_short_market_name` call in this module uses the title as the SUBJECT
            # of a clause that adds a fact ("… odds up 5 points", "… resolving soon");
            # this one had no clause. Falls through to the empty terminal below, and
            # from there to `primary_reason` in `routes/feed.py`.
            return ""
        return f"{leader_name} {_verb} at {_display_pct(leader_probability, rendered_leader_percent)}%"

    return ""


def generate_futures_context_summary(
    *,
    headline: Optional[str],
    highlight_reasons: list[str],
    market_name: Optional[str] = None,
    leader_name: Optional[str] = None,
    leader_probability: Optional[float] = None,
    rendered_leader_percent: Optional[int] = None,
    # #4700: see `generate_futures_reason`. Defaults False -> singular verbatim.
    leader_is_team: bool = False,
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
    _verb = leader_agreement_verb(leader_name, leader_is_team)

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
        if _weak_outcome_label(leader_name):
            return ""
        if leader_name and leader_probability is not None:
            return f"{leader_name} {_verb} at {_display_pct(leader_probability, rendered_leader_percent)}%"
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
        if leader and len(headline) < 80:
            lower_headline = headline.lower()
            lower_leader = leader_name.lower() if leader_name else ""
            if lower_leader and lower_leader not in lower_headline:
                return f"{headline}; {leader}"
        return headline

    return leader
