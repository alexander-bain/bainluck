"""C1 regression corpus — sport mis-tag at mint (queue 401 census, queue 402 fix F3).

The census of 49,423 open futures markets (2026-08-24) found ~49 markets whose
``llm_sport_category`` is contradicted by the market's own title. Every one of
them is the same mechanism: ``categorize_by_rules`` ran an ordered list of
regexes over free text and took the FIRST match, with no scoring and no negative
evidence. One ambiguous word decided the sport:

    "New Zealand Darts **Masters**"        -> golf
    "**World Series** of Darts"            -> baseball
    "**Thunder** Bay, ON Mayoral Election" -> basketball
    "The **Magic** Faraway Tree"           -> basketball
    "The **Open** Weights ... letter"      -> golf

This file is the red-first gate for F3. The MISTAG cases below all FAILED before
the positive-evidence rewrite; the CONTROL cases all PASSED before it and must
keep passing, which is the harder half — ``\\bdarts?\\b`` also matches the NFL
quarterback **Jaxson Dart** and the tennis player **Harriet Dart**, so a naive
"raise darts above golf" fix trades one mis-tag class for another.

Specimen ids are real production rows; they are kept in the ids so a future
reader can re-pull the row. See ``.claude/handoff/REPORT-Q-CONTAMINATION-2026-08-24.md``.
"""

import pytest

from app.utils.futures_categorization import categorize_by_rules


# ---------------------------------------------------------------------------
# MIS-TAGS — each of these was wrong in production on 2026-08-24.
# (market_name, wrong_category_before, expected_after)
# `expected_after` of None means "no confident rule-based answer" — the LLM
# fallback owns it. That is a correct outcome: a wrong sport is worse than no
# sport, because the wrong one is persisted into the canonical key.
# ---------------------------------------------------------------------------
C1_MISTAGS = [
    # --- "World Series" of DARTS, filed under baseball:MLB:championship:2026 ---
    # 13 sibling rows in production; 3 representatives here.
    ("World Series of Darts: Jonny Clayton vs Ben Robb", "baseball", "darts"),      # 59304735
    ("World Series of Darts: Gerwyn Price vs Simon Whitlock", "baseball", "darts"),  # 59304742
    ("World Series of Darts: Gerwyn Price vs James Wade", "baseball", "darts"),      # 59428372

    # --- "Masters" pulling everything into golf ---
    ("New Zealand Darts Masters: Winner", "golf", "darts"),                          # 58416367
    ("Most kills on a single map at Masters London 2026?", "golf", "esports"),       # 35418786
    ('"Masters of the Universe" Opening Weekend Box Office', "golf", "entertainment"),  # 31169677

    # --- "The Open" pulling an AI-policy question into golf ---
    # `tech` already had a pattern for "Anthropic"; it simply lost the race to
    # golf's "the Open". Scoring alone is enough here.
    ("Will Anthropic sign the Open Weights and American AI Leadership letter?",
     "golf", "tech"),                                                                # 58015857

    # --- Ambiguous league/tournament words beating the real domain ---
    # Both of these were found BY this corpus while it was being written: they
    # were drafted as controls, and failed red alongside the census specimens.
    ("Premier League Darts: Winner", "soccer", "darts"),
    ("Magnus Carlsen to win the Chess World Cup", "soccer", "chess"),

    # --- NBA team tokens pulling politics/entertainment into basketball ---
    ("Thunder Bay, ON Mayoral Election Winner", "basketball", "politics"),           # 59520510
    ("Practical Magic 2 · Rotten Tomatoes score", "basketball", "entertainment"),  # 58728438
    ('"The Magic Faraway Tree" Rotten Tomatoes Score?', "basketball", "entertainment"),  # 59170844
    ('Will "The Magic Faraway Tree" score at least 80 on the Rotten Tomatoes Tomatometer?',
     "basketball", "entertainment"),                                                 # 59170845
    ('Will "The Magic Faraway Tree" score at least 90 on the Rotten Tomatoes Tomatometer?',
     "basketball", "entertainment"),                                                 # 59170847
]


# ---------------------------------------------------------------------------
# CONTROLS — correct in production, and the fix must not move them.
# These are the specimens a careless fix breaks. "Dart" is a surname; "Masters"
# and "The Open" really are golf most of the time; "World Series" really is
# baseball most of the time. Positive evidence has to WIN here, not just veto.
# ---------------------------------------------------------------------------
C1_CONTROLS = [
    # Row 59165075 ("Los Angeles L next governor") is a census C1 specimen whose
    # DB value is `basketball`, but `categorize_by_rules` already answers
    # `politics` for it -- so the bad value came from another writer (the LLM
    # fallback, or a pre-rules backfill), not from this function. It is a CONTROL
    # here, and the DB row needs the F2 re-key rather than F3.
    ("Los Angeles L next governor before Jan 1, 2027?", "politics"),               # 59165075

    # Real golf that must stay golf, despite sharing tokens with the mis-tags.
    ("Masters Tournament Winner", "golf"),                                           # 4
    ("The Open Winner", "golf"),                                                     # 6
    ("Husqvarna British Masters hosted by Sir Nick Faldo - Winner", "golf"),         # 59485750
    ("Husqvarna British Masters hosted by Sir Nick Faldo - Top 5 Finish", "golf"),   # 59485751
    ("PGA Championship Winner", "golf"),
    ("LIV Golf Indianapolis: Winner", "golf"),

    # Real baseball that must stay baseball.
    ("World Series Winner", "baseball"),
    ("Who will win the 2026 World Series?", "baseball"),
    ("NL Manager of the Year", "baseball"),                                          # 210

    # "Dart" the SURNAME must not become darts.
    ("Pro Football: Jaxson Dart 2026-27 Regular Season Passing Yards", "football"),  # 58835774
    ("Pro Football: Jaxson Dart 2026-27 Regular Season Rushing Touchdowns", "football"),  # 58836096
    ("Will Jaxson Dart finish as a top-5 QB in the 2026-27 NFL season?", "football"),  # 59385198
    ("US Open, Qualification WTA: Jordyn Hazelitt vs Harriet Dart", "tennis"),        # 59484290

    # Real darts that must stay darts.
    ("PDC World Darts Championship Winner", "darts"),
    ("Premier League Darts: Winner", "darts"),

    # Real basketball that must stay basketball, despite team-name tokens.
    ("Oklahoma City Thunder to win the NBA Championship", "basketball"),
    ("Orlando Magic 2026-27 Regular Season Wins", "basketball"),

    # Tennis that must stay tennis (Monte-Carlo Masters precedence, and the real
    # US Open draws that F2's shadow key will later separate by gender).
    ("Monte-Carlo Masters Winner", "tennis"),
    ("2026 Men’s US Open Winner (Tennis)", "tennis"),                            # 114159
    ("2026 Women’s US Open Winner (Tennis)", "tennis"),                          # 114160

    # Chess — the 20 false positives the census subtracted from its 69 regex hits.
    # They were never mis-tagged; they must not start being mis-tagged now.
    ("World Chess Championship Winner", "chess"),
    ("Magnus Carlsen to win the Chess World Cup", "chess"),
]


# ---------------------------------------------------------------------------
# KNOWN UNREACHABLE — a census specimen that title-only rules cannot fix.
#
# 38277227 "Asia Masters 2026 Winner" is snooker. Its title carries no snooker
# token, so the only signal available is "Masters", and it is character-for-
# character the same signal that makes "Masters Tournament Winner" correctly
# golf. No scoring rule can separate them; a rule that demoted a lone ambiguous
# match to None would take the real Masters down with it.
#
# Recorded rather than deleted, because a corpus that quietly drops the specimen
# it cannot fix reports 100% and hides the gap. This one is owed to F2 (league /
# level discriminators) or the LLM fallback, not to F3.
# ---------------------------------------------------------------------------
C1_UNREACHABLE_BY_RULES = [
    ("Asia Masters 2026 Winner", "golf"),  # 38277227, snooker
]


@pytest.mark.parametrize("name,still_returns", C1_UNREACHABLE_BY_RULES)
def test_c1_unreachable_specimen_is_documented(name, still_returns):
    """Pins the known gap so it is visible, and fails loudly if it ever changes.

    If this test starts failing because the value moved, that is good news --
    update the corpus. It exists so the gap cannot be forgotten.
    """
    assert categorize_by_rules(name) == still_returns


@pytest.mark.parametrize("name,wrong_before,expected", C1_MISTAGS)
def test_c1_mistag_is_not_the_wrong_sport(name, wrong_before, expected):
    """The headline assertion: the market no longer lands in the wrong sport.

    This is deliberately separate from the exact-value assertion below. What
    corrupts the canonical key, the feed and every league page is the WRONG
    value being persisted -- ``baseball:MLB:championship:2026`` on a darts
    match. Returning None is a full fix for that harm; returning the right
    sport is better, and is asserted separately so a partial fix is visible
    as a partial fix rather than a failure.
    """
    got = categorize_by_rules(name)
    assert got != wrong_before, (
        f"{name!r} still classifies as {wrong_before!r} -- the C1 mis-tag is live"
    )


@pytest.mark.parametrize(
    "name,expected",
    [(n, e) for n, _w, e in C1_MISTAGS if e is not None],
)
def test_c1_mistag_reaches_the_right_sport(name, expected):
    """The stronger assertion: positive evidence found the RIGHT sport."""
    assert categorize_by_rules(name) == expected


@pytest.mark.parametrize("name,expected", C1_CONTROLS)
def test_c1_controls_do_not_regress(name, expected):
    """Correct classifications that a careless F3 fix would break."""
    assert categorize_by_rules(name) == expected, (
        f"{name!r} regressed -- the fix over-corrected"
    )
