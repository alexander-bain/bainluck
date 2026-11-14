"""#12042: the container twin sweep loads evidence only for families of two or more rows.

`polymarket_container_twin_sweep` peaked at 473.8 MB on worker-background (512 MB)
and finished 2 of 13 runs on Nov 10-11 (both at its 300 s limit, terminal fail):
its window now holds ~45k events (plan estimate; 1,852 on 2026-09-17), and every
one was loaded as a full `Event` ORM row. The judgement reads a row only for the
members of a key holding two or more events, so the sweep now loads exactly those,
narrowed to the columns the election and the row read. These tests pin that the
plan is unchanged and that nothing outside a family is loaded.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

from app.tasks import polymarket_container_twin_sweep as sweep
from app.utils.polymarket_container_twins import (
    ContainerMarket,
    ContainerRow,
    judged_key,
    plan_container_tags,
    split_family_event_ids,
)

KICKOFF = "2026-09-19T23:00:00Z"
OTHER_KICKOFF = "2026-09-20T23:00:00Z"
BASE = "Lexington SC vs. Orange County SC"
OTHER = "Miami FC vs. Tampa Bay Rowdies"


def _m(event_id, name, vgs=KICKOFF):
    return ContainerMarket(event_id=event_id, name=name, venue_game_start=vgs)


#: A split family (1, 2), a twin family with an anchored duplicate (3, 4), a
#: fixture on one row (5), the same title at another kickoff (6), and a market
#: with no kickoff at all (7).
MARKETS = [
    _m(1, BASE), _m(1, f"{BASE} - Exact Score"), _m(2, f"{BASE} - More Markets"),
    _m(3, OTHER), _m(4, f"{OTHER} - More Markets"),
    _m(5, "Austin FC vs. LA Galaxy"), _m(5, "Austin FC vs. LA Galaxy - Halftime Result"),
    _m(6, BASE, vgs=OTHER_KICKOFF),
    _m(7, f"{BASE} - More Markets", vgs=None),
]

ALL_ROWS = {
    1: ContainerRow(1, identity_rank=(2,)), 2: ContainerRow(2, identity_rank=(1,)),
    3: ContainerRow(3, identity_rank=(2,)), 4: ContainerRow(4, espn_id="401", identity_rank=(1,)),
    5: ContainerRow(5, identity_rank=(1,)), 6: ContainerRow(6, identity_rank=(1,)),
    7: ContainerRow(7, identity_rank=(1,)),
}


def test_only_events_in_a_family_of_two_or_more_are_selected():
    assert split_family_event_ids(MARKETS) == {1, 2, 3, 4}


def test_the_plan_is_identical_with_only_the_family_rows():
    full = plan_container_tags(MARKETS, ALL_ROWS)
    family = split_family_event_ids(MARKETS)
    narrow = plan_container_tags(MARKETS, {k: v for k, v in ALL_ROWS.items() if k in family})
    assert [(t.duplicate_id, t.canonical_id) for t in narrow.tags] == [
        (t.duplicate_id, t.canonical_id) for t in full.tags
    ]
    assert narrow.refusals == full.refusals
    assert (narrow.keys_examined, narrow.rows_considered, narrow.split_keys_examined) == (
        full.keys_examined, full.rows_considered, full.split_keys_examined)
    # The control: the fixture really exercises a tag AND a refusal.
    assert full.tags and full.refusals


def test_the_plan_and_the_selection_share_one_key_predicate():
    assert judged_key(_m(7, BASE, vgs=None)) is None
    assert judged_key(_m(7, BASE, vgs="  ")) is None
    assert judged_key(_m(1, f"{BASE} - Exact Score")) == (BASE, KICKOFF)


class _Session:
    """Answers the population read with MARKETS, then records the Event read."""

    def __init__(self):
        self.statements = []

    async def execute(self, stmt, params=None):
        self.statements.append(stmt)
        if len(self.statements) == 1:
            rows = [SimpleNamespace(event_id=m.event_id, name=m.name, vgs=m.venue_game_start,
                                    tags_text="[]") for m in MARKETS if m.venue_game_start]
            return rows
        ids = sorted(stmt.compile().params.get("id_1", []))
        self.requested = ids
        events = [SimpleNamespace(id=i, espn_id=None, statpal_fixture_id=None, status="scheduled",
                                  home_score=None, away_score=None, external_id=None,
                                  win_probability_sources={}, sport=None) for i in ids]

        class _R:
            def scalars(self_inner):
                class _S:
                    def all(self_s):
                        return events
                return _S()
        return _R()


def test_load_rows_reads_only_family_events_with_narrow_columns(monkeypatch):
    monkeypatch.setattr(sweep, "twin_identity_rank", lambda e: (0,), raising=False)
    session = _Session()
    markets, rows, current_tags = asyncio.run(sweep.load_rows(session, lookback=45, lookahead=45))
    assert session.requested == [1, 2, 3, 4], "events outside a family were loaded"
    assert set(rows) == {1, 2, 3, 4}
    assert set(current_tags) == {1, 2, 3, 4}
    assert len(markets) == 8  # every market with a kickoff still reaches the plan
    sql = str(session.statements[1])
    assert "box_score_data" not in sql and "events.espn_id" in sql
    assert "events.win_probability_sources" in sql and "events.statpal_fixture_id" in sql


def test_no_family_means_no_event_read():
    class _Lonely(_Session):
        async def execute(self, stmt, params=None):
            self.statements.append(stmt)
            return [SimpleNamespace(event_id=9, name=BASE, vgs=KICKOFF, tags_text="[]")]

    session = _Lonely()
    markets, rows, current_tags = asyncio.run(sweep.load_rows(session, lookback=45, lookahead=45))
    assert len(session.statements) == 1 and rows == {} and current_tags == {}
