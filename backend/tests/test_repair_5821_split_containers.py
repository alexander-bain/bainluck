"""#5821 — guards for the split-container collapse, CERT-2793's required repair.

CERT-2793 BLOCKed the prevention (PR #5864) because it only stops the NEXT split
family being minted: the 687 families that already exist carry non-null, DIFFERENT
event ids, and the prevention's helper is reached only from the auto-create path
selected for unlinked rows. The block named three shapes of repair — "linked-row
repair, event retirement, or serving dedupe". This file guards the first.

WHY THE SERVING DEDUPE ALONE WAS NOT ENOUGH, WHICH IS THE WHOLE REASON THIS FILE
EXISTS. `repair_5821_polymarket_listing_dates.py` (CERT-2798, tokened) is the
serving dedupe: re-date both rows to the venue kickoff and `fold_twin_events`
collapses them to one card. Measured on production 2026-09-13 11:2xZ, that alone
is also a regression, because the fold elects on
`(score, espn_id, external_id, source_count, -id)` and unions only
`win_probability_sources` — the loser's LINKED MARKETS stay on the hidden row,
and `/api/events/{id}/game-markets` loads props strictly by `event_id`:

    15311506  the base       1 market   sources: polymarket  -> SURVIVES
    15311503  the companion 16 markets  sources: none        -> HIDDEN
    served:   survivor totals 0/spreads 0/periods 0; hidden 6/4/3

    125 future split families · 119 lose their props to the fold · 597 tier-5
    markets · 603 Polymarket markets the repair re-points in total

The population query was run against production read-only and returns those 125
families; both of its refusals (`n_bases = 1`, the fold-identity equality) are
INERT on today's rows — removing them leaves the count at 125 — which the script
header states rather than implies.

So the repair re-points the family's markets onto the row the fold is going to
elect, and the row it hides then carries nothing. The end state is the one the
PREVENTION already produces for families minted from now on: one event holding
the moneyline and the derivatives together.

WHAT THIS FILE CAN AND CANNOT TEST. The population query is Postgres-only by
construction (`::timestamptz`, `now()`, a JSONB `->>`, a window function) and CI's
only real-Postgres job runs one unrelated file, so — exactly as in the sibling
suite — these guards cover what is decidable without a database: the election,
the shared write gate, the runbook's honesty, and the reader outcome driven
through the REAL fold rather than described.
"""

from __future__ import annotations

import argparse
import importlib.util
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
REPAIR_PATH = _SCRIPTS / "repair_5821_split_container_markets.py"
RESTORE_PATH = _SCRIPTS / "restore_5821_split_container_markets.py"
DATE_REPAIR_PATH = _SCRIPTS / "repair_5821_polymarket_listing_dates.py"


def _load(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def repair():
    return _load(REPAIR_PATH)


@pytest.fixture(scope="module")
def restore():
    return _load(RESTORE_PATH)


@pytest.fixture(scope="module")
def date_repair():
    return _load(DATE_REPAIR_PATH)


# The production specimen, as measured. The companion minted FIRST and so holds
# the LOWER id — which matters, because the id is the fold's last tiebreak and a
# repair that leaned on it would elect the wrong row.
COMPANION_ID = 15311503
BASE_ID = 15311506
HOME = "Al Ain FC"
AWAY = "Al Nassr Club"
SPORT = 4001


def _family(now):
    """The specimen pair, as production holds it: two events, split markets.

    The companion carries the derivatives and NO probability source; the base
    carries the moneyline and the one source. Both clocks are Gamma LISTING
    stamps in the past, 30 minutes apart, for a fixture two days away.
    """
    from app.models.models import Event

    venue = now + timedelta(days=2)
    companion = Event(
        id=COMPANION_ID,
        sport_id=SPORT,
        home_team_name=HOME,
        away_team_name=AWAY,
        commence_time=now - timedelta(hours=7, minutes=30),
        status="suspended",
        win_probability_sources=None,
    )
    base = Event(
        id=BASE_ID,
        sport_id=SPORT,
        home_team_name=HOME,
        away_team_name=AWAY,
        commence_time=now - timedelta(hours=7),
        status="suspended",
        win_probability_sources={"polymarket": {"value": 0.165}},
    )
    return companion, base, venue


class TestTheElection:
    def test_the_survivor_is_the_serving_layers_choice_not_ours(self, repair):
        """🔴 The repair must move markets ONTO the row the fold keeps.

        `elect_survivor` imports `twin_identity_rank` rather than re-spelling it.
        Asserted here against the function itself, so a future edit that grows a
        private opinion reds — moving markets onto the row the fold hides is the
        defect with extra steps.
        """
        from app.utils.event_twin_fold import twin_identity_rank

        now = datetime.now(timezone.utc)
        companion, base, _ = _family(now)

        survivor, loser = repair.elect_survivor(companion, base)

        assert (survivor, loser) == (base, companion)
        assert twin_identity_rank(survivor) > twin_identity_rank(loser)

    def test_the_election_is_order_independent(self, repair):
        """The arrival order is not ours to choose — tonight the COMPANION
        minted first. A rule that depended on argument order would fix one of
        the two orientations and silently invert on the other."""
        now = datetime.now(timezone.utc)
        companion, base, _ = _family(now)

        assert repair.elect_survivor(companion, base) == repair.elect_survivor(
            base, companion
        )

    def test_the_source_count_outranks_the_row_id(self, repair):
        """🔴 THE SPECIMEN'S WHOLE SHAPE, as a test. The companion has the LOWER
        id and would win the `-id` tiebreak; it loses because the base carries a
        probability source. If this ever inverts, the repair would move 16
        derivative markets onto a row the fold hides, which is strictly worse
        than the duplicate it set out to remove."""
        now = datetime.now(timezone.utc)
        companion, base, _ = _family(now)

        assert companion.id < base.id
        survivor, _ = repair.elect_survivor(companion, base)
        assert survivor.id == BASE_ID


class TestTheReaderOutcome:
    def test_existing_split_container_family_serves_one_event_5821(
        self, repair, date_repair
    ):
        """🔴 THE REQUIRED TEST (CERT-2793).

        An EXISTING split family — two events, the markets divided between them —
        serves ONE event afterwards, with NOTHING left on the row the fold hides.

        Both halves are asserted BEFORE as well as AFTER, so the test cannot pass
        against a repair that does nothing: before it the pair is two cards and
        the props are on the row that loses.

        The two repairs are driven by their OWN decision functions, never by a
        re-implementation of them here — `elect_survivor` for where the markets
        go, `planned_write` for the clocks that make the fold collapse the pair.
        """
        from app.utils.event_twin_fold import fold_twin_events

        now = datetime.now(timezone.utc)
        companion, base, venue = _family(now)
        rows = [companion, base]

        # The family's markets, as production holds them: the derivatives on the
        # companion, the moneyline on the base.
        links = {mid: COMPANION_ID for mid in range(9001, 9017)}  # 16 derivatives
        links[9100] = BASE_ID  # the moneyline

        # ---- BEFORE ---------------------------------------------------------
        before = fold_twin_events(rows)
        assert len(before.events) == 2, (
            "the pair folded before the repair — then this test is measuring "
            "something other than the collapse"
        )
        assert len(set(links.values())) == 2, "the family is not split to begin with"

        # ---- THE LINKED-ROW REPAIR -----------------------------------------
        survivor, loser = repair.elect_survivor(companion, base)
        for market_id, event_id in list(links.items()):
            if event_id == loser.id:
                links[market_id] = survivor.id

        # ---- THE SERVING DEDUPE, the sibling repair -------------------------
        for row in rows:
            plan = date_repair.planned_write(row.status, row.commence_time, venue, now)
            for column, value in plan.items():
                setattr(row, column, value)
        after = fold_twin_events(rows)

        # ONE READER CARD.
        assert len(after.events) == 1, (
            "the two rows still serve as two cards "
            f"(got {[e.id for e in after.events]})"
        )
        served = after.events[0]

        # 🔴 AND IT CARRIES THE WHOLE FAMILY. This is the half the date repair
        # alone fails: `/events/{id}/game-markets` loads props by `event_id`, so
        # a market still pointing at the hidden row is a prop no reader reaches.
        assert set(links.values()) == {served.id}, (
            f"{sum(1 for e in links.values() if e != served.id)} of "
            f"{len(links)} markets are still on the row the fold hides — the "
            "reader gets one card with the props missing"
        )
        assert len(links) == 17, "the family lost a market somewhere in the move"

    def test_the_date_repair_alone_leaves_the_props_stranded(
        self, repair, date_repair
    ):
        """🔴 READ THIS ONE SECOND. It is the regression, as a test.

        Without the linked-row repair, the fold still gives one card — and every
        derivative market is on the row it hid. A future edit that deletes the
        re-point half reds here with the reason attached, instead of shipping a
        card whose props silently vanished.
        """
        from app.utils.event_twin_fold import fold_twin_events

        now = datetime.now(timezone.utc)
        companion, base, venue = _family(now)
        rows = [companion, base]
        links = {mid: COMPANION_ID for mid in range(9001, 9017)}
        links[9100] = BASE_ID

        for row in rows:
            plan = date_repair.planned_write(row.status, row.commence_time, venue, now)
            for column, value in plan.items():
                setattr(row, column, value)
        after = fold_twin_events(rows)

        assert len(after.events) == 1
        stranded = [m for m, e in links.items() if e != after.events[0].id]
        assert len(stranded) == 16, (
            "the date repair no longer strands the derivatives — if that is a "
            "real improvement, this guard and the repair it justifies should be "
            "revisited together rather than one of them deleted"
        )


class TestTheMembershipIsConfirmedNotGuessed:
    def test_the_suffix_list_comes_from_the_matcher(self, repair):
        """One vocabulary, not a copy. A suffix added to the matcher must widen
        this population the same day; a second list here is how a repair starts
        looking up base names nothing composes."""
        from app.tasks.prediction_market_matching import (
            _POLYMARKET_CONTAINER_SUFFIXES,
        )

        pattern = repair.suffix_regex()
        for suffix in _POLYMARKET_CONTAINER_SUFFIXES:
            assert re.search(pattern, f"A vs. B{suffix}"), suffix
        assert not re.search(pattern, "A vs. B")

    def test_a_suffix_is_matched_only_at_the_END(self, repair):
        """Anchored, so a fixture whose own title happens to contain the phrase
        is not swept in as somebody's container."""
        pattern = repair.suffix_regex()

        assert not re.search(pattern, "More Markets United vs. B")

    def test_the_population_refuses_an_ambiguous_base(self, repair):
        """`n_bases = 1`. A base title resolving to two base events at the same
        kickoff is refused, never picked between — the sibling repair refuses its
        own ambiguity (27 events) for the same reason."""
        assert "n_bases = 1" in repair._POPULATION_SQL_TEMPLATE

    def test_the_population_requires_the_folds_own_identity(self, repair):
        """🔴 The guard the PREVENTION does not need and a repair does. The
        prevention decides where a NEW market attaches; this MOVES markets that
        already have a home, so it refuses unless the two rows are the pair the
        fold would itself collapse once their clocks agree — same sport, same two
        names. Without this a shared base title plus a shared kickoff could move
        markets between two genuinely different fixtures."""
        sql = repair._POPULATION_SQL_TEMPLATE

        assert "ce.sport_id IS NOT DISTINCT FROM be.sport_id" in sql
        assert "ce.home_team_name = be.home_team_name" in sql
        assert "ce.away_team_name = be.away_team_name" in sql

    def test_only_future_fixtures_are_in_scope(self, repair):
        """Past families are excluded for the sibling's reason: settled rows feed
        settlement and calibration windows, and the reader-visible defect is not
        there."""
        sql = repair._POPULATION_SQL_TEMPLATE

        assert sql.count("> now()") == 2, (
            "both the container and the base side must be bounded to the future"
        )

    def test_an_unlinked_market_is_not_this_repairs_business(self, repair):
        """It has no wrong home to move it out of, and the matcher — with the
        prevention deployed — attaches it correctly. Moving it here would race
        the matcher for no gain."""
        assert "m.event_id IS NOT NULL" in repair._POPULATION_SQL_TEMPLATE


class TestTheWriteGate:
    @pytest.mark.parametrize("flag", ["backup", "apply"])
    def test_a_write_is_refused_off_the_producer_app(self, repair, monkeypatch, flag):
        monkeypatch.setenv("HEROKU_APP_NAME", "bainluck")
        args = argparse.Namespace(backup=False, apply=False)
        setattr(args, flag, True)

        refusal = repair.wrong_app_refusal(args)

        assert refusal and repair.PRODUCER_APP in refusal

    @pytest.mark.parametrize("flag", ["backup", "apply"])
    def test_a_write_is_refused_on_no_app_at_all(self, repair, monkeypatch, flag):
        """UNSET refuses too. Unset means a laptop pointed at the production
        database with whatever happens to be checked out, which is precisely the
        case the gate exists to stop."""
        monkeypatch.delenv("HEROKU_APP_NAME", raising=False)
        args = argparse.Namespace(backup=False, apply=False)
        setattr(args, flag, True)

        assert repair.wrong_app_refusal(args)

    def test_a_dry_run_reads_anywhere(self, repair, monkeypatch):
        monkeypatch.delenv("HEROKU_APP_NAME", raising=False)

        assert (
            repair.wrong_app_refusal(argparse.Namespace(backup=False, apply=False))
            is None
        )

    def test_the_gate_is_the_SIBLINGS_gate_not_a_copy(self, repair, date_repair):
        """🔴 One gate, four programs. Two gates for one decision is how a
        runbook and its program start to disagree — and this pairing already
        shipped that bug once: the sibling's refusal read a flag its own undo's
        parser does not have, so it raised INSIDE the gate, failing open on the
        program it was added to protect."""
        # Asserted on where the function is DEFINED, not on object identity:
        # these fixtures load each script by path, so the sibling the repair
        # imported through `sys.path` is a different module OBJECT from the one
        # loaded here, and an identity check would fail for a reason that does
        # not exist in production. `co_filename` is the claim that matters — a
        # hand-copied gate would name THIS file.
        assert repair.wrong_app_refusal.__code__.co_filename.endswith(
            "repair_5821_polymarket_listing_dates.py"
        )
        assert repair.PRODUCER_APP == date_repair.PRODUCER_APP

    def test_the_restore_takes_the_same_gate(self, restore):
        assert restore.wrong_app_refusal.__code__.co_filename.endswith(
            "repair_5821_polymarket_listing_dates.py"
        )

    def test_the_restore_ACTUALLY_CALLS_the_gate(self, restore, monkeypatch):
        """🔴 A MUTATION SURVIVED WITHOUT THIS. Asserting the restore holds a
        reference to the gate proves neither that it calls it nor that the call
        is reached before the write. Run it on the wrong app and require exit 2
        with no database touched — deleting the call from `run()` reds here and
        nowhere else.
        """
        import asyncio

        monkeypatch.setenv("HEROKU_APP_NAME", "bainluck")

        def _explode(*a, **k):  # pragma: no cover — the point is it is not called
            raise AssertionError("the restore reached the database on the wrong app")

        monkeypatch.setattr(
            "app.tasks.base.get_task_session", _explode, raising=False
        )

        code = asyncio.run(restore.run(argparse.Namespace(apply=True)))

        assert code == 2


class TestTheRunbookIsHonest:
    def test_every_flag_the_header_prints_exists(self, repair):
        parser_flags = {"--backup", "--apply", "--dry-run"}
        header = repair.__doc__

        # `--[a-z]` and not `--[a-z-]`: the header's section rules are long runs
        # of dashes, and the looser pattern reads one as a flag named `----`.
        for flag in re.findall(r"--[a-z][a-z-]*", header):
            assert flag in parser_flags, f"the header prints {flag}, the parser has not"

    def test_the_undo_line_names_a_script_that_exists_and_takes_its_flag(
        self, restore
    ):
        assert RESTORE_PATH.exists()

        p = argparse.ArgumentParser()
        p.add_argument("--apply", action="store_true")
        assert p.parse_args(["--apply"]).apply

    def test_the_apply_points_at_the_date_repair_as_the_NEXT_step(self, repair):
        """🔴 The ordering is load-bearing and it is printed, not assumed. Run
        the other way round and the fold hides a row while its markets are still
        on it, which is the 597-market regression this repair exists to prevent.
        """
        source = REPAIR_PATH.read_text()

        assert "NEXT: run repair_5821_polymarket_listing_dates.py" in source

    def test_the_header_states_the_measured_population(self, repair):
        """The numbers an operator sizes the attended window on are in the file
        they run, not only in a cert nobody reads at 3am."""
        header = repair.__doc__

        assert "125" in header and "597" in header and "603" in header

    def test_the_header_admits_the_refusals_are_inert_today(self, repair):
        """🔴 MEASURED, NOT IMPLIED. Removing `n_bases = 1` and the fold-identity
        equality leaves the production count at 125 — both refusals exclude
        nothing today. They are right to exist (this repair MOVES links that
        already have a home), but a header that listed them without saying so
        would read as though they were filtering, and the next person to size an
        attended window would believe a narrowing that is not happening."""
        assert "INERT ON TODAY'S POPULATION" in repair.__doc__
