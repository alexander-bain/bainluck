"""#8628 r2 — one match stops filling a club search's market rows.

The ladder fold (r1) left production `dda40b8b` (2026-09-25 ~17:55Z) serving
`?q=united` with 7 of its 10 market rows from `Scunthorpe United FC vs.
Hartlepool United FC`, each a DIFFERENT ladder. `?q=real` served 4 from one
Segunda match. The fixtures are those served rows, verbatim, in served order.
"""

from __future__ import annotations

import inspect

import pytest

from app.routes import events as ev


class _Market:
    def __init__(self, id, name, source="polymarket", market_tier=5):
        self.id = id
        self.source = source
        self.name = name
        self.market_tier = market_tier
        self.canonical_market_key = None


SH = "Scunthorpe United FC vs. Hartlepool United FC"
MW = "Manchester United WFC vs. West Ham United FC"
UNITED_PAGE = [
    _Market(61857970, "Serbia Parliamentary Election Winner", market_tier=1),
    _Market(62351207, f"{MW}: Manchester United WFC O/U 1.5"),
    _Market(62303937, f"{MW}: West Ham United FC O/U 0.5"),
    _Market(62322202, f"{SH}: Scunthorpe United FC O/U 5.5 Corners"),
    _Market(62322203, f"{SH}: Hartlepool United FC O/U 4.5 Corners"),
    _Market(61823335, f"{SH}: Scunthorpe United FC O/U 1.5"),
    _Market(61823337, f"{SH}: Hartlepool United FC O/U 0.5"),
    _Market(61823340, f"{SH}: Scunthorpe United FC 1st Half O/U 0.5"),
    _Market(61823341, f"{SH}: Hartlepool United FC 1st Half O/U 0.5"),
    _Market(60942432, f"{SH} - More Markets"),
]
SH_IDS = {m.id for m in UNITED_PAGE if m.name.startswith(SH)}

CR = "AD Ceuta FC vs. Real Sociedad de Fútbol B"
REAL_PAGE = [
    _Market(392, "Champions League Winner: PSG vs Arsenal", source="kalshi", market_tier=1),
    _Market(62361436, f"{CR}: Real Sociedad de Fútbol B 1st Half O/U 0.5"),
    _Market(62361444, f"{CR}: Real Sociedad de Fútbol B 2nd Half O/U 1.5"),
    _Market(61816646, f"{CR}: Real Sociedad de Fútbol B O/U 0.5"),
    _Market(62136071, f"{CR}: Real Sociedad de Fútbol B O/U 4.5 Corners"),
    _Market(62349349, "Real Salt Lake vs. New England Revolution: Real Salt Lake 1st Half O/U 3.5"),
    _Market(62351183, "Real Valladolid CF vs. Córdoba CF: Real Valladolid CF 1st Half O/U 0.5"),
]


def _words(q):
    return frozenset(ev._SEARCH_WORD.findall(q.lower()))


def _compose(rows, q):
    """The handler's window loop and its sink, over rows in rank order."""
    seen, kept, counts, over = set(), {}, {}, set()
    out = []
    for m in rows:
        if not ev._admit_search_future(m, seen, kept, []):
            continue
        if ev._is_over_match_cap(m, counts, _words(q)):
            over.add(m.id)
        out.append(m)
    return [m.id for m in ev._sink_over_match_cap(out, over)], over


def test_precondition_the_old_rule_serves_seven_rows_of_one_match():
    seen, kept = set(), {}
    admitted = [m.id for m in UNITED_PAGE if ev._admit_search_future(m, seen, kept, [])]
    assert len(admitted) == 10
    assert sum(1 for i in admitted if i in SH_IDS) == 7


class TestTheMatchKey:
    @pytest.mark.parametrize("m", [m for m in UNITED_PAGE if m.id in SH_IDS])
    def test_every_scunthorpe_row_shares_one_key(self, m):
        assert ev._search_match_key(m) == "match:" + SH.lower()

    def test_the_more_markets_suffix_is_the_same_fixture(self):
        assert ev._search_match_key(_Market(1, f"{SH} - Exact Score")) == "match:" + SH.lower()

    def test_a_bare_fixture_is_its_own_key(self):
        assert ev._search_match_key(_Market(1, "Rangers vs. Maple Leafs")) == "match:rangers vs. maple leafs"

    def test_a_v_fixture_counts(self):
        assert ev._search_match_key(_Market(1, "Hull v Leeds: Hull O/U 1.5")) == "match:hull v leeds"

    @pytest.mark.parametrize("name", [
        "Champions League Winner: PSG vs Arsenal",
        "Serbia Parliamentary Election Winner",
        "Will there be a run scored in the first inning?: Texas Rangers vs. Minnesota Twins",
        "",
    ])
    def test_a_row_that_names_no_fixture_before_its_colon_has_no_key(self, name):
        assert ev._search_match_key(_Market(1, name)) is None


class TestTheCap:
    def test_united_keeps_two_scunthorpe_rows_in_place_and_sinks_five(self):
        ids, over = _compose(UNITED_PAGE, "united")
        assert over == {61823335, 61823337, 61823340, 61823341, 60942432}
        assert ids[:5] == [61857970, 62351207, 62303937, 62322202, 62322203]
        assert ids[5:] == [61823335, 61823337, 61823340, 61823341, 60942432]

    def test_a_match_that_ranks_first_gives_its_slots_to_the_rows_below(self):
        sh = [m for m in UNITED_PAGE if m.id in SH_IDS]
        rest = [m for m in UNITED_PAGE if m.id not in SH_IDS]
        ids, _ = _compose(sh + rest, "united")
        assert ids[:5] == [62322202, 62322203, 61857970, 62351207, 62303937]
        assert set(ids[5:]) == SH_IDS - {62322202, 62322203}

    def test_sinking_drops_nothing(self):
        ids, _ = _compose(UNITED_PAGE, "united")
        assert sorted(ids) == sorted(m.id for m in UNITED_PAGE)

    def test_real_sinks_the_ceuta_match_past_two(self):
        ids, over = _compose(REAL_PAGE, "real")
        assert over == {61816646, 62136071}
        assert ids[-2:] == [61816646, 62136071]
        assert ids[:5] == [392, 62361436, 62361444, 62349349, 62351183]

    def test_a_fixtures_first_rows_are_its_highest_ranked(self):
        rows = list(reversed(UNITED_PAGE))
        _, over = _compose(rows, "united")
        kept = SH_IDS - over
        assert kept == {60942432, 61823341}

    def test_the_cap_is_two(self):
        assert ev._SEARCH_MATCH_ROWS_CAP == 2


class TestTheQueryThatNamesTheMatch:
    def test_naming_both_sides_disarms_the_cap(self):
        _, over = _compose(UNITED_PAGE, "scunthorpe hartlepool")
        assert over == set()

    @pytest.mark.parametrize("q", ["united", "scunthorpe", "hartlepool", "united fc"])
    def test_a_word_on_one_side_or_on_both_does_not(self, q):
        _, over = _compose(UNITED_PAGE, q)
        assert len(over) == 5

    def test_accented_names_split_into_words(self):
        key = ev._search_match_key(REAL_PAGE[1])
        assert ev._query_names_both_sides(key, _words("ceuta fútbol"))


class TestTheHandlerWiring:
    SRC = inspect.getsource(ev.search_events)

    def test_both_admission_loops_count_the_cap(self):
        assert self.SRC.count("if _is_over_match_cap(m, _match_counts, _query_words):") == 2

    def test_the_refill_gate_still_counts_an_over_cap_row(self):
        """The cap must never FIRE a refill (2.4-4.0 s on `united`, 3 ms on
        `city` where it does not run): the gate's count is the pre-cap one."""
        start = self.SRC.index("    _answer_rows = sum(")
        gate = self.SRC[start:self.SRC.index("_answer_rows < _SEARCH_FUTURES_PAGE", start)]
        assert "_over_match_cap_ids" not in gate

    def test_once_the_refill_runs_the_count_drops_the_sunk_rows(self):
        gate = self.SRC.index("_answer_rows < _SEARCH_FUTURES_PAGE")
        drop = self.SRC.index("_answer_rows -= sum(")
        refill = self.SRC.index("futures_query.offset(_SEARCH_FUTURES_WINDOW)")
        assert gate < drop < refill
        assert "if m.id in _over_match_cap_ids" in self.SRC[drop:refill]

    def test_the_refill_loop_counts_only_rows_that_lead(self):
        loop = self.SRC[self.SRC.index("refill_rows, expanded,"):]
        assert "and m.id not in _over_match_cap_ids\n            ):\n                _answer_rows += 1" in loop

    def test_the_sink_runs_outside_the_refill_branch(self):
        """The window alone can hold over-cap rows, so the sink cannot live in
        the branch that only runs on a collapse."""
        assert "\n    if _over_match_cap_ids:\n        deduped_futures = _demote_teamless_sport(\n            _sink_over_match_cap(" in self.SRC

    def test_the_sink_runs_before_the_page_is_sliced(self):
        assert self.SRC.index("_sink_over_match_cap(deduped_futures") < self.SRC.index(
            "_deduped_page = deduped_futures[:_SEARCH_FUTURES_PAGE]"
        )

    def test_the_query_words_come_from_the_identity_not_the_raw_query(self):
        assert "_SEARCH_WORD.findall(_q_identity.lower())" in self.SRC
