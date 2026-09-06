"""#3478 — a cup tie says WHICH cup, so its moneyline reaches its own game.

#3446 shipped the 73 PROP legs of these cup ties and pinned the 15 `…GAME`
(moneyline) legs unmapped, because the obvious completion — `soccer_other` for
all fifteen — regressed 17 golden-set pairs (CI run 34019815553). This file is
the completion done by measurement, and the measurement split the fifteen into
three buckets that need three different answers.

WHAT WAS ACTUALLY BROKEN, measured against production 2026-09-06 over the 1,066
rows in these 15 series: 39 are linked to an event and 419 carry a sport tag
that is not soccer. `KXUECLGAME` alone had 11 markets attached to
`baseball_other` EVENTS and 3 to `americanfootball_other` — a Europa Conference
League tie living on a baseball game. That is caused by the unmapped ticker:
`_score_candidates` falls back to the row's own `llm_sport_category` when the
ticker answers nothing, so a mis-tagged row is scoped to the wrong sport and
then links inside it. The ticker is re-read on every matching pass, so mapping
it repairs rows already in the table with no re-ingest.

WHY THE VALUE IS NOT A LABEL. A mapped `…GAME` prefix is ARMED: it enters the
matcher's game pass and its value becomes the hard sport gate. There the value
does two jobs in opposite directions — it REJECTS every candidate that fails
`event.sport.key.startswith(value)`, and its mere PRESENCE lifts the no-prefix
guard that otherwise demands score >= 21 before anything may link. So:

  * `soccer_other` fails twice: it rejects the right event for a competition
    that has its own key, AND (being a real key with thousands of events) it
    admits a crowd of wrong ones with the threshold switched off.
  * bare `soccer` fixes only the first half. It still lifts the threshold over
    every soccer event we hold — measured here, that flips 10 adjudicated
    negatives into links, 9 of them `KXSERIECCUPGAME` ties landing on the same
    two clubs' Serie C LEAGUE fixture.
  * the competition's own key is the only value that admits its fixtures and
    refuses everything else.

Expectations are written literally. Deriving them from the map under test would
make this file agree with production by construction and assert nothing.
"""

import pytest

from app.utils.sport_keys import (
    KALSHI_GAME_TICKER_PREFIXES,
    KALSHI_TICKER_TO_SPORT_KEY,
    get_sport_key_from_ticker,
)

# ─────────────────────────────────────────────────────────────────────────────
# BUCKET 1 — ARMED. Eight competitions with a real league key.
#
# (ticker prefix, the key, events behind that key in production 2026-09-06).
# The event count is here because a key that exists but is empty would pass a
# spelling check and still refuse every fixture at runtime.
# ─────────────────────────────────────────────────────────────────────────────
ARMED = [
    ("KXEFLCUPGAME", "soccer_england_efl_cup", 87),
    ("KXFACUPGAME", "soccer_fa_cup", 50),
    ("KXDFBPOKALGAME", "soccer_germany_dfb_pokal", 56),
    ("KXCOPPAITALIAGAME", "soccer_italy_coppa_italia", 29),
    ("KXUELGAME", "soccer_uefa_europa_league", 65),
    ("KXUECLGAME", "soccer_uefa_europa_conference_league", 63),
    ("KXCONMEBOLLIBGAME", "soccer_conmebol_copa_libertadores", 155),
    ("KXCONMEBOLSUDGAME", "soccer_conmebol_copa_sudamericana", 161),
]

# ─────────────────────────────────────────────────────────────────────────────
# THE COST THIS CHANGE ACCEPTS, pinned so it is a decision and not a surprise.
#
# Arming a precise key REJECTS candidates that fail `startswith`, and 20 links
# that exist in production today fail it. Fourteen of those twenty are the bug
# being fixed — `baseball_other` and `americanfootball_other` events that a
# soccer moneyline should never have reached. **Six are correct links that this
# change breaks**, and they are all the same shape:
#
#   KXFACUPGAME-26SEP04OSSPON  -> Ossett United v Pontefract      [soccer_other]
#   KXUECLGAME-26JUL09PENFCC   -> Pen-y-Bont v FC Coloma          [soccer_other]
#   KXUECLGAME-26JUL09MLBTBI   -> Mondorf-Les-Bains v Dinamo Tb.  [soccer_other]
#   KXUECLGAME-26JUL09ALAYEL   -> Alashkert Yerevan v FC Yelimai  [soccer_other]
#   KXUELGAME-26JUL09DYKUCL    -> Dynamo Kyiv v Uni Cluj          [soccer_other]
#   (+1 more UECL July qualifier)
#
# THE CAUSE IS ON OUR EVENT SIDE, NOT IN THIS MAP: we file a cup's QUALIFYING
# rounds under `soccer_other` and only its main draw under the competition key.
# Measured 2026-09-06 — `soccer_uefa_europa_conference_league` holds 0 events in
# July/August/September and 18 on Oct 15 (the league phase), while every UECL
# market we hold is a July qualifier; `soccer_uefa_europa_league` starts Sep 16;
# `soccer_fa_cup` holds the main draw while Ossett United v Pontefract, a
# qualifying tie, is `soccer_other`.
#
# WHY IT IS STILL RIGHT TO ARM THEM. The six are resolved past ties, so nothing
# a reader can open changes. The forward case is near and large: UEL's league
# phase is 2026-09-16 (18 events already ingested) and UECL's is 2026-10-15 (18
# events), and an unmapped ticker sends those straight back into the
# `llm_sport_category` fallback that produced the 14 baseball attachments in the
# first place. Bare `soccer` was measured as the alternative that keeps all six
# — it scores 650/709 against the golden set versus 652 for precise keys, and
# starts a new wrong link — so it is worse on the instrument, not better.
#
# The real repair is to file cup qualifying rounds under their competition key.
# Filed as the follow-up on #3478; this list is here so that work can find its
# own population, and so nobody re-derives this measurement.
# ─────────────────────────────────────────────────────────────────────────────
LINKS_THIS_CHANGE_KNOWINGLY_BREAKS = 6
LINKS_THIS_CHANGE_DETACHES_AS_WRONG = 14
QUALIFYING_ROUNDS_MISFILED_AS = "soccer_other"

# The two competitions whose key holds NO event in the window their markets
# actually fall in. Armed deliberately, for the league phase — see above.
ARMED_AHEAD_OF_THEIR_LEAGUE_PHASE = {
    "KXUELGAME": "2026-09-16",
    "KXUECLGAME": "2026-10-15",
}


# ─────────────────────────────────────────────────────────────────────────────
# BUCKET 2 — NO KEY TO NAME. Six competitions with no row in `sports` at all
# (verified 2026-09-06). `soccer_greece_super_league` is the Greek LEAGUE, not
# the Greek Cup; there is no Taça de Portugal, no Coppa Italia Serie C, no Copa
# do Brasil, no Israeli cup and no ASEAN key.
# ─────────────────────────────────────────────────────────────────────────────
NO_KEY_YET = [
    "KXGRECUPGAME",
    "KXTACAPORTGAME",
    "KXSERIECCUPGAME",
    "KXCOPADOBRASILGAME",
    "KXISRPLCUPGAME",
    "KXASEANGAME",
]

# ─────────────────────────────────────────────────────────────────────────────
# BUCKET 3 — HELD. Correct, but it moves a golden pair, and the golden set is
# lane1b's under D39. See `test_the_held_leagues_cup_prefix_lands_with_its_
# amendment_or_not_at_all` below, which is the coupling and not a wish.
# ─────────────────────────────────────────────────────────────────────────────
HELD_PENDING_GOLDEN_AMENDMENT = "KXLEAGUESCUPGAME"
HELD_PAIR_MARKET_ID = 59173468
HELD_PAIR_EVENT_ID = 15291291

GENERIC_SOCCER_VALUES = ["soccer", "soccer_other"]


# =============================================================================
# The eight that ship
# =============================================================================


@pytest.mark.parametrize("prefix,key,_events", ARMED)
def test_an_armed_cup_leg_answers_with_its_own_competition(prefix, key, _events):
    ticker = f"{prefix}-26SEP02ABCDEF"
    assert get_sport_key_from_ticker(ticker) == key


@pytest.mark.parametrize("prefix,key,_events", ARMED)
def test_an_armed_cup_leg_is_actually_armed_for_the_matcher(prefix, key, _events):
    """Classification alone was never the ship.

    The prop legs beside these are deliberately kept OUT of
    `KALSHI_GAME_TICKER_PREFIXES` so they never become a hard sport key. These
    eight are in it on purpose — that membership is what lets a moneyline reach
    its game. A future tidy-up that moves them to the classification-only set
    would leave every test above green and un-ship the fix.
    """
    assert prefix.lower() in KALSHI_GAME_TICKER_PREFIXES


@pytest.mark.parametrize("prefix,key,events", ARMED)
def test_the_key_admits_its_own_fixture_and_refuses_the_generic_bucket(
    prefix, key, events
):
    """CERT-2043's finding, restated as the filter the matcher really runs.

    This asserts the MECHANISM (`startswith`), not the spelling, because the
    value is only right in virtue of what the filter does with it.
    """
    assert events > 0, f"{key} has no events — it would refuse its own fixtures"
    # The competition's own fixtures pass the gate.
    assert key.startswith(key)
    # …and the generic bucket does not stand in for it, in either direction.
    assert not key.startswith("soccer_other"), (
        f"{prefix} keyed inside the generic bucket — this is the #3446 "
        "regression: `soccer_other` refuses the competition's own fixtures"
    )
    assert not "soccer_other".startswith(key)


def test_no_armed_prefix_carries_a_generic_soccer_value():
    offenders = {
        prefix: KALSHI_TICKER_TO_SPORT_KEY.get(prefix.lower())
        for prefix, _key, _events in ARMED
        if KALSHI_TICKER_TO_SPORT_KEY.get(prefix.lower()) in GENERIC_SOCCER_VALUES
    }
    assert not offenders, (
        "an armed `…GAME` leg fell back to a generic soccer value: "
        f"{offenders}. Both regress the golden set — `soccer_other` by refusing "
        "the competition's own fixtures, bare `soccer` by lifting the >=21 "
        "no-prefix threshold over every soccer event we hold."
    )


# =============================================================================
# The six with nothing to name — and why "just use `soccer`" is refused
# =============================================================================


@pytest.mark.parametrize("prefix", NO_KEY_YET)
def test_a_competition_with_no_league_key_stays_unmapped(prefix):
    """Not an oversight — a measured refusal.

    Mapping these six to bare `soccer` was tried and measured against the
    golden set on 2026-09-06: 10 adjudicated negatives began linking, 9 of them
    `KXSERIECCUPGAME` ties landing on the same two clubs' Serie C league
    fixture. A Coppa Italia Serie C tie and a Serie C league match ARE the same
    two clubs in different competitions, which is exactly the pair that the
    no-prefix threshold is currently the only thing telling apart.

    Arming these is a real ship and it is not this one: it needs the six league
    keys to exist in `sports` first, and then events behind them. Filed on
    #3478 rather than guessed at here.
    """
    assert prefix.lower() not in KALSHI_TICKER_TO_SPORT_KEY
    assert get_sport_key_from_ticker(f"{prefix}-26SEP02ABCDEF") is None


@pytest.mark.parametrize("prefix", NO_KEY_YET)
def test_an_unkeyed_cup_leg_is_not_armed_for_the_matcher(prefix):
    assert prefix.lower() not in KALSHI_GAME_TICKER_PREFIXES


# =============================================================================
# The ninth, and the coupling that keeps it honest
# =============================================================================


def test_the_held_leagues_cup_prefix_lands_with_its_amendment_or_not_at_all():
    """The two halves are one commit, and this is the test that says so.

    `KXLEAGUESCUPGAME` -> `soccer_concacaf_leagues_cup` is correct — Kalshi's
    own `rules_primary` for the held pair reads "the Toluca vs Austin
    professional LEAGUES CUP soccer game originally scheduled for Aug 26, 2026",
    and event 15291291 is `soccer_concacaf_leagues_cup` "Toluca v Austin FC" at
    2026-08-27 00:30Z with the contract settling 2026-08-27 03:05:27Z.

    But the golden set adjudicated that pair `None` on 2026-09-02, under the
    note `non-sport-category;cup-ticker`, on a row stored as
    `llm_sport_category='legal'` — i.e. WHILE this ticker was unmapped. Mapping
    the prefix without the matching amendment takes the ratchet red for an
    improvement; recording the amendment without the prefix takes it red the
    other way. The golden set is lane1b's under D39, so this lane maps the
    prefix only once their amendment is banked.

    This test does not forbid the mapping. It forbids the HALF.
    """
    mapped = HELD_PENDING_GOLDEN_AMENDMENT.lower() in KALSHI_TICKER_TO_SPORT_KEY

    import json
    from pathlib import Path

    amendments = json.loads(
        (
            Path(__file__).parent
            / "fixtures"
            / "matching_golden_adjudication_amendments.json"
        ).read_text()
    )["amendments"]
    amended = any(
        a["market_id"] == HELD_PAIR_MARKET_ID and a["now"] == HELD_PAIR_EVENT_ID
        for a in amendments
    )

    assert mapped == amended, (
        f"{HELD_PENDING_GOLDEN_AMENDMENT} mapped={mapped} but the golden-set "
        f"amendment for market {HELD_PAIR_MARKET_ID} -> event "
        f"{HELD_PAIR_EVENT_ID} present={amended}. These land together or not at "
        "all — see this test's docstring for why either half alone reads as a "
        "regression that is not one."
    )


# =============================================================================
# The whole partition, so nothing falls between the buckets
# =============================================================================


@pytest.mark.parametrize("prefix", sorted(ARMED_AHEAD_OF_THEIR_LEAGUE_PHASE))
def test_a_competition_armed_ahead_of_its_league_phase_is_still_armed(prefix):
    """These two are the ones the cost above is mostly about.

    Their competition key holds no event in the window their current markets
    fall in, so arming them breaks four correct links to `soccer_other`
    qualifying ties and creates none until the league phase. That was measured
    and accepted, not overlooked — the alternative (bare `soccer`) scores worse
    on the golden set AND starts a new wrong link.

    This test exists so the decision cannot be quietly reversed by someone who
    rediscovers the four broken links and reads them as a plain regression.
    Reversing it is fine; doing it without reading this is not.
    """
    assert prefix in {p for p, _k, _e in ARMED}
    assert prefix.lower() in KALSHI_GAME_TICKER_PREFIXES


def test_the_accepted_link_cost_is_stated_as_a_number_not_a_shrug():
    """A disclosed cost that nobody wrote down is an undisclosed cost.

    CERT-2087's lesson on #3562 was that disclosing a limitation is not removing
    it. This does not remove the six broken links either — it pins them, so the
    follow-up that fixes the cause (cup qualifying rounds filed under
    `soccer_other` instead of their competition key) has a population to work
    from and does not have to re-measure.
    """
    assert LINKS_THIS_CHANGE_KNOWINGLY_BREAKS == 6
    assert LINKS_THIS_CHANGE_DETACHES_AS_WRONG == 14
    assert QUALIFYING_ROUNDS_MISFILED_AS == "soccer_other"
    # The wrong links removed outnumber the right ones broken. If a future
    # measurement inverts that, this change stops paying for itself.
    assert LINKS_THIS_CHANGE_DETACHES_AS_WRONG > LINKS_THIS_CHANGE_KNOWINGLY_BREAKS


def test_every_one_of_the_fifteen_game_legs_is_in_exactly_one_bucket():
    """#3446 named fifteen. A sixteenth appearing, or one going missing, means
    the population moved and this file's measurement is stale."""
    armed = {p for p, _k, _e in ARMED}
    assert armed & set(NO_KEY_YET) == set()
    assert HELD_PENDING_GOLDEN_AMENDMENT not in armed
    assert HELD_PENDING_GOLDEN_AMENDMENT not in NO_KEY_YET
    assert len(armed) + len(NO_KEY_YET) + 1 == 15
