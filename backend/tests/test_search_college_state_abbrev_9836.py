"""#9836 — the reader's `St.` for `State`, as a pure contract that runs on every push.

The route-level proof (team, game and both venues' markets served for `ohio st`)
lives in `tests/integration/test_search_college_state_abbrev_pg_9836.py`, which
needs Postgres and runs in the `search-recall` job. This half cannot skip.
"""

from __future__ import annotations

import pytest

from app.routes import events as ev
from app.utils.name_normalization import (
    college_state_expansion,
    college_state_query,
    expand_search_terms,
)


@pytest.mark.parametrize("typed", [["ohio", "st"], ["ohio", "St."], ["penn", "ST"]])
def test_a_trailing_st_also_asks_for_state(typed) -> None:
    (first, _), (term, expansion) = expand_search_terms(typed)
    assert first == typed[0]
    assert term == typed[1], "the typed term is kept — `st` still reaches `Ohio St.`"
    assert expansion == "state"


@pytest.mark.parametrize("typed", [["st", "louis"], ["st.", "johns"], ["st"], ["stl"], ["ohio", "state"]])
def test_a_leading_st_or_any_other_word_gets_no_state(typed) -> None:
    assert all(expansion != "state" for _, expansion in expand_search_terms(typed))


def test_the_state_expansion_never_displaces_another_dictionary() -> None:
    """LAST in the chain: `la st` keeps `la` -> `los angeles`."""
    assert expand_search_terms(["la", "st"]) == [("la", "los angeles"), ("st", "state")]


@pytest.mark.parametrize(
    "typed, rewritten",
    [
        ("ohio st", "ohio state"),
        ("Penn St.", "Penn state"),
        ("ohio st iowa", "ohio state iowa"),
    ],
)
def test_the_team_gate_query_is_rewritten(typed, rewritten) -> None:
    assert college_state_query(typed) == rewritten


@pytest.mark.parametrize("typed", ["st louis", "St. Johns", "ohio state", "stanford", "west ham"])
def test_queries_without_a_non_leading_st_are_not_rewritten(typed) -> None:
    assert college_state_query(typed) is None


def test_expansion_is_positional() -> None:
    assert college_state_expansion(0, "st") is None
    assert college_state_expansion(1, "st") == "state"
    assert college_state_expansion(1, "st.") == "state"
    assert college_state_expansion(1, "saint") is None


def _bound(clause) -> list[str]:
    return [str(v).lower() for v in clause.compile().params.values() if isinstance(v, str)]


def test_the_team_gate_binds_the_rewritten_query() -> None:
    assert any("ohio state" in v for v in _bound(ev._build_team_search_filter("ohio st")))


def test_the_team_gate_is_unchanged_without_the_abbreviation(monkeypatch) -> None:
    """None path: for a query with no non-leading `st` the gate's SQL is exactly
    what it is with the #9836 arm removed — and for `ohio st` it is not, so the
    comparison is able to differ."""
    typed = ["ohio state", "st louis", "red sox", "ohio st"]
    with_arm = [str(ev._build_team_search_filter(q).compile()) for q in typed]
    monkeypatch.setattr(ev, "college_state_query", lambda q: None)
    without_arm = [str(ev._build_team_search_filter(q).compile()) for q in typed]
    assert with_arm[:3] == without_arm[:3]
    assert with_arm[3] != without_arm[3]
