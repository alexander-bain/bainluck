"""#2602: same-domain concept cards are spaced, and nothing else changes.

EDITORIAL policy guard. SYNTHETIC ASCII fixtures throughout — no production
payload, no account data. Two layers:

* the pure helper ``space_discover_concept_families`` — multiset, protected
  prefix, displacement bound, anchors, graceful runs, determinism;
* the REAL ``apply_discover_display_chain`` — the stage is wired last for
  Discover, is absent for Sports and My Stuff, and the served order is one list
  for every page size and offset (#5101's property, re-asserted with concept
  cards in the pool, which that file's pool does not contain).
"""

import copy
import random
from datetime import datetime, timezone

import pytest

from app.routes.feed import (
    DISCOVER_COMPOSITION_WINDOW,
    _canonical_item_key,
    apply_discover_display_chain,
)
from app.utils.feed_market_quality import (
    DISCOVER_SPACING_MAX_DISPLACEMENT,
    discover_spacing_family,
    space_discover_concept_families,
)
from app.utils.personalization import PersonalizationContext

NOW = datetime(2026, 9, 17, 16, 0, 0, tzinfo=timezone.utc)
K = DISCOVER_SPACING_MAX_DISPLACEMENT
P = DISCOVER_COMPOSITION_WINDOW


def _fut(i, score=50.0, category="politics"):
    return {
        "type": "futures",
        "score": int(score),
        "_rank_score": float(score),
        "_sort_time": 0,
        "reason": f"Question {i}: 60% chance, up 12 points this week",
        "headline": "Up 12 points this week",
        "context_summary": "60% chance, up 12 points this week",
        "data": {
            "id": 1000 + i,
            "name": f"Will question {i} resolve yes?",
            "llm_sport_category": category,
            "market_tier": 2,
            "top_outcomes": [{"name": "Yes", "probability": 0.6}],
        },
    }


def _concept(slug, score=25.0, domain="ufc", **extra):
    data = {
        "key": f"event:{domain}:{slug}",
        "name": f"Fighter A{slug} vs Fighter B{slug}",
        "domain": domain,
        "status": "upcoming",
        "is_major": False,
        "is_marquee": False,
        "leader": {"name": f"Fighter A{slug}", "probability": 0.6},
    }
    data.update(extra)
    return {
        "type": "concept",
        "score": int(score),
        "_rank_score": float(score),
        "_sort_time": 0,
        "reason": "",
        "headline": "Upcoming",
        "data": data,
    }


def _keys(items):
    return [_canonical_item_key(it) for it in items]


def _longest_run(items, start=0):
    best = run = 0
    prev = None
    for it in items[start:]:
        fam = discover_spacing_family(it)
        run = run + 1 if (fam is not None and fam == prev) else (1 if fam else 0)
        best = max(best, run)
        prev = fam
    return best


def _tail_block(n_before=30, n_concepts=5, n_after=5):
    items = [_fut(i, 90 - i) for i in range(n_before)]
    items += [_concept(f"c{i}") for i in range(n_concepts)]
    items += [_fut(500 + i, 20 - i, "weather") for i in range(n_after)]
    return items


# ------------------------------------------------------------------ helper ---


def test_a_run_of_five_is_dissolved_when_the_pool_has_separators():
    items = _tail_block()
    assert _longest_run(items) == 5
    out, meta = space_discover_concept_families(items)
    assert _longest_run(out) == 1
    assert meta["unresolved_adjacent"] == 0


def test_the_multiset_is_unchanged():
    items = _tail_block()
    out, _ = space_discover_concept_families(items)
    assert sorted(_keys(out)) == sorted(_keys(items))
    assert len(out) == len(items)
    assert all(a is b for a, b in zip(sorted(out, key=id), sorted(items, key=id)))


def test_scores_and_identity_fields_are_untouched():
    items = _tail_block()
    before = copy.deepcopy(items)
    space_discover_concept_families(items)
    assert items == before  # input list and every dict unmodified


def test_the_protected_prefix_is_byte_identical_even_when_it_holds_a_run():
    items = [_concept(f"p{i}", 95) for i in range(4)] + _tail_block()
    out, _ = space_discover_concept_families(items)
    assert _keys(out[:P]) == _keys(items[:P])


@pytest.mark.parametrize("seed", range(40))
def test_no_card_moves_further_than_the_bound(seed):
    rng = random.Random(seed)
    items = []
    for i in range(140):
        roll = rng.random()
        if roll < 0.25:
            items.append(_concept(f"s{seed}x{i}", domain=rng.choice(["ufc", "boxing", "f1"])))
        else:
            items.append(_fut(i, category=rng.choice(["politics", "mma", "weather"])))
    out, meta = space_discover_concept_families(items)
    pos = {k: i for i, k in enumerate(_keys(items))}
    moves = [abs(pos[k] - j) for j, k in enumerate(_keys(out))]
    assert max(moves) <= K
    assert meta["max_displacement_seen"] == max(moves)
    assert sorted(_keys(out)) == sorted(_keys(items))
    assert _keys(out[:P]) == _keys(items[:P])
    assert _longest_run(out, P) <= _longest_run(items, P)


def test_an_all_one_domain_list_is_served_as_it_stands():
    items = [_concept(f"a{i}", 90 - i) for i in range(40)]
    out, meta = space_discover_concept_families(items)
    assert _keys(out) == _keys(items)
    assert meta["moved"] == 0
    assert meta["unresolved_adjacent"] == len(items) - P


def test_the_end_of_a_tail_keeps_a_run_rather_than_dropping_a_card():
    items = _tail_block(n_concepts=6, n_after=2)
    out, meta = space_discover_concept_families(items)
    assert len(out) == len(items)
    assert meta["unresolved_adjacent"] >= 1
    assert _longest_run(out) < 6


def test_a_near_empty_feed_is_returned_unchanged():
    for n in (0, 1, 2, P, P + 1):
        items = [_concept(f"n{i}") for i in range(n)]
        out, meta = space_discover_concept_families(items)
        assert _keys(out) == _keys(items) and meta["moved"] == 0


def test_mixed_families_are_not_spaced_against_each_other():
    items = [_fut(i, 90 - i) for i in range(P)]
    items += [_concept("u1"), _concept("f1a", domain="f1"), _concept("u2"), _concept("g1", domain="golf")]
    out, meta = space_discover_concept_families(items)
    assert _keys(out) == _keys(items) and meta["moved"] == 0


def test_ufc_and_boxing_read_as_one_family_other_domains_do_not():
    assert discover_spacing_family(_concept("a")) == discover_spacing_family(
        _concept("b", domain="boxing")
    )
    assert discover_spacing_family(_concept("a")) != discover_spacing_family(
        _concept("c", domain="f1")
    )


def test_different_promotions_and_distinct_real_events_all_survive():
    items = [_fut(i, 90 - i) for i in range(P)]
    cards = [
        _concept("26sep19", name="331: Van vs Pantoja"),
        _concept("26sep18powerslap23", name="Power Slap 23", sport_label="Combat"),
        _concept("26sep22dwcs", name="Contender Series", sport_label="Combat"),
        _concept("26dec27", name="Saint-Denis vs Pimblett"),
        _concept("27jul11", name="Pimblett vs McGregor"),  # same fighter, later date
    ]
    items += cards + [_fut(900 + i, 10) for i in range(6)]
    out, _ = space_discover_concept_families(items)
    assert {c["data"]["key"] for c in cards} <= {(it["data"].get("key")) for it in out}
    assert _longest_run(out) == 1


def test_the_family_key_is_the_domain_not_the_display_label():
    a = _concept("x", sport_label="UFC")
    b = _concept("x", sport_label="MMA")
    assert discover_spacing_family(a) == discover_spacing_family(b)
    base = [_fut(i, 90 - i) for i in range(P)]
    tail = [_fut(800 + i, 10) for i in range(5)]
    o1, _ = space_discover_concept_families(base + [a, _concept("y")] + tail)
    o2, _ = space_discover_concept_families(base + [b, _concept("y")] + tail)
    assert _keys(o1) == _keys(o2)


def test_a_same_subject_futures_card_is_not_used_as_the_separator():
    items = [_fut(i, 90 - i) for i in range(P)]
    member = _fut(700, 24, "mma")  # e.g. a standalone member market
    other = _fut(701, 23, "weather")
    items += [_concept("m1"), _concept("m2"), member, other]
    out, _ = space_discover_concept_families(items)
    assert _keys(out[P:]) == _keys([items[P], other, items[P + 1], member])


def test_a_parent_and_its_standalone_member_are_both_still_served():
    items = [_fut(i, 90 - i) for i in range(P)]
    member = _fut(710, 60, "mma")
    items += [member, _concept("parent"), _concept("other"), _fut(711, 10)]
    out, _ = space_discover_concept_families(items)
    assert _canonical_item_key(member) in _keys(out)
    assert out.index(member) == P  # a non-concept card is never deferred


@pytest.mark.parametrize("flag", ["is_marquee", "is_major", "marquee_whathit"])
def test_an_anchor_keeps_its_exact_index(flag):
    items = [_fut(i, 90 - i) for i in range(P)]
    anchor = _concept("anchor", **{flag: True})
    items += [_concept("c1"), anchor, _concept("c2"), _fut(720, 10), _fut(721, 9)]
    out, _ = space_discover_concept_families(items)
    assert out.index(anchor) == items.index(anchor)


def test_a_live_concept_is_never_deferred_and_never_crossed():
    items = [_fut(i, 90 - i) for i in range(P)]
    live = _concept("live", status="live")
    items += [_concept("c1"), _concept("c2"), live, _fut(730, 10)]
    out, _ = space_discover_concept_families(items)
    assert out.index(live) == items.index(live)


def test_same_input_same_output_every_time():
    items = _tail_block()
    first, _ = space_discover_concept_families(copy.deepcopy(items))
    for _ in range(5):
        again, _ = space_discover_concept_families(copy.deepcopy(items))
        assert _keys(again) == _keys(first)


def test_it_is_idempotent_once_a_run_is_dissolved():
    out, _ = space_discover_concept_families(_tail_block())
    again, meta = space_discover_concept_families(out)
    assert _keys(again) == _keys(out) and meta["moved"] == 0


# ------------------------------------------------------ the real chain -------

PAGE_SIZES = [1, 10, 20, 50, 250]


def _pool():
    """SYNTHETIC full population: 110 futures on a score plateau + 9 concepts."""
    cats = ["politics", "economics", "tech", "entertainment", "weather", "soccer", "golf"]
    pool = [_fut(i, 95.0 - (i // 2), cats[i % len(cats)]) for i in range(110)]
    for i in range(110):
        pool[i]["data"]["name"] = f"Will distinct subject number {i} happen by 2027?"
    pool += [_concept("26sep19", 53.0)]
    pool += [_concept(f"t{i}", 42.0) for i in range(2)]
    pool += [_concept(f"u{i}", 41.0) for i in range(5)]
    pool += [_concept("b1", 41.0, domain="boxing")]
    # a real tail does not end on the concepts: lower-scored cards follow them
    pool += [_fut(300 + i, 38.0 - i, cats[i % len(cats)]) for i in range(12)]
    for i in range(12):
        pool[-12 + i]["data"]["name"] = f"Will tail subject number {i} happen by 2028?"
    return pool


def _serve(pool, *, limit=250, offset=0, **kw):
    kw.setdefault("event_pct", 0.15)
    kw.setdefault("ctx", PersonalizationContext())
    items, meta = apply_discover_display_chain(
        copy.deepcopy(pool), limit=limit, now=NOW, **kw
    )
    return items[offset : offset + limit], items, meta


def test_the_chain_spaces_the_run_and_reports_it():
    _, full, meta = _serve(_pool())
    assert meta["concept_spacing"] is not None
    assert meta["concept_spacing"]["moved"] > 0
    # six tied combat cards, first separator five slots away: the bound (4)
    # leaves the first pair and dissolves the rest. 6 -> 2, not 6 -> 1, and the
    # remainder is COUNTED rather than hidden.
    assert _longest_run(full, P) == 2
    assert meta["concept_spacing"]["unresolved_adjacent"] == 1


def test_the_chain_keeps_every_card_the_unspaced_build_serves(monkeypatch):
    _, spaced, _ = _serve(_pool())
    import app.routes.feed as feed_module

    monkeypatch.setattr(
        feed_module,
        "space_discover_concept_families",
        lambda items, **_: (items, {"moved": 0, "unresolved_adjacent": 0, "bound": 0}),
    )
    _, plain, _ = _serve(_pool())
    assert _longest_run(plain, P) >= 5  # the defect exists without the stage
    assert sorted(_keys(spaced)) == sorted(_keys(plain))
    assert _keys(spaced[:P]) == _keys(plain[:P])
    pos = {k: i for i, k in enumerate(_keys(plain))}
    assert max(abs(pos[k] - j) for j, k in enumerate(_keys(spaced))) <= K


@pytest.mark.parametrize("size", PAGE_SIZES)
def test_every_page_size_is_a_prefix_of_the_largest(size):
    page, _, _ = _serve(_pool(), limit=size)
    largest, _, _ = _serve(_pool(), limit=250)
    assert _keys(page) == _keys(largest)[:size]


@pytest.mark.parametrize("size", [1, 7, 10, 20, 50])
def test_walking_the_pages_meets_every_card_exactly_once(size):
    _, full, _ = _serve(_pool())
    walked = []
    offset = 0
    while True:
        page, _, _ = _serve(_pool(), limit=size, offset=offset)
        if not page:
            break
        walked += _keys(page)
        offset += size
    assert walked == _keys(full)
    assert len(set(walked)) == len(walked)


def test_a_refresh_with_identical_inputs_serves_the_identical_order():
    a = _keys(_serve(_pool())[1])
    pool = _pool()
    random.Random(7).shuffle(pool)  # candidate-query order must not matter
    assert _keys(_serve(pool)[1]) == a


def test_sports_mode_is_not_spaced():
    _, _, meta = _serve(_pool(), event_pct=0.6, sports_mode=True)
    assert meta["concept_spacing"] is None


def test_my_stuff_is_not_spaced():
    _, full, meta = _serve(_pool(), my_teams_only=True)
    assert meta["concept_spacing"] is None


def test_a_signed_in_reader_with_affinities_gets_the_same_guarantees():
    ctx = PersonalizationContext()
    ctx.is_authenticated = True
    ctx.discover_category_affinities = {"politics": 0.9, "mma": 0.8}
    _, full, meta = _serve(_pool(), ctx=ctx, cold_start=False)
    assert sorted(_keys(full)) == sorted(_keys(_serve(_pool())[1]))
    assert _longest_run(full, P) <= 2


# --------------------------------------------- production-shaped field names ---
#
# The tests above build their own dicts, so they prove the POLICY and are blind
# to the only way this pass can silently go inert: reading a key the adapter
# does not emit. `_spacing_is_anchor` and `discover_spacing_family` are pure
# `.get()` chains — a renamed field does not raise, it just stops matching, and
# every assertion above would still pass while a marquee card lost its seat.
#
# KEY SET PROVENANCE (not payload provenance): the names below were read off an
# anonymous production `GET /api/feed?limit=150` capture on 2026-09-17 (148 of
# 148 cards, `edition 520fb74e1b76ca10`) and cross-read against the concept
# adapter in `routes/feed.py`, which emits `key/name/domain/status/is_major/
# is_marquee/marquee_whathit`. `discover_marquee_final` is an EVENT-card field
# (truthy on 2 of the 148). Only the NAMES are pinned here; every value is
# synthetic ASCII, so no production or account data lands in the repo.

PRODUCTION_CONCEPT_DATA_KEYS = frozenset(
    {
        "domain",
        "entry_count",
        "fight_count",
        "headline_bout",
        "is_major",
        "is_marquee",
        "key",
        "leader",
        "marquee_whathit",
        "name",
        "price_observed_at",
        "start_date",
        "status",
    }
)

#: Every field `_spacing_is_anchor` consults, by name.
SPACING_ANCHOR_FIELDS = frozenset(
    {"status", "is_marquee", "is_major", "discover_marquee_final", "marquee_whathit"}
)


def _production_shaped_concept(**overrides) -> dict:
    """A concept card carrying exactly the key set production serves."""
    data = {
        "domain": "ufc",
        "entry_count": 0,
        "fight_count": 11,
        "headline_bout": "Fighter A vs Fighter B",
        "is_major": False,
        "is_marquee": False,
        "key": "event:ufc:26sep19",
        "leader": {"name": "Fighter A", "probability": 0.62},
        "marquee_whathit": False,
        "name": "331: Fighter A vs Fighter B",
        "price_observed_at": "2026-09-17T20:00:00+00:00",
        "start_date": "2026-09-19",
        "status": "upcoming",
    }
    data.update(overrides)
    assert set(data) >= PRODUCTION_CONCEPT_DATA_KEYS, "fixture drifted from the payload"
    return {"type": "concept", "score": 25, "_rank_score": 25.0, "_sort_time": 0, "data": data}


def test_the_family_key_is_a_field_the_concept_adapter_actually_emits():
    # `domain` is the whole pass: without it every card is family `None` and the
    # stage is a no-op that still ticks, passes and logs nothing.
    assert "domain" in PRODUCTION_CONCEPT_DATA_KEYS
    assert discover_spacing_family(_production_shaped_concept()) == "concept:combat"


def test_every_anchor_field_is_a_real_payload_field():
    # `discover_marquee_final` is the one anchor field concept cards never carry
    # — it rides EVENT cards, which this pass never defers anyway. The other four
    # must be concept-payload fields or the anchor guard is decorative.
    assert SPACING_ANCHOR_FIELDS - {"discover_marquee_final"} <= PRODUCTION_CONCEPT_DATA_KEYS


@pytest.mark.parametrize(
    "overrides",
    [
        {"is_marquee": True},
        {"is_major": True},
        {"marquee_whathit": True},
        {"status": "live"},
    ],
)
def test_a_production_shaped_anchor_keeps_its_exact_slot(overrides):
    items = [_fut(i, 90 - i) for i in range(P)]
    anchor = _production_shaped_concept(key="event:ufc:anchor", **overrides)
    items += [_concept("c1"), anchor, _concept("c2"), _fut(740, 10), _fut(741, 9)]
    out, _ = space_discover_concept_families(items)
    assert out.index(anchor) == items.index(anchor)


def test_a_production_shaped_upcoming_card_is_still_movable():
    # The mirror of the test above: `status: "upcoming"` — what every one of the
    # eight live concept cards actually carries — must NOT read as an anchor, or
    # the pass is inert on precisely the population it was built for.
    items = [_fut(i, 90 - i) for i in range(P)]
    first = _production_shaped_concept(key="event:ufc:a")
    second = _production_shaped_concept(key="event:ufc:b")
    items += [first, second, _fut(750, 10), _fut(751, 9)]
    out, meta = space_discover_concept_families(items)
    assert meta["moved"] > 0
    assert _longest_run(out, P) == 1
