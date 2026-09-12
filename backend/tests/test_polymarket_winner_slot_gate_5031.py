"""#5031 — the Polymarket winner slot may only be filled by a winner market.

THE DEFECT, in the shape a reader saw it. Alex's phone showed a Polymarket leg
of 52-49 on a match the sportsbooks had at 31-69. The leg was not a stale price
and not a hollow book: it was the price of a DIFFERENT QUESTION. Our market
60634611 is Polymarket condition `0x5edd…`, "Gauff vs. Rybakina: Match O/U
23.5" — a totals prop, ~0.50 by construction — stored as the match winner. The
real winner market (`0xa85e…`, 74% Gauff) was never the leg.

THE MECHANISM. `compute_source_home_probability` asked `select_primary_market`
first and exempted whatever it returned from admission. That exemption was
written for Kalshi, where the primary is chosen by a venue-side signal
(`feeds_win_prob_blend` on the ticker). For Polymarket `is_game_winner_market`
is hard-False on every row, so the tie-break degrades to "lowest market id" —
the OLDEST row — and Polymarket mints Exact Score, Total Corners and Player
Props before the match-winner child. The exempt row was routinely a derivative,
and its outcomes carry the team names (`St. Louis City SC 2 - 2 Minnesota
United FC`, `Venezia FC (-1.5)`, `Columbus Crew`), so `find_moneyline_outcome`
resolved them by containment and wrote a scoreline's price as the moneyline.

MEASURED, on every OPEN Polymarket market linked to an event commencing in
(-6h, +48h) — 1,096 markets / 231 groups, production, 2026-09-11 04:20Z:

  * 89 groups have a primary that is not a game winner;
  * in **10** the derivative is resolving and its number is the stored leg
    (before -> after, real rows, driven through the real function):
    Real Racing Club 0.910 -> 0.380 · Maringa 0.285 -> 0.535 ·
    Stockport 0.270 -> 0.500 · Columbus Crew 0.580 -> 0.500 ·
    Magdeburg 0.535 -> 0.455 · Orlando City 0.555 -> 0.520;
  * **7** events hold a leg written by a derivative whose group contains no
    winner market at all, and **3 of those are already frozen** — the
    derivative stopped resolving, so nothing would ever overwrite them. Event
    15301219 sat at 0.070 from an Exact Score `2 - 2` leg while Kalshi read
    0.705 on the same match.

That last bullet is why this ship has two halves and why a test suite for the
gate alone would pass over a live defect: A GATE THAT ONLY REFUSES TO WRITE
FREEZES THE OLD VALUE. The page renders `win_probability_sources`, not this
task.

THE THIRD THING, and the one that cost the measurement: the gate CANNOT be
source-agnostic. Applying the class recognizer to every source's primary reads
as the simpler rule and blanks the entire UFC card — over the same window's 468
Kalshi groups it refuses 13 live fight winners (`Fight Night: Silva vs
Delgado`, `KXUFCFIGHT-26SEP12SILDEL`) because the colon defeats the bare-matchup
shape, no winner word appears, and the ticker holds neither "game" nor "winner".
`TestTheKalshiCardDoesNotGoBlank` is that regression, pinned.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.models.models import Event

# The module object as well as the names, because one test restores the
# pre-#5031 behaviour by rebinding `admissible_as_blend_speaker` on the module —
# rebinding a name imported into THIS module would not change what
# `compute_source_home_probability` calls.
from app.utils import live_blend
from app.utils.live_blend import (
    MarketOutcomes,
    admissible_as_blend_speaker,
    compute_source_home_probability,
    count_admissible_speakers,
)


NOW = datetime(2026, 9, 11, 4, 20, tzinfo=timezone.utc)

HOME = "St. Louis City SC"
AWAY = "Minnesota United FC"


# =============================================================================
# Fakes — only the attributes the blend and the writer actually read
# =============================================================================


class _Market:
    def __init__(self, mid, name, *, source="polymarket", external_id=None):
        self.id = mid
        self.name = name
        self.source = source
        self.external_id = external_id


class _Outcome:
    current_yes_bid = current_yes_ask = None

    def __init__(self, rank, name, probability):
        self.rank = rank
        self.name = name
        self.current_probability = probability


class _EventRow:
    def __init__(self, event_id, wps=None, opening=None):
        self.id = event_id
        self.win_probability_sources = wps
        self.opening_home_probability = opening


class _Result:
    def __init__(self, rows, scalar=None):
        self._rows = rows
        self._scalar = scalar

    def all(self):
        return list(self._rows)

    def scalars(self):
        return self

    def scalar_one_or_none(self):
        return self._scalar

    def __iter__(self):
        return iter(self._rows)


class _FakeSession:
    """Serves the SELECTs the retirement issues and records its UPDATEs."""

    def __init__(self, event_row, outcomes=()):
        self._event_row = event_row
        self._outcomes = list(outcomes)
        self.updates = []
        self.added = []
        self.commits = 0

    async def get(self, model, pk):
        assert model is Event
        return self._event_row if pk == self._event_row.id else None

    async def execute(self, stmt):
        text = str(stmt)
        if text.lstrip().upper().startswith("UPDATE"):
            self.updates.append(stmt)
            return _Result([])
        if "futures_outcomes" in text:
            return _Result(self._outcomes)
        if "win_prob_snapshots" in text:
            return _Result([], scalar=None)
        if "odds_snapshots" in text:
            return _Result([], scalar=None)
        if "events" in text:
            return _Result([], scalar=self._event_row.win_probability_sources)
        raise AssertionError(f"unexpected statement: {text[:160]}")

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.commits += 1

    async def rollback(self):  # pragma: no cover — error path only
        pass

    def written_sources(self):
        """The `win_probability_sources` dict the recorded UPDATE would write."""
        for stmt in self.updates:
            values = dict(stmt._values)
            col = Event.__table__.c.win_probability_sources
            if col in values:
                return values[col].value
        return None


def _entry(mid, name, outcomes=(), *, source="polymarket", external_id=None):
    return MarketOutcomes(
        market=_Market(mid, name, source=source, external_id=external_id),
        outcomes=[_Outcome(rank, oname, prob) for rank, oname, prob in outcomes],
    )


def _ref(market_id, name, *, source="polymarket", external_id=None, event_id=15301219):
    from app.tasks.prediction_market_matching import _LinkedMarketRef

    return _LinkedMarketRef(
        market_id=market_id,
        source=source,
        external_id=external_id,
        name=name,
        event_id=event_id,
        event_commence_time=NOW - timedelta(hours=1),
        home_team_name=HOME,
        away_team_name=AWAY,
    )


# The production shape: the derivative books are minted BEFORE the winner child,
# so the winner loses the "lowest id" tie-break every time.
#
# THE LOWEST ID HERE IS `First Team to Score`, DELIBERATELY, and the first draft
# of this file got it wrong. Put `Exact Score` at the lowest id and the headline
# test passes on master too — every one of that market's outcomes names BOTH
# teams (`St. Louis City SC 2 - 2 Minnesota United FC`), so containment is
# ambiguous, it stays silent on its own and the group falls through to the
# winner without any help from this ship. `First Team to Score` lists the two
# teams exactly as the winner market does, so it RESOLVES while exempt. That is
# the shape production wears — event 15301194 (Columbus Crew) stores 0.580 off
# precisely this row — and it is the only shape in which the gate is
# load-bearing.
def _st_louis_group(with_winner=True):
    group = [
        _entry(
            59852281,
            f"{HOME} vs. {AWAY} - First Team to Score",
            [(1, HOME, 0.58), (2, AWAY, 0.42)],
        ),
        _entry(
            59852290,
            f"{HOME} vs. {AWAY} - Exact Score",
            [(1, f"{HOME} 2 - 2 {AWAY}", 0.07), (2, f"{HOME} 1 - 0 {AWAY}", 0.11)],
        ),
    ]
    if with_winner:
        group.append(
            _entry(
                59852299,
                f"{HOME} vs. {AWAY}",
                [(1, HOME, 0.705), (2, AWAY, 0.295)],
            )
        )
    return group


# =============================================================================
# 1. The gate — the primary loses its exemption
# =============================================================================


class TestThePrimaryIsNoLongerExemptFromAdmission:
    def test_the_oldest_row_being_a_derivative_no_longer_makes_it_the_speaker(self):
        """RED ON MASTER: the exempt `First Team to Score` row speaks 0.58.

        Kills the mutant that restores `if not is_primary and not …` — the one
        line this ship changes.
        """
        reading = compute_source_home_probability(_st_louis_group(), HOME, AWAY)

        assert reading is not None, "a real winner market is in the group"
        assert reading.market.name == f"{HOME} vs. {AWAY}", (
            "the winner child must speak, not the Exact Score row that outranks "
            "it on id"
        )
        assert reading.home_probability == pytest.approx(0.705)

    def test_the_derivative_that_resolves_is_the_whole_defect(self):
        """A derivative CAN resolve — that is why refusing it matters.

        Without this, a reader of the test above could conclude the derivative
        was simply unreadable and the gate inert. It is not. `First Team to
        Score` lists the two teams as its outcomes, exactly as the winner market
        does, so containment resolves it and 0.58 — the chance St. Louis scores
        first — is written as the chance St. Louis WINS.

        (The Exact Score row of the same event is the sibling case: every one of
        its outcomes names BOTH teams, so containment is ambiguous and it stays
        silent on its own. It is still refused — it is simply not the specimen
        that proves resolution, and reaching for it here is what made the first
        draft of this test pass for the wrong reason.)
        """
        alone = _st_louis_group(with_winner=False)[:1]
        assert alone[0].market.name.endswith("First Team to Score")
        assert admissible_as_blend_speaker(alone[0].market, is_primary=True) is False

        # `outcomes` is accepted and ignored (#5273), and so are
        # `event_commence_time` and `now` (#4854): this stub reproduces the
        # pre-#5031 rule, which was "the primary is exempt" and consulted
        # nothing else. Dropping a parameter would make the double reject the
        # call its subject now makes, which is a harness failure wearing the
        # costume of a regression. Each new parameter the real gate grows is
        # added here as accepted-and-ignored for exactly that reason — the stub
        # must stay callable by the subject while still deciding the old way.
        def _exempt_primary(
            market, *, is_primary, outcomes=None, event_commence_time=None, now=None
        ):
            return True if is_primary else False

        original = live_blend.admissible_as_blend_speaker
        live_blend.admissible_as_blend_speaker = _exempt_primary
        try:
            before = compute_source_home_probability(alone, HOME, AWAY)
        finally:
            live_blend.admissible_as_blend_speaker = original

        assert before is not None and before.home_probability == pytest.approx(0.58), (
            "the pre-#5031 behaviour must reproduce, or this suite is proving "
            "nothing about the defect"
        )
        assert compute_source_home_probability(alone, HOME, AWAY) is None

    @pytest.mark.parametrize(
        "name",
        [
            # Every one measured on production in the (-6h,+48h) window.
            "Venezia FC vs. ACF Fiorentina - More Markets",
            "St. Louis City SC vs. Minnesota United FC - Exact Score",
            "St. Louis City SC vs. Minnesota United FC - First Team to Score",
            "St. Louis City SC vs. Minnesota United FC - Second Half Result",
            "St. Louis City SC vs. Minnesota United FC - Halftime Result",
            "Stade Rennais FC 1901 vs. Olympique de Marseille - Player Props",
            "Burgos CF vs. AD Ceuta FC - Total Corners",
            "Cukierman/Poljak vs. Cornea/Neuchrist: Match O/U 23.5",
            "Córdoba CF vs. UD Almería: UD Almería O/U 5.5 Corners",
        ],
    )
    def test_the_production_derivative_vocabulary_is_refused_as_primary(self, name):
        assert (
            admissible_as_blend_speaker(_Market(1, name), is_primary=True) is False
        ), f"{name!r} is not a game winner and must not fill the winner slot"

    @pytest.mark.parametrize(
        "name",
        [
            # The other side of the same window: real Polymarket winners, which
            # must keep speaking. The accented ones are #5041's fix and this is
            # the test that notices if the letter class narrows back to ASCII.
            "St. Louis City SC vs. Minnesota United FC",
            "AFC Bournemouth vs. Brentford FC",
            "1. FC Köln vs. SV Werder Bremen",
            "Club León FC vs. Atlético San Luis",
            "SE Palmeiras vs. São Paulo FC",
            "Holy Cross vs. Miami (OH)",
        ],
    )
    def test_a_real_polymarket_winner_is_still_admitted_as_primary(self, name):
        assert admissible_as_blend_speaker(_Market(1, name), is_primary=True) is True


# =============================================================================
# 2. The regression the measurement caught — the gate is PER SOURCE
# =============================================================================


class TestTheKalshiCardDoesNotGoBlank:
    """A source-agnostic gate refuses 13 live UFC winners. Measured, not feared.

    `Fight Night: Silva vs Delgado` is the real fight winner: the colon defeats
    the bare-matchup shape, the title has no winner word, and `KXUFCFIGHT-…`
    carries neither "game" nor "winner", so the shared CLASS recognizer answers
    "other". Kalshi's admission is a venue-side ticker rule
    (`feeds_win_prob_blend`) applied in `_reading_for_entry`, and that rule —
    not this one — is the one that is right about a Kalshi row.
    """

    UFC = "Fight Night: Silva vs Delgado"
    TICKER = "KXUFCFIGHT-26SEP12SILDEL"

    def test_the_class_recognizer_really_does_refuse_a_real_fight_winner(self):
        """The premise of this whole class. If this flips, the guard is inert."""
        from app.utils.game_market_class import classify_game_market_class

        assert classify_game_market_class(self.UFC, self.TICKER) != "moneyline"

    def test_a_kalshi_primary_is_still_admitted(self):
        market = _Market(1, self.UFC, source="kalshi", external_id=self.TICKER)
        assert admissible_as_blend_speaker(market, is_primary=True) is True

    def test_the_ufc_primary_still_speaks_through_the_real_function(self):
        group = [
            _entry(
                1,
                self.UFC,
                [(1, "Silva", 0.775), (2, "Delgado", 0.225)],
                source="kalshi",
                external_id=self.TICKER,
            )
        ]
        reading = compute_source_home_probability(group, "Silva", "Delgado")

        assert reading is not None, (
            "gating the Kalshi primary on the class recognizer blanks the card"
        )
        assert reading.home_probability == pytest.approx(0.775)

    def test_a_kalshi_group_can_never_be_retired_by_the_speaker_count(self):
        group = [
            _entry(
                1,
                self.UFC,
                [(1, "Silva", 0.775)],
                source="kalshi",
                external_id=self.TICKER,
            )
        ]
        assert count_admissible_speakers(group) == 1

    def test_the_kalshi_fallback_keeps_its_stricter_burden(self):
        """Unchanged by this ship: only the PRIMARY's exemption was source-split.

        A Kalshi row that is not the primary still has to clear the class
        recognizer, which is the #759 "new admission proves itself" rule. A
        mutant that returns True for every Kalshi row dies here.
        """
        market = _Market(2, self.UFC, source="kalshi", external_id=self.TICKER)
        assert admissible_as_blend_speaker(market, is_primary=False) is False


# =============================================================================
# 3. The discriminator — structural silence vs a transient one
# =============================================================================


class TestStructuralSilenceIsNotTheSameAsAnUnpricedWinner:
    def test_a_group_of_only_derivatives_counts_zero_speakers(self):
        group = _st_louis_group(with_winner=False)
        assert compute_source_home_probability(group, HOME, AWAY) is None
        assert count_admissible_speakers(group) == 0

    def test_a_winner_market_with_no_price_is_silent_but_still_counts(self):
        """The transient case. Retiring here would twitch the hero every 15 min.

        Kills the mutant that retires on `reading is None` instead of on the
        speaker count.
        """
        group = _st_louis_group(with_winner=False)
        group.append(
            _entry(59852299, f"{HOME} vs. {AWAY}", [(1, HOME, None), (2, AWAY, None)])
        )

        assert compute_source_home_probability(group, HOME, AWAY) is None
        assert count_admissible_speakers(group) == 1

    def test_an_empty_group_counts_zero_without_raising(self):
        assert count_admissible_speakers([]) == 0
        assert count_admissible_speakers(None) == 0


# =============================================================================
# 4. The other half — the stored leg is RETIRED, not left frozen
# =============================================================================


@pytest.mark.asyncio
class TestTheWriterRetiresALegNoWinnerMarketCanBack:
    async def test_the_frozen_leg_is_removed_when_the_group_holds_no_winner(self):
        """RED ON MASTER: master returns None and leaves 0.07 on the event.

        Event 15301219's real state on 2026-09-11: a Polymarket leg of 0.070
        written by an Exact Score row that has since stopped resolving, against
        Kalshi's 0.705. Nothing on master ever overwrites it.
        """
        from app.tasks.prediction_market_matching import _phase2_persist_group_reading

        event_row = _EventRow(
            15301219,
            {
                "polymarket": {"value": 0.07, "updated_at": "2026-09-10T18:00:00+00:00"},
                "kalshi": {"value": 0.705, "updated_at": "2026-09-11T04:00:00+00:00"},
            },
        )
        session = _FakeSession(event_row)
        stats = {"snapshots_written": 0, "snapshots_deduped": 0, "errors": []}

        spoke = await _phase2_persist_group_reading(
            session,
            [
                _ref(59852281, f"{HOME} vs. {AWAY} - Exact Score"),
                _ref(59852290, f"{HOME} vs. {AWAY} - First Team to Score"),
            ],
            stats,
        )

        assert spoke is None
        written = session.written_sources()
        assert written is not None, "the frozen leg must be retired, not left alone"
        assert "polymarket" not in written
        assert written["kalshi"]["value"] == 0.705, (
            "a retirement removes ONE source key and never touches a sibling"
        )
        assert stats["funnel"]["blend_source_retired_no_winner_market"] == 1
        assert session.commits == 1

    async def test_a_transient_silence_leaves_the_stored_leg_alone(self):
        """A winner market exists but has no price — nothing is written at all.

        Kills the mutant that drops the `count_admissible_speakers` check and
        retires on every None reading.
        """
        from app.tasks.prediction_market_matching import _phase2_persist_group_reading

        event_row = _EventRow(
            15301219, {"polymarket": {"value": 0.42, "updated_at": "x"}}
        )
        session = _FakeSession(event_row)
        stats = {"snapshots_written": 0, "snapshots_deduped": 0, "errors": []}

        spoke = await _phase2_persist_group_reading(
            session,
            [
                _ref(59852281, f"{HOME} vs. {AWAY} - Exact Score"),
                _ref(59852299, f"{HOME} vs. {AWAY}"),
            ],
            stats,
        )

        assert spoke is None, "no outcomes are served, so nothing can speak"
        assert session.updates == [], (
            "a winner market with no price is transient — the leg stays"
        )
        assert "blend_source_retired_no_winner_market" not in stats.get("funnel", {})

    async def test_an_event_with_no_stored_leg_writes_nothing(self):
        """Idempotence: the retirement is a no-op once it has run."""
        from app.tasks.prediction_market_matching import _phase2_persist_group_reading

        session = _FakeSession(_EventRow(15301219, {"kalshi": {"value": 0.7}}))
        stats = {"snapshots_written": 0, "snapshots_deduped": 0, "errors": []}

        await _phase2_persist_group_reading(
            session, [_ref(59852281, f"{HOME} vs. {AWAY} - Exact Score")], stats,
        )

        assert session.updates == []
        assert session.commits == 0

    async def test_a_group_that_speaks_never_reaches_the_retirement(self):
        """The winner child speaks, so the leg is UPDATED rather than dropped."""
        from app.tasks.prediction_market_matching import _phase2_persist_group_reading

        session = _FakeSession(
            _EventRow(15301219, {"polymarket": {"value": 0.07}}),
            outcomes=[
                type(
                    "_O",
                    (),
                    {
                        "market_id": 59852299,
                        "rank": 1,
                        "name": HOME,
                        "current_probability": 0.705,
                        "current_yes_bid": None,
                        "current_yes_ask": None,
                        "last_updated": None,
                    },
                )(),
            ],
        )
        stats = {"snapshots_written": 0, "snapshots_deduped": 0, "errors": []}

        spoke = await _phase2_persist_group_reading(
            session,
            [
                _ref(59852281, f"{HOME} vs. {AWAY} - Exact Score"),
                _ref(59852299, f"{HOME} vs. {AWAY}"),
            ],
            stats,
        )

        assert spoke == 59852299
        written = session.written_sources()
        assert written is not None and "polymarket" in written
        assert written["polymarket"]["value"] == pytest.approx(0.705)
        assert "blend_source_retired_no_winner_market" not in stats.get("funnel", {})
