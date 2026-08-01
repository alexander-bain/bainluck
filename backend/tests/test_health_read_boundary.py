"""Queue #294 / C102 — the fail-honest health-rail contract.

The defect these guard against is not "the endpoint crashed"; it is "the
endpoint answered confidently while blind". Nine health rails wrapped their
Redis read in a bare ``except: return None``, so five very different conditions
arrived downstream as one value:

    dependency loss · missing key · malformed bytes · wrong JSON type · stale run

Downstream that became ``no_data`` / ``no_run_cached`` / a zero / an opaque 500,
and in the worst case a GREEN cockpit tile coloured from a legacy score during a
Redis outage. Every test here pins ONE of those cases staying distinguishable.

Table-driven where the same matrix applies to many rails, because the regression
risk is a rail being added later without the boundary.
"""

import json
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from app.utils import candidate_base as cb
from app.utils import health_reads as hr

# --- Fixtures / helpers ------------------------------------------------------

BOOM = RuntimeError("Error 111 connecting to rediss://h:secretpw@ec2.example:6379. ECONNREFUSED.")


_UNSET = object()


def _client(get=_UNSET, **extra):
    """A MagicMock Redis whose GET behaviour is scripted per test.

    ``get=None`` means "the key is absent" — distinct from omitting ``get``,
    which is exactly the missing-vs-unset conflation this whole file is about.
    """
    r = MagicMock()
    if get is not _UNSET:
        r.get.side_effect = get if callable(get) else (lambda _k: get)
    for name, value in extra.items():
        setattr(r, name, value)
    return r


def _dead_get(_key):
    raise BOOM


def _patch_client(r):
    """Patch the factory the boundary imports (it imports at call time)."""
    return patch("app.tasks.redis_state.get_redis_client", return_value=r)


def _dead_client():
    return patch("app.tasks.redis_state.get_redis_client", side_effect=BOOM)


_ADMIN_AUTH = patch("app.routes.admin._check_admin_secret", return_value=True)


# --- The boundary itself -----------------------------------------------------


class TestRedisReadClassification:
    """One read → exactly one of five statuses, never a collapse."""

    @pytest.mark.parametrize(
        "raw,expected",
        [
            (json.dumps({"a": 1}), hr.OK),
            (None, hr.MISSING),
            (b"{not json", hr.MALFORMED),
            ('"a string"', hr.WRONG_SHAPE),
            ("[1, 2, 3]", hr.WRONG_SHAPE),
            ("42", hr.WRONG_SHAPE),
            ("null", hr.WRONG_SHAPE),
        ],
    )
    def test_json_statuses(self, raw, expected):
        read = hr.read_json(_client(get=raw), "k")
        assert read.status == expected

    def test_command_failure_is_unavailable_not_missing(self):
        """The distinction the whole queue exists for."""
        read = hr.read_json(_client(get=_dead_get), "k")
        assert read.status == hr.UNAVAILABLE
        assert read.missing is False
        assert read.error_class == "RuntimeError"

    def test_bytes_payload_decodes(self):
        read = hr.read_json(_client(get=b'{"a": 1}'), "k")
        assert read.ok and read.value == {"a": 1}

    def test_expect_type_is_honoured(self):
        assert hr.read_json(_client(get="[1,2]"), "k", expect=list).ok
        assert hr.read_json(_client(get="[1,2]"), "k", expect=(dict, list)).ok

    def test_read_text_scalar(self):
        assert hr.read_text(_client(get=b"0"), "k").value == "0"
        assert hr.read_text(_client(get=None), "k").status == hr.MISSING
        assert hr.read_text(_client(get=_dead_get), "k").status == hr.UNAVAILABLE

    def test_client_construction_failure_classified(self):
        with _dead_client():
            conn, failure = hr.client(key="k")
        assert conn is None
        assert failure.status == hr.UNAVAILABLE

    def test_client_construction_success(self):
        with _patch_client(_client(get=None)):
            conn, failure = hr.client(key="k")
        assert conn is not None and failure is None

    def test_command_wrapper_classifies_arbitrary_commands(self):
        ok = hr.command("q", lambda: 7)
        assert ok.ok and ok.value == 7
        bad = hr.command("q", _fail)
        assert bad.status == hr.UNAVAILABLE

    def test_degraded_excludes_missing(self):
        """`missing` is an ANSWER. Only the other three are degradation."""
        assert hr.RedisRead(hr.MISSING, "k").degraded is False
        for status in (hr.MALFORMED, hr.WRONG_SHAPE, hr.UNAVAILABLE):
            assert hr.RedisRead(status, "k").degraded is True


def _fail():
    raise BOOM


class TestRedaction:
    """An admin payload is not a place to publish the Redis password."""

    def test_credentials_stripped_from_url(self):
        text = hr.redact(BOOM)
        assert "secretpw" not in text
        assert "***" in text

    @pytest.mark.parametrize(
        "message",
        [
            "auth failed: password=hunter2",
            "bad token=abc123def",
            "AUTH: secret=s3kr3t",
        ],
    )
    def test_credential_pairs_stripped(self, message):
        out = hr.redact(RuntimeError(message))
        for leaked in ("hunter2", "abc123def", "s3kr3t"):
            assert leaked not in out

    def test_bounded_length(self):
        assert len(hr.redact(RuntimeError("x" * 5000))) <= 160

    def test_empty_message_falls_back_to_class(self):
        assert hr.redact(ValueError("")) == "ValueError"

    def test_read_never_exposes_raw_payload(self):
        """A malformed payload's BYTES must not ride out in the error."""
        read = hr.read_json(_client(get='{"candidate_ids": [99991'), "k")
        assert read.status == hr.MALFORMED
        assert "99991" not in json.dumps(read.as_status())


class TestAgeAndCompleteness:
    def test_age_of_iso_stamp(self):
        stamp = (datetime.now(timezone.utc) - timedelta(seconds=120)).isoformat()
        assert 118 <= hr.age_seconds(stamp) <= 122

    def test_z_suffix_parsed(self):
        assert hr.age_seconds("2026-07-31T00:00:00Z") is not None

    def test_clock_skew_reported_negative_not_clamped(self):
        """A future stamp is skew. Clamping it to 0 hides the condition the
        production reader rejects on."""
        future = (datetime.now(timezone.utc) + timedelta(seconds=600)).isoformat()
        assert hr.age_seconds(future) < 0

    @pytest.mark.parametrize("value", [None, "", "not-a-date", 12345, {}])
    def test_unparseable_stamps_are_none(self, value):
        assert hr.age_seconds(value) is None

    def test_completeness_rollup(self):
        ok, missing = hr.RedisRead(hr.OK, "a"), hr.RedisRead(hr.MISSING, "b")
        dead = hr.RedisRead(hr.UNAVAILABLE, "c")
        assert hr.completeness({"a": ok, "b": missing})["status"] == "complete"
        assert hr.completeness({"a": ok, "c": dead})["status"] == "partial"
        assert hr.completeness({"c": dead})["status"] == "unavailable"
        assert hr.completeness({})["status"] == "complete"

    def test_completeness_names_the_degraded_fields(self):
        rolled = hr.completeness(
            {"a": hr.RedisRead(hr.OK, "a"), "z": hr.RedisRead(hr.MALFORMED, "z")}
        )
        assert rolled["degraded_fields"] == ["z"]
        assert rolled["fields_degraded"] == 1


# --- Leaf rails: the six sentinel /last endpoints ----------------------------

_LAST_RAILS = [
    ("get_calibration_sentinel_last", "bainluck:calibration_sentinel:last"),
    ("get_flow_sentinel_last", "bainluck:flow_sentinel:last"),
    ("get_grid_sentinel_last", "bainluck:grid_sentinel:last"),
    ("get_board_sentinel_last", "bainluck:board_sentinel:last"),
    ("get_horizon_sentinel_last", "bainluck:horizon_sentinel:last"),
    ("get_settled_concept_sentinel_last", "bainluck:settled_concept_sentinel:last"),
]


def _call_rail(name, r=None, dead=False):
    """Call a rail directly.

    NB: calling a FastAPI handler outside the framework leaves un-passed params
    as their ``Query(...)`` objects, which are TRUTHY — so a bool flag like
    ``backtest`` must be passed explicitly or it silently reads the other key.
    """
    import asyncio
    import inspect

    import app.routes.admin as admin_mod

    fn = getattr(admin_mod, name)
    kwargs = {}
    if "backtest" in inspect.signature(fn).parameters:
        kwargs["backtest"] = False
    ctx = _dead_client() if dead else _patch_client(r)
    with _ADMIN_AUTH, ctx:
        return asyncio.run(fn(MagicMock(), "secret", **kwargs))


@pytest.mark.parametrize("name,key", _LAST_RAILS)
class TestSentinelLastRails:
    """#1197: every one of these was an unguarded GET + json.loads."""

    def test_construction_failure_is_503(self, name, key):
        with pytest.raises(HTTPException) as exc:
            _call_rail(name, dead=True)
        assert exc.value.status_code == 503
        assert "secretpw" not in str(exc.value.detail)

    def test_command_failure_is_503_not_500(self, name, key):
        with pytest.raises(HTTPException) as exc:
            _call_rail(name, r=_client(get=_dead_get))
        assert exc.value.status_code == 503

    def test_missing_key_is_no_run_cached(self, name, key):
        out = _call_rail(name, r=_client(get=None))
        assert out == {"status": "no_run_cached", "key": key}

    def test_malformed_is_explicit_not_500(self, name, key):
        out = _call_rail(name, r=_client(get=b"{not json"))
        assert out["status"] == "unparseable"
        assert out["error_class"] == "JSONDecodeError"

    def test_wrong_shape_is_explicit(self, name, key):
        """A bare list used to be returned verbatim as if it were a scorecard."""
        out = _call_rail(name, r=_client(get="[1, 2, 3]"))
        assert out["status"] == "wrong_shape"

    def test_happy_path_returns_payload_verbatim(self, name, key):
        payload = {"status": "green", "scorecard": {"flows_total": 4}}
        out = _call_rail(name, r=_client(get=json.dumps(payload)))
        assert out == payload

    def test_requires_admin_auth(self, name, key):
        import asyncio

        import app.routes.admin as admin_mod

        with patch(
            "app.routes.admin._check_admin_secret",
            side_effect=HTTPException(status_code=403, detail="no"),
        ):
            with pytest.raises(HTTPException) as exc:
                asyncio.run(getattr(admin_mod, name)(MagicMock(), None))
        assert exc.value.status_code == 403


def test_calibration_backtest_variant_uses_its_own_key():
    import asyncio

    import app.routes.admin as admin_mod

    with _ADMIN_AUTH, _patch_client(_client(get=None)):
        out = asyncio.run(
            admin_mod.get_calibration_sentinel_last(MagicMock(), "s", backtest=True)
        )
    assert out["key"] == "bainluck:calibration_sentinel:last_backtest"


# --- Latency rail ------------------------------------------------------------


class TestLatencyRail:
    """C102: only the FIRST command was guarded; every per-endpoint
    ZRANGEBYSCORE ran outside the boundary."""

    def _call(self, r=None, dead=False, top=50):
        import asyncio

        import app.routes.admin as admin_mod

        ctx = _dead_client() if dead else _patch_client(r)
        with _ADMIN_AUTH, ctx:
            return asyncio.run(
                admin_mod.get_latency_stats(MagicMock(), "s", top=top)
            )

    def _sample(self, ms):
        return f"{time.time()}:{ms}"

    def test_construction_failure_is_503(self):
        with pytest.raises(HTTPException) as exc:
            self._call(dead=True)
        assert exc.value.status_code == 503

    def test_smembers_failure_is_503(self):
        r = _client(smembers=MagicMock(side_effect=BOOM))
        with pytest.raises(HTTPException) as exc:
            self._call(r)
        assert exc.value.status_code == 503

    def test_later_command_failure_no_longer_opaque_500(self):
        """The exact C102 case: SMEMBERS succeeds, then the connection drops."""
        r = _client(
            smembers=MagicMock(return_value={"a", "b"}),
            zrangebyscore=MagicMock(side_effect=BOOM),
        )
        with pytest.raises(HTTPException) as exc:
            self._call(r)
        assert exc.value.status_code == 503
        assert "secretpw" not in str(exc.value.detail)

    def test_mixed_success_keeps_siblings_and_names_the_failure(self):
        """One endpoint readable, one not → 200 with both facts."""

        def _zrange(key, *_a, **_kw):
            if key == "latency:good":
                return [self._sample(120) for _ in range(30)]
            raise BOOM

        r = _client(
            smembers=MagicMock(return_value={"good", "bad"}),
            zrangebyscore=MagicMock(side_effect=_zrange),
        )
        out = self._call(r)
        assert [e["endpoint"] for e in out["endpoints"]] == ["good"]
        assert out["completeness"] == "partial"
        assert out["unreadable_endpoints"][0]["endpoint"] == "bad"
        assert out["unreadable_endpoints"][0]["status"] == hr.UNAVAILABLE

    def test_all_healthy_is_complete(self):
        r = _client(
            smembers=MagicMock(return_value={"good"}),
            zrangebyscore=MagicMock(
                return_value=[self._sample(100) for _ in range(30)]
            ),
        )
        out = self._call(r)
        assert out["completeness"] == "complete"
        assert out["unreadable_endpoints"] == []

    def test_genuinely_empty_window_is_not_an_error(self):
        """An endpoint set with no samples in the hour is quiet, not broken."""
        r = _client(
            smembers=MagicMock(return_value={"good"}),
            zrangebyscore=MagicMock(return_value=[]),
        )
        out = self._call(r)
        assert out["endpoints"] == []
        assert out["completeness"] == "complete"

    def test_no_endpoints_tracked_keeps_its_note(self):
        r = _client(smembers=MagicMock(return_value=set()))
        assert self._call(r)["note"] == "No latency data collected yet"


# --- Candidate-base rail -----------------------------------------------------


def _envelope(identity, *, age_s=5.0, ids=(1, 2, 3), schema=None):
    generated = datetime.now(timezone.utc) - timedelta(seconds=age_s)
    return {
        "schema_version": schema or cb.CANDIDATE_BASE_SCHEMA_VERSION,
        "generated_at": generated.isoformat(),
        "generated_epoch_ms": int(generated.timestamp() * 1000),
        "identity": identity,
        "candidate_ids": list(ids),
        "external_curator_recall_ids": [],
        "pool_counts": {"volume": 2},
        "source_watermark": generated.isoformat(),
    }


class TestCandidateBaseHonesty:
    def _call(self, store, *, fail_keys=()):
        import asyncio

        import app.routes.admin as admin_mod

        def _get(key):
            if key in fail_keys:
                raise BOOM
            return store.get(key)

        r = _client(get=_get, ttl=MagicMock(return_value=600))
        with _ADMIN_AUTH, _patch_client(r):
            return asyncio.run(admin_mod.get_candidate_base_state(MagicMock(), "s"))

    def setup_method(self):
        self.identity = cb.base_identity(None, None)
        self.fresh_key, self.last_good_key = cb._redis_keys(self.identity)
        self.on = {cb.CANDIDATE_BASE_ENABLED_KEY: "1"}

    def test_fresh_key_serves_fresh(self):
        out = self._call(
            {**self.on, self.fresh_key: json.dumps(_envelope(self.identity, age_s=5))}
        )
        assert out["would_serve"] == cb.PROV_FRESH
        assert out["status"] == "enabled"
        assert out["completeness"]["status"] == "complete"

    def test_expired_last_good_is_not_advertised_as_serveable(self):
        """C102: ANY structurally valid last-good used to read as serveable,
        even long past CANDIDATE_BASE_LAST_GOOD_MAX_AGE_S."""
        stale = cb.CANDIDATE_BASE_LAST_GOOD_MAX_AGE_S + 600
        out = self._call(
            {
                **self.on,
                self.last_good_key: json.dumps(
                    _envelope(self.identity, age_s=stale)
                ),
            }
        )
        assert out["would_serve"] == cb.PROV_DIRECT
        assert out["keys"]["last_good"]["valid"] is True  # structurally fine…
        assert out["keys"]["last_good"]["within_last_good_max_age"] is False  # …but old

    def test_last_good_just_inside_max_age_still_serves(self):
        inside = cb.CANDIDATE_BASE_LAST_GOOD_MAX_AGE_S - 60
        out = self._call(
            {
                **self.on,
                self.last_good_key: json.dumps(
                    _envelope(self.identity, age_s=inside)
                ),
            }
        )
        assert out["would_serve"] == cb.PROV_LAST_GOOD

    def test_stale_fresh_key_falls_through_to_last_good(self):
        """Mirrors the reader: an aged FRESH key is itself a last-good."""
        out = self._call(
            {
                **self.on,
                self.fresh_key: json.dumps(
                    _envelope(self.identity, age_s=cb.CANDIDATE_BASE_FRESH_SECONDS + 120)
                ),
            }
        )
        assert out["would_serve"] == cb.PROV_LAST_GOOD

    def test_clock_skew_envelope_is_not_served(self):
        """A future-stamped envelope is rejected by `_usable` (age < 0)."""
        out = self._call(
            {**self.on, self.fresh_key: json.dumps(_envelope(self.identity, age_s=-600))}
        )
        assert out["would_serve"] == cb.PROV_DIRECT
        assert out["keys"]["fresh"]["age_seconds"] < 0  # reported, not clamped
        assert out["keys"]["fresh"]["is_fresh"] is False

    def test_wrong_identity_envelope_is_not_served(self):
        out = self._call(
            {**self.on, self.fresh_key: json.dumps(_envelope("some:other:identity"))}
        )
        assert out["would_serve"] == cb.PROV_DIRECT

    def test_wrong_schema_version_is_not_served(self):
        out = self._call(
            {**self.on, self.fresh_key: json.dumps(_envelope(self.identity, schema=1))}
        )
        assert out["would_serve"] == cb.PROV_DIRECT

    def test_wrong_json_type_does_not_500(self):
        """C102: a valid-JSON list reached an unguarded `envelope.get`."""
        out = self._call({**self.on, self.fresh_key: "[1, 2, 3]"})
        assert out["keys"]["fresh"]["key_status"] == hr.WRONG_SHAPE
        assert out["keys"]["fresh"]["valid"] is False
        assert out["would_serve"] == cb.PROV_DIRECT

    def test_one_payload_key_unreadable_is_partial_not_enabled(self):
        """The switch reading fine does not make the base's state known."""
        out = self._call(self.on, fail_keys={self.fresh_key})
        assert out["status"] == "partial"
        assert out["degraded_keys"] == ["fresh"]
        assert out["keys"]["fresh"]["present"] is None  # unknown, not False

    def test_all_payload_keys_unreadable_is_unavailable(self):
        out = self._call(self.on, fail_keys={self.fresh_key, self.last_good_key})
        assert out["status"] == "unavailable"
        assert out["would_serve"] is None
        assert out["would_serve_status"] == "unknown"

    def test_switch_read_failure_is_unavailable(self):
        out = self._call({}, fail_keys={cb.CANDIDATE_BASE_ENABLED_KEY})
        assert out["status"] == "unavailable"
        assert out["enabled"] is None

    def test_kill_switch_off_still_wins(self):
        out = self._call({cb.CANDIDATE_BASE_ENABLED_KEY: "0"})
        assert out["would_serve"] == cb.PROV_DISABLED

    def test_never_exposes_candidate_ids_or_credentials(self):
        out = self._call(
            {
                **self.on,
                self.fresh_key: json.dumps(
                    _envelope(self.identity, ids=(99991, 99992))
                ),
            },
            fail_keys={self.last_good_key},
        )
        blob = json.dumps(out)
        assert "99991" not in blob
        assert "secretpw" not in blob

    def test_clock_disagreement_between_the_two_stamps_is_flagged(self):
        """`generated_at` (what the reader gates on) and `generated_epoch_ms`
        (the publication clock) must agree; a hand-written envelope where they
        do not would otherwise be judged on a different age than reported."""
        env = _envelope(self.identity, age_s=5)
        env["generated_epoch_ms"] -= 3_600_000
        out = self._call({**self.on, self.fresh_key: json.dumps(env)})
        assert out["keys"]["fresh"]["clock_disagreement_s"] is not None


# --- Category precompute rail ------------------------------------------------


class TestCategoryPrecomputeRail:
    def _call(self, r=None, dead=False):
        import asyncio

        import app.routes.admin as admin_mod

        ctx = _dead_client() if dead else _patch_client(r)
        with _ADMIN_AUTH, ctx:
            return asyncio.run(
                admin_mod.get_category_precompute_last(MagicMock(), "s")
            )

    def test_dependency_loss_is_503(self):
        with pytest.raises(HTTPException) as exc:
            self._call(r=_client(get=_dead_get))
        assert exc.value.status_code == 503

    def test_missing_stays_unknown(self):
        assert self._call(r=_client(get=None))["status"] == "unknown"

    def test_malformed_stays_unparseable(self):
        assert self._call(r=_client(get=b"{oops"))["status"] == "unparseable"

    def test_wrong_shape_is_new_and_explicit(self):
        out = self._call(r=_client(get="[]"))
        assert out["status"] == "wrong_shape"
        assert out["report"] is None

    def test_schema_validation_flags_a_report_without_sections(self):
        out = self._call(r=_client(get=json.dumps({"grid_leagues": {}})))
        assert out["status"] == "incomplete_schema"
        assert out["missing_fields"] == ["sections"]

    def test_freshness_annotated_from_the_producers_stamp(self):
        started = (datetime.now(timezone.utc) - timedelta(seconds=300)).isoformat()
        out = self._call(
            r=_client(get=json.dumps({"sections": {}, "started_at": started}))
        )
        assert out["status"] == "ok"
        assert 295 <= out["age_seconds"] <= 305
        assert out["stale"] is False


# --- Ops snapshot composition ------------------------------------------------


class TestOpsSnapshotProvenance:
    def _snapshot(self, *, warm=None, dead=False, fresh=True):

        import app.routes.admin as admin_mod
        import app.tasks.redis_state as rs

        admin_mod._OPS_SNAPSHOT_CACHE["at"] = 0.0
        admin_mod._OPS_SNAPSHOT_CACHE["data"] = None
        return self._compute(admin_mod, rs, warm, dead, fresh)

    def _compute(self, admin_mod, rs, warm, dead, fresh):
        import asyncio

        warm = warm or {}

        def _get(key):
            if dead:
                raise BOOM
            value = warm.get(key)
            return json.dumps(value) if isinstance(value, (dict, list)) else value

        r = _client(get=_get, llen=MagicMock(return_value=0))
        with _ADMIN_AUTH, patch.object(rs, "get_redis_client", lambda *a, **k: r), patch.object(
            rs, "get_task_metrics", lambda label: {"health": "healthy"}
        ), patch.object(rs, "get_all_task_metrics", lambda: []), patch.object(
            rs, "get_odds_api_quota", lambda: {"remaining": 1}
        ):
            return asyncio.run(
                admin_mod.get_ops_snapshot(request=MagicMock(), secret="s", fresh=fresh)
            )

    def test_redis_down_is_unavailable_not_no_data(self):
        """The headline C102 defect: an outage wearing the cold-cache costume."""
        snap = self._snapshot(dead=True)
        for field in ("link_rate", "matured_linkage", "time_horizon", "sentry"):
            assert snap[field]["status"] == hr.UNAVAILABLE, field
            assert snap[field]["error_class"] == "RuntimeError"
        assert snap["sentinels"]["grid"]["status"] == hr.UNAVAILABLE
        assert snap["completeness"]["status"] == "unavailable"

    def test_genuine_cold_cache_still_reads_no_data(self):
        """The honest cold case must NOT be renamed — it stays distinguishable
        from the outage above."""
        snap = self._snapshot(warm={})
        assert snap["link_rate"]["status"] == "no_data"
        assert snap["sentry"]["status"] == "no_data"
        assert snap["completeness"]["status"] == "complete"

    def test_mixed_composite_reports_partial(self):
        """One warm key present, the rest missing → complete (all readable)."""
        snap = self._snapshot(
            warm={"bainluck:flow_sentinel:last": {"status": "green", "filed": []}}
        )
        assert snap["sentinels"]["flow"]["status"] == "green"
        assert snap["completeness"]["status"] == "complete"

    def test_malformed_key_is_malformed_not_no_data(self):
        snap = self._snapshot(warm={"bainluck:sentry:top_24h": "{broken"})
        assert snap["sentry"]["status"] == hr.MALFORMED
        assert snap["completeness"]["status"] == "partial"
        assert snap["completeness"]["degraded_fields"] == ["sentry"]

    def test_wrong_shape_key_is_wrong_shape(self):
        snap = self._snapshot(warm={"bainluck:admin:link_rate": [1, 2]})
        assert snap["link_rate"]["status"] == hr.WRONG_SHAPE

    def test_sentry_no_token_survives_untouched(self):
        """#1501: no_token, no_data, and unavailable are three states."""
        snap = self._snapshot(
            warm={"bainluck:sentry:top_24h": {"status": "no_token", "issues": []}}
        )
        assert snap["sentry"]["status"] == "no_token"

    def test_genuine_zero_queue_depth_is_not_an_error(self):
        assert self._snapshot(warm={})["celery"]["queue_depths"]["background"] == 0

    def test_unreadable_queue_depth_is_a_status_not_a_zero(self):
        import asyncio

        import app.routes.admin as admin_mod
        import app.tasks.redis_state as rs

        admin_mod._OPS_SNAPSHOT_CACHE["at"] = 0.0
        admin_mod._OPS_SNAPSHOT_CACHE["data"] = None
        r = _client(get=lambda _k: None, llen=MagicMock(side_effect=BOOM))
        with _ADMIN_AUTH, patch.object(rs, "get_redis_client", lambda *a, **k: r), patch.object(
            rs, "get_task_metrics", lambda label: {"health": "healthy"}
        ), patch.object(rs, "get_all_task_metrics", lambda: []), patch.object(
            rs, "get_odds_api_quota", lambda: {"remaining": 1}
        ):
            snap = asyncio.run(
                admin_mod.get_ops_snapshot(request=MagicMock(), secret="s", fresh=True)
            )
        depth = snap["celery"]["queue_depths"]["background"]
        assert isinstance(depth, dict) and depth["status"] == hr.UNAVAILABLE

    def test_task_metric_failure_keeps_its_error_status(self):
        import asyncio

        import app.routes.admin as admin_mod
        import app.tasks.redis_state as rs

        admin_mod._OPS_SNAPSHOT_CACHE["at"] = 0.0
        admin_mod._OPS_SNAPSHOT_CACHE["data"] = None

        def _boom(_label):
            raise BOOM

        r = _client(get=lambda _k: None, llen=MagicMock(return_value=0))
        with _ADMIN_AUTH, patch.object(rs, "get_redis_client", lambda *a, **k: r), patch.object(
            rs, "get_task_metrics", _boom
        ), patch.object(rs, "get_all_task_metrics", lambda: []), patch.object(
            rs, "get_odds_api_quota", lambda: {"remaining": 1}
        ):
            snap = asyncio.run(
                admin_mod.get_ops_snapshot(request=MagicMock(), secret="s", fresh=True)
            )
        assert snap["cal_beat"]["status"] == "error"
        assert "secretpw" not in json.dumps(snap)

    def test_cache_hit_carries_source_and_age(self):
        import asyncio

        import app.routes.admin as admin_mod
        import app.tasks.redis_state as rs

        self._snapshot(warm={})  # populate
        admin_mod._OPS_SNAPSHOT_CACHE["at"] = time.time() - 42
        r = _client(get=lambda _k: None, llen=MagicMock(return_value=0))
        with _ADMIN_AUTH, patch.object(rs, "get_redis_client", lambda *a, **k: r):
            snap = asyncio.run(
                admin_mod.get_ops_snapshot(request=MagicMock(), secret="s", fresh=False)
            )
        assert snap["cache"] == "hit"
        assert 41 <= snap["cache_age_s"] <= 44
        assert snap["cache_source"] == "in_process"

    def test_fresh_bypass_reports_the_fresh_failure_not_the_old_success(self):
        """`fresh=true` during an outage must not resurrect a cached success."""
        healthy = self._snapshot(
            warm={"bainluck:admin:link_rate": {"overall": {"link_rate_pct": 100}}}
        )
        assert healthy["link_rate"]["overall"]["link_rate_pct"] == 100

        import app.routes.admin as admin_mod
        import app.tasks.redis_state as rs

        # Cache is warm with the healthy payload; now the store dies.
        degraded = self._compute(admin_mod, rs, None, True, True)
        assert degraded["link_rate"]["status"] == hr.UNAVAILABLE
        assert degraded["cache"] == "miss"

    def test_degraded_snapshot_is_cached_only_with_its_provenance(self):
        """A degraded snapshot may be cached, but it can never later be served
        as an ordinary healthy beat."""
        import asyncio

        import app.routes.admin as admin_mod
        import app.tasks.redis_state as rs

        self._snapshot(dead=True)
        r = _client(get=lambda _k: None, llen=MagicMock(return_value=0))
        with _ADMIN_AUTH, patch.object(rs, "get_redis_client", lambda *a, **k: r):
            served = asyncio.run(
                admin_mod.get_ops_snapshot(request=MagicMock(), secret="s", fresh=False)
            )
        assert served["cache"] == "hit"
        assert served["completeness"]["status"] == "unavailable"
        assert served["link_rate"]["status"] == hr.UNAVAILABLE

    def test_requires_admin_auth(self):
        import asyncio

        import app.routes.admin as admin_mod

        with patch(
            "app.routes.admin._check_admin_secret",
            side_effect=HTTPException(status_code=403, detail="no"),
        ):
            with pytest.raises(HTTPException):
                asyncio.run(
                    admin_mod.get_ops_snapshot(request=MagicMock(), secret=None, fresh=True)
                )


# --- Cockpit composition -----------------------------------------------------


class TestCockpitFailHonesty:
    def _groups(self, store=None, dead=False):
        import app.routes.admin_cockpit as ck

        store = store or {}

        def _get(key):
            if dead:
                raise BOOM
            value = store.get(key)
            return json.dumps(value) if isinstance(value, (dict, list)) else value

        return ck, _patch_client(_client(get=_get))

    def test_grid_verdict_unreadable_is_unknown_with_cause(self):
        ck, ctx = self._groups(dead=True)
        with ctx:
            group = ck._grid_sentinel_group()
        assert group["status"] == "unknown"
        assert group["unreadable"] is True
        assert group["read_status"] == hr.UNAVAILABLE
        assert "secretpw" not in json.dumps(group)

    def test_grid_verdict_never_run_still_returns_none_for_legacy_fallback(self):
        """The legacy raw-score fallback stays legal for a GENUINE never-run."""
        ck, ctx = self._groups({})
        with ctx:
            assert ck._grid_sentinel_group() is None

    def test_grid_malformed_verdict_is_unknown_not_fallback(self):
        ck, ctx = self._groups({"bainluck:grid_sentinel:last": "{broken"})
        with ctx:
            group = ck._grid_sentinel_group()
        assert group["unreadable"] is True

    def test_grid_tile_does_not_colour_from_legacy_score_when_verdict_unreadable(self):
        """THE false-green. A dependency outage must not borrow GREEN from the
        raw audit average this codebase documents as crying wolf."""
        import app.routes.admin_cockpit as ck

        unreadable = ck._unknown_group(
            hr.RedisRead(hr.UNAVAILABLE, "bainluck:grid_sentinel:last", error="EOF"),
            "Grid Sentinel verdict",
            {"per_league": []},
        )
        assert unreadable["status"] == "unknown"
        assert unreadable["per_league"] == []
        # And the tile branch keyed off `unreadable` never reads `avg_score`.
        assert unreadable.get("numeric") is None

    def test_flow_group_distinguishes_unreadable_from_never_run(self):
        ck, dead_ctx = self._groups(dead=True)
        with dead_ctx:
            assert ck._flow_sentinel_group()["unreadable"] is True
        _, cold_ctx = self._groups({})
        with cold_ctx:
            cold = ck._flow_sentinel_group()
        assert cold["status"] == "unknown" and cold["unreadable"] is False

    def test_data_quality_group_distinguishes_unreadable_from_never_run(self):
        ck, dead_ctx = self._groups(dead=True)
        with dead_ctx:
            assert ck._data_quality_group()["unreadable"] is True
        _, cold_ctx = self._groups({})
        with cold_ctx:
            assert ck._data_quality_group()["unreadable"] is False

    def test_queue_depths_report_their_failure(self):
        import app.routes.admin_cockpit as ck

        r = _client(get=lambda _k: None, llen=MagicMock(side_effect=BOOM))
        with _patch_client(r):
            depths = ck._queue_depths()
        assert depths["background"] is None
        assert depths["errors"]["background"]["status"] == hr.UNAVAILABLE

    def test_queue_depths_zero_is_still_zero(self):
        import app.routes.admin_cockpit as ck

        r = _client(get=lambda _k: None, llen=MagicMock(return_value=0))
        with _patch_client(r):
            depths = ck._queue_depths()
        assert depths["background"] == 0 and depths["errors"] == {}

    def test_read_redis_json_shim_still_returns_none_for_subtitles(self):
        import app.routes.admin_cockpit as ck

        with _patch_client(_client(get=_dead_get)):
            assert ck._read_redis_json("bainluck:admin:link_rate") is None


class TestCockpitRankingKillSwitch:
    """C102: an observability payload must not PICK a value for a product
    control whose store is unreachable."""

    def _eval_queue(self, *, dead=False, value=None):
        import asyncio

        import app.routes.admin_cockpit as ck

        db = MagicMock()
        result = MagicMock()
        result.scalars.return_value.all.return_value = []
        result.scalar.return_value = 0
        db.execute = MagicMock(return_value=result)

        async def _execute(*_a, **_kw):
            return result

        db.execute = _execute
        ctx = _dead_client() if dead else _patch_client(_client(get=lambda _k: value))
        with ctx:
            return asyncio.run(ck._eval_queue(db))

    def test_unreadable_switch_is_omitted_not_enabled(self):
        """The field is OMITTED, not nulled: `killSwitchView` treats `undefined`
        as "we don't know → hide the button", whereas a JSON null falls through
        that guard and renders "Enable" — asserting the switch is OFF during an
        outage. The cause rides in `eval_promote_status` instead."""
        out = self._eval_queue(dead=True)
        assert "eval_promote_enabled" not in out
        assert out["eval_promote_status"] == hr.UNAVAILABLE
        assert out["eval_promote_error"]

    def test_command_failure_is_also_omitted(self):
        import asyncio

        import app.routes.admin_cockpit as ck

        result = MagicMock()
        result.scalars.return_value.all.return_value = []
        result.scalar.return_value = 0

        async def _execute(*_a, **_kw):
            return result

        db = MagicMock()
        db.execute = _execute
        with _patch_client(_client(get=_dead_get)):
            out = asyncio.run(ck._eval_queue(db))
        assert "eval_promote_enabled" not in out
        assert out["eval_promote_status"] == hr.UNAVAILABLE

    def test_absent_key_keeps_the_documented_default(self):
        """Unset IS a known state for an opt-out switch — only unreadable is
        unknown."""
        out = self._eval_queue(value=None)
        assert out["eval_promote_enabled"] is True
        assert out["eval_promote_status"] == "ok"

    def test_explicitly_disabled_is_false(self):
        out = self._eval_queue(value="0")
        assert out["eval_promote_enabled"] is False
        assert out["eval_promote_status"] == "ok"
