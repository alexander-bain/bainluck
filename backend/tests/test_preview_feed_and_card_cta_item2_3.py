"""Tests for preview-list cache-miss resilience (Item 2) and grouping card CTA item_count/item_noun (Item 3)."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

import pytest

from app.utils import roundup_containers as rc
from app.utils.container_machinery import _machinery_card_item_count_and_noun


def _make_base_items(count: int = 30) -> list[dict[str, Any]]:
    now_iso = "2026-11-20T18:00:00+00:00"
    items: list[dict[str, Any]] = []
    for i in range(count):
        items.append(
            {
                "type": "futures",
                "score": 100.0 - i,
                "data": {
                    "id": 900000 + i,
                    "name": f"Base market {i}",
                    "category": "politics",
                    "last_updated": now_iso,
                    "outcomes": [{"id": i * 2 + 1, "name": "Yes", "probability": 0.55}],
                },
            }
        )
    return items


def _make_machinery_feed_item(slug: str, *, stage: str) -> tuple[dict[str, Any], dict[str, Any]]:
    fi = {
        "type": "bundle",
        "score": 50.0,
        "data": {
            "id": f"roundup:{slug}",
            "title": f"Headline for {slug}",
            "shared_question": f"Headline for {slug}",
            "collection_ref": {
                "slug": slug,
                "name": f"Headline for {slug}",
                "href": f"/collections/{slug}",
                "kind": "roundup",
            },
            "roundup": {
                "kicker": "TEST",
                "rows": [
                    {"label": "Row A", "probability": 0.55, "market_id": 1001},
                    {"label": "Row B", "probability": 0.45, "market_id": 1002},
                ],
                "footer": "",
                "machinery_card": {
                    "slug": slug,
                    "stage": stage,
                    "form_id": "benchmark_strip",
                    "section_count": 1,
                    "item_count": 11,
                    "item_noun": "cities",
                    "title": f"Headline for {slug}",
                    "subtitle": "",
                    "footer": "",
                    "destination_href": f"/collections/{slug}",
                    "rows": [],
                },
            },
            "items": [],
        },
    }
    cp = {"slug": slug, "name": f"Headline for {slug}", "items": []}
    return fi, cp


def _make_machinery_producer(
    slug: str,
    *,
    stage: str = "public",
) -> rc.RoundupProducer:
    async def _produce(_db: Any, *, now: Any = None) -> Any:
        return None

    return rc.RoundupProducer(
        slug=slug,
        name=slug,
        kind="roundup",
        category="other",
        section_title="Markets",
        footer="",
        produce=_produce,
        membership="computed-produced",
        relations=(),
        level="container",
        rule={"producer": "container_machinery"},
        stage=stage,
        enabled=lambda: True,
    )


def _machinery_slugs_in(items: list[dict[str, Any]]) -> list[str]:
    out: list[str] = []
    for it in items:
        if rc._is_machinery_roundup_item(it):
            out.append(rc._roundup_item_slug(it))
    return out


class TestPreviewFeedResilienceItem2:
    """Slow or cold preview sets must never empty `/api/feed?machinery=preview`."""

    @pytest.mark.asyncio
    async def test_preview_cache_miss_keeps_all_six_public_and_built_previews_when_one_is_slow_and_one_errors(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        now = datetime(2026, 11, 20, 20, 0, tzinfo=timezone.utc)
        public_slugs = [
            "machinery-2028-presidential",
            "machinery-oscars-best-picture",
            "machinery-fed-and-macro",
            "machinery-nba-night",
            "machinery-next-james-bond",
            "machinery-nfl-week",
        ]
        preview_slugs = [
            "machinery-white-christmas",
            "machinery-slow-cold-preview",
            "machinery-who-gets-engaged",
            "machinery-broken-preview",
        ]
        fake_producers = {
            **{s: _make_machinery_producer(s, stage="public") for s in public_slugs},
            **{s: _make_machinery_producer(s, stage="preview") for s in preview_slugs},
        }
        monkeypatch.setattr(rc, "ROUNDUP_PRODUCERS", fake_producers)
        monkeypatch.setattr(rc, "ensure_optional_roundup_candidates", lambda: None)
        monkeypatch.setattr(rc, "ROUNDUP_PREVIEW_PRODUCER_TIMEOUT_SECONDS", 0.05)
        monkeypatch.setattr(rc, "ROUNDUP_PREVIEW_STAGE_BUDGET_SECONDS", 2.0)
        stats_before = rc.get_roundup_read_failure_stats_10m(now=now.timestamp())

        async def _no_shared(_producers: Any, _db: Any) -> tuple[dict[str, Any], bool]:
            return {}, True

        async def _no_last_good(*_args: Any, **_kwargs: Any) -> Any:
            return None

        async def _fake_eval(
            producer: rc.RoundupProducer, _db: Any, **_kwargs: Any
        ) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
            if producer.slug == "machinery-slow-cold-preview":
                await asyncio.sleep(0.5)
            if producer.slug == "machinery-broken-preview":
                raise RuntimeError("boom on preview")
            return _make_machinery_feed_item(producer.slug, stage=producer.stage)

        monkeypatch.setattr(rc, "_prefetch_shared_roundup_entries", _no_shared)
        monkeypatch.setattr(rc, "_load_last_good_roundup_copy", _no_last_good)
        monkeypatch.setattr(rc, "evaluate_roundup_producer", _fake_eval)

        class _FakeDB:
            def __init__(self) -> None:
                self.rollbacks = 0

            async def rollback(self) -> None:
                self.rollbacks += 1

        db = _FakeDB()
        result = await rc.add_roundup_feed_items(
            db,
            _make_base_items(40),
            budget_seconds=10.0,
            stage_budget_seconds=2.5,
            now=now,
            include_machinery=True,
            machinery_only=True,
            include_preview=True,
        )

        served_slugs = _machinery_slugs_in(result)
        for s in public_slugs:
            assert s in served_slugs, f"public grouping {s} was dropped!"
        assert "machinery-white-christmas" in served_slugs
        assert "machinery-who-gets-engaged" in served_slugs
        assert "machinery-slow-cold-preview" not in served_slugs
        assert "machinery-broken-preview" not in served_slugs
        assert db.rollbacks == 2
        # Preview misses must not trigger public failure alarms.
        stats = rc.get_roundup_read_failure_stats_10m(now=now.timestamp())
        assert stats["failed"] == stats_before["failed"]
        assert stats["dropped_no_copy"] == stats_before["dropped_no_copy"]

    @pytest.mark.asyncio
    async def test_preview_warm_copies_survive_even_if_cold_preview_exhausts_preview_budget(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        now = datetime(2026, 11, 20, 20, 0, tzinfo=timezone.utc)
        fake_producers = {
            "machinery-next-james-bond": _make_machinery_producer(
                "machinery-next-james-bond", stage="public"
            ),
            # Registered BEFORE the warm preview so naive sequential order would starve it
            "machinery-cold-slow": _make_machinery_producer(
                "machinery-cold-slow", stage="preview"
            ),
            "machinery-white-christmas": _make_machinery_producer(
                "machinery-white-christmas", stage="preview"
            ),
        }
        monkeypatch.setattr(rc, "ROUNDUP_PRODUCERS", fake_producers)
        monkeypatch.setattr(rc, "ensure_optional_roundup_candidates", lambda: None)
        monkeypatch.setattr(rc, "ROUNDUP_PREVIEW_PRODUCER_TIMEOUT_SECONDS", 0.05)
        monkeypatch.setattr(rc, "ROUNDUP_PREVIEW_STAGE_BUDGET_SECONDS", 0.05)

        async def _prefetch(_producers: Any, _db: Any) -> tuple[dict[str, Any], bool]:
            return {"machinery-white-christmas": {"warm": True}}, True

        async def _load_last_good(
            producer: rc.RoundupProducer, *_args: Any, **kwargs: Any
        ) -> Any:
            if producer.slug == "machinery-white-christmas" and kwargs.get("prefetched_shared"):
                fi, cp = _make_machinery_feed_item(producer.slug, stage="preview")
                return fi, cp, 5.0, 900.0
            return None

        async def _fake_eval(
            producer: rc.RoundupProducer, _db: Any, **_kwargs: Any
        ) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
            if producer.slug == "machinery-cold-slow":
                await asyncio.sleep(0.5)
            return _make_machinery_feed_item(producer.slug, stage=producer.stage)

        monkeypatch.setattr(rc, "_prefetch_shared_roundup_entries", _prefetch)
        monkeypatch.setattr(rc, "_load_last_good_roundup_copy", _load_last_good)
        monkeypatch.setattr(rc, "evaluate_roundup_producer", _fake_eval)

        result = await rc.add_roundup_feed_items(
            object(),
            _make_base_items(30),
            budget_seconds=10.0,
            stage_budget_seconds=2.5,
            now=now,
            include_machinery=True,
            machinery_only=True,
            include_preview=True,
        )
        served_slugs = _machinery_slugs_in(result)
        assert "machinery-next-james-bond" in served_slugs
        assert "machinery-white-christmas" in served_slugs
        assert "machinery-cold-slow" not in served_slugs

    @pytest.mark.asyncio
    async def test_public_list_all_or_nothing_rule_is_unchanged(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        now = datetime(2026, 11, 20, 20, 0, tzinfo=timezone.utc)
        fake_producers = {
            "machinery-2028-presidential": _make_machinery_producer(
                "machinery-2028-presidential", stage="public"
            ),
            "machinery-fed-and-macro": _make_machinery_producer(
                "machinery-fed-and-macro", stage="public"
            ),
        }
        monkeypatch.setattr(rc, "ROUNDUP_PRODUCERS", fake_producers)
        monkeypatch.setattr(rc, "ensure_optional_roundup_candidates", lambda: None)
        monkeypatch.setattr(rc, "ROUNDUP_PRODUCER_TIMEOUT_SECONDS", 0.05)

        async def _no_last_good(*_args: Any, **_kwargs: Any) -> Any:
            return None

        async def _fake_eval(
            producer: rc.RoundupProducer, _db: Any, **_kwargs: Any
        ) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
            if producer.slug == "machinery-fed-and-macro":
                await asyncio.sleep(0.5)
            return _make_machinery_feed_item(producer.slug, stage="public")

        monkeypatch.setattr(rc, "_load_last_good_roundup_copy", _no_last_good)
        monkeypatch.setattr(rc, "evaluate_roundup_producer", _fake_eval)

        result = await rc.add_roundup_feed_items(
            object(),
            _make_base_items(30),
            budget_seconds=5.0,
            stage_budget_seconds=2.5,
            now=now,
            include_machinery=True,
            machinery_only=True,
            include_preview=False,
        )
        assert _machinery_slugs_in(result) == []


class TestMachineryCardCtaCountAndNounItem3:
    """machinery_card must carry item_count and item_noun for one-section CTA wording."""

    def test_sibling_fields_grid_defaults_to_markets(self) -> None:
        vb = {"form_id": "sibling_fields_grid", "items": [{"id": i} for i in range(7)]}
        assert _machinery_card_item_count_and_noun(vb) == (7, "markets")

    def test_benchmark_strip_uses_explicit_item_noun_or_benchmarks(self) -> None:
        cities_vb = {
            "form_id": "benchmark_strip",
            "item_noun": "cities",
            "items": [{"id": i} for i in range(11)],
        }
        assert _machinery_card_item_count_and_noun(cities_vb) == (11, "cities")

        couples_vb = {
            "form_id": "benchmark_strip",
            "item_noun": "couples",
            "items": [{"id": i} for i in range(16)],
        }
        assert _machinery_card_item_count_and_noun(couples_vb) == (16, "couples")

        default_vb = {
            "form_id": "benchmark_strip",
            "items": [{"id": i} for i in range(4)],
        }
        assert _machinery_card_item_count_and_noun(default_vb) == (4, "benchmarks")

    def test_other_forms_match_section_renderer_nouns(self) -> None:
        assert _machinery_card_item_count_and_noun(
            {"form_id": "coin_flip_matchups", "items": [{}, {}, {}]}
        ) == (3, "games")
        assert _machinery_card_item_count_and_noun(
            {"form_id": "matchup_slate", "items": [{}, {}]}
        ) == (2, "games")
        assert _machinery_card_item_count_and_noun(
            {
                "form_id": "paired_stage_bars",
                "paired_metric_set": {"entries": [{}, {}, {}, {}, {}]},
            }
        ) == (5, "contenders")
        assert _machinery_card_item_count_and_noun(
            {"form_id": "probability_history_chart", "items": [{}, {}]}
        ) == (2, "charts")
        assert _machinery_card_item_count_and_noun(
            {"form_id": "stacked_bar_list", "items": [{"outcomes": [{}, {}, {}, {}]}]}
        ) == (4, "outcomes")
