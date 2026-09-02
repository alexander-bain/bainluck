"""CERT-767 — the 15-minute writer stops asking only the lowest-id row.

═══ THE SPECIMEN ═══

CERT-759 withheld a token for a repair that parsed tour-last Polymarket names
correctly, on the ground that the writer never got as far as the parse. CERT-767
withheld the next one for the same reason one layer down: `live_blend`'s grouped
decision was repaired and PROVED on a 36-group replay, but that helper is not the
only writer of `win_probability_sources`. `_match_prediction_markets` — the
15-minute matcher, and the ONLY writer that reaches a scheduled event — kept its
own inline copy that picked the group's primary market and parsed that row alone.

    exact-head reproduction, empty parent id 1 + match-winner child id 9
      repaired shared helper   ->  speaker 9, home 0.62
      Phase 2's inline writer  ->  primary 1, matchup None, nothing written

The shape is not hypothetical. Production, 2026-09-02, the twelve US Open events
whose Polymarket source was blank — eleven of them lead with a ZERO-OUTCOME
`- Exact Score` book at the lowest id, with the match winner minted next:

    event 15299603  59959738  out=0  Brandon Nakashima vs. Alex Michelsen - Exact Score
                    59959774  out=2  US Open ATP: Brandon Nakashima vs Alex Michelsen
    event 15300837  60026245  out=0  Taylor Fritz vs. Mattia Bellucci - Exact Score
                    60026295  out=2  US Open ATP: Taylor Fritz vs Mattia Bellucci

The twelfth, event 15298238, is the OTHER half of the CERT-767 finding: its
lowest-id row IS the readable winner (Yes @ 0.165), and it is blank only because
it completed on 08-31, outside Phase 2's 24-hour completed window and outside the
live poll entirely. Nothing that ran would ever ask it again. That is what
`_phase2b_completed_catchup` exists for.

═══ WHAT THESE TESTS PIN ═══

1. THE COMPOSED WRITER (the cert's named requirement): an already-linked
   completed event with a lower-id empty row and a valid winner child persists
   the Polymarket source key AND the CHILD's market id — driven through the real
   persistence function against a fake session, not asserted from source text.
2. NO SECOND COPY: the Phase 2 loop must not carry its own matchup parse or
   moneyline resolution. That is the #1951 class — a duplicated decider does not
   throw when it drifts, it just quietly disagrees.
3. THE CATCH-UP'S THREE SAFETY PROPERTIES: holes only, no snapshot, bounded.
4. ADMISSION, unchanged by the widening: the group still refuses to speak when
   no row can, and neither a Polymarket derivative nor a Kalshi prop can be
   fallen back onto.

ONE OF THESE IS A BOTH-ARM CONTROL AND THE REST ARE NOT, which is worth saying
out loud. `test_both_kalshi_unlink_arms_are_still_inline` runs and passes on
master too — it guards that extracting the READING did not carry a LINK arm out
of `_match_prediction_markets`, where q439 and q504b scan for those deciders.
Every other test here drives a function master does not have, so master cannot
green them; their strength comes from the mutation record in the commit message,
not from an arm crossing. The arm-crossing version of "widening cannot move an
existing answer" lives one layer down, in
`test_live_blend_parent_veto_cert759.py`.

The new symbols are imported INSIDE each test, deliberately: on master they do
not exist, and a module-level import would turn the red arm into a collection
error for the whole file instead of a failure per behaviour.
"""

import ast
import inspect
import textwrap
from datetime import datetime, timedelta, timezone

import pytest

from app.models.models import Event


NOW = datetime(2026, 9, 2, 20, 0, tzinfo=timezone.utc)


# =============================================================================
# Fakes — only the attributes the writer actually reads
# =============================================================================


class _Outcome:
    def __init__(self, market_id, rank, name, probability):
        self.market_id = market_id
        self.rank = rank
        self.name = name
        self.current_probability = probability
        self.current_yes_bid = None
        self.current_yes_ask = None


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
    """Serves the four SELECTs the group writer issues; records the UPDATEs.

    Dispatch is on the rendered table name, most specific first — `events` is
    last because every other statement mentions an `event_id` column.
    """

    def __init__(self, outcomes, event_row):
        self._outcomes = outcomes
        self._event_row = event_row
        self.updates = []
        self.added = []
        self.commits = 0
        self.statements = []

    async def get(self, model, pk):
        assert model is Event
        return self._event_row if pk == self._event_row.id else None

    async def execute(self, stmt):
        text = str(stmt)
        self.statements.append(text)
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

    def stamped_sources(self):
        """The `win_probability_sources` dict the recorded UPDATE would write."""
        for stmt in self.updates:
            values = dict(stmt._values)
            col = Event.__table__.c.win_probability_sources
            if col in values:
                return values[col].value
        return None


def _ref(market_id, name, *, source="polymarket", external_id=None, event_id=15299603):
    from app.tasks.prediction_market_matching import _LinkedMarketRef

    return _LinkedMarketRef(
        market_id=market_id,
        source=source,
        external_id=external_id,
        name=name,
        event_id=event_id,
        event_commence_time=NOW - timedelta(hours=30),
        home_team_name="Brandon Nakashima",
        away_team_name="Alex Michelsen",
    )


def _cert759_group():
    """The exact shape CERT-759 reproduced: empty parent id 1, winner child id 9."""
    return [
        _ref(1, "Brandon Nakashima vs. Alex Michelsen - Exact Score"),
        _ref(9, "US Open ATP: Brandon Nakashima vs Alex Michelsen"),
    ]


def _cert759_outcomes():
    """Only the child has outcomes — the parent is the row that could not speak."""
    return [
        _Outcome(9, 1, "Brandon Nakashima", 0.62),
        _Outcome(9, 2, "Alex Michelsen", 0.38),
    ]


# =============================================================================
# 1. The composed writer guard — the cert's named requirement
# =============================================================================


@pytest.mark.asyncio
class TestTheComposedWriterPersistsTheChild:
    async def test_an_empty_lower_id_row_no_longer_vetoes_the_persisted_source(self):
        """RED ON MASTER: the writer picks market 1, reads None, writes nothing."""
        from app.tasks.prediction_market_matching import _phase2_persist_group_reading

        session = _FakeSession(_cert759_outcomes(), _EventRow(15299603))
        stats = {"snapshots_written": 0, "snapshots_deduped": 0, "errors": []}

        spoke = await _phase2_persist_group_reading(
            session, _cert759_group(), stats,
        )

        assert spoke == 9, "the match-winner child must be the market that speaks"
        stamped = session.stamped_sources()
        assert stamped is not None, "no win_probability_sources UPDATE was recorded"
        assert "polymarket" in stamped, (
            "the Polymarket source key was not persisted — the empty parent still "
            "vetoes its group in the writer that stamps every scheduled event"
        )
        assert session.commits == 1

    async def test_the_snapshot_audit_trail_names_the_child_not_the_primary(self):
        """`market_id` must be the row that spoke, or the audit trail lies."""
        from app.tasks.prediction_market_matching import _phase2_persist_group_reading

        session = _FakeSession(_cert759_outcomes(), _EventRow(15299603))
        stats = {"snapshots_written": 0, "snapshots_deduped": 0, "errors": []}

        await _phase2_persist_group_reading(session, _cert759_group(), stats)

        assert len(session.added) == 1, "expected exactly one new win_prob_snapshot"
        game_state = session.added[0].game_state
        assert game_state["market_id"] == 9
        assert game_state["market_name"].startswith("US Open ATP:")
        assert stats["snapshots_written"] == 1

    async def test_the_persisted_probability_is_the_childs_price(self):
        from app.tasks.prediction_market_matching import _phase2_persist_group_reading

        session = _FakeSession(_cert759_outcomes(), _EventRow(15299603))
        stats = {"snapshots_written": 0, "snapshots_deduped": 0, "errors": []}

        await _phase2_persist_group_reading(session, _cert759_group(), stats)

        entry = session.stamped_sources()["polymarket"]
        value = entry["value"] if isinstance(entry, dict) else entry
        assert value == pytest.approx(0.62)

    async def test_a_group_whose_primary_already_speaks_is_unchanged(self):
        """WIDENING CANNOT MOVE AN ANSWER THAT ALREADY EXISTS.

        Not a both-arm control — this writer does not exist on master, so the
        arm-crossing version of this property lives in
        `test_live_blend_parent_veto_cert759.py` against the shared helper.
        Here it is pinned by mutation: pass the primary alone instead of the
        group and this stays green while the veto test reds, which is exactly
        how you tell a preference from a verdict.
        """
        from app.tasks.prediction_market_matching import _phase2_persist_group_reading

        group = [
            _ref(1, "US Open ATP: Brandon Nakashima vs Alex Michelsen"),
            _ref(9, "Brandon Nakashima vs. Alex Michelsen - Exact Score"),
        ]
        session = _FakeSession(
            [_Outcome(1, 1, "Brandon Nakashima", 0.71),
             _Outcome(1, 2, "Alex Michelsen", 0.29)],
            _EventRow(15299603),
        )
        stats = {"snapshots_written": 0, "snapshots_deduped": 0, "errors": []}

        spoke = await _phase2_persist_group_reading(session, group, stats)

        assert spoke == 1
        entry = session.stamped_sources()["polymarket"]
        value = entry["value"] if isinstance(entry, dict) else entry
        assert value == pytest.approx(0.71)

    async def test_a_group_where_nothing_can_speak_writes_nothing(self):
        """Falling through the group is not a licence to guess."""
        from app.tasks.prediction_market_matching import _phase2_persist_group_reading

        session = _FakeSession([], _EventRow(15299603))
        stats = {"snapshots_written": 0, "snapshots_deduped": 0, "errors": []}

        spoke = await _phase2_persist_group_reading(
            session, _cert759_group(), stats,
        )

        assert spoke is None
        assert session.updates == []
        assert session.commits == 0

    async def test_a_derivative_child_is_never_fallen_back_onto(self):
        """The reason the fallback is gated at all.

        `- Halftime Result` parses and its two outcomes resolve. If the fallback
        admitted it, a halftime price would be stamped as the match moneyline.
        """
        from app.tasks.prediction_market_matching import _phase2_persist_group_reading

        group = [
            _ref(1, "Brandon Nakashima vs. Alex Michelsen - Exact Score"),
            _ref(9, "Brandon Nakashima vs. Alex Michelsen - Halftime Result"),
        ]
        session = _FakeSession(
            [_Outcome(9, 1, "Brandon Nakashima", 0.55),
             _Outcome(9, 2, "Alex Michelsen", 0.45)],
            _EventRow(15299603),
        )
        stats = {"snapshots_written": 0, "snapshots_deduped": 0, "errors": []}

        assert await _phase2_persist_group_reading(session, group, stats) is None
        assert session.updates == []

    async def test_a_kalshi_prop_child_is_never_fallen_back_onto(self):
        """Widening the SEARCH never widens ADMISSION."""
        from app.tasks.prediction_market_matching import _phase2_persist_group_reading

        group = [
            _ref(1, "Empty parent", source="kalshi", external_id="KXNBAGAME-26FEB20BOSGSW"),
            _ref(9, "Celtics vs Warriors", source="kalshi",
                 external_id="KXNBASPREAD-26FEB20BOSGSW"),
        ]
        session = _FakeSession(
            [_Outcome(9, 1, "Boston Celtics", 0.6), _Outcome(9, 2, "Golden State Warriors", 0.4)],
            _EventRow(15299603),
        )
        stats = {"snapshots_written": 0, "snapshots_deduped": 0, "errors": []}

        assert await _phase2_persist_group_reading(session, group, stats) is None
        assert session.updates == []


# =============================================================================
# 2. No second copy of the decision inside the Phase 2 loop
# =============================================================================


def _calls_in(node):
    return {
        n.func.id if isinstance(n.func, ast.Name) else getattr(n.func, "attr", "")
        for n in ast.walk(node)
        if isinstance(n, ast.Call)
    }


class TestPhase2HasNoSecondCopyOfTheDecision:
    def _tree(self):
        from app.tasks.prediction_market_matching import _match_prediction_markets

        return ast.parse(
            textwrap.dedent(inspect.getsource(_match_prediction_markets))
        )

    def test_the_loop_no_longer_resolves_a_moneyline_itself(self):
        """RED ON MASTER: Phase 2 calls `find_moneyline_outcome` three times."""
        assert "find_moneyline_outcome" not in _calls_in(self._tree()), (
            "Phase 2 is resolving the moneyline itself again — that is the "
            "#1951 second-copy class the CERT-767 repair removed"
        )

    def test_the_loop_no_longer_parses_the_matchup_itself(self):
        """RED ON MASTER."""
        assert "extract_matchup_with_ticker_fallback" not in _calls_in(self._tree()), (
            "Phase 2 is parsing the matchup itself again; the shared helper's "
            "parse is the one that decides which row speaks"
        )

    def test_the_loop_routes_through_the_shared_group_writer(self):
        """RED ON MASTER: the symbol does not exist there."""
        assert "_phase2_persist_group_reading" in _calls_in(self._tree())

    def test_the_loop_hands_over_the_GROUP_and_not_the_primary_alone(self):
        """The mutation that survived the first battery, and the one that matters.

        Every behavioural test in this file drives
        `_phase2_persist_group_reading` directly, so all of them stay green if
        the call site quietly reverts to `[market]` — a fully repaired writer,
        handed one row, reproducing CERT-759 exactly. The wiring IS the ship, so
        the wiring gets its own assertion: the group the writer is asked about
        must come from `all_per_event_source`, the dict that holds every linked
        row of this (event, source).
        """
        from app.tasks.prediction_market_matching import _match_prediction_markets

        tree = ast.parse(
            textwrap.dedent(inspect.getsource(_match_prediction_markets))
        )
        calls = [
            n for n in ast.walk(tree)
            if isinstance(n, ast.Call)
            and getattr(n.func, "id", "") == "_phase2_persist_group_reading"
        ]
        assert len(calls) == 1, f"expected one Phase 2 hand-off, found {len(calls)}"
        group_arg = ast.dump(calls[0].args[1])
        assert "all_per_event_source" in group_arg, (
            "Phase 2 is handing the group writer something other than the whole "
            f"(event, source) group — the lowest-id veto is back. Got: {group_arg[:160]}"
        )

    def test_the_group_writer_calls_the_shared_blend_decision(self):
        from app.tasks.prediction_market_matching import _phase2_persist_group_reading

        src = inspect.getsource(_phase2_persist_group_reading)
        assert "_compute_source_home_probability" in _calls_in(ast.parse(textwrap.dedent(src))), (
            "the group writer must ask `live_blend.compute_source_home_probability`, "
            "not a local re-derivation of it"
        )

    def test_both_kalshi_unlink_arms_are_still_inline(self):
        """CONTROL — green in BOTH arms.

        q439 and q504b scan `_match_prediction_markets` itself for these two
        deciders. Extracting the READING must not have carried a LINK arm out
        with it.
        """
        calls = _calls_in(self._tree())
        assert "_ticker_date_conflicts_with_event" in calls
        assert "is_kalshi_match_segment_ticker" in calls
        assert "is_combat_fight_ticker" in calls


# =============================================================================
# 3. The catch-up's three safety properties
# =============================================================================


class _CatchupSession:
    """Captures the candidate SQL and answers with a scripted candidate set."""

    def __init__(self, pages=None):
        self.texts = []
        self.params = []
        self._pages = list(pages or [])

    async def execute(self, stmt, params=None):
        self.texts.append(str(stmt))
        self.params.append(params)
        if self._pages:
            return _Result(self._pages.pop(0))
        return _Result([], scalar=None)

    async def commit(self):  # pragma: no cover — nothing to commit on an empty set
        pass

    async def rollback(self):  # pragma: no cover
        pass


class _FakeRedis:
    """The three verbs the cursor uses, and a record of what it did."""

    def __init__(self, initial=None, fail=False):
        self.store = dict(initial or {})
        self.deleted = []
        self.fail = fail

    def get(self, key):
        if self.fail:
            raise RuntimeError("redis down")
        return self.store.get(key)

    def set(self, key, value):
        self.store[key] = value

    def delete(self, key):
        self.deleted.append(key)
        self.store.pop(key, None)


@pytest.fixture
def fake_redis(monkeypatch):
    """Patch the cursor's Redis at its import site inside the catch-up."""
    from app.tasks import redis_state

    holder = _FakeRedis()
    monkeypatch.setattr(redis_state, "get_redis_client", lambda *a, **k: holder)
    return holder


@pytest.mark.asyncio
class TestTheCompletedCatchupIsSafeAndBounded:
    async def test_it_only_selects_events_missing_the_source_key(self, fake_redis):
        """HOLES ONLY. It may add a reading; it may never move an existing one."""
        from app.tasks.prediction_market_matching import _phase2b_completed_catchup

        session = _CatchupSession()
        stats = {"funnel": {}, "errors": []}
        await _phase2b_completed_catchup(session, NOW, stats, lambda: 600.0)

        assert session.texts, "the catch-up issued no candidate query at all"
        for sql in session.texts:
            assert "NOT jsonb_exists" in sql, (
                "the candidate query does not demand the source key be ABSENT, so "
                "the catch-up could overwrite a number the user is already shown"
            )

    async def test_it_is_bounded_at_both_ends_and_ordered_oldest_first(self, fake_redis):
        """gotcha #41 — a sweep over an ageing population needs a floor AND a cap."""
        from app.tasks.prediction_market_matching import _phase2b_completed_catchup

        session = _CatchupSession()
        stats = {"funnel": {}, "errors": []}
        await _phase2b_completed_catchup(session, NOW, stats, lambda: 600.0)

        for sql in session.texts:
            assert "LIMIT" in sql.upper()
            assert "commence_time >=" in sql, "no age floor — the sweep walks back forever"
            assert "ORDER BY e.commence_time ASC" in sql

    async def test_it_only_looks_at_events_already_past_phase_2s_window(self, fake_redis):
        from app.tasks.prediction_market_matching import _phase2b_completed_catchup

        session = _CatchupSession()
        stats = {"funnel": {}, "errors": []}
        await _phase2b_completed_catchup(session, NOW, stats, lambda: 600.0)

        for sql in session.texts:
            assert "e.commence_time < :recent" in sql
            assert "'completed', 'closed'" in sql

    async def test_an_exhausted_budget_stops_it_before_the_first_query(self, fake_redis):
        """It shares a 15-minute task with a link pass and a backfill."""
        from app.tasks.prediction_market_matching import _phase2b_completed_catchup

        session = _CatchupSession()
        stats = {"funnel": {}, "errors": []}
        await _phase2b_completed_catchup(session, NOW, stats, lambda: 10.0)

        assert session.texts == []
        assert stats["funnel"]["phase2b_budget_stopped"] is True

    async def test_it_writes_the_blend_key_but_never_a_snapshot(self):
        """0t-1 stays fixed: a settled event's chart gains no new point."""
        from app.tasks.prediction_market_matching import _phase2_persist_group_reading

        session = _FakeSession(_cert759_outcomes(), _EventRow(15298238))
        stats = {"snapshots_written": 0, "snapshots_deduped": 0, "errors": []}

        spoke = await _phase2_persist_group_reading(
            session, _cert759_group(), stats, write_snapshot=False,
        )

        assert spoke == 9
        assert "polymarket" in session.stamped_sources()
        assert session.added == [], "the catch-up appended a win_prob_snapshot"
        assert stats["snapshots_written"] == 0
        assert not any("win_prob_snapshots" in s for s in session.statements)

    async def test_the_catchup_passes_write_snapshot_false(self):
        """The property above is only real if the catch-up actually asks for it."""
        from app.tasks.prediction_market_matching import _phase2b_completed_catchup

        tree = ast.parse(
            textwrap.dedent(inspect.getsource(_phase2b_completed_catchup))
        )
        calls = [
            n for n in ast.walk(tree)
            if isinstance(n, ast.Call)
            and getattr(n.func, "id", "") == "_phase2_persist_group_reading"
        ]
        assert len(calls) == 1
        kwargs = {k.arg: k.value for k in calls[0].keywords}
        assert "write_snapshot" in kwargs
        assert kwargs["write_snapshot"].value is False

    async def test_it_never_unlinks(self):
        """A settled, low-signal population gets no power over the linkage table."""
        from app.tasks.prediction_market_matching import _phase2b_completed_catchup

        tree = ast.parse(
            textwrap.dedent(inspect.getsource(_phase2b_completed_catchup))
        )
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "update":
                raise AssertionError("the catch-up issues an UPDATE of its own")
        src = inspect.getsource(_phase2b_completed_catchup)
        assert "event_id=None" not in src


@pytest.mark.asyncio
class TestTheCatchupActuallyAdvances:
    """The sharp edge of "holes only": a REFUSED row never leaves the set.

    Without a cursor, `ORDER BY commence_time ASC LIMIT 75` hands the same page
    back every fifteen minutes forever. Measured on production 2026-09-02, the
    first page of this query is 75 Brazilian lower-division rows whose own
    `away_team_name` ends `- Halftime Result` — none of which will ever resolve,
    and behind which US Open 15298238 sits unreachable. A sweep that cannot
    advance is a sweep that reports work and does none.
    """

    def _page(self, *stamps):
        return [
            (9000 + i, "Home", "Away", datetime.fromisoformat(s))
            for i, s in enumerate(stamps)
        ]

    async def test_the_cursor_advances_past_the_page_it_just_read(self, fake_redis):
        from app.tasks.prediction_market_matching import (
            _PHASE2B_CURSOR_KEY_PREFIX,
            _phase2b_completed_catchup,
        )

        session = _CatchupSession(pages=[
            self._page("2026-08-28T10:00:00+00:00", "2026-08-29T11:00:00+00:00"),
            [],  # the markets lookup for that page
        ])
        stats = {"funnel": {}, "errors": []}
        await _phase2b_completed_catchup(session, NOW, stats, lambda: 600.0)

        stored = fake_redis.store[f"{_PHASE2B_CURSOR_KEY_PREFIX}kalshi"]
        assert stored.startswith("2026-08-29T11:00"), (
            f"the cursor did not advance past the page it read (got {stored})"
        )

    async def test_a_stored_cursor_is_used_as_the_page_start(self, fake_redis):
        from app.tasks.prediction_market_matching import (
            _PHASE2B_CURSOR_KEY_PREFIX,
            _phase2b_completed_catchup,
        )

        fake_redis.store[f"{_PHASE2B_CURSOR_KEY_PREFIX}kalshi"] = (
            "2026-08-30T00:00:00+00:00"
        )
        session = _CatchupSession()
        stats = {"funnel": {}, "errors": []}
        await _phase2b_completed_catchup(session, NOW, stats, lambda: 600.0)

        kalshi_params = session.params[0]
        assert kalshi_params["cursor"] == datetime(2026, 8, 30, tzinfo=timezone.utc)

    async def test_a_cursor_older_than_the_floor_is_clamped_to_the_floor(self, fake_redis):
        """A cursor left by a longer floor must not re-walk retired ground."""
        from app.tasks.prediction_market_matching import (
            _PHASE2B_AGE_FLOOR_DAYS,
            _PHASE2B_CURSOR_KEY_PREFIX,
            _phase2b_completed_catchup,
        )

        fake_redis.store[f"{_PHASE2B_CURSOR_KEY_PREFIX}kalshi"] = (
            "2020-01-01T00:00:00+00:00"
        )
        session = _CatchupSession()
        stats = {"funnel": {}, "errors": []}
        await _phase2b_completed_catchup(session, NOW, stats, lambda: 600.0)

        expected_floor = NOW - timedelta(days=_PHASE2B_AGE_FLOOR_DAYS)
        assert session.params[0]["cursor"] == expected_floor

    async def test_a_dry_scan_wraps_the_cursor_back_to_the_floor(self, fake_redis):
        """Otherwise the sweep parks at the end of the population and stays there."""
        from app.tasks.prediction_market_matching import (
            _PHASE2B_CURSOR_KEY_PREFIX,
            _phase2b_completed_catchup,
        )

        for source in ("kalshi", "polymarket"):
            fake_redis.store[f"{_PHASE2B_CURSOR_KEY_PREFIX}{source}"] = (
                "2026-09-01T00:00:00+00:00"
            )
        session = _CatchupSession()  # every page empty
        stats = {"funnel": {}, "errors": []}
        await _phase2b_completed_catchup(session, NOW, stats, lambda: 600.0)

        assert stats["funnel"]["phase2b_wrapped"] == 2
        assert fake_redis.store == {}, "the dry scan left a cursor parked at the end"

    async def test_no_cursor_means_it_declines_rather_than_pinning(self, monkeypatch):
        """gotcha #53 — the zero-yield case is recorded, not silent."""
        from app.tasks import redis_state
        from app.tasks.prediction_market_matching import _phase2b_completed_catchup

        monkeypatch.setattr(
            redis_state, "get_redis_client",
            lambda *a, **k: (_ for _ in ()).throw(RuntimeError("redis down")),
        )
        session = _CatchupSession()
        stats = {"funnel": {}, "errors": []}

        assert await _phase2b_completed_catchup(
            session, NOW, stats, lambda: 600.0,
        ) == 0
        assert session.texts == [], "it swept without a cursor and will pin"
        assert "phase2b_cursor_unavailable" in stats["funnel"]

    async def test_the_page_query_is_cursor_bounded(self, fake_redis):
        from app.tasks.prediction_market_matching import _phase2b_completed_catchup

        session = _CatchupSession()
        stats = {"funnel": {}, "errors": []}
        await _phase2b_completed_catchup(session, NOW, stats, lambda: 600.0)

        for sql in session.texts:
            assert "e.commence_time > :cursor" in sql


class TestTheCatchupIsWiredIntoTheTask:
    def test_the_task_runs_it(self):
        """RED ON MASTER — an unwired repair heals nothing."""
        from app.tasks.prediction_market_matching import _match_prediction_markets

        tree = ast.parse(
            textwrap.dedent(inspect.getsource(_match_prediction_markets))
        )
        assert "_phase2b_completed_catchup" in _calls_in(tree)

    def test_the_bounds_are_named_constants(self):
        from app.tasks import prediction_market_matching as pmm

        assert pmm._PHASE2B_AGE_FLOOR_DAYS > 0
        assert 0 < pmm._PHASE2B_EVENTS_PER_SOURCE <= 500
