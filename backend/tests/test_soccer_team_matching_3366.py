"""The soccer pair rule, measured against the whole two-day join population.

#3366 / D50, program step "soccer shadow stamping". `app/utils/nfl_team_matching`
is equality-after-normalization and soccer scores 17/90 on it. This file is the
proof that `app/utils/soccer_team_matching` scores 67/90 on the SAME population
and links no wrong game while doing it.

The corpus (`fixtures/statpal_soccer_join_corpus_20260907.json`) is real on both
sides, read 2026-09-07:

    our_events         90   production `events`, sports.key LIKE 'soccer%',
                            commence_time in [2026-09-07T20:00Z, 2026-09-10T06:00Z)
    statpal_fixtures  621   StatPal v2 `soccer/matches/daily` offsets 1 and 2,
                            deduped by `fallback_id_3` (15 verbatim repeats)

`ACCEPTED_LINKS` pins every link BY ID PAIR, not just the count. A count would
pass while the rule swapped one game for another; all 67 were read by hand when
they were first generated, so a diff here is a claim that needs re-reading, not
a number to bump.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from app.utils.nfl_team_matching import pair_matches as nfl_pair_matches
from app.utils.soccer_team_matching import (
    CLUB_FORM_TOKENS,
    SQUAD_QUALIFIERS,
    soccer_pair_matches,
    soccer_team_matches,
    soccer_tokens,
)

CORPUS = Path(__file__).parent / "fixtures" / "statpal_soccer_join_corpus_20260907.json"

#: The caller's contract, part 3 (module docstring): this is the window the
#: measurement was taken through, and the U19 fixture five hours from its senior
#: game is why it is not wider.
MATCH_WINDOW = timedelta(hours=1)


@pytest.fixture(scope="module")
def corpus() -> dict:
    return json.loads(CORPUS.read_text())


def _join(corpus: dict, rule) -> tuple[list[tuple[int, str]], list[int]]:
    """Run one pair rule over the whole corpus. Returns (accepted, ambiguous)."""
    fixtures = [
        (f, datetime.fromisoformat(f["kickoff"])) for f in corpus["statpal_fixtures"]
    ]
    accepted: list[tuple[int, str]] = []
    ambiguous: list[int] = []
    for event in corpus["our_events"]:
        start = datetime.fromisoformat(event["commence_time"])
        hits = [
            f
            for f, kickoff in fixtures
            if abs(kickoff - start) <= MATCH_WINDOW
            and rule((f["home"], f["away"]), (event["home"], event["away"]))
        ]
        if len(hits) == 1:
            accepted.append((event["event_id"], hits[0]["fallback_id_3"]))
        elif hits:
            ambiguous.append(event["event_id"])
    return sorted(accepted), ambiguous


#: Every link the rule makes over the corpus, `(our event id, StatPal
#: fallback_id_3)`. Read by hand at generation: each comment names one fixture
#: twice, once in each side's spelling.
ACCEPTED_LINKS: tuple[tuple[int, str], ...] = (
    (15223746, "9537419"),  # Boca Juniors v Sao Paulo  ==  Boca Juniors v Sao Paulo
    (15275083, "9537853"),  # Fluminense-RJ v Platense  ==  Fluminense v Platense
    (15290702, "9538492"),  # Palmeiras-SP v LDU Quito  ==  Palmeiras v LDU Quito
    (15291890, "9543653"),  # Vitoria v Grêmio  ==  Vitoria v Gremio
    (
        15293383,
        "9542143",
    ),  # Independiente Santa Fe v Vasco da Gama  ==  Santa Fe v Vasco
    (
        15296353,
        "9544921",
    ),  # Union Santa Fe v Instituto de Córdoba  ==  Union de Santa Fe v Instituto
    (15296749, "9542367"),  # AEK Athens v LASK  ==  AEK Athens v LASK
    (
        15296750,
        "9543323",
    ),  # Club Brugge v Aston Villa  ==  Club Brugge KV v Aston Villa
    (15296751, "9543344"),  # Borussia Dortmund v Villarreal  ==  Dortmund v Villarreal
    (15296752, "9542328"),  # Real Madrid v Inter Milan  ==  Real Madrid v Inter
    (15296753, "9543345"),  # Lille v Real Betis  ==  Lille v Betis
    (15296754, "9542336"),  # Porto v Manchester City  ==  FC Porto v Manchester City
    (15296755, "9543348"),  # Barcelona v Feyenoord  ==  Barcelona v Feyenoord
    (15296756, "9543349"),  # VfB Stuttgart v Viking FK  ==  Stuttgart v Viking
    (15296757, "9543350"),  # Napoli v Arsenal  ==  Napoli v Arsenal
    (
        15296760,
        "9543351",
    ),  # Paris Saint Germain v ŠK Slovan Bratislava  ==  PSG v Slovan Bratislava
    (15297725, "9540022"),  # FC Twente Enschede v SC Telstar  ==  Twente v Telstar
    (15298410, "9546264"),  # Norwich City v Birmingham City  ==  Norwich v Birmingham
    (
        15298412,
        "9546265",
    ),  # Charlton Athletic v Queens Park Rangers  ==  Charlton v QPR
    (
        15298430,
        "9467854",
    ),  # Austin FC v Colorado Rapids  ==  Austin FC v Colorado Rapids
    (
        15298465,
        "9467850",
    ),  # D.C. United v Columbus Crew SC  ==  DC United v Columbus Crew
    (
        15298466,
        "9467855",
    ),  # Chicago Fire v Inter Miami CF  ==  Chicago Fire v Inter Miami
    (
        15298467,
        "9467856",
    ),  # Houston Dynamo v Real Salt Lake  ==  Houston Dynamo v Real Salt Lake
    (15298469, "9467849"),  # CF Montreal v Charlotte FC  ==  CF Montreal v Charlotte
    (
        15298470,
        "9467852",
    ),  # Philadelphia Union v FC Cincinnati  ==  Philadelphia Union v FC Cincinnati
    (15298471, "9467853"),  # Toronto FC v Nashville SC  ==  Toronto FC v Nashville SC
    (
        15298472,
        "9467851",
    ),  # New York City FC v New England Revolution  ==  New York City v New England Revolution
    (
        15298473,
        "9467857",
    ),  # Minnesota United FC v FC Dallas  ==  Minnesota United v FC Dallas
    (15300032, "9541732"),  # Deportes Limache v Cobresal  ==  Limache v Cobresal
    (
        15300112,
        "9541335",
    ),  # Incheon United v Bucheon FC 1995  ==  Incheon v Bucheon FC 1995
    (
        15300191,
        "9542875",
    ),  # Al-Ettifaq v Al-Faisaly KSA FC  ==  Al Ettifaq v Al-Faisaly
    (15300197, "9324493"),  # NEC Nijmegen v Excelsior  ==  Nijmegen v Excelsior
    (15300461, "9543963"),  # Al-Qadsiah v Al-Ahli  ==  Al Qadsiah v Al Ahli SC
    (15300466, "9542877"),  # Al-Ittihad v Al-Fayha  ==  Al Ittihad v Al Fayha
    (15300829, "9544440"),  # Cuiabá v Athletic Club (MG)  ==  Cuiaba v Athletic Club
    (15300870, "9544441"),  # Criciuma v Juventude  ==  Criciuma v Juventude
    (15300988, "9546355"),  # VPS Vaasa v AC Oulu  ==  VPS v AC Oulu
    (15300989, "9546376"),  # FC Lahti v IFK Mariehamn  ==  Lahti v Mariehamn
    (15300990, "9546375"),  # Ilves Tampere v Jaro  ==  Ilves v Jaro
    (15300991, "9546377"),  # TPS Turku v SJK Seinäjoki  ==  TPS v SJK
    (15300992, "9546356"),  # IF Gnistan v KuPS Kuopio  ==  Gnistan v KuPS
    (15301129, "9546357"),  # HJK Helsinki v FC Inter Turku  ==  HJK v Inter Turku
    (15301142, "9543964"),  # Al-Kholood v Al-Shabab  ==  Al Kholood v Al Shabab
    (15301143, "9545032"),  # Al-Nassr v Abha Club  ==  Al Nassr v Abha
    (15301144, "9543965"),  # Al-Fateh v Diriyah Club  ==  Al Fateh v Al Diriyah
    (15301191, "9541143"),  # Moreirense FC v Benfica  ==  Moreirense v Benfica
    (15301237, "9544443"),  # Fortaleza v Avai  ==  Fortaleza v Avai
    (
        15301238,
        "9544442",
    ),  # Botafogo-SP v Grêmio Novorizontino  ==  Botafogo SP v Novorizontino
    (
        15301240,
        "9545713",
    ),  # Operario PR v Clube de Regatas Brasil  ==  Operario-PR v CRB
    (15301248, "9541917"),  # Daejeon Citizen v FC Anyang  ==  Daejeon v Anyang
    (15301249, "9541918"),  # Gangwon FC v Jeonbuk Hyundai Motors  ==  Gangwon v Jeonbuk
    (15301250, "9541919"),  # Gwangju FC v Jeju United FC  ==  Gwangju FC v Jeju SK
    (
        15301253,
        "9541985",
    ),  # Nordic United FC v IFK Värnamo  ==  Nordic United v Varnamo
    (15301255, "9541687"),  # Ljungskile SK v Norrby IF  ==  Ljungskile v Norrby
    (15301283, "9545757"),  # Wrexham AFC v Burnley  ==  Wrexham v Burnley
    (15301284, "9545754"),  # Cardiff City v Stoke City  ==  Cardiff v Stoke
    (15301285, "9545756"),  # Watford v Preston North End  ==  Watford v Preston
    (15301286, "9545755"),  # Southampton v Swansea City  ==  Southampton v Swansea
    (15301287, "9545758"),  # Bolton Wanderers v West Ham United  ==  Bolton v West Ham
    (15301288, "9542013"),  # Bournemouth v Lincoln City  ==  Bournemouth v Lincoln
    (
        15301289,
        "9542019",
    ),  # Leyton Orient v Bradford City  ==  Leyton Orient v Bradford City
    (
        15301290,
        "9542015",
    ),  # Crystal Palace v Middlesbrough  ==  Crystal Palace v Middlesbrough
    (15301291, "9542026"),  # Sunderland v Hull City  ==  Sunderland v Hull
    (15301292, "9542023"),  # Millwall v Newcastle United  ==  Millwall v Newcastle
    (15301293, "9542570"),  # Chelsea v Leeds United  ==  Chelsea v Leeds
    (15305489, "9326664"),  # Rangers v St Mirren  ==  Rangers v St. Mirren
    (15305594, "9326665"),  # St Johnstone v Celtic  ==  St Johnstone v Celtic
)


class TestTheCorpusIsWhatItClaims:
    def test_population_sizes(self, corpus):
        assert len(corpus["our_events"]) == 90
        assert len(corpus["statpal_fixtures"]) == 621

    def test_fixture_ids_are_unique_because_the_board_repeats_itself(self, corpus):
        """The dedupe is part 1 of the caller's contract, so it is asserted.

        15 of StatPal's 636 raw rows are verbatim repeats carrying the same
        `fallback_id_3`; the corpus is the deduped view and must stay one.
        """
        ids = [f["fallback_id_3"] for f in corpus["statpal_fixtures"]]
        assert len(ids) == len(set(ids))
        assert corpus["provenance"]["duplicate_rows_dropped"] == 15

    def test_the_board_carries_the_reserve_and_youth_sides_the_guard_exists_for(
        self, corpus
    ):
        """If these ever leave the corpus, the squad guard stops being tested."""
        names = {f["home"] for f in corpus["statpal_fixtures"]} | {
            f["away"] for f in corpus["statpal_fixtures"]
        }
        for shadow in (
            "Everton U21",
            "Wolves U21",
            "Atlanta United 2",
            "Atl. Madrid U19",
        ):
            assert shadow in names, shadow


class TestTheRuleOverTheWholePopulation:
    def test_the_nfl_rule_is_the_control_and_it_scores_17(self, corpus):
        """Why this module exists at all. 17/90 is not a usable anchor channel."""
        accepted, ambiguous = _join(corpus, nfl_pair_matches)
        assert len(accepted) == 17
        assert ambiguous == []

    def test_this_rule_links_exactly_the_pinned_67(self, corpus):
        accepted, ambiguous = _join(corpus, soccer_pair_matches)
        assert ambiguous == [], "a second candidate means a receipt, never a link"
        assert tuple(accepted) == ACCEPTED_LINKS

    def test_every_link_is_one_to_one_in_both_directions(self, corpus):
        """Two of our rows claiming one fixture would be a twin being linked twice."""
        accepted, _ = _join(corpus, soccer_pair_matches)
        assert len({e for e, _ in accepted}) == len(accepted)
        assert len({f for _, f in accepted}) == len(accepted)

    def test_no_link_reaches_a_squad_qualified_fixture(self, corpus):
        """The direct form of the guard: no accepted fixture names a B/U/W side."""
        by_id = {f["fallback_id_3"]: f for f in corpus["statpal_fixtures"]}
        accepted, _ = _join(corpus, soccer_pair_matches)
        for _, fixture_id in accepted:
            fixture = by_id[fixture_id]
            for name in (fixture["home"], fixture["away"]):
                assert not any(
                    SQUAD_QUALIFIERS.match(t) for t in soccer_tokens(name)
                ), f"{fixture['home']} v {fixture['away']}"

    def test_the_23_misses_are_accounted_for_by_the_boards_own_span(self, corpus):
        """5 past the tail, 1 before the head — read-window, not name, defects."""
        accepted, _ = _join(corpus, soccer_pair_matches)
        linked = {e for e, _ in accepted}
        kickoffs = [
            datetime.fromisoformat(f["kickoff"]) for f in corpus["statpal_fixtures"]
        ]
        head, tail = min(kickoffs), max(kickoffs)
        misses = [e for e in corpus["our_events"] if e["event_id"] not in linked]
        assert len(misses) == 23
        after = [e for e in misses if datetime.fromisoformat(e["commence_time"]) > tail]
        before = [
            e for e in misses if datetime.fromisoformat(e["commence_time"]) < head
        ]
        assert len(after) == 5, [e["home"] for e in after]
        assert len(before) == 1, [e["home"] for e in before]


class TestTheThreeTiers:
    @pytest.mark.parametrize(
        "statpal,ours",
        [
            ("Napoli", "Napoli"),
            ("Gremio", "Grêmio"),  # the fold, on a soccer input
            ("Atl. Madrid", "Atl Madrid"),  # punctuation only
            ("St. Mirren", "St Mirren"),
        ],
    )
    def test_equality_is_the_degenerate_subset_and_still_matches(self, statpal, ours):
        assert soccer_team_matches(statpal, ours)

    @pytest.mark.parametrize(
        "statpal,ours",
        [
            ("Wrexham", "Wrexham AFC"),
            ("Cardiff", "Cardiff City"),
            ("Instituto", "Instituto de Córdoba"),
            ("Dortmund", "Borussia Dortmund"),
            ("Nijmegen", "NEC Nijmegen"),
            ("FC Porto", "Porto"),  # the long side is OURS here; direction is free
            ("DC United", "D.C. United"),  # the single-letter join
        ],
    )
    def test_token_subset(self, statpal, ours):
        assert soccer_team_matches(statpal, ours)

    @pytest.mark.parametrize(
        "statpal,ours",
        [
            ("PSG", "Paris Saint Germain"),
            ("QPR", "Queens Park Rangers"),
            ("CRB", "Clube de Regatas Brasil"),  # needs the club-form-stripped spelling
        ],
    )
    def test_initialism(self, statpal, ours):
        assert soccer_team_matches(statpal, ours)

    def test_an_initialism_needs_two_letters_and_two_words(self):
        """A single letter against anything is not evidence of a club."""
        assert not soccer_team_matches("B", "Barcelona")
        assert not soccer_team_matches("BA", "Barcelona")

    def test_a_one_letter_initialism_is_refused_even_when_it_is_correct(self):
        """`FC Porto` stripped of its club form initialises to `p`, and `P` is
        not a club. The two-character floor is what stops that pairing."""
        assert not soccer_team_matches("P", "FC Porto")
        assert not soccer_team_matches("FC Porto", "P")


class TestTheTrapsTheBoardIsFullOf:
    @pytest.mark.parametrize(
        "statpal,ours",
        [
            ("Everton U21", "Everton"),
            ("Wolves U21", "Wolverhampton Wanderers"),
            ("Atl. Madrid U19", "Atlético Madrid"),
            ("Atlanta United 2", "Atlanta United"),
            ("New York City II", "New York City"),
            ("Racing Club 2", "Racing Club"),
            ("Barcelona W", "Barcelona"),
            ("Barcelona Women", "Barcelona"),
            ("Chelsea Reserves", "Chelsea"),
        ],
    )
    def test_a_different_squad_of_the_same_club_is_not_the_club(self, statpal, ours):
        assert not soccer_team_matches(statpal, ours)

    def test_the_squad_guard_does_not_eat_a_club_whose_name_says_juniors(self):
        """`jrs` is not a marker: Boca Juniors are a senior club."""
        assert soccer_team_matches("Boca Juniors", "Boca Juniors")
        assert soccer_team_matches("Argentinos Juniors", "Argentinos Juniors FC")

    @pytest.mark.parametrize(
        "statpal,ours",
        [
            ("Manchester United", "Manchester City"),
            ("Man Utd", "Man City"),
            ("Sheffield United", "Sheffield Wednesday"),
            ("Inter", "Inter Miami"),  # subset would take it; the guard is the window
        ],
    )
    def test_two_clubs_are_not_one(self, statpal, ours):
        if statpal == "Inter":
            # DOCUMENTED, not asserted away: `Inter` IS a subset of `Inter
            # Miami`, and this rule says so. Nothing in a NAME can tell them
            # apart — what does is that Serie A and MLS do not kick off within
            # an hour of each other, which is the caller's ±1h window and its
            # one-match refusal, not this function.
            assert soccer_team_matches(statpal, ours)
            return
        assert not soccer_team_matches(statpal, ours)

    def test_the_named_reserve_side_residual_is_pinned_where_it_can_be_seen(self):
        """`Real Madrid Castilla` is Real Madrid's B team and this rule matches it.

        Pinned deliberately, with the reason in the module docstring: no suffix
        rule catches a named B-team, and a from-memory list of them is exactly
        the unmeasured vocabulary this module refuses to write. The day a
        measured list exists, this assertion flips and the change is visible.
        """
        assert soccer_team_matches("Real Madrid Castilla", "Real Madrid")


class TestRefusals:
    @pytest.mark.parametrize("blank", [None, "", "   ", "!!!"])
    def test_a_blank_name_matches_nothing_including_another_blank(self, blank):
        assert not soccer_team_matches(blank, "Chelsea")
        assert not soccer_team_matches("Chelsea", blank)
        assert not soccer_team_matches(blank, blank)

    def test_a_name_that_is_only_club_form_words_identifies_no_club(self):
        assert not soccer_team_matches("FC", "FC Porto")
        assert not soccer_team_matches("AC", "AC Milan")

    def test_two_club_form_only_names_do_not_pair_with_each_other(self):
        """The reason the empty-core refusal runs before anything else.

        `FC` and `FC` are equal strings and still name no club; a rule that
        answered on equality first would link two rows whose team names never
        arrived.
        """
        assert not soccer_team_matches("FC", "FC")
        assert not soccer_team_matches("the club", "The Club")

    def test_club_form_tokens_never_include_united_or_city(self):
        """The Manchester rule, as data rather than as a test of one pair."""
        assert "united" not in CLUB_FORM_TOKENS
        assert "city" not in CLUB_FORM_TOKENS
        assert "real" not in CLUB_FORM_TOKENS


class TestOrientation:
    def test_home_matches_home_and_away_matches_away(self):
        assert soccer_pair_matches(("Wrexham", "Burnley"), ("Wrexham AFC", "Burnley"))

    def test_the_reverse_fixture_is_a_different_game(self):
        assert not soccer_pair_matches(
            ("Wrexham", "Burnley"), ("Burnley", "Wrexham AFC")
        )


class TestTokenisation:
    def test_runs_of_single_letters_join_and_a_lone_letter_does_not(self):
        assert soccer_tokens("D.C. United") == ["dc", "united"]
        assert soccer_tokens("U. Espanola") == ["u", "espanola"]
        assert soccer_tokens("A.S. Roma") == ["as", "roma"]

    def test_a_run_of_three_single_letters_joins_as_one(self):
        assert soccer_tokens("F.C.K. Copenhagen") == ["fck", "copenhagen"]

    def test_whole_words_are_never_joined_to_each_other(self):
        assert soccer_tokens("Wrexham AFC") == ["wrexham", "afc"]
        assert soccer_tokens("Preston North End") == ["preston", "north", "end"]

    def test_the_fold_is_the_one_soccer_needs(self):
        """Pinned on soccer inputs so an NFL-side change to the shared
        normalizer fails a test that says SOCCER."""
        assert soccer_tokens("Grêmio") == ["gremio"]
        assert soccer_tokens("Atlético Madrid") == ["atletico", "madrid"]
        assert soccer_tokens("SJK Seinäjoki") == ["sjk", "seinajoki"]
        assert soccer_tokens("Al-Ettifaq") == ["al", "ettifaq"]
        assert soccer_tokens("  Boca   Juniors  ") == ["boca", "juniors"]


class TestThisModuleHasNoCallerYetAndThatIsDeliberate:
    """A rule with no caller is a declaration nobody drives, so say why.

    The consumer is a soccer entry in `stamp_v1_statpal_fixtures.LEAGUES`, and
    it cannot be written yet for two reasons that are not this file's to fix:

      * `LeagueSpec` is built around `/v1/{sport}/season-schedule`, and soccer
        has no such endpoint — its schedule is v2 `matches/daily?offset=N`,
        one day per call.
      * The id a soccer anchor is keyed on is `fallback_id_3`, which reaches
        `StatPalFixture` on the #3366 branch that is not merged yet.

    So this asserts the ABSENCE, the way `test_statpal_live_anchor_entrypoint_3094`
    asserts its own, so that the next session reads the reason before adding a
    fifth stamper.
    """

    def test_soccer_is_not_a_stamped_league_yet(self):
        from app.tasks.stamp_v1_statpal_fixtures import LEAGUES

        assert not any(key.startswith("soccer") for key in LEAGUES), (
            "a soccer LeagueSpec landed: wire soccer_pair_matches into it, and "
            "delete this test in the same commit"
        )
