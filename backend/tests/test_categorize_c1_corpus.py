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


# ---------------------------------------------------------------------------
# ROUND 2 — the four findings of the C-F3-CATEGORIZE-1 BLOCK.
#
# The first round of this fix shipped with a documented plural-only invariant, a
# scoring rewrite meant to retire first-match-wins, and a category-blind
# ambiguity set. The cert found that all three claims were false ON THE SHIPPING
# PATH, and it found them with specimens, which is why they are specimens here.
#
# Each block below fails on the parent AND on the first-round head. A guard that
# only fails on the parent would not have caught this round's defects.
# ---------------------------------------------------------------------------

# Every symbol this round introduces is imported INSIDE the test that needs it,
# never at module scope. The reason is the red-first requirement: a module-level
# import of `sport_evidence_breakdown` makes this whole file un-collectable
# against the parent and against the first-round head, and pytest then exits 2 --
# a story about the harness, not a result (gotcha #54). Kept function-local, the
# specimen guards below run on all three trees and FAIL on two of them, which is
# what a red-first receipt has to mean.


# --- Finding 1: singular "Dart" is a surname, not a sport -------------------

# The first round put `\bdarts\b` (plural) on `_STRONG_EVIDENCE_PATTERNS` and
# wrote a comment saying singular "Dart" must not reach darts -- while leaving
# `\bdarts?\b` on SPORT_PATTERNS, which is the list the scorer actually reads.
# Both specimens scored `darts` 3 and won.
F3_SINGULAR_DART_SPECIMENS = [
    # (name, category that must NOT be returned)
    ("Will Jaxson Dart be the first overall pick?", "darts"),
    ("Will Harriet Dart win a Grand Slam?", "darts"),
    ("Jaxson Dart 2026 Passing Yards Leader", "darts"),
    ("Harriet Dart vs Emma Raducanu", "darts"),
]


@pytest.mark.parametrize("name,forbidden", F3_SINGULAR_DART_SPECIMENS)
def test_f3_singular_dart_surname_is_not_darts(name, forbidden):
    """Cert specimen 1. A surname is not evidence of a sport."""
    assert categorize_by_rules(name) != forbidden


@pytest.mark.parametrize("name,_forbidden", F3_SINGULAR_DART_SPECIMENS)
def test_f3_singular_dart_scores_no_darts_evidence_at_all(name, _forbidden):
    """The stronger form: not "darts lost the tie" but "darts was never evidence".

    Asserted on the breakdown rather than the verdict, because a fix that left
    singular "Dart" scoring for darts and merely arranged for something else to
    outscore it would pass the test above and fail the moment the rival token
    disappeared -- which is exactly what "Will Harriet Dart win a Grand Slam?"
    is: a title with no rival token at all.
    """
    from app.utils.futures_categorization import sport_evidence_breakdown

    assert "darts" not in sport_evidence_breakdown(name)


def test_f3_plural_darts_still_wins_on_the_shipping_path():
    """The invariant has to hold in the direction that keeps real darts working.

    This is the half a naive plural-only edit breaks, and it is asserted through
    the scorer (not just the verdict) because the whole finding was that a claim
    proven on `_STRONG_EVIDENCE_PATTERNS` said nothing about SPORT_PATTERNS.
    """
    from app.utils.futures_categorization import sport_evidence_breakdown

    assert categorize_by_rules("PDC World Darts Championship Winner") == "darts"
    assert categorize_by_rules("New Zealand Darts Masters: Winner") == "darts"
    assert "darts" in sport_evidence_breakdown("World Series of Darts: Gerwyn Price vs James Wade")


def test_f3_singular_dart_is_absent_from_every_shipping_darts_pattern():
    """No pattern that feeds the scorer may match a lone singular "dart".

    Written against the patterns rather than against titles so that adding a new
    darts pattern with `darts?` in it goes red here, instead of waiting for the
    next quarterback named Dart to be mis-filed in production.
    """
    from app.utils.futures_categorization import (
        SPORT_PATTERNS,
        _STRONG_EVIDENCE_PATTERNS,
    )

    offenders = [
        pattern.pattern
        for pattern, category in list(SPORT_PATTERNS) + list(_STRONG_EVIDENCE_PATTERNS)
        if category == "darts" and pattern.search("Jaxson Dart")
    ]
    assert offenders == [], (
        f"these darts patterns match the singular surname: {offenders}"
    )


# --- Finding 2: evidence accumulates; ties never consult list order ---------

def test_f3_two_agreeing_tokens_beat_one_stronger_token():
    """Cert specimen 2 -- the T20 fixture that came out basketball.

    `cricket` matched twice ("T20" and "cricket") inside ONE alternation, and
    `search()` billed it once, so two independent facts read as one and lost a
    3-3 tie to "Bulls" on SPORT_PATTERNS line number.
    """
    from app.utils.futures_categorization import (
        score_sport_evidence,
        sport_evidence_breakdown,
    )

    name = "Royal Nimar Eagles vs Bundelkhand Bulls T20 cricket"
    breakdown = sport_evidence_breakdown(name)
    assert set(breakdown["cricket"]) == {"t20", "cricket"}, (
        "both cricket tokens must be counted, not just the first"
    )
    assert score_sport_evidence(name)["cricket"] > score_sport_evidence(name)["basketball"]
    assert categorize_by_rules(name) == "cricket"


def test_f3_the_same_word_twice_is_one_piece_of_evidence():
    """Accumulation must not become repetition-counting.

    Otherwise the fix for specimen 2 hands any title a way to win by saying one
    word three times, which is a new mis-tag class rather than a fix.
    """
    from app.utils.futures_categorization import score_sport_evidence

    once = score_sport_evidence("cricket winner")
    thrice = score_sport_evidence("cricket cricket cricket winner")
    assert once["cricket"] == thrice["cricket"]


def test_f3_a_token_on_both_lists_is_counted_once_at_its_strongest():
    """`darts` is on SPORT_PATTERNS (3) and `_STRONG_EVIDENCE_PATTERNS` (5).

    Counting it twice would make "strong" mean "double", so a token's strength
    would depend on how many lists happen to mention it.
    """
    from app.utils.futures_categorization import sport_evidence_breakdown

    evidence = sport_evidence_breakdown("PDC World Darts Championship")["darts"]
    assert evidence["darts"] == 5


def test_f3_an_undeclared_tie_returns_none_rather_than_a_list_position():
    """The retired rule, asserted dead.

    A tie that no one has adjudicated must produce None. This is the assertion
    that separates "declared precedence" from "SPORT_PATTERNS order under a new
    name": if the ladder still fell back to ordering, this would return a
    category.
    """
    # cricket vs basketball, forced to an exact tie by giving each one token of
    # equal weight. Neither pair is in `_DECLARED_PRECEDENCE`.
    from app.utils.futures_categorization import score_sport_evidence

    name = "Bulls vs cricket"
    scores = score_sport_evidence(name)
    assert scores["basketball"] == scores["cricket"], "specimen must actually tie"
    assert categorize_by_rules(name) is None


def test_f3_declared_precedence_is_finite_and_reasoned():
    """The escape hatch must stay small enough to read, and mean what it says.

    Each key is the EXACT tied set, so an entry cannot quietly adjudicate a
    contest it was not written for.
    """
    from app.utils.futures_categorization import _DECLARED_PRECEDENCE

    for tied, winner in _DECLARED_PRECEDENCE.items():
        assert len(tied) >= 2
        assert winner in tied, (
            f"{winner!r} is declared the winner of {set(tied)} but is not in it"
        )


def test_f3_declared_precedence_only_fires_on_an_exact_tie():
    """A declared pair must not override real evidence.

    "NBA Defensive Player of the Year" carries a committing basketball token, so
    weight decides it and the football/basketball declaration never runs. If the
    declaration were consulted before the evidence, this would say football.
    """
    assert categorize_by_rules("NBA Defensive Player of the Year") == "basketball"
    assert categorize_by_rules("Defensive Player of the Year") == "football"


# --- Finding 3: ambiguity is per-category, not per-word ---------------------

def test_f3_the_athletics_specimen_lands_on_the_sport():
    """Cert specimen 3.

    Held in one flat set, "Athletics" was weak for both readings, so a track meet
    tied 1-1 with the Oakland ball club and lost on line number.

    Resolved by the PHRASE, not by promoting the word: "World Athletics" is the
    federation and cannot mean Oakland, so olympics accumulates real evidence
    while the bare noun stays weak in both readings. See
    `test_f3_promoting_the_bare_noun_would_break_the_ball_club` for the measured
    reason the word itself is not promoted.
    """
    from app.utils.futures_categorization import (
        _evidence_weight,
        score_sport_evidence,
    )

    name = "World Athletics Championship 100m Winner"
    scores = score_sport_evidence(name)
    assert scores["olympics"] > scores["baseball"]
    assert categorize_by_rules(name) == "olympics"
    assert _evidence_weight("Athletics", "baseball") == 1
    assert _evidence_weight("Athletics", "olympics") == 1, (
        "the bare noun is weak in BOTH readings; the phrase is what commits"
    )


@pytest.mark.parametrize(
    "name",
    [
        "Oakland Athletics 2026 Regular Season Wins Total",
        "Oakland Athletics to win the World Series",
        "Will the Athletics make the playoffs?",
    ],
)
def test_f3_promoting_the_bare_noun_would_break_the_ball_club(name):
    """The direction the cert's literal prescription regresses.

    Making "athletics" positive evidence for olympics sends every one of these to
    olympics (or to None, on a tie with "wins total"), which trades one mis-tag
    class for a larger one. This is the guard that keeps the fix at phrase
    granularity.
    """
    assert categorize_by_rules(name) == "baseball"


def test_f3_a_category_sensitive_entry_demotes_only_its_named_categories():
    """The mechanism, not just the one specimen.

    A token listed for `baseball` must keep full weight everywhere else --
    otherwise the category-sensitive table is just a slower flat set.
    """
    from app.utils.futures_categorization import (
        _AMBIGUOUS_ANYWHERE,
        _AMBIGUOUS_FOR_CATEGORY,
        _evidence_weight,
    )

    for token, categories in _AMBIGUOUS_FOR_CATEGORY.items():
        assert token not in _AMBIGUOUS_ANYWHERE, (
            f"{token!r} is both weak-everywhere and weak-for-some; the tables disagree"
        )
        for category in categories:
            assert _evidence_weight(token, category) == 1
        assert _evidence_weight(token, "a-category-that-does-not-exist") == 3


def test_f3_weak_everywhere_tokens_are_still_weak_everywhere():
    """The flat set has not quietly stopped working."""
    from app.utils.futures_categorization import _evidence_weight

    assert _evidence_weight("Masters", "golf") == 1
    assert _evidence_weight("Masters", "darts") == 1
    assert _evidence_weight("World Cup", "soccer") == 1
