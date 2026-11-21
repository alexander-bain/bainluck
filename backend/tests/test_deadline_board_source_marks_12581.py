"""Deadline cards explain real inputs, including a calculated opposite side."""

import copy
from types import SimpleNamespace

import pytest

from app.utils.roundup_containers import (
    RoundupMembers,
    RoundupRefusal,
    evaluate_roundup_producer,
    reset_roundup_cache_for_tests,
)
from app.utils.same_deadline_board import (
    BY_DECEMBER_31_PRODUCER,
    select_same_deadline_board,
)
from tests.test_same_deadline_board import (
    FIXED_NOW,
    _live_december_31_markets,
    _live_november_30_markets,
)


def select(rows, **kwargs):
    result = select_same_deadline_board(
        rows, deadline="2026-12-31", now=FIXED_NOW, **kwargs
    )
    assert isinstance(result, RoundupMembers)
    return result


def mark_quote(row, source, probability):
    mark = row["source_mark"]
    assert mark["state"] == "single"
    assert len(mark["sources"]) == 1
    quote = mark["sources"][0]
    assert quote["key"] == source
    assert quote["probability"] == pytest.approx(probability)
    assert quote["observed_at"] is None
    assert quote["reason"] == "observation_unknown"
    return mark


@pytest.mark.parametrize(
    ("factory", "deadline"),
    [
        (_live_december_31_markets, "2026-12-31"),
        (_live_november_30_markets, "2026-11-30"),
    ],
)
def test_full_board_and_member_inputs_are_preserved_without_borrowing_row_clocks(
    factory, deadline
):
    rows = factory()
    original = copy.deepcopy(rows)
    result = select_same_deadline_board(rows, deadline=deadline, now=FIXED_NOW)
    assert isinstance(result, RoundupMembers)
    by_id = {r["id"]: r for r in rows}
    for row in result.rows:
        market = by_id[row["market_id"]]
        mark_quote(row, market["source"], market["outcomes"][0]["probability"])
    for member in result.members:
        market = by_id[member["id"]]
        for row, original_row in zip(
            member["card"]["top_outcomes"], market["outcomes"]
        ):
            mark_quote(row, market["source"], original_row["probability"])
    assert rows == original


def test_yes_only_market_explains_the_calculated_no_without_inventing_a_no_quote():
    rows = _live_december_31_markets()
    rows[0]["source"] = "kalshi"
    rows[0]["outcomes"] = rows[0]["outcomes"][:1]
    result = select(rows)
    card = next(m["card"] for m in result.members if m["id"] == rows[0]["id"])
    yes, no = card["top_outcomes"]
    mark_quote(yes, "kalshi", 0.885)
    mark = mark_quote(no, "kalshi", 0.885)
    assert no["probability"] == pytest.approx(0.115)
    assert mark["method"] == "The No number is 100% minus this source's Yes price"


def test_complementary_rounding_explains_a_one_point_difference():
    result = select(_live_december_31_markets())
    card = result.members[0]["card"]
    yes, no = card["top_outcomes"]
    assert yes["rendered_percent"] == 89
    assert no["rendered_percent"] == 11
    mark = mark_quote(no, "polymarket", 0.115)
    assert mark["method"] == "Rounded with Yes so the two rows total 100%"


def test_conflicting_stored_no_and_displayed_complement_keep_a_refusal_reason():
    rows = _live_december_31_markets()
    rows[0]["outcomes"][1]["probability"] = 0.4
    result = select(rows)
    no = result.members[0]["card"]["top_outcomes"][1]
    assert no["probability"] == 0.4
    assert no["rendered_percent"] == 11
    assert no["source_mark"] == {
        "state": "none",
        "sources": [],
        "reason": "display_basis_conflict",
    }


@pytest.mark.parametrize("source", [None, "", "both", "unknown-provider"])
def test_missing_source_never_inherits_the_legacy_polymarket_default(source):
    rows = _live_december_31_markets()
    rows[0]["source"] = source
    result = select(rows)
    mark = result.rows[0]["source_mark"]
    assert mark["state"] == "none"
    assert mark["sources"] == []
    assert mark["reason"] == "source_evidence_incomplete"


def test_real_zero_and_one_remain_inputs_when_the_configured_band_admits_them():
    rows = _live_december_31_markets()
    rows[0]["outcomes"][0]["probability"] = 0.0
    rows[0]["outcomes"][1]["probability"] = 1.0
    result = select(rows, band=(0.0, 1.0))
    card = next(m["card"] for m in result.members if m["id"] == rows[0]["id"])
    mark_quote(card["top_outcomes"][0], "polymarket", 0.0)
    mark_quote(card["top_outcomes"][1], "polymarket", 1.0)


def test_an_unknown_result_is_not_relabelled_as_a_current_quote():
    rows = _live_december_31_markets()
    rows[0]["outcomes"][0]["resolution_source"] = "ungradeable_result"
    result = select(rows)
    mark = result.rows[0]["source_mark"]
    assert mark == {"state": "none", "sources": [], "reason": "result_unknown"}


def test_held_marks_do_not_change_when_inputs_or_another_output_are_mutated():
    rows = _live_december_31_markets()
    result = select(rows)
    expected = copy.deepcopy(result.rows[0]["source_mark"])
    rows[0]["source"] = "kalshi"
    rows[0]["outcomes"][0]["probability"] = 0.2
    result.members[0]["card"]["top_outcomes"][0]["source_mark"]["sources"].clear()
    assert result.rows[0]["source_mark"] == expected


@pytest.mark.asyncio
async def test_cached_container_and_feed_keep_their_marks_without_another_read(
    monkeypatch,
):
    monkeypatch.setenv("CONTAINERS_READ_CACHE_ENABLED", "true")

    class Session:
        def __init__(self):
            self.calls = 0
            self.refuse_read = False

        async def execute(self, statement):
            assert not self.refuse_read, "cached response must not issue a query"
            self.calls += 1
            rows = _live_december_31_markets()
            return SimpleNamespace(
                all=lambda: rows,
                scalars=lambda: SimpleNamespace(
                    all=lambda: rows,
                    unique=lambda: SimpleNamespace(all=lambda: rows),
                ),
            )

    session = Session()
    reset_roundup_cache_for_tests()
    try:
        feed, container = await evaluate_roundup_producer(
            BY_DECEMBER_31_PRODUCER, session, now=FIXED_NOW
        )
        assert all("source_mark" in r for r in feed["data"]["roundup"]["rows"])
        expected = copy.deepcopy(container)
        assert session.calls > 0
        session.refuse_read = True
        # Read this producer's cache. Child-board navigation has independent reads.
        cached_feed, cached = await evaluate_roundup_producer(
            BY_DECEMBER_31_PRODUCER, session, now=FIXED_NOW
        )
        assert cached_feed == feed
        assert cached == expected
        assert all(
            "source_mark" in o
            for m in cached["sections"][0]["members"]
            for o in m["card"]["top_outcomes"]
        )
    finally:
        reset_roundup_cache_for_tests()


def test_withheld_or_graded_members_still_refuse_with_the_original_reason():
    rows = _live_december_31_markets()[:4]
    blocked_id = rows[0]["outcomes"][0]["id"]
    result = select_same_deadline_board(
        rows,
        deadline="2026-12-31",
        now=FIXED_NOW,
        withheld_by_market={rows[0]["id"]: {blocked_id}},
    )
    assert isinstance(result, RoundupRefusal)
    assert ("member", rows[0]["id"], f"withheld_price_{blocked_id}") in result.reasons
