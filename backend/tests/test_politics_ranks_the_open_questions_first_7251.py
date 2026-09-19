"""#7251 — every /politics section leads with the questions still open.

Production LOOK at 390px on 2026-09-19, and the served payload behind it
(`GET /api/politics`, `updated_at 15:25:16Z`): **45 of the page's 60 cards were
>95% or <5%**, and four of its six sections were 10 of 10 decided. The
Gubernatorial section opened with eight consecutive cards whose probability bar
is drawn full, each captioned with a name that has already won.

The mechanism was one key, spent at two sites in this file:

    rows.sort(key=lambda r: -abs(r["prob"] - 50))        # build_section
    side_markets.sort(key=lambda r: -abs(r["prob"] - 50))

Distance from 50, DESCENDING — most-decided-first. The tell is SCOTUS, whose ten
cards ran `2.1, 4.3, 4.5, 5.5, 8.0, 8.2, 91.0, 88.0, 85.5, 18.5`: the single
genuinely open question on the page was ranked LAST of ten.

Three things this file pins, because all three had to be true at once:

1.  **The order is flipped** — open first, and it is measured over a pool
    LARGER than the cap, because both call sites slice after sorting. The key
    is a SELECTOR, not merely an order: a section with more candidates than
    slots did not bury its open questions, it dropped them from the payload.

2.  **Arity, not distance from 50** (`_decidedness`). A bare sign flip
    reproduces this issue's own complaint in the other direction: a five-way
    field whose leader sits at 2.1% is a perfectly open race, and `abs(p - 50)`
    scores it 47.9 and ranks it last. Every 98% card in the shopped
    Gubernatorial table is a THREE-outcome market, so this page is where that
    mismodelling actually renders.

3.  **A volume floor that DEMOTES and never deletes** (`_never_really_traded`).
    Ranking by uncertainty alone promotes degenerate rows — flipping SCOTUS
    most-open-first puts a 4-contract market above an 11,031-contract one. The
    floor sinks those. It does not drop them, and neither is the existing
    `prob > 95` guard widened, because a section on this page can be ~entirely
    decided and a deleting floor could render one blank — a state the page has
    never drawn.

⚠️  WHAT THIS FILE CANNOT REACH, STATED SO NOBODY READS MORE INTO IT.
`build_section` is a closure inside the endpoint and `side_markets` is built
mid-function, so neither can be called without a database. Re-implementing
`sorted(pairs, key=...)[:limit]` in a test would be a fixture answering its own
question. So the split is deliberate: the behavioural arms below prove the KEY
is right, and `test_no_sort_in_politics_is_keyed_on_distance_from_50` — an
`ast` walk, not a regex — proves both call sites actually spend it. A missed
call site is SILENT: it does not error, it just keeps serving the wall.
"""

import ast
import inspect
from types import SimpleNamespace

import pytest

from app.routes import politics as politics_module
from app.routes.politics import (
    _by_uncertainty,
    _decidedness,
    _never_really_traded,
)


def row(prob: float, outcome_count: int = 2) -> dict:
    return {"prob": prob, "outcome_count": outcome_count}


def market(volume: int | None = 50_000) -> SimpleNamespace:
    """A market that has plainly traded, unless the caller says otherwise."""
    return SimpleNamespace(volume=volume)


def rank(pairs: list[tuple[dict, SimpleNamespace]]) -> list[dict]:
    """The pool in served order — the key under test, ascending."""
    return [r for r, _ in sorted(pairs, key=lambda rm: _by_uncertainty(*rm))]


# --------------------------------------------------------------------------
# The ship: the reader's section stops opening with finished races
# --------------------------------------------------------------------------

def test_the_one_open_question_leads_a_section_of_finished_races():
    """#7251's headline, in the shape the Gubernatorial section had."""
    open_one = row(50.0)
    pool = [(open_one, market())] + [
        (row(p), market()) for p in (98, 98, 97, 97, 97, 97, 96, 96, 96)
    ]
    assert rank(pool)[0] is open_one


def test_the_scotus_specimen_leads_instead_of_trailing():
    """The exact ten probabilities a reader saw, in the order they were served.

    18.5% — `market_id 56914114`, the H-2A monetary-remedies question — was
    tenth of ten. Volumes are the measured ones, so the two degenerate rows
    (9 and 4 contracts) are present and must NOT take the lead off it.
    """
    served = [
        (2.1, 11_031), (4.3, 2_322), (4.5, 23_344), (5.5, 820), (8.0, 11_029),
        (8.2, 11_031), (91.0, 4), (88.0, 820), (85.5, 9), (18.5, 395),
    ]
    pool = [(row(p), market(v)) for p, v in served]
    assert rank(pool)[0]["prob"] == 18.5


def test_the_key_selects_not_merely_orders_over_a_pool_past_the_cap():
    """Both call sites slice after sorting, so the cap is where this pays.

    A 30-row pool against `build_section`'s `limit=10`: under the old key the
    open question was 30th and never reached the payload at all.
    """
    open_one = row(50.0)
    pool = [(open_one, market())] + [(row(97.0), market()) for _ in range(29)]
    served = rank(pool)[:10]
    assert open_one in served
    assert served[0] is open_one


def test_nothing_is_dropped_the_floor_demotes():
    """Demotion, not deletion — a section can be ~all-decided and must render."""
    pool = [(row(p), market(v)) for p, v in [(98, 4), (2, None), (50, 9), (97, 50_000)]]
    assert len(rank(pool)) == 4


def test_an_all_thin_section_still_fills_its_slice():
    """Every row below the floor: a deleting floor renders this section blank."""
    pool = [(row(p), market(4)) for p in (50, 60, 97, 98)]
    served = rank(pool)[:10]
    assert len(served) == 4
    assert served[0]["prob"] == 50


# --------------------------------------------------------------------------
# Arity: distance from 50 is only the binary answer
# --------------------------------------------------------------------------

def test_a_three_way_at_98_is_as_settled_as_a_binary_at_98():
    """Where every 98% Gubernatorial card came from — the guard never saw them.

    `outcome_count <= 2 and prob > 95` is scoped to binaries, so Idaho (3
    outcomes, 97.9%) and Illinois (3 outcomes, 97.7%) sail through a guard
    written to catch exactly them. Ranking is what stops them leading.
    """
    three_way = _decidedness(row(97.9, outcome_count=3))
    binary = _decidedness(row(97.9, outcome_count=2))
    assert three_way == pytest.approx(binary, abs=0.05)
    assert three_way > 0.9


def test_a_flat_field_is_open_however_low_its_leader_sits():
    """629's finding: the cure must not reproduce the defect it cures.

    A five-way whose leader is at 2.1% is a perfectly flat field. `abs(p - 50)`
    scores it 47.9 — indistinguishable from a settled 97.9% — and a bare sign
    flip would therefore rank it LAST, which is #7251's own SCOTUS complaint.
    """
    flat_five = row(2.1, outcome_count=5)
    flat_seventeen = row(34.5, outcome_count=17)
    decided_three = row(97.9, outcome_count=3)

    assert _decidedness(flat_five) < 0.1
    assert _decidedness(flat_seventeen) < 0.5
    assert rank([
        (decided_three, market()),
        (flat_seventeen, market()),
        (flat_five, market()),
    ])[-1] is decided_three


def test_a_wider_field_is_not_scored_as_more_decided_than_a_narrow_one():
    """A flat 3-way and a flat 15-way are equally open — both floor at 0.0."""
    assert _decidedness(row(100 / 3, outcome_count=3)) == pytest.approx(0.0, abs=0.01)
    assert _decidedness(row(100 / 15, outcome_count=15)) == pytest.approx(0.0, abs=0.01)


def test_a_leader_beneath_a_flat_field_is_open_not_negatively_decided():
    """The clamp. A stale rung can price a leader below `100/n`."""
    assert _decidedness(row(1.0, outcome_count=5)) == 0.0


def test_the_low_tail_is_demoted_and_it_is_a_one_sided_contract():
    """629's fixture trap, pinned so the next reader does not rebuild it wrong.

    12 of entertainment's 14 sub-5% rows carry `outcome_count == 1` — one-sided
    Kalshi "Yes" contracts. A two-sided binary written at 2% is SERVED as its
    98% side, because `_market_row` takes `priced[0]` after sorting descending.
    So the specimen for the `<5` tail is arity 1, not arity 2, and a fixture
    that builds it as a two-outcome market is testing a row the page never
    serves.
    """
    one_sided_no = row(2.0, outcome_count=1)
    assert _decidedness(one_sided_no) > 0.9
    assert rank([(one_sided_no, market()), (row(55.0), market())])[-1] is one_sided_no


# --------------------------------------------------------------------------
# The volume floor: degenerate rows sink, unknown volume fails open
# --------------------------------------------------------------------------

def test_a_four_contract_market_does_not_outrank_a_traded_one():
    """The measured reason the floor exists.

    The gap is deliberately narrow — 50% against 60% — so that only the floor
    can produce this order. The thin row is the MORE open of the two, so a key
    that ignored volume would rank it first.
    """
    thin_and_open = (row(50.0), market(4))
    traded = (row(60.0), market(11_031))
    assert rank([thin_and_open, traded])[0] is traded[0]


def test_an_unknown_volume_fails_open():
    """`volume` is NULL on 6 of the 60 served rows; reading NULL as 0 sinks them.

    California AG, North Dakota SoS, Alabama AG, the Italy referendum, Maine
    HD-94 and a Thailand row — demoted on no evidence. Same narrow gap as
    above, so the arms separate.
    """
    unknown_and_open = (row(50.0), market(None))
    traded = (row(60.0), market(11_031))
    assert rank([unknown_and_open, traded])[0] is unknown_and_open[0]
    assert _never_really_traded(market(None)) is False


def test_the_floor_sits_in_the_gap_the_distribution_actually_has():
    """min 4 · 5 · 9 · then nothing until 127 · 146 · 200 · 269 · 395.

    Every floor in [10, 127) yields the identical partition, which is why the
    threshold is not a tuned parameter. The motivating specimen — the SCOTUS
    row at 395 — must clear it with room to spare.
    """
    assert all(_never_really_traded(market(v)) for v in (4, 5, 9))
    assert not any(_never_really_traded(market(v)) for v in (127, 146, 200, 269, 395))


def test_a_traded_zero_is_not_the_same_as_an_unknown():
    """`volume=0` is data — the market says nothing ever traded. NULL is absence."""
    assert _never_really_traded(market(0)) is True
    assert _never_really_traded(market(None)) is False


def test_a_market_object_with_no_volume_attribute_at_all_fails_open():
    """An absent attribute is absence of data, like a NULL — never a refusal."""
    assert _never_really_traded(SimpleNamespace()) is False


def test_the_volume_column_the_floor_reads_still_exists():
    """The arm that stops the `getattr` default becoming the production path.

    `_never_really_traded` reads `volume` through `getattr(..., None)` so that
    a market object without the attribute fails open. If the column were ever
    renamed or dropped, every row would silently read as "traded" and the floor
    would become a no-op with no test failing anywhere — so the column's
    existence is asserted here rather than assumed.
    """
    from app.models import FuturesMarket

    assert "volume" in FuturesMarket.__table__.columns


# --------------------------------------------------------------------------
# The binding arm: both call sites actually spend the key
# --------------------------------------------------------------------------

def test_no_sort_in_politics_is_keyed_on_distance_from_50():
    """`ast`, not a regex — a non-greedy `\\(...\\)` truncates a nested call.

    This is the arm that makes the behavioural arms above mean anything. A
    call site left on the old key does not raise; it silently keeps serving
    the wall, and no payload assertion in this file would notice.
    """
    tree = ast.parse(inspect.getsource(politics_module))

    offenders = []
    keyed_by_uncertainty = 0

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        key = next((k.value for k in node.keywords if k.arg == "key"), None)
        if key is None:
            continue
        src = ast.unparse(key)
        # NO PRE-FILTER ON `"prob"`, and the first draft of this guard had one.
        # It read 0 of 2 call sites, because the key they spend is
        # `lambda rm: _by_uncertainty(*rm)` — the word `prob` lives inside the
        # helper, not at the call site. A guard narrowed to the shape of the
        # code it was written against passes the moment that shape changes.
        if "_by_uncertainty" in src:
            keyed_by_uncertainty += 1
            continue
        if "abs(" in src and "50" in src:
            offenders.append(src)

    assert offenders == [], (
        "a probability sort is still keyed on distance from 50 — #7251 is the "
        f"defect that key causes: {offenders}"
    )
    assert keyed_by_uncertainty >= 2, (
        "expected both #7251 call sites (`build_section` and `side_markets`) to "
        f"sort through `_by_uncertainty`, found {keyed_by_uncertainty}"
    )
