"""#1809 — CU v2 quantitative frame (C1) + registry-grounded subject (C2).

The writer gained two additive profile slots behind one `writer_rev` bump:

* **frame** `{measure, comparator, value, unit, horizon_kind}`, governed by a
  property rather than a label — every extracted `value`/`unit` must appear
  LITERALLY in the market title. On violation the sanitizer drops the WHOLE
  frame and keeps the rest of the profile.
* **subjects / subject_ref**, resolved at write time against the entity
  registry and the team-identity index by string/alias match ONLY (no LLM call
  on this path). An unresolved mention is written as an explicit
  `unresolved:<string>` marker, and a market with no mentions at all as
  `unresolved:__none__` — never a silent empty (gotcha #53).

The title fixtures are REAL production market names (sampled from
`futures_markets` on 2026-08-12), because the invariant is only worth what the
title shapes it has actually seen: "13M", "15,000+", "2026-27", "0.1% brackets"
and the `___` placeholder titles are all live rows, and each one is a way a
naive parser has already been wrong at least once.

Clock discipline (gotcha #44): the frame/grounding logic is pure and takes no
clock at all; the one writer test that needs a timestamp derives it by offset
from a frozen `NOW` and asserts nothing about the wall clock. No anchor in this
file branches on the time of day.
"""

import json
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

import pytest

from app.tasks.enrich_markets import (
    CU_V2_SCHEMA_VERSION,
    CU_WRITER_REV,
    DISCOVER_LLM_METADATA_KEY,
    _cu_v2_needs_retag,
    _resolve_entity_refs,
    enrich_cu_v2_profiles,
)
from app.utils.cu_frame import (
    DROP_ABSENT,
    DROP_NO_MEASURE,
    DROP_NOT_AN_OBJECT,
    DROP_UNIT_NOT_IN_TITLE,
    DROP_VALUE_NOT_IN_TITLE,
    NO_SUBJECT_MARKER,
    UNRESOLVED_PREFIX,
    clean_entity_mentions,
    ground_subjects,
    is_resolved_ref,
    normalize_comparator,
    normalize_horizon_kind,
    normalize_measure,
    sanitize_cu_frame,
    unit_appears_in_title,
    value_appears_in_title,
)

NOW = datetime(2026, 8, 12, 12, 0, tzinfo=timezone.utc)

# Real open-market titles, sampled from production 2026-08-12.
T_DRAKE = "Will Drake have above 13M daily views in August 2026?"
T_SINNER = "Will Jannik Sinner have 15,000+ ATP Points Before 2027?"
T_CLARK = "Caitlin Clark to Score 40+ Points in any Game this Season"
T_LEBRON = "LeBron James to Announce his Retirement Before the 2026-27 Season"
T_QUAKE = "Will there be an at least 8.0 magnitude earthquake in California before 2028?"
T_HOUSING = "Will Canada housing starts go above 300K in 2026?"
T_SPY = "S&P 500 (SPY) closes above ___ on August 13?"
T_PERU = "Peru Election 2nd Round: Margin of Victory? (0.1% brackets)"
T_TEMP = "Highest temperature in NYC on Aug 9, 2026?"
T_HURRICANE = "Will 2 or more hurricanes make landfall in the US in 2026?"


# ==========================================================================
# Acceptance: the literal-presence property
# ==========================================================================


class TestLiteralPresenceProperty:
    """Every extracted value/unit appears verbatim in the title — or no frame."""

    @pytest.mark.parametrize(
        "title,value",
        [
            (T_DRAKE, "13M"),
            (T_SINNER, "15,000"),
            (T_CLARK, "40"),
            (T_QUAKE, "8.0"),
            (T_HOUSING, "300K"),
            (T_PERU, "0.1"),
            (T_HURRICANE, "2"),
        ],
    )
    def test_honest_values_are_accepted(self, title, value):
        assert value_appears_in_title(value, title) is True

    @pytest.mark.parametrize(
        "title,value,why",
        [
            (T_DRAKE, "13000000", "13M expanded — the W7M bug class"),
            (T_SINNER, "15000000", "digits invented past the comma group"),
            (T_HOUSING, "300000", "300K expanded"),
            (T_SPY, "6400", "placeholder title states no number at all"),
            (T_CLARK, "4", "fragment of 40"),
            (T_TEMP, "9", "9 only exists inside 'Aug 9,' — see boundary test"),
            (T_QUAKE, "8", "8 is a fragment of 8.0"),
        ],
    )
    def test_invented_values_are_rejected(self, title, value, why):
        # T_TEMP's "9" IS a standalone token ("Aug 9,"), so it is accepted by
        # the literal rule; every other row here must be rejected outright.
        if value == "9":
            assert value_appears_in_title(value, title) is True, why
        else:
            assert value_appears_in_title(value, title) is False, why

    def test_comma_stripped_title_still_counts_as_literal(self):
        # Same digits, same order — 15000 against a title's "15,000".
        assert value_appears_in_title("15000", T_SINNER) is True

    @pytest.mark.parametrize(
        "value,title,expected",
        [
            ("5", "Winner of the 2025 election?", False),   # fragment of 2025
            ("2", "Over 2.5 goals?", False),                # fragment of 2.5
            ("2.5", "Over 2.5 goals?", True),
            ("2025", "Winner of the 2025 election?", True),
            ("25", "Winner of the 2025 election?", False),  # tail fragment
        ],
    )
    def test_number_fragments_never_satisfy_the_property(self, value, title, expected):
        assert value_appears_in_title(value, title) is expected

    def test_season_range_tail_is_not_a_value(self):
        """"2026-27" -> 27 is the named rung bug — dead by construction."""
        assert value_appears_in_title("27", T_LEBRON) is False
        assert value_appears_in_title("2026", T_LEBRON) is True

    def test_spaced_range_is_not_affected_by_the_season_guard(self):
        title = "How many 6.5 or above earthquakes August 10 - August 16?"
        assert value_appears_in_title("16", title) is True
        assert value_appears_in_title("6.5", title) is True

    @pytest.mark.parametrize(
        "unit,title,expected",
        [
            ("Points", T_CLARK, True),          # case-insensitive
            ("points", T_SINNER, True),
            ("%", T_PERU, True),                # symbol unit, substring
            ("percent", T_PERU, False),         # expanded — not literal
            ("m", "Market close above 5?", False),  # no standalone 'm'
            ("M", T_DRAKE, True),               # "13M"
            ("goals", "Over 2.5 goals?", True),
        ],
    )
    def test_unit_literal_presence(self, unit, title, expected):
        assert unit_appears_in_title(unit, title) is expected


class TestFrameSanitizer:
    """Drop the frame, keep the profile — and say which slot failed."""

    def test_honest_frame_survives_intact(self):
        frame, drop = sanitize_cu_frame(
            {
                "measure": "ATP Points",
                "comparator": ">=",
                "value": "15,000",
                "unit": "Points",
                "horizon_kind": "multi_year",
            },
            title=T_SINNER,
        )
        assert drop is None
        assert frame == {
            "measure": "atp_points",
            "comparator": "gte",
            "value": "15,000",
            "unit": "Points",
            "horizon_kind": "multi_year",
        }

    def test_all_five_slots_are_always_present(self):
        frame, _ = sanitize_cu_frame({"measure": "points"}, title=T_CLARK)
        assert set(frame) == {"measure", "comparator", "value", "unit", "horizon_kind"}

    def test_invented_value_drops_the_whole_frame(self):
        frame, drop = sanitize_cu_frame(
            {"measure": "daily_views", "comparator": "gt", "value": 13000000, "unit": "M"},
            title=T_DRAKE,
        )
        assert frame is None
        assert drop == DROP_VALUE_NOT_IN_TITLE

    def test_expanded_unit_drops_the_whole_frame(self):
        frame, drop = sanitize_cu_frame(
            {"measure": "margin", "comparator": "range", "value": "0.1", "unit": "percent"},
            title=T_PERU,
        )
        assert frame is None
        assert drop == DROP_UNIT_NOT_IN_TITLE

    def test_placeholder_title_cannot_carry_a_value(self):
        frame, drop = sanitize_cu_frame(
            {"measure": "index_close", "comparator": "gt", "value": "6400"},
            title=T_SPY,
        )
        assert frame is None
        assert drop == DROP_VALUE_NOT_IN_TITLE

    def test_measureless_frame_is_dropped(self):
        frame, drop = sanitize_cu_frame({"value": "40", "unit": "Points"}, title=T_CLARK)
        assert frame is None
        assert drop == DROP_NO_MEASURE

    @pytest.mark.parametrize("raw,expected", [(None, DROP_ABSENT), ("40+", DROP_NOT_AN_OBJECT), ([], DROP_NOT_AN_OBJECT)])
    def test_absent_and_malformed_frames_report_distinct_reasons(self, raw, expected):
        frame, drop = sanitize_cu_frame(raw, title=T_CLARK)
        assert frame is None
        assert drop == expected

    def test_measure_without_a_number_is_a_valid_frame(self):
        """"Who wins the scoring title?" has a measure and no threshold."""
        frame, drop = sanitize_cu_frame(
            {"measure": "points", "comparator": None, "value": None, "unit": None},
            title="Who wins the scoring title?",
        )
        assert drop is None
        assert frame["measure"] == "points"
        assert frame["value"] is None

    def test_integral_float_value_renders_without_dot_zero(self):
        frame, drop = sanitize_cu_frame(
            {"measure": "points", "value": 40.0}, title=T_CLARK
        )
        assert drop is None
        assert frame["value"] == "40"

    def test_null_strings_are_treated_as_null(self):
        frame, _ = sanitize_cu_frame(
            {"measure": "points", "value": "null", "unit": "none"}, title=T_CLARK
        )
        assert frame["value"] is None
        assert frame["unit"] is None

    @pytest.mark.parametrize(
        "raw,expected",
        [(">=", "gte"), ("at least", "gte"), ("above", "gt"), ("≤", "lte"),
         ("under", "lt"), ("exactly", "eq"), ("between", "range"),
         ("wibble", None), (None, None), (42, None)],
    )
    def test_comparator_vocabulary(self, raw, expected):
        assert normalize_comparator(raw) == expected

    def test_unknown_comparator_does_not_drop_the_frame(self):
        frame, drop = sanitize_cu_frame(
            {"measure": "points", "comparator": "wibble", "value": "40"}, title=T_CLARK
        )
        assert drop is None
        assert frame["comparator"] is None

    @pytest.mark.parametrize(
        "raw,expected",
        [("annual", "annual"), ("multi_year", "multi_year"), ("Daily", "daily"),
         ("fortnightly", None), (None, None)],
    )
    def test_horizon_vocabulary(self, raw, expected):
        assert normalize_horizon_kind(raw) == expected

    @pytest.mark.parametrize(
        "raw,expected",
        [("ATP Points", "atp_points"), ("high temperature", "high_temperature"),
         ("  RT score ", "rt_score"), ("", None), (None, None), (7, None)],
    )
    def test_measure_normalization(self, raw, expected):
        assert normalize_measure(raw) == expected


# ==========================================================================
# Acceptance: grounded subject, with an explicit unresolved marker
# ==========================================================================


class TestGroundSubjects:
    def test_resolved_mentions_carry_registry_refs(self):
        mentions = [{"name": "Boston Celtics", "type": "team"}]
        resolved = {
            "Boston Celtics": {
                "ref": "entity:42", "entity_id": 42, "kind": "team", "source": "registry_alias",
            }
        }
        subjects, ref, entity_id, ok = ground_subjects(mentions, resolved)
        assert ref == "entity:42"
        assert entity_id == 42
        assert ok is True
        assert subjects[0]["match"] == "registry_alias"

    def test_unresolved_mention_gets_an_explicit_marker_never_an_empty(self):
        mentions = [{"name": "Some Obscure FC", "type": "team"}]
        subjects, ref, entity_id, ok = ground_subjects(mentions, {})
        assert ref == f"{UNRESOLVED_PREFIX}Some Obscure FC"
        assert entity_id is None
        assert ok is False
        assert subjects[0]["ref"].startswith(UNRESOLVED_PREFIX)
        # The name survives INSIDE the marker — that is the whole point.
        assert "Some Obscure FC" in subjects[0]["ref"]

    def test_no_mentions_is_distinguishable_from_a_failed_match(self):
        subjects, ref, entity_id, ok = ground_subjects([], {})
        assert subjects == []
        assert ref == NO_SUBJECT_MARKER
        assert ref != f"{UNRESOLVED_PREFIX}"
        assert entity_id is None
        assert ok is False

    def test_resolution_outranks_the_models_ordering(self):
        mentions = [
            {"name": "Unknown United", "type": "team"},   # rank 0, unresolved
            {"name": "Lionel Messi", "type": "person"},   # rank 1, resolved
        ]
        resolved = {
            "Lionel Messi": {
                "ref": "entity:7", "entity_id": 7, "kind": "person", "source": "registry_alias",
            }
        }
        _, ref, entity_id, ok = ground_subjects(mentions, resolved)
        assert (ref, entity_id, ok) == ("entity:7", 7, True)

    def test_type_preference_breaks_ties_among_resolved(self):
        mentions = [
            {"name": "Paris", "type": "place"},
            {"name": "France", "type": "team"},
        ]
        resolved = {
            "Paris": {"ref": "entity:1", "entity_id": 1, "kind": "place", "source": "registry_alias"},
            "France": {"ref": "entity:2", "entity_id": 2, "kind": "team", "source": "registry_alias"},
        }
        _, ref, _, _ = ground_subjects(mentions, resolved)
        assert ref == "entity:2"

    def test_team_ref_is_resolved_even_though_it_has_no_entity_id(self):
        mentions = [{"name": "LAL", "type": "team"}]
        resolved = {
            "LAL": {
                "ref": "team:31", "entity_id": None, "kind": "team",
                "source": "team_identity_mapping",
            }
        }
        subjects, ref, entity_id, ok = ground_subjects(mentions, resolved)
        assert ref == "team:31"
        assert entity_id is None
        # The ref prefix is authoritative, NOT the null entity_id.
        assert ok is True
        assert is_resolved_ref(subjects[0]["ref"]) is True

    def test_every_mention_is_represented_in_subjects(self):
        mentions = [{"name": f"E{i}", "type": "team"} for i in range(5)]
        resolved = {"E2": {"ref": "entity:2", "entity_id": 2, "kind": "team", "source": "registry_alias"}}
        subjects, _, _, _ = ground_subjects(mentions, resolved)
        assert len(subjects) == 5
        assert sum(1 for s in subjects if is_resolved_ref(s["ref"])) == 1
        assert all(s["ref"] for s in subjects)


class TestCleanEntityMentions:
    def test_dict_and_bare_string_forms_both_survive(self):
        out = clean_entity_mentions([{"name": "Celtics", "type": "team"}, "openai"])
        assert out == [
            {"name": "Celtics", "type": "team"},
            {"name": "openai", "type": ""},
        ]

    def test_case_insensitive_dedup_and_junk_rejection(self):
        out = clean_entity_mentions(
            [{"name": "Celtics", "type": "team"}, {"name": "celtics", "type": "team"},
             {"name": "", "type": "team"}, 17, None, {"name": "X", "type": "nonsense"}]
        )
        assert [o["name"] for o in out] == ["Celtics", "X"]
        assert out[1]["type"] == ""

    def test_non_list_input_is_empty(self):
        assert clean_entity_mentions(None) == []
        assert clean_entity_mentions("Celtics") == []


# ==========================================================================
# Acceptance: write-time resolution against registry + team mappings
# ==========================================================================


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def mappings(self):
        return self

    def all(self):
        return self._rows


class _FakeSession:
    """Duck-typed AsyncSession: records statements, replays canned results."""

    def __init__(self, results=None):
        self.results = list(results or [])
        self.executed = []
        self.commits = 0
        self.rollbacks = 0

    async def execute(self, stmt, params=None):
        self.executed.append((stmt, params))
        if self.results:
            return self.results.pop(0)
        return _FakeResult([])

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1


class _FakeEntity:
    def __init__(self, id_, kind):
        self.id = id_
        self.kind = kind


class TestResolveEntityRefs:
    async def test_registry_alias_hit(self, monkeypatch):
        async def fake_resolve_aliases(session, names, **kw):
            return {"Boston Celtics": _FakeEntity(42, "team")}

        monkeypatch.setattr(
            "app.services.entity_registry.resolve_aliases", fake_resolve_aliases
        )
        session = _FakeSession()
        out = await _resolve_entity_refs(session, ["Boston Celtics"])
        assert out["Boston Celtics"] == {
            "ref": "entity:42", "entity_id": 42, "kind": "team", "source": "registry_alias",
        }
        # Registry hit for every name -> no team-mapping fallback query at all.
        assert session.executed == []

    async def test_team_identity_fallback_for_a_registry_miss(self, monkeypatch):
        async def fake_resolve_aliases(session, names, **kw):
            return {}

        monkeypatch.setattr(
            "app.services.entity_registry.resolve_aliases", fake_resolve_aliases
        )
        session = _FakeSession(
            [_FakeResult([{"key": "lakers", "team_count": 1, "team_id": 31}])]
        )
        out = await _resolve_entity_refs(session, ["Lakers"])
        assert out["Lakers"] == {
            "ref": "team:31", "entity_id": None, "kind": "team",
            "source": "team_identity_mapping",
        }

    async def test_ambiguous_team_name_stays_unresolved(self, monkeypatch):
        """NCAA school names collide across sources (#1204) — never guess."""

        async def fake_resolve_aliases(session, names, **kw):
            return {}

        monkeypatch.setattr(
            "app.services.entity_registry.resolve_aliases", fake_resolve_aliases
        )
        session = _FakeSession(
            [_FakeResult([{"key": "wildcats", "team_count": 4, "team_id": 8}])]
        )
        out = await _resolve_entity_refs(session, ["Wildcats"])
        assert out == {}

    async def test_no_names_touches_the_database_not_at_all(self, monkeypatch):
        called = []

        async def fake_resolve_aliases(session, names, **kw):
            called.append(names)
            return {}

        monkeypatch.setattr(
            "app.services.entity_registry.resolve_aliases", fake_resolve_aliases
        )
        session = _FakeSession()
        assert await _resolve_entity_refs(session, ["", "  ", None]) == {}
        assert called == []
        assert session.executed == []


# ==========================================================================
# Acceptance: the writer end-to-end (LLM mocked, sessions faked)
# ==========================================================================


def _llm_payload(**overrides):
    payload = {
        "topic": "sports",
        "subtopic": "basketball",
        "entities": [{"name": "Caitlin Clark", "type": "person"}],
        "geography": "us",
        "story_key": "story:clark_scoring",
        "series_key": None,
        "temporal": "event_tied",
        "event_date": "2026-09-01",
        "recurrence": "one_off",
        "stakes": 2,
        "breadth": 3,
        "oddity": 1,
        "arc": "milestone",
        "hook_facts": [],
        "junk_flags": [],
        "confidence": 0.9,
        "frame": {
            "measure": "points",
            "comparator": "gte",
            "value": "40",
            "unit": "Points",
            "horizon_kind": "annual",
        },
    }
    payload.update(overrides)
    return payload


class _FakeLLMClient:
    def __init__(self, payload):
        self._payload = payload
        self.calls = 0
        outer = self

        class _Completions:
            def create(self, **kwargs):
                outer.calls += 1
                outer.last_prompt = kwargs["messages"][0]["content"]
                return type(
                    "R", (), {
                        "choices": [type("C", (), {
                            "message": type("M", (), {"content": json.dumps(outer._payload)})()
                        })()],
                        "usage": type("U", (), {"prompt_tokens": 900, "completion_tokens": 260})(),
                    },
                )()

        self.chat = type("Chat", (), {"completions": _Completions()})()


@asynccontextmanager
async def _fake_session_cm(session):
    yield session


def _install_writer_fakes(monkeypatch, *, payload, market_name, resolved=None, resolve_raises=False):
    """Wire the writer to fake sessions + a fake LLM. Returns the write session."""
    read_rows = [{
        "id": 1234,
        "name": market_name,
        "source": "kalshi",
        "status": "open",
        "category": "basketball",
        "resolution_date": None,
        "market_metadata": {},
        "outcomes": [{"name": "Yes", "prob": 0.4, "move": 0.0}],
    }]
    read_session = _FakeSession([_FakeResult(read_rows)])
    write_session = _FakeSession()
    resolve_session = _FakeSession()
    sessions = iter([read_session, write_session, resolve_session])

    def fake_get_task_session():
        return _fake_session_cm(next(sessions))

    monkeypatch.setattr(
        "app.tasks.enrich_markets.get_task_session", fake_get_task_session
    )
    monkeypatch.setattr(
        "app.services.llm._get_client", lambda: _FakeLLMClient(payload)
    )

    async def fake_resolve_aliases(session, names, **kw):
        if resolve_raises:
            raise RuntimeError("statement timeout")
        return {
            name: _FakeEntity(hit["entity_id"], hit["kind"])
            for name, hit in (resolved or {}).items()
            if name in names
        }

    monkeypatch.setattr(
        "app.services.entity_registry.resolve_aliases", fake_resolve_aliases
    )

    async def no_sleep(_seconds):
        return None

    monkeypatch.setattr("app.tasks.enrich_markets.asyncio.sleep", no_sleep)
    return write_session


def _written_profile(write_session):
    """Pull the profile out of the recorded Core UPDATE."""
    for stmt, _params in write_session.executed:
        compiled = getattr(stmt, "compile", None)
        if compiled is None:
            continue
        try:
            metadata = compiled().params.get("market_metadata")
        except Exception:
            continue
        if isinstance(metadata, dict) and DISCOVER_LLM_METADATA_KEY in metadata:
            return metadata[DISCOVER_LLM_METADATA_KEY]
    raise AssertionError("no profile was written")


class TestWriterEndToEnd:
    async def test_profile_carries_frame_and_grounded_subject(self, monkeypatch):
        write_session = _install_writer_fakes(
            monkeypatch,
            payload=_llm_payload(),
            market_name=T_CLARK,
            resolved={"Caitlin Clark": {"entity_id": 77, "kind": "person"}},
        )
        stats = await enrich_cu_v2_profiles(limit=1)
        profile = _written_profile(write_session)

        assert profile["writer_rev"] == CU_WRITER_REV
        assert profile["schema_version"] == CU_V2_SCHEMA_VERSION
        assert profile["frame"] == {
            "measure": "points", "comparator": "gte", "value": "40",
            "unit": "Points", "horizon_kind": "annual",
        }
        assert profile["subject_ref"] == "entity:77"
        assert profile["subject_entity_id"] == 77
        assert profile["subject_resolved"] is True
        assert profile["subjects"][0]["name"] == "Caitlin Clark"

        assert stats["frames_written"] == 1
        assert stats["frames_dropped_literal"] == 0
        assert stats["subjects_resolved"] == 1
        assert stats["subject_resolution_rate"] == 1.0
        assert stats["markets_subject_resolved"] == 1

    async def test_literal_violation_drops_the_frame_and_keeps_the_profile(self, monkeypatch):
        """The acceptance's exact contract: frame goes, profile stays."""
        payload = _llm_payload(
            entities=[{"name": "Drake", "type": "person"}],
            frame={"measure": "daily_views", "comparator": "gt",
                   "value": 13000000, "unit": "M", "horizon_kind": "monthly"},
        )
        write_session = _install_writer_fakes(
            monkeypatch, payload=payload, market_name=T_DRAKE, resolved={}
        )
        stats = await enrich_cu_v2_profiles(limit=1)
        profile = _written_profile(write_session)

        assert profile["frame"] is None
        # ...and every other slot is intact — the profile was NOT abandoned.
        assert profile["topic"] == "sports"
        assert profile["stakes"] == 2
        assert profile["liveness"] == "active"
        assert profile["subject_ref"] == f"{UNRESOLVED_PREFIX}Drake"
        assert stats["generated"] == 1
        assert stats["frames_written"] == 0
        assert stats["frames_dropped_literal"] == 1

    async def test_absent_frame_is_written_as_an_explicit_null(self, monkeypatch):
        write_session = _install_writer_fakes(
            monkeypatch,
            payload=_llm_payload(frame=None),
            market_name="Who wins the 2028 Democratic nomination?",
            resolved={},
        )
        stats = await enrich_cu_v2_profiles(limit=1)
        profile = _written_profile(write_session)
        # The KEY exists and is null — an absent key would read to a
        # frame-first consumer as "this writer never ran".
        assert "frame" in profile
        assert profile["frame"] is None
        assert stats["frames_absent"] == 1
        assert stats["frames_dropped_literal"] == 0

    async def test_unresolved_subject_is_marked_never_silently_empty(self, monkeypatch):
        write_session = _install_writer_fakes(
            monkeypatch, payload=_llm_payload(), market_name=T_CLARK, resolved={}
        )
        stats = await enrich_cu_v2_profiles(limit=1)
        profile = _written_profile(write_session)
        assert profile["subject_ref"] == f"{UNRESOLVED_PREFIX}Caitlin Clark"
        assert profile["subject_entity_id"] is None
        assert profile["subject_resolved"] is False
        assert stats["subjects_unresolved"] == 1
        assert stats["subject_resolution_rate"] == 0.0

    async def test_market_with_no_entities_uses_the_none_marker(self, monkeypatch):
        write_session = _install_writer_fakes(
            monkeypatch,
            payload=_llm_payload(entities=[]),
            market_name=T_CLARK,
            resolved={},
        )
        await enrich_cu_v2_profiles(limit=1)
        profile = _written_profile(write_session)
        assert profile["subject_ref"] == NO_SUBJECT_MARKER
        assert profile["subjects"] == []

    async def test_resolver_failure_is_counted_not_swallowed(self, monkeypatch):
        """A resolver error must not read as 'nothing matched' (gotcha #53)."""
        write_session = _install_writer_fakes(
            monkeypatch, payload=_llm_payload(), market_name=T_CLARK,
            resolve_raises=True,
        )
        stats = await enrich_cu_v2_profiles(limit=1)
        profile = _written_profile(write_session)
        assert stats["subject_resolve_errors"] == 1
        assert stats["generated"] == 1  # the profile still got written
        assert profile["subject_resolved"] is False

    async def test_prompt_asks_for_the_frame(self, monkeypatch):
        _install_writer_fakes(
            monkeypatch, payload=_llm_payload(), market_name=T_CLARK, resolved={}
        )
        await enrich_cu_v2_profiles(limit=1)
        from app.tasks.enrich_markets import _CU_V2_PROMPT
        assert "frame" in _CU_V2_PROMPT
        assert "horizon_kind" in _CU_V2_PROMPT
        assert "EXACTLY as the title writes it" in _CU_V2_PROMPT


class TestWriterRevBump:
    """The bump is what makes rev-4 profiles (no frame, no subjects) re-tag."""

    def _profile(self, rev):
        return {
            DISCOVER_LLM_METADATA_KEY: {
                "schema_version": CU_V2_SCHEMA_VERSION,
                "writer_rev": rev,
                # Fresh by age — only the rev may force the re-tag here.
                "generated_at": (NOW - timedelta(minutes=5)).isoformat(),
            }
        }

    def test_previous_rev_is_retagged_even_when_fresh(self):
        assert _cu_v2_needs_retag(self._profile(CU_WRITER_REV - 1), now=NOW) is True

    def test_current_rev_still_earns_the_freshness_skip(self):
        assert _cu_v2_needs_retag(self._profile(CU_WRITER_REV), now=NOW) is False

    def test_rev_is_ahead_of_the_frameless_revision(self):
        assert CU_WRITER_REV >= 5
