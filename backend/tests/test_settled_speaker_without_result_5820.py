"""#5820 — a SETTLED market may not be the live speaker for a game with no result.

THE PAGE THIS IS ABOUT. `/events/15310861` (Liu vs Blinkova, WTA challenger) drew
"**No result reported**" under a hero reading **99% – 1%**, beside "CHANCE OF
GOING OVER 100% / 100% / 100%" and "Liu wins Set 1 100%". Every number on it is
a settlement price being served as a current observation.

IT IS DECIDABLE FROM THE ROW ALONE — no ground truth, no venue call:

    events.win_probability_sources->'kalshi'
        value       0.99
        updated_at  2026-09-13T03:53:13Z        <-- we claim we just read this
        market_id   60836384
    futures_markets 60836384
        status      'resolved'
        settled_at  2026-09-13T00:40:00Z        <-- it stopped moving here
    events.completed_at  NULL                   <-- and we have no result

Three hours and thirteen minutes after the book closed, the writer stamped it
again as if it were live.

WHY #5548'S ARM CANNOT REACH IT. That ship retires a leg whose every admissible
speaker is a SETTLED BOOK, and `_is_settled_book` is a PRICE mechanism: every
outcome at 0.00/1.00, so `find_moneyline_outcome` resolves by no route, the
reading is None and `_retire_unbacked_blend_source` runs. A Kalshi book settles
at the last TRADE — 0.99/0.01 — which is strictly inside the band. So the
reading is NOT None, the retirement is never called, and the writer re-publishes
the settlement price every fifteen minutes. The price arm and the status arm are
two different questions about one word.

BOTH DIRECTIONS, AND THE SECOND IS THE LOAD-BEARING ONE (gotcha #43). Measured
on production over the 7-day linked window, 2026-09-13 05:2xZ:

    events holding a kalshi blend leg                            936
      cited market settled, event has NO result                  151   <- refused
        of those, at a NON-terminal price (invisible to #5548)    106
      cited market settled, event IS completed                    221   <- MUST speak
      cited market not settled                                    564   <- MUST speak
    polymarket, same shape, no result                              23   <- refused

A blanket "a resolved market is inadmissible" would delete the number 221
finished games are supposed to show — "settled means settled", heroes show
winners. That is why the clause asks `event_has_result is False` and not
`not event_has_result`, and why the tri-state exists at all.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.models.models import Event
from app.utils.live_blend import (
    MarketOutcomes,
    admissible_as_blend_speaker,
    admissible_speakers_are_settled_without_result,
    admissible_speakers_are_unobserved_since_kickoff,
    compute_source_home_probability,
    count_admissible_speakers,
)


# The production specimen, by name and at its real ids.
EVENT_ID = 15310861
MARKET_ID = 60836384
TICKER = "KXWTACHALLENGERMATCH-26SEP12LIUBLI"
HOME = "Claire Liu"
AWAY = "Anna Blinkova"
SETTLED_AT = datetime(2026, 9, 13, 0, 40, tzinfo=timezone.utc)
NOW = datetime(2026, 9, 13, 3, 53, tzinfo=timezone.utc)
KICKOFF = NOW - timedelta(hours=5)


# =============================================================================
# Fakes — only the attributes the gate and the writer actually read
# =============================================================================


class _Market:
    def __init__(self, mid, name, *, source="kalshi", external_id=None, status="open"):
        self.id = mid
        self.name = name
        self.source = source
        self.external_id = external_id
        self.status = status


class _Outcome:
    current_yes_bid = current_yes_ask = None

    def __init__(self, rank, name, probability, *, is_winner=False, market_id=None):
        self.rank = rank
        self.name = name
        self.current_probability = probability
        self.is_winner = is_winner
        self.market_id = market_id
        # `last_updated` is the stamp #4854's clause reads (`_last_observation`)
        # — the name matters: a fake carrying any other spelling reads as an
        # unfetched book and makes that clause abstain, which would let this
        # file pass while asserting nothing about the interaction.
        self.last_updated = NOW


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
    """Serves the SELECTs the writer/retirement issue and records its UPDATEs."""

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
        for stmt in self.updates:
            values = dict(stmt._values)
            col = Event.__table__.c.win_probability_sources
            if col in values:
                return values[col].value
        return None


def _settled_kalshi_pair(*, has_result, status="resolved", graded=False):
    """The specimen's group: the two sides of the WTA match, settled at 0.99/0.01.

    A per-team Kalshi pair, priced where the book actually closed rather than at
    the 1.00/0.00 the price arm looks for.
    """
    return [
        MarketOutcomes(
            market=_Market(
                MARKET_ID, f"{HOME} vs {AWAY}", external_id=TICKER, status=status
            ),
            outcomes=[
                _Outcome(1, HOME, 0.99, is_winner=graded),
                _Outcome(2, AWAY, 0.01),
            ],
            event_commence_time=KICKOFF,
            event_has_result=has_result,
        ),
    ]


# =============================================================================
# 1. The clause — refused with no result, admitted with one
# =============================================================================


class TestTheSettledSpeakerClause:
    def test_the_specimen_is_refused_when_the_event_has_no_result(self):
        """RED ON MASTER: 60836384 speaks, and 0.99 lands on a resultless page."""
        entry = _settled_kalshi_pair(has_result=False)[0]
        assert (
            admissible_as_blend_speaker(
                entry.market,
                is_primary=True,
                outcomes=entry.outcomes,
                event_commence_time=entry.event_commence_time,
                event_has_result=False,
            )
            is False
        )

    def test_the_same_row_speaks_once_the_event_is_completed(self):
        """The 221 finished games. Settled means settled — the leg stays."""
        entry = _settled_kalshi_pair(has_result=True)[0]
        assert (
            admissible_as_blend_speaker(
                entry.market,
                is_primary=True,
                outcomes=entry.outcomes,
                event_commence_time=entry.event_commence_time,
                event_has_result=True,
            )
            is True
        )

    def test_an_unmeasured_caller_keeps_todays_behaviour(self):
        """None is 'not measured', not 'no result'.

        Kills the mutant that writes `not event_has_result`: it reads the same
        on False and on None, and would arm the clause at every construction
        site that has never heard of it.
        """
        entry = _settled_kalshi_pair(has_result=None)[0]
        assert (
            admissible_as_blend_speaker(
                entry.market,
                is_primary=True,
                outcomes=entry.outcomes,
                event_commence_time=entry.event_commence_time,
                event_has_result=None,
            )
            is True
        )

    def test_an_open_market_on_a_resultless_event_still_speaks(self):
        """The 564. The clause is about settlement, not about having no result."""
        entry = MarketOutcomes(
            market=_Market(
                MARKET_ID, f"{HOME} vs {AWAY}", external_id=TICKER, status="open"
            ),
            outcomes=[_Outcome(1, HOME, 0.62), _Outcome(2, AWAY, 0.38)],
            event_commence_time=KICKOFF,
            event_has_result=False,
        )
        assert (
            admissible_as_blend_speaker(
                entry.market,
                is_primary=True,
                outcomes=entry.outcomes,
                event_commence_time=entry.event_commence_time,
                event_has_result=False,
            )
            is True
        )

    def test_a_graded_outcome_settles_a_market_kalshi_left_open(self):
        """Gotcha #33: Kalshi settled markets keep `status='open'`.

        The reason the clause delegates to `settledness.market_assigned_settled`
        rather than typing `status == 'resolved'` here — that spelling would
        read this row as live forever.
        """
        entry = _settled_kalshi_pair(has_result=False, status="open", graded=True)[0]
        assert (
            admissible_as_blend_speaker(
                entry.market,
                is_primary=True,
                outcomes=entry.outcomes,
                event_commence_time=entry.event_commence_time,
                event_has_result=False,
            )
            is False
        )

    def test_the_clause_outranks_the_kalshi_primary_exemption(self):
        """Placement, not ordering trivia.

        `admissible_as_blend_speaker` returns True immediately for a Kalshi
        PRIMARY. Put this clause after that line and the production specimen —
        a Kalshi primary — still speaks and the ship changes nothing. Asked
        here as the primary AND as a fallback so the mutant that moves the
        clause below the exemption dies on the first arm.
        """
        entry = _settled_kalshi_pair(has_result=False)[0]
        for is_primary in (True, False):
            assert (
                admissible_as_blend_speaker(
                    entry.market,
                    is_primary=is_primary,
                    outcomes=entry.outcomes,
                    event_has_result=False,
                )
                is False
            ), f"a settled Kalshi market spoke as is_primary={is_primary}"

    def test_polymarket_is_refused_on_the_same_evidence(self):
        """The 23. The clause is source-agnostic; the row refutes itself."""
        entry = MarketOutcomes(
            market=_Market(
                60258512,
                f"{HOME} vs. {AWAY}",
                source="polymarket",
                status="resolved",
            ),
            outcomes=[_Outcome(1, HOME, 0.97), _Outcome(2, AWAY, 0.03)],
            event_commence_time=KICKOFF,
            event_has_result=False,
        )
        assert (
            admissible_as_blend_speaker(
                entry.market,
                is_primary=True,
                outcomes=entry.outcomes,
                event_has_result=False,
            )
            is False
        )


# =============================================================================
# 2. The reading — the group falls silent instead of publishing 0.99
# =============================================================================


class TestTheGroupStopsSpeaking:
    def test_the_settled_pair_publishes_nothing(self):
        group = _settled_kalshi_pair(has_result=False)
        assert compute_source_home_probability(group, HOME, AWAY) is None
        assert count_admissible_speakers(group) == 0

    def test_the_completed_event_still_publishes_its_settled_number(self):
        """The other direction, through the writer rather than the predicate."""
        group = _settled_kalshi_pair(has_result=True)
        reading = compute_source_home_probability(group, HOME, AWAY)
        assert reading is not None, (
            "a finished game must keep the number that says who won"
        )
        assert reading.home_probability == pytest.approx(0.99)

    def test_a_settled_sibling_is_not_averaged_into_a_live_speaker(self):
        """A contributor is gated like a speaker (CERT-2646), #5820 included.

        The Kalshi devig arm asks the ticker rule directly rather than going
        through `admissible_as_blend_speaker`, so the clause has to be asked
        there too or half of a per-team pair settles and is still averaged in.
        """
        live = MarketOutcomes(
            market=_Market(
                70000001,
                f"{HOME} vs {AWAY}",
                external_id=TICKER,
                status="open",
            ),
            outcomes=[_Outcome(1, HOME, 0.60), _Outcome(2, AWAY, 0.40)],
            event_commence_time=KICKOFF,
            event_has_result=False,
        )
        settled = MarketOutcomes(
            market=_Market(
                70000002,
                f"{AWAY} vs {HOME}",
                external_id=TICKER,
                status="resolved",
            ),
            outcomes=[_Outcome(1, AWAY, 0.99), _Outcome(2, HOME, 0.01)],
            event_commence_time=KICKOFF,
            event_has_result=False,
        )
        reading = compute_source_home_probability([live, settled], HOME, AWAY)
        assert reading is not None
        assert reading.home_probability == pytest.approx(0.60), (
            "the live half must stand alone; averaging in a settled book would "
            "read 0.305 and be stamped as a devigged moneyline"
        )
        assert reading.devigged is False


# =============================================================================
# 3. The cause separator — the funnel must not fold this into an old counter
# =============================================================================


class TestTheFunnelSaysWhichSilence:
    def test_the_specimen_names_the_settled_cause(self):
        assert (
            admissible_speakers_are_settled_without_result(
                _settled_kalshi_pair(has_result=False)
            )
            is True
        )

    def test_a_completed_event_names_no_cause(self):
        assert (
            admissible_speakers_are_settled_without_result(
                _settled_kalshi_pair(has_result=True)
            )
            is False
        )

    def test_a_group_with_no_speaker_at_all_abstains(self):
        """#5031's population keeps its own counter.

        A pure derivative is refused with the clause armed AND with it
        abstaining, so this cause must not claim it.
        """
        group = [
            MarketOutcomes(
                market=_Market(
                    59852281,
                    f"{HOME} vs {AWAY} - Exact Score",
                    source="polymarket",
                    status="open",
                ),
                outcomes=[_Outcome(1, "2 - 1", 0.07)],
                event_commence_time=KICKOFF,
                event_has_result=False,
            )
        ]
        assert admissible_speakers_are_settled_without_result(group) is False

    def test_an_empty_group_abstains_without_raising(self):
        assert admissible_speakers_are_settled_without_result([]) is False
        assert admissible_speakers_are_settled_without_result(None) is False

    def test_the_kickoff_cause_is_not_stolen_by_this_one(self):
        """#4854's population must still report as #4854's.

        An OPEN book nobody has looked at since kickoff is refused by the
        observation clause and by nothing here.
        """
        stale = MarketOutcomes(
            market=_Market(
                70000003,
                f"{HOME} vs. {AWAY}",
                source="polymarket",
                status="open",
            ),
            outcomes=[
                _Outcome(1, HOME, 0.55),
                _Outcome(2, AWAY, 0.45),
            ],
            event_commence_time=KICKOFF,
            event_has_result=False,
        )
        for outcome in stale.outcomes:
            outcome.last_updated = KICKOFF - timedelta(hours=2)
        assert admissible_speakers_are_unobserved_since_kickoff([stale], now=NOW) is True
        assert admissible_speakers_are_settled_without_result([stale]) is False


# =============================================================================
# 4. The writer — the frozen 0.99 is actually removed from the event
# =============================================================================


def _ref(market_id, name, *, source="kalshi", external_id=TICKER, status="resolved",
         has_result=False):
    from app.tasks.prediction_market_matching import _LinkedMarketRef

    return _LinkedMarketRef(
        market_id=market_id,
        source=source,
        external_id=external_id,
        name=name,
        event_id=EVENT_ID,
        event_commence_time=KICKOFF,
        home_team_name=HOME,
        away_team_name=AWAY,
        status=status,
        event_has_result=has_result,
    )


@pytest.mark.asyncio
class TestTheFrozenLegIsRetired:
    async def test_the_specimens_leg_is_removed_and_counted_apart(self):
        """RED ON MASTER: 0.99 survives every pass because the reading is not None."""
        from app.tasks.prediction_market_matching import _phase2_persist_group_reading

        event_row = _EventRow(
            EVENT_ID,
            {
                "kalshi": {
                    "value": 0.99,
                    "updated_at": "2026-09-13T03:53:13.405235+00:00",
                },
                "espn": {"value": 0.5, "updated_at": "2026-09-13T03:00:00+00:00"},
            },
        )
        session = _FakeSession(
            event_row,
            outcomes=[
                _Outcome(1, HOME, 0.99, market_id=MARKET_ID),
                _Outcome(2, AWAY, 0.01, market_id=MARKET_ID),
            ],
        )
        stats = {"snapshots_written": 0, "snapshots_deduped": 0, "errors": []}

        spoke = await _phase2_persist_group_reading(
            session, [_ref(MARKET_ID, f"{HOME} vs {AWAY}")], stats,
        )

        assert spoke is None, "a settled market may not speak for a resultless game"
        written = session.written_sources()
        assert written is not None, "the frozen leg must be retired, not left alone"
        assert "kalshi" not in written
        assert written["espn"]["value"] == 0.5, (
            "a retirement removes ONE source key and never touches a sibling"
        )
        assert stats["funnel"]["blend_source_retired_settled_without_result"] == 1
        for stolen in (
            "blend_source_retired_settled_book",
            "blend_source_retired_no_winner_market",
            "blend_source_retired_unobserved_since_kickoff",
        ):
            assert stolen not in stats["funnel"], (
                f"a new cause folded into {stolen} reads as a spike in an old one"
            )
        assert session.commits == 1

    async def test_a_completed_event_keeps_its_settled_leg(self):
        """The 221, end to end. Nothing is written and nothing is retired."""
        from app.tasks.prediction_market_matching import _phase2_persist_group_reading

        event_row = _EventRow(
            EVENT_ID, {"kalshi": {"value": 0.99, "updated_at": "x"}},
        )
        session = _FakeSession(
            event_row,
            outcomes=[
                _Outcome(1, HOME, 0.99, market_id=MARKET_ID),
                _Outcome(2, AWAY, 0.01, market_id=MARKET_ID),
            ],
        )
        stats = {"snapshots_written": 0, "snapshots_deduped": 0, "errors": []}

        spoke = await _phase2_persist_group_reading(
            session,
            [_ref(MARKET_ID, f"{HOME} vs {AWAY}", has_result=True)],
            stats,
        )

        assert spoke == MARKET_ID, "the settled winner still speaks for a finished game"
        written = session.written_sources()
        assert written is not None and "kalshi" in written, (
            "retiring this leg would delete the number a finished game shows"
        )
        assert written["kalshi"]["value"] == pytest.approx(0.99)


# =============================================================================
# 5. The plumbing — the tri-state actually reaches the gate from both writers
# =============================================================================


class TestBothWritersMeasureIt:
    def test_the_matcher_reads_completed_at_into_the_tri_state(self):
        """A source scan would pass on a commented-out line; this reads the AST.

        Both live writers must derive `event_has_result` from the EVENT's
        `completed_at` — not from `status`, which is a different column with a
        different vocabulary, and not from a literal.
        """
        import ast
        import pathlib

        root = pathlib.Path(__file__).resolve().parents[1] / "app" / "tasks"
        for name in ("prediction_market_matching.py", "live_blend_refresh.py"):
            tree = ast.parse((root / name).read_text())
            derived = [
                node
                for node in ast.walk(tree)
                if isinstance(node, ast.keyword)
                and node.arg == "event_has_result"
                and isinstance(node.value, ast.Compare)
                and isinstance(node.value.left, ast.Attribute)
                and node.value.left.attr == "completed_at"
            ]
            assert derived, (
                f"{name} must derive event_has_result from the event's "
                "completed_at, or the gate never arms on its path"
            )
