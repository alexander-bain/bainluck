"""#7261 — the ANSWERS card is headed by a market that answers something.

WHAT THE READER SAW. Alex, `https://bainluck.com/search?q=dodgers`: the section
headed **ANSWERS**, card titled **DODGERS**, led with

    Player Props    Shay Whitcomb: Home Runs O/U 0.5    7%

— a 7% home-run prop for a player on the OPPOSING team, offered as the answer to
a fan typing their club's name. The `First 5 Innings Winner` market in the same
family would have printed `Los Angeles Dodgers 65%`.

STILL LIVE WHEN THIS WAS BUILT, on a different query. `q=dodgers` had drifted to
an honest headline by 2026-09-19 21:50Z; `q=astros` reproduced it exactly in the
same minute, and that payload is the specimen every fixture below is cut from:

    HEADLINE  Atlanta Braves vs. Houston Astros - Player Props
                Grant Holmes: Strikeouts O/U 3.5   57%      (25 legs, sum 271%)
    member    Atlanta Braves vs. Houston Astros - First 5 Innings Winner
                Houston Astros 45.5% · Atlanta Braves 40%   ( 3 legs, sum  99%)
    member    Atlanta Braves vs. Houston Astros           <- bare-matchup container
                1st 5 Innings O/U 2.5 78.5% · O/U 3.5 64.5%
    member    Dorados de Chihuahua vs Astros de Jalisco   <- #7259, correctly last

THE MECHANISM. `_compose_futures_families` took `headline = members[0]`. A
`- Player Props` container is a BUNDLE of independent binaries, so it has no
leading outcome in any sense a reader can use — `max()` over a set that is not a
partition is not a favourite. #5516 mirrored: that ship withdraws an exclusive
board summing far UNDER 100% because the SET cannot be read; this is the
over-100% side of the same coin.

🔴 THE FIRST CUT WAS KEYED ON `mutually_exclusive` AND IT WAS WRONG. The flag
does read `False` on the bundles, but it reads `False` on plain one-leg
propositions too — `NBA: Stephen Curry to leave Warriors?` (0.02),
`LeBron James to Announce his Retirement` (0.02), `Bronny James to Play for the
Lakers` (0.92) — which are the CORRECT headlines for their families. Measured
live across 15 club queries, that rule moved 6 and four of them somewhere worse:
`q=warriors` skipped the Curry market and landed on `New Zealand Warriors vs
Newcastle Knights`, an NRL rugby fixture, defeating #7259's own wrong-sport
demotion. The shipped rule reads the LEG SUM, which is self-evidencing, and
`TestTheStoredFlagIsNotConsulted` below is what stops anyone going back.

THE INVERSION THE ISSUE WARNED ABOUT. #7261 declined to propose a fix because
the obvious rule — "prefer the member whose leading outcome names the entity" —
is right for `dodgers` (the club is IN the answer space) and wrong for
`lebron james` (the entity is in the market NAME, the answer space is teams), so
it demotes the correct headline. The rule shipped here never reads the query,
which is why `TestTheEntityInversionIsNotReintroduced` can drive the SAME
composer with a LeBron family and pin the headline unmoved.

MEASURED ON PRODUCTION BEFORE IT SHIPPED — 15 club queries, 2 move: `astros`
(the ship) and `mets`, which was heading `Philadelphia Phillies vs. New York
Mets` with `1st 5 Innings O/U 3.5 at 99.65%`, an 18-leg container summing 704%
printing a near-certainty about a game it does not price. Thirteen unchanged.

RED-FIRST. Revert `_family_headline_index`'s loop body to `return 0` and
`TestTheAstrosSpecimen` fails on the headline name; no import moves, so there is
no collection error to mistake for a failure (gotcha #124).
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.routes.events import (
    _compose_futures_families,
    _family_headline_index,
    _futures_board_is_not_a_partition,
)


def _outcome(name, prob, oid):
    """An outcome shaped to SURVIVE `_search_surviving_legs`.

    The predicate deliberately judges the legs the card draws, not the raw rows
    (#5516: market 57574860 sums to 11.0 on raw rows and draws one leg), so a
    fixture leg that the refusal chain drops would silently stop counting. Each
    leg therefore carries a distinct `external_id` and a real book.
    """
    return SimpleNamespace(
        id=oid,
        name=name,
        external_id=f"leg-{oid}",
        current_probability=prob,
        current_odds=None,
        current_american_odds=None,
        current_yes_bid=max(0.01, prob - 0.02),
        current_yes_ask=min(0.99, prob + 0.02),
        previous_probability=None,
        is_winner=None,
        rank=None,
        team_id=None,
    )


def _market(*, mid, name, legs, exclusive=True, volume=0.0):
    """A futures market shaped as the composer reads it.

    `exclusive` defaults to the honest value and is overridden only by
    `TestTheStoredFlagIsNotConsulted`: the shipped rule must not read it, so a
    fixture that set it per-case would make the flag look load-bearing again.
    """
    now = datetime.now(timezone.utc)
    return SimpleNamespace(
        id=mid,
        name=name,
        external_id=f"KX-{mid}",
        llm_sport_category="baseball",
        category="baseball",
        market_tier=5,
        market_type="prop",
        sport=None,
        sport_id=None,
        source="polymarket",
        volume=volume,
        status="open",
        mutually_exclusive=exclusive,
        resolution_date=(now + timedelta(days=2)).date(),
        updated_at=now,
        canonical_market_key=None,
        image_url=None,
        hook_description=None,
        group_id=None,
        event_id=None,
        outcomes=[_outcome(n, p, mid * 100 + i) for i, (n, p) in enumerate(legs)],
    )


#: The props bundle's real shape: 25 independent binaries summing 271%. Spelled
#: as a generator rather than 25 literals because the COUNT and the SUM are the
#: specimen, not the player names.
def _props_legs():
    legs = [
        ("Grant Holmes: Strikeouts O/U 3.5", 0.57),
        ("Hayden Wesneski: Strikeouts O/U 4.5", 0.40),
        ("Yordan Alvarez: Home Runs O/U 0.5", 0.25),
        ("Ozzie Albies: Home Runs O/U 0.5", 0.135),
    ]
    legs += [(f"Player {i}: Hits O/U 0.5", 0.08) for i in range(21)]
    return legs  # 25 legs, sum 2.035 + 0.679 = 2.714


def _astros_family():
    return [
        _market(
            mid=1,
            name="Atlanta Braves vs. Houston Astros - Player Props",
            legs=_props_legs(),
            exclusive=False,
        ),
        _market(
            mid=2,
            name="Atlanta Braves vs. Houston Astros - First 5 Innings Winner",
            legs=[
                ("Houston Astros", 0.455),
                ("Atlanta Braves", 0.40),
                ("Draw", 0.14),
            ],
        ),
        _market(
            mid=3,
            name="Atlanta Braves vs. Houston Astros",
            legs=[(f"1st 5 Innings O/U {i/2}", 0.78) for i in range(1, 10)],
            exclusive=False,
        ),
        _market(
            mid=4,
            name="Dorados de Chihuahua vs Astros de Jalisco",
            legs=[("Dorados de Chihuahua", 0.62), ("Astros de Jalisco", 0.38)],
        ),
    ]


def _fmt(m):
    return {
        "id": m.id,
        "name": m.name,
        "top_outcomes": [
            {"name": o.name, "probability": o.current_probability}
            for o in sorted(
                m.outcomes, key=lambda o: o.current_probability or 0, reverse=True
            )
        ],
    }


def _compose(markets, query="astros"):
    return _compose_futures_families(
        markets, [(query, None)], _fmt, {m.id for m in markets}
    )


# ==========================================================================
# The predicate, on the specimen's own numbers.
# ==========================================================================


class TestThePartitionTest:
    def test_the_props_bundle_is_not_a_partition(self):
        m = _market(mid=1, name="x - Player Props", legs=_props_legs())
        assert sum(p for _, p in _props_legs()) > 2.0  # the fixture IS the specimen
        assert _futures_board_is_not_a_partition(m) is True

    def test_a_real_three_way_board_is_a_partition(self):
        m = _market(
            mid=2,
            name="First 5 Innings Winner",
            legs=[("Houston Astros", 0.455), ("Atlanta Braves", 0.40), ("Draw", 0.14)],
        )
        assert _futures_board_is_not_a_partition(m) is False

    def test_a_lone_proposition_is_never_a_bundle(self):
        """`NBA: Stephen Curry to leave Warriors?` serves ONE leg at 0.02 and is
        flagged non-exclusive; it is an honest complete card and heads its
        family. Note what protects it: NOT a minimum-legs precondition (the
        predicate has none — see its docstring) but the arithmetic below."""
        m = _market(mid=3, name="NBA: Stephen Curry to leave Warriors?",
                    legs=[("Yes", 0.02)], exclusive=False)
        assert _futures_board_is_not_a_partition(m) is False

    def test_the_bar_stays_above_a_single_legs_ceiling(self):
        """⚠️ THE INVARIANT THAT LETS THE MINIMUM-LEGS PRECONDITION BE ABSENT.

        A probability cannot exceed 1.0, so n legs cannot sum past n: while the
        bar is above 1.0, no one-leg market can ever be called a bundle, and
        #5516's precondition 2 is unreachable here rather than merely unused
        (mutation testing agreed — severing it changed no test, so it was
        deleted). Drop the bar below 1.0 and that stops being true: one-leg
        propositions become reachable and `q=warriors` heads with a rugby
        fixture again. This test, not the deleted line, is the protection."""
        from app.routes.events import _BOARD_MAX_PARTITION_SUM

        assert _BOARD_MAX_PARTITION_SUM > 1.0

    def test_a_two_leg_board_cannot_trip_the_bar_either(self):
        """The same arithmetic one step further, pinned because it is why the
        threshold's real floor is THREE legs. Two maximal legs sum to exactly
        2.0 and the test is strict, so even a degenerate pair is safe."""
        m = _market(mid=6, name="degenerate pair", legs=[("A", 1.0), ("B", 1.0)])
        assert _futures_board_is_not_a_partition(m) is False

    def test_the_ambiguous_over_round_band_is_left_alone(self):
        """2.0 is the conservative end of the measured gap on purpose. A board
        carrying ordinary vig (1.03-2.00, 9.4% of the population) still heads
        its family — narrowing this constant is a re-measurement, not a tidy."""
        m = _market(mid=4, name="vig", legs=[("A", 0.55), ("B", 0.52), ("C", 0.40)])
        assert sum([0.55, 0.52, 0.40]) > 1.0
        assert _futures_board_is_not_a_partition(m) is False

    def test_a_truncated_ladder_cannot_trip_it(self):
        """#5516 needs an untruncated precondition; this does not, and the
        asymmetry is the reason. A slice of a real partition sums LOW."""
        m = _market(mid=5, name="World Series Champion",
                    legs=[(f"Team {i}", 0.033) for i in range(30)])
        assert _futures_board_is_not_a_partition(m) is False

    def test_a_cumulative_ladder_is_demoted_though_it_asks_ONE_question(self):
        """THE SECOND PRODUCTION SPECIMEN, and a different shape from the first.

        `?q=rangers`, 2026-09-20 01:44Z, live: the RANGERS family headed with

            NHL: NYR Rangers Total Points       70+ points   95%   (sum 392%)
            Islanders vs. Rangers               Islanders 47%      <- demoted, grey
            Will New York Rangers advance ...   No 87%
            Will New York Rangers advance ...   No 94%

        A fan typing their club is answered with `70+ points, 95%` while the
        club's actual next game sits below it in grey.

        WHY IT IS ITS OWN TEST rather than another props bundle. The predicate's
        docstring justifies itself as catching "several unrelated questions
        stacked in one row", and a props container is exactly that. This is NOT:
        it is ONE question asked at five NESTED thresholds, where every leg is a
        strict superset of the next (70+ contains 75+ contains 80+ ...). The
        rule must still demote it, and for a reason worth pinning — the max of a
        cumulative ladder is always its LOOSEST rung, so the headline drifts to
        whichever threshold is nearest certain and tells the reader least. The
        arithmetic that catches it is the same; the reading is not. Narrow this
        predicate to "unrelated questions" and the ladders come back silently.
        """
        rangers_total_points = [
            ("70+ points", 0.945),
            ("75+ points", 0.920),
            ("80+ points", 0.825),
            ("85+ points", 0.710),
            ("90+ points", 0.520),
        ]
        # The fixture IS the specimen: nested, honest, and unreadable as a set.
        assert sum(p for _, p in rangers_total_points) > 2.0
        probs = [p for _, p in rangers_total_points]
        assert probs == sorted(probs, reverse=True), "a cumulative ladder descends"

        m = _market(mid=7, name="NHL: NYR Rangers Total Points",
                    legs=rangers_total_points)
        assert _futures_board_is_not_a_partition(m) is True

        # ...and the scan hands the card to the game, which is the ship.
        game = _market(mid=8, name="Islanders vs. Rangers",
                       legs=[("Islanders", 0.47)])
        assert _family_headline_index([m, game]) == 1


# ==========================================================================
# The specimen, end to end through the composer.
# ==========================================================================


class TestTheAstrosSpecimen:
    def test_the_props_bundle_no_longer_heads_the_card(self):
        fam = _compose(_astros_family())[0]
        assert fam["headline"]["name"] != (
            "Atlanta Braves vs. Houston Astros - Player Props"
        )

    def test_the_card_now_answers_with_the_club(self):
        """#7261's acceptance verbatim. Asserted on the RENDERED top row, not on
        the market name — the name was never the defect."""
        fam = _compose(_astros_family())[0]
        assert fam["headline"]["name"] == (
            "Atlanta Braves vs. Houston Astros - First 5 Innings Winner"
        )
        assert fam["headline"]["top_outcomes"][0]["name"] == "Houston Astros"

    def test_a_players_prop_line_is_not_the_printed_answer(self):
        """The row Alex actually read. Pinned apart from the assertion above so
        a headline that is merely DIFFERENT cannot pass this file while still
        printing a player's stat line."""
        top = _compose(_astros_family())[0]["headline"]["top_outcomes"][0]["name"]
        assert "Strikeouts" not in top and "Home Runs" not in top

    def test_the_demoted_bundle_is_still_on_the_page(self):
        """A REORDER AND NOTHING ELSE — the blast radius #7261 required. The
        props market keeps its place in the family; it stops speaking for it."""
        fam = _compose(_astros_family())[0]
        assert "Atlanta Braves vs. Houston Astros - Player Props" in [
            m["name"] for m in fam["members"]
        ]

    def test_no_family_is_dropped_and_none_is_created(self):
        fams = _compose(_astros_family())
        assert len(fams) == 1
        assert fams[0]["member_count"] == 4

    def test_every_member_is_rendered_exactly_once(self):
        """`rest` is rebuilt around the promoted index, so the obvious way to
        get this wrong is to drop two rows or print one twice."""
        fam = _compose(_astros_family())[0]
        ids = [fam["headline"]["id"]] + [m["id"] for m in fam["members"]]
        assert sorted(ids) == [1, 2, 3, 4]


# ==========================================================================
# 🔴 The rule that was measured WRONG and must not come back.
# ==========================================================================


class TestTheStoredFlagIsNotConsulted:
    def test_a_bundle_flagged_exclusive_is_still_demoted(self):
        """The flag is unreliable in both directions; the legs are the evidence.
        Flip the bundle's flag to True and it must STILL lose the headline."""
        markets = _astros_family()
        markets[0].mutually_exclusive = True
        assert _family_headline_index(markets) == 1

    def test_a_one_leg_proposition_flagged_non_exclusive_still_heads(self):
        """The `q=warriors` regression, as a test. `Curry to leave Warriors?`
        carries `mutually_exclusive = False` on production and is the right
        headline; the flag-keyed rule skipped it to an NRL rugby fixture."""
        markets = [
            _market(mid=1, name="NBA: Stephen Curry to leave Warriors?",
                    legs=[("Yes", 0.02)], exclusive=False),
            _market(mid=2, name="New Zealand Warriors vs Newcastle Knights",
                    legs=[("New Zealand Warriors", 0.55), ("Newcastle Knights", 0.45)]),
        ]
        assert _family_headline_index(markets) == 0
        assert "Curry" in _compose(markets, query="warriors")[0]["headline"]["name"]

    def test_the_flag_is_absent_from_the_predicate(self):
        """Structural backstop: the column name must not appear in the
        predicate's code at all, so a reintroduction cannot be subtle."""
        import inspect

        src = inspect.getsource(_futures_board_is_not_a_partition)
        body = src.split('"""')[-1]  # past the docstring, which DISCUSSES the flag
        assert "mutually_exclusive" not in body


# ==========================================================================
# #7261's stated reason for not proposing a fix.
# ==========================================================================


class TestTheEntityInversionIsNotReintroduced:
    def _lebron(self):
        return [
            _market(mid=10, name="LeBron James Next Team",
                    legs=[("Lakers", 0.62), ("Cavaliers", 0.18), ("Retire", 0.20)]),
            _market(mid=11, name="Will LeBron James announce a Presidential run?",
                    legs=[("No", 0.97), ("Yes", 0.03)]),
        ]

    def test_lebron_james_next_team_still_heads_its_family(self):
        """The market NAMES the entity and its answer space is teams, so no
        printed outcome says "LeBron James". A rule keyed on the reader's query
        would demote it; this one never reads the query."""
        fam = _compose(self._lebron(), query="lebron james")[0]
        assert fam["headline"]["name"] == "LeBron James Next Team"
        assert fam["headline"]["top_outcomes"][0]["name"] == "Lakers"

    def test_the_rule_does_not_consult_the_query(self):
        """Structural, not behavioural: `_family_headline_index` takes members
        and nothing else, so no future edit can reach the query text without
        changing a signature this test reads."""
        import inspect

        assert list(inspect.signature(_family_headline_index).parameters) == ["members"]


# ==========================================================================
# A scan down the existing ranking, not a re-sort.
# ==========================================================================


class TestItSkipsRatherThanSorts:
    def test_the_wrong_sport_cousin_is_not_promoted(self):
        """`Astros de Jalisco` is a clean two-way partition and would win any
        re-sort keyed on answerability. It is LAST because #7259's
        `_demote_wrong_sport` put it there, and a scan preserves that."""
        assert "Jalisco" not in _compose(_astros_family())[0]["headline"]["name"]

    def test_the_first_answerable_member_wins_not_the_best_one(self):
        """Stated as a property so the implementation cannot drift into scoring:
        the EARLIER answerable member heads, though the later has more volume
        and a more confident leg."""
        markets = [
            _market(mid=1, name="Astros bundle", legs=_props_legs()),
            _market(mid=2, name="Astros early", volume=1.0,
                    legs=[("Houston Astros", 0.45), ("Other", 0.55)]),
            _market(mid=3, name="Astros later", volume=9_000_000.0,
                    legs=[("Houston Astros", 0.95), ("Other", 0.05)]),
        ]
        assert _family_headline_index(markets) == 1

    def test_an_already_answerable_leader_is_untouched(self):
        """The common case — 13 of the 15 club queries measured. Index 0 is a
        partition, the scan stops immediately, nothing moves."""
        markets = _astros_family()
        markets[0] = _market(
            mid=1,
            name="Will the Houston Astros clinch a spot in the 2026 MLB Postseason?",
            legs=[("Yes", 0.62), ("No", 0.38)],
        )
        assert _family_headline_index(markets) == 0


# ==========================================================================
# Fallbacks. The rule may never cost a family or invent a headline.
# ==========================================================================


class TestItFallsBackRatherThanDropping:
    def test_a_family_of_only_bundles_keeps_its_current_headline(self):
        """Nothing here can answer. Today's behaviour is the floor: head with
        members[0] rather than drop the card or leave it headless."""
        markets = [
            _market(mid=1, name="Astros props A", legs=_props_legs()),
            _market(mid=2, name="Astros props B", legs=_props_legs()),
        ]
        assert _family_headline_index(markets) == 0
        fams = _compose(markets)
        assert len(fams) == 1
        assert fams[0]["headline"]["name"] == "Astros props A"

    def test_a_market_with_no_legs_at_all_does_not_crash_the_scan(self):
        """`_compose_futures_families` is fed the answer-bearing set, so this
        should be unreachable — but a headline pick that raises would take the
        whole search response with it, and that trade is not worth a guess."""
        markets = [
            _market(mid=1, name="Astros empty", legs=[]),
            _market(mid=2, name="Astros real",
                    legs=[("Houston Astros", 0.6), ("Other", 0.4)]),
        ]
        assert _family_headline_index(markets) == 0

    def test_a_market_whose_legs_were_never_loaded_is_not_demoted(self):
        """THE COMPOSER IS THE FIRST THING IN THIS PATH TO READ `outcomes`, so
        it is the first that can meet a row without them. Every pre-#7261
        fixture in the suite builds markets with no `outcomes` attribute at all
        — 25 tests across four files went red on an `AttributeError` before this
        guard, which is exactly how a lazily-loaded relationship would present
        in production: a 500 on the whole search response, not a bad headline.
        No legs visible means no evidence, and no evidence means no demotion."""
        thin = SimpleNamespace(id=1, name="Astros unloaded")
        assert not hasattr(thin, "outcomes")
        assert _futures_board_is_not_a_partition(thin) is False
        assert _family_headline_index([thin, _market(
            mid=2, name="Astros real",
            legs=[("Houston Astros", 0.6), ("Other", 0.4)])]) == 0


# ==========================================================================
# #2646's promise has to stay payable across the skip.
# ==========================================================================


class TestTheMoreCountPromiseSurvivesTheSkip:
    def _seven(self):
        return [_market(mid=1, name="Astros bundle", legs=_props_legs())] + [
            _market(mid=i, name=f"Astros market {i}",
                    legs=[("Houston Astros", 0.5), ("Other", 0.5)])
            for i in range(2, 8)
        ]

    def test_overflow_is_counted_from_the_reordered_rest(self):
        """Seven members, one bundle at the head. The promoted member leaves
        `rest` at six, four are shown, so exactly two are below — and the
        bundle, now demoted into `rest`, is one of the four shown."""
        fam = _compose(self._seven())[0]
        assert fam["headline"]["id"] == 2
        assert len(fam["members"]) == 4
        assert fam["more_count"] == 2
        assert fam["member_count"] == 7

    def test_unserialized_overflow_is_still_not_promised(self):
        """#2646's rule re-asserted through the new code path: a member the
        response does not ship is on nobody's page and is not counted."""
        fams = _compose_futures_families(
            self._seven(), [("astros", None)], _fmt, {1, 2, 3, 4, 5}
        )
        assert fams[0]["more_count"] == 0
