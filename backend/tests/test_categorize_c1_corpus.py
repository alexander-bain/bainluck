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

from app.utils.futures_categorization import categorize_by_rules, score_sport_evidence


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
# C-F3-CATEGORIZE-3's three P1s (BLOCK on 38685f64), each with the test that
# catches it (D53). All three were live on the branch head the BLOCK froze; each
# assertion below was RED before the repair in this commit.
#
# Note why the existing controls above missed the first one: every Jaxson Dart
# control carries a strong football token ("Pro Football", "NFL", "QB"), so
# football outscored darts on evidence. The BLOCK's specimen carries none, so
# the two tied 3-3 and SPORT_PATTERNS order handed it to darts. A control set
# that only samples the easy half of a class does not cover the class.
# ---------------------------------------------------------------------------

def test_p1_singular_dart_is_a_surname_not_a_sport():
    """P1-1: ``\\bdarts?\\b`` in SPORT_PATTERNS matched the NFL QB's surname.

    `_STRONG_EVIDENCE_PATTERNS` already used the plural deliberately and said so
    in a comment; SPORT_PATTERNS had never learned it.
    """
    assert categorize_by_rules("Will Jaxson Dart be the first overall pick?") == "football"
    # The tennis half of the same surname collision, also with no strong token.
    assert categorize_by_rules("Harriet Dart to reach the second round") != "darts"
    # And the plural still commits, with no other evidence in the string at all.
    assert categorize_by_rules("Darts: Luke Humphries vs Michael van Gerwen") == "darts"


def test_p1_evidence_is_counted_per_distinct_term_not_per_regex():
    """P1-2: one ``search()`` per pattern scored regex AUTHORING, not evidence.

    Cricket owns a single alternation, so its three terms in "rajasthan royals to
    win ipl t20" scored 3 -- tying the ONE incidental baseball token "royals",
    which then won on SPORT_PATTERNS order. Counting distinct matched text makes
    the cricket evidence add up.
    """
    scores = score_sport_evidence("rajasthan royals to win ipl t20")
    assert scores["cricket"] > scores.get("baseball", 0), (
        f"cricket evidence must outweigh one stray team token, got {scores}"
    )
    assert categorize_by_rules("Rajasthan Royals to win IPL T20") == "cricket"

    # The other direction (gotcha #43): dedup on matched TEXT, so a category
    # cannot farm a score by owning many patterns that match the SAME word.
    repeated = score_sport_evidence("nba nba nba nba")
    single = score_sport_evidence("nba")
    assert repeated == single, (
        f"repeating one token must not inflate its score: {repeated} vs {single}"
    )


def test_p1_a_track_meet_is_not_filed_as_baseball():
    """P1-3: "athletics" is the Oakland A's to this file, so a track meet scored
    baseball 1, nothing outscored 1, and a lone ambiguous match wins unopposed.

    WHAT ACTUALLY CARRIES THIS TEST, stated because the BLOCK diagnosed P1-3 as
    "`_AMBIGUOUS_EVIDENCE` is category-blind" and the repair for the *specimen*
    is not the pairing: it is the veto. Verified by mutation -- reverting
    `_evidence_weight` to the flat set leaves this test GREEN, while dropping
    "athletics" from `_VETO_ONLY_CATEGORIES` or removing `world\\s+athletics`
    from the strong patterns turns it RED. Making ambiguity a (category, word)
    relation is an anti-drift change with NO behavioural delta on any reachable
    input (measured: the only vocabulary entries whose discount it changes are
    "open" and "giants", and no pattern in this file ever emits either as bare
    matched text -- they always match inside "the open" / "us open" /
    "san francisco giants"). It is pinned structurally by
    `test_ambiguity_pairs_are_derived_from_the_patterns_not_restated`, not here.
    Do not read this test as coverage of the pairing.
    """
    assert categorize_by_rules("World Athletics Championship 100m Winner") != "baseball"
    # Veto-only: we can recognise the domain without having a category for it, so
    # the row goes to the LLM fallback rather than to a confident wrong answer.
    assert categorize_by_rules("World Athletics Championship 100m Winner") is None

    # The pairing must NOT cost the category whose claim is genuine.
    assert categorize_by_rules("Will the Oakland Athletics win the World Series?") == "baseball"
    # And the veto must not reach a box-office market: "$100M" is why bare race
    # distances are absent from the athletics pattern.
    assert categorize_by_rules("Will Avatar 3 gross over $100M opening weekend?") == "entertainment"


def test_ambiguity_pairs_are_derived_from_the_patterns_not_restated():
    """The table cannot drift from the patterns it describes.

    Every derived pair names a real (category, word) the patterns can actually
    produce -- so an entry for a word no pattern matches cannot sit in the set
    silently weighting nothing, which is how "jazz", "kings" and "browns" got in.
    """
    from app.utils.futures_categorization import _AMBIGUOUS_EVIDENCE, _AMBIGUOUS_FOR

    assert _AMBIGUOUS_FOR, "the derivation produced nothing -- it is not wired up"
    for category, token in _AMBIGUOUS_FOR:
        assert token in _AMBIGUOUS_EVIDENCE, (
            f"{token!r} is paired but is not in the curated vocabulary"
        )
    # The three dead entries are still dead, and provably so: they pair with
    # nothing, which is the derivation refusing to invent a claimant.
    paired = {token for _c, token in _AMBIGUOUS_FOR}
    assert {"jazz", "kings", "browns"}.isdisjoint(paired)
    # "athletics" is ambiguous for baseball specifically -- the P1-3 pairing.
    assert ("baseball", "athletics") in _AMBIGUOUS_FOR


# ---------------------------------------------------------------------------
# CERT-1967's repair — the guard at the FULL CALLER, not at the unit
# ---------------------------------------------------------------------------


def test_a_t20_league_reaches_cricket_through_the_whole_cascade():
    """CERT-1967 BLOCK: every assertion in this file could be green while the
    fix was undone.

    The grader's mutation: repair only ``('soccer', 'premier league')`` in
    ``_AMBIGUOUS_FOR`` to the prior inert ``('darts', 'premier league')``. Every
    C1 case above, all three P1 assertions and every structural assertion stay
    GREEN -- and 98 of the 680 frozen movement titles go back to soccer. The
    reason is that the assertions above stop at ``categorize_by_rules`` or at the
    shape of the pair table, and neither notices which category "premier league"
    is discounted FOR; the pairing only shows up once a real title makes soccer
    and cricket compete over it.

    So this test drives ``resolve_event_category`` -- the entry point the poller
    actually calls, tags and all -- on a production title from the movement
    class. It is the one assertion in this file that the grader's mutation
    reddens.
    """
    from app.tasks.polymarket import _tags_to_category, resolve_event_category

    title = "Kuwait Kerala Premier League T20: Arabian Eagles vs Blue Giants"
    category, sport = _tags_to_category([])
    resolved_category, resolved_sport, arm = resolve_event_category(
        category, sport, title, [title]
    )

    assert resolved_sport == "cricket", (
        f"a T20 league resolved as {resolved_sport!r} -- 'premier league' is "
        f"being discounted for the wrong claimant, so soccer wins a word that "
        f"only cricket's competing evidence should have beaten"
    )
    assert (resolved_category, arm) == ("championship", "fallback")


def test_premier_league_is_discounted_for_soccer_and_no_one_else():
    """Supplemental to the test above: the pairing itself, stated once.

    Kept deliberately narrow. This pins WHICH claimant the word is doubtful for,
    which is the single bit the mutation flips; the full-caller test above is
    what proves that bit is load-bearing. A pair assertion alone would not --
    it passes against a table that no caller consults.
    """
    from app.utils.futures_categorization import _AMBIGUOUS_FOR

    claimants = {c for c, token in _AMBIGUOUS_FOR if token == "premier league"}
    assert claimants == {"soccer"}, (
        f"'premier league' is discounted for {sorted(claimants)}; it is only "
        f"ambiguous when SOCCER claims it (Premier League Darts is the other "
        f"reading, and darts has its own strong evidence)"
    )
