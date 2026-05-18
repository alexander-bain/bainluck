from datetime import datetime, timedelta, timezone

import pytest

from app.tasks.enrich_markets import (
    DISCOVER_LLM_METADATA_KEY,
    DISCOVER_LLM_SCHEMA_VERSION,
    _discover_llm_feature_tokens,
    _discover_llm_score_adjustment,
    enrich_discover_llm_metadata,
    _get_discover_llm_metadata,
    _json_from_llm_response,
    _metadata_needs_discover_llm_refresh,
    _sanitize_discover_llm_metadata,
)


def test_json_from_llm_response_handles_fenced_json():
    parsed = _json_from_llm_response('```json\n{"topic":"music"}\n```')
    assert parsed == {"topic": "music"}


def test_sanitize_discover_llm_metadata_bounds_and_cleans_values():
    now = datetime(2026, 5, 17, tzinfo=timezone.utc)
    metadata = _sanitize_discover_llm_metadata(
        {
            "topic": "Music Charts!",
            "subtopic": "Spotify Top 10",
            "archetype": "Culture Moment",
            "audience_scope": "very global",
            "salience_score": 9,
            "entities": ["Noah Kahan", "Noah Kahan", "!!!"],
            "junk_flags": ["Local Election"],
            "comparison_axes": ["sports vs music"],
            "why_interesting": "x" * 500,
        },
        now=now,
    )

    assert metadata["schema_version"] == DISCOVER_LLM_SCHEMA_VERSION
    assert metadata["topic"] == "music_charts"
    assert metadata["subtopic"] == "spotify_top_10"
    assert metadata["archetype"] == "culture_moment"
    assert metadata["audience_scope"] == "broad"
    assert metadata["salience_score"] == 5
    assert metadata["entities"] == ["noah kahan"]
    assert metadata["junk_flags"] == ["local election"]
    assert metadata["comparison_axes"] == ["sports vs music"]
    assert len(metadata["why_interesting"]) == 240


def test_discover_llm_score_adjustment_boosts_salient_named_cards():
    adjustment = _discover_llm_score_adjustment(
        {
            "salience_score": 5,
            "audience_scope": "mainstream",
            "entities": ["noah kahan"],
            "junk_flags": [],
        }
    )
    assert adjustment == 8


def test_discover_llm_score_adjustment_penalizes_junk_local_cards():
    adjustment = _discover_llm_score_adjustment(
        {
            "salience_score": 2,
            "audience_scope": "local",
            "entities": [],
            "junk_flags": ["local_election", "thin_liquidity"],
        }
    )
    assert adjustment <= -10


def test_discover_llm_feature_tokens_include_entities_and_axes():
    tokens = _discover_llm_feature_tokens(
        {
            "topic": "music",
            "subtopic": "spotify",
            "archetype": "culture_moment",
            "audience_scope": "mainstream",
            "entities": ["Noah Kahan"],
            "comparison_axes": ["sports vs music"],
        }
    )

    assert "llm_topic:music" in tokens
    assert "llm_archetype:culture_moment" in tokens
    assert "llm_entity:noah_kahan" in tokens
    assert "llm_axis:sports_vs_music" in tokens


def test_get_discover_llm_metadata_requires_current_schema():
    current = {
        DISCOVER_LLM_METADATA_KEY: {
            "schema_version": DISCOVER_LLM_SCHEMA_VERSION,
            "topic": "tech",
        }
    }
    stale = {
        DISCOVER_LLM_METADATA_KEY: {
            "schema_version": DISCOVER_LLM_SCHEMA_VERSION - 1,
            "topic": "tech",
        }
    }

    assert _get_discover_llm_metadata(current)["topic"] == "tech"
    assert _get_discover_llm_metadata(stale) is None


def test_cached_discover_llm_metadata_helpers_tolerate_partial_values():
    cached = {
        DISCOVER_LLM_METADATA_KEY: {
            "schema_version": DISCOVER_LLM_SCHEMA_VERSION,
            "topic": None,
            "subtopic": "ai",
            "archetype": "",
            "audience_scope": "mainstream",
            "salience_score": "not-a-number",
            "entities": [None, "OpenAI", ""],
            "junk_flags": [],
            "comparison_axes": ["AI vs markets", 123],
        }
    }

    metadata = _get_discover_llm_metadata(cached)

    assert metadata is not None
    assert _discover_llm_score_adjustment(metadata) == 2
    assert _discover_llm_feature_tokens(metadata) == [
        "llm_subtopic:ai",
        "llm_audience_scope:mainstream",
        "llm_entity:openai",
        "llm_axis:ai_vs_markets",
    ]


def test_metadata_needs_refresh_after_max_age():
    now = datetime(2026, 5, 17, tzinfo=timezone.utc)
    fresh = {
        DISCOVER_LLM_METADATA_KEY: {
            "schema_version": DISCOVER_LLM_SCHEMA_VERSION,
            "generated_at": (now - timedelta(days=3)).isoformat(),
        }
    }
    old = {
        DISCOVER_LLM_METADATA_KEY: {
            "schema_version": DISCOVER_LLM_SCHEMA_VERSION,
            "generated_at": (now - timedelta(days=45)).isoformat(),
        }
    }

    assert not _metadata_needs_discover_llm_refresh(fresh, now=now)
    assert _metadata_needs_discover_llm_refresh(old, now=now)


@pytest.mark.asyncio
async def test_enrich_discover_llm_metadata_skips_without_llm_client(monkeypatch):
    from app.services import llm

    monkeypatch.setattr(llm, "_get_client", lambda: None)

    def fail_if_session_is_opened():
        raise AssertionError("metadata enrichment should not open a DB session without an LLM client")

    monkeypatch.setattr("app.tasks.enrich_markets.get_task_session", fail_if_session_is_opened)

    assert await enrich_discover_llm_metadata(limit=1) == {"skipped": True}
