"""#5105 D2 — the variety-promotion hook and the two offline arms.

``diversify_discover_first_page`` grew an opt-in ``promotion_gate`` /
``promotion_trace`` so the offline replay can compare two definitions of "a card
may be promoted for variety" on one retained capture (``discover_display_replay``
``d2_arm_a`` / ``d2_arm_b``). Production passes neither, so the first and widest
guard here is that the hook is inert: no gate, a trace alone, and the observer
gate all return the served order over a corpus that provably fires every
mechanism the hook touches.

The boundary controls then pin what a gate may and may not do: a rank-earned
seat is never asked about; a refused promotion yields to the mechanism's own
next candidate or fallback, never to a forced weak card; and the page keeps its
length. The arm predicates are read from the shared oracles
(``_is_clean_replacement_for``, ``lacks_a_why_now``) and the served bars, never
restated.
"""

from __future__ import annotations

import random

import pytest

from app.utils import discover_display_replay as ddr
from app.utils import feed_market_quality as fmq
from app.utils.feed_market_quality import _feed_item_key, diversify_discover_first_page

WHY = "Up 12 points since Sep 2"


def _f(
    card_id,
    category: str,
    score: float,
    *,
    why: bool = True,
    ladder: bool = False,
    quality: str = "normal",
    name: str | None = None,
) -> dict:
    caption = WHY if why else f"{card_id} leads at 40%"
    return {
        "type": "futures",
        "score": score,
        "_rank_score": float(score),
        "headline": caption,
        "reason": caption,
        "context_summary": caption,
        "_quality_class": quality,
        "_quality_ladder_or_bucket": ladder,
        "data": {
            "id": card_id,
            "name": name or f"Question {card_id}?",
            "llm_sport_category": category,
            "hook_description": None,
        },
    }


def _ids(items):
    return [it["data"]["id"] for it in items]


def _gate(policy):
    return ddr.d2_promotion_gate(policy)


A = ddr.STAGE_POLICY_D2_ARM_A
B = ddr.STAGE_POLICY_D2_ARM_B
OBSERVER = ddr.STAGE_POLICY_D2_BASELINE_TRACE


# --------------------------------------------------------------------------- #
# The hook is inert by default — over a corpus that fires every mechanism
# --------------------------------------------------------------------------- #

_NAMES = [
    ("Best AI model at end of 2026?", "tech"),
    ("Will Elon Musk tweet 100 times?", "tech"),
    ("Grammys 2027: Album of the Year Winner", "entertainment"),
    ("Taylor Swift engaged?", "entertainment"),
    ("Will it snow in Buffalo by October 31?", "weather"),
    ("Will Bill Belichick be fired as coach?", "football"),
    ("Florida man arrested for alligator?", "other"),
    ("Will China invade Taiwan by 2027?", "geopolitics"),
    ("Fed decision in Oct 2026?", "economics"),
    ("Largest IPO by market cap in 2026?", "economics"),
    ("2028 U.S. Presidential Election winner?", "politics"),
    ("Senate control after the midterms?", "politics"),
]


def _random_pool(rng: random.Random) -> list[dict]:
    pool = []
    # Some pools lean political so the top-ten texture repair has work to do.
    weights = [1] * len(_NAMES)
    if rng.random() < 0.4:
        weights = [6 if cat in ("politics", "geopolitics") else 1 for _, cat in _NAMES]
    for i in range(rng.randint(18, 40)):
        name, category = rng.choices(_NAMES, weights=weights)[0]
        pool.append(
            _f(
                f"c{i}",
                category,
                rng.choice([98, 95, 93, 91, 90, 89, 88, 85, 80, 74, 60, 45, 30]),
                why=rng.random() < 0.6,
                ladder=rng.random() < 0.15,
                name=f"{name} #{i}",
            )
        )
        if rng.random() < 0.1:
            pool[-1]["_quality_story_key"] = f"story{rng.randint(0, 2)}"
    if rng.random() < 0.5:
        pool.append(
            {
                "type": "event",
                "score": rng.choice([95, 60, 35]),
                "headline": "",
                "reason": "",
                "data": {"id": f"e{rng.random()}"},
            }
        )
    # The chain's rank order is not the display score the bars read; noise
    # lets a high-score card arrive late, which is when hunger/archetype fill.
    pool.sort(key=lambda it: it["score"] + rng.gauss(0, 20), reverse=True)
    shape = rng.random()
    if shape < 0.3:
        # A strong card from a category the page otherwise lacks, ranked last.
        name, category = rng.choice(
            [
                n
                for n in _NAMES
                if n[1] in ("tech", "entertainment", "weather", "economics")
            ]
        )
        group = fmq._discover_category_group(_f("x", category, 0))
        pool = [it for it in pool if fmq._discover_category_group(it) != group]
        pool.append(
            _f(
                "late",
                category,
                rng.choice([95, 91, 85]),
                why=rng.random() < 0.6,
                name=f"{name} late",
            )
        )
    elif shape < 0.6:
        # A political head, then strong non-political cards inside the page.
        head = [
            _f(
                f"h{i}",
                rng.choice(["politics", "geopolitics"]),
                98 - i,
                name=f"Senate control after the midterms? h{i}",
            )
            for i in range(8)
        ]
        body = [
            _f(
                f"b{i}",
                rng.choice(["tech", "economics", "entertainment"]),
                93,
                why=rng.random() < 0.6,
                name=f"{rng.choice(_NAMES)[0]} b{i}",
            )
            for i in range(6)
        ]
        pool = head + body + pool
    return pool


def test_no_gate_a_trace_alone_and_the_observer_gate_all_serve_the_same_order():
    rng = random.Random(5105)
    fired: set[str] = set()
    for _ in range(400):
        pool = _random_pool(rng)
        cold = rng.random() < 0.7
        served = diversify_discover_first_page(list(pool), cold_start=cold)
        trace: list = []
        traced = diversify_discover_first_page(
            list(pool), cold_start=cold, promotion_trace=trace
        )
        observed_trace: list = []
        observed = diversify_discover_first_page(
            list(pool),
            cold_start=cold,
            promotion_gate=_gate(OBSERVER),
            promotion_trace=observed_trace,
        )
        assert [_feed_item_key(i) for i in traced] == [
            _feed_item_key(i) for i in served
        ]
        assert [_feed_item_key(i) for i in observed] == [
            _feed_item_key(i) for i in served
        ]
        fired |= {e["mechanism"] for e in trace if e["event"] == "promotion"}
    # Not vacuous: these mechanisms each made decisions in the corpus. The
    # strict-variety swaps need a political top ten that the real archetype
    # caps make rare at random; they are pinned on constructed pages below.
    assert {"cap_walk", "required_archetype", "category_hunger"} <= fired, fired


# --------------------------------------------------------------------------- #
# Boundary controls
# --------------------------------------------------------------------------- #


def test_a_rank_earned_seat_is_never_put_to_the_gate():
    asked: list = []

    def refuse_everything(card, **kw):
        asked.append(card["data"]["id"])
        return False, {}

    pool = [_f("L", "economics", 98, ladder=True), _f("X", "tech", 90)]
    out = diversify_discover_first_page(pool, promotion_gate=refuse_everything)
    assert _ids(out)[:2] == ["L", "X"]
    assert asked == []


def _cold_pool():
    # P3 is refused by the cold-start cap of 2; everything below it that is
    # seated before P3 returns is a cap promotion.
    return [
        _f("P1", "politics", 98),
        _f("P2", "politics", 97),
        _f("P3", "politics", 96),
        _f("L", "economics", 90, ladder=True),
        _f("Q", "economics", 88, why=False),
        _f("C", "tech", 92),
        _f("U", "politics", 40),
    ]


def test_arm_a_refuses_an_unclean_cap_promotion_and_keeps_the_page_whole():
    served = diversify_discover_first_page(
        _cold_pool(), first_page_size=5, cold_start=True
    )
    assert _ids(served)[:4] == ["P1", "P2", "L", "Q"]

    trace: list = []
    arm = diversify_discover_first_page(
        _cold_pool(),
        first_page_size=5,
        cold_start=True,
        promotion_gate=_gate(A),
        promotion_trace=trace,
    )
    # The ladder and the reasonless card do not jump the capped P3 into the
    # first ten; the clean tech card does. The page keeps its length and the
    # refused cards stay in the feed (nothing is dropped).
    assert _ids(arm)[:3] == ["P1", "P2", "C"]
    assert len(arm) == len(served)
    assert set(_ids(arm)) == set(_ids(served))
    refused = {
        e["card"]["data"]["id"]
        for e in trace
        if e["event"] == "promotion" and not e["allowed"]
    }
    assert {"L", "Q"} <= refused
    seat = next(
        e for e in trace if e["event"] == "seat" and e["card"]["data"]["id"] == "C"
    )
    assert seat["kind"] == "cap_promotion"
    assert seat["deferred"]["data"]["id"] == "P3"
    assert seat["cause"] == "cold_start_category_cap"


def test_arm_b_never_promotes_an_unbarred_card_but_it_keeps_ranked_seats():
    # U (politics, clean, why-now) is unbarred: A may promote it, B may not.
    card = _f("U", "politics", 97)
    ok_a, checks = _gate(A)(card, slot=12, mechanism="cap_walk", existing_bar=None)
    ok_b, _ = _gate(B)(card, slot=12, mechanism="cap_walk", existing_bar=None)
    assert ok_a and not ok_b
    assert checks["defined_bar"] is None and checks["defined_bar_ok"] is False
    # ...and the same unbarred card at the top of the pool is still seated.
    out = diversify_discover_first_page(
        [card, _f("T", "tech", 50)], promotion_gate=_gate(B)
    )
    assert _ids(out)[0] == "U"


@pytest.mark.parametrize("score,allowed", [(89, False), (90, True)])
def test_arm_b_reads_the_served_tech_bar(score, allowed):
    card = _f("T", "tech", score)
    assert ddr.d2_defined_bar(card) == fmq.DISCOVER_CATEGORY_HUNGER_THRESHOLDS["tech"]
    ok, _ = _gate(B)(card, slot=12, mechanism="cap_walk", existing_bar=None)
    assert ok is allowed


def test_the_defined_bar_is_the_higher_of_the_category_and_archetype_bars(monkeypatch):
    monkeypatch.setattr(fmq, "_discover_archetype_group", lambda item: "culture_moment")
    card = _f("N", "entertainment", 85)
    assert fmq.DISCOVER_CATEGORY_HUNGER_THRESHOLDS["entertainment"] == 80
    assert ddr.d2_defined_bar(card) == fmq.DISCOVER_REQUIRED_ARCHETYPE_MIN_SCORE == 90


def test_the_gate_reads_the_shared_oracles_never_a_copy():
    cards = [
        _f("w", "tech", 95),
        _f("r", "tech", 95, why=False),
        _f("l", "tech", 95, ladder=True),
        _f("q", "tech", 95, quality="low_quality"),
        {"type": "event", "score": 95, "headline": "", "reason": "", "data": {"id": 9}},
        {
            "type": "bundle",
            "score": 95,
            "headline": "",
            "reason": "",
            "data": {"id": "b", "items": [_f("m", "tech", 90, why=False)]},
        },
    ]
    for policy in (A, B):
        gate = _gate(policy)
        for card in cards:
            for slot in (0, 9, 10, 19):
                ok, c = gate(card, slot=slot, mechanism="cap_walk", existing_bar=None)
                assert c["clean_replacement"] == fmq._is_clean_replacement_for(
                    card, position=slot, why_now_window=fmq.FIRST_PAGE_WHY_NOW_WINDOW
                )
                assert c["why_now_twenty_ok"] == (not fmq.lacks_a_why_now(card))
                assert ok == c["a_allowed" if policy == A else "b_allowed"]


def test_b_adds_the_type_scoped_why_now_past_slot_ten_and_a_does_not():
    reasonless = _f("r", "tech", 95, why=False)
    assert _gate(A)(reasonless, slot=12, mechanism="cap_walk", existing_bar=None)[0]
    assert not _gate(B)(reasonless, slot=12, mechanism="cap_walk", existing_bar=None)[0]
    # Inside the first ten, A already refuses it (the served promotion rule).
    assert not _gate(A)(reasonless, slot=3, mechanism="cap_walk", existing_bar=None)[0]
    # The clause-(d) check is futures/bundle only: a game card is never judged
    # reasonless past slot ten for want of futures copy.
    game = {
        "type": "event",
        "score": 95,
        "headline": "",
        "reason": "",
        "data": {"id": 9},
    }
    assert _gate(B)(game, slot=12, mechanism="cap_walk", existing_bar=None)[1][
        "why_now_twenty_ok"
    ]


def test_a_refused_hunger_candidate_yields_to_the_next_and_none_means_no_swap():
    selected = [_f(f"p{i}", "politics", 95) for i in range(6)]
    first = _f("E1", "entertainment", 85, why=False)
    second = _f("E2", "entertainment", 82)
    pool = selected + [first, second]

    served = list(selected)
    fmq._ensure_category_hunger(served, pool)
    assert "E1" in _ids(served)

    gated = list(selected)
    fmq._ensure_category_hunger(gated, pool, gate=_gate(A))
    assert "E2" in _ids(gated) and "E1" not in _ids(gated)

    untouched = list(selected)
    fmq._ensure_category_hunger(untouched, selected + [first], gate=_gate(A))
    assert _ids(untouched) == _ids(selected)


def test_a_refused_required_archetype_candidate_yields_to_the_next(monkeypatch):
    archetypes = {"W1": "health_weather_risk", "W2": "health_weather_risk"}
    monkeypatch.setattr(
        fmq,
        "_discover_archetype_group",
        lambda item: archetypes.get(item["data"]["id"], "political_power"),
    )
    monkeypatch.setattr(fmq, "_DISCOVER_REQUIRED_ARCHETYPES", ("health_weather_risk",))
    selected = [_f(f"p{i}", "politics", 95) for i in range(6)]
    pool = selected + [_f("W1", "weather", 95, ladder=True), _f("W2", "weather", 91)]

    served = list(selected)
    fmq._ensure_required_archetypes(served, pool)
    assert "W1" in _ids(served)

    gated = list(selected)
    fmq._ensure_required_archetypes(gated, pool, gate=_gate(A))
    assert "W2" in _ids(gated) and "W1" not in _ids(gated)


def test_a_refused_strict_top10_swap_leaves_the_page_order_alone():
    top = [_f(f"p{i}", "politics", 95) for i in range(10)]
    tail = [_f("T1", "tech", 95, ladder=True)] + [
        _f(f"z{i}", "politics", 60) for i in range(9)
    ]
    served = top + tail
    fmq._improve_strict_variety(served, served)
    assert "T1" in _ids(served[:10])

    observed, trace = top + tail, []
    fmq._improve_strict_variety(observed, observed, gate=_gate(OBSERVER), trace=trace)
    assert _ids(observed) == _ids(served)
    assert {e["mechanism"] for e in trace} >= {"strict_top10_non_political"}

    gated = top + tail
    fmq._improve_strict_variety(gated, gated, gate=_gate(A))
    assert _ids(gated[:10]) == _ids(top)


@pytest.mark.parametrize("in_page", [True, False])
def test_the_fun_card_repair_is_unmoved_by_the_observer_and_gated_by_a(in_page):
    fun = _f(
        "F",
        "entertainment",
        90,
        why=False,
        name="Grammys 2027: Album of the Year Winner",
    )
    top = [
        _f(f"m{i}", "economics", 95, name=f"Fed decision in Oct 2026? {i}")
        for i in range(10)
    ]
    tail = [
        _f(f"z{i}", "economics", 60, name=f"Fed decision in Oct 2026? z{i}")
        for i in range(9)
    ]
    page = top + ([fun] + tail if in_page else tail + [_f("z9", "economics", 60)])
    pool = page if in_page else page + [fun]

    served = list(page)
    fmq._improve_strict_variety(served, pool)
    assert "F" in _ids(served[:10])

    observed, trace = list(page), []
    fmq._improve_strict_variety(observed, pool, gate=_gate(OBSERVER), trace=trace)
    assert _ids(observed) == _ids(served)
    assert any(e["mechanism"].startswith("strict_fun_card") for e in trace)

    # A reasonless futures card may not be promoted into the first ten.
    gated = list(page)
    fmq._improve_strict_variety(gated, pool, gate=_gate(A))
    assert "F" not in _ids(gated[:10])


def test_an_unknown_d2_policy_refuses():
    with pytest.raises(ddr.DisplayReplayError):
        ddr.d2_promotion_gate("d2_arm_c")


@pytest.mark.parametrize("policy", [None, A])
def test_hunger_still_gives_up_when_its_first_candidate_has_no_slot(policy):
    # The served rule: the FIRST candidate decides whether the target gets a
    # slot. E1 (80) cannot displace a 98 (98 > 80 + 15), so the target is
    # skipped even though the later E2 (95) could have. A gate only ever lets a
    # REFUSED candidate yield; it never turns a no-slot verdict into a search.
    selected = [_f(f"p{i}", "politics", 98) for i in range(6)]
    pool = selected + [_f("E1", "entertainment", 80), _f("E2", "entertainment", 95)]
    out = list(selected)
    fmq._ensure_category_hunger(
        out, pool, gate=None if policy is None else _gate(policy)
    )
    assert _ids(out) == _ids(selected)
