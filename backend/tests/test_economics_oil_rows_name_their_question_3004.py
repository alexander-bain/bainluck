"""#3004: the /economics Crude Oil card stops printing a made-up number under a label that names no question.

Reproduced at 390px on production 2026-09-16 22:28 PDT — the same two rows
authority/412 photographed at 19:4x, rotated specimens, identical shape:

    rendered            prints   the venue quotes
    WTI No                 32%   50.0
    Oil At least 370       13%   97.0

THE LABEL IS THE SMALLER HALF. The issue was filed against the label, and the
label is real: `frontend/app/economics/page.tsx` prefers `${sym} ${range}` over
the question whenever `sym` is present, so a reader is handed `Oil At least 370`
with no way to learn whether 370 is barrels, dollars or rigs. But both rows were
also printing a number nobody quoted, because both markets were fed through a
path that assumes a partition:

  * `Number of US oil rigs at end of 2026` is twelve CUMULATIVE `At least X`
    rungs — 97.0, 96.0, 93.5, 90.5, 86.5, 82.5, 78.0, 66.0, 57.0, 21.0, 5.0, 4.5
    — summing to 777.5%. `_brackets_from_outcomes(normalize=True)` rescales
    anything over 105% back to 100, so 97.0 was served as 12.5. The page said
    13% about an event its own source prices at 97%.

  * `Will WTI Crude Oil (WTI) hit (LOW) $90 Week of September 14 2026?` is a
    Yes/No binary whose outcome set also carries two rungs of a sibling ladder
    (No .50, Yes .495, ↓ $90 .495, ↓ $65 .055 — 154.5%), so the same rescale
    turned P(No) = 50.0 into 32.4, and the modal label into the word `No`.

REPAIRING ONLY THE LABEL WOULD HAVE BEEN WORSE THAN LEAVING IT. `Oil At least
370 — 13%` is cryptic, and a reader distrusts it; `Number of US oil rigs at end
of 2026 · At least 370 — 13%` is a confident sentence wrong by 84 points.

The ladder half is this file's own rule, one call site short: the
`_CUMULATIVE_PREFIXES` block says in as many words that such rows "legitimately
sum well over 100% and must never be normalized or rescaled against each other",
and `_is_cumulative_ladder` has been there since #2563 to detect it. The energy
branch asks a weaker question — `any("above" in name)` — which `At least 370`
fails, so the ladder reaches the partition path and is rescaled.

What this file pins:

  1. each production specimen's number, as an EQUALITY against the price the
     venue quotes. Never "not 12.5": a mutant returning 0 satisfies that;
  2. the row is STILL SERVED, and still carries its question. This ship moves a
     number DOWN in one case (32.4 → 49.5 is up, 12.5 → 57.0 is up, but the
     ladder fallback arm moves one down) and a vanished row would satisfy every
     "the wrong label is gone" assertion as happily as a repair does;
  3. `sym`/`range` are GONE from the repaired rows — that, and only that, is
     what makes the page print the question, because the renderer's fallback to
     `o.q` is unreachable while `sym` is present;
  4. a genuine partition still takes the composite path, unchanged. `WTI 85 or
     above` is a fair reading of one and has no specimen on today's card;
  5. GAS IS REFUSED. The gas card is a histogram of the whole distribution, so
     one rung would draw a one-bar chart. Gas markets are cumulative ladders as
     often as oil ones, so the refusal is load-bearing;
  6. the wiring itself, by source scan — an optional new arm is invisible to
     mypy and to every test in this file if the route stops calling it. Mutated
     three ways (delete, rename, constant), per ux/1307's finding that a scan
     without a word boundary survives a rename.

The fake-market helper is lifted from the sibling guard
`test_economics_row_names_the_leg_it_prints_6696.py` (discover, #6696), whose
`leader` rail this ship's rows ride: real ORM objects rather than stand-ins,
because a double carrying only today's fields turns the next column read into an
AttributeError in the guard instead of a finding in the code.

Every price below is the stored `current_probability` read by `db-query` at
2026-09-17 05:3xZ, the same minute as the served payload above.
"""

import re
from pathlib import Path

from app.models import FuturesMarket, FuturesOutcome
from app.routes import economics as econ
from app.routes.economics import _ladder_rung, _oil_row


def _market(name: str, outcomes: list[tuple[str, float | None]], *, mid: int = 1,
            source: str = "kalshi"):
    market = FuturesMarket(id=mid, name=name, source=source)
    market.outcomes = [
        FuturesOutcome(name=n, external_id=n, current_probability=p)
        for n, p in outcomes
    ]
    return market


# --- The two production specimens ------------------------------------------

RIGS_NAME = "Number of US oil rigs at end of 2026"
RIGS_RUNGS = [
    ("At least 370", 0.970),
    ("At least 380", 0.960),
    ("At least 390", 0.935),
    ("At least 400", 0.905),
    ("At least 410", 0.865),
    ("At least 420", 0.825),
    ("At least 430", 0.780),
    ("At least 440", 0.660),
    ("At least 450", 0.570),
    ("At least 500", 0.210),
    ("At least 550", 0.050),
    ("At least 600", 0.045),
]

WTI_NAME = "Will WTI Crude Oil (WTI) hit (LOW) $90 Week of September 14 2026?"
WTI_LEGS = [
    ("No", 0.500),
    ("Yes", 0.495),
    ("↓ $90", 0.495),
    ("↓ $65", 0.055),
]


def _rigs():
    return _market(RIGS_NAME, RIGS_RUNGS, mid=3970343)


def _wti():
    return _market(WTI_NAME, WTI_LEGS, mid=60787563, source="polymarket")


class TestTheDefectTheseSpecimensReproduce:
    """The fixtures are the defect, not a straw version of it.

    Every assertion in this file is about a function that did not exist before
    this ship, so "it fails on the pre-fix body" is only an ImportError and
    proves nothing about the specimens. THIS class is the red half: it runs the
    two UNCHANGED helpers the old path used — `_brackets_from_outcomes` then
    `_modal_bracket` — over the same fixtures and asserts they produce, to the
    tenth, the two numbers and the two labels a reader saw on production at
    22:28 PDT. If a later edit makes these pass differently, the specimens have
    stopped reproducing #3004 and the rest of the file is guarding nothing.
    """

    def test_the_rigs_ladder_rescaled_into_the_number_on_the_page(self):
        brackets = econ._brackets_from_outcomes(_rigs())
        _, prob, label = econ._modal_bracket(brackets)
        assert (prob, label) == (12.5, "At least 370")  # rendered `Oil At least 370 — 13%`
        assert sum(b[0] for b in econ._brackets_from_outcomes(_rigs(), normalize=False)) == 777.5

    def test_the_contaminated_binary_rescaled_into_the_number_on_the_page(self):
        brackets = econ._brackets_from_outcomes(_wti())
        _, prob, label = econ._modal_bracket(brackets)
        assert (prob, label) == (32.4, "No")  # rendered `WTI No — 32%`

    def test_the_weak_cumulative_test_is_what_lets_the_ladder_through(self):
        # The energy branch's own gate. `At least 370` carries no "above", so
        # the ladder is handed to the partition path — while the file's
        # `_is_cumulative_ladder`, three hundred lines up, has always said yes.
        rigs = _rigs()
        assert not any("above" in (o.name or "").lower() for o in rigs.outcomes)
        assert econ._is_cumulative_ladder(rigs)


class TestTheRigsLadder:
    """Twelve cumulative rungs summing to 777.5%, served as 12.5."""

    def test_prints_a_price_the_venue_quotes(self):
        row = _oil_row(_rigs())
        assert row is not None, "the row must still be served, not withheld"
        # 57.0 is `At least 450`'s own stored price. Not 12.5 (the rescale), and
        # not 97.0 (the loosest bound, which is the least informative rung).
        assert row["prob"] == 57.0

    def test_names_the_rung_that_price_belongs_to(self):
        row = _oil_row(_rigs())
        assert row["leader"] == "At least 450"

    def test_carries_the_question_whole(self):
        row = _oil_row(_rigs())
        assert row["q"] == RIGS_NAME

    def test_drops_sym_and_range_so_the_page_can_reach_the_question(self):
        # The renderer is `q={o.sym ? `${o.sym} ${o.range}` : o.q}` — while `sym`
        # is present the question is unreachable, whatever else is in the row.
        row = _oil_row(_rigs())
        assert "sym" not in row
        assert "range" not in row

    def test_the_seam_holds(self):
        # `prob` is the price of the outcome `leader` names — the number and the
        # name must not be able to come from two different rungs.
        row = _oil_row(_rigs())
        named = [p for n, p in RIGS_RUNGS if n == row["leader"]]
        assert named == [row["prob"] / 100]

    def test_keeps_the_rest_of_the_row_contract(self):
        row = _oil_row(_rigs())
        assert row["market_id"] == 3970343
        assert row["delta"] is None
        assert row["src"]


class TestTheContaminatedBinary:
    """A Yes/No market carrying two rungs of a sibling ladder."""

    def test_prints_the_price_of_an_answerable_leg(self):
        row = _oil_row(_wti())
        assert row is not None
        # 49.5 is what the venue quotes for a leg that is not the question's own
        # `No`. 32.4 was the rescale of 50.0 across four overlapping outcomes.
        assert row["prob"] == 49.5

    def test_never_prints_the_negation(self):
        row = _oil_row(_wti())
        assert row["leader"] != "No"
        assert row["prob"] != 50.0

    def test_carries_the_question_and_no_composite(self):
        row = _oil_row(_wti())
        assert row["q"] == WTI_NAME
        assert "sym" not in row
        assert "range" not in row

    def test_the_seam_holds_whichever_of_the_tied_legs_wins(self):
        # `Yes` and `↓ $90` are both priced .495, so which one `max` returns is
        # decided by outcome order — the NAME may be either (`Yes` suppresses to
        # None as uninformative), but the PRICE cannot differ, and a named
        # leader must be the leg whose price is printed.
        row = _oil_row(_wti())
        if row["leader"] is not None:
            named = [p for n, p in WTI_LEGS if n == row["leader"]]
            assert named == [row["prob"] / 100]

    def test_leader_is_always_present_even_when_null(self):
        # An absent key is indistinguishable from a payload cached before the
        # field existed, which the page must also survive (#6696's contract).
        assert "leader" in _oil_row(_wti())


class TestWhatIsLeftAlone:
    def test_a_genuine_partition_falls_through_to_the_composite(self):
        partition = _market(
            "WTI price at year end?",
            [("85 or above", 0.16), ("80 to 85", 0.34), ("75 to 80", 0.30), ("70 to 75", 0.20)],
        )
        assert _oil_row(partition) is None

    def test_a_gas_ladder_is_refused_so_its_histogram_keeps_every_bar(self):
        gas = _market(
            "Natural gas price on September 30?",
            [("Above 2.5", 0.90), ("Above 3.0", 0.62), ("Above 3.5", 0.21)],
        )
        assert _oil_row(gas) is None

    def test_the_gas_refusal_is_load_bearing_not_decorative(self):
        # The same market with the word `gas` out of its name IS re-routed, so
        # the refusal is the only thing keeping the histogram whole.
        not_gas = _market(
            "Brent crude price on September 30?",
            [("Above 2.5", 0.90), ("Above 3.0", 0.62), ("Above 3.5", 0.21)],
        )
        assert _oil_row(not_gas) is not None

    def test_a_binary_too_wide_for_the_row_builder_falls_through(self):
        # `_market_row` refuses above five outcomes (#2950). That is a
        # fall-through to the bracket path, not a dropped row.
        wide = _market(
            "Will WTI Crude Oil (WTI) hit $90 this week?",
            [("Yes", 0.4), ("No", 0.6), ("a", 0.1), ("b", 0.1), ("c", 0.1), ("d", 0.1)],
        )
        assert _oil_row(wide) is None

    def test_an_unpriced_ladder_is_refused_rather_than_printed_at_zero(self):
        empty = _market(
            "Number of US oil rigs at end of 2027",
            [("At least 370", None), ("At least 380", None)],
        )
        assert _oil_row(empty) is None


class TestTheRungChoice:
    def test_takes_the_tightest_bound_the_market_still_favours(self):
        rung = _ladder_rung(_rigs())
        assert (rung.name, float(rung.current_probability)) == ("At least 450", 0.570)

    def test_a_ladder_favouring_nothing_falls_back_to_its_dearest_rung(self):
        longshot = _market(
            "Number of US oil rigs at end of 2026",
            [("At least 500", 0.21), ("At least 550", 0.05), ("At least 600", 0.045)],
        )
        rung = _ladder_rung(longshot)
        assert rung.name == "At least 500"

    def test_a_rung_at_exactly_half_counts_as_favoured(self):
        # `>= 0.5`, not `> 0.5`: a coin-flip bound is still the tightest thing
        # the market has not called against.
        even = _market(
            "Number of US oil rigs at end of 2026",
            [("At least 400", 0.80), ("At least 450", 0.50), ("At least 500", 0.20)],
        )
        assert _ladder_rung(even).name == "At least 450"

    def test_first_of_a_tie_wins(self):
        tied = _market(
            "Number of US oil rigs at end of 2026",
            [("At least 400", 0.80), ("At least 450", 0.57), ("At least 460", 0.57)],
        )
        assert _ladder_rung(tied).name == "At least 450"

    def test_a_descending_ladder_reads_the_same_way(self):
        # `below`/`before` rungs rise with the threshold instead of falling, and
        # "the tightest bound still favoured" is the same sentence either way —
        # which is why the choice is made on the price and never on a number
        # parsed out of the label.
        deadline = _market(
            "When will the SPR refill finish?",
            [("Before Jan 1, 2027", 0.20), ("Before Jan 1, 2028", 0.55), ("Before Jan 1, 2030", 0.92)],
        )
        assert _ladder_rung(deadline).name == "Before Jan 1, 2028"

    def test_unpriced_rungs_are_skipped_not_read_as_zero(self):
        holey = _market(
            "Number of US oil rigs at end of 2026",
            [("At least 400", None), ("At least 450", 0.60), ("At least 500", 0.20)],
        )
        assert _ladder_rung(holey).name == "At least 450"


class TestTheWiring:
    """The route must actually call the new arm.

    `_oil_row` is a new optional arm on one branch of one loop: every test above
    passes whether or not the energy section calls it. ux/1307 measured the
    other half of this — a source scan without a word boundary survives the
    mutant that RENAMES the thing it is guarding, because `_oil_row` matches
    happily inside `x_oil_row`. So the scan below is anchored on both sides and
    mutated three ways: delete the call (no match), rename it (the lookbehind
    refuses), and pass a constant (the argument is asserted).
    """

    def _energy_section(self) -> str:
        source = Path(econ.__file__).read_text()
        start = source.index("# --- Energy section ---")
        end = source.index("# --- Housing section ---", start)
        return source[start:end]

    def test_the_energy_section_calls_the_new_arm(self):
        assert re.search(r"(?<!\w)_oil_row\(m\)", self._energy_section())

    def test_the_scan_is_not_vacuous(self):
        # The anti-strawman control: the same scan over the section it must NOT
        # match. If this ever passes, the scan is matching something else.
        source = Path(econ.__file__).read_text()
        housing = source[source.index("# --- Housing section ---"):]
        assert not re.search(r"(?<!\w)_oil_row\(m\)", housing)

    def test_the_row_it_returns_is_appended_and_short_circuits(self):
        section = self._energy_section()
        assert "oil_rows.append(_oil)" in section
        # Without the `continue` the market would be appended twice — once as a
        # repaired row and once as the composite the bracket path builds.
        appended = section.index("oil_rows.append(_oil)")
        assert "continue" in section[appended:appended + 120]
