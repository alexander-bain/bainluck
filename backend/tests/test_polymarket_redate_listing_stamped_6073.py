"""#6073, the third half: re-date the fixtures ALREADY minted from the listing stamp.

The other two halves are PREVENTION and only reach a mint. This one reaches the
standing population, and `tasks/polymarket.py`'s block above
`REDATE_LISTING_STAMPED_SQL` carries the production census these tests are built
from (2026-09-14, the whole band):

    band (commence_time_source='polymarket', live|suspended, still linked)   827
      venue start LATER than ours                                     820 (100%)
      venue start EARLIER than ours                                     0
      venue start still in the FUTURE                                 566
      of those 566: carrying a score / period / clock / completed_at    0 each
    groups linking to more than one event                            21 of 895
    groups carrying two different venue_game_start values              0 of 895

Two things are asserted here that a census cannot assert: that each refusal is
REAL (drive the predicate at it), and that the function WRITES what the ship
claims (drive it with a recording session and read the statements back). A rail
that selects correctly and writes the wrong column reads identical from a count.
"""

import ast
import inspect
import re
import textwrap
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.tasks import polymarket as poly
from app.tasks.polymarket import (
    REDATE_LISTING_STAMPED_SQL,
    redate_polymarket_listing_stamped_events,
    redate_target,
)
from app.utils.event_completion import (
    POLYMARKET_VENUE_COMMENCE_SOURCE,
    commence_time_is_a_reported_start,
)


NOW = datetime(2026, 9, 14, 6, 0, tzinfo=timezone.utc)


def _utc(*args):
    return datetime(*args, tzinfo=timezone.utc)


# ── The four production specimens of #6073 ───────────────────────────────────
#
# IMPORTED, never re-typed. The ingest half's suite already records these as read
# from the venue (notice 26) and they are the same four rows; two suites in one
# repo quoting different production readings for event 15312412 is exactly the
# drift that makes a later reader trust neither. One definition, so a correction
# to it reaches both halves at once.
#
# Shape: (event_id, our listing stamp, the venue's own start, skew hours). All
# four are ITF tennis; all four rendered "No result reported" for a match nobody
# had played.
from tests.test_polymarket_child_venue_stamp_6073 import SPECIMENS  # noqa: E402


class TestTheDateMoves:
    """The venue's instant replaces the listing stamp, forward only."""

    @pytest.mark.parametrize("event_id,listed,venue,skew", SPECIMENS)
    def test_each_specimen_takes_the_venue_instant(self, event_id, listed, venue, skew):
        decision = redate_target(
            venue_game_start=venue.isoformat(), event_commence=listed, now=NOW,
        )
        assert decision is not None, f"{event_id} was refused"
        target, _status = decision
        assert target == venue

    @pytest.mark.parametrize("event_id,listed,venue,skew", SPECIMENS)
    def test_the_measured_skew_is_what_the_move_closes(
        self, event_id, listed, venue, skew
    ):
        # Guards the specimens themselves: if a later edit mistypes one of these
        # instants, the recorded skew stops matching and this fails rather than
        # silently testing a fixture that never existed.
        measured = (venue - listed).total_seconds() / 3600
        assert round(measured, 1) == skew

    def test_a_backward_move_is_refused(self):
        # Measured 0/820 today. It is refused because moving a start BACKWARD can
        # only make a match that has not happened read as one that has — #6073's
        # own defect, arriving from the other side.
        assert redate_target(
            venue_game_start=_utc(2026, 9, 14, 6, 0).isoformat(),
            event_commence=_utc(2026, 9, 14, 13, 0),
            now=NOW,
        ) is None

    def test_agreement_is_not_a_write(self):
        instant = _utc(2026, 9, 14, 13, 0)
        assert redate_target(
            venue_game_start=instant.isoformat(), event_commence=instant, now=NOW,
        ) is None

    def test_a_naive_column_does_not_raise_and_is_read_as_utc(self):
        # The driver can hand back a naive column; the arithmetic must not blow up
        # on it, and it must not be read as local time.
        decision = redate_target(
            venue_game_start="2026-09-14T13:00:00",
            event_commence=datetime(2026, 9, 13, 19, 12),
            now=NOW,
        )
        assert decision is not None
        assert decision[0] == _utc(2026, 9, 14, 13, 0)

    @pytest.mark.parametrize("bad", [None, "", "not-a-timestamp", "2026-13-45"])
    def test_an_unusable_stamp_writes_nothing(self, bad):
        assert redate_target(
            venue_game_start=bad,
            event_commence=_utc(2026, 9, 13, 19, 12),
            now=NOW,
        ) is None

    def test_a_z_suffixed_stamp_parses(self):
        # What `sub_market_metadata` and the parent row both write.
        decision = redate_target(
            venue_game_start="2026-09-14T13:00:00Z",
            event_commence=_utc(2026, 9, 13, 19, 12),
            now=NOW,
        )
        assert decision is not None
        assert decision[0] == _utc(2026, 9, 14, 13, 0)


class TestEvidenceOfPlayRefusesTheRow:
    """0 of 566 carry any of these today. The guard is for the day one does."""

    @pytest.mark.parametrize(
        "field,value",
        [
            ("home_score", 0),
            ("home_score", 3),
            ("away_score", 0),
            ("away_score", 2),
            ("period", 1),
            ("game_clock", "12:00"),
        ],
    )
    def test_any_reported_play_signal_refuses(self, field, value):
        kwargs = {
            "venue_game_start": _utc(2026, 9, 14, 13, 0).isoformat(),
            "event_commence": _utc(2026, 9, 13, 19, 12),
            "now": NOW,
            field: value,
        }
        assert redate_target(**kwargs) is None

    def test_a_zero_score_is_evidence_too(self):
        # 0-0 is a REPORTED score, not an absent one: something watched this game
        # and said nobody had scored. The measured population carries NULL, not 0.
        assert redate_target(
            venue_game_start=_utc(2026, 9, 14, 13, 0).isoformat(),
            event_commence=_utc(2026, 9, 13, 19, 12),
            now=NOW,
            home_score=0,
            away_score=0,
        ) is None

    def test_with_no_signals_at_all_the_row_moves(self):
        # The complement of the six above — proves they are refusing on the signal
        # and not on something the fixture shares with them.
        assert redate_target(
            venue_game_start=_utc(2026, 9, 14, 13, 0).isoformat(),
            event_commence=_utc(2026, 9, 13, 19, 12),
            now=NOW,
            home_score=None,
            away_score=None,
            period=None,
            game_clock=None,
        ) is not None


class TestGotcha46IsNeverInverted:
    """`completed_at >= commence_time` is an invariant; violating it means a
    cross-event data merge. Refused, never clamped."""

    def test_a_target_past_completed_at_is_refused(self):
        assert redate_target(
            venue_game_start=_utc(2026, 9, 14, 13, 0).isoformat(),
            event_commence=_utc(2026, 9, 13, 19, 12),
            now=NOW,
            completed_at=_utc(2026, 9, 14, 10, 0),
        ) is None

    def test_a_target_before_completed_at_is_allowed(self):
        decision = redate_target(
            venue_game_start=_utc(2026, 9, 14, 8, 0).isoformat(),
            event_commence=_utc(2026, 9, 13, 19, 12),
            now=NOW,
            completed_at=_utc(2026, 9, 14, 10, 0),
        )
        assert decision is not None
        assert decision[0] == _utc(2026, 9, 14, 8, 0)

    def test_completed_at_exactly_at_the_target_is_allowed(self):
        instant = _utc(2026, 9, 14, 10, 0)
        decision = redate_target(
            venue_game_start=instant.isoformat(),
            event_commence=_utc(2026, 9, 13, 19, 12),
            now=NOW,
            completed_at=instant,
        )
        assert decision is not None


class TestTheStatusRidesOnlyWhenTheStartIsStillAhead:

    def test_a_future_start_goes_back_to_scheduled(self):
        # The ship: 566 rows rendering "No result reported" for matches that have
        # not begun.
        decision = redate_target(
            venue_game_start=_utc(2026, 9, 14, 13, 0).isoformat(),
            event_commence=_utc(2026, 9, 13, 19, 12),
            now=NOW,
        )
        assert decision == (_utc(2026, 9, 14, 13, 0), "scheduled")

    def test_a_past_start_moves_the_date_and_leaves_the_status(self):
        # 261 of the 827. The date was still wrong; whether the row is live,
        # finished or stale is not something this rail can know.
        decision = redate_target(
            venue_game_start=_utc(2026, 9, 14, 5, 0).isoformat(),
            event_commence=_utc(2026, 9, 13, 19, 12),
            now=NOW,
        )
        assert decision == (_utc(2026, 9, 14, 5, 0), None)

    def test_the_status_boundary_is_now(self):
        assert redate_target(
            venue_game_start=NOW.isoformat(),
            event_commence=NOW - timedelta(hours=5),
            now=NOW,
        )[1] is None
        assert redate_target(
            venue_game_start=(NOW + timedelta(seconds=1)).isoformat(),
            event_commence=NOW - timedelta(hours=5),
            now=NOW,
        )[1] == "scheduled"

    def test_the_source_it_writes_is_a_reported_start(self):
        # The whole point of moving the row back to `scheduled`: the ordinary
        # promotion gate must be willing to take it live at the real hour. If
        # `polymarket_venue` were a derived source, the rescheduled rows would
        # never go live again and this ship would trade one defect for another.
        assert commence_time_is_a_reported_start(POLYMARKET_VENUE_COMMENCE_SOURCE)


# ── Driving the rail itself ──────────────────────────────────────────────────


class _RecordingResult:
    def __init__(self, rows, rowcount=0):
        self._rows = rows
        self.rowcount = rowcount

    def fetchall(self):
        return self._rows


class _RecordingSession:
    """Returns canned SELECT rows, then records every statement written.

    ``write_rowcount`` is what the UPDATE reports back. It defaults to ``1`` —
    the row was still there — and a test sets it to ``0`` to stand for the row
    having moved under the pass. That models the ACCOUNTING only: whether the
    shipped WHERE actually declines a changed row is a question about what a
    server decides, and is answered by
    ``tests/integration/test_polymarket_redate_atomicity_6073_pg.py``. A fake
    cannot answer it, which is the whole reason that gate exists.
    """

    def __init__(self, rows, write_rowcount=1):
        self._rows = rows
        self.write_rowcount = write_rowcount
        self.selected_params = None
        self.writes = []
        self.commits = 0

    async def execute(self, stmt, params=None):
        sql = str(stmt)
        if "UPDATE events" in sql:
            self.writes.append((sql, params))
            return _RecordingResult([], rowcount=self.write_rowcount)
        self.selected_params = params
        return _RecordingResult(self._rows)

    async def commit(self):
        self.commits += 1


class _Ctx:
    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, *exc):
        return False


def _row(**kw):
    base = dict(
        event_id=1,
        event_commence=_utc(2026, 9, 13, 19, 12),
        completed_at=None,
        home_score=None,
        away_score=None,
        period=None,
        game_clock=None,
        status="suspended",
        group_id="polymarket:99",
        venue_game_start=_utc(2026, 9, 14, 13, 0).isoformat(),
        n_stamps=1,
        n_events=1,
        # CERT-2840: the group has to NAME the fixture, and the default row is a
        # well-paired one — a real production title over the real specimen pair.
        # The mislink arms override these two and nothing else, so what they
        # change is exactly what they are about.
        home_team_name="Alessandra Mazzola",
        away_team_name="Beatrise Zeltina",
        linked_names=["Alessandra Mazzola vs. Beatrise Zeltina"],
        linked_external_ids=["0xabc"],
    )
    base.update(kw)
    return SimpleNamespace(**base)


#: The pass's clock for every arm in this file, FIXED.
#:
#: Gotcha #44, and this file paid for it: `rescheduled` counts only the rows
#: whose corrected start is still ahead, so with the real wall clock the arms
#: over `SPECIMENS` asserted 4 and got 4 until 09:00Z on 2026-09-14 — the moment
#: the first two specimens' venue starts went past — and 2 for ever afterwards.
#: The suite was green when it was written and red a few hours later, on no
#: branch's change. Real production instants are the right corpus; reading the
#: wall clock beside them is not.
#:
#: Chosen to sit AFTER every specimen's listed start (2026-09-13 20:14Z at the
#: earliest, 2026-09-14 01:59Z at the latest) and BEFORE every venue start
#: (09:00Z at the earliest), so each row is in the band and each corrected start
#: is in the future. No branch on the clock — one instant, stated.
_NOW = _utc(2026, 9, 14, 6, 0)


async def _run(monkeypatch, rows, write_rowcount=1):
    session = _RecordingSession(rows, write_rowcount=write_rowcount)
    monkeypatch.setattr(poly, "get_task_session", lambda: _Ctx(session))

    class _Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return _NOW

    monkeypatch.setattr(poly, "datetime", _Clock)
    stats = await redate_polymarket_listing_stamped_events()
    return stats, session


class TestTheRailWritesWhatTheShipClaims:

    @pytest.mark.asyncio
    async def test_a_future_start_writes_all_three_columns_in_one_statement(
        self, monkeypatch
    ):
        stats, session = await _run(monkeypatch, [_row()])
        assert stats["moved"] == 1
        assert stats["rescheduled"] == 1
        assert len(session.writes) == 1, "two statements would let one land alone"
        sql, params = session.writes[0]
        assert "commence_time = :dt" in sql
        assert "commence_time_source = :src" in sql
        assert "status = :status" in sql
        assert params["dt"] == _utc(2026, 9, 14, 13, 0)
        assert params["src"] == POLYMARKET_VENUE_COMMENCE_SOURCE
        assert params["status"] == "scheduled"
        assert params["id"] == 1
        assert session.commits == 1

    @pytest.mark.asyncio
    async def test_a_past_start_writes_the_date_and_never_the_status(
        self, monkeypatch
    ):
        stats, session = await _run(
            monkeypatch,
            [_row(venue_game_start=_utc(2026, 9, 14, 5, 0).isoformat())],
        )
        assert stats["moved"] == 1
        assert stats["rescheduled"] == 0
        sql, params = session.writes[0]
        # The SET clause only. Since CERT-2834 the WHERE names `status` too — it
        # re-asserts the value it read — and the claim here is that the status is
        # never WRITTEN, which is a statement about what is before the WHERE.
        set_clause, where_clause = sql.split("WHERE", 1)
        assert "status" not in set_clause
        assert "status" not in params
        assert "e.status IS NOT DISTINCT FROM" in where_clause

    @pytest.mark.asyncio
    async def test_it_selects_on_the_listing_stamp_and_nothing_else(
        self, monkeypatch
    ):
        # An odds_api / ESPN / StatPal-dated row must never be reachable: those
        # are real schedules and outrank the venue's own listing.
        _stats, session = await _run(monkeypatch, [_row()])
        assert session.selected_params == {"listing_src": "polymarket"}

    @pytest.mark.asyncio
    async def test_a_multi_event_group_is_skipped_and_counted(self, monkeypatch):
        # 21 of 895 groups. One instant cannot date three fixtures; that is the
        # twins class (#2693), not a dating defect.
        stats, session = await _run(monkeypatch, [_row(n_events=3)])
        assert stats["moved"] == 0
        assert stats["skipped_multi_event_group"] == 1
        assert session.writes == []
        assert session.commits == 0

    @pytest.mark.asyncio
    async def test_a_group_disagreeing_with_itself_is_skipped_and_counted(
        self, monkeypatch
    ):
        stats, session = await _run(monkeypatch, [_row(n_stamps=2)])
        assert stats["moved"] == 0
        assert stats["skipped_ambiguous_stamp"] == 1
        assert session.writes == []

    @pytest.mark.asyncio
    async def test_a_row_with_a_score_is_skipped_through_the_rail_too(
        self, monkeypatch
    ):
        # The predicate refuses it; this proves the rail asks the predicate rather
        # than only the SQL.
        stats, session = await _run(monkeypatch, [_row(home_score=6)])
        assert stats["moved"] == 0
        assert stats["skipped_no_change"] == 1
        assert session.writes == []

    @pytest.mark.asyncio
    async def test_nothing_to_do_commits_nothing_and_says_so(self, monkeypatch):
        stats, session = await _run(monkeypatch, [])
        assert stats == {
            "scanned": 0,
            "moved": 0,
            "rescheduled": 0,
            "skipped_multi_event_group": 0,
            "skipped_ambiguous_stamp": 0,
            "skipped_unpaired_group": 0,
            "skipped_no_change": 0,
            "skipped_raced": 0,
        }
        assert session.commits == 0

    @pytest.mark.asyncio
    async def test_the_whole_specimen_slate_moves_in_one_pass(self, monkeypatch):
        rows = [
            _row(event_id=eid, event_commence=listed, venue_game_start=venue.isoformat())
            for eid, listed, venue, _skew in SPECIMENS
        ]
        stats, session = await _run(monkeypatch, rows)
        assert stats["scanned"] == 4
        assert stats["moved"] == 4
        assert stats["rescheduled"] == 4
        assert {p["id"] for _s, p in session.writes} == {e for e, *_ in SPECIMENS}
        assert session.commits == 1

    @pytest.mark.asyncio
    async def test_single_event_mislink_cannot_retime_event_6073(self, monkeypatch):
        """CERT-2840's witness.

        Every gate before this one counts: one event in the group, one stamp,
        nothing moved underneath. A SINGLE market mislinked to a SINGLE event
        satisfies all of them — `n_events` is 1 because there is one, and the
        stamp is unambiguous because there is only one of those too. What none
        of them ask is whether the market is about this match.

        Here a Serena-Gauff market is linked to the Mazzola-Zeltina fixture: the
        exact same-sport single-mislink shape CERT-2835 drove against the other
        rail. Before the pairing gate the sweep wrote Serena-Gauff's kickoff
        onto it and stamped `polymarket_venue` beside it — a confident wrong
        time, sourced.
        """
        rows = [_row(
            linked_names=["Serena Williams vs. Coco Gauff"],
            linked_external_ids=["0xdeadbeef"],
        )]
        stats, session = await _run(monkeypatch, rows)

        assert stats["moved"] == 0, (
            "a market naming another fixture cannot say when this one starts"
        )
        assert stats["rescheduled"] == 0
        assert stats["skipped_unpaired_group"] == 1
        assert session.writes == [], "no UPDATE may be issued at all"

    @pytest.mark.asyncio
    async def test_a_well_paired_group_still_moves_6073(self, monkeypatch):
        """The twin, without which the gate above passes by declining the world.

        Same row, same everything, except the market's title names the event's
        own two players. It must still be repaired — the ship's whole claim.
        """
        stats, session = await _run(monkeypatch, [_row()])

        assert stats["moved"] == 1
        assert stats["rescheduled"] == 1
        assert stats["skipped_unpaired_group"] == 0
        assert len(session.writes) == 1

    @pytest.mark.asyncio
    async def test_a_non_game_level_market_cannot_retime_a_fixture_6073(
        self, monkeypatch
    ):
        """The non-game-level twin.

        A tournament-winner market can sit in a group and be perfectly VALID as
        a market — it is simply not evidence about when one fixture starts. It
        names a player, not a pair, so there is no matchup to map and the rail
        must decline rather than treat "it parsed to something" as agreement.
        """
        rows = [_row(
            linked_names=["Will Carlos Alcaraz win the US Open?"],
            linked_external_ids=["0xfeed"],
        )]
        stats, session = await _run(monkeypatch, rows)

        assert stats["moved"] == 0
        assert stats["skipped_unpaired_group"] == 1
        assert session.writes == []

    @pytest.mark.asyncio
    async def test_a_group_with_no_linked_market_left_cannot_retime_6073(
        self, monkeypatch
    ):
        """`array_agg ... FILTER` yields NULL, not an empty list, when the group
        has no linked market — and NULL is what the detach in Phase 1.5 leaves
        behind. The pairing gate has to read that as "unproven", not crash on it.
        """
        rows = [_row(linked_names=None, linked_external_ids=None)]
        stats, session = await _run(monkeypatch, rows)

        assert stats["moved"] == 0
        assert stats["skipped_unpaired_group"] == 1

    @pytest.mark.asyncio
    async def test_shared_participant_different_opponent_cannot_retime_event_6073(
        self, monkeypatch
    ):
        """CERT-2842's witness, and the sharper half of the mislink class.

        A market reading "Mazzola vs. Serena" shares a participant with the event
        "Mazzola vs. Zeltina" and is a DIFFERENT MATCH. The first pairing gate
        accepted it, because it asked the matcher's `match_teams_to_event`, which
        returns an orientation as soon as ONE side matches — the right answer to
        the question the matcher asks it, the wrong answer to the question this
        rail asks it.

        On a tour one player appears in a great many fixtures, so a single
        matched name is close to no evidence at all. Both participants must map,
        one-to-one.
        """
        rows = [_row(
            linked_names=["Alessandra Mazzola vs. Serena Williams"],
            linked_external_ids=["0xshared"],
        )]
        stats, session = await _run(monkeypatch, rows)

        assert stats["moved"] == 0, (
            "sharing one player does not make it the same match"
        )
        assert stats["rescheduled"] == 0
        assert stats["skipped_unpaired_group"] == 1
        assert session.writes == []

    @pytest.mark.asyncio
    async def test_the_pair_may_be_named_in_either_order_6073(self, monkeypatch):
        """The valid twin for the two-sided rule.

        Nothing guarantees the market lists home first, and a rule that demanded
        it would decline half the band while looking strict. Away-then-home must
        still repair.
        """
        rows = [_row(
            linked_names=["Beatrise Zeltina vs. Alessandra Mazzola"],
            linked_external_ids=["0xswapped"],
        )]
        stats, session = await _run(monkeypatch, rows)

        assert stats["moved"] == 1
        assert stats["skipped_unpaired_group"] == 0
        assert len(session.writes) == 1

    @pytest.mark.asyncio
    async def test_an_event_missing_a_team_name_cannot_be_paired_6073(
        self, monkeypatch
    ):
        """Half a pairing is not a pairing, and the helper will not say so.

        `match_teams_to_event(matchup, "Alessandra Mazzola", None, ...)` returns
        a TRUTHY orientation dict: it is satisfied by ONE side matching, which is
        the right answer to the question the matcher asks it and the wrong answer
        to the question this rail asks it. If the event's away team is unknown,
        nothing distinguishes this fixture from any other involving that player —
        which on a tour is a great many — so the instant is unproven and must not
        be written.

        Found by mutation: deleting the `home and away` guard left every arm in
        this file green, because no other arm has an event with one side missing.
        """
        rows = [_row(away_team_name=None)]
        stats, session = await _run(monkeypatch, rows)

        assert stats["moved"] == 0
        assert stats["skipped_unpaired_group"] == 1
        assert session.writes == []

    @pytest.mark.asyncio
    async def test_one_bad_row_does_not_cost_the_healthy_siblings(self, monkeypatch):
        rows = [_row(event_id=1, n_events=4), _row(event_id=2)]
        stats, session = await _run(monkeypatch, rows)
        assert stats["moved"] == 1
        assert [p["id"] for _s, p in session.writes] == [2]


class TestItIsWiredAndTheGatesAreInTheQuery:

    def test_the_poll_actually_calls_it(self):
        # The class this repo keeps re-learning: a fix behind a helper no caller
        # runs. Read from the AST of the poll body, not from a grep of the module.
        tree = ast.parse(inspect.getsource(poly._poll_polymarket_markets))
        called = {
            node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        assert "redate_polymarket_listing_stamped_events" in called

    def test_it_runs_after_the_link_sweep(self):
        # It reads `event_id` on child rows that sweep has just written.
        src = inspect.getsource(poly._poll_polymarket_markets)
        assert src.index("link_polymarket_sub_markets()") < src.index(
            "redate_polymarket_listing_stamped_events()"
        )

    def test_the_query_carries_both_group_gates(self):
        assert "n_stamps = 1" in REDATE_LISTING_STAMPED_SQL
        assert "n_events = 1" in REDATE_LISTING_STAMPED_SQL

    def test_the_query_never_reaches_a_finished_row(self):
        # 17,633 closed + 6,261 voided rows carry this provenance. Re-dating a
        # finished game is worth nothing and risks the #46 inversion.
        assert "IN ('live', 'suspended')" in REDATE_LISTING_STAMPED_SQL
        assert "closed" not in REDATE_LISTING_STAMPED_SQL
        assert "voided" not in REDATE_LISTING_STAMPED_SQL

    def test_the_listing_source_is_a_bind_not_a_literal(self):
        assert ":listing_src" in REDATE_LISTING_STAMPED_SQL

    def test_the_query_projects_every_column_the_pass_reads_off_the_row(self):
        """The join between the SELECT and the loop, asserted from both ends.

        🔴 THIS ARM EXISTS BECAUSE ITS ABSENCE WAS MEASURED. Deleting
        ``g.group_id AS group_id`` from the query left all 72 tests green: the
        loop's rows are `SimpleNamespace`s the test built, and a hand-built
        object carries every attribute regardless of what the SQL projected. In
        production the same edit is ``AttributeError: 'Row' object has no
        attribute 'group_id'`` on the first row — swallowed by the ``except``
        the poll wraps this sweep in, so the rail would be dead and the suite
        green forever.

        Neither end is written by hand. The attributes come from the AST of the
        shipped function, so a column read tomorrow is covered without anyone
        remembering this file; the output names come from a real Postgres parser
        rather than a regex, so the CTEs' internal aliases cannot satisfy it by
        accident.
        """
        import sqlglot

        tree = ast.parse(
            textwrap.dedent(
                inspect.getsource(poly.redate_polymarket_listing_stamped_events)
            )
        )
        read = {
            node.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "r"
        }
        assert read, "the AST walk found nothing — this arm would be vacuous"

        projected = set(
            sqlglot.parse_one(
                REDATE_LISTING_STAMPED_SQL, read="postgres"
            ).named_selects
        )
        assert read <= projected, (
            f"the loop reads {sorted(read - projected)} off each row and the "
            f"query does not project it"
        )


# ── CERT-2834: the write re-asserts what the select decided on ───────────────
#
# Selecting a row into a repair band is not permission to write over it. These
# arms hold the SHAPE of the guard — that every decision column is restated,
# null-safely, and that the pass counts a declined write instead of reporting a
# move it did not make. Whether a real server then declines a changed row is a
# different question and it is answered by
# `tests/integration/test_polymarket_redate_atomicity_6073_pg.py`; nothing here
# can answer it, because the session is a double.


class TestTheWriteRefusesARowThatMoved:

    #: Column → the cast the WHERE must carry. Every one of these is either an
    #: input `redate_target` refuses on or a column this statement WRITES, and
    #: the cast is the column's own type: `IS NOT DISTINCT FROM $1` gives
    #: Postgres nothing to infer from, so an uncast bind raises at runtime and
    #: the whole rail dies in the `except` around it, silently, forever.
    GUARDED = [
        ("e.commence_time", ":was_commence", "timestamptz"),
        ("e.commence_time_source", ":listing_src", "text"),
        ("e.status", ":was_status", "text"),
        ("e.home_score", ":was_home_score", "integer"),
        ("e.away_score", ":was_away_score", "integer"),
        ("e.period", ":was_period", "text"),
        ("e.game_clock", ":was_game_clock", "text"),
        ("e.completed_at", ":was_completed_at", "timestamptz"),
    ]

    @pytest.mark.parametrize("sql_name", [
        "REDATE_WRITE_DATE_ONLY_SQL",
        "REDATE_WRITE_WITH_STATUS_SQL",
    ])
    @pytest.mark.parametrize("column,bind,cast", GUARDED)
    def test_both_writes_restate_every_decision_column(
        self, sql_name, column, bind, cast
    ):
        sql = getattr(poly, sql_name)
        clause = f"{column} IS NOT DISTINCT FROM CAST({bind} AS {cast})"
        assert clause in sql, f"{sql_name} does not re-assert {column}"

    @pytest.mark.parametrize("sql_name", [
        "REDATE_WRITE_DATE_ONLY_SQL",
        "REDATE_WRITE_WITH_STATUS_SQL",
    ])
    def test_neither_write_matches_on_the_id_alone(self, sql_name):
        # The defect itself, as a shape: `WHERE id = :id` and nothing else.
        #
        # Counted over the EVENT columns only, with the column name in the
        # pattern. The guard also carries a null-safe comparison on the group's
        # stamp (CERT-2837), which is not an `events` column and must not be
        # able to stand in for one: a bare `IS NOT DISTINCT FROM` count would
        # let a dropped column guard be masked by an added group clause, which
        # is exactly the substitution this arm exists to notice.
        sql = getattr(poly, sql_name)
        where = sql.split("WHERE", 1)[1]
        assert len(re.findall(r"\be\.\w+ IS NOT DISTINCT FROM", where)) == len(
            self.GUARDED
        )

    #: CERT-2837. An absence cannot be asserted with a negative: `NOT EXISTS`
    #: over a group whose rows have all been detached is true, so the two
    #: negative clauses pass vacuously at the exact moment Phase 1.5 withdraws
    #: this group's claim on the event. These are the positive halves.
    REQUIRED_EXISTS = [
        ("still links this event", "fm1.event_id = :id"),
        (
            "still carries the stamp being written",
            "fm1s.market_metadata->>'venue_game_start'",
        ),
    ]

    @pytest.mark.parametrize("sql_name", [
        "REDATE_WRITE_DATE_ONLY_SQL",
        "REDATE_WRITE_WITH_STATUS_SQL",
    ])
    @pytest.mark.parametrize("what,clause", REQUIRED_EXISTS)
    def test_both_writes_require_the_group_evidence_to_still_be_there(
        self, sql_name, what, clause
    ):
        sql = getattr(poly, sql_name)
        assert clause in sql, f"{sql_name} does not assert the group {what}"
        # Positively. A `NOT EXISTS` carrying the same body would read as a
        # guard and mean the opposite.
        body = sql.split(clause, 1)[0]
        opener = body.rfind("EXISTS (")
        assert not body[:opener].rstrip().endswith("NOT"), (
            f"{sql_name} asserts '{what}' as a NOT EXISTS — that is the "
            "vacuous-pass defect CERT-2837 found, inverted"
        )

    @pytest.mark.parametrize("sql_name", [
        "REDATE_WRITE_DATE_ONLY_SQL",
        "REDATE_WRITE_WITH_STATUS_SQL",
    ])
    def test_no_nullable_column_is_compared_with_plain_equality(self, sql_name):
        # `= NULL` is never true. Six of the eight are NULL on the whole
        # production band, so an `=` form would decline every row and this rail
        # would repair nothing while reporting success.
        sql = getattr(poly, sql_name)
        for _, bind, _cast in self.GUARDED:
            assert f"= {bind}" not in sql, bind

    @pytest.mark.parametrize("sql_name", [
        "REDATE_WRITE_DATE_ONLY_SQL",
        "REDATE_WRITE_WITH_STATUS_SQL",
    ])
    def test_both_writes_re_assert_the_two_group_gates(self, sql_name):
        # The matcher's window, not the score poll's: a group that gained a
        # second event no longer names one fixture, and a group that gained a
        # second stamp no longer agrees with itself about when it is.
        sql = getattr(poly, sql_name)
        assert sql.count("NOT EXISTS") == 2
        assert "fm2.event_id <> :id" in sql
        assert "<> CAST(:was_venue_game_start AS text)" in sql

    def test_both_writes_share_one_where(self):
        # Two copies drift; the one that is not read in review is the one that
        # loses a clause. They are the same string by construction.
        assert poly._REDATE_UNCHANGED_WHERE in poly.REDATE_WRITE_DATE_ONLY_SQL
        assert poly._REDATE_UNCHANGED_WHERE in poly.REDATE_WRITE_WITH_STATUS_SQL

    @pytest.mark.asyncio
    async def test_the_pass_binds_the_values_it_read(self, monkeypatch):
        # A guard whose binds come from anywhere but the selected row is a
        # guard comparing the row against itself.
        row = _row(
            event_commence=_utc(2026, 9, 13, 19, 12),
            status="suspended",
            group_id="polymarket:4242",
        )
        _stats, session = await _run(monkeypatch, [row])
        (_sql, params), = session.writes
        assert params["was_commence"] == row.event_commence
        assert params["was_status"] == "suspended"
        assert params["was_home_score"] is None
        assert params["was_away_score"] is None
        assert params["was_period"] is None
        assert params["was_game_clock"] is None
        assert params["was_completed_at"] is None
        assert params["group_id"] == "polymarket:4242"
        assert params["was_venue_game_start"] == row.venue_game_start
        assert params["listing_src"] == poly.LISTING_COMMENCE_SOURCE

    @pytest.mark.asyncio
    async def test_a_declined_write_is_counted_and_never_reported_as_a_move(
        self, monkeypatch
    ):
        stats, session = await _run(monkeypatch, [_row()], write_rowcount=0)
        assert len(session.writes) == 1, "it must still attempt the write"
        assert stats["skipped_raced"] == 1
        assert stats["moved"] == 0
        assert stats["rescheduled"] == 0
        assert session.commits == 0, "nothing moved, so there is nothing to commit"

    @pytest.mark.asyncio
    async def test_a_declined_row_does_not_cost_its_healthy_siblings(
        self, monkeypatch
    ):
        # The `continue` must skip the accounting, not the loop.
        stats, _session = await _run(
            monkeypatch, [_row(event_id=1), _row(event_id=2)], write_rowcount=0
        )
        assert stats["scanned"] == 2
        assert stats["skipped_raced"] == 2

    @pytest.mark.asyncio
    async def test_the_counter_exists_even_when_nothing_races(self, monkeypatch):
        # A key that only appears on the unhappy path is a key no dashboard can
        # chart and no reader of a healthy log can tell from a missing rail.
        stats, _session = await _run(monkeypatch, [_row()])
        assert stats["skipped_raced"] == 0
        assert stats["moved"] == 1
