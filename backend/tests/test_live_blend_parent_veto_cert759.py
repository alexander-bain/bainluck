"""LIVE-045 / CERT-759 — the lowest-id Polymarket row stops vetoing its group.

PILLAR: TRUTH. SHIP: a US Open match page shows a Polymarket price instead of
nothing, on the 11 of 36 events where the source had a price the whole time and
the blend never asked the market that had it.

THE DEFECT. `compute_source_home_probability` is the ONE writer of
`Event.win_probability_sources` for Kalshi and Polymarket — both the 120s poll
and the WebSocket fast lane go through it. It asks `select_primary_market` for
one market and then treats that answer as final: parse it, resolve it, or return
None for the whole source. `select_primary_market` prefers a game winner and
otherwise takes the LOWEST market id, but `is_game_winner_market` gates KALSHI
only, so for Polymarket every row of a group scores the same and "lowest id"
means OLDEST. Polymarket mints the event-level parent and the derivative books
(Exact Score, Match O/U) before the match-winner child that carries the
moneyline. Measured by CERT-759: an empty parent at id 1 beside a match-winner
child at id 9 selects primary 1 and reads None, and the source goes blank on
exactly the events this blend exists for.

THE REPAIR, and its two halves. The primary is now a PREFERENCE — asked first,
so anything that already spoke keeps saying the same thing — and the rest of the
group is tried in deterministic id order until a market CAN speak. That half
only widens. The other half is what keeps the widening safe: Polymarket
decomposes a game into rows that share the match winner's two-outcome shape AND
its "A vs. B" title, differing only by a qualifier (`- Halftime Result`,
`- Exact Score`, `: Both Teams to Score`). Those names parse and their outcomes
resolve, so an UNGATED fallback stamps a halftime price as the match moneyline —
93 of them in the 3-day replay this branch measured. So every non-primary
candidate must first prove it is a game winner by the shared
`game_market_class` recognizer.

Every test here drives the PUBLIC `compute_source_home_probability`, never the
new private helpers, so this whole file imports and runs under both arms — a
red-first run against master is a real assertion failure, not an ImportError.
"""

import pytest

from app.utils.live_blend import MarketOutcomes, compute_source_home_probability

HOME = "Ben Shelton"
AWAY = "Hubert Hurkacz"


class _Outcome:
    def __init__(self, name, prob, rank=None):
        self.name = name
        self.current_probability = prob
        self.current_yes_bid = None
        self.current_yes_ask = None
        self.rank = rank


class _Market:
    def __init__(self, id, source, external_id, name):
        self.id = id
        self.source = source
        self.external_id = external_id
        self.name = name


def _poly(id, name, outcomes):
    return MarketOutcomes(
        market=_Market(id, "polymarket", f"0x{id:04x}", name),
        outcomes=[_Outcome(n, p, i + 1) for i, (n, p) in enumerate(outcomes)],
    )


def _kalshi(id, ticker, name, outcomes):
    return MarketOutcomes(
        market=_Market(id, "kalshi", ticker, name),
        outcomes=[_Outcome(n, p, i + 1) for i, (n, p) in enumerate(outcomes)],
    )


#: The match-winner child. Yes = the home player, priced 0.62.
def _match_winner(id=9):
    return _poly(
        id,
        f"US Open ATP: {HOME} vs {AWAY}",
        [("Yes", 0.62), ("No", 0.38)],
    )


#: The event-level parent: minted first, carries no usable outcomes.
def _empty_parent(id=1):
    return _poly(id, "US Open ATP", [])


class TestTheEmptyParentNoLongerVetoesItsChild:
    """🔴 RED-FIRST — CERT-759's reproduction, at the ids the cert named."""

    def test_parent_id_1_plus_match_winner_id_9_reads_the_child(self):
        """The exact case the cert withheld a token over.

        On master this returns None: primary resolves to market 1, whose name
        `US Open ATP` has no matchup in it, and the group is abandoned there.
        """
        reading = compute_source_home_probability(
            [_empty_parent(1), _match_winner(9)], HOME, AWAY
        )
        assert reading is not None, (
            "the empty id-1 parent vetoed the id-9 match-winner child"
        )
        assert reading.home_probability == pytest.approx(0.62)

    def test_the_reading_names_the_market_that_actually_spoke(self):
        """`BlendReading.market` is the audit trail both callers stamp into
        `win_prob_snapshots.game_state` — "why did the blend say that". Naming
        the parent while the number came from the child would make that trail
        point at a market with no price in it."""
        reading = compute_source_home_probability(
            [_empty_parent(1), _match_winner(9)], HOME, AWAY
        )
        assert reading.market.id == 9
        assert reading.market.name == f"US Open ATP: {HOME} vs {AWAY}"
        assert reading.outcome.name == "Yes"

    def test_the_child_alone_always_worked_which_is_why_this_was_invisible(self):
        """Green in BOTH arms, on purpose: the child on its own has always
        resolved. The defect only ever appeared when a lower-id sibling existed,
        which is why it survived every single-market test."""
        reading = compute_source_home_probability([_match_winner(9)], HOME, AWAY)
        assert reading is not None
        assert reading.home_probability == pytest.approx(0.62)

    def test_order_in_the_sequence_does_not_change_the_answer(self):
        """The fallback walks market id, not list order, so two passes that load
        the same group in different row orders must agree. A row-order-dependent
        blend does not throw — it flickers."""
        forward = compute_source_home_probability(
            [_empty_parent(1), _match_winner(9)], HOME, AWAY
        )
        reverse = compute_source_home_probability(
            [_match_winner(9), _empty_parent(1)], HOME, AWAY
        )
        assert forward.market.id == reverse.market.id == 9
        assert forward.home_probability == reverse.home_probability


class TestTheRealShapeThatBlankedProduction:
    """The population measurement found the parent is rarely the culprit — the
    lowest-id row is usually an `Exact Score` book. Same defect, real ids."""

    def test_exact_score_at_the_lowest_id_no_longer_silences_the_group(self):
        exact_score = _poly(
            59955246,
            f"{HOME} vs. {AWAY} - Exact Score",
            [("3-0", 0.18), ("3-1", 0.22), ("3-2", 0.20)],
        )
        winner = _poly(
            59959795,
            f"US Open ATP: {HOME} vs {AWAY}",
            [("Yes", 0.76), ("No", 0.24)],
        )
        reading = compute_source_home_probability([exact_score, winner], HOME, AWAY)
        assert reading is not None
        assert reading.market.id == 59959795
        assert reading.home_probability == pytest.approx(0.76)


class TestTheFallbackNeverTakesADerivative:
    """🔴 THE SAFETY PROPERTY. These are the shapes an ungated fallback ate.

    Each derivative below parses into a matchup AND resolves a team outcome —
    that is precisely the hazard. Nothing downstream would notice a halftime
    price wearing the moneyline's name: it sits between 0 and 1, it moves, and
    it usually ends on the correct side. The only thing between a reader and a
    confidently-wrong hero is that a non-primary market must prove it is a game
    winner before it may speak.
    """

    DERIVATIVES = [
        f"{HOME} vs. {AWAY} - Halftime Result",
        f"{HOME} vs. {AWAY} - Exact Score",
        f"{HOME} vs. {AWAY} - More Markets",
        f"{HOME} vs. {AWAY}: Both Teams to Score",
        f"{HOME} vs. {AWAY}: Both Teams to Score in Second Half",
        f"{HOME} vs. {AWAY}: First Team to Score",
    ]

    @pytest.mark.parametrize("name", DERIVATIVES)
    def test_a_derivative_below_an_unparseable_primary_stays_silent(self, name):
        """No match winner in the group at all. The blend must say nothing
        rather than reach for the derivative that is sitting right there."""
        group = [
            _poly(1, "US Open ATP", []),
            _poly(2, name, [(HOME, 0.71), (AWAY, 0.29)]),
        ]
        reading = compute_source_home_probability(group, HOME, AWAY)
        assert reading is None, (
            f"{name!r} was stamped as the match moneyline "
            f"({reading.home_probability if reading else None})"
        )

    @pytest.mark.parametrize("name", DERIVATIVES)
    def test_the_match_winner_is_preferred_over_a_lower_id_derivative(self, name):
        """With a real winner present, the fallback must walk PAST the
        derivative — even though the derivative has the lower id and would
        resolve happily — and land on the winner."""
        group = [
            _poly(1, "US Open ATP", []),
            _poly(2, name, [(HOME, 0.71), (AWAY, 0.29)]),
            _poly(3, f"US Open ATP: {HOME} vs {AWAY}", [("Yes", 0.62), ("No", 0.38)]),
        ]
        reading = compute_source_home_probability(group, HOME, AWAY)
        assert reading is not None
        assert reading.market.id == 3, f"the fallback took {name!r}"
        assert reading.home_probability == pytest.approx(0.62)


class TestPropsStillRefuse:
    """live/041's seven shapes, driven through the WRITER rather than the parser.

    live/041 asserted these do not parse. That is the property that must survive
    a change to what the writer is willing to try, so it is re-asserted at the
    layer this branch moved: each prop is the ONLY sibling of an unparseable
    parent, so if the fallback would take it, it takes it here.
    """

    PROP_MARKETS = [
        ("Set Handicap: Shelton (-1.5) vs Hurkacz (+1.5)",
         [("Yes", 0.525), ("No", 0.475)]),
        ("Set Handicap: Shelton (-2.5) vs Hurkacz (+2.5)",
         [("Yes", 0.275), ("No", 0.725)]),
        ("Set 1 Winner: Shelton vs Hurkacz", [("Yes", 0.610), ("No", 0.400)]),
        ("Set 2 Winner: Shelton vs Hurkacz", [("Yes", 0.615), ("No", 0.385)]),
        ("Game Spread: Shelton (-3.5) vs Hurkacz (+3.5)",
         [("Yes", 0.5), ("No", 0.5)]),
        ("Shelton vs. Hurkacz: Match O/U 36.5", [("Over", 0.595), ("Under", 0.405)]),
        ("Ben Shelton vs. Hubert Hurkacz: Total Sets O/U 3.5",
         [("Over", 0.65), ("Under", 0.355)]),
    ]

    @pytest.mark.parametrize("name,outcomes", PROP_MARKETS)
    def test_a_prop_never_becomes_the_blend(self, name, outcomes):
        group = [_poly(1, "US Open ATP", []), _poly(2, name, outcomes)]
        reading = compute_source_home_probability(group, "Shelton", "Hurkacz")
        assert reading is None, f"{name!r} became the blend"


class TestNothingThatAlreadySpokeChanges:
    """CONTROLS — green in BOTH arms, which is what makes them controls.

    The claim this branch makes is "can only widen". These pin it: every group
    whose primary already resolved must come out byte-identical, because the
    primary is still asked first and is still exempt from the fallback gate.
    """

    def test_a_lone_match_winner_is_unchanged(self):
        reading = compute_source_home_probability([_match_winner(9)], HOME, AWAY)
        assert reading.market.id == 9
        assert reading.home_probability == pytest.approx(0.62)
        assert reading.devigged is False

    def test_the_kalshi_per_team_pair_still_devigs(self):
        """The two-market devig is the behaviour most exposed to a change in
        which market is called the speaker — it keys off the speaker's id to
        find the sibling."""
        group = [
            _kalshi(11, "KXATPMATCH-26SEP02SHEHUR-SHE", "Shelton vs. Hurkacz",
                    [("Yes", 0.64), ("No", 0.36)]),
            _kalshi(12, "KXATPMATCH-26SEP02SHEHUR-HUR", "Hurkacz vs. Shelton",
                    [("Yes", 0.40), ("No", 0.60)]),
        ]
        reading = compute_source_home_probability(group, "Shelton", "Hurkacz")
        assert reading is not None
        assert reading.devigged is True
        assert reading.market.id == 11

    def test_a_kalshi_prop_primary_is_still_refused_when_alone(self):
        """The Kalshi admission gate moved INTO the per-market attempt. A prop
        that is the only market must still write nothing — moving a gate is
        exactly how a gate gets dropped."""
        group = [
            _kalshi(11, "KXATPSETWINNER-26SEP02SHEHUR-SHE", "Shelton vs. Hurkacz",
                    [("Yes", 0.61), ("No", 0.39)]),
        ]
        assert compute_source_home_probability(group, "Shelton", "Hurkacz") is None

    def test_a_kalshi_set_winner_never_becomes_the_fallback(self):
        """`kxatpsetwinner` carries the SAME two player names as `kxatpmatch`,
        so it resolves happily. It is refused twice over now — by the Kalshi
        ticker gate and by the fallback's game-winner gate — and the point of
        asserting it here is that BOTH could be removed independently."""
        group = [
            _kalshi(10, "KXATPMATCH-26SEP02SHEHUR-SHE", "Set 3", []),
            _kalshi(11, "KXATPSETWINNER-26SEP02SHEHUR-SHE", "Shelton vs. Hurkacz",
                    [("Yes", 0.61), ("No", 0.39)]),
        ]
        assert compute_source_home_probability(group, "Shelton", "Hurkacz") is None

    def test_the_primary_is_exempt_from_the_fallback_gate(self):
        """🔴 The control that stops the safety gate from eating the product.

        `FC Nordsjælland vs. Aarhus GF` is a plain, real match winner. The
        shared recognizer refuses it anyway: its team-token pattern is
        ASCII-only, so `æ` breaks the bare-matchup match and it classifies as
        `other`. That is fine for a fallback, which must fail closed — but the
        primary has been writing this event's blend all along, and applying the
        gate to it would blank it.

        Not hypothetical: applying the gate to the primary as well was run as a
        mutation against the banked 3-day population and cost **199** live
        readings, 48 of them non-ASCII names exactly like this one. The whole
        claim of this branch is "can only widen", and this is the test that
        holds it.
        """
        group = [
            _poly(
                1,
                "FC Nordsjælland vs. Aarhus GF",
                [("FC Nordsjælland", 0.55), ("Aarhus GF", 0.45)],
            )
        ]
        reading = compute_source_home_probability(
            group, "FC Nordsjælland", "Aarhus GF"
        )
        assert reading is not None, (
            "the fallback's game-winner gate leaked onto the primary"
        )
        assert reading.home_probability == pytest.approx(0.55)

    def test_an_empty_group_says_nothing(self):
        assert compute_source_home_probability([], HOME, AWAY) is None

    def test_a_group_with_no_usable_market_still_says_nothing(self):
        """The widened search must not turn "nobody can speak" into a guess."""
        group = [_poly(1, "US Open ATP", []), _poly(2, "US Open ATP", [])]
        assert compute_source_home_probability(group, HOME, AWAY) is None
