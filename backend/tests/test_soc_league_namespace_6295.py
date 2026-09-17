"""#6295 — a soccer ticker never borrows another competition's club abbreviations.

WHAT A READER SAW. On 2026-09-16 the La Liga page carried a card reading
**"Bayer Leverkusen v Athletic Club"** with a green LIVE chip, and the Serie A
page carried **"Paris Saint-Germain v Genoa"**. Neither fixture exists: Bayer
Leverkusen do not play in Spain and PSG do not play in Italy. Alex saw the first
one on the live rail (#6295, comment 2026-09-17T00:29Z).

WHAT WENT WRONG. #2706 namespaced ``_KALSHI_TEAM_ABBREVS`` by SPORT, and #3672
closed the unregistered-prefix hole. Both stopped one sport answering another's
ticker. But ``_SPORT_KEY_TO_ABBREV_SUFFIX`` maps SIX soccer competitions — EPL,
La Liga, Bundesliga, Serie A, Ligue 1 and the Champions League — onto the single
``_soc`` suffix, so the very same collision stayed open one level down, INSIDE
soccer::

    KXLALIGAGAME-26SEP16LEVATH   "Levante vs Bilbao"
        lev + "_soc" -> "lev_soc" -> Bayer Leverkusen   (the BUNDESLIGA block)

    KXSERIEAGAME-26SEP20PARGEN   "Parma Calcio vs Genoa"
        par + "_soc" -> "par_soc" -> Paris Saint-Germain (the UCL block)

One flat namespace cannot hold both Levante and Bayer Leverkusen under ``lev``.
That is why the fix declares an OWNER rather than widening the map: there is no
value for ``lev_soc`` that is right for both leagues.

THE SPECIMENS ARE NOT INVENTED. Every ticker and every market name in
``PHANTOM_FIXTURES`` was read off production on 2026-09-16 by replaying the
shipping resolver over all 1,400 open Kalshi ``A vs B`` markets. The three events
named below were live rows: 15312871 (LIVE), 15312872 and 15312896, all
``commence_time_source='kalshi'`` with no anchor of either kind.

WHY THE FIX IS A REFUSAL AND NOT A REWRITE. ``_resolve_team_abbrev``'s own
docstring already says a miss is strictly better than a wrong team, because a
miss falls through to the market-title parse. Production proves it: the UEL
ticker ``KXUELGAME-26SEP16LEVCEL`` has an unregistered prefix, so its codes never
resolve at all and the title survives as "Leverkusen / NK Celje" — correct. This
fix makes La Liga and Serie A behave the way that ticker already does.

WHY NOT "LET THE TITLE ALWAYS WIN FOR SOCCER". Measured and REJECTED. Over the
same corpus it fixes 9 markets and DEGRADES 5 good ones: ``Minnesota United /
LA Galaxy`` becomes ``Minnesota / Los Angeles G``, ``St. Louis City SC`` becomes
``Saint Louis``, ``Paris Saint-Germain`` becomes ``PSG``. The ticker override
exists for exactly that and is right to. ``STILL_TICKER_PARSED`` pins those.

WHY THERE ARE FOUR ARMS. The phantom arm alone would pass if someone deleted the
soccer block entirely, so ``STILL_TICKER_PARSED`` pins the soccer tickers that
were already right. ``test_the_specimen_reaches_the_new_gate`` exists because a
refusal test goes VACUOUS the moment its specimen starts being refused one gate
earlier — it asserts the colliding key is still IN the map and still resolves for
its OWN league, so the arm under test is the one doing the work. And a fixed
table goes stale the moment a ``_soc`` key is added, so
``test_every_soc_abbreviation_declares_which_competition_owns_it`` fails CI if
the map and the ownership table ever drift apart.
"""

from __future__ import annotations

import pytest

from app.utils.prediction_market_matching import (
    _KALSHI_TEAM_ABBREVS,
    _SPORT_KEY_TO_ABBREV_SUFFIX,
    extract_matchup_with_ticker_fallback,
    extract_team_codes_from_ticker,
    extract_teams_from_ticker,
)

# The symbols the fix introduces are imported lazily inside the tests that need
# them. A module-level import would turn the whole file into a COLLECTION ERROR
# before the fix, which makes every arm vacuous instead of red — the red has to
# be an assertion. (Same reasoning as tests/test_kalshi_abbrev_sport_namespace_2706.py.)


# ---------------------------------------------------------------------------
# Arm 1 — the three phantoms a reader could see on production.
# ---------------------------------------------------------------------------

#: (ticker, market's own name, correct a, correct b, the club we minted instead)
PHANTOM_FIXTURES = [
    # La Liga, event 15312871, LIVE on the league page with a green chip.
    # `lev` is the Bundesliga block's Bayer Leverkusen; here it means Levante.
    (
        "KXLALIGAGAME-26SEP16LEVATH",
        "Levante vs Bilbao",
        "Levante",
        "Bilbao",
        "Bayer Leverkusen",
    ),
    # The same segment on the three prop boards that hang off that fixture.
    (
        "KXLALIGATOTAL-26SEP16LEVATH",
        "Levante vs Bilbao: Total Goals",
        "Levante",
        "Bilbao",
        "Bayer Leverkusen",
    ),
    (
        "KXLALIGASPREAD-26SEP16LEVATH",
        "Levante vs Bilbao: Spread",
        "Levante",
        "Bilbao",
        "Bayer Leverkusen",
    ),
    (
        "KXLALIGABTTS-26SEP16LEVATH",
        "Levante vs Bilbao: BTTS",
        "Levante",
        "Bilbao",
        "Bayer Leverkusen",
    ),
    # La Liga, event 15312872. The collision is on side B here, not side A —
    # the refusal must not be orientation-dependent.
    (
        "KXLALIGAGAME-26SEP20VILLEV",
        "Villarreal vs Levante",
        "Villarreal",
        "Levante",
        "Bayer Leverkusen",
    ),
    # Serie A, event 15312896. `par` is the CHAMPIONS LEAGUE block's PSG; here
    # it means Parma. A different owning competition from the La Liga cases, so
    # the arm is not pinned to one entry of the table.
    (
        "KXSERIEAGAME-26SEP20PARGEN",
        "Parma Calcio vs Genoa",
        "Parma Calcio",
        "Genoa",
        "Paris Saint-Germain",
    ),
]


@pytest.mark.parametrize(
    "ticker,market_name,team_a,team_b,the_club_we_minted", PHANTOM_FIXTURES
)
def test_a_foreign_league_code_no_longer_names_the_fixture(
    ticker, market_name, team_a, team_b, the_club_we_minted
):
    """The reader-scale assertion: what the matching path actually hands on.

    Asserting only that `_resolve_team_abbrev` returns None would prove the gate
    fires without proving the fixture gets a correct name — reaching a helper's
    documented arm is not the fix until it is measured at the reader's scale.
    """
    matchup = extract_matchup_with_ticker_fallback(market_name, ticker)

    assert matchup is not None, f"{ticker} must still produce a matchup"
    assert (matchup.team_a, matchup.team_b) == (team_a, team_b)
    # And say out loud that the phantom club is gone from BOTH sides, so the
    # test cannot pass by moving it from one to the other.
    assert the_club_we_minted not in (matchup.team_a, matchup.team_b)


@pytest.mark.parametrize(
    "ticker,market_name,team_a,team_b,the_club_we_minted", PHANTOM_FIXTURES
)
def test_the_ticker_itself_declines_rather_than_answering_wrongly(
    ticker, market_name, team_a, team_b, the_club_we_minted
):
    """The mechanism, stated separately from its consequence.

    `extract_teams_from_ticker` must return None — a refusal — rather than a
    different pair. A fix that swapped in some OTHER map's answer would pass the
    reader-scale arm above by luck; this pins that the route is abstention.
    """
    assert extract_teams_from_ticker(ticker) is None
    assert extract_team_codes_from_ticker(ticker) is None


# ---------------------------------------------------------------------------
# Arm 2 — soccer tickers that were already right and must not move.
# ---------------------------------------------------------------------------

#: (ticker, market name, team_a, team_b) — all measured unchanged by the fix.
STILL_TICKER_PARSED = [
    # A Bundesliga ticker asking for its OWN Bundesliga codes. This is the exact
    # pair of keys the La Liga cases are refused for; the owner test is that the
    # owning league still gets them.
    (
        "KXBUNDESLIGAGAME-26SEP19BMGM05",
        "M´gladbach vs Mainz",
        "Borussia Monchengladbach",
        "Mainz",
    ),
    # La Liga asking for La Liga codes. `ath` also has an MLB bare owner, so this
    # doubles as proof the #2706 layer still runs underneath.
    ("KXLALIGAGAME-26SEP19ATHALA", "Bilbao vs Alaves", "Athletic Club", "Alaves"),
    # Ligue 1 asking for Ligue 1 codes — and the reason "title always wins" was
    # rejected: the ticker's "Paris Saint-Germain" is better than the title's "PSG".
    (
        "KXLIGUE1GAME-26SEP20OLMPSG",
        "Marseille vs PSG",
        "Marseille",
        "Paris Saint-Germain",
    ),
    ("KXLIGUE1GAME-26SEP19OLREN", "Lyon vs Stade Rennais", "Lyon", "Rennes"),
    # MLS is its own `_mls` namespace and must be untouched by a `_soc` rule —
    # and its ticker names are the ones the override exists to protect
    # ("Los Angeles G" is what the title would have given).
    (
        "KXMLSGAME-26SEP19MINLAG",
        "Minnesota vs Los Angeles G",
        "Minnesota United",
        "LA Galaxy",
    ),
    (
        "KXMLSGAME-26SEP19STLTOR",
        "Saint Louis vs Toronto",
        "St. Louis City SC",
        "Toronto FC",
    ),
]


@pytest.mark.parametrize("ticker,market_name,team_a,team_b", STILL_TICKER_PARSED)
def test_a_league_still_gets_its_own_codes(ticker, market_name, team_a, team_b):
    assert extract_teams_from_ticker(ticker) == (team_a, team_b)

    matchup = extract_matchup_with_ticker_fallback(market_name, ticker)
    assert matchup is not None
    assert (matchup.team_a, matchup.team_b) == (team_a, team_b)


#: Non-soccer tickers. A `_soc` rule that reached these would be a catastrophe,
#: so the blast radius is asserted rather than assumed.
UNTOUCHED_BY_A_SOCCER_RULE = [
    ("KXNBAGAME-26FEB21DETCHI", "Pistons", "Bulls"),
    ("KXNFLGAME-26SEP13ATLPIT", "Falcons", "Steelers"),
]


@pytest.mark.parametrize("ticker,team_a,team_b", UNTOUCHED_BY_A_SOCCER_RULE)
def test_other_sports_are_untouched(ticker, team_a, team_b):
    assert extract_teams_from_ticker(ticker) == (team_a, team_b)


#: The OTHER reader of `_resolve_team_abbrev`: a Kalshi OUTCOME ticker, which
#: names one team per rung (`KXSB-27-LAR`). It derives its own competition and so
#: has its own plumbing, and a mutation pass found nothing pinned it — the fix
#: was already correct here and the suite was simply blind to the call site.
#: (ticker, expected — None means the code is another competition's club)
OUTCOME_TICKERS = [
    # La Liga rung whose code is the Bundesliga's: refused.
    ("KXLALIGAGAME-26SEP16LEVATH-LEV", None),
    # The other rung of the SAME board, whose code La Liga does own: kept.
    ("KXLALIGAGAME-26SEP16LEVATH-ATH", ("ath", "Athletic Club")),
    # The owning league still gets the very code La Liga was refused.
    ("KXBUNDESLIGAGAME-26SEP19BMGM05-LEV", ("lev", "Bayer Leverkusen")),
    # Serie A rung whose code is the Champions League block's PSG: refused.
    ("KXSERIEAGAME-26SEP20PARGEN-PAR", None),
    # Non-soccer rung: untouched.
    ("KXSB-27-LAR", ("lar", "Rams")),
]


@pytest.mark.parametrize("ticker,expected", OUTCOME_TICKERS)
def test_the_outcome_ticker_path_obeys_the_same_ownership(ticker, expected):
    from app.utils.prediction_market_matching import (
        extract_team_code_from_outcome_ticker,
    )

    assert extract_team_code_from_outcome_ticker(ticker) == expected


def test_a_cup_ticker_may_still_use_every_domestic_code():
    """A continental competition draws its field from everywhere.

    Refusing domestic codes for a Champions League ticker would spend correct
    resolutions to buy nothing, so `_SOC_LEAGUES_WITH_OWN_VOCABULARY` excludes
    the cups. This pins that decision as a decision.
    """
    from app.utils.prediction_market_matching import (
        _SOC_LEAGUES_WITH_OWN_VOCABULARY,
        _resolve_team_abbrev,
    )

    assert "soccer_uefa_champs_league" not in _SOC_LEAGUES_WITH_OWN_VOCABULARY

    # Real Madrid is declared to La Liga; a UCL ticker still gets it.
    assert (
        _resolve_team_abbrev("rma", "_soc", "soccer_uefa_champs_league")
        == "Real Madrid"
    )
    # ...while the same code is refused to a DIFFERENT domestic league.
    assert _resolve_team_abbrev("rma", "_soc", "soccer_italy_serie_a") is None


def test_an_unknown_asker_keeps_the_pre_fix_answer():
    """`sport_key=None` must not refuse.

    The `sport_suffix_override` caller is the #3672 repair, which replays a
    historical resolution to prove a stored name was minted by that bug. A rule
    that postdates the row must not re-decide it, or the repair stops being able
    to tell "minted by the bug" from "merely resembles it".
    """
    from app.utils.prediction_market_matching import _resolve_team_abbrev

    assert _resolve_team_abbrev("lev", "_soc") == "Bayer Leverkusen"
    assert _resolve_team_abbrev("lev", "_soc", None) == "Bayer Leverkusen"

    # And through the public door the repair actually uses.
    assert extract_team_codes_from_ticker(
        "KXLALIGAGAME-26SEP16LEVATH", sport_suffix_override="_soc"
    ) == (("lev", "Bayer Leverkusen"), ("ath", "Athletic Club"))


# ---------------------------------------------------------------------------
# Arm 3 — anti-vacuity. The specimen must REACH the arm under test.
# ---------------------------------------------------------------------------


def test_the_specimen_reaches_the_new_gate():
    """Prove the phantom arm is not passing for an earlier reason.

    A refusal test goes vacuous the instant its specimen starts being refused one
    gate earlier — the assertion still passes and the clause under test is dead.
    So: the colliding keys are still IN the map, and they still resolve for the
    competition that owns them. If someone deletes `lev_soc`, this arm goes red
    and tells them the phantom tests above stopped testing anything.
    """
    from app.utils.prediction_market_matching import (
        _SOC_ABBREV_LEAGUE_OWNER,
        _resolve_team_abbrev,
    )

    assert _KALSHI_TEAM_ABBREVS["lev_soc"] == "Bayer Leverkusen"
    assert _KALSHI_TEAM_ABBREVS["par_soc"] == "Paris Saint-Germain"

    assert _SOC_ABBREV_LEAGUE_OWNER["lev"] == "soccer_germany_bundesliga"
    assert _SOC_ABBREV_LEAGUE_OWNER["par"] == "soccer_uefa_champs_league"

    # The owning competition still gets its club — the refusal is targeted, not
    # a deletion by another name.
    assert (
        _resolve_team_abbrev("lev", "_soc", "soccer_germany_bundesliga")
        == "Bayer Leverkusen"
    )
    # ...and the asking competition is refused it.
    assert _resolve_team_abbrev("lev", "_soc", "soccer_spain_la_liga") is None


def test_the_refusal_cannot_fire_outside_the_shared_soccer_namespace():
    """The predicate itself, at its edges."""
    from app.utils.prediction_market_matching import (
        _soc_key_belongs_to_another_competition,
    )

    # Right code, right foreign owner, but not the `_soc` namespace.
    assert not _soc_key_belongs_to_another_competition(
        "lev", "_mls", "soccer_spain_la_liga"
    )
    assert not _soc_key_belongs_to_another_competition(
        "lev", "", "soccer_spain_la_liga"
    )
    # Undeclared code: nothing is known, so nothing is refused.
    assert not _soc_key_belongs_to_another_competition(
        "zzz", "_soc", "soccer_spain_la_liga"
    )
    # The owning league is never refused its own key.
    assert not _soc_key_belongs_to_another_competition(
        "lev", "_soc", "soccer_germany_bundesliga"
    )
    # The one case that must fire.
    assert _soc_key_belongs_to_another_competition(
        "lev", "_soc", "soccer_spain_la_liga"
    )


# ---------------------------------------------------------------------------
# Arm 4 — the guard on the CLASS, so the table cannot drift from the map.
# ---------------------------------------------------------------------------


def test_every_soc_abbreviation_declares_which_competition_owns_it():
    """Add a `_soc` key and you MUST declare its competition.

    The sibling rule for `_BARE_ABBREV_OWNER` (#2706) is what keeps that table
    honest; this is the same rule for the shared soccer namespace. Without it the
    next club added to the map re-opens #6295 silently.

    `_socN` keys (`bay_soc2`, `mon_soc2`, …) are deliberately excluded: the
    lookup composes `abbrev + "_soc"`, so a `_soc2` key can only be reached by an
    abbreviation literally ending in `_soc` and is unreachable by construction.
    """
    from app.utils.prediction_market_matching import _SOC_ABBREV_LEAGUE_OWNER

    reachable = {
        key[: -len("_soc")]
        for key in _KALSHI_TEAM_ABBREVS
        if key.endswith("_soc")
    }
    undeclared = sorted(reachable - set(_SOC_ABBREV_LEAGUE_OWNER))

    assert not undeclared, (
        "these _soc abbreviations declare no owning competition, so a ticker "
        f"from any soccer league can still be handed them: {undeclared}. "
        "Add them to _SOC_ABBREV_LEAGUE_OWNER (#6295)."
    )


def test_the_ownership_table_names_only_real_soccer_competitions():
    """An owner that is not a soccer sport key can never equal an asker.

    A typo'd league name would make the entry inert — it would refuse EVERY
    asker for that code instead of all-but-one, which is a silent coverage loss
    rather than a red test. So the values are checked against the suffix map.
    """
    from app.utils.prediction_market_matching import _SOC_ABBREV_LEAGUE_OWNER

    for abbrev, owner in sorted(_SOC_ABBREV_LEAGUE_OWNER.items()):
        assert _SPORT_KEY_TO_ABBREV_SUFFIX.get(owner) == "_soc", (
            f"{abbrev!r} is declared to {owner!r}, which is not a competition "
            "that resolves in the _soc namespace"
        )


def test_no_abbreviation_is_declared_to_a_competition_that_cannot_ask():
    """Every owning league must be reachable as an asker, or its keys are dead.

    `_SOC_LEAGUES_WITH_OWN_VOCABULARY` is derived from the table's own values, so
    this pins that the derivation kept all five domestic leagues.
    """
    from app.utils.prediction_market_matching import (
        _SOC_ABBREV_LEAGUE_OWNER,
        _SOC_LEAGUES_WITH_OWN_VOCABULARY,
    )

    assert _SOC_LEAGUES_WITH_OWN_VOCABULARY == {
        "soccer_epl",
        "soccer_spain_la_liga",
        "soccer_germany_bundesliga",
        "soccer_italy_serie_a",
        "soccer_france_ligue_one",
    }
    assert set(_SOC_ABBREV_LEAGUE_OWNER.values()) == (
        _SOC_LEAGUES_WITH_OWN_VOCABULARY | {"soccer_uefa_champs_league"}
    )
