"""#4983 — the kickoff class is served headline-first, and the budget is spent.

WHAT WENT WRONG, AND WHY IT COULD NOT BE SEEN.

#4896 put a kickoff key at the front of this rail's ordering so a game about to
be played leads the refresh queue. It worked, and it exposed the next thing: the
class it promoted is far larger than the budget it has to fit in. MEASURED on
production 2026-09-11, the kickoff class is 588 markets / 1,150 condition ids on
a *weeknight* against a 1,000-id ``CONDITION_BUDGET``, and the rolling window
peaks Saturday at ~3,220 ids — 322%.

Two things then made the overflow land in the worst possible place:

1. **Ordering was strictly ``kickoff ASC``**, so one game's 47-id prop ladder was
   served ahead of the next game's 1-id headline market. 165 ladder markets (14%
   of the class) carry 51% of its demand, while 501 of 588 markets cost exactly
   one id. The ≤3h slice alone is 1,342 ids, so admission provably ran out
   INSIDE the games about to be played.
2. **Admission ``break``ed on the first market that did not fit** rather than
   skipping it, so a single oversized ladder abandoned the remaining budget to
   every cheaper, more urgent market queued behind it.

And there is no rotation to absorb any of it: ``_KICKOFF_ATTEMPT_TTL_SECONDS`` is
45 minutes against a 60-minute beat, deliberately, so every kickoff marker has
expired by the next beat. A row the budget passes over is passed over on EVERY
beat until its kickoff goes by — dropped, not deferred. Ordering is therefore the
*only* thing deciding who is ever served, which is what makes these tests worth
having at all.

WHAT IS GUARDED HERE. The admission phases (headline → ladder → drain), the
reserve that stops the kickoff class zeroing the #3879 backlog drain, the two
invariants #4827 established that this change had to preserve exactly (a market
is never split; at most one market per RUN may overshoot), and the shortfall
counters that make an acceptance failure a number instead of an inference.

🔴 THE PRODUCER-SIDE TEST IS ``test_a_later_games_headline_beats_an_earlier_games_ladder``.
Every other test here still passes if the partition is deleted and the class goes
back to one kickoff-ordered pool. That one does not. If it is ever weakened, this
file stops guarding the ship and only guards its bookkeeping.
"""

import app.tasks.polymarket_condition_refresh as rail

from tests.test_polymarket_condition_refresh_3879 import _arm, _Service, _writes


def _ids(n, tag):
    """``n`` distinct condition ids — ``len(cids)`` IS the cost being rationed."""
    return [f"0x{tag}{i:04d}" for i in range(n)]


def _prop(mid, player):
    """A producer-shaped player prop: a real Polymarket prop NAME, one bare cid.

    The shape is the whole point of CERT-2564. Polymarket writes every decomposed
    sub-market with a bare condition-id external id, props included, so a prop is
    indistinguishable from a game winner by COST — both are one id. Only the name
    separates them.
    """
    return {mid: (f"{player}: Anytime Goalscorer", f"0x{mid:064x}")}


def _winner(mid, home, away):
    """A producer-shaped game winner: the bare matchup title, one bare cid."""
    return {mid: (f"{home} vs. {away}", f"0x{mid:064x}")}


def _admitted(service, candidates):
    """Which market ids this run actually asked Gamma for.

    Read at the REQUEST boundary rather than at the writer: admission is the
    thing under test, and the writer only runs for markets Gamma hands back, so
    asserting there makes a test that passes when nothing was admitted at all.
    """
    asked = {cid for call in service.calls for cid in call}
    return sorted(mid for mid, cids in candidates if asked & set(cids))


class TestTheImminentGameGetsItsOwnNumberFirst:
    """Phase 1 — the acceptance #4896 exists to hold."""

    async def test_a_later_games_headline_beats_an_earlier_games_ladder(
        self, monkeypatch
    ):
        """THE PRODUCER-SIDE TEST. Restore the single kickoff-ordered pool and this fails.

        THE SHAPE MATTERS, AND THE OBVIOUS SHAPE DOES NOT BIND. A ladder that is
        too big to fit is skipped by the `continue` fix whether or not the class
        is partitioned, so a test built on one proves only the skip. The
        partition earns its keep in the opposite case: a ladder that FITS, and
        whose 70 ids are then not available to the headline markets queued
        behind it.

        Game A kicks off soonest and brings a 70-id prop ladder; twenty more
        games follow, each wanting a single id for its own headline number.
        Under one kickoff-ordered pool the ladder is taken at position two and
        the budget runs out ten games later. Partitioned, every game's headline
        number is served and the ladder waits.
        """
        candidates = [
            (1, _ids(1, "a")),  # game A, kicks off soonest — headline
            (2, _ids(70, "b")),  # game A — prop ladder, and it FITS
        ] + [(i, _ids(1, f"h{i:02d}")) for i in range(3, 23)]  # 20 more games
        svc = _Service()
        _arm(
            monkeypatch,
            candidates=candidates,
            stale=len(candidates),
            served=100,
            imminent={mid for mid, _ in candidates},
            # The ladder is a ladder because of what it IS, not what it costs
            # (CERT-2564). Everything else takes the default bare-matchup name.
            names=_prop(2, "Son Heung-min"),
            service=svc,
        )

        # 100 ids, less a fifth reserved for the drain, is a kickoff cap of 80.
        stats = await rail._refresh_stale_polymarket_conditions(condition_budget=100)

        admitted = _admitted(svc, candidates)
        assert stats["kickoff_headline_due"] == 21, (
            "every imminent game's headline market must be served before any "
            f"game's ladder; served {stats['kickoff_headline_due']} of 21 "
            "(a single kickoff-ordered pool serves 10 and spends the rest on "
            "one game's props)"
        )
        assert stats["kickoff_headline_shortfall"] == 0
        assert 2 not in admitted, "the 70-id ladder must not displace 11 headlines"
        assert stats["kickoff_ladder_due"] == 0
        assert stats["kickoff_ladder_shortfall"] == 1

    async def test_one_id_player_prop_cannot_precede_one_id_game_winner_under_saturated_budget(
        self, monkeypatch
    ):
        """THE REPAIR TEST (CERT-2564). Cost cannot tell these two apart; semantics can.

        The first cut of this ship split the class on `len(cids) <= 3`. Both rows
        here cost exactly ONE id — which is what every producer-written
        Polymarket sub-market costs, props included — so that rule called them
        both headlines, left them in one pool in kickoff order, and served the
        prop. It then reported `headline_due=1 / shortfall=1` while doing it,
        so the counters agreed with themselves and disagreed with the ship.

        The prop is ordered FIRST, so kickoff order alone would take it, and the
        budget admits exactly one market. Nothing but the headline/ladder split
        can put the game's own number ahead of another game's prop here.
        """
        candidates = [
            (1, _ids(1, "p")),  # kicks off soonest — but it is a PROP
            (2, _ids(1, "w")),  # the next game's own number
        ]
        svc = _Service()
        _arm(
            monkeypatch,
            candidates=candidates,
            stale=2,
            served=100,
            imminent={1, 2},
            names={**_prop(1, "Erling Haaland"), **_winner(2, "Arsenal", "Chelsea")},
            service=svc,
        )

        # One id of capacity: the reserve clamps to 1 // 5 == 0, so the kickoff
        # cap is the whole budget and exactly one one-id market fits.
        stats = await rail._refresh_stale_polymarket_conditions(condition_budget=1)

        admitted = _admitted(svc, candidates)
        assert admitted == [2], (
            "the game's own number must be served before another game's prop; "
            f"admitted {admitted} (a cost-based split admits [1], the prop)"
        )
        # The counters have to agree with the admission, not merely be non-zero:
        # the cost split reported headline_due=1 while serving the prop.
        assert stats["kickoff_headline_due"] == 1
        assert stats["kickoff_headline_shortfall"] == 0
        assert stats["kickoff_ladder_due"] == 0
        assert stats["kickoff_ladder_shortfall"] == 1

    async def test_an_oversized_ladder_no_longer_abandons_the_budget(
        self, monkeypatch
    ):
        """`break` → skip. The pool is ordered by urgency, not by cost."""
        # All ladders, so phase 1 is empty and phase 2 does the work under a
        # kickoff cap of 100 - (100 // 5) = 80: the first is admitted (nothing is
        # due yet, 30), the second cannot fit (30 + 60 > 80), and the third can
        # (30 + 20 <= 80). The old `break` stopped at the second and never
        # reached the third, spending 30 of a possible 50.
        candidates = [(1, _ids(30, "a")), (2, _ids(60, "b")), (3, _ids(20, "c"))]
        svc = _Service()
        _arm(
            monkeypatch,
            candidates=candidates,
            stale=3,
            served=100,
            imminent={1, 2, 3},
            names={
                **_prop(1, "Bukayo Saka"),
                **_prop(2, "Cole Palmer"),
                **_prop(3, "Kai Havertz"),
            },
            service=svc,
        )

        stats = await rail._refresh_stale_polymarket_conditions(condition_budget=100)

        admitted = _admitted(svc, candidates)
        assert admitted == [1, 3], f"expected the skip, not the break; got {admitted}"
        assert stats["conditions_requested"] == 50

    async def test_the_headline_shortfall_is_a_number_not_an_inference(
        self, monkeypatch
    ):
        """`budget_exhausted` is True in healthy operation, so it cannot report this.

        The acceptance failure — games about to be played whose own number was
        not refreshed — needs its own counter or it is invisible behind a flag
        that is already set for benign reasons.
        """
        candidates = [(i, _ids(1, f"{i:02d}")) for i in range(1, 21)]
        _arm(
            monkeypatch,
            candidates=candidates,
            stale=20,
            served=100,
            imminent=set(range(1, 21)),
            writer=_writes,
        )

        stats = await rail._refresh_stale_polymarket_conditions(condition_budget=10)

        # 10 ids of budget, minus a fifth held for the drain, is 8 headlines.
        assert stats["kickoff_headline_due"] == 8
        assert stats["kickoff_headline_shortfall"] == 12
        assert stats["budget_exhausted"] is True


class TestTheDrainIsNeverZeroedByTheKickoffClass:
    """Phase 3 — #4983's containment half, and #3879's original purpose."""

    async def test_a_kickoff_class_larger_than_the_budget_still_leaves_the_drain_ids(
        self, monkeypatch
    ):
        kickoff = [(i, _ids(1, f"k{i:02d}")) for i in range(1, 101)]
        backlog = [(500 + i, _ids(1, f"d{i:02d}")) for i in range(1, 21)]
        candidates = kickoff + backlog
        svc = _Service()
        _arm(
            monkeypatch,
            candidates=candidates,
            stale=120,
            served=1000,
            imminent={i for i, _ in kickoff},
            service=svc,
        )

        stats = await rail._refresh_stale_polymarket_conditions(condition_budget=50)

        assert stats["drain_due"] == 10, (
            "a fifth of the budget is a floor under the backlog drain — without "
            "it the kickoff class takes every id, every beat, all weekend"
        )
        assert stats["kickoff_headline_due"] == 40
        assert any(mid > 500 for mid in _admitted(svc, candidates))

    async def test_the_reserve_is_a_floor_and_never_a_ceiling(self, monkeypatch):
        """A quiet Monday must still drain at the full budget, not at 200 ids."""
        candidates = [(1, _ids(1, "k"))] + [
            (500 + i, _ids(1, f"d{i:02d}")) for i in range(1, 41)
        ]
        _arm(
            monkeypatch,
            candidates=candidates,
            stale=41,
            served=1000,
            imminent={1},
            writer=_writes,
        )

        stats = await rail._refresh_stale_polymarket_conditions(condition_budget=50)

        assert stats["kickoff_headline_due"] == 1
        assert stats["drain_due"] == 40, "unspent kickoff budget belongs to the drain"

    async def test_a_budget_at_or_under_the_reserve_cannot_starve_the_priority_class(
        self, monkeypatch
    ):
        """`condition_budget` is a parameter; the reserve is clamped to a fifth.

        Subtracting a flat 200 from a budget of 200 would drive the kickoff cap
        to zero and serve the backlog while games kicked off unrefreshed — the
        exact inversion of this ship.
        """
        kickoff = [(i, _ids(1, f"k{i:02d}")) for i in range(1, 11)]
        backlog = [(500 + i, _ids(1, f"d{i:02d}")) for i in range(1, 11)]
        _arm(
            monkeypatch,
            candidates=kickoff + backlog,
            stale=20,
            served=100,
            imminent={i for i, _ in kickoff},
            writer=_writes,
        )

        stats = await rail._refresh_stale_polymarket_conditions(condition_budget=5)

        assert stats["kickoff_headline_due"] == 4
        assert stats["drain_due"] == 1


class TestTheInvariantsThisChangeHadToPreserve:
    """#4827's two rules. A phased admission is where they quietly break."""

    async def test_a_market_is_never_split_across_the_budget_line(self, monkeypatch):
        """A half-refreshed ladder is worse than a stale one."""
        candidates = [(1, _ids(3, "a")), (2, _ids(40, "b")), (3, _ids(3, "c"))]
        svc = _Service()
        _arm(
            monkeypatch,
            candidates=candidates,
            stale=3,
            served=100,
            imminent={1, 2, 3},
            service=svc,
        )

        await rail._refresh_stale_polymarket_conditions(condition_budget=10)

        requested = {cid for call in svc.calls for cid in call}
        assert requested, "nothing was requested — this assertion would be vacuous"
        # Whatever was taken, no market contributed a partial id set.
        for mid, cids in candidates:
            taken = requested & set(cids)
            assert len(taken) in (0, len(cids)), f"market {mid} was split"

    async def test_at_most_one_market_per_run_may_overshoot_not_one_per_phase(
        self, monkeypatch
    ):
        """The unconditional first admission stays keyed on `due` being empty GLOBALLY.

        Three phases each admitting an oversized first market would triple the
        wall this budget exists to bound.
        """
        candidates = [
            (1, _ids(40, "a")),  # kickoff ladder, oversized, admitted as run-first
            (2, _ids(40, "b")),  # kickoff ladder, oversized — must NOT be admitted
            (500, _ids(40, "c")),  # drain, oversized — must NOT be admitted
        ]
        _arm(
            monkeypatch,
            candidates=candidates,
            stale=3,
            served=100,
            imminent={1, 2},
            names={**_prop(1, "Mohamed Salah"), **_prop(2, "Darwin Núñez")},
            writer=_writes,
        )

        stats = await rail._refresh_stale_polymarket_conditions(condition_budget=10)

        assert stats["markets_due"] == 1
        assert stats["conditions_requested"] == 40

    async def test_a_pool_with_no_kickoff_rows_admits_exactly_as_before(
        self, monkeypatch
    ):
        """The ~10,600 non-kickoff rows must not feel this change at all."""
        candidates = [(i, _ids(1, f"d{i:02d}")) for i in range(1, 31)]
        _arm(
            monkeypatch,
            candidates=candidates,
            stale=30,
            served=100,
            imminent=set(),
            writer=_writes,
        )

        stats = await rail._refresh_stale_polymarket_conditions(condition_budget=10)

        assert stats["markets_due"] == 10
        assert stats["drain_due"] == 10
        assert stats["kickoff_headline_due"] == 0
        assert stats["kickoff_headline_shortfall"] == 0

    async def test_the_market_cap_still_binds_independently_of_the_id_cap(
        self, monkeypatch
    ):
        """Two caps, whichever binds first — #4827's shape, across three phases."""
        candidates = [(i, _ids(1, f"k{i:02d}")) for i in range(1, 51)]
        _arm(
            monkeypatch,
            candidates=candidates,
            stale=50,
            served=100,
            imminent={i for i, _ in candidates},
            writer=_writes,
        )

        stats = await rail._refresh_stale_polymarket_conditions(
            budget=5, condition_budget=1000
        )

        assert stats["markets_due"] == 5


class TestTheSizingConstantsSayWhatWasMeasured:
    """A wrong figure in a sizing constant's docstring is how a budget is mis-sized."""

    def test_the_cost_based_threshold_is_gone_and_cannot_come_back(self):
        """CERT-2564: `len(cids) <= 3` called a one-id player prop a headline.

        The constant is not merely unused — it is retired, because any value of
        it is wrong. Asserting its absence is what stops the next session
        reintroducing a "cheap means game-level" rule that reads plausible and
        measures false.
        """
        assert not hasattr(rail, "KICKOFF_HEADLINE_MAX_IDS")

    def test_the_split_is_semantic_and_uses_the_one_shared_recognizer(self):
        """A prop and a game winner that cost the SAME must land in different halves."""
        cid = "0x" + "ab" * 32  # producer shape: a bare condition id, for both
        assert rail._is_headline_market("Arsenal vs. Chelsea", cid) is True
        assert rail._is_headline_market("Erling Haaland: Anytime Goalscorer", cid) is False
        # The game-level books a reader sees on the card are all headlines.
        assert rail._is_headline_market("Gauff vs. Rybakina: Match O/U 23.5", cid) is True
        # An unreadable name falls to the ladder half — a later slot in the same
        # beat, never ahead of a game that is about to start.
        assert rail._is_headline_market("", cid) is False
        # #5041: the recognizer this delegates to must read a name that is not
        # English, or this split silently demotes whole leagues to the ladder.
        assert rail._is_headline_market("1. FC Köln vs. SV Werder Bremen", cid) is True
        assert rail._is_headline_market("Club León FC vs. Atlético San Luis", cid) is True

    def test_the_reserve_is_a_fifth_of_the_production_budget(self):
        assert rail.DRAIN_RESERVE_IDS == 200
        assert rail.DRAIN_RESERVE_IDS == rail.CONDITION_BUDGET // 5

    def test_the_retired_277_id_figure_is_gone_from_the_kickoff_docstring(self):
        """It was measured under the 3-hour horizon and never re-taken at 24.

        It also contradicted the table 30 lines above it by 2.4x. Two constants
        in one file disagreeing about the same quantity is the defect; asserting
        the stale one cannot come back is the guard.
        """
        # A `#:` comment block is not a runtime docstring — an int has no
        # `__doc__` of its own — so the assertion has to read the module source.
        import inspect

        source = inspect.getsource(rail)
        head, _, _ = source.partition("KICKOFF_STALE_MINUTES = 45")
        assert head, "the constant moved; this guard is reading nothing"
        assert "leaves ~723 for the backlog drain" not in head
        assert "1,150 condition ids on a weeknight" in head
