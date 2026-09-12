"""T11-1 (#5461) — no newsletter prose reaches the production hook prompt, ever again.

`enrich_market_hooks` used to sample three sentences at random out of
``app/data/polymarket_blurbs.json`` — fifty blurbs lifted verbatim from the Polymarket
newsletter — and paste them into the prompt as "Examples of great hooks", with a
hard-coded fallback triple written in the same voice. D138 forbids it: the newsletters
teach the SHAPE of a good description, never their sentences, and their prose never
enters production generation.

These tests are the contract, and it is worth being exact about what each half proves,
because the obvious framing is wrong. **The corpus was never IN the old source** — it was
read from disk at runtime — so a source scan would have passed on the old code and proves
nothing about the past. The two that would have gone red on `origin/master` are
``test_neither_module_names_the_corpus_file_at_all`` (the loader and the filename were
there) and ``test_neither_module_draws_a_random_sample`` (``random.sample`` was there);
the retired hard-coded fallback triple is separately pinned by its own probes.

What closes the loop on the runtime path is
``test_the_tasks_prompt_is_the_pure_function_and_nothing_else``: the task's prompt is
exactly the output of :func:`build_hook_prompt`, and that output is what the shingle tests
measure. The shingle detector carries a positive control so it cannot pass by being broken,
and the corpus loader asserts the corpus is present and non-empty before measuring against
it.
"""

from __future__ import annotations

import inspect
import json
import re
from pathlib import Path

import pytest

from app.utils.hook_prompt import (
    HOOK_EXAMPLES,
    HOOK_STYLE_CRITERIA,
    build_hook_prompt,
)

_CORPUS = Path(__file__).resolve().parents[1] / "app" / "data" / "polymarket_blurbs.json"

#: Eight words is short enough to catch a lightly edited lift and long enough that ordinary
#: English ("the first time in a decade") cannot collide with it by accident.
_SHINGLE = 8


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", text.lower())


def _shingles(text: str, n: int = _SHINGLE) -> set[str]:
    w = _words(text)
    return {" ".join(w[i : i + n]) for i in range(len(w) - n + 1)}


def _load_corpus() -> list[dict]:
    """The newsletter corpus, with its own presence asserted.

    A guard that reads a fixture must fail loudly when the fixture disappears, or the day
    someone deletes the file every assertion below starts passing over nothing.
    """
    assert _CORPUS.exists(), (
        f"{_CORPUS} is gone. That may be correct — but it is the population these guards "
        "are measured against, so update this test deliberately rather than letting it "
        "pass over an empty set."
    )
    corpus = json.loads(_CORPUS.read_text())
    assert isinstance(corpus, list) and len(corpus) >= 20, (
        f"expected the full newsletter corpus, got {len(corpus)} entries"
    )
    return corpus


def _static_prompt() -> str:
    """The prompt's own scaffolding — everything that is not read from a market row."""
    return build_hook_prompt(
        market_name="",
        category="",
        leaderboard_lines=[],
        resolve_str="",
        volume_str="",
    )


class TestNoNewsletterProseInThePrompt:
    def test_the_shingle_detector_actually_fires(self):
        """Positive control. Without this the three tests below can pass while broken."""
        corpus = _load_corpus()
        a_real_blurb = corpus[0]["blurb"]
        assert _shingles(a_real_blurb), "the first blurb is too short to shingle"
        assert _shingles(a_real_blurb) & _shingles(
            f"some preamble {a_real_blurb} some suffix"
        ), "the detector cannot see a blurb quoted verbatim — fix the detector, not the code"

    def test_no_corpus_shingle_survives_in_the_prompt_scaffolding(self):
        corpus = _load_corpus()
        prompt_shingles = _shingles(_static_prompt())
        for entry in corpus:
            overlap = _shingles(entry["blurb"]) & prompt_shingles
            assert not overlap, (
                f"newsletter prose reached the prompt: {sorted(overlap)[:2]} "
                f"(from {entry.get('market_name')!r})"
            )

    def test_no_corpus_shingle_survives_in_either_module_source(self):
        """Not just the composed string — the source, so a commented-out lift is caught too."""
        corpus = _load_corpus()
        from app.tasks import enrich_markets
        from app.utils import hook_prompt

        for module in (hook_prompt, enrich_markets):
            src_shingles = _shingles(inspect.getsource(module))
            for entry in corpus:
                overlap = _shingles(entry["blurb"]) & src_shingles
                assert not overlap, (
                    f"newsletter prose is in {module.__name__}: {sorted(overlap)[:2]}"
                )

    def test_neither_module_names_the_corpus_file_at_all(self):
        """No carve-out. Both modules explain what was removed WITHOUT naming the file,
        so this can be a flat substring check — a guard that excuses its own subject's
        name is a hole the next paste hides in."""
        from app.tasks import enrich_markets
        from app.utils import hook_prompt

        for module in (enrich_markets, hook_prompt):
            src = inspect.getsource(module)
            for forbidden in (_CORPUS.name, "_load_polymarket_blurbs"):
                assert forbidden not in src, (
                    f"{forbidden!r} is back in {module.__name__}"
                )

    def test_the_tasks_prompt_is_the_pure_function_and_nothing_else(self):
        """Closes the loop the source scans cannot: the corpus was never IN the old source,
        it was loaded at runtime. So the guarantee is that the task's `prompt` is exactly
        `build_hook_prompt(...)` — whose output the tests above measure — with no second
        assignment splicing anything else in."""
        import ast

        from app.tasks import enrich_markets

        tree = ast.parse(inspect.getsource(enrich_markets))
        fn = next(
            n
            for n in ast.walk(tree)
            if isinstance(n, ast.AsyncFunctionDef) and n.name == "enrich_market_hooks"
        )
        prompt_assignments = [
            n
            for n in ast.walk(fn)
            if isinstance(n, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "prompt" for t in n.targets)
        ]
        assert len(prompt_assignments) == 1, (
            f"expected exactly one `prompt = ...` in enrich_market_hooks, "
            f"found {len(prompt_assignments)}"
        )
        value = prompt_assignments[0].value
        assert isinstance(value, ast.Call) and isinstance(value.func, ast.Name), (
            "the prompt is no longer a single call — re-read what it is built from"
        )
        assert value.func.id == "build_hook_prompt", (
            f"the prompt is built by {value.func.id}, not the audited pure function"
        )


class TestThePromptIsReproducible:
    def test_same_inputs_give_a_byte_identical_prompt(self):
        """The old prompt drew `random.sample` per market, so no trace could reproduce it."""
        kwargs = dict(
            market_name="Who will be the next Prime Minister of Israel?",
            category="politics",
            leaderboard_lines=["#1 Gadi Eizenkot: 52%", "#2 Naftali Bennett: 21%"],
            resolve_str="Resolves: Nov 03, 2026",
            volume_str="24h volume: $412K",
        )
        first = build_hook_prompt(**kwargs)
        for _ in range(20):
            assert build_hook_prompt(**kwargs) == first

    def test_neither_module_draws_a_random_sample(self):
        """Asked of the AST, not of a substring.

        The first cut of this test grepped the source for "random" and went red on this
        module's own prose explaining what was removed — a guard matching its own
        explanation. An import and a call are structural; say so structurally.
        """
        import ast

        from app.tasks import enrich_markets
        from app.utils import hook_prompt

        for module in (hook_prompt, enrich_markets):
            tree = ast.parse(inspect.getsource(module))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        assert alias.name.split(".")[0] != "random", (
                            f"{module.__name__} imports random — a per-market sample makes "
                            "the prompt irreproducible, which is half of T11-1"
                        )
                if isinstance(node, ast.ImportFrom):
                    assert (node.module or "").split(".")[0] != "random", (
                        f"{module.__name__} imports from random"
                    )
                if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
                    assert not (
                        node.value.id == "random" and node.attr in {"sample", "choice", "choices", "shuffle"}
                    ), f"{module.__name__} calls random.{node.attr}"


class TestThePromptStillSaysWhatItMustSay:
    """Non-vacuity. Emptying the examples or the criteria must not leave these green."""

    def test_every_authored_example_reaches_the_prompt(self):
        assert len(HOOK_EXAMPLES) >= 3
        prompt = _static_prompt()
        for example in HOOK_EXAMPLES:
            assert example in prompt

    def test_every_criterion_reaches_the_prompt(self):
        assert len(HOOK_STYLE_CRITERIA) >= 5
        prompt = _static_prompt()
        for criterion in HOOK_STYLE_CRITERIA:
            assert criterion in prompt

    def test_the_examples_are_labelled_as_shape_not_material(self):
        """An unlabelled example invites the model to reuse its subject as a fact."""
        prompt = _static_prompt().lower()
        assert "shape, not the material" in prompt
        assert "describe no real event" in prompt

    @pytest.mark.parametrize(
        "rule",
        [
            "NEVER include specific percentages",
            "NEVER reference prediction markets",
            "max 250 chars",
        ],
    )
    def test_the_operative_rules_survive(self, rule: str):
        assert rule in _static_prompt()

    def test_the_authored_examples_obey_the_rules_they_teach(self):
        """The retired fallback triple did not: 'sending this market surging' is a venue
        reference sitting directly under 'NEVER reference prediction markets'."""
        banned = (
            "polymarket",
            "kalshi",
            "odds",
            "traders",
            "betting",
            "gambling",
            "this market",
        )
        for example in HOOK_EXAMPLES:
            lowered = example.lower()
            for word in banned:
                assert word not in lowered, f"{word!r} in an authored example: {example!r}"
            assert "%" not in example
            assert len(example) <= 250, f"{len(example)} chars: {example!r}"


class TestOldPromptCopyCannotOutliveTheServeGate:
    """The stale-copy half of T11-1's acceptance, argued from the two constants.

    No backfill ships with this change and none is needed, but that is a claim about
    convergence and it rests on a gap between two numbers that live in different modules:
    a hook is regenerated once it is older than the REGEN TTL, and it is suppressed at
    serve time once it is older than the SERVE gate. As long as the serve gate is finite,
    every hook a reader can still see after that many days was written by the new prompt —
    with no backfill, no spend, and no data repair.

    Measured on production 2026-09-12 while building this: of 576 open liquid markets
    carrying a hook, 377 were 32-127 days old. Those are already suppressed at serve time
    (they serve no hook at all, which is its own quality finding and its own issue) — they
    are not stale prose on a card.
    """

    def test_the_serve_gate_is_finite_and_short(self):
        from app.utils.hook_staleness import STALE_HOOK_MAX_AGE_DAYS

        assert 0 < STALE_HOOK_MAX_AGE_DAYS <= 14, (
            "old-prompt copy ages out of the feed in STALE_HOOK_MAX_AGE_DAYS. Raising this "
            "lengthens the window in which a reader can still see a hook written by the "
            "retired newsletter-example prompt."
        )

    def test_a_hook_older_than_the_serve_gate_is_suppressed(self):
        from datetime import datetime, timedelta, timezone

        from app.utils.hook_staleness import STALE_HOOK_MAX_AGE_DAYS, is_hook_stale

        now = datetime(2026, 9, 12, tzinfo=timezone.utc)
        old = now - timedelta(days=STALE_HOOK_MAX_AGE_DAYS + 1)
        fresh = now - timedelta(days=STALE_HOOK_MAX_AGE_DAYS - 1)
        common = dict(
            hook_description="written by the retired prompt",
            hook_leader_at_generation="Somebody",
            current_leader_name="Somebody",
            current_leader_probability=None,
            market_metadata={},
            now=now,
        )
        assert is_hook_stale(hook_generated_at=old, **common) is True
        # Both sides: the gate must not suppress everything, or the convergence argument
        # is true for an uninteresting reason.
        assert is_hook_stale(hook_generated_at=fresh, **common) is False

    def test_the_regeneration_ttl_stays_below_the_serve_gate(self):
        """Two constants, one capability — assert the GAP, not each number alone.

        `_needs_regeneration` refreshes at 24h; the serve gate suppresses at 7 days. If
        the regen TTL ever exceeded the serve gate, markets would fall out of the feed's
        hook entirely and sit there un-refreshed, and nothing else in the suite would say
        so.
        """
        from datetime import datetime, timedelta, timezone
        from types import SimpleNamespace

        from app.tasks.enrich_markets import _needs_regeneration
        from app.utils.hook_staleness import STALE_HOOK_MAX_AGE_DAYS

        now = datetime(2026, 9, 12, tzinfo=timezone.utc)
        just_inside_the_serve_gate = now - timedelta(
            days=STALE_HOOK_MAX_AGE_DAYS, hours=-1
        )
        market = SimpleNamespace(
            hook_description="anything",
            hook_generated_at=just_inside_the_serve_gate,
            hook_leader_at_generation="Somebody",
            market_metadata={},
        )
        assert _needs_regeneration(market, "Somebody", 0.5, now) is True, (
            "a hook still inside the serve gate must already be queued for regeneration"
        )


class TestTheMarketRowStillTravels:
    """The ship replaced the examples, not the evidence. Every input must still arrive."""

    def test_market_name_category_leaderboard_resolution_and_volume_all_appear(self):
        prompt = build_hook_prompt(
            market_name="Fed decision in September",
            category="economics",
            leaderboard_lines=["#1 Hike 25bps: 79%", "#2 Hold: 19%"],
            resolve_str="Resolves: Sep 17, 2026",
            volume_str="24h volume: $1.2M",
        )
        for fragment in (
            "Fed decision in September",
            "economics",
            "#1 Hike 25bps: 79%",
            "#2 Hold: 19%",
            "Resolves: Sep 17, 2026",
            "24h volume: $1.2M",
        ):
            assert fragment in prompt
