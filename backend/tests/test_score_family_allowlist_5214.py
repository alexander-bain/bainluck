"""#5214: the score resolver may only grade families a final score can decide.

`_resolve_kalshi_from_scores` knows exactly one fact — the game's final score — and
used to decide what it was allowed to answer with `_non_ml`, a DENYLIST of leg-type
substrings. A denylist asks "have I been told to stay away from this?" when the only
safe question is "can I actually grade this?", so every family nobody had thought to
list was graded as a moneyline: who reaches 10 points first, who won set 2, who
advances on aggregate, how many triple-doubles.

The defect class this file guards: *a resolver that knows one fact must name the
questions that fact answers, not the questions it does not.* An allowlist is refutable
by a new family arriving; a denylist is refuted only by a reader finding a wrong
verdict, and by then `game_score` has made it permanent.

Specimens are production tickers measured 2026-09-11 ~14:0xZ. The refused ones are
split by how much they had already cost:

  * REALIZED — 137 outcomes were carrying a verdict nothing could have computed.
  * PENDING  — 211 markets sat in the candidate scan, admitted by the denylist.
  * LATENT   — reachable, and holding no `game_score` row only because Kalshi
               settled them first (gotcha #35: that cover expires at 74-86 days).
"""

import importlib
import re

import pytest

#: NOT `from app.tasks import backfill_winners` — `app/tasks/__init__.py` re-exports
#: the celery task of the same name, so that binds the FUNCTION and every read below
#: silently answers about a two-line wrapper instead of the module.
bw = importlib.import_module("app.tasks.backfill_winners")


#: Verbatim, the denylist that decided this before #5214 — the red arm. Every REFUSED
#: specimen below passes it, which is precisely what made the bug invisible.
_PRE_5214_DENYLIST = (
    "total", "spread", "pts", "reb", "ast", "3pt", "blk", "stl", "hrr", "hit",
    "tb", "ks", "hr", "rfi", "f5", "mention",
    "1htotal", "1hspread", "1hwinner", "2htotal", "2hspread", "2hwinner",
)


def _pre_5214_would_grade(ticker: str) -> bool:
    """The shipped-before rule: graded unless a denylist token appears anywhere."""
    low = ticker.lower()
    return not any(t in low for t in _PRE_5214_DENYLIST)


REFUSED_REALIZED = [
    ("KXNCAAMBFIRST10-26MAR19HPWIS",
     "first to 10 points, graded High Point off an 82-83 game"),
    ("KXWTASETWINNER-26AUG21BEJKEY-2",
     "set 2 of a 2-1 match, graded to the match winner like set 1"),
    ("KXATPSETWINNER-26AUG30SWEMOU-3",
     "set 3 of a match that ended 2-0 — the set was never played"),
    ("KXUCLADVANCE-26FEB25JUVGAL",
     "two-leg tie, graded off one leg's 3-2"),
]

#: NOTE ON SPECIMEN SELECTION. Every ticker here was pulled from production with
#: `external_id !~* <denylist>` applied, because the obvious sample does not prove
#: anything: `KXNBA3D-26JUN13NYKSAS` spells `ks` in NYK+SAS, `KXMLBRBI-…TBATL`
#: spells `tb`, `KXEPLCORNERS-…BREBRI` spells `reb`. The denylist turns those away
#: BY ACCIDENT, so they are silent about the allowlist. The red arm in the test
#: below is what caught it — ten of the first eleven specimens drafted here were
#: unusable for exactly this reason.
REFUSED_PENDING = [
    ("KXNBA3D-26MAY05CLEDET", "Triple Doubles, 173 markets pending"),
    ("KXUFCROUNDS-26SEP12KLOGAN", "Round of Finish, 20 pending"),
    ("KXNBA2D-26MAY05CLEDET", "Double Doubles, 9 pending"),
    ("KXMLBOUTS-26SEP101305HOUPHI", "Outs Recorded, 7 pending"),
    ("KXNFLPASSTDS-26SEP14DENKC", "Passing Touchdowns, 1 pending"),
    ("KXNFLRECYDS-26SEP14DENKC", "Receiving Yards, 1 pending"),
]

REFUSED_LATENT = [
    ("KXNHLGOAL-26JUN11VGKCAR", "goalscorer prop, 342 markets"),
    ("KXNHLFIRSTGOAL-26JUN11VGKCAR", "first goalscorer, 339 markets"),
    ("KXUFCVICROUND-26SEP12KLOGAN", "round of victory, 39 markets"),
    ("KXMLBRBI-26SEP101305HOUPHI", "runs batted in, 36 markets"),
    ("KXMLBINNINGWIN-26SEP101610TEXSEA-1", "wins a single inning, 261 markets"),
    ("KXNCAAFFIRSTTDTEAM-26SEP03MASSRUTG", "first touchdown team, 45 markets"),
    ("KXEPLCORNERS-26SEP12CFCHUL", "corner count"),
    ("KXNBAOVERTIME-26MAY05CLEDET", "does it go to overtime"),
    ("KXLALIGASCORE-26SEP11SEVVCF", "exact scoreline"),
    ("KXNCAALAXFINAL-26", "a final, not a game moneyline"),
    ("KXNBAWEST-27", "conference futures, not a game"),
]

#: The `EXACTMATCH` carve-out gets its own list: it is the only family that ends in
#: an admitted suffix while asking a question the score cannot answer.
REFUSED_EXACTMATCH = [
    ("KXATPEXACTMATCH-26SEP11ZVEKHA", "exact set score: 'Nuno Borges wins 2-0'"),
    ("KXWTAEXACTMATCH-26AUG31DARSTE", "exact set score, women's draw"),
]

#: Full-game questions a final score really does decide. Several are deliberately
#: #5116 specimens — a team-abbreviation collision inside the EVENT segment must not
#: reach a rule keyed on the FAMILY segment, or this fix re-imports that bug.
ADMITTED = [
    ("KXNCAAMBGAME-26APR04WVUCREI", "moneyline, 1005 outcomes graded"),
    ("KXNBAGAME-26OCT20BOSDET", "moneyline"),
    ("KXNHLGAME-26MAY16BUFMTL", "moneyline"),
    ("KXMLBGAME-26SEP131920SDSF", "moneyline"),
    ("KXMLBSTGAME-26MAR241205TBATL", "spring training moneyline, 352 graded"),
    ("KXWTAMATCH-26SEP12SABRYB", "tennis match winner"),
    ("KXATPMATCH-26SEP11ZVEKHA", "tennis match winner"),
    ("KXRUGBYNRLMATCH-26SEP05WARMAN", "rugby match winner"),
    ("KXMLSBTTS-26SEP04NYCNSH", "both teams to score"),
    ("KXWCBTTS-26JUL14FRAESP", "both teams to score"),
    ("KXUECLGAME-26AUG26SCRHOM", "moneyline"),
    ("KXAFLGAME-26SEP110610GEEFRE", "moneyline"),
]

#: #5116's own specimens, kept separate. These are real full-game markets whose
#: EVENT segment spells a prop token across the team boundary. The allowlist must
#: admit them — if it did not, this fix would re-import the exact bug #5116 closed.
#: They are NOT in `ADMITTED` above because `_non_ml` still skips them downstream
#: (#5230), so saying "these get graded" would overclaim; what is asserted here is
#: only that the FAMILY rule does not turn them away.
ADMITTED_DESPITE_TEAM_COLLISION = [
    ("KXNHLGAME-26FEB25TORTB", "TOR+TB spells 'tb'"),
    ("KXMLBGAME-26MAR261615TBSTL", "spells both 'tb' and 'stl'"),
    ("KXAFLGAME-26MAR150015SKSMEL", "S|KS|MEL spells 'ks'"),
    ("KXMLSBTTS-26MAR01SDSTL", "SD+STL spells 'stl'"),
    ("KXEKSTRAKLASAGAME-26SEP12LEGWIS", "the league's NAME spells 'ks' (#5230)"),
]


@pytest.mark.parametrize(
    "ticker,why",
    REFUSED_REALIZED + REFUSED_PENDING + REFUSED_LATENT + REFUSED_EXACTMATCH,
    ids=[t for t, _ in REFUSED_REALIZED + REFUSED_PENDING + REFUSED_LATENT
         + REFUSED_EXACTMATCH],
)
def test_a_final_score_cannot_answer_this_so_it_is_refused(ticker, why):
    # Red arm FIRST: if the denylist already turned this away, the specimen proves
    # nothing about the allowlist and the failure is in this file, not the fix.
    assert _pre_5214_would_grade(ticker), (
        f"{ticker} is not a specimen of the #5214 bug ({why}) — the pre-fix "
        "denylist already refused it"
    )
    assert not bw._score_gradeable_family(ticker), f"{ticker} still graded ({why})"


@pytest.mark.parametrize("ticker,why", ADMITTED, ids=[t for t, _ in ADMITTED])
def test_full_game_questions_are_still_graded(ticker, why):
    assert bw._score_gradeable_family(ticker), f"{ticker} lost coverage ({why})"


@pytest.mark.parametrize(
    "ticker,why",
    ADMITTED_DESPITE_TEAM_COLLISION,
    ids=[t for t, _ in ADMITTED_DESPITE_TEAM_COLLISION],
)
def test_a_team_abbreviation_collision_does_not_reach_the_family_rule(ticker, why):
    # Red arm: the denylist DID refuse these, which is #5116's bug. If one stops
    # doing so the specimen has gone stale and proves nothing.
    assert not _pre_5214_would_grade(ticker), (
        f"{ticker} is not a #5116 collision specimen ({why})"
    )
    assert bw._score_gradeable_family(ticker), (
        f"{ticker} refused by the FAMILY rule ({why}) — #5116 has been re-imported"
    )


def test_exactmatch_is_refused_on_its_own_and_not_by_the_outcome_count():
    """The carve-out must hold by NAME, not because something else declines first.

    `KXATPEXACTMATCH` carries 4-6 outcomes ("wins 2-0", "wins 2-1", …) so the
    `n_outcomes != 2` guard downstream would also turn it away. That guard is about
    market shape, not about what the score can answer — a best-of-three exact-score
    market with two outcomes would sail past it. A guard that only holds because an
    unrelated short-circuit fires first is a guard that is not being tested.
    """
    assert bw._SCORE_GRADEABLE_FAMILY_RE.search("KXATPEXACTMATCH"), (
        "specimen is wrong: EXACTMATCH must end in an ADMITTED suffix, otherwise "
        "the carve-out is doing nothing and this test is vacuous"
    )
    assert not bw._score_gradeable_family("KXATPEXACTMATCH-26SEP09VACBOR")


def test_every_canonical_fight_and_doubles_winner_family_remains_score_gradeable():
    """CERT-2624's repair: the two functions that ask "is this the contest winner?"
    may not disagree.

    `feeds_win_prob_blend` decides which Kalshi tickers are canonical WINNER lines,
    and it answers with `COMBAT_FIGHT_WINNER_PREFIXES | TENNIS_MATCH_WINNER_PREFIXES`.
    A suffix rule keyed on `game|match` admits `KXATPMATCH` and refuses
    `KXATPDOUBLES` — the same question, turned away because of how its sport spells
    the family. This asserts the allowlist is a SUPERSET of the blend's vocabulary,
    generatively, so a prefix added to that vocabulary tomorrow is admitted here
    without anyone remembering to edit a list.
    """
    from app.utils.prediction_market_matching import (
        COMBAT_FIGHT_WINNER_PREFIXES,
        TENNIS_MATCH_WINNER_PREFIXES,
        feeds_win_prob_blend,
    )

    canonical = COMBAT_FIGHT_WINNER_PREFIXES | TENNIS_MATCH_WINNER_PREFIXES
    assert canonical, "the blend's winner vocabulary is empty — specimen is wrong"

    for prefix in sorted(canonical):
        ticker = f"{prefix.upper()}-26SEP12ABCDEF"
        # The premise: this really is a canonical winner line to the OTHER function.
        assert feeds_win_prob_blend(ticker), (
            f"{ticker} is not a specimen — feeds_win_prob_blend does not call it a "
            "winner line, so the two functions were never in disagreement about it"
        )
        assert bw._score_gradeable_family(ticker), (
            f"{ticker} is a canonical winner line for the win-prob blend but the "
            "score resolver refuses its family — CERT-2624's defect"
        )


def test_the_canonical_winner_set_is_load_bearing_and_not_a_restated_suffix_rule():
    """Red arm for the test above: without the constant, six of them fail.

    If every canonical prefix happened to end in an admitted suffix, the superset
    assertion would pass with `_CANONICAL_WINNER_FAMILIES` deleted and would be
    decorative. Six do not — the fight families and all four doubles variants — and
    those six are exactly what the repair adds.
    """
    only_the_suffix_rule = {
        prefix for prefix in bw._CANONICAL_WINNER_FAMILIES
        if bw._SCORE_GRADEABLE_FAMILY_RE.search(prefix)
    }
    needs_the_constant = set(bw._CANONICAL_WINNER_FAMILIES) - only_the_suffix_rule

    assert needs_the_constant == {
        "kxufcfight",
        "kxboxing",
        "kxatpdoubles",
        "kxwtadoubles",
        "kxatpchallengerdoubles",
        "kxwtachallengerdoubles",
    }, (
        "the set of families that depend on the constant has changed; if this is a "
        "deliberate addition to the blend vocabulary, update this list — the point "
        "is that the change is never silent"
    )
    # And the mirror: the suffix rule alone really does turn each of them away.
    for prefix in needs_the_constant:
        assert not bw._SCORE_GRADEABLE_FAMILY_RE.search(prefix), prefix


@pytest.mark.parametrize(
    "ticker,why",
    [
        ("KXATPSETWINNER-26AUG30SWEMOU-3", "a SET winner is not the match winner"),
        ("KXWTASETWINNER-26AUG21BEJKEY-2", "a SET winner is not the match winner"),
        ("KXATPEXACTMATCH-26SEP11ZVEKHA", "the exact set score, not who won"),
        ("KXWTAEXACTMATCH-26AUG31DARSTE", "the exact set score, not who won"),
        ("KXUFCROUNDS-26SEP12KLOGAN", "which ROUND it ends in, not who wins"),
        ("KXUFCVICROUND-26SEP12KLOGAN", "round of victory, not who wins"),
    ],
    ids=lambda v: v if isinstance(v, str) and v.startswith("KX") else "",
)
def test_the_fight_and_racquet_props_beside_them_are_still_refused(ticker, why):
    """Widening to fight/doubles WINNERS must not drag their prop siblings in.

    These live in the same sports and share prefixes with the newly admitted
    families (`KXUFCFIGHT` vs `KXUFCROUNDS`, `KXATPMATCH` vs `KXATPSETWINNER`), so
    they are the population a careless widening would capture.
    """
    assert not bw._score_gradeable_family(ticker), f"{ticker} admitted ({why})"


def test_the_rule_reads_the_family_segment_not_the_whole_ticker():
    """#5116's lesson, applied forward.

    A Kalshi ticker is `SERIES-EVENT[-STRIKE]` and the EVENT segment concatenates two
    team abbreviations, so any rule matched against the whole id can be spelled by a
    team boundary. Here the risk runs the other way — an ADMITTED suffix appearing
    after the dash would let a prop through.
    """
    assert not bw._score_gradeable_family("KXNBAPTS-26JUN13NYKGAME"), (
        "a prop family was admitted because the EVENT segment ends in 'game'"
    )
    assert not bw._score_gradeable_family("KXNHLGOAL-26FEB25TORMATCH")
    # And the mirror: a real family keeps its verdict however the event reads.
    assert bw._score_gradeable_family("KXNBAGAME-26JUN13NYKPTS")


def test_period_markets_are_refused_before_the_family_gate_is_consulted():
    """`KXMLS1HBTTS` ends in an admitted suffix and must still never be graded.

    #4923: a FIRST-HALF both-teams-to-score question was answered with "did both
    teams score in the WHOLE match" — 49 markets, 45 of them affirmative. The family
    gate deliberately does not re-litigate that; `_ticker_period` owns it and runs
    first. This test pins the ORDER, because the gate reads as if it were the only
    thing standing between a 1H market and a final-score verdict.
    """
    assert bw._score_gradeable_family("KXMLS1HBTTS-26MAR01SDSTL"), (
        "specimen is wrong: if the family gate already refuses this, the test says "
        "nothing about ordering"
    )
    assert bw._ticker_period("KXMLS1HBTTS-26MAR01SDSTL") == "1h"
    assert bw._ticker_period("KXNBA1QWINNER-26JUN13NYKSAS") == "1q"


#: The ONE family the allowlist admits while the re-null clears it — #5230. The word
#: EKSTRAKLASA contains `ks`, the strikeout token, INSIDE the family segment, so
#: #5116's anchoring cannot reach it. It is latent, not live (2 markets, 6 outcomes,
#: all settled by Kalshi first), and fixing it means grading MORE, which needs its own
#: measurement rather than a drive-by inside a ship whose point is grading less.
#: Delete this entry as part of #5230 — the test will demand it.
KNOWN_ALLOWLIST_RENULL_DISAGREEMENT = {"KXEKSTRAKLASAGAME"}

#: Every Kalshi family observed over completed/closed events, production
#: 2026-09-11 ~14:0xZ (434 total). Only the ones that end in an admitted SUFFIX are
#: listed. That was the whole admitted set when this was gathered; since CERT-2624 it
#: is not, because `_CANONICAL_WINNER_FAMILIES` admits fight/doubles lines that end in
#: neither `game` nor `match`. The disagreement check below unions those in rather
#: than restating them here, so this list can stay what it says it is.
_ADMITTED_FAMILIES_PRODUCTION = [
    "KXAFLGAME", "KXALEAGUEGAME", "KXARGPREMDIVGAME", "KXATPMATCH",
    "KXBELGIANPLGAME", "KXBRASILEIROBGAME", "KXBRASILEIROGAME",
    "KXBUNDESLIGA2GAME", "KXBUNDESLIGAGAME", "KXCHNSLGAME", "KXCONMEBOLLIBGAME",
    "KXCONMEBOLSUDGAME", "KXCOPPAITALIAGAME", "KXDENSUPERLIGAGAME",
    "KXDFBPOKALGAME", "KXEFLCHAMPIONSHIPGAME", "KXEFLCUPGAME", "KXEFLL1GAME",
    "KXEKSTRAKLASAGAME", "KXELITESERIENGAME", "KXEPLGAME", "KXEUROLEAGUEGAME",
    "KXFACUPGAME", "KXFIFAGAME", "KXGER3LGAME", "KXJLEAGUEGAME",
    "KXLALIGAGAME", "KXLEAGUESCUPGAME", "KXLIGAMXGAME", "KXLIGAPORTUGALGAME",
    "KXLIGUE1GAME", "KXLIGUE2GAME", "KXMLBGAME", "KXMLBSTGAME", "KXMLSGAME",
    "KXNBAGAME", "KXNBLGAME", "KXNCAABBGAME", "KXNCAAFGAME", "KXNCAAMBGAME",
    "KXNCAAMLAXGAME", "KXNCAAWBGAME", "KXNFLGAME", "KXNHLGAME", "KXODIMATCH",
    "KXRUGBYNRLMATCH", "KXSAUDIPLGAME", "KXSCOTTISHPREMGAME", "KXSERIEAGAME",
    "KXSERIEBGAME", "KXSHLGAME", "KXSLGREECEGAME", "KXSUPERLIGGAME",
    "KXUECLGAME", "KXUELGAME", "KXWCGAME", "KXWNBAGAME", "KXWTAMATCH",
    "KXWTESTMATCH",
]


def test_the_allowlist_and_the_re_null_do_not_disagree_about_a_family():
    """A family the resolver may grade must not be one the repair immediately clears.

    Otherwise the row churns — graded, cleared, graded — and the reader sees a blank
    in the gap. That is #5116's loop, and it is the reason the allowlist and the
    re-null ship in the same commit rather than one after the other.
    """
    # The canonical winner families are unioned in DELIBERATELY.
    # `_ADMITTED_FAMILIES_PRODUCTION` was gathered as "production families ending in
    # an admitted SUFFIX", which was the whole admitted set when it was written. Once
    # `_CANONICAL_WINNER_FAMILIES` started admitting fight/doubles lines (CERT-2624)
    # that list stopped being the admitted set by construction, and this check would
    # have gone silently blind to exactly the families the repair added.
    candidates = set(_ADMITTED_FAMILIES_PRODUCTION) | {
        prefix.upper() for prefix in bw._CANONICAL_WINNER_FAMILIES
    }
    assert "KXUFCFIGHT" in candidates, (
        "the canonical winner families are not reaching this check — it is blind to "
        "the population CERT-2624's repair admitted"
    )
    disagree = {
        family
        for family in candidates
        if bw._score_gradeable_family(family)
        and re.search(bw._ML_REPAIR_TOKENS_ANCHORED, family, re.IGNORECASE)
    }
    assert disagree == KNOWN_ALLOWLIST_RENULL_DISAGREEMENT, (
        f"allowlist/re-null disagreement changed: {sorted(disagree)}. A NEW entry "
        "means a gradeable family is being churned; a MISSING one means #5230 is "
        "fixed and this marker should be deleted."
    )


def test_the_re_null_reaches_every_family_the_allowlist_newly_refuses():
    """Refusing the family stops the bleeding; the repair is what heals the 137 rows.

    A `game_score` verdict is permanent — the source is not in
    OVERWRITABLE_WINNER_SOURCES_SQL and the candidate scan drops any market already
    holding one — so a row already written is unreachable by the allowlist alone.
    """
    for ticker, why in REFUSED_REALIZED:
        family = ticker.split("-")[0]
        assert re.search(bw._ML_REPAIR_TOKENS_ANCHORED, family, re.IGNORECASE), (
            f"{family} is refused going forward but its {why} rows stay graded — "
            "the re-null cannot reach them"
        )


def test_the_resolver_counts_its_refusals():
    """A refusal that is not counted is indistinguishable from a market never seen.

    `refused_family` is how the next session tells "the allowlist is working" from
    "the candidate scan went empty", which is the `task_verdict` rule (gotcha #53:
    "it returned" is not "it worked").
    """
    import inspect

    source = inspect.getsource(bw._resolve_kalshi_from_scores)
    assert 'stats["refused_family"] += 1' in source
    assert '"refused_family": 0' in inspect.getsource(bw)
    # The gate must sit AFTER the period refusal, or `refused_period` loses its
    # meaning and #4923's counter starts reading zero.
    assert source.index("refused_period") < source.index("refused_family")
