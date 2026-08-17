"""C185 closure: the real composition, bound to the canonical ordering corpus.

THE CORPUS IS THE AUTHORITY. Every ALLOW case in
``tests/evals/fixtures/discover_lead_order_contract.json`` is replayed through
the PRODUCTION pass (``compose_lead``) and its ``after`` order is asserted
exactly. When the corpus and the code disagree, the code is wrong.

That direction matters here specifically. The version of this file authored
alongside the corpus asserted the order production ACTUALLY produced — the
buggy one — so the suite was green while the defect shipped, and the corpus
sat beside it as inert data. A test that records behaviour cannot detect it.
The bug it documented is preserved below as ``current-production-residual``:
the ordering production used to emit, now asserted to be unreachable.

The defect (UX-P025 RED): ``_pin_marquee_items`` and ``lead_with_tonights_games``
were two sequential passes that BOTH write a prefix, so they composed as
last-writer-wins and a live/imminent game displaced the pinned marquee. See
``compose_lead`` for why the fix had to be a single composition rather than a
reordering of the two.
"""

from __future__ import annotations

import inspect
from datetime import datetime, timedelta, timezone

from app.routes import feed as feed_module
from app.routes.feed import get_feed
from app.utils.tonights_games import compose_lead, lead_with_tonights_games
from scripts.evals.discover_lead_order_contract import evaluate, evaluate_pack, load_pack


# Fixed instant, never `now()` — gotcha #44 (a near-midnight run must not move a
# seeded game onto a different date token and re-colour the whole corpus).
NOW = datetime(2026, 8, 8, 23, tzinfo=timezone.utc)


def item(
    identity: str,
    kind: str,
    *,
    marquee: bool = False,
    status: str | None = None,
    soon: bool = False,
    score: int | None = None,
) -> dict:
    data: dict = {"id": identity}
    if kind == "event":
        data.update({"status": status or "live", "home_team_data": {"logo": "x"}})
        if soon:
            data["commence_time"] = (NOW + timedelta(hours=1)).isoformat()
    return {
        "type": kind,
        "score": score if score is not None else (35 if kind == "event" else 90),
        "_marquee_pin": marquee,
        "data": data,
    }


def item_for_label(label: str, score: int) -> dict:
    """Build a real feed item from a corpus label.

    The corpus speaks in labels (``marquee:open``, ``game:soon``); production
    speaks in feed dicts. This is the only place the two vocabularies meet, so
    the corpus stays readable and the binding stays honest.
    """
    if label.startswith("marquee:"):
        # Concepts and tournaments both earn the pin; alternate so the corpus
        # exercises each kind rather than only the first.
        kind = "tournament" if label.endswith(":second") else "concept"
        return item(label, kind, marquee=True, score=score)
    if label.startswith("game:"):
        if label.endswith(":soon"):
            return item(label, "event", status="scheduled", soon=True, score=score)
        return item(label, "event", status="live", score=score)
    if label.startswith("bundle:"):
        return item(label, "bundle", score=score)
    return item(label, "futures", score=score)


def rows_for(case: dict) -> list[dict]:
    return [
        item_for_label(label, score)
        for label, score in zip(case["before"], case["scores_before"])
    ]


def ids(rows: list[dict]) -> list[str]:
    return [row["data"]["id"] for row in rows]


def composed(rows: list[dict]) -> list[dict]:
    """The production composition, exactly as the route invokes it."""
    return compose_lead(rows, NOW)


# ── The corpus, and production bound to it ────────────────────────────────────


def test_fixture_corpus_matches_canonical_contract() -> None:
    result = evaluate_pack(load_pack())
    assert result["passed"] == result["total"] == 8


def test_every_allow_case_is_reproduced_by_the_real_composition() -> None:
    """The binding. Each ALLOW case's `after` IS the production requirement."""
    cases = [c for c in load_pack()["cases"] if c["expected"]["verdict"] == "ALLOW"]
    assert len(cases) == 5, "corpus shrank — the ordering authority must not thin out"

    failures = []
    for case in cases:
        rows = rows_for(case)
        actual = ids(composed(rows))
        if actual != case["after"]:
            failures.append(f"{case['id']}: expected {case['after']}, got {actual}")
    assert not failures, "production composition contradicts the corpus:\n" + "\n".join(failures)


def test_every_allow_case_also_passes_the_contract_evaluator() -> None:
    """Belt and braces: the evaluator must ALLOW what production emits."""
    for case in load_pack()["cases"]:
        if case["expected"]["verdict"] != "ALLOW":
            continue
        rows = rows_for(case)
        scores_before = [row["score"] for row in rows]
        after = composed(rows)
        verdict = evaluate(
            {
                "before": ids(rows),
                "after": ids(after),
                "scores_before": scores_before,
                # Read back off the ORIGINAL rows, in their original order — the
                # corpus's own convention. SCORES_CHANGED asks "was a score
                # mutated", not "did items move"; feeding it the reordered list
                # would make every correct reorder look like a mutation.
                "scores_after": [row["score"] for row in rows],
            }
        )
        assert verdict == {"verdict": "ALLOW", "errors": []}, f"{case['id']}: {verdict}"


def test_the_production_residual_ordering_is_now_unreachable() -> None:
    """The regression pin: the exact order UX-P025 shipped must not recur."""
    case = next(c for c in load_pack()["cases"] if c["id"] == "current-production-residual")
    rows = rows_for(case)
    after = ids(composed(rows))

    # The corpus REFUSES this ordering; production must no longer produce it.
    assert after != case["after"], "marquee displacement has returned (C185)"
    assert after == ["marquee:open", "game:live", "future:a"]

    verdict = evaluate(
        {
            "before": ids(rows),
            "after": after,
            "scores_before": case["scores_before"],
            "scores_after": case["scores_before"],
        }
    )
    assert verdict == {"verdict": "ALLOW", "errors": []}


# ── The properties confirmed clean, which must STAY clean ─────────────────────


def test_no_marquee_game_leads_and_membership_scores_stay_identical() -> None:
    rows = [item("future:a", "futures"), item("game:live", "event"), item("bundle:a", "bundle")]
    before_identities = sorted(map(id, rows))
    before_scores = [row["score"] for row in rows]
    after = composed(rows)
    assert ids(after)[0] == "game:live"
    assert sorted(map(id, after)) == before_identities
    assert [row["score"] for row in rows] == before_scores


def test_multiple_marquees_keep_relative_order_and_both_stay_above_the_game() -> None:
    rows = [
        item("marquee:first", "concept", marquee=True),
        item("game:live", "event"),
        item("marquee:second", "tournament", marquee=True),
    ]
    assert ids(composed(rows)) == ["marquee:first", "marquee:second", "game:live"]


def test_scheduled_game_leads_below_the_marquee_not_above_it() -> None:
    rows = [
        item("marquee:open", "concept", marquee=True),
        item("game:soon", "event", status="scheduled", soon=True),
    ]
    assert ids(composed(rows)) == ["marquee:open", "game:soon"]


def test_sports_mode_never_invokes_the_tonights_games_prefix() -> None:
    """Gate OFF: marquees still pin, games keep their place.

    The functional half of the route gate. Sports mode must not acquire a game
    lead-in through this pass — #1091 is the standing lesson about a feed pass
    reaching a surface it was never scoped to.
    """
    rows = [
        item("future:a", "futures"),
        item("game:live", "event"),
        item("marquee:open", "concept", marquee=True),
    ]
    assert ids(compose_lead(rows, NOW, include_tonights_games=False)) == [
        "marquee:open",
        "future:a",
        "game:live",
    ]


def test_a_marquee_that_is_itself_a_game_does_not_consume_a_lead_slot() -> None:
    """A pinned game leads as a MARQUEE; the cap still admits max_lead others."""
    rows = [
        item("marquee:game", "event", marquee=True),
        item("game:one", "event"),
        item("game:two", "event"),
        item("future:a", "futures"),
    ]
    assert ids(compose_lead(rows, NOW, max_lead=2)) == [
        "marquee:game",
        "game:one",
        "game:two",
        "future:a",
    ]


def test_pagination_after_reorder_has_no_duplicate_members() -> None:
    rows = [item("future:a", "futures"), item("game:live", "event"), item("future:b", "futures")]
    after = composed(rows)
    assert ids(after[:2]) == ["game:live", "future:a"]
    assert ids(after[2:]) == ["future:b"]
    assert len({id(row) for row in after}) == len(rows)


def test_bundles_remain_opaque_and_malformed_input_is_returned_unchanged() -> None:
    bundle = item("bundle:a", "bundle")
    rows = [bundle, item("future:a", "futures")]
    assert composed(rows) == rows

    malformed = [None, bundle]
    assert compose_lead(malformed, NOW) == malformed
    # The pass it replaces kept the same contract; both must stay defensive.
    assert lead_with_tonights_games(malformed, NOW) == malformed
    assert compose_lead([], NOW) == []


def test_no_score_is_mutated_by_the_composition() -> None:
    rows = [
        item("marquee:open", "concept", marquee=True, score=99),
        item("game:live", "event", score=35),
        item("future:a", "futures", score=90),
    ]
    composed(rows)
    assert [row["score"] for row in rows] == [99, 35, 90]


# ── Route wiring ──────────────────────────────────────────────────────────────


def test_route_uses_ONE_composition_and_gates_only_the_games_prefix() -> None:
    # #1923 moved the composition out of `get_feed` and into the shared display
    # chain, so the served path is now TWO functions. The contract is unchanged
    # and the assertion is widened rather than relaxed: exactly one
    # prefix-writing call across the whole served path. Anchoring on `get_feed`
    # alone would now pass while a second `compose_lead` sat in the chain.
    served_path = inspect.getsource(get_feed) + inspect.getsource(
        feed_module.apply_discover_display_chain
    )

    # Exactly one prefix-writing CALL. Two is the defect, whatever their order.
    # Matched with the open paren so the route's own explanation of the C185
    # defect — which necessarily names both retired passes — is not a false hit.
    assert served_path.count("compose_lead(") == 1
    assert "_pin_marquee_items(" not in served_path
    assert "lead_with_tonights_games(" not in served_path

    chain = inspect.getsource(feed_module.apply_discover_display_chain)
    call_at = chain.index("items = compose_lead(")
    call_block = chain[call_at : call_at + 200]
    assert "include_tonights_games=discover_mode" in call_block

    # The gate is now a named variable, so pin its DEFINITION — otherwise the
    # three clauses could be quietly widened and this test would still pass on
    # the name alone.
    gate_at = chain.index("discover_mode = ")
    gate_block = chain[gate_at : gate_at + 200]
    assert "not my_teams_only" in gate_block
    assert "event_pct is not None and event_pct < 0.3" in gate_block
    assert "or not include_events" in gate_block


def test_the_displacing_pass_is_gone_from_the_route_module() -> None:
    """Not merely uncalled — unimportable, so it cannot be re-paired."""
    assert not hasattr(feed_module, "_pin_marquee_items")
