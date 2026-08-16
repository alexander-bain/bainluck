"""#1501 — the Sentry ``before_send`` volume policy.

The org's error quota (5,000/month, Developer plan, period the 21st -> the 20th)
was being spent in eight days: 6,584 billable events in 2026-07-21 -> 07-29
(3,585 ``error`` + 2,999 ``default``), measured through Sentry's Discover API.
The consequence is not lost noise — it is that **a green Sentry read means
nothing**, and #1445 and #1199 both failed silently behind a 0-events bucket
that only meant the quota was gone.

These tests pin the three tiers and, more importantly, the four properties that
keep the filter honest when it is wrong about the census:

* drops are bound to **provenance**, never to a hostname substring;
* a **novel failure site** always sends its first event, even when its class and
  its task have already been seen;
* the filter **fails OPEN** — a bug in it must never suppress error reporting;
* the **fleet volume** is re-derived by replaying the real census, so the claim
  in the docstring cannot drift away from the code.

No assertion here reads the wall clock: ``_SignatureThrottle.allow`` takes an
injected ``now`` and the census fixture carries fixed dates (gotcha #44).
"""

from __future__ import annotations

import collections
import gzip
import json
import re
from pathlib import Path

import pytest

from app.utils.sentry_filter import (
    BACKSTOP_PER_WINDOW,
    BACKSTOP_WINDOW_S,
    DROP_EXC_NAMES,
    DUPLICATE_EVENT_LOGGERS,
    THROTTLE_EXC_NAMES,
    THROTTLE_PER_WINDOW,
    THROTTLE_WINDOW_S,
    VERDICT_DROP,
    VERDICT_PASS,
    VERDICT_THROTTLE,
    SentryVolumeFilter,
    _failure_site,
    _SignatureThrottle,
    build_before_send,
    classify,
    configured_broker_hosts,
    event_signature,
)
from tests.fixtures.sentry_formation import (
    CENSUS_DYNO_INCARNATIONS,
    CENSUS_MEAN_INCARNATIONS_PER_DAY,
    CENSUS_SINGLE_DAY_INCARNATIONS,
    DAILY_BUDGET,
    FORMATION,
    MAX_WORKER_CONCURRENCY,
    MEASURED_RELEASES_PER_DAY,
    MIN_SAFE_MARGIN,
    NOVEL_SIGNATURE_CAPACITY_FLOOR,
    QUOTA_EVENTS_PER_MONTH,
    STEADY_SDK_PROCESSES,
    STEADY_TYPES,
    WATCHDOG_COOLDOWN_WINDOWS_PER_DAY,
    WATCHDOG_PAIRS_PER_DAY,
    WATCHDOG_POOL_CHILDREN,
    novel_signature_reserve,
    sdk_processes,
    watchdog_ceiling_per_day,
)

CENSUS_PATH = Path(__file__).parent / "fixtures" / "sentry_census_2026_07_21.json.gz"

#: The production Heroku Redis endpoint, anonymised in the fixture. It keeps the
#: real suffix on purpose — the hostile specimen below shares it.
BROKER_HOST = "ec2-0-0-0-0.compute-1.amazonaws.com"

#: Codex C-CERT-SENTRY (a)'s specimen: a genuine third-party API, AWS-hosted, on
#: the SAME domain as our broker. Any substring or suffix host test swallows it.
HOSTILE_API_HOST = "api-v2.ec2-44-201-2-3.compute-1.amazonaws.com"


@pytest.fixture(autouse=True)
def _broker_env(monkeypatch):
    """Point the broker-host provenance at the fixture's placeholder endpoint."""
    monkeypatch.setenv("REDIS_URL", f"rediss://:pw@{BROKER_HOST}:10819")
    for var in ("CELERY_BROKER_URL", "BROKER_URL", "CELERY_RESULT_BACKEND",
                "REDIS_TLS_URL", "HEROKU_REDIS_URL"):
        monkeypatch.delenv(var, raising=False)
    configured_broker_hosts(refresh=True)
    yield
    configured_broker_hosts(refresh=True)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _exc_event(exc_type="ValueError", value="boom", transaction="app.tasks.poll_odds",
               module="", frames=None, **extra):
    value_dict = {"type": exc_type, "module": module, "value": value}
    if frames is not None:
        value_dict["stacktrace"] = {"frames": frames}
    event = {"transaction": transaction, "exception": {"values": [value_dict]}}
    event.update(extra)
    return event


def _frame(module, function, in_app=True, lineno=1):
    return {"module": module, "function": function, "in_app": in_app, "lineno": lineno}


def _log_event(message, logger_name, **extra):
    event = {"logger": logger_name, "logentry": {"formatted": message}}
    event.update(extra)
    return event


def _hint(exc_name, message="boom", module="builtins"):
    cls = type(exc_name, (Exception,), {"__module__": module})
    return {"exc_info": (cls, cls(message), None)}


# ===========================================================================
# CODEX FINDING (a) — provenance, not hostname substrings
# ===========================================================================

class TestBrokerProvenanceNotHostnameSubstrings:
    """A generic AWS-hosted API outage must NOT be misread as Redis churn.

    The shipped predecessor matched Redis noise with the host markers
    ``("compute-1.amazonaws.com", "redis", "ec2-")`` plus a transport marker
    list containing "connection reset by peer". A real upstream HTTPS
    ``ConnectionError`` for an AWS-hosted third-party API satisfies BOTH arms and
    was silently swallowed. Its only upstream test used
    ``api.the-odds-api.com``, which contains neither marker — so nothing caught
    it.
    """

    HOSTILE = (
        f"HTTPSConnectionPool(host='{HOSTILE_API_HOST}', port=443): "
        "Max retries exceeded — Connection reset by peer"
    )

    def test_aws_hosted_third_party_api_outage_is_NOT_dropped(self):
        """The exact specimen from the finding. This is the whole point."""
        event = _exc_event(exc_type="ConnectionError", value=self.HOSTILE, transaction=None)
        assert classify(event, None) != VERDICT_DROP
        f = SentryVolumeFilter()
        assert f(event, None) is not None
        assert f.counts["dropped"] == 0

    def test_the_hostile_host_really_does_contain_the_old_markers(self):
        """Guard the guard: if this stops being a hostile specimen, say so."""
        low = self.HOSTILE.lower()
        assert "compute-1.amazonaws.com" in low
        assert "ec2-" in low
        assert "connection reset by peer" in low

    def test_a_suffix_match_would_also_have_swallowed_it(self):
        """Branch lane-oob narrowed substring -> SUFFIX, which is necessary but
        not sufficient: ``.amazonaws.com`` still describes every AWS-hosted API."""
        assert HOSTILE_API_HOST.endswith(".compute-1.amazonaws.com")
        assert HOSTILE_API_HOST not in configured_broker_hosts()

    def test_our_own_broker_endpoint_IS_dropped(self):
        """The other direction (gotcha #43): the real noise must still go."""
        msg = (
            f"Error 8 connecting to {BROKER_HOST}:10819. "
            "[SSL: UNEXPECTED_EOF_WHILE_READING] EOF occurred in violation of protocol"
        )
        assert classify(_exc_event(exc_type="ConnectionError", value=msg), None) == VERDICT_DROP

    def test_broker_endpoint_in_a_url_shaped_message_is_dropped(self):
        msg = f"consumer: Cannot connect to rediss://:**@{BROKER_HOST}:10819//: Error 8"
        assert classify(_exc_event(exc_type="ConnectionError", value=msg), None) == VERDICT_DROP

    def test_redis_module_provenance_is_enough_without_any_hostname(self):
        """redis-py's message names the EC2 host and never the word 'redis' —
        which is exactly why the old `"redis" in str(exc)` test never fired."""
        msg = "Error 104 connecting to some-host:6379. Connection reset by peer."
        assert "redis" not in msg.lower()
        event = _exc_event(exc_type="ConnectionError", value=msg, module="redis.exceptions")
        assert classify(event, None) == VERDICT_DROP

    def test_kombu_and_amqp_transport_also_covered(self):
        for module in ("kombu.exceptions", "amqp.exceptions"):
            event = _exc_event(exc_type="ConnectionError", value="broker gone", module=module)
            assert classify(event, None) == VERDICT_DROP, module

    def test_redis_response_error_is_our_bug_and_survives(self):
        """Not every redis exception is transport churn."""
        event = _exc_event(exc_type="ResponseError", value="WRONGTYPE", module="redis.exceptions")
        assert classify(event, None) == VERDICT_PASS

    def test_unrelated_host_on_the_broker_port_is_not_dropped(self):
        msg = "Error 111 connecting to cache.partner.example:10819. Connection refused."
        assert classify(_exc_event(exc_type="ConnectionError", value=msg), None) != VERDICT_DROP

    def test_lookalike_suffix_host_is_not_dropped(self):
        msg = f"Error 111 connecting to {BROKER_HOST}.evil.example:6379."
        assert classify(_exc_event(exc_type="ConnectionError", value=msg), None) != VERDICT_DROP

    def test_upstream_odds_api_outage_survives(self):
        msg = "HTTPSConnectionPool(host='api.the-odds-api.com', port=443): Max retries exceeded"
        assert classify(_exc_event(exc_type="ConnectionError", value=msg), None) != VERDICT_DROP

    def test_broker_hosts_come_from_env_not_from_a_hardcoded_domain(self):
        hosts = configured_broker_hosts()
        assert BROKER_HOST in hosts
        assert not any(h.startswith(".") for h in hosts), "suffixes are not host provenance"


class TestInfraLoggerBoundMessageRules:
    """Message-shaped drops need an infra logger, so no app line can trip them."""

    SIGKILL = "Process 'ForkPoolWorker-290' pid:5340 exited with 'signal 9 (SIGKILL)'"

    def test_worker_recycle_record_is_dropped(self):
        assert classify(_log_event(self.SIGKILL, "multiprocessing"), None) == VERDICT_DROP

    def test_same_text_from_an_application_logger_is_NOT_dropped(self):
        """Provenance, not text. An app module reporting a subprocess death is a
        real report; billiard recycling its own child is not."""
        assert classify(_log_event(self.SIGKILL, "app.tasks.kalshi"), None) == VERDICT_PASS

    def test_template_plus_params_shape_matches_too(self):
        """The LoggingIntegration ships the %-template and params separately, so
        the rendered substring never exists — a rendered-form regex would
        silently never fire."""
        event = {
            "logger": "multiprocessing",
            "logentry": {
                "message": "Process %r pid:%r exited with %r",
                "params": ["ForkPoolWorker-290", 5340, "signal 9 (SIGKILL)"],
            },
        }
        assert classify(event, None) == VERDICT_DROP

    def test_celery_redis_retry_ladder_is_dropped(self):
        event = _log_event("Connection to Redis lost: Retry (15/20) in 1.00 second.",
                           "celery.backends.redis")
        assert classify(event, None) == VERDICT_DROP

    def test_hard_time_limit_log_twin_is_dropped(self):
        event = _log_event("Hard time limit (300s) exceeded for app.tasks.discover_events[abc]",
                           "celery.worker.request")
        assert classify(event, None) == VERDICT_DROP

    def test_watchdog_alert_text_is_never_filtered_here(self):
        """#1158's Sentry-only classes are cut by a cooldown at the source, never
        by dropping them in before_send."""
        for msg in (
            "Market CREATION stalled: kalshi — no new markets in 7.3h",
            "Suspected event-loop block: poll_kalshi phase 'upsert_loop@243s'",
        ):
            assert classify(_log_event(msg, "app.tasks.watchdog"), None) == VERDICT_PASS


class TestDropVersusThrottleSplit:
    """The line is drawn on 'does task-metrics already carry this?'."""

    @pytest.mark.parametrize("name", ["WorkerLostError", "TimeLimitExceeded", "Terminated"])
    def test_parent_side_task_death_is_dropped(self, name):
        """Raised in the pool PARENT: the stack is billiard's own teardown and
        says nothing about where the child was. hard_kills_24h covers it."""
        assert name in DROP_EXC_NAMES
        assert classify(_exc_event(exc_type=name, value=""), None) == VERDICT_DROP

    def test_the_old_inline_filters_WorkerLost_typo_is_also_covered(self):
        assert {"WorkerLost", "WorkerLostError"} <= DROP_EXC_NAMES

    def test_soft_time_limit_is_throttled_not_dropped(self):
        """Raised INTO the task, so its stack names the operation that overran —
        which no counter records. Absent from the old inline filter entirely."""
        assert "SoftTimeLimitExceeded" in THROTTLE_EXC_NAMES
        assert "SoftTimeLimitExceeded" not in DROP_EXC_NAMES
        assert classify(_exc_event(exc_type="SoftTimeLimitExceeded", value=""), None) == VERDICT_THROTTLE

    def test_first_soft_time_limit_survives_and_repeats_do_not(self):
        """Gotcha #43, both directions."""
        f = SentryVolumeFilter()
        event = _exc_event(exc_type="SoftTimeLimitExceeded", value="",
                           transaction="app.tasks.refresh_open_commentary")
        assert f(event, None) is not None
        for _ in range(50):
            f(event, None)
        assert f.counts["passed"] == 1
        assert f.counts["throttled"] == 50
        assert f.counts["dropped"] == 0

    def test_sqlalchemy_cascade_is_dropped(self):
        assert classify(_exc_event(exc_type="PendingRollbackError"), None) == VERDICT_DROP

    def test_event_loop_teardown_is_throttled_but_real_runtime_errors_are_not(self):
        noise = _exc_event(exc_type="RuntimeError", value="Event loop is closed")
        real = _exc_event(exc_type="RuntimeError", value="something genuinely broke")
        assert classify(noise, None) == VERDICT_THROTTLE
        assert classify(real, None) == VERDICT_PASS

    def test_integrity_error_is_never_filtered(self):
        """#1445's uq_game_moment_event_key class."""
        assert classify(_exc_event(exc_type="IntegrityError", value="duplicate key"), None) == VERDICT_PASS


# ===========================================================================
# CODEX FINDING (b) — the signature must carry a failure-site identity
# ===========================================================================

class TestNovelFailureSiteAlwaysSends:
    """A signature of class + transaction alone suppresses novel bugs.

    Certified against the predecessor: four distinct ``ValueError`` failure sites
    inside ``app.tasks.poll_odds`` produced sent, sent, sent, **suppressed** —
    so "every novel error sends its first event" was false, and the hidden
    failure-site diagnostic is unrecoverable (task metrics count failures, they
    do not name lines).
    """

    SITES = [
        ("app.tasks.odds", "_parse_bookmaker"),
        ("app.tasks.odds", "_normalise_price"),
        ("app.utils.aggregation", "compute_aggregate_probability"),
        ("app.services.odds_api", "fetch_events"),
    ]

    def _event(self, module, function):
        return _exc_event(
            exc_type="ValueError",
            value="bad probability",
            transaction="app.tasks.poll_odds",
            frames=[_frame("app.tasks.base", "run_async"), _frame(module, function)],
        )

    def test_four_failure_sites_in_one_task_all_send(self):
        """THE acceptance test for finding (b). Four is deliberate: the coarse
        signature's backstop is 3, so three would have passed by accident."""
        assert BACKSTOP_PER_WINDOW < len(self.SITES), "fewer sites than the cap proves nothing"
        f = SentryVolumeFilter()
        for module, function in self.SITES:
            event = self._event(module, function)
            assert f(event, None) is not None, f"novel failure site suppressed: {module}:{function}"
        assert f.counts["passed"] == len(self.SITES)
        assert f.counts["backstopped"] == 0

    def test_the_sites_share_one_class_and_one_transaction(self):
        """Without this the test above would be trivially satisfiable."""
        events = [self._event(m, fn) for m, fn in self.SITES]
        assert {e["exception"]["values"][0]["type"] for e in events} == {"ValueError"}
        assert {e["transaction"] for e in events} == {"app.tasks.poll_odds"}

    def test_each_site_gets_its_own_signature(self):
        sigs = {event_signature(self._event(m, fn), "ValueError") for m, fn in self.SITES}
        assert len(sigs) == len(self.SITES)

    def test_repeats_of_ONE_site_are_still_capped(self):
        """The other direction: finer signatures must not disable the backstop."""
        f = SentryVolumeFilter()
        event = self._event(*self.SITES[0])
        sent = sum(1 for _ in range(500) if f(event, None) is not None)
        assert sent == BACKSTOP_PER_WINDOW

    def test_line_number_is_not_part_of_the_identity(self):
        """A lineno in the key would re-open the whole budget on every deploy
        that shifts an unrelated line above the raise."""
        a = _exc_event(frames=[_frame("app.tasks.odds", "parse", lineno=10)])
        b = _exc_event(frames=[_frame("app.tasks.odds", "parse", lineno=97)])
        assert event_signature(a, "ValueError") == event_signature(b, "ValueError")

    def test_in_app_frames_win_over_library_frames(self):
        frames = [
            _frame("app.tasks.odds", "parse", in_app=True),
            _frame("httpx._client", "send", in_app=False),
        ]
        assert "app.tasks.odds:parse" in event_signature(_exc_event(frames=frames), "ValueError")

    def test_explicit_fingerprint_wins(self):
        """The watchdog sets scope.fingerprint = [alert_class, provider]; Sentry's
        own grouping is the most authoritative site identity available."""
        a = _exc_event(fingerprint=["creation_stall", "kalshi"], transaction="t")
        b = _exc_event(fingerprint=["creation_stall", "polymarket"], transaction="t")
        assert event_signature(a, "X") != event_signature(b, "X")
        assert "creation_stall" in event_signature(a, "X")

    def test_default_fingerprint_token_is_ignored(self):
        event = _exc_event(fingerprint=["{{ default }}"], frames=[_frame("m", "f")])
        assert "m:f" in event_signature(event, "ValueError")

    def test_traceback_from_the_hint_is_used_when_the_event_has_no_frames(self):
        def _inner_a():
            raise ValueError("a")

        def _inner_b():
            raise ValueError("b")

        hints = []
        for fn in (_inner_a, _inner_b):
            try:
                fn()
            except ValueError as exc:
                hints.append({"exc_info": (type(exc), exc, exc.__traceback__)})
        sigs = {event_signature({"transaction": "app.tasks.poll_odds"}, "ValueError", h)
                for h in hints}
        assert len(sigs) == 2, "distinct raising functions must not share a signature"

    def test_message_variance_does_NOT_split_the_signature(self):
        """Hostnames/PIDs/row-ids in messages are how one class spends a month."""
        frames = [_frame("app.tasks.odds", "parse")]
        a = _exc_event(value="host-A pid 1", frames=frames)
        b = _exc_event(value="host-B pid 2", frames=frames)
        assert event_signature(a, "ConnectionError") == event_signature(b, "ConnectionError")

    def test_missing_everything_does_not_crash(self):
        assert event_signature({}, "ValueError").startswith("ValueError|")


# ===========================================================================
# CODEX FINDING (c) — the volume claim, re-derived from the real census
# ===========================================================================

def _load_census():
    with gzip.open(CENSUS_PATH, "rt", encoding="utf-8") as fh:
        return json.load(fh)


def _census_event(row):
    """Rebuild the event the classifier would have seen.

    Schema 2 (codex C-CERT-SENTRY-R2 finding 3): the row's real deepest in-app
    frame is attached, so ``_failure_site`` takes the branch it takes in
    production — the frame — instead of falling through to ``culprit``. Under
    schema 1 every row fell through, which merged distinct production failure
    sites into one throttle bucket and made the replay UNDERCOUNT sends.

    Two honest limits, kept visible rather than smoothed over:

    * ``module`` stays empty. Discover exposes no field for the *defining
      module* of the exception class, so the module-provenance drop path is
      still reached only via the endpoint fallback. This makes the replay
      PESSIMISTIC (it drops less than production does), which is the safe
      direction and is asserted as such below.
    * a row with ``site == ""`` genuinely carried no in-app frame; it falls
      through to ``culprit`` exactly as production would.
    """
    event = {}
    if row["transaction"]:
        event["transaction"] = row["transaction"]
    if row["culprit"]:
        event["culprit"] = row["culprit"]
    if row["logger"]:
        event["logger"] = row["logger"]
    if row["kind"] == "error":
        value = {"type": row["exc_type"], "module": "", "value": row["message"]}
        site = row.get("site") or ""
        if site:
            module, _, function = site.rpartition(":")
            value["stacktrace"] = {"frames": [
                {"module": module or "?", "function": function or "?", "in_app": True}
            ]}
        event["exception"] = {"values": [value]}
    else:
        event["logentry"] = {"formatted": row["message"]}
    return event


_WATCHDOG_CULPRIT = "app.tasks.run_freshness_watchdog"
#: Emissions per [alert_class, provider] pair per day. One event, not two: the
#: ``logger.critical`` twin no longer reaches Sentry (see
#: DUPLICATE_EVENT_LOGGERS). Modelled as a CEILING rather than replayed, because
#: the census is bucketed by day and carries no timestamps.
#:
#: Codex C-CERT-SENTRY-R2 finding 1: this used to be the cooldown's 4/day alone,
#: which prices the HAPPY PATH of a gate that is designed to fail open. See
#: ``watchdog_ceiling_per_day`` — the honest ceiling is the worse of the two
#: shipped states, and both are bounded by the backstop.
def _watchdog_per_pair_per_day() -> int:
    return watchdog_ceiling_per_day(BACKSTOP_PER_WINDOW) // WATCHDOG_PAIRS_PER_DAY


def _watchdog_pair(message):
    match = re.match(r"Market CREATION stalled: (\S+)", message)
    if match:
        return ("creation_stall", match.group(1))
    match = re.match(r"Suspected event-loop block: (\S+) phase '([^@']+)", message)
    if match:
        return ("phase_block", f"{match.group(1)}:{match.group(2)}")
    return None


def _processes_for(row, model):
    """SDK processes on one dyno that can raise THIS signature.

    ``dyno`` models one throttle table per dyno incarnation (a LOWER bound —
    a dyno hosts several processes). ``process`` models the prefork reality:
    a task-side error can land on any of the pool's children, while billiard's
    worker-death records and the uvicorn request path are single-process.
    """
    if model == "dyno":
        return 1
    culprit, transaction, log = row["culprit"] or "", row["transaction"] or "", row["logger"] or ""
    if culprit.startswith("billiard.") or log in (
        "multiprocessing", "celery.worker.request",
        "celery.worker.consumer.consumer", "celery.backends.asynchronous",
    ):
        return 1
    if transaction.startswith("/api/") or transaction.startswith("http"):
        return 1
    if transaction.startswith("app.tasks.") or culprit.startswith("app.tasks."):
        return max(spec["concurrency"] or 1
                   for spec in FORMATION.values() if spec["kind"] == "celery_worker")
    return 1


def replay(census, model):
    """Replay the census through the filter AS SHIPPED. Returns per-day volume."""
    days = len(census["days"])
    filters: dict = collections.defaultdict(dict)
    round_robin: collections.Counter = collections.Counter()
    watchdog_pairs: dict = collections.defaultdict(set)
    sent = 0
    residual: collections.Counter = collections.Counter()

    for row in census["rows"]:
        if row["culprit"] == _WATCHDOG_CULPRIT:
            if row["logger"] in DUPLICATE_EVENT_LOGGERS:
                continue  # ignore_logger: never reaches Sentry at all now
            pair = _watchdog_pair(row["message"])
            if pair:
                from app.tasks.watchdog import _normalize_provider
                watchdog_pairs[row["day"]].add((pair[0], _normalize_provider(pair[1])))
            continue
        procs = _processes_for(row, model)
        event = _census_event(row)
        signature = event_signature(event, row["exc_type"])
        for _ in range(row["count"]):
            key = (row["dyno"], row["day"], signature)
            slot = round_robin[key] % procs
            round_robin[key] += 1
            worker = filters[(row["dyno"], row["day"])].setdefault(slot, SentryVolumeFilter())
            if worker(event, None) is not None:
                sent += 1
                residual[signature] += 1

    watchdog = sum(len(p) for p in watchdog_pairs.values()) * _watchdog_per_pair_per_day()
    return {
        "days": days,
        "offered": sum(r["count"] for r in census["rows"]),
        "sent": sent + watchdog,
        "sent_non_watchdog": sent,
        "sent_watchdog_ceiling": watchdog,
        "per_day": (sent + watchdog) / days,
        "residual": residual,
    }


class TestTheFixtureCarriesNoCredentials:
    """A committed error-message corpus is a credential surface.

    Found 2026-08-14 (queue 351), already on master: this fixture contained the
    app's **live ``ADMIN_TOKEN``**, captured by Sentry inside
    ``Client error '403 Forbidden' for url '...&secret=<64 hex>'`` — the legacy
    ``?secret=`` path that Queue #252 removed from *auth* but not from the
    *caller*, so it kept being sent, kept 403ing, and kept being recorded.

    It survived a certification that scanned this very file for secrets, for two
    reasons worth keeping:

    * the value sits in a URL inside a message, not in anything config-shaped;
    * **the artifact is gzip**, and the repo's gitleaks backstop scans text. A
      binary fixture is a blind spot for every text scanner pointed at the repo.

    So the scan has to live where the file is already being decompressed, which
    is here. The builder scrubs at the source; this asserts the result, because
    a scrub nobody verifies is a scrub that silently stops matching.
    """

    CREDENTIAL_RE = re.compile(
        r"(?i)\b(secret|token|api[_-]?key|apikey|password|passwd|pwd|"
        r"access[_-]?token|admin[_-]?token|signature)=([^&\s'\"]{12,})"
    )

    @pytest.fixture(scope="class")
    def raw(self):
        with gzip.open(CENSUS_PATH, "rt", encoding="utf-8") as fh:
            return fh.read()

    def test_no_query_string_credential_survives(self, raw):
        found = [
            (name, value) for name, value in self.CREDENTIAL_RE.findall(raw)
            if value != "REDACTED"
        ]
        assert not found, (
            f"{len(found)} credential-shaped query values in the fixture "
            f"(parameter names: {sorted({n for n, _ in found})}) — REDACT and "
            "ROTATE; history keeps the value forever, so deleting the line is "
            "not the remedy"
        )

    def test_the_redaction_kept_the_parameter_name(self, raw):
        """The name is what makes a leak legible to the next reader; only the
        value goes. This also proves the scrub actually ran on this file."""
        assert "secret=REDACTED" in raw

    def test_no_bare_high_entropy_hex_secret(self, raw):
        """A 64-char hex run is what both of this project's real tokens look
        like. Task ids are UUIDs (dashed, 36 chars) and do not match."""
        assert not re.findall(r"\b[0-9a-f]{48,}\b", raw)

    def test_no_broker_credentials(self, raw):
        assert "rediss://:pw@" not in raw
        assert not re.findall(r"rediss?://[^\s\"]*:[^@\"\s]{4,}@(?!REDACTED)", raw)


class TestFormationIsParsedNotAssumed:
    """The budget arithmetic must price the WHOLE Procfile."""

    def test_the_declared_process_types_are_what_we_derived_from(self):
        assert STEADY_TYPES == (
            "scheduler", "web", "worker-background", "worker-heavy",
            "worker-realtime", "worker-ws",
        ), "Procfile changed — re-run the replay and re-derive the ceiling"

    def test_every_steady_type_initialises_the_sdk(self):
        """web imports app.main; the celery types boot app.tasks.celery_app;
        worker-ws runs run_kalshi_ws.py, whose `from app.tasks.kalshi_ws import`
        executes app/tasks/__init__.py and therefore its sentry_sdk.init."""
        assert len(STEADY_TYPES) == 6

    def test_prefork_children_each_hold_their_own_throttle_table(self):
        assert sdk_processes(FORMATION["worker-realtime"]) == 5  # parent + 4
        assert sdk_processes(FORMATION["worker-background"]) == 3
        assert sdk_processes(FORMATION["worker-heavy"]) == 3
        assert sdk_processes(FORMATION["web"]) == 1
        assert STEADY_SDK_PROCESSES == 14

    def test_release_is_excluded_as_transient(self):
        assert "release" in FORMATION and "release" not in STEADY_TYPES

    def test_children_are_recycled_so_state_resets(self):
        """--max-memory-per-child is the restart model: a recycled child forks
        from the parent with an EMPTY throttle table."""
        assert FORMATION["worker-realtime"]["max_memory_kb"] == 350_000
        assert FORMATION["worker-background"]["max_memory_kb"] == 200_000


class TestFleetVolumeCeiling:
    """Codex C-CERT-SENTRY (c): re-derive the number, do not quote one.

    The predecessor claimed "42 events/day/process" from a replay that collapsed
    each aggregate class to ONE synthetic transaction and asserted only
    ``cut > 95%``. Executing that fixture through its own predicate gave 1.75/day
    — and "per process" was never a fleet number anyway.

    This replays the REAL per-signature census (Sentry Discover, 2026-07-21 ->
    07-29, grouped by signature x dyno-incarnation x day) through the filter as
    shipped, under two models of where the per-process throttle state lives.
    """

    @pytest.fixture(scope="class")
    def census(self):
        return _load_census()

    def test_the_fixture_is_the_real_cycle(self, census):
        assert census["totals"]["error"] == 3_585
        assert census["totals"]["default"] == 2_999
        assert census["totals"]["error"] + census["totals"]["default"] == 6_584
        assert len(census["days"]) == 8

    def test_the_unfiltered_baseline_is_5x_the_budget(self, census):
        baseline = 6_584 / 8
        assert round(baseline, 1) == 823.0
        assert baseline / DAILY_BUDGET > 5

    def test_measured_volume_expected_case(self, census):
        """One throttle table per dyno incarnation. A LOWER bound: 552 of the
        563 observed ``server_name`` values appear on exactly one day, i.e. ~70
        process incarnations per day, and each dyno hosts several of them."""
        result = replay(census, "dyno")
        assert result["sent"] == 588, "policy changed — re-derive and update the report"
        assert round(result["per_day"], 1) == 73.5
        assert result["per_day"] < DAILY_BUDGET

    def test_measured_volume_worst_case(self, census):
        """Task-side errors spread round-robin across every prefork child, which
        is realistic rather than adversarial: Celery routes a task to whichever
        child is free. This is the operative ceiling.

        **This number is a REPLAY, not a bound on the policy** (codex
        C-CERT-SENTRY-R2 finding 1). It prices only signatures present in one
        frozen eight-day census, so on its own it cannot see a state the census
        did not contain. The two such states that matter are priced explicitly
        in :class:`TestBudgetSurvivesItsNegativeControls`, and the certified
        margin is the one THERE, not the one here.
        """
        result = replay(census, "process")
        assert result["sent"] == 1_090
        assert round(result["per_day"], 1) == 136.2
        assert result["per_day"] < DAILY_BUDGET, (
            "the worst-case fleet/day ceiling must fit the quota"
        )

    def test_the_worst_case_still_fits_the_month(self, census):
        result = replay(census, "process")
        assert result["per_day"] * 30.4 < QUOTA_EVENTS_PER_MONTH


class TestBudgetSurvivesItsNegativeControls:
    """Codex C-CERT-SENTRY-R2 finding 1 — the replay is not a ceiling.

    At the certified policy (backstop 3) the replay read 157.0/day against a
    164.47/day budget, and **either** of the two controls below took it over:
    169/day for a novel worker signature, 167/day for the watchdog's tested
    Redis-down path. A margin that only survives the sample is not a margin.

    Both controls are now priced INTO the budget, and the cap was lowered until
    the priced total cleared a floor rather than a threshold.
    """

    @pytest.fixture(scope="class")
    def census(self):
        return _load_census()

    def _priced(self, census, signatures=1):
        base = replay(census, "process")["per_day"]
        return base + novel_signature_reserve(BACKSTOP_PER_WINDOW, signatures)

    def test_control_one_a_novel_worker_signature_is_reserved_for(self, census):
        """The census cannot contain tomorrow's bug.

        One new task erroring on every run is capped per process and reaches
        every child in the pool, so it costs ``cap x children`` per day until
        someone fixes it. At backstop 3 that was +12/day and it broke the
        budget; the reserve is now paid for up front instead of discovered.
        """
        reserve = novel_signature_reserve(BACKSTOP_PER_WINDOW, 1)
        assert reserve == BACKSTOP_PER_WINDOW * MAX_WORKER_CONCURRENCY == 4
        assert self._priced(census, 1) < DAILY_BUDGET

    def test_control_two_the_watchdog_cooldown_fails_open(self, census):
        """``_alert_on_cooldown`` returns False when Redis is unreachable.

        That is deliberate and tested — a telemetry-infra failure must never
        swallow an alarm — which means the cooldown can NEVER be assumed to be
        holding when pricing the watchdog. The previous model priced only the
        happy path at 4 windows/day.

        The repair is not a bigger allowance, it is that the backstop now binds
        first: ``1 x 2 background children`` is below the 4/day a working
        cooldown allows, so the failure mode is bounded by the same number as
        the healthy one and costs nothing extra.
        """
        assert BACKSTOP_PER_WINDOW * WATCHDOG_POOL_CHILDREN <= WATCHDOG_COOLDOWN_WINDOWS_PER_DAY, (
            "the backstop no longer binds the watchdog — the fail-open path is "
            "unpriced again and the cooldown's happy path is back in the budget"
        )
        assert watchdog_ceiling_per_day(BACKSTOP_PER_WINDOW) == 10
        # And the control that would have caught the original: at the certified
        # cap the fail-open path exceeded what the model charged for it.
        assert watchdog_ceiling_per_day(3) > WATCHDOG_PAIRS_PER_DAY * WATCHDOG_COOLDOWN_WINDOWS_PER_DAY / 2

    def test_the_slack_is_stated_in_bugs_not_percent(self, census):
        """A percentage is abstract. This is the same fact an operator can act
        on: how many MORE novel high-frequency worker signatures the remaining
        slack absorbs before the quota is at risk."""
        base = replay(census, "process")["per_day"]
        per_signature = novel_signature_reserve(BACKSTOP_PER_WINDOW, 1)
        capacity = int((DAILY_BUDGET - base) // per_signature)
        assert capacity >= NOVEL_SIGNATURE_CAPACITY_FLOOR, (
            f"only {capacity} novel worker signatures of slack remain"
        )

    def test_the_margin_is_a_FLOOR_not_a_range(self, census):
        """The assertion this replaces was ``0.0 < headroom < 0.10``.

        Its docstring promised that a change making the margin thinner would
        fail. It did the opposite: shrinking the margin from 5% to 0.1% passes
        that assertion comfortably. A test whose name is the opposite of its
        assertion is worse than no test, because it is *cited* as cover.

        A floor cannot be satisfied by getting worse.
        """
        margin = (DAILY_BUDGET - self._priced(census, 1)) / DAILY_BUDGET
        assert margin >= MIN_SAFE_MARGIN, (
            f"margin {margin:.1%} is below the {MIN_SAFE_MARGIN:.0%} floor — "
            "cut volume or lower a cap; do NOT lower the floor"
        )

    def test_a_thinner_margin_would_fail_this_suite(self, census):
        """The negative control ON the floor itself, so it cannot rot the way
        its predecessor did: a hypothetical policy at 0.1% margin must FAIL."""
        hypothetical = DAILY_BUDGET * 0.999
        margin = (DAILY_BUDGET - hypothetical) / DAILY_BUDGET
        assert not (margin >= MIN_SAFE_MARGIN), "the floor accepts a 0.1% margin"

    def test_even_two_novel_signatures_still_fit_the_quota(self, census):
        """Weaker than the floor and deliberately kept: two simultaneous novel
        worker signatures eat into the margin (13.9%, under the floor) but do
        NOT exhaust the quota. The floor is where we act; this is where we
        would be in trouble."""
        assert self._priced(census, 2) < DAILY_BUDGET

    def test_the_month_fits_with_the_reserve_applied(self, census):
        assert self._priced(census, 1) * 30.4 < QUOTA_EVENTS_PER_MONTH

    def test_the_dominant_residual_is_named(self, census):
        """The biggest surviving signature is ONE chronically overrunning task.
        That is the filter working: a real bug should be surfaced, not hidden."""
        result = replay(census, "process")
        top, count = result["residual"].most_common(1)[0]
        assert "SoftTimeLimitExceeded" in top and "refresh_open_commentary" in top
        assert count / result["days"] > 30

    def test_schema_2_round_trips_the_signature_fields(self, census):
        """Codex C-CERT-SENTRY-R2 finding 3, direct.

        The predecessor fixture asserted only ``>500 anonymised server_name
        values``, which proves CARDINALITY and nothing about fidelity. What the
        classifier actually consumes is the failure site, and schema 1 carried
        no frames at all — so every row fell through to ``culprit`` and the
        replay could not have noticed a collapsed bucket if it happened.
        """
        assert census["schema_version"] == 2
        rows_with_site = [r for r in census["rows"] if r["site"]]
        assert len(rows_with_site) > 800, "the frames did not survive the rebuild"
        # the site is a real module:function, and it reaches _failure_site
        row = next(r for r in rows_with_site if r["exc_type"] == "IntegrityError")
        assert ":" in row["site"] and row["frame_depth"] > 0
        assert _failure_site(_census_event(row), None) == row["site"]
        # and a row with no in-app frame falls through to culprit, as production does
        frameless = next((r for r in census["rows"]
                          if not r["site"] and r["culprit"] and r["kind"] == "error"), None)
        if frameless is not None:
            assert _failure_site(_census_event(frameless), None) == frameless["culprit"]

    def test_missing_signature_fields_can_only_UNDERCOUNT(self, census):
        """The monotonicity that makes finding 3 tractable.

        Stripping the site information can never *raise* the replay's volume:
        fewer distinguishable signatures means more events sharing one
        allowance, and a shared allowance suppresses more. So a fixture missing
        signature fields is biased toward undercounting — the optimistic
        direction — which is why "the omissions make it pessimistic" could not
        be assumed and had to be checked.

        Measured on this change: rebuilding schema 1 -> schema 2 moved the
        replay from **133.6 to 141.1/day** at the then-current policy, a 5.6%
        correction upward. The site-agnostic rule for signal-injected classes
        then returned 4.9/day of that, which is why the number below is 136.2
        rather than either. Both movements are real and neither is a tuning
        knob.
        """
        stripped = {**census, "rows": [{**r, "site": ""} for r in census["rows"]]}
        assert replay(stripped, "process")["per_day"] <= replay(census, "process")["per_day"]

    def test_bucket_collapse_is_MEASURED_against_sentrys_own_grouping(self, census):
        """``issue`` is Sentry's grouping id. It is never fed to the filter — it
        is the independent yardstick that turns "can our signature collapse
        distinct production buckets?" from an argument into a number.

        Two directions, both reported:

        * a signature covering >1 issue is a COLLAPSE (we would suppress a
          distinct bug behind another one's allowance);
        * an issue split across >1 signature is the safe direction — more
          allowances, more volume, already priced by the replay.
        """
        sig_to_issues = collections.defaultdict(set)
        for row in census["rows"]:
            if row["culprit"] == _WATCHDOG_CULPRIT:
                continue  # modelled separately; its real fingerprint is not in Discover
            signature = event_signature(_census_event(row), row["exc_type"])
            sig_to_issues[signature].add(row["issue"])

        collapsed = {s: i for s, i in sig_to_issues.items() if len(i) > 1}
        worst = max((len(i) for i in collapsed.values()), default=0)
        # The remaining collapses are the SITE-AGNOSTIC classes (by design — one
        # chronic timeout is one bucket) plus rows Sentry split on fields no
        # before_send can see. What must not happen is a signature swallowing a
        # large family of genuinely distinct issues.
        assert worst <= 5, (
            f"one signature now covers {worst} distinct Sentry issues — "
            "a novel bug can hide behind an existing one's allowance"
        )
        assert len(collapsed) / max(1, len(sig_to_issues)) < 0.15

    def test_the_incarnation_multiplier_is_corroborated_not_asserted(self, census):
        """Codex C-CERT-SENTRY-R2 finding 3, second half.

        563 distinct ``server_name`` values prove cardinality, not that each is
        a restart. The corroboration is external and is recorded in
        ``sentry_formation``: 11.9 Heroku releases/day measured over the
        adjacent 16.8-day span, and 5-20 distinct releases/day inside the window
        via Sentry. Every release restarts every dyno, so at 6 steady types a
        12-release day mints ~72 hostnames — against an observed mean of 71.9.

        This test pins the fixture-side facts that arithmetic rests on, so a
        rebuild that changes the partition cannot silently change the budget.
        """
        dynos = collections.defaultdict(set)
        for row in census["rows"]:
            dynos[row["dyno"]].add(row["day"])
        assert len(dynos) == CENSUS_DYNO_INCARNATIONS
        single_day = sum(1 for days in dynos.values() if len(days) == 1)
        assert single_day == CENSUS_SINGLE_DAY_INCARNATIONS
        assert single_day / len(dynos) > 0.95, (
            "incarnations now persist across days — they are not restarts and "
            "the allowance-reset multiplier must be re-derived"
        )
        per_day = collections.defaultdict(set)
        for row in census["rows"]:
            per_day[row["day"]].add(row["dyno"])
        mean = sum(len(v) for v in per_day.values()) / len(per_day)
        assert abs(mean - CENSUS_MEAN_INCARNATIONS_PER_DAY) < 0.01
        # the deploy rate is the same order as the churn it is offered to explain
        assert 0.5 < (MEASURED_RELEASES_PER_DAY * len(STEADY_TYPES)) / mean < 2.0

    def test_the_replay_uses_process_and_queue_provenance(self, census):
        """Not a single synthetic transaction per class: the fixture is grouped
        by dyno incarnation, and the process model is derived from the Procfile."""
        rows = census["rows"]
        assert len({r["dyno"] for r in rows}) > 500
        # 174 distinct (class, culprit, transaction) triples, against the
        # predecessor replay's 10 synthetic one-transaction-per-class rows.
        assert len({(r["exc_type"], r["culprit"], r["transaction"]) for r in rows}) == 176
        assert _processes_for({"culprit": "", "transaction": "app.tasks.poll_odds",
                               "logger": ""}, "process") == 4
        assert _processes_for({"culprit": "billiard.pool in mark_as_worker_lost",
                               "transaction": "", "logger": ""}, "process") == 1

    def test_every_tier_actually_fires_on_real_data(self, census):
        verdicts = collections.Counter()
        for row in census["rows"]:
            verdicts[classify(_census_event(row), None)] += row["count"]
        assert verdicts[VERDICT_DROP] == 3_491
        assert verdicts[VERDICT_THROTTLE] == 863
        assert verdicts[VERDICT_PASS] == 2_230
        assert sum(verdicts.values()) == 6_584


# ===========================================================================
# Throttle mechanics, fail-open, wiring
# ===========================================================================

class TestThrottleBucket:
    """Clock is injected — nothing here reads the wall clock (gotcha #44)."""

    def test_first_event_always_allowed(self):
        assert _SignatureThrottle().allow("s", limit=1, window_s=100, now=0.0) is True

    def test_limit_enforced_within_window(self):
        t = _SignatureThrottle()
        assert t.allow("s", limit=2, window_s=100, now=0.0) is True
        assert t.allow("s", limit=2, window_s=100, now=10.0) is True
        assert t.allow("s", limit=2, window_s=100, now=20.0) is False

    def test_window_opening_at_monotonic_zero_is_a_real_window(self):
        """Truthiness instead of membership would reset the bucket every call and
        silently disable the throttle for that signature forever."""
        t = _SignatureThrottle()
        assert t.allow("s", limit=1, window_s=100, now=0.0) is True
        assert t.allow("s", limit=1, window_s=100, now=0.0) is False

    def test_window_rolls_over(self):
        t = _SignatureThrottle()
        assert t.allow("s", limit=1, window_s=100, now=0.0) is True
        assert t.allow("s", limit=1, window_s=100, now=50.0) is False
        assert t.allow("s", limit=1, window_s=100, now=100.0) is True

    def test_signatures_are_independent(self):
        t = _SignatureThrottle()
        assert t.allow("a", limit=1, window_s=100, now=0.0) is True
        assert t.allow("b", limit=1, window_s=100, now=0.0) is True

    def test_table_is_bounded(self):
        """This dict lives for the life of a worker process — it must not grow."""
        t = _SignatureThrottle()
        for i in range(3000):
            t.allow(f"s{i}", limit=1, window_s=100, now=float(i))
        assert len(t.snapshot()) <= 512


class TestBackstop:
    """The part that does NOT depend on the census being right."""

    def test_novel_signature_always_sends_its_first_event(self):
        f = SentryVolumeFilter()
        for i in range(200):
            event = _exc_event(exc_type="BrandNewError", transaction=f"app.tasks.t{i}")
            assert f(event, None) is not None, "a novel error was suppressed"

    def test_unidentified_flooding_signature_is_capped(self):
        f = SentryVolumeFilter()
        event = _exc_event(exc_type="SomeUnknownFlood")
        sent = sum(1 for _ in range(5000) if f(event, None) is not None)
        assert sent == BACKSTOP_PER_WINDOW
        assert f.counts["backstopped"] == 5000 - BACKSTOP_PER_WINDOW

    def test_caps_stay_tight_enough_to_fit_the_budget(self):
        """Loosening these without re-running the replay is what re-exhausts the
        quota. The replay tests above are the real guard; these pin the shape."""
        assert THROTTLE_PER_WINDOW <= 2
        assert BACKSTOP_PER_WINDOW <= 4
        assert THROTTLE_WINDOW_S >= 3600
        assert BACKSTOP_WINDOW_S >= 3600


class TestFailOpen:
    """A filter bug must never take error reporting down with it."""

    #: All three of these degenerate to the SAME signature (``unknown|?|?``),
    #: which is correct — there is nothing in them to tell apart. So each gets
    #: its own filter: sharing one would test the backstop (a repeat of one
    #: signature is capped, by design) rather than the fail-open property this
    #: class exists for. At ``BACKSTOP_PER_WINDOW`` 3 the distinction was
    #: invisible because three shapes fitted under the cap by luck.
    MALFORMED = [
        ({}, None),
        ({"exception": None}, {}),
        ({"exception": {"values": [None]}}, {}),
    ]

    @pytest.mark.parametrize("event,hint", MALFORMED)
    def test_malformed_events_do_not_raise(self, event, hint):
        f = SentryVolumeFilter()
        assert f(event, hint) is not None
        assert f.counts["dropped"] == 0, "a malformed event must never be DROPPED"

    def test_malformed_events_share_one_signature_so_repeats_are_capped(self):
        """The other direction, stated rather than left as a surprise: these
        are indistinguishable, so a flood of them is one signature and IS
        capped. Fail-open is about the first event, not about unbounded volume.
        """
        sigs = {event_signature(e or {}, "", h) for e, h in self.MALFORMED}
        assert len(sigs) == 1
        f = SentryVolumeFilter()
        sent = sum(1 for e, h in self.MALFORMED if f(e, h) is not None)
        assert sent == BACKSTOP_PER_WINDOW

    def test_internal_error_fails_open(self, monkeypatch):
        f = SentryVolumeFilter()
        monkeypatch.setattr(
            "app.utils.sentry_filter.classify",
            lambda *a, **k: (_ for _ in ()).throw(RuntimeError("filter bug")),
        )
        event = _exc_event()
        assert f(event, None) is event, "filter must fail OPEN, not swallow"

    def test_hostile_hint_fails_open(self):
        class Hostile(dict):
            def get(self, *a, **k):
                raise RuntimeError("boom")

        f = SentryVolumeFilter()
        event = _exc_event()
        assert f(event, Hostile()) is event

    def test_hint_exc_info_is_used_when_the_event_body_is_empty(self):
        f = SentryVolumeFilter()
        msg = f"Error 8 connecting to {BROKER_HOST}:10819."
        assert f({}, _hint("ConnectionError", msg)) is None


class TestWiring:
    """#1501's root cause: the filter existed, but only on the web process."""

    def test_both_entry_points_use_the_shared_filter(self):
        import inspect

        import app.main as main_mod
        import app.tasks as tasks_mod

        for mod in (main_mod, tasks_mod):
            src = inspect.getsource(mod)
            assert "build_before_send" in src, f"{mod.__name__} not wired to the shared filter"
            assert "before_send=" in src, f"{mod.__name__} passes no before_send"

    def test_no_inline_filter_survives_in_either_entry_point(self):
        """Guard against someone re-adding a second, divergent policy."""
        import inspect

        import app.main as main_mod
        import app.tasks as tasks_mod

        for mod in (main_mod, tasks_mod):
            assert "def _before_send" not in inspect.getsource(mod)

    def test_builder_returns_independent_instances(self):
        a, b = build_before_send(), build_before_send()
        assert a is not b
        assert a.counts is not b.counts

    def test_duplicate_log_events_are_ignored_at_the_sdk(self):
        """774 of the watchdog's 1,588 events were the logger.critical twin of a
        capture_message that carries a fingerprint and tags. Silence the twin."""
        from sentry_sdk.integrations.logging import ignore_logger

        from app.utils.sentry_filter import install_logger_ignores

        assert "app.tasks.watchdog" in DUPLICATE_EVENT_LOGGERS
        assert install_logger_ignores() == DUPLICATE_EVENT_LOGGERS
        assert callable(ignore_logger)
