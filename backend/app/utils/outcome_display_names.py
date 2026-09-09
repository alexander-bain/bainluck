"""Reader-facing display names for outcome rows whose stored name is a venue slug.

#4151 — Discover page one printed `claude-fable-5.1-max leads at 68%` one row
under `Claude leads at 62%`, inside the same "Which AI model comes out on top?"
bundle. A reader cannot tell whether those name the same thing, which is exactly
the question the card is asking them to answer.

🔴 THERE IS NOTHING TO INGEST. Checked against Kalshi's own API (standing notice
26): for `KXTOPMODEL-26SEP30-CLF51M` every human-facing field the venue serves is
the slug — `yes_sub_title`, `no_sub_title`, `custom_strike: {"Model": …}`, and
`rules_primary` ("If claude-fable-5.1-max is the top-ranked AI model on Sep 30,
2026 …"). Kalshi names the outcome by the model id because LMArena, its
resolution source, does. Our stored row matches the venue exactly. So this is
not an ingest bug and not a mapping miss: the display name has to be ours.

WHY THERE IS NO SLUG-TO-NAME TABLE
----------------------------------
A lookup table is the #4135 defect this issue cites — an unmapped key reaching
the screen — and the venue adds models monthly, so the table would be stale by
design. What ships instead is a *typographic* normalisation of the venue's own
token: it re-typesets `claude-fable-5.1-max` as `Claude Fable 5.1 Max` and can
therefore never assert anything the venue did not.

THE PREDICATE IS TWO INDEPENDENT LOCKS, AND ONE IS NOT ENOUGH
-------------------------------------------------------------
Measured over every hyphen- or underscore-bearing outcome name in production
(n=288,382 rows, 2026-09-09):

    slug-shaped by SHAPE alone                        468
      ... of those, on a question about AI models     451   <- rewritten
      ... of those, on any other question              17   <- left alone
    on an AI-model question but not slug-shaped         0

Shape alone is nowhere near safe. 920 of the first 1,000 hyphenated names are
`quantity` bucket labels — `120-139`, `$250-$255`, `17.5-18m`, `350k-400k`,
`660-670b`, `7th-9th` — and re-typesetting those produces nonsense. Worse, the
17 in the second row above are names whose lowercase spelling IS their identity:

    blink-182     the band            'Who will release a new album in 2026?'
    estar_backs   an esports team     'Amaru Gaming vs. estar_backs'
    ex-1win       an esports team     'ex-1win vs. Lazer Cats'
    korekore_ch   a Kick streamer     'Who will be the Most Watched Kick Streamer…'

`estar_backs` and `muse-spark` are structurally identical, so no shape rule can
tell a handle from a model id. The market's own QUESTION can, and it is the same
signal a reader uses. It also generalises across venues where a series allowlist
could not: these markets arrive from Kalshi (`KXTOPMODEL`) *and* Polymarket,
whose event ids are opaque numbers that change every week.

Both locks must hold. The failure direction is deliberately one-way: a market
phrased in some way this module does not recognise keeps its slug (status quo,
no regression), and a new *model* inside a question it does recognise is
typeset correctly — which is the case that actually churns.
"""

import re

# A venue slug: starts with a letter, all lowercase, no spaces, and joined by at
# least one separator. Leading-letter is load-bearing — it is what excludes
# `9-1-1` (the ABC show), `7th-9th` and `120-139`, all of which are real outcome
# names on live markets.
#
# 🔴 THE SEPARATOR CLASS AND THE TOKEN CLASS MUST STAY DISJOINT. This first read
# `(?:[-_.][a-z0-9.]+)+`, with `.` in BOTH halves, so a `.` could be consumed as
# either a separator or a token character and the engine had exponentially many
# ways to split the same string. CodeQL `py/redos` caught it as two high-severity
# alerts on PR #4230; measured, `a-` + n×`..` grew ~8x per two repetitions (31
# chars = 10ms, and 27+ chars was already unbounded in practice) on a pattern
# that runs inside `GET /api/feed`. Dropping `.` from the token class makes every
# separator unambiguous and the match linear: 403 chars now costs 2µs.
# A version point still survives, because `.` is a separator and the digits
# around it are their own tokens — `claude-fable-5.1-max` and `gpt-4.1` match
# exactly as before. The only value whose classification changed in the whole
# real population is `a-.b` (two adjacent separators), which is not an outcome
# name and now keeps its slug — the safe direction.
_SLUG_RE = re.compile(r"^[a-z][a-z0-9]*(?:[-_.][a-z0-9]+)+$")

# The question whose answers are model identifiers. Kept deliberately narrow:
# widening it is a decision to re-typeset some other market's answers, and that
# is the direction that breaks names like `blink-182`.
_MODEL_QUESTION_RE = re.compile(r"\b(?:ai\s+models?|llms?)\b", re.IGNORECASE)

# Casing hints, NOT a name table. An initialism missing from this set degrades
# to Title Case (`Glm 4.6`) — readable, and still not a raw slug — so a stale
# entry here can never put a venue token back on the screen. That one-way
# failure is the whole reason this is a casing set and not a slug→name map.
_INITIALISMS = {"gpt", "glm"}


def _is_model_question(market_name: str | None) -> bool:
    return bool(market_name) and bool(_MODEL_QUESTION_RE.search(market_name))


def _prettify_slug(slug: str) -> str:
    """Re-typeset a venue slug as a name a person would say out loud.

    🔴 A SEPARATOR BETWEEN TWO DIGITS IS A VERSION POINT, NOT A WORD BREAK.
    Splitting on every hyphen turns `claude-opus-4-6` into "Claude Opus 4 6",
    which reads worse than the slug did — the `4-6` is one version, and the
    build id in `claude-opus-4-5-20251101-thinking-32k` is one token too. So a
    separator becomes a space only where a letter sits on one side of it.
    """
    # Split only at separators adjacent to a letter; `(?<=[a-z])` / `(?=[a-z])`
    # keep `4-6` and `5.0-0110` intact.
    words = re.split(r"(?<=[a-z0-9])[-_](?=[a-z])|(?<=[a-z])[-_](?=[a-z0-9])", slug)
    out = []
    for word in words:
        if word.lower() in _INITIALISMS:
            out.append(word.upper())
        elif word[:1].isalpha():
            # Only the first character — `qwen3.5` must not become `Qwen3.5`'s
            # neighbours' problem, and `.title()` would give `Qwen3.5` -> `Qwen3.5`
            # but `k2.5` -> `K2.5` only by accident. Capitalising position 0 is
            # the whole intent.
            out.append(word[0].upper() + word[1:])
        else:
            out.append(word)
    return " ".join(out)


def display_outcome_name(outcome_name: str | None, market_name: str | None) -> str:
    """The name a reader should see for one outcome row.

    Returns `outcome_name` unchanged unless BOTH locks hold. Never mutates.
    """
    if not outcome_name or not _is_model_question(market_name):
        return outcome_name or ""
    if not _SLUG_RE.match(outcome_name):
        return outcome_name
    return _prettify_slug(outcome_name)


def display_outcome_names(
    top_outcomes: list[dict],
    market_name: str | None,
) -> list[dict]:
    """Apply `display_outcome_name` across a list of outcome dicts.

    Returns a NEW list; the input is not mutated.
    """
    if not top_outcomes or not _is_model_question(market_name):
        return top_outcomes
    return [
        {**o, "name": display_outcome_name(o.get("name"), market_name)}
        for o in top_outcomes
    ]
