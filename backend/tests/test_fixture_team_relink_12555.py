"""146-A: the hourly task repairs wrong game clubs without changing prices/results."""

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import DateTime, select, update
from sqlalchemy.orm import Session

from app.models import Event, FuturesMarket, FuturesOutcome, Sport, Team
from app.tasks import team_linking
from app.utils.fixture_clubs import load_fixture_clubs
from tests.test_game_team_identity_12555 import _run, _seed
from tests.test_team_link_drain_advances_7307 import _AsyncShim, _FakeCursorStore, _make_engine


CAPTURE = json.loads((Path(__file__).parent / "fixtures/fixture_relink_12555.json").read_text())


def _insert(session, model, row):
    values = dict(row)
    for column in model.__table__.columns:
        if isinstance(column.type, DateTime) and isinstance(values.get(column.name), str):
            values[column.name] = datetime.fromisoformat(values[column.name])
    session.execute(model.__table__.insert().values(**values))


def _captured_seed(session, status):
    _insert(session, Sport, {"id": 1, "key": "americanfootball_nfl", "name": "NFL", "active": True})
    other_sport = next(t["sport_id"] for t in CAPTURE["teams"] if t["id"] == 10740)
    _insert(session, Sport, {"id": other_sport, "key": "baseball_mlb", "name": "MLB", "active": True})
    for team in CAPTURE["teams"]:
        _insert(session, Team, team)
    _insert(session, Event, CAPTURE["event"])
    for market in CAPTURE["markets"]:
        _insert(session, FuturesMarket, {**market, "status": status})
    # The snapshot contains these control outcomes but not their parent market
    # rows. Their contexts are explicitly synthetic, not production evidence.
    for market_id in CAPTURE["control_markets_without_snapshot"]:
        _insert(session, FuturesMarket, {
            "id": market_id, "source": "control", "external_id": str(market_id),
            "name": "Synthetic non-game control context", "status": "open",
            "category": "championship", "market_tier": 1, "event_id": None,
        })
    for row in CAPTURE["targets"] + CAPTURE["controls"]:
        _insert(session, FuturesOutcome, row)
    session.commit()


def _snapshot(session, model):
    return {row["id"]: dict(row) for row in session.execute(select(model.__table__)).mappings()}


def _repair(session, store=None, limit=200):
    stats = {
        "outcomes_relinked_into_fixture": 0, "outcomes_unlinked_outside_fixture": 0,
        "outcomes_fixture_clears_held": 0,
        "fixture_relink_identity_changed": 0, "fixture_refusals": {},
        "fixture_refusal_samples": [], "errors": [], "units_rolled_back": [],
    }
    store = store if store is not None else _FakeCursorStore()
    writes = []
    asyncio.run(team_linking._relink_outside_fixture(_AsyncShim(session), stats, limit, store, writes))
    session.commit()
    team_linking._apply_cursor_writes(store, writes)
    return stats


@pytest.mark.parametrize("status", ["open", "resolved", "closed"])
def test_captured_42_targets_change_only_club_and_all_78_controls_stay_identical(status, caplog):
    caplog.set_level(logging.INFO, logger=team_linking.__name__)
    with Session(_make_engine()) as session:
        _captured_seed(session, status)
        before = _snapshot(session, FuturesOutcome)
        markets = _snapshot(session, FuturesMarket)
        events = _snapshot(session, Event)
        teams = _snapshot(session, Team)
        targets = {row["id"] for row in CAPTURE["targets"]}
        controls = {row["id"] for row in CAPTURE["controls"]}
        assert len(targets) == 42 and len(controls) == 78 and not targets & controls
        store = _FakeCursorStore()
        repaired = 0
        for _ in range(10):
            stats = _repair(session, store)
            repaired += stats["outcomes_relinked_into_fixture"]
            assert stats["errors"] == stats["units_rolled_back"] == []
            assert stats["outcomes_unlinked_outside_fixture"] == 0
            after = _snapshot(session, FuturesOutcome)
            assert {oid: after[oid] for oid in controls} == {oid: before[oid] for oid in controls}
            if repaired == 42:
                break
        assert repaired == 42
        assert after == {oid: {**row, "team_id": 541} if oid in targets else row for oid, row in before.items()}
        assert _snapshot(session, FuturesMarket) == markets
        assert _snapshot(session, Event) == events
        assert _snapshot(session, Team) == teams
        receipts = [r.getMessage() for r in caplog.records if r.getMessage().startswith("Fixture relink relinked:")]
        assert len(receipts) == 42
        for oid in targets:
            receipt = next(line for line in receipts if f"outcome={oid} " in line)
            assert f"market={before[oid]['market_id']} fixture={CAPTURE['event']['id']}" in receipt
            assert "old_club=10740 new_club=541 matched_by=name" in receipt
            assert f"sport=americanfootball_nfl status={status}" in receipt
        again = _repair(session, store)
        assert again["outcomes_relinked_into_fixture"] == 0
        assert _snapshot(session, FuturesOutcome) == after


@pytest.mark.parametrize("change,reason", [
    ({"delete": True}, "missing_event"),
    ({"away_team_id": None, "away_team_name": "Unknown club"}, "away_club_unknown"),
    ({"sport_id": 999999}, "unknown_fixture_sport"),
    ({"home_team_id": 10740}, "home_club_sport_or_gender_mismatch"),
    ({"away_team_id": 541, "away_team_name": "Arizona Cardinals"}, "same_club_on_both_sides"),
    ({"home_team_id": 999999}, "home_club_unknown"),
    ({"home_team_name": "Seattle Seahawks"}, "home_club_name_mismatch"),
])
def test_unknown_fixture_refuses_new_links_and_leaves_stored_links_unchanged(change, reason):
    with Session(_make_engine()) as session:
        _seed(session)
        event = session.get(Event, 14781145)
        if change.get("delete"):
            session.delete(event)
        else:
            for key, value in change.items():
                setattr(event, key, value)
        session.commit()
        links, stats = _run(session, use_llm=True)
        assert all(links[oid] is None for oid in range(1, 8))
        assert links[8] == 10740
        assert stats["fixture_refusals"][reason] >= 7
        assert {"event_id": 14781145, "reason": reason} in stats["fixture_refusal_samples"]


def test_duplicate_exact_fixture_name_is_not_arbitrarily_picked():
    with Session(_make_engine()) as session:
        _seed(session, home_id=None, away_id=None)
        session.add(Team(id=9999, sport_id=1, name="Arizona Cardinals"))
        session.commit()
        links, stats = _run(session)
        assert all(links[oid] is None for oid in range(1, 8))
        assert links[8] == 10740
        assert stats["fixture_refusals"]["home_club_ambiguous"] >= 7


@pytest.mark.parametrize("status", ["open", "resolved", "closed"])
def test_verified_fixture_with_no_unique_replacement_holds_the_clear(status, caplog):
    caplog.set_level(logging.INFO, logger=team_linking.__name__)
    with Session(_make_engine()) as session:
        _seed(session)
        session.get(FuturesOutcome, 8).name = "Unknown Player"
        session.get(FuturesMarket, 67649495).status = status
        session.commit()
        before = _snapshot(session, FuturesOutcome)
        stats = _repair(session)
        assert stats["outcomes_unlinked_outside_fixture"] == 0
        assert stats["outcomes_fixture_clears_held"] == 1
        assert _snapshot(session, FuturesOutcome) == before
        assert ("Fixture relink clear_held: outcome=8 market=67649495 fixture=14781145 "
                "old_club=10740 new_club=none matched_by=none sport=americanfootball_nfl "
                f"status={status} reason=no_fixture_match") in caplog.text


def test_future_clear_enablement_records_the_committed_clear(caplog):
    caplog.set_level(logging.INFO, logger=team_linking.__name__)
    with Session(_make_engine()) as session:
        _seed(session)
        session.get(FuturesOutcome, 8).name = "Unknown Player"
        session.commit()
        before = _snapshot(session, FuturesOutcome)
        with patch.object(team_linking, "_FIXTURE_CLEARS_ENABLED", True):
            stats = _repair(session)
        assert stats["outcomes_unlinked_outside_fixture"] == 1
        assert _snapshot(session, FuturesOutcome) == {
            oid: {**row, "team_id": None} if oid == 8 else row for oid, row in before.items()
        }
        assert "old_club=10740 new_club=cleared matched_by=none" in caplog.text


def test_roster_replacement_records_its_matching_method(caplog):
    caplog.set_level(logging.INFO, logger=team_linking.__name__)
    with Session(_make_engine()) as session:
        _seed(session)
        session.get(FuturesOutcome, 8).name = "Kyler Murray"
        session.commit()
        stats = _repair(session)
        assert stats["outcomes_relinked_into_fixture"] == 1
        assert "old_club=10740 new_club=541 matched_by=roster" in caplog.text


def test_cursor_moves_past_refusals_and_reserves_space_for_settled_games():
    with Session(_make_engine()) as session:
        _seed(session)
        session.query(FuturesOutcome).delete()
        event = session.get(Event, 14781145)
        session.add(Event(id=2, sport_id=1, home_team_id=541, home_team_name="Arizona Cardinals", away_team_name="Unknown club",
                          commence_time=event.commence_time))
        session.add_all([
            FuturesMarket(id=2, source="polymarket", external_id="unknown-fixture", name="Unknown fixture",
                          event_id=2, status="open", market_tier=1),
            FuturesMarket(id=3, source="polymarket", external_id="settled-game", name="Finished game",
                          event_id=14781145, status="resolved", market_tier=1),
        ])
        session.flush()
        for oid in range(1, 7):
            session.add(FuturesOutcome(id=oid, name="Cardinals", external_id=str(oid), team_id=10740,
                                       market_id=2 if 2 <= oid <= 5 else 67649495 if oid == 1 else 3))
        session.commit()
        store = _FakeCursorStore()
        first = _repair(session, store, limit=4)
        assert first["fixture_selected_open"] == 3
        assert first["fixture_selected_resolved"] == 1
        assert first["outcomes_relinked_into_fixture"] == 1
        assert first["fixture_refused_open_markets"] == {"away_club_unknown": 1}
        assert int(store.data[team_linking._FIXTURE_CURSOR_OPEN]) == 3
        assert _snapshot(session, FuturesOutcome)[6]["team_id"] == 541
        second = _repair(session, store, limit=4)
        assert second["fixture_selected_open"] == 2
        assert second["outcomes_relinked_into_fixture"] == 1
        assert _snapshot(session, FuturesOutcome)[1]["team_id"] == 541
        assert team_linking._FIXTURE_CURSOR_OPEN not in store.data


def test_an_ineligible_read_page_advances_to_the_older_wrong_link():
    with Session(_make_engine()) as session:
        _seed(session)
        session.add_all([
            FuturesOutcome(id=9, name="Cardinals", external_id="valid-nine", market_id=67649495, team_id=541),
            FuturesOutcome(id=10, name="Rams", external_id="null-ten", market_id=67649495, team_id=None),
        ])
        session.commit()
        store = _FakeCursorStore()
        with patch.object(team_linking, "_FIXTURE_SCAN_LIMIT", 2), patch.object(team_linking, "_FIXTURE_SCAN_WINDOWS", 1):
            first = _repair(session, store)
            assert first["fixture_scanned_open"] == first["fixture_scanned_resolved"] == 2
            assert first["fixture_selected_open"] == 0
            assert first["outcomes_relinked_into_fixture"] == 0
            assert int(store.data[team_linking._FIXTURE_CURSOR_OPEN]) == 9
            second = _repair(session, store)
        assert second["outcomes_relinked_into_fixture"] == 1
        after = _snapshot(session, FuturesOutcome)
        assert after[8]["team_id"] == after[9]["team_id"] == 541
        assert after[10]["team_id"] is None


def test_empty_id_ranges_advance_without_wrapping_or_skipping_the_tail():
    with Session(_make_engine()) as session:
        _seed(session)
        session.add(FuturesOutcome(id=100, name="Rams", external_id="new-unlinked", market_id=67649495, team_id=None))
        session.commit()
        store = _FakeCursorStore()
        with patch.object(team_linking, "_FIXTURE_ID_SPAN", 20), patch.object(team_linking, "_FIXTURE_SCAN_WINDOWS", 1):
            first = _repair(session, store)
            assert first["outcomes_relinked_into_fixture"] == 0
            assert int(store.data[team_linking._FIXTURE_CURSOR_OPEN]) == 81
            empty = _repair(session, store)
            assert empty["fixture_scanned_open"] == 0
            assert int(store.data[team_linking._FIXTURE_CURSOR_OPEN]) == 61
            for _ in range(3):
                last = _repair(session, store)
            assert int(store.data[team_linking._FIXTURE_CURSOR_OPEN]) == 1
            tail = _repair(session, store)
            assert tail["outcomes_relinked_into_fixture"] == 0
        assert last["outcomes_relinked_into_fixture"] == 1
        assert _snapshot(session, FuturesOutcome)[8]["team_id"] == 541
        assert team_linking._FIXTURE_CURSOR_OPEN not in store.data


@pytest.mark.parametrize("changed", ["outcome", "market", "fixture", "club", "price"])
def test_identity_changes_refuse_but_a_new_price_is_preserved(changed):
    with Session(_make_engine()) as session:
        _seed(session)
        original = load_fixture_clubs

        async def change_after_read(shim, ids):
            result = await original(shim, ids)
            if changed == "outcome":
                session.execute(update(FuturesOutcome).where(FuturesOutcome.id == 8).values(name="Rams"))
            elif changed == "market":
                session.execute(update(FuturesMarket).where(FuturesMarket.id == 67649495).values(event_id=None))
            elif changed == "fixture":
                session.execute(update(Event).where(Event.id == 14781145).values(away_team_id=10741))
            elif changed == "club":
                session.execute(update(Team).where(Team.id == 541).values(name="Changed identity"))
            elif changed == "price":
                session.execute(update(FuturesOutcome).where(FuturesOutcome.id == 8).values(current_probability=0.6789))
            return result

        with patch("app.utils.fixture_clubs.load_fixture_clubs", change_after_read):
            stats = _repair(session)
        row = _snapshot(session, FuturesOutcome)[8]
        assert stats["errors"] == []
        assert stats["fixture_relink_identity_changed"] == int(changed != "price")
        assert row["team_id"] == (541 if changed == "price" else 10740)
        if changed == "price":
            assert float(row["current_probability"]) == 0.6789


def test_fixture_failure_rolls_back_repairs_and_the_success_counter(caplog):
    caplog.set_level(logging.INFO, logger=team_linking.__name__)
    with Session(_make_engine()) as session:
        _seed(session)
        session.add(FuturesOutcome(id=9, name="Cardinals", external_id="second", market_id=67649495, team_id=10740))
        session.commit()
        before = _snapshot(session, FuturesOutcome)
        original = _AsyncShim.execute
        writes = 0

        async def fail_second_write(shim, statement, *args, **kwargs):
            nonlocal writes
            if statement.is_update:
                writes += 1
                if writes == 2:
                    raise RuntimeError("injected unit failure")
            return await original(shim, statement, *args, **kwargs)

        with patch.object(_AsyncShim, "execute", fail_second_write):
            stats = _repair(session)
        assert stats["outcomes_relinked_into_fixture"] == 0
        assert stats["units_rolled_back"] == ["Fixture relink open"]
        assert _snapshot(session, FuturesOutcome) == before
        assert "Fixture relink relinked:" not in caplog.text
        assert "Fixture relink cleared:" not in caplog.text
