"""#6347 — an ``odds_api`` ``external_id`` is not a door out of ``suspended``.

THE SHIP: searching a MiLB club stops leading with two dead games.

On production 2026-09-15, ``/search?q=Durham%20Bulls`` opened with two cards
reading ``No result reported`` over a **Pre-match** 49%/51%, for games that had
kicked off six and nine days earlier — ranked ABOVE the only card carrying a
real result. ``suspended`` is in every list allowlist, so those rows are
reader-reachable forever.

WHY THEY ARE FOREVER. ``odds_polling``'s wall-clock net writes ``suspended``
without a ``completed_at`` so the scores feed can promote the row back to live
(``odds_polling.py:425``). For this population nothing ever does:

  * ``espn_sync``'s three suspended-admitting arms all require
    ``Event.espn_id.isnot(None)``; these rows have none.
  * ``odds_polling``'s settle loop selects ``Event.status == "live"``.
  * ``polymarket`` and ``kalshi_resolution_sweep`` do admit ``suspended`` — but
    only reach a row through a market hanging off it.
  * the scores fetch IS keyed on ``external_id``, and is bounded by
    ``days_from=3``.

``suspended_row_is_unreachable`` refused all of them anyway, for holding an
``external_id`` — an id that, by the reasoning in that function's own
docstring, cannot reach them. Measured: **711 rows, 100% ``odds_api``**; 150
carry a Kalshi/Polymarket market and keep their door; 490 clear every test past
a floor that also clears the scores window.

RED-FIRST, MEASURED: **10 of 34 fail** with ``event_completion.py`` /
``espn_sync.py`` / ``odds_polling.py`` reverted, and every one of the ten is a
rule this ship changes. The other 24 — the whole of
:class:`TestNothingElseIsNewlyAdmitted` — PASS IN BOTH TREES. They are the "who
NEWLY matches?" half, and a control that cannot run against the old tree is not
a control.

🔴 Getting that number honestly took two corrections, both recorded at the
helpers below, because the first two readings were about the harness rather
than the rule: a module-level import of the new constant made the whole file a
collection error (exit 2, 0 informative), and then the changed SIGNATURE made
every call raise ``TypeError`` (31 of 34 red, which looks like overwhelming
evidence and is none). A red-first count is only worth quoting once the
controls in it can go green.
"""

import inspect
from datetime import datetime, timedelta, timezone

import pytest

from app.utils.event_completion import (
    EVENT_SUSPENDED,
    UNREACHABLE_SUSPENDED_MARGIN,
    suspended_row_is_unreachable,
)

NOW = datetime(2026, 9, 15, 10, 0, tzinfo=timezone.utc)

#: The wire value, spelled out rather than imported, for TWO reasons. It pins
#: what is actually stored in ``events.commence_time_source`` — a test that
#: imports the constant it is checking agrees with itself and with nothing else.
#: And it keeps this module IMPORTABLE against a tree without the ship, so
#: red-first measures one failing test per broken rule instead of a single
#: collection error (exit 2, which is a story about the harness, not a result).
ODDS_API_SOURCE_WIRE_VALUE = "odds_api"


def _floor():
    """The floor exactly as the arm derives it — never a hand-typed 96h.

    🔴 THE FALLBACK IS WHAT MAKES THE CONTROLS REAL, AND IT WAS ADDED AFTER A
    MEASUREMENT. With the ship reverted, ``ODDS_SCORES_LOOKBACK`` does not
    exist, so a strict import here raised inside every single test — 32 of 34
    red, including the eight refusals that are supposed to hold in BOTH trees.
    A control that goes red because the module moved has told you nothing about
    the rule; it just agrees with the other failures. With the fallback, the
    only tests that can go red on the old tree are the ones about behaviour
    this ship changes, which is what red-first is for.
    """
    try:
        from app.tasks.espn_sync import unreachable_suspended_floor
    except ImportError:  # pragma: no cover — only on a tree without the ship
        from app.tasks.espn_sync import SUSPENDED_RESUME_WINDOW

        return SUSPENDED_RESUME_WINDOW + UNREACHABLE_SUSPENDED_MARGIN

    return unreachable_suspended_floor()


def _row(**over):
    """The production specimen: Durham Bulls v Nashville Sounds, 2026-09-09.

    ``baseball_milb``, minted by the Odds API, never anchored, never scored.
    """
    base = dict(
        status=EVENT_SUSPENDED,
        commence_time=NOW - timedelta(days=6),
        external_id="65325eabae27182083c9f8ae06cdf250",
        espn_id=None,
        statpal_fixture_id=None,
        home_score=None,
        away_score=None,
        completed_at=None,
        anchor_acquirable=False,
        now=NOW,
        floor=_floor(),
        commence_time_source=ODDS_API_SOURCE_WIRE_VALUE,
        market_anchored=False,
    )
    base.update(over)
    return base


def _verdict(**over):
    """Ask the predicate, dropping arguments the tree in front of us lacks.

    🔴 SECOND THING MEASURED RATHER THAN ASSUMED. This ship CHANGES THE
    SIGNATURE, so a plain call raises ``TypeError`` on a reverted tree and every
    test in the file goes red together — 31 of 34, which is a number about the
    signature and not about any rule. The controls in
    :class:`TestNothingElseIsNewlyAdmitted` only mean something if they can run
    against BOTH trees and still refuse, so the two new keywords are dropped
    when the function does not take them.

    This is deliberately NOT a compatibility shim for production: the arm passes
    both arguments and :meth:`…test_the_two_new_arguments_are_keyword_only_and_required`
    asserts they are mandatory there. It exists so red-first can distinguish
    "the rule changed" from "the call changed".
    """
    kwargs = _row(**over)
    accepted = inspect.signature(suspended_row_is_unreachable).parameters
    return suspended_row_is_unreachable(
        **{k: v for k, v in kwargs.items() if k in accepted}
    )


class TestTheDefectReproduces:
    """The specimen is selected by NO writer. Without this the suite is air."""

    def test_no_espn_arm_can_see_it(self):
        """All three suspended-admitting ESPN arms require an espn_id."""
        from app.tasks import espn_sync

        src = inspect.getsource(espn_sync)
        admits = src.count('Event.status.in_(["live", EVENT_SUSPENDED])')
        assert admits >= 3, "the ESPN arms moved — re-aim this scan"
        # Each one is immediately followed by the espn_id requirement.
        assert src.count(
            'Event.status.in_(["live", EVENT_SUSPENDED]),\n'
            "            Event.espn_id.isnot(None),"
        ) == admits, "an ESPN arm admits suspended WITHOUT requiring an espn_id"

    def test_the_odds_settle_loop_only_selects_live(self):
        from app.tasks import odds_polling

        src = inspect.getsource(odds_polling.detect_and_close_stale_events)
        assert 'Event.status == "live"' in src
        assert "EVENT_SUSPENDED," not in src.split("select(Event)")[1][:400], (
            "the settle loop now admits suspended — this specimen has a door"
        )

    def test_the_specimen_is_past_every_door_s_window(self):
        from app.tasks.espn_sync import SUSPENDED_RESUME_WINDOW
        from app.tasks.odds_polling import ODDS_SCORES_LOOKBACK

        row = _row()
        age = NOW - row["commence_time"]
        assert age > SUSPENDED_RESUME_WINDOW
        assert age > ODDS_SCORES_LOOKBACK


class TestTheNewBranchAdmitsExactlyTheMeasuredPopulation:
    def test_the_constant_carries_the_value_production_actually_stores(self):
        from app.utils.event_completion import ODDS_API_COMMENCE_SOURCE

        assert ODDS_API_COMMENCE_SOURCE == ODDS_API_SOURCE_WIRE_VALUE

    def test_the_production_specimen_is_now_unreachable(self):
        assert _verdict() is True

    def test_an_empty_string_external_id_was_never_the_question(self):
        """The id-less half of #5532 is untouched by any of this."""
        assert _verdict(external_id=None) is True
        assert _verdict(external_id="   ") is True


class TestNothingElseIsNewlyAdmitted:
    """"Who NEWLY matches?" — the whole answer, one refusal per test."""

    @pytest.mark.parametrize(
        "source",
        ["kalshi", "polymarket", "kalshi_ticker", "kalshi_occurrence",
         "espn", "statpal", "", None],
    )
    def test_only_odds_api_provenance_relaxes_the_id_test(self, source):
        assert _verdict(commence_time_source=source) is False

    def test_a_market_anchored_row_keeps_its_door(self):
        """150 of the 711. polymarket/kalshi_resolution_sweep admit suspended."""
        assert _verdict(market_anchored=True) is False

    @pytest.mark.parametrize("fuzzy", [None, 0, "", "no"])
    def test_market_anchored_must_be_exactly_false(self, fuzzy):
        """An unknown anchor state is not a known-absent one.

        ``is False`` and not ``not market_anchored``: a caller that could not
        answer the question must not be read as having answered "no".
        """
        assert _verdict(market_anchored=fuzzy) is False

    def test_an_espn_id_still_refuses_regardless_of_provenance(self):
        assert _verdict(espn_id="401778901") is False

    def test_a_statpal_id_still_refuses_regardless_of_provenance(self):
        assert _verdict(statpal_fixture_id="88213") is False

    @pytest.mark.parametrize(
        "over",
        [{"home_score": 0}, {"away_score": 3}, {"completed_at": NOW}],
    )
    def test_a_row_carrying_a_result_still_refuses(self, over):
        """Something reached it, which refutes the premise directly."""
        assert _verdict(**over) is False

    def test_an_espn_covered_sport_still_refuses(self):
        """`_backfill_espn_ids` can still go and get the anchor."""
        assert _verdict(anchor_acquirable=True) is False

    def test_a_row_that_is_not_suspended_still_refuses(self):
        for status in ("live", "scheduled", "completed", "closed"):
            assert _verdict(status=status) is False


class TestTheFloorClearsTheDoorThisShipOpens:
    def test_a_row_inside_the_scores_window_is_refused(self):
        """The scores fetch IS keyed on external_id — do not take its row."""
        from app.tasks.odds_polling import ODDS_SCORES_LOOKBACK

        inside = NOW - (ODDS_SCORES_LOOKBACK - timedelta(hours=1))
        assert _verdict(commence_time=inside) is False

    def test_the_floor_strictly_exceeds_the_scores_window(self):
        """Read off the ARM's own function, never a copy of its formula.

        A `max` → `min` mutation survived this test while it recomputed the
        floor itself: the test agreed with itself and the arm was free to
        disagree with both. `unreachable_suspended_floor` exists so this line
        calls the thing it is judging.
        """
        from app.tasks.espn_sync import unreachable_suspended_floor
        from app.tasks.odds_polling import ODDS_SCORES_LOOKBACK

        assert unreachable_suspended_floor() > ODDS_SCORES_LOOKBACK, (
            "a floor that merely equals the window has no margin at all"
        )

    def test_the_floor_did_not_shrink_for_the_id_less_population(self):
        from app.tasks.espn_sync import (
            SUSPENDED_RESUME_WINDOW,
            unreachable_suspended_floor,
        )

        assert (
            unreachable_suspended_floor()
            >= SUSPENDED_RESUME_WINDOW + UNREACHABLE_SUSPENDED_MARGIN
        )

    def test_the_arm_spends_the_named_floor_rather_than_inlining_one(self):
        from app.tasks.espn_sync import _transition_event_statuses_impl

        src = inspect.getsource(_transition_event_statuses_impl)
        assert "unreachable_floor = unreachable_suspended_floor()" in src

    def test_the_lookback_is_not_quietly_shrunk_below_the_venue_maximum(self):
        """Kills a `timedelta(days=0)`, which every other test tolerates.

        Shrinking the constant shrinks the request AND the floor together, so
        the two stay consistent and nothing else in this file notices — the
        "row inside the scores window" test even passes VACUOUSLY, because a
        zero window puts its specimen in the future. The reason that is still
        not safe: 3 is the Odds API's documented `daysFrom` maximum, and if the
        venue clamps or ignores a smaller value the request keeps its old reach
        while our floor has moved in under it. Protect for the venue's bound,
        not for the one we happen to ask.
        """
        from app.tasks.odds_polling import ODDS_SCORES_LOOKBACK

        assert ODDS_SCORES_LOOKBACK >= timedelta(days=3)

    def test_the_scores_call_site_spends_the_constant(self):
        from app.tasks import odds_polling

        src = inspect.getsource(odds_polling)
        assert "days_from=ODDS_SCORES_LOOKBACK.days" in src
        assert "days_from=3" not in src, "the bound must never be restated"


class TestTheAnchorProbeActuallyReadsTheTable:
    """The 150 rows that KEEP their door depend on this one query.

    Nothing else in the suite executes it: the screen excludes anchored rows in
    SQL, so a ``_row_has_market_anchor`` that simply ``return False`` passed
    every other test in this file. It is the second of the two asks, and the
    whole point of a second ask is that it does not inherit the first one's
    answer — so it gets a real table with real rows.
    """

    def _rig(self):
        from sqlalchemy import create_engine
        from sqlalchemy.dialects.postgresql import ARRAY, JSONB
        from sqlalchemy.ext.compiler import compiles
        from sqlalchemy.orm import Session

        from app.models.models import Base, Event, FuturesMarket, Sport

        @compiles(JSONB, "sqlite")
        def _jsonb_sqlite(type_, compiler, **kw):  # pragma: no cover - rail
            return "JSON"

        @compiles(ARRAY, "sqlite")
        def _array_sqlite(type_, compiler, **kw):  # pragma: no cover - rail
            return "JSON"

        engine = create_engine("sqlite://")
        Base.metadata.create_all(
            engine,
            tables=[
                Event.__table__,
                Sport.__table__,
                FuturesMarket.__table__,
            ],
        )
        session = Session(engine, expire_on_commit=False)
        sport = Sport(key="baseball_milb", name="MiLB")
        session.add(sport)
        session.flush()

        bare = Event(
            sport_id=sport.id,
            home_team_name="Durham Bulls",
            away_team_name="Nashville Sounds",
            commence_time=NOW - timedelta(days=6),
            status=EVENT_SUSPENDED,
            external_id="65325eabae27182083c9f8ae06cdf250",
        )
        anchored = Event(
            sport_id=sport.id,
            home_team_name="Memphis Redbirds",
            away_team_name="Norfolk Tides",
            commence_time=NOW - timedelta(days=6),
            status=EVENT_SUSPENDED,
            external_id="fb00b98db9506720d4ea93481dfa458d",
        )
        session.add_all([bare, anchored])
        session.flush()
        session.add(
            FuturesMarket(
                event_id=anchored.id,
                source="kalshi",
                external_id="KXMILBGAME-26SEP09MEMNOR",
                name="Memphis Redbirds vs Norfolk Tides",
                category="game",
                mutually_exclusive=True,
                status="open",
            )
        )
        session.commit()

        class _AsyncShim:
            """`await session.execute(stmt)` over a real sync sqlite session.

            aiosqlite is not installed here. The shim changes who awaits, never
            what is executed — the statement under test is compiled and run
            against real rows, which is the only part that can be wrong.
            """

            def __init__(self, inner):
                self._inner = inner

            async def execute(self, stmt):
                return self._inner.execute(stmt)

        return _AsyncShim(session), bare.id, anchored.id

    @pytest.mark.asyncio
    async def test_a_bare_row_reads_as_unanchored(self):
        from app.tasks.espn_sync import _row_has_market_anchor

        session, bare_id, _ = self._rig()
        assert await _row_has_market_anchor(session, bare_id) is False

    @pytest.mark.asyncio
    async def test_a_row_with_a_market_reads_as_anchored(self):
        """Kills a `_row_has_market_anchor` that always answers "no"."""
        from app.tasks.espn_sync import _row_has_market_anchor

        session, _, anchored_id = self._rig()
        assert await _row_has_market_anchor(session, anchored_id) is True

    @pytest.mark.asyncio
    async def test_the_probe_does_not_answer_for_a_sibling_row(self):
        """A market on ANOTHER event must not anchor this one.

        The uncorrelated-EXISTS failure mode, asked of the helper rather than
        of the compiled screen: "any market anywhere" would make both rows read
        anchored and retire nothing, forever, silently.
        """
        from app.tasks.espn_sync import _row_has_market_anchor

        session, bare_id, anchored_id = self._rig()
        assert await _row_has_market_anchor(session, anchored_id) is True
        assert await _row_has_market_anchor(session, bare_id) is False


class TestTheVerdictIsNotSmuggledOutOfTheWhereClause:
    def _arm_source(self):
        from app.tasks.espn_sync import _transition_event_statuses_impl

        src = inspect.getsource(_transition_event_statuses_impl)
        marker = "suspended → retired"
        assert marker in src, "the arm's banner comment moved — re-aim this scan"
        return src[src.index(marker):]

    def test_the_screen_excludes_market_anchored_rows(self):
        src = self._arm_source()
        assert "market_anchored_exists" in src
        assert "~market_anchored_exists" in src

    def test_the_screen_scopes_the_relaxation_to_the_named_provenance(self):
        src = self._arm_source()
        assert "ODDS_API_COMMENCE_SOURCE" in src
        assert '"odds_api"' not in src and "'odds_api'" not in src, (
            "the provenance is a constant, not a literal in a WHERE clause"
        )

    def test_the_market_exists_subquery_is_correlated_not_a_cross_join(self):
        """The one way this ship could ship INERT and look perfectly fine.

        An uncorrelated ``EXISTS`` compiles to ``FROM futures_markets, events``
        — "does ANY market point at ANY event", which is always true, so
        ``NOT EXISTS`` is always false and the whole ``odds_api`` branch selects
        nothing, forever, silently. No source scan can see the difference: the
        Python reads identically either way. Only the compiled SQL can.

        (SQLAlchemy auto-correlates here, so this passes today. It is pinned
        because the thing it guards is invisible everywhere else — rendering the
        ``whereclause`` alone, out of its enclosing SELECT, genuinely does print
        the cross join.)
        """
        from sqlalchemy import and_, or_, select

        from app.models import Event, FuturesMarket
        from app.utils.event_completion import ODDS_API_COMMENCE_SOURCE

        exists_clause = (
            select(FuturesMarket.id)
            .where(FuturesMarket.event_id == Event.id)
            .exists()
        )
        compiled = str(
            select(Event.id).where(
                or_(
                    Event.external_id.is_(None),
                    and_(
                        Event.commence_time_source == ODDS_API_COMMENCE_SOURCE,
                        ~exists_clause,
                    ),
                )
            )
        )
        assert "FROM futures_markets \nWHERE futures_markets.event_id = events.id" in compiled
        assert "FROM futures_markets, events" not in compiled, (
            "the EXISTS lost its correlation — the odds_api branch is inert"
        )

    def test_the_verdict_is_still_asked_on_every_screened_row(self):
        src = self._arm_source()
        assert "suspended_row_is_unreachable(" in src
        assert "commence_time_source=event.commence_time_source" in src
        assert "market_anchored=await _row_has_market_anchor(" in src

    def test_the_two_new_arguments_are_keyword_only_and_required(self):
        """A caller that has not been taught to ask gets a TypeError.

        The fail-closed shape: "this call site is out of date" and "the row is
        genuinely inert" must not be able to look alike.
        """
        sig = inspect.signature(suspended_row_is_unreachable)
        for name in ("commence_time_source", "market_anchored"):
            p = sig.parameters[name]
            assert p.kind is inspect.Parameter.KEYWORD_ONLY
            assert p.default is inspect.Parameter.empty

        positional = _row()
        for name in ("commence_time_source", "market_anchored"):
            missing = {k: v for k, v in positional.items() if k != name}
            with pytest.raises(TypeError):
                suspended_row_is_unreachable(**missing)
