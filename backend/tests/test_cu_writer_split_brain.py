"""#1808 — the CU v1/v2 split brain.

Two LLM enrichment writers own `market_metadata['discover_llm']`:

* v1 `enrich_discover_llm_metadata` (beat: every 6h) read the key through an
  accessor that rejects `schema_version != 1`, so a v2 profile was
  indistinguishable from *no profile* — its refresh predicate said "needs
  refresh" and the profile was overwritten back to v1.
* v2 `enrich_cu_v2_profiles` (beat: every 12h) re-tags anything that is not
  `schema_version=2 AND writer_rev=CU_WRITER_REV`, overwriting v1 back to v2.

Both select from the same candidate pool in the same order, so the feed's top
markets oscillated between profile shapes depending on which beat ran last —
and every market wearing a v2 profile silently lost its LLM score adjustment,
its `llm_*` personalization tokens, and its public card metadata, because
`routes/feed.py` read v1 only.

These tests pin both halves of the acceptance:

1. Run BOTH writers' skip/refresh predicates twice over the same fixture
   metadata — `schema_version` must be stable across cycles.
2. A v2 profile that merits it must produce a non-zero score adjustment and
   non-empty feature tokens through the shared version-aware accessor.

The clock is frozen out entirely (gotcha #44): every timestamp is derived by
offset from a fixed `NOW`, and both predicates take `now` explicitly.
"""

from datetime import datetime, timedelta, timezone

from app.tasks.enrich_markets import (
    CU_V2_OWNERSHIP_MAX_AGE_DAYS,
    CU_V2_SCHEMA_VERSION,
    CU_WRITER_REV,
    DISCOVER_LLM_METADATA_KEY,
    DISCOVER_LLM_SCHEMA_VERSION,
    _cu_v2_needs_retag,
    _cu_v2_profile_owns_key,
    _discover_llm_feature_tokens,
    _discover_llm_score_adjustment,
    _get_discover_llm_metadata,
    _get_discover_llm_view,
    _metadata_needs_discover_llm_refresh,
    _sanitize_discover_llm_metadata,
    _v2_profile_as_v1_shape,
)

NOW = datetime(2026, 8, 12, 12, 0, tzinfo=timezone.utc)


def _v1_profile(*, generated_at: datetime, topic: str = "tech") -> dict:
    return {
        "schema_version": DISCOVER_LLM_SCHEMA_VERSION,
        "generated_at": generated_at.isoformat(),
        "model": "gpt-4o-mini",
        "topic": topic,
        "subtopic": "ai",
        "archetype": "milestone",
        "audience_scope": "broad",
        "salience_score": 4,
        "entities": ["openai"],
        "junk_flags": [],
        "comparison_axes": ["ai_tech"],
        "why_interesting": "",
    }


def _v2_profile(
    *,
    generated_at: datetime,
    writer_rev: int = CU_WRITER_REV,
    stakes: int = 4,
    breadth: int = 5,
    geography: str = "global",
    junk_flags: list | None = None,
    arc: str = "race",
) -> dict:
    return {
        "schema_version": CU_V2_SCHEMA_VERSION,
        "writer_rev": writer_rev,
        "model": "gpt-4o-mini",
        "generated_at": generated_at.isoformat(),
        "topic": "sports",
        "subtopic": "soccer",
        "entities": [
            {"name": "Argentina", "type": "team"},
            {"name": "Lionel Messi", "type": "person"},
        ],
        "geography": geography,
        "story_key": "story:world_cup_final",
        "series_key": "series:world_cup",
        "temporal_class": "event_tied",
        "event_date": "2026-07-19",
        "recurrence": "one_off",
        "stakes": stakes,
        "breadth": breadth,
        "oddity": 1,
        "arc": arc,
        "hook_facts": [{"type": "stat", "text": "Argentina have won two of the last three finals."}],
        "junk_flags": junk_flags if junk_flags is not None else [],
        "confidence": 0.9,
        "liveness": "active",
    }


# --------------------------------------------------------------------------
# Acceptance 1 — schema_version is stable when both writers run, twice
# --------------------------------------------------------------------------


def _v1_writer_cycle(metadata: dict, *, now: datetime) -> tuple[dict, str]:
    """Apply the REAL v1 refresh predicate; write a v1 profile if it fires."""
    if not _metadata_needs_discover_llm_refresh(metadata, now=now):
        return metadata, "skipped"
    nxt = dict(metadata)
    nxt[DISCOVER_LLM_METADATA_KEY] = _sanitize_discover_llm_metadata(
        {"topic": "sports", "subtopic": "soccer", "salience_score": 4}, now=now
    )
    return nxt, "wrote"


def _v2_writer_cycle(metadata: dict, *, now: datetime) -> tuple[dict, str]:
    """Apply the REAL v2 skip predicate; write a v2 profile if it fires."""
    if not _cu_v2_needs_retag(metadata, now=now):
        return metadata, "skipped"
    nxt = dict(metadata)
    nxt[DISCOVER_LLM_METADATA_KEY] = _v2_profile(generated_at=now)
    return nxt, "wrote"


def test_schema_version_is_stable_when_both_writers_run_twice():
    """The acceptance pin: no oscillation of `discover_llm.schema_version`.

    Four starting states, both beats, two full cycles six hours apart (the v1
    beat's real cadence). Before the fix the v1 writer stamped v1 over every v2
    profile on every cycle and the v2 writer stamped it straight back, so
    `schema_version` alternated 2 -> 1 -> 2 forever.
    """
    fixtures = {
        "no_profile": {},
        "v1_profile": {DISCOVER_LLM_METADATA_KEY: _v1_profile(generated_at=NOW - timedelta(days=2))},
        "v2_current_rev": {DISCOVER_LLM_METADATA_KEY: _v2_profile(generated_at=NOW - timedelta(hours=2))},
        "v2_stale_rev": {
            DISCOVER_LLM_METADATA_KEY: _v2_profile(
                generated_at=NOW - timedelta(hours=2), writer_rev=CU_WRITER_REV - 1
            )
        },
        "other_metadata_preserved": {
            "shape": "binary",
            DISCOVER_LLM_METADATA_KEY: _v2_profile(generated_at=NOW - timedelta(hours=2)),
        },
    }

    for label, start in fixtures.items():
        metadata = start
        # Cycle 1 — both beats fire.
        metadata, _ = _v1_writer_cycle(metadata, now=NOW)
        metadata, _ = _v2_writer_cycle(metadata, now=NOW)
        settled = metadata[DISCOVER_LLM_METADATA_KEY]["schema_version"]

        # Cycle 2, six hours later — neither writer may change the version.
        cycle2 = NOW + timedelta(hours=6)
        metadata, v1_action = _v1_writer_cycle(metadata, now=cycle2)
        assert v1_action == "skipped", f"{label}: v1 writer overwrote a v2-owned key"
        assert metadata[DISCOVER_LLM_METADATA_KEY]["schema_version"] == settled, label

        metadata, _ = _v2_writer_cycle(metadata, now=cycle2)
        assert metadata[DISCOVER_LLM_METADATA_KEY]["schema_version"] == settled, label
        assert settled == CU_V2_SCHEMA_VERSION, f"{label}: v2 must own the shared key"

    # Sibling keys under market_metadata survive both writers.
    metadata = fixtures["other_metadata_preserved"]
    assert metadata.get("shape") == "binary"


def test_v1_refresh_predicate_defers_to_a_current_rev_v2_profile():
    metadata = {DISCOVER_LLM_METADATA_KEY: _v2_profile(generated_at=NOW - timedelta(hours=1))}
    assert _cu_v2_profile_owns_key(metadata, now=NOW) is True
    assert _metadata_needs_discover_llm_refresh(metadata, now=NOW) is False


def test_v1_refresh_predicate_defers_to_a_stale_rev_v2_profile():
    """Re-tagging its own older revisions is the v2 writer's job. If v1 grabbed
    them in the meantime, the oscillation is back during every rev bump."""
    metadata = {
        DISCOVER_LLM_METADATA_KEY: _v2_profile(
            generated_at=NOW - timedelta(hours=1), writer_rev=CU_WRITER_REV - 1
        )
    }
    assert _metadata_needs_discover_llm_refresh(metadata, now=NOW) is False
    # ...and the v2 writer does still re-tag it.
    assert _cu_v2_needs_retag(metadata, now=NOW) is True


def test_v1_reclaims_an_abandoned_v2_profile():
    """The one escape hatch: the v2 writer refreshes its own rows every ~24h, so
    a v2 profile older than the ownership window means that beat is dead."""
    metadata = {
        DISCOVER_LLM_METADATA_KEY: _v2_profile(
            generated_at=NOW - timedelta(days=CU_V2_OWNERSHIP_MAX_AGE_DAYS + 1)
        )
    }
    assert _cu_v2_profile_owns_key(metadata, now=NOW) is False
    assert _metadata_needs_discover_llm_refresh(metadata, now=NOW) is True


def test_v1_refresh_predicate_unchanged_for_v1_and_missing_profiles():
    """The gate must not swallow the v1 writer's own freshness behaviour."""
    assert _metadata_needs_discover_llm_refresh({}, now=NOW) is True
    assert _metadata_needs_discover_llm_refresh(None, now=NOW) is True
    fresh = {DISCOVER_LLM_METADATA_KEY: _v1_profile(generated_at=NOW - timedelta(days=3))}
    stale = {DISCOVER_LLM_METADATA_KEY: _v1_profile(generated_at=NOW - timedelta(days=45))}
    assert _metadata_needs_discover_llm_refresh(fresh, now=NOW) is False
    assert _metadata_needs_discover_llm_refresh(stale, now=NOW) is True


def test_v2_retag_predicate_skips_only_fresh_current_rev_profiles():
    current = {DISCOVER_LLM_METADATA_KEY: _v2_profile(generated_at=NOW - timedelta(hours=2))}
    aged = {DISCOVER_LLM_METADATA_KEY: _v2_profile(generated_at=NOW - timedelta(days=2))}
    v1 = {DISCOVER_LLM_METADATA_KEY: _v1_profile(generated_at=NOW)}

    assert _cu_v2_needs_retag(current, now=NOW) is False
    assert _cu_v2_needs_retag(aged, now=NOW) is True
    assert _cu_v2_needs_retag(v1, now=NOW) is True
    assert _cu_v2_needs_retag({}, now=NOW) is True


# --------------------------------------------------------------------------
# Acceptance 2 — v2-profiled markets keep their feed signals
# --------------------------------------------------------------------------


def test_v2_profile_yields_nonzero_adjustment_and_feature_tokens():
    """The regression that cost the feed its LLM signal: this returned 0 and []
    for every v2-profiled market, because the v1-only accessor read them as
    unenriched."""
    metadata = {DISCOVER_LLM_METADATA_KEY: _v2_profile(generated_at=NOW)}

    view = _get_discover_llm_view(metadata)
    assert view is not None

    # stakes 4 + breadth 5 -> salience 5 (+6), broad scope (0), named entities (+2)
    adjustment = _discover_llm_score_adjustment(view)
    assert adjustment == 8

    tokens = _discover_llm_feature_tokens(view)
    assert tokens
    assert "llm_topic:sports" in tokens
    assert "llm_subtopic:soccer" in tokens
    assert "llm_archetype:race" in tokens
    assert "llm_audience_scope:broad" in tokens
    assert "llm_entity:argentina" in tokens
    assert "llm_entity:lionel_messi" in tokens


def test_v2_junk_profile_is_penalized_not_ignored():
    metadata = {
        DISCOVER_LLM_METADATA_KEY: _v2_profile(
            generated_at=NOW,
            stakes=1,
            breadth=1,
            geography="local",
            junk_flags=["ladder", "dated_bucket"],
            arc="none",
        )
    }
    view = _get_discover_llm_view(metadata)
    # salience 1 (-6), local scope (-25), two unknown-vocabulary junk flags (-12),
    # named entities (+2) -> clamped at the v1 floor.
    assert _discover_llm_score_adjustment(view) == -30
    assert view["archetype"] == "other"


def test_v2_junk_flags_map_one_to_one():
    profile = _v2_profile(
        generated_at=NOW, junk_flags=["ladder", "dated_bucket", "social_count", "duplicate_phrasing"]
    )
    adapted = _v2_profile_as_v1_shape(profile)
    assert adapted["junk_flags"] == [
        "ladder",
        "dated_bucket",
        "social_count",
        "duplicate_phrasing",
    ]


def test_v2_salience_and_scope_mapping():
    def adapt(**kwargs):
        return _v2_profile_as_v1_shape(_v2_profile(generated_at=NOW, **kwargs))

    # Mean of stakes and breadth, rounded up on a half (never banker's rounding).
    assert adapt(stakes=1, breadth=1)["salience_score"] == 1
    assert adapt(stakes=4, breadth=5)["salience_score"] == 5
    assert adapt(stakes=3, breadth=3)["salience_score"] == 3
    assert adapt(stakes=5, breadth=5)["salience_score"] == 5

    # Scope comes from breadth...
    assert adapt(breadth=5)["audience_scope"] == "broad"
    assert adapt(breadth=4)["audience_scope"] == "mainstream"
    assert adapt(breadth=3)["audience_scope"] == "mainstream"
    assert adapt(breadth=2)["audience_scope"] == "niche"
    assert adapt(breadth=1)["audience_scope"] == "niche"
    # ...except "local", which is only ever asserted from an explicit geography,
    # because it carries v1's harshest penalty (-25).
    assert adapt(breadth=1, geography="global")["audience_scope"] != "local"
    assert adapt(breadth=5, geography="local")["audience_scope"] == "local"
    # "specialist" has no v2 analogue and must never be guessed.
    scopes = {adapt(breadth=b, geography=g)["audience_scope"] for b in range(1, 6) for g in ("global", "us", "local")}
    assert "specialist" not in scopes


def test_v2_adapter_tolerates_missing_and_malformed_fields():
    sparse = {"schema_version": CU_V2_SCHEMA_VERSION, "topic": "politics"}
    adapted = _v2_profile_as_v1_shape(sparse)
    assert adapted["salience_score"] == 3  # v1's neutral default -> 0 adjustment
    assert adapted["audience_scope"] == "broad"
    assert adapted["entities"] == []
    assert adapted["junk_flags"] == []
    assert adapted["comparison_axes"] == []
    assert _discover_llm_score_adjustment(adapted) == 0
    assert _discover_llm_feature_tokens(adapted) == [
        "llm_topic:politics",
        "llm_archetype:other",
        "llm_audience_scope:broad",
    ]

    malformed = {
        "schema_version": CU_V2_SCHEMA_VERSION,
        "stakes": "high",
        "breadth": None,
        "entities": ["bare string", {"name": None}, {"name": "Real Madrid"}],
        "junk_flags": None,
        "hook_facts": [{"type": "stat"}, {"text": "  a real fact  "}],
    }
    adapted = _v2_profile_as_v1_shape(malformed)
    assert adapted["salience_score"] == 3
    assert adapted["entities"] == ["bare string", "real madrid"]
    assert adapted["junk_flags"] == []
    assert adapted["why_interesting"] == "a real fact"


def test_view_returns_v1_profiles_natively_and_rejects_unknown_versions():
    v1 = _v1_profile(generated_at=NOW)
    assert _get_discover_llm_view({DISCOVER_LLM_METADATA_KEY: v1}) is v1

    assert _get_discover_llm_view(None) is None
    assert _get_discover_llm_view({}) is None
    assert _get_discover_llm_view({DISCOVER_LLM_METADATA_KEY: "nope"}) is None
    assert _get_discover_llm_view({DISCOVER_LLM_METADATA_KEY: {"schema_version": 99}}) is None

    # The v1-only accessor is deliberately NOT loosened: the split brain is closed
    # at the writer predicate and the shared view, not by making v1 read v2.
    assert _get_discover_llm_metadata({DISCOVER_LLM_METADATA_KEY: _v2_profile(generated_at=NOW)}) is None


def test_feed_reads_discover_llm_through_the_shared_view_only():
    """Guard against a future edit re-importing a version-specific accessor into
    the feed path (ruling 021 — two consumers of one input share the DECISION)."""
    import inspect

    from app.routes import feed

    src = inspect.getsource(feed)
    assert "_get_discover_llm_view(" in src
    assert "_get_discover_llm_metadata(" not in src
    assert "_get_cu_v2_profile(" not in src
