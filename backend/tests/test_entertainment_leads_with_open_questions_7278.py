"""#7278 — /entertainment leads with questions still open, not a wall of settled ones.

THE READER'S COMPLAINT, from a production LOOK at phone width on 2026-09-19
18:20Z (`artifacts/latency-628/BEFORE-entertainment-most-decided-first-1820Z.png`,
banked with the payload it was read against). A page headlined "Live
probabilities on charts, box office, reality TV, and the moments breaking the
internet" served, top to bottom:

    Pop culture prediction feed   98, 98, 98, 98, 2, 98, 97, 98, 96, 98 …
    Critic scores / box office     2, 98, 98, 98, 98 …
    Tech & Culture                 2%, 2%, 2%, 4%, 5%, 6%, 7% …

Measured on that payload: `cultural_moments` **20 of 20** rows >95% or <5%, and
`movies_tv.side_markets` **10 of 10**. Both tails lead, because the key was
`-abs(prob - 50)` — distance from 50 DESCENDING, which ranks a 2% market level
with a 98% one and both above a 45% one.

THE SORT IS A SELECTOR, NOT AN ORDERER, and that is the part the screenshot
cannot show. Every one of the three sites is followed by a slice, and the pools
dwarf the caps — the same payload served `themes.movies_tv.count = 505`
candidates for `side_markets[:10]`, `music.count = 253` for `[:12]`, and
`tech_culture.count = 58` for `[:15]`. So the comparator does not merely order
the wall; it CHOOSES it, dropping the open questions out of the payload
entirely. That is why these tests assert over pools larger than the cap: a test
that sorts exactly `cap` rows would pass on a fix that changed nothing a reader
can reach.

WHY THE `_is_interesting` GUARD IS NOT WIDENED HERE, stated so a later reader
does not "finish the job". The guard at line 302 is asymmetric — it drops
`outcome_count <= 2 and prob > 95`, so it catches neither the `<5` tail nor the
multi-outcome 98s, which is where the 20/20 feed comes from. Widening it to
drop both tails DELETES rows, and `cultural_moments` was 20-of-20 decided on the
measured day: a symmetric drop could empty the section, a state that page has
never rendered. Ranking demotes without deleting and degrades gracefully — a
section holding nothing but settled markets still shows them rather than going
blank. The page's own `_score_for_trending` is the precedent: it carries no
symmetric guard either, scores `(50 - abs(prob - 50))`, and served **0 of 5**
decided rows on the same payload where its siblings served 20/20 and 10/10.

WHAT WOULD MAKE THIS FILE VACUOUS, stated so a later reader can check it:
these are all assertions that uncertain rows come FIRST, and a builder that
returned nothing, or that dropped every decided row, would satisfy every one of
them. Two controls answer that. `test_the_retired_comparator_fails_this_file`
re-runs the selection assertion under the old key and requires it to FAIL — if
that test ever passes, the rest of this file is measuring nothing. And
`test_a_settled_market_is_still_served_when_it_is_all_there_is` pins the
no-deletion half: the fix ranks, it does not filter.

MUTATION-TESTED against five rewrites of the production key, all of which this
file kills: reverting to `-abs(prob - 50)`; dropping the arity branch for a bare
distance-from-50; removing the volume tiebreak; promoting volume from a tiebreak
to a weight; and unclamping the multi-outcome branch. The last two survived the
first draft — `test_volume_cannot_overturn_even_a_narrow_openness_gap` and
`test_leaders_below_the_flat_baseline_tie_at_wide_open` are the specimens added
to kill them, and the note in the first of those records why the obvious version
of that assertion is blind.
"""

import itertools
from types import SimpleNamespace

import pytest

#: #8083: `_market_row` reads `o.id` for the per-outcome price refusal.
_OUTCOME_IDS = itertools.count(1)

from app.routes.entertainment import (
    _build_cultural,
    _build_list,
    _by_uncertainty,
    _decidedness,
)

def _retired_key(row: dict) -> float:
    """The key this replaced, verbatim, so the control below runs the real thing."""
    return -abs(row["prob"] - 50)


def _market(name: str, prob: float, *, volume_24h=None, outcome_count: int = 1):
    """A FuturesMarket-shaped stand-in `_market_row` will serve.

    `prob` is the LEADER's probability, and `_market_row` takes the leader by
    sorting the outcomes descending — so every other outcome here is priced
    below `prob`. That is not fixture convenience, it is the shape of the real
    data: of the 14 sub-5% rows on the measured payload, **12 carry
    `outcome_count == 1`** (a one-sided Kalshi "Yes" contract). A two-sided
    binary written at 2% would be served as its 98% side, so the low tail
    cannot be built that way.

    The remaining outcomes split what is left of the book, which keeps the
    ladder a plausible one and `outcome_count` honest.
    """
    # #8083: `_market_row` reads `o.id` for the per-outcome price refusal.
    leader = SimpleNamespace(
        id=next(_OUTCOME_IDS),
        name=f"{name} — yes",
        current_probability=prob / 100.0,
        probability_change_24h=0.0,
    )
    others = max(outcome_count - 1, 0)
    rest = [
        SimpleNamespace(
            id=next(_OUTCOME_IDS),
            name=f"{name} — other {i}",
            # Strictly below the leader, so `priced[0]` is the leader.
            current_probability=min(prob, (100 - prob) / others) / 100.0,
            probability_change_24h=0.0,
        )
        for i in range(others)
    ]
    return SimpleNamespace(
        id=abs(hash((name, prob))) % 10**6,
        name=name,
        source="kalshi",
        external_id=f"TEST-{abs(hash(name)) % 10**6}",
        outcomes=[leader, *rest],
        volume_24h=volume_24h,
        image_url=None,
        resolution_date=None,
        updated_at=None,
        hook_description=None,
        hook_generated_at=None,
        hook_leader_at_generation=None,
        market_metadata=None,
    )


def _probs(rows):
    return [r["prob"] for r in rows]


def _settled(row: dict) -> bool:
    """Is this row a foregone conclusion, as a READER would judge it?

    Written out independently of `_decidedness` rather than calling it, so
    these tests state the intent and would catch the production key being
    rewritten to something that merely agrees with itself.
    """
    prob, oc = row["prob"], row["outcome_count"]
    if oc <= 2:
        return prob > 95 or prob < 5
    # On a field of n, a low leader is a wide-open race, not a settled one.
    return prob > 95


# ---------------------------------------------------------------------------
# The ship: an over-cap pool serves its open questions, not its settled ones.
# ---------------------------------------------------------------------------


def _over_cap_pool():
    """40 markets for a 12-slot section: 12 open, 28 settled across BOTH tails.

    The settled rows are deliberately built in the two shapes the real page
    serves them in — one-sided contracts pinned at each tail, and multi-outcome
    "Winner" ladders at 96-99%, which is where all 35 of the measured
    near-certainties came from and which `_is_interesting` cannot see.
    """
    open_qs = [
        _market(f"open-{i}", p)
        for i, p in enumerate([48, 52, 45, 55, 41, 59, 38, 62, 35, 65, 30, 70])
    ]
    settled_high = [
        _market(f"settled-high-{i}", 96 + (i % 4), outcome_count=3)
        for i in range(14)
    ]
    settled_low = [_market(f"settled-low-{i}", 4 - (i % 4)) for i in range(14)]
    return [*settled_high, *settled_low, *open_qs]


def test_the_comparator_selects_the_open_questions_out_of_an_over_cap_pool():
    served = _build_list(_over_cap_pool(), limit=12)

    assert len(served) == 12
    assert [r["prob"] for r in served if _settled(r)] == [], (
        "a settled market reached a 12-slot section while 12 open questions "
        f"waited in the pool: {_probs(served)}"
    )


def test_cultural_moments_selects_open_questions_from_its_own_pool():
    """`_build_cultural` is the 20-of-20 section the reader photographed."""
    pool = _over_cap_pool() + [
        _market(f"extra-settled-{i}", 97, outcome_count=4) for i in range(20)
    ]
    themed = {"awards": pool, "celebrity": [], "viral": [], "other": []}

    served = _build_cultural(themed)

    assert len(served) == 20
    # Twelve open questions exist in a pool of sixty. They must take the first
    # twelve slots; the remaining eight fall back to the least-settled of the
    # rest, which is the no-deletion half of the fix.
    assert not any(_settled(r) for r in served[:12]), (
        f"the open questions did not lead the cultural feed: {_probs(served)}"
    )


def test_both_tails_of_a_binary_are_demoted_not_just_the_high_one():
    """The old guard tested `prob > 95` only; on a one-sided contract 2% means
    "almost certainly no" and is exactly as settled as 98%.
    """
    served = _build_list(
        [
            _market("settled-low", 2),
            _market("settled-high", 98),
            _market("still-open", 45),
        ],
        limit=3,
    )

    assert served[0]["prob"] == 45, (
        f"a settled market outranked the open question: {_probs(served)}"
    )
    assert all(_settled(r) for r in served[1:])


def test_a_multi_outcome_near_certainty_is_demoted():
    """`outcome_count > 2` at 98% is where every card in the 20-of-20 feed came
    from, and `_is_interesting`'s `outcome_count <= 2` clause cannot see it.
    """
    served = _build_list(
        [
            _market("settled-multi", 98, outcome_count=5),
            _market("still-open", 47),
        ],
        limit=2,
    )

    assert served[0]["prob"] == 47, f"98% led a section: {_probs(served)}"


def test_a_wide_field_with_a_low_leader_is_an_open_question_not_a_settled_one():
    """The correction distance-from-50 gets wrong, and the reason `_decidedness`
    branches on arity at all.

    "Big Brother Season 28 · Winner" is seventeen-way with its leader at 34.5%,
    and "Who will Elon Musk back a primary against in 2026?" is five-way at
    2.1%. Both are as open as a question gets. A bare `abs(prob - 50)` flip
    scores them 15.5 and 47.9 and buries the second one last — which is #7251's
    SCOTUS complaint reproduced by the fix meant to cure it.
    """
    served = _build_list(
        [
            _market("settled-multi-winner", 97, outcome_count=17),
            _market("elon-primary", 2.1, outcome_count=5),
            _market("big-brother-winner", 34.5, outcome_count=17),
        ],
        limit=3,
    )

    assert [r["prob"] for r in served[:2]] == [2.1, 34.5], (
        f"a wide-open field was ranked as settled: {_probs(served)}"
    )
    assert served[2]["prob"] == 97


def test_a_flat_field_scores_the_same_regardless_of_how_wide_it_is():
    """A three-way toss-up and a fifteen-way toss-up are both wide open, so the
    arity branch is normalised against the flat baseline rather than against 0.
    """
    flat_3 = _decidedness({"prob": 100 / 3, "outcome_count": 3})
    flat_15 = _decidedness({"prob": 100 / 15, "outcome_count": 15})

    assert flat_3 == pytest.approx(0.0, abs=1e-9)
    assert flat_15 == pytest.approx(0.0, abs=1e-9)


def test_a_near_certainty_scores_the_same_on_either_branch():
    """The two branches must be on ONE scale — they are sorted in one list."""
    binary = _decidedness({"prob": 97.9, "outcome_count": 2})
    three_way = _decidedness({"prob": 97.9, "outcome_count": 3})

    assert binary == pytest.approx(0.958, abs=0.01)
    assert three_way == pytest.approx(0.969, abs=0.01)


# ---------------------------------------------------------------------------
# volume_24h orders ties. It never gates.
# ---------------------------------------------------------------------------


def test_volume_breaks_a_tie_between_equally_open_questions():
    served = _build_list(
        [
            _market("thin", 50, volume_24h=4),
            _market("traded", 50, volume_24h=11031),
        ],
        limit=2,
    )

    assert [r["volume_24h"] for r in served] == [11031, 4]


def test_an_untraded_open_question_still_outranks_a_heavily_traded_settled_one():
    """The floor question, answered. `volume_24h` is null on 49 of the 115
    served rows — 13 of the 20 in the worst section — so gating or weighting on
    it would rank most of the page on missing data. It is a tiebreak only, and
    must never lift a settled market over an open one.
    """
    served = _build_list(
        [
            _market("settled-but-busy", 98, volume_24h=11031),
            _market("open-but-untraded", 50, volume_24h=None),
        ],
        limit=2,
    )

    assert served[0]["prob"] == 50 and served[0]["volume_24h"] is None


def test_volume_cannot_overturn_even_a_narrow_openness_gap():
    """A tiebreak, not a weight — and the gap here is deliberately narrow.

    The obvious version of this test (an untraded 50% against a traded 98%) is
    blind: any sane volume weight is too small to bridge that much decidedness,
    so it passes whether volume is a tiebreak or a weight. These two rows are
    0.2 apart, which a `min(volume/1000, 50)`-shaped weight WOULD overturn —
    and overturning it is the failure mode the null coverage forbids, because
    the 49 of 115 rows carrying no volume would be demoted wholesale.
    """
    served = _build_list(
        [
            _market("slightly-less-open-but-busy", 60, volume_24h=11031),
            _market("most-open-but-untraded", 50, volume_24h=None),
        ],
        limit=2,
    )

    assert served[0]["prob"] == 50, (
        "volume outranked openness, so it is acting as a weight rather than a "
        f"tiebreak: {[(r['prob'], r['volume_24h']) for r in served]}"
    )


def test_leaders_below_the_flat_baseline_tie_at_wide_open():
    """The clamp's observable behaviour. Two fields whose leaders sit below
    their own flat baseline are both simply "as open as it gets" — they tie at
    0.0 and `volume_24h` orders them, rather than the arithmetic inventing a
    ranking between two equally open races.
    """
    five_way = {"prob": 2.1, "outcome_count": 5, "volume_24h": None}
    fifteen_way = {"prob": 3.5, "outcome_count": 15, "volume_24h": None}

    assert _decidedness(five_way) == 0.0
    assert _decidedness(fifteen_way) == 0.0
    assert _by_uncertainty(five_way)[0] == _by_uncertainty(fifteen_way)[0]


def test_a_null_volume_sorts_last_within_a_tie_and_no_further():
    keyed = sorted(
        [
            {"prob": 50.0, "outcome_count": 1, "volume_24h": None},
            {"prob": 50.0, "outcome_count": 1, "volume_24h": 7},
            {"prob": 90.0, "outcome_count": 1, "volume_24h": 99999},
        ],
        key=_by_uncertainty,
    )

    assert [r["volume_24h"] for r in keyed] == [7, None, 99999]


# ---------------------------------------------------------------------------
# Controls.
# ---------------------------------------------------------------------------


def test_the_retired_comparator_fails_this_file():
    """The strawman guard. If this passes, every assertion above is vacuous."""
    pool_rows = [
        {"prob": p, "outcome_count": 1, "volume_24h": None}
        for p in [98, 97, 96, 2, 3, 4, 48, 52, 45]
    ]

    old_first = sorted(pool_rows, key=_retired_key)[:3]
    new_first = sorted(pool_rows, key=_by_uncertainty)[:3]

    assert all(_settled(r) for r in old_first), (
        "the retired key no longer leads with settled markets, so it is not "
        "the defect this file was written against"
    )
    assert not any(_settled(r) for r in new_first)


def test_a_settled_market_is_still_served_when_it_is_all_there_is():
    """The fix RANKS, it does not filter — a section holding nothing but
    settled markets still renders rather than going blank. This is the reason
    `_is_interesting` was left asymmetric; see the module docstring.
    """
    served = _build_list(
        [_market(f"settled-{i}", 97, outcome_count=3) for i in range(5)],
        limit=12,
    )

    assert len(served) == 5


def test_every_section_builder_uses_the_shared_key():
    """Wiring, not semantics: a future edit that reverts one of the three call
    sites to its own lambda would leave the tests above green for the sites it
    did not touch.
    """
    import inspect

    from app.routes import entertainment

    src = inspect.getsource(entertainment)

    assert "-abs(r[\"prob\"] - 50)" not in src, (
        "the retired comparator is back at one of the section builders"
    )
    assert src.count("key=_by_uncertainty") == 3, (
        "expected exactly three section builders on the shared sort key "
        "(_build_list, _build_cultural side markets, _build_cultural)"
    )
