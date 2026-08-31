"""Q440 (#2231) — one question about a Kalshi ticker, one decider.

Three predicates answer "is this ticker game-level?" and they disagree:

    app/utils/sport_keys.py       is_kalshi_game_ticker()        bare startswith
    app/utils/sport_keys.py       is_kalshi_game_level_ticker()  longest-prefix-wins
    app/tasks/kalshi.py           _is_kalshi_game_ticker()       bare startswith

Eight futures prefixes strictly EXTEND a game prefix, so a bare ``startswith``
against the game map calls a season market a game. Measured on production
2026-08-29, that is not hypothetical — it renders:

    event 14611830  Nuggets vs Timberwolves   ->  "Pro Basketball Pacific Division Winner"
    event 14970359  Padres vs Blue Jays       ->  "Pro Baseball Home Run Derby Selections"
    event 5766515   "At least 1 game played"  ->  "Will at least 1 game be played in the
                                                   Women's Pro Basketball season?"

...all inside ``GET /api/events/{id}/game-markets``'s ``other`` bucket.

Four prefixes hold 78 linked rows between them, but only **3** of those links are
wrong — the other 75 are ``KXNBAPTSLEADER``, which is a per-game prop correctly
attached to its own game. That split is the finding, not a footnote: the naive
repair unlinks all 78.

The reverse collision is the COMMON one (``kxmlbrfi`` extends the FUTURES prefix
``kxmlb``) — 143 pairs measured 2026-08-29, 155 after Q435's tennis additions —
so "refuse if any futures prefix matches" is wrong in the other direction and
fails silently: every one of those real game families would stop anchoring while
every counter still read healthy. That control is asserted here too, as a
property over the maps rather than a pinned count (Q462).

One member of the eight is a MIS-FILED MAP ENTRY rather than a predicate bug:
``kxnbaptsleader`` ("Atlanta at New York: Points Leader") is a per-game prop, and
production has 75 of them correctly linked to their own game. Classifying it as
futures — which is what longest-prefix-wins does while the map says futures —
would break 75 correct links. The map is corrected; the predicate is not bent
around it.
"""

from __future__ import annotations

import pytest

from app.tasks.kalshi import _is_kalshi_game_ticker as task_game_label
from app.utils.prediction_market_matching import is_game_level_market
from app.utils.sport_keys import (
    KALSHI_FUTURES_TICKER_TO_SPORT_KEY,
    KALSHI_GAME_TICKER_PREFIXES,
    KALSHI_TICKER_TO_DISPLAY_LABEL,
    is_kalshi_game_level_ticker,
)

# ── Production specimens, all measured 2026-08-29 via /api/admin/db-query ────
#
# (ticker, market name, the event it was wrongly attached to)
SEASON_SPECIMENS = [
    (
        "KXNBAPACIFIC-25",
        "Pro Basketball Pacific Division Winner",
        14611830,  # Nuggets vs Timberwolves, 2026-04-28
    ),
    (
        "KXMLBHRDERBYQUAL-26",
        "Pro Baseball Home Run Derby Selections",
        14970359,  # Padres vs Blue Jays, 2026-07-12
    ),
    (
        "KXWNBAGAMESPLAYED-26BINARY",
        "Will at least 1 game be played in the Women's Pro Basketball season?",
        5766515,  # a pseudo-event whose two "teams" are both "At least 1 game played"
    ),
]

# The game prefix each of the above extends — the reason a bare startswith says yes.
SEASON_SPECIMEN_SHADOWED_GAME_PREFIX = {
    "KXNBAPACIFIC-25": "kxnbapa",  # Points + Assists combo prop
    "KXMLBHRDERBYQUAL-26": "kxmlbhr",  # Player home runs prop
    "KXWNBAGAMESPLAYED-26BINARY": "kxwnbagame",  # WNBA game
}

# The must-not-regress control: a genuine per-game prop whose ticker extends a
# game prefix AND appears in the futures map. 75 of these are linked to the right
# game in production right now.
GAME_PROP_SPECIMENS = [
    ("KXNBAPTSLEADER-26APR18ATLNYK", "Atlanta at New York: Points Leader"),
    ("KXNBAPTSLEADER-26MAY09DETCLE", "Detroit at Cleveland: Points Leader"),
]

# The 143-case direction: a GAME prefix that extends a FUTURES prefix. These must
# stay game-level, and this is the half that fails quietly.
REVERSE_CONTROL_SPECIMENS = [
    ("KXMLBRFI-26AUG29KCCLE", "kxmlb"),  # game prefix kxmlbrfi over futures kxmlb
    ("KXMLBGAME-26AUG291610KCCLE", "kxmlb"),
    ("KXNBAGAME-26FEB19BOSGSW", "kxnba"),
]


def _futures_extending_game_pairs() -> list[tuple[str, str]]:
    game = set(KALSHI_GAME_TICKER_PREFIXES)
    return sorted(
        (f, g)
        for f in KALSHI_FUTURES_TICKER_TO_SPORT_KEY
        for g in game
        if f != g and f.startswith(g)
    )


def _game_extending_futures_pairs() -> list[tuple[str, str]]:
    futures = set(KALSHI_FUTURES_TICKER_TO_SPORT_KEY)
    return sorted(
        (g, f)
        for g in KALSHI_GAME_TICKER_PREFIXES
        for f in futures
        if g != f and g.startswith(f)
    )


class TestSeasonMarketsAreNotGames:
    """The ship: a season market stops reading as a game on every rail."""

    @pytest.mark.parametrize("ticker,name,_event_id", SEASON_SPECIMENS)
    def test_predicate_refuses(self, ticker, name, _event_id):
        assert is_kalshi_game_level_ticker(ticker) is False

    @pytest.mark.parametrize("ticker,name,_event_id", SEASON_SPECIMENS)
    def test_matching_gate_refuses(self, ticker, name, _event_id):
        """``is_game_level_market`` is the gate that hands a market to game matching.

        Signal 1 is the ticker. With the ticker refused, the name must not rescue
        it — none of these three names is a matchup.
        """
        assert (
            is_game_level_market(name, external_id=ticker, num_outcomes=2) is False
        ), f"{ticker} would be handed to game matching"

    @pytest.mark.parametrize("ticker,name,_event_id", SEASON_SPECIMENS)
    def test_ingest_does_not_label_it_a_game(self, ticker, name, _event_id):
        """``tasks/kalshi._is_kalshi_game_ticker`` names ingested markets.

        A truthy return sends the event through ``_build_game_market_name``,
        which renames a season question as a matchup.
        """
        assert task_game_label(ticker) is None

    @pytest.mark.parametrize("ticker,name,_event_id", SEASON_SPECIMENS)
    def test_the_shadowed_game_prefix_really_is_the_cause(self, ticker, name, _event_id):
        """Non-vacuous: prove each specimen DOES extend a real game prefix.

        Without this, the three tests above would still pass if the game prefix
        were quietly deleted from the map, and they would be asserting nothing
        about longest-prefix-wins.
        """
        shadowed = SEASON_SPECIMEN_SHADOWED_GAME_PREFIX[ticker]
        assert shadowed in set(KALSHI_GAME_TICKER_PREFIXES)
        assert ticker.lower().startswith(shadowed)


class TestGamePropsStillReachTheirGame:
    """The control that costs 75 correct production links if it breaks."""

    @pytest.mark.parametrize("ticker,name", GAME_PROP_SPECIMENS)
    def test_points_leader_is_game_level(self, ticker, name):
        assert is_kalshi_game_level_ticker(ticker) is True

    @pytest.mark.parametrize("ticker,name", GAME_PROP_SPECIMENS)
    def test_points_leader_reaches_game_matching(self, ticker, name):
        assert is_game_level_market(name, external_id=ticker, num_outcomes=2) is True

    @pytest.mark.parametrize("ticker,name", GAME_PROP_SPECIMENS)
    def test_points_leader_is_labelled_at_ingest(self, ticker, name):
        assert task_game_label(ticker) == "NBA"

    def test_kxnbaptsleader_is_not_in_the_futures_map(self):
        """It is a per-game prop. Its presence in the futures map is the defect.

        ``kxnbapts`` (player points prop) already covers it on the game side, so
        this is a deletion, not a move.
        """
        assert "kxnbaptsleader" not in KALSHI_FUTURES_TICKER_TO_SPORT_KEY
        assert "kxnbapts" in set(KALSHI_GAME_TICKER_PREFIXES)


class TestReverseDirectionDoesNotRegress:
    """The 143 cases where a GAME prefix extends a FUTURES prefix."""

    @pytest.mark.parametrize("ticker,shadowed_futures", REVERSE_CONTROL_SPECIMENS)
    def test_still_game_level(self, ticker, shadowed_futures):
        assert is_kalshi_game_level_ticker(ticker) is True

    @pytest.mark.parametrize("ticker,shadowed_futures", REVERSE_CONTROL_SPECIMENS)
    def test_the_shadowing_futures_prefix_really_exists(self, ticker, shadowed_futures):
        """Non-vacuous, same reason as above."""
        assert shadowed_futures in KALSHI_FUTURES_TICKER_TO_SPORT_KEY
        assert ticker.lower().startswith(shadowed_futures)

    def test_reverse_collisions_are_the_bulk(self):
        """The reverse direction dominates — so "refuse on any futures prefix" is wrong.

        RE-DERIVED (Q462). This asserted `== 143`, a literal measured 2026-08-29.
        Q435 then added twelve `kxatp*`/`kxwta*` tennis prefixes — a routine and
        correct map addition — and the literal read 155. `155 - 143 = 12`: the
        arithmetic closed exactly, so the count was never reporting a defect, only
        reporting that the maps had grown. A literal census in an assertion breaks
        on every future ticker addition, which trains the reader to re-baseline it
        without looking.

        So assert the PROPERTY the count was standing in for. The claim this test
        makes on behalf of the queue is that the reverse collision is the common
        case, which is why "refuse if any futures prefix matches" would fail
        silently across a large population of real game families rather than in a
        corner. Measured today: 155 reverse pairs against 8 forward. The bar is
        deliberately far below that ratio — it is a direction check, not a
        re-pinned number.
        """
        reverse = _game_extending_futures_pairs()
        forward = _futures_extending_game_pairs()

        assert forward, "forward collisions gone: this queue's whole class vanished"
        assert len(reverse) > 10 * len(forward), (
            f"reverse {len(reverse)} vs forward {len(forward)}: the reverse "
            "direction is no longer the bulk, so the argument for "
            "longest-prefix-wins over a blanket futures refusal needs re-reading"
        )

    def test_every_reverse_collision_still_reads_game_level(self):
        """The half that fails quietly, asserted over the whole map, not specimens.

        This is what the `== 143` literal was really protecting: not the size of
        the population but that none of it regressed. Walking the pairs says so
        directly and needs no edit when a ticker is added.
        """
        offenders = sorted(
            g
            for g, _futures in _game_extending_futures_pairs()
            if not is_kalshi_game_level_ticker(f"{g}-26TEST")
        )
        assert offenders == [], (
            f"{len(offenders)} game families that extend a futures prefix stopped "
            f"reading as game-level: {offenders}"
        )


class TestTheThreePredicatesAgree:
    """One question, one answer — asserted by walking the maps, not a literal list."""

    def test_no_futures_prefix_reads_as_game_level(self):
        offenders = [
            f
            for f in sorted(KALSHI_FUTURES_TICKER_TO_SPORT_KEY)
            if is_kalshi_game_level_ticker(f + "-26TEST")
        ]
        assert offenders == []

    def test_every_game_prefix_still_reads_as_game_level(self):
        offenders = [
            g
            for g in sorted(KALSHI_GAME_TICKER_PREFIXES)
            if not is_kalshi_game_level_ticker(g + "-26TEST")
        ]
        assert offenders == []

    def test_ingest_predicate_never_labels_a_future_a_game(self):
        """``tasks/kalshi`` walks a THIRD key set, so it gets the RULE, not the map.

        The invariant it must hold is its own: never return a label when a
        LONGER futures prefix matches. Asserting instead that it agrees with
        ``is_kalshi_game_level_ticker`` outright would be wrong — see the
        companion test below.
        """
        offenders = [
            f
            for f in sorted(KALSHI_FUTURES_TICKER_TO_SPORT_KEY)
            if task_game_label(f + "-26TEST") is not None
        ]
        assert offenders == []

    def test_the_four_unsupported_leagues_are_the_only_key_set_difference(self):
        """A deliberate difference, pinned so it cannot grow in silence.

        AHL / DEL / KHL / Dimayor carry a Kalshi display label — ingest still
        wants to name their markets properly — but they are excluded from
        ``KALSHI_GAME_TICKER_PREFIXES`` because this repo does not ingest their
        events, so the matching predicate correctly says "not a game" for them.
        That is the whole reason ``tasks/kalshi`` applies the rule itself rather
        than delegating. Any FIFTH such prefix is a decision, not an accident,
        and should fail here first.
        """
        labelled_but_not_matchable = sorted(
            p
            for p in KALSHI_TICKER_TO_DISPLAY_LABEL
            if task_game_label(p + "-26TEST") is not None
            and not is_kalshi_game_level_ticker(p + "-26TEST")
        )
        assert labelled_but_not_matchable == [
            "kxahlgame",
            "kxdelgame",
            "kxdimayorgame",
            "kxkhlgame",
        ]

    def test_futures_extending_game_collisions_are_pinned(self):
        """Seven distinct futures prefixes, eight pairs, after the map correction.

        Nine pairs before it (``kxnbaptsleader`` accounted for one, and
        ``kxnflrecydsrecord`` extends two different game prefixes). Pinned so a
        new collision arrives as a red test rather than as a silently
        misclassified market.
        """
        pairs = _futures_extending_game_pairs()
        assert len(pairs) == 8
        assert sorted({f for f, _g in pairs}) == [
            "kxmlbhits",
            "kxmlbhrderby",
            "kxnbapacific",
            "kxnbareboundtitle",
            "kxnflrecydsrecord",
            "kxvalorantgameteam",
            "kxwnbagamesplayed",
        ]

    def test_is_kalshi_game_ticker_is_gone(self):
        """Two names for one question is how they drifted. There is now one."""
        import app.utils.sport_keys as sk

        assert not hasattr(sk, "is_kalshi_game_ticker")


class TestTheRepairArmIsNarrow:
    """The self-healing arm in Phase 1.5, and the 14,046 links it must not take.

    Measured over all 123,544 linked Kalshi markets on production 2026-08-29:

        not is_kalshi_game_level_ticker(...)   14,049 rows   <- WRONG arm
        is_kalshi_shadowed_futures_ticker(...)      3 rows   <- the arm

    The 14,046 in between are linked BY NAME under a ticker with no game prefix
    at all — `kxwtasetwinner` (1,951), `kxatpgtotal` (862), `kxdota2map` (413),
    `kxboxing` (220), `kxcbagame` (189). Every one of them is a correct link. An
    arm keyed on the broad predicate would delete all of them and every counter
    it reports would still read healthy.

    AMENDED (Q462): `kxwtasetwinner` and `kxatpgtotal` were name-linked when that
    census was taken and are ticker-linked now — Q435 added them to the game map,
    which is the correct fix for that pair and shrinks the broad arm's blast
    radius by their 2,813 rows. It does not change the conclusion: the seven
    remaining census prefixes are still name-linked, and the narrow predicate is
    still the only one the arm may use. The census is left at its measured
    2026-08-29 values rather than silently restated — a re-measure belongs to the
    measurement lane, not to a test edit.
    """

    # The census head, verbatim from the production reading. These were prefixes
    # with NO game prefix at measure time; two have since acquired one (see the
    # Q462 amendment above), which the tests below derive rather than assume.
    NAME_LINKED_PREFIXES = [
        "kxwtasetwinner",
        "kxatpgtotal",
        "kxdota2map",
        "kxcodmap",
        "kxkborfi",
        "kxboxing",
        "kxjbleaguegame",
        "kxcbagame",
        "kxdimayorgame",
    ]

    @pytest.mark.parametrize("prefix", NAME_LINKED_PREFIXES)
    def test_name_linked_markets_are_not_repair_candidates(self, prefix):
        """The arm must be blind to every one of these, whatever else changed.

        RE-DERIVED (Q462). This used to assert, for all nine, that the broad
        predicate calls the prefix not-game-level — stated as the "premise" that
        makes the narrow arm necessary. That premise was true when written and
        Q435 expired two of them: `kxwtasetwinner` and `kxatpgtotal` are now game
        prefixes in their own right, so the broad predicate calls them game-level
        and they were never the broad arm's victims. The guard was working — it
        reported that its own reasoning had gone stale — but a premise that has to
        be retyped whenever the map grows is the wrong shape for it.

        The invariant that does NOT expire, and the one the ship rests on, is the
        second assertion: the narrow predicate refuses all nine. That is asserted
        unconditionally. The premise is now READ off the map instead of
        remembered, and split, because the two groups make different arguments.
        """
        from app.utils.sport_keys import is_kalshi_shadowed_futures_ticker

        ticker = f"{prefix.upper()}-26MAY10BOSPHI"

        # The load-bearing assertion: unconditional, for every census prefix.
        assert is_kalshi_shadowed_futures_ticker(ticker) is False

        # The premise, derived. A prefix is at risk from a broad-predicate arm
        # exactly when it has no game prefix of its own.
        has_game_prefix = any(
            prefix.startswith(g) for g in set(KALSHI_GAME_TICKER_PREFIXES)
        )
        assert is_kalshi_game_level_ticker(ticker) is has_game_prefix, (
            f"{prefix}: the broad predicate disagrees with the game map about "
            "whether this prefix is game-level — longest-prefix-wins should make "
            "these two answers the same question"
        )

    def test_the_broad_arm_would_still_destroy_most_of_this_census(self):
        """Non-vacuity for the test above: the danger it describes is still real.

        If every census prefix acquired a game prefix, the split above would go
        all-True and stop arguing anything. Measured 2026-08-29 the census head
        was nine name-linked prefixes; Q435 correctly moved two into the game map.
        The remaining seven are still linked BY NAME under a ticker with no game
        prefix at all, and a repair keyed on `not is_kalshi_game_level_ticker`
        still takes every one of them.
        """
        game = set(KALSHI_GAME_TICKER_PREFIXES)
        at_risk = [
            p
            for p in self.NAME_LINKED_PREFIXES
            if not any(p.startswith(g) for g in game)
        ]
        assert at_risk, (
            "every census prefix now has a game prefix, so this census no longer "
            "demonstrates the broad arm's blast radius — re-measure it before "
            "trusting the narrow-arm argument"
        )
        # All of them read not-game-level, which is exactly the broad arm's key.
        assert all(
            not is_kalshi_game_level_ticker(f"{p.upper()}-26MAY10BOSPHI")
            for p in at_risk
        )

    @pytest.mark.parametrize("ticker,name,_event_id", SEASON_SPECIMENS)
    def test_the_three_production_rows_are_repair_candidates(
        self, ticker, name, _event_id
    ):
        from app.utils.sport_keys import is_kalshi_shadowed_futures_ticker

        assert is_kalshi_shadowed_futures_ticker(ticker) is True

    @pytest.mark.parametrize("ticker,name", GAME_PROP_SPECIMENS)
    def test_a_real_game_prop_is_never_a_repair_candidate(self, ticker, name):
        from app.utils.sport_keys import is_kalshi_shadowed_futures_ticker

        assert is_kalshi_shadowed_futures_ticker(ticker) is False

    def test_the_arm_is_wired_to_the_narrow_predicate(self):
        """AST, not a substring scan — a comment naming it is not a call site.

        Q439 learned this the expensive way: its first wiring assertion went
        green on a comment.
        """
        import ast
        import inspect

        from app.tasks import prediction_market_matching as task_mod

        src = inspect.getsource(task_mod._phase15_revalidate)
        tree = ast.parse(inspect.cleandoc(src))
        called = {
            n.func.id
            for n in ast.walk(tree)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
        }
        assert "is_kalshi_shadowed_futures_ticker" in called
        assert "is_kalshi_game_level_ticker" not in called, (
            "the broad predicate must never gate the repair — 14,046 rows"
        )


class TestExactKeyCollisionFailsToFutures:
    """Undefined behaviour, defined: a tie is NOT game-level.

    The maps share no exact key today. If one ever arrives, the safe direction is
    the same on both rails this predicate feeds:

      * the anchor key builder — a false positive is an ABSORPTION, one game
        claiming another's identity (ruling 048 / gotcha #32);
      * the matching gate — a false positive puts a season market on a game page,
        which is the bug this queue exists to close.

    A false negative on either rail leaves a market unlinked: visible, reversible,
    and nobody's identity is destroyed.
    """

    def test_maps_share_no_exact_key_today(self):
        assert (
            set(KALSHI_GAME_TICKER_PREFIXES) & set(KALSHI_FUTURES_TICKER_TO_SPORT_KEY)
        ) == set()

    def test_a_tie_resolves_to_not_game_level(self, monkeypatch):
        import app.utils.sport_keys as sk

        colliding = "kxnbagame"
        assert colliding in set(sk.KALSHI_GAME_TICKER_PREFIXES)
        monkeypatch.setitem(
            sk.KALSHI_FUTURES_TICKER_TO_SPORT_KEY, colliding, "basketball_nba"
        )
        assert sk.is_kalshi_game_level_ticker("KXNBAGAME-26FEB19BOSGSW") is False
