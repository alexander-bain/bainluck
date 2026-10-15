"""#11042 slice 3 — every LLM call reserves budget, retries boundedly and waits for a slot.

``app.services.llm_request.complete_chat`` is the only sender. These tests pin:

* a reservation is taken BEFORE every attempt, against the per-job budget and
  the shared daily budget, and a reservation that does not fit means the client
  is never called;
* a response with usage is settled to its real cost; no usage, a timeout, a
  local failure or a cancellation keeps the worst case booked (unknown is never
  zero); an error the provider answered is released;
* retries are this layer's (every client is built ``max_retries=0``), capped,
  and each retry reserves again;
* concurrency is bounded by a slot the calling THREAD holds, so cancelling an
  async awaiter does not free it while the call is still running;
* a malformed budget or an unreachable ledger refuses.

No test makes a network call; the ledger is the in-memory one conftest installs,
except the Lua test, which runs against a real redis-server when redislite is
installed.
"""

from __future__ import annotations

import ast
import asyncio
import pathlib
import threading
from datetime import date

import httpx
import openai
import pytest

from app.services import llm_request
from app.services.llm_models import (
    LEGACY_MODEL,
    MODELS,
    REPLACEMENT_MODEL,
    TASKS,
    UnsupportedModelError,
    cost_upper_bound_usd,
    prompt_tokens_upper_bound,
)
from app.services.llm_request import (
    JobBudget,
    LLMBudgetExceeded,
    LLMBudgetUnavailable,
    LLMConcurrencyExhausted,
    MemoryBudgetLedger,
    complete_chat,
    complete_chat_detailed,
)

APP = pathlib.Path(__file__).resolve().parents[1] / "app"
DAY = date(2026, 12, 1)
MESSAGES = [{"role": "system", "content": "Classify."}, {"role": "user", "content": "Chiefs at Bills"}]
MAX_OUT = 50


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for name in ("LLM_MODEL", "DISCOVER_LLM_MODEL", llm_request.DAILY_BUDGET_ENV, llm_request.CONCURRENCY_ENV,
                 *(f"LLM_MODEL_{t.upper()}" for t in TASKS)):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(llm_request, "_slots", None)
    sleeps: list[float] = []
    monkeypatch.setattr(llm_request, "_sleep", sleeps.append)
    return sleeps


@pytest.fixture
def ledger():
    led = MemoryBudgetLedger()
    llm_request.set_ledger(led)
    return led


def _micros(usd: float) -> int:
    return llm_request._to_micros(usd)


RESERVATION = _micros(cost_upper_bound_usd(LEGACY_MODEL, MESSAGES, MAX_OUT))


class _Usage:
    def __init__(self, prompt_tokens, completion_tokens):
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens


class _Response:
    def __init__(self, usage):
        self.usage = usage
        self.choices = [type("C", (), {"message": type("M", (), {"content": "football"})()})()]


def _request():
    return httpx.Request("POST", "https://api.openai.com/v1/chat/completions")


def _status_error(status: int, retry_after: str | None = None):
    headers = {"retry-after": retry_after} if retry_after else {}
    response = httpx.Response(status, request=_request(), headers=headers)
    cls = {429: openai.RateLimitError, 400: openai.BadRequestError}.get(status, openai.InternalServerError)
    return cls("err", response=response, body=None)


class _Client:
    """``script``: one item per attempt — a usage object/None to answer, or an exception to raise."""

    def __init__(self, *script):
        self.script = list(script)
        self.calls: list[dict] = []
        outer = self

        class _Completions:
            def create(self, **kwargs):
                outer.calls.append(kwargs)
                step = outer.script[min(len(outer.calls), len(outer.script)) - 1]
                if isinstance(step, BaseException):
                    raise step
                return _Response(step)

        self.chat = type("Chat", (), {"completions": _Completions()})()


def _call(client, **kw):
    kw.setdefault("today", DAY)
    return complete_chat_detailed("classify", client, messages=MESSAGES, max_output_tokens=MAX_OUT, temperature=0, **kw)


# --------------------------------------------------------------------------
# The upper bound really is an upper bound
# --------------------------------------------------------------------------


def test_prompt_bound_counts_every_byte_and_the_framing():
    text = "héllo wörld — 日本語 🎾"
    msgs = [{"role": "user", "content": text}]
    assert prompt_tokens_upper_bound(msgs) == len(text.encode()) + len(b"user") + 8 + 8


def test_prompt_bound_is_above_the_real_tokenizer_count():
    tiktoken = pytest.importorskip("tiktoken")
    enc = tiktoken.get_encoding("o200k_base")
    samples = ["Chiefs at Bills, 1:00 PM ET", "日本語のテキスト 🎾🎾🎾", '{"a": [1, 2, 3]}' * 40, "x" * 5000]
    for s in samples:
        msgs = [{"role": "system", "content": "You classify."}, {"role": "user", "content": s}]
        real = sum(len(enc.encode(m["content"])) + len(enc.encode(m["role"])) + 4 for m in msgs) + 3
        assert real <= prompt_tokens_upper_bound(msgs)


def test_cost_bound_charges_a_full_answer_at_the_models_rates():
    p = prompt_tokens_upper_bound(MESSAGES)
    assert cost_upper_bound_usd(LEGACY_MODEL, MESSAGES, 100) == pytest.approx((p * 0.15 + 100 * 0.60) / 1e6)
    assert cost_upper_bound_usd(REPLACEMENT_MODEL, MESSAGES, 100) == pytest.approx((p * 0.10 + 100 * 0.50) / 1e6)
    with pytest.raises(UnsupportedModelError):
        cost_upper_bound_usd("gpt-9-unpriced", MESSAGES, 100)


# --------------------------------------------------------------------------
# Reservation and settlement
# --------------------------------------------------------------------------


def test_a_response_with_usage_is_settled_to_its_real_cost(ledger):
    result = _call(_Client(_Usage(900, 20)))
    real = _micros((900 * 0.15 + 20 * 0.60) / 1e6)
    assert result.cost_usd == pytest.approx((900 * 0.15 + 20 * 0.60) / 1e6)
    assert result.model == LEGACY_MODEL
    assert ledger.totals[DAY.isoformat()] == real
    assert ledger.tasks[(DAY.isoformat(), "classify")] == real


def test_a_response_with_no_usage_keeps_the_worst_case_booked(ledger):
    result = _call(_Client(None))
    assert result.cost_usd is None
    assert ledger.totals[DAY.isoformat()] == RESERVATION


def test_a_local_failure_keeps_the_reservation_and_is_not_retried(ledger):
    client = _Client(ValueError("boom"))
    with pytest.raises(ValueError):
        _call(client)
    assert len(client.calls) == 1
    assert ledger.totals[DAY.isoformat()] == RESERVATION


def test_the_shared_cap_refuses_before_the_client_is_called(ledger, monkeypatch):
    monkeypatch.setenv(llm_request.DAILY_BUDGET_ENV, "0")
    client = _Client(_Usage(1, 1))
    with pytest.raises(LLMBudgetExceeded):
        _call(client)
    assert client.calls == []
    assert ledger.totals == {}


def test_the_cap_admits_a_reservation_that_exactly_fits_and_not_one_micro_more(ledger, monkeypatch):
    monkeypatch.setenv(llm_request.DAILY_BUDGET_ENV, str(RESERVATION / 1e6))
    _call(_Client(None))  # fits exactly, and no usage keeps it all booked
    client = _Client(None)
    with pytest.raises(LLMBudgetExceeded):
        _call(client)
    assert client.calls == []


def test_spend_is_shared_across_tasks_and_per_day(ledger, monkeypatch):
    monkeypatch.setenv(llm_request.DAILY_BUDGET_ENV, str(1.5 * RESERVATION / 1e6))
    _call(_Client(None))
    with pytest.raises(LLMBudgetExceeded):
        complete_chat("hooks", _Client(None), messages=MESSAGES, max_output_tokens=MAX_OUT, temperature=0, today=DAY)
    _call(_Client(None), today=date(2026, 12, 2))  # a new UTC day has its own budget


@pytest.mark.parametrize("raw", ["ten", "-1", "nan", "inf"])
def test_a_malformed_budget_refuses(ledger, monkeypatch, raw):
    monkeypatch.setenv(llm_request.DAILY_BUDGET_ENV, raw)
    client = _Client(_Usage(1, 1))
    with pytest.raises(LLMBudgetUnavailable):
        _call(client)
    assert client.calls == []


def test_an_unreachable_ledger_refuses_and_releases_the_job(monkeypatch):
    class _Down:
        def reserve(self, *a):
            raise ConnectionError("redis down")

    llm_request.set_ledger(_Down())
    job = JobBudget(1.0)
    client = _Client(_Usage(1, 1))
    with pytest.raises(LLMBudgetUnavailable):
        _call(client, job_budget=job)
    assert client.calls == [] and job.spent_usd == 0


def test_a_job_budget_refuses_when_its_remainder_cannot_cover_the_worst_case(ledger):
    job = JobBudget(RESERVATION / 1e6)
    _call(_Client(_Usage(10, 1)), job_budget=job)  # settles far below the reservation
    assert job.spent_usd == pytest.approx(_micros((10 * 0.15 + 0.60) / 1e6) / 1e6)
    _call(_Client(None), job_budget=JobBudget(RESERVATION / 1e6))
    tight = JobBudget(RESERVATION / 1e6 - 1e-6)
    client = _Client(_Usage(1, 1))
    with pytest.raises(LLMBudgetExceeded):
        _call(client, job_budget=tight)
    assert client.calls == []


def test_a_shared_refusal_does_not_charge_the_job(ledger, monkeypatch):
    monkeypatch.setenv(llm_request.DAILY_BUDGET_ENV, "0")
    job = JobBudget(1.0)
    with pytest.raises(LLMBudgetExceeded):
        _call(_Client(_Usage(1, 1)), job_budget=job)
    assert job.spent_usd == 0


def test_an_unregistered_task_refuses_before_any_reservation(ledger):
    client = _Client(_Usage(1, 1))
    with pytest.raises(UnsupportedModelError):
        complete_chat("not_a_task", client, messages=MESSAGES, max_output_tokens=1, temperature=0)
    assert client.calls == [] and ledger.totals == {}


def test_every_registered_task_can_be_priced_on_every_model():
    for model in MODELS:
        for _ in TASKS:
            assert cost_upper_bound_usd(model, MESSAGES, 2200) > 0


# --------------------------------------------------------------------------
# Retries: owned here, capped, each attempt reserved
# --------------------------------------------------------------------------


def test_a_rate_limit_is_retried_and_each_answered_error_is_released(ledger, _clean_env):
    client = _Client(_status_error(429, retry_after="1"), _status_error(503), _Usage(900, 20))
    result = _call(client)
    assert len(client.calls) == 3
    assert result.cost_usd is not None
    assert ledger.totals[DAY.isoformat()] == _micros((900 * 0.15 + 20 * 0.60) / 1e6)
    assert _clean_env[0] == 1.0  # honoured a short Retry-After
    assert len(_clean_env) == 2 and all(0 <= s <= llm_request.BACKOFF_CAP_S for s in _clean_env)


def test_a_timeout_is_retried_and_each_attempt_keeps_its_reservation(ledger):
    timeout = openai.APITimeoutError(request=_request())
    client = _Client(timeout, timeout, timeout)
    with pytest.raises(openai.APITimeoutError):
        _call(client)
    assert len(client.calls) == 1 + llm_request.DEFAULT_MAX_RETRIES
    assert ledger.totals[DAY.isoformat()] == 3 * RESERVATION


def test_a_bad_request_is_not_retried(ledger):
    client = _Client(_status_error(400), _Usage(1, 1))
    with pytest.raises(openai.BadRequestError):
        _call(client)
    assert len(client.calls) == 1
    assert ledger.totals[DAY.isoformat()] == 0


def test_max_retries_is_honoured_and_capped(ledger):
    err = _status_error(500)
    one = _Client(err, err, err)
    with pytest.raises(openai.InternalServerError):
        _call(one, max_retries=1)
    assert len(one.calls) == 2
    many = _Client(*([err] * 10))
    with pytest.raises(openai.InternalServerError):
        _call(many, max_retries=99)
    assert len(many.calls) == 1 + llm_request.MAX_RETRIES_CEILING


def test_a_retry_that_no_longer_fits_the_budget_stops(ledger, monkeypatch):
    monkeypatch.setenv(llm_request.DAILY_BUDGET_ENV, str(1.5 * RESERVATION / 1e6))
    timeout = openai.APITimeoutError(request=_request())
    client = _Client(timeout, _Usage(1, 1))
    with pytest.raises(LLMBudgetExceeded):
        _call(client)
    assert len(client.calls) == 1


# --------------------------------------------------------------------------
# Concurrency
# --------------------------------------------------------------------------


def test_a_call_with_no_free_slot_is_refused_and_slots_come_back(ledger, monkeypatch):
    monkeypatch.setenv(llm_request.CONCURRENCY_ENV, "1")
    monkeypatch.setattr(llm_request, "CONCURRENCY_WAIT_S", 0.01)
    slots = llm_request._get_slots()
    assert slots.acquire(timeout=0)
    client = _Client(_Usage(1, 1))
    with pytest.raises(LLMConcurrencyExhausted):
        _call(client)
    assert client.calls == []
    slots.release()
    with pytest.raises(ValueError):
        _call(_Client(ValueError("x")))
    _call(_Client(_Usage(1, 1)))  # the failed call gave its slot back


async def test_cancelling_the_awaiter_does_not_free_the_slot_while_the_call_runs(ledger, monkeypatch):
    monkeypatch.setenv(llm_request.CONCURRENCY_ENV, "1")
    monkeypatch.setattr(llm_request, "CONCURRENCY_WAIT_S", 0.01)
    started, finish = threading.Event(), threading.Event()

    class _Blocking(_Client):
        def __init__(self):
            super().__init__(_Usage(1, 1))
            inner = self.chat.completions.create

            def create(**kw):
                started.set()
                finish.wait(5)
                return inner(**kw)

            self.chat.completions.create = create

    task = asyncio.ensure_future(asyncio.to_thread(_call, _Blocking()))
    assert await asyncio.to_thread(started.wait, 5)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    with pytest.raises(LLMConcurrencyExhausted):
        _call(_Client(_Usage(1, 1)))  # the orphaned thread still holds the only slot
    finish.set()


# --------------------------------------------------------------------------
# Static guards: no client retries behind this layer's back
# --------------------------------------------------------------------------


def _calls(predicate):
    out = []
    for path in sorted(APP.rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Call) and predicate(node):
                out.append((str(path.relative_to(APP.parent)), node.lineno))
    return out


def _kw(node, name):
    return next((k.value for k in node.keywords if k.arg == name), None)


def test_every_openai_client_is_built_without_sdk_retries():
    def bad(node):
        if ast.unparse(node.func) not in {"OpenAI", "openai.OpenAI", "AsyncOpenAI", "openai.AsyncOpenAI"}:
            return False
        value = _kw(node, "max_retries")
        return not (isinstance(value, ast.Constant) and value.value == 0)

    assert _calls(lambda n: ast.unparse(n.func) in {"OpenAI", "openai.OpenAI"}), "the walk found no client"
    assert _calls(bad) == []


def test_no_with_options_reintroduces_sdk_retries():
    def bad(node):
        return isinstance(node.func, ast.Attribute) and node.func.attr == "with_options" and (
            _kw(node, "max_retries") is not None
        )

    assert _calls(bad) == []


def test_the_static_guards_bite_on_the_old_shapes(tmp_path, monkeypatch):
    bad = tmp_path / "app" / "bad.py"
    bad.parent.mkdir()
    bad.write_text(
        "import openai\n"
        "c = openai.OpenAI(timeout=30.0)\n"
        "c = c.with_options(timeout=8.0, max_retries=1)\n"
    )
    monkeypatch.setattr(__import__(__name__, fromlist=["APP"]), "APP", bad.parent)
    with pytest.raises(AssertionError):
        test_every_openai_client_is_built_without_sdk_retries()
    with pytest.raises(AssertionError):
        test_no_with_options_reintroduces_sdk_retries()


def test_the_registry_guard_bites_on_the_slice_2_shape_and_a_variable_task(tmp_path, monkeypatch):
    import tests.test_llm_model_registry_11042 as reg

    bad = tmp_path / "app" / "bad.py"
    bad.parent.mkdir()
    bad.write_text(
        "def f(client, t):\n"
        "    client.chat.completions.create(**chat_request_kwargs('hooks', max_output_tokens=1, temperature=0))\n"
        "    complete_chat(t, client, messages=[], max_output_tokens=1, temperature=0)\n"
        "    complete_chat('hooks', client, model='x', messages=[], max_output_tokens=1, temperature=0)\n"
    )
    monkeypatch.setattr(reg, "APP", bad.parent)
    assert reg._completion_sites() == [
        ("app/bad.py", 2, None, ()),
        ("app/bad.py", 3, None, ()),
        ("app/bad.py", 4, "hooks", ("model",)),
    ]


# --------------------------------------------------------------------------
# The production ledger's Lua, on a real redis-server
# --------------------------------------------------------------------------


def test_the_redis_ledger_checks_and_books_atomically(tmp_path, monkeypatch):
    redislite = pytest.importorskip("redislite")
    server = redislite.Redis(str(tmp_path / "ledger.rdb"))
    try:
        led = llm_request.RedisBudgetLedger()
        monkeypatch.setattr(led, "_client", lambda: server)
        day = DAY.isoformat()
        assert led.reserve(day, "hooks", 600, 1000) is True
        assert led.reserve(day, "cu_v2", 401, 1000) is False  # would cross the cap
        assert led.reserve(day, "cu_v2", 400, 1000) is True
        led.adjust(day, "hooks", -500)
        key = f"bainluck:llm_budget:{day}"
        assert int(server.get(key)) == 500
        assert int(server.hget(f"{key}:tasks", "hooks")) == 100
        assert int(server.hget(f"{key}:tasks", "cu_v2:calls")) == 1
        assert 0 < server.ttl(key) <= 3 * 24 * 3600

        results: list[bool] = []
        barrier = threading.Barrier(8)

        def racer():
            barrier.wait()
            results.append(led.reserve(day, "race", 100, 1000))

        threads = [threading.Thread(target=racer) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert results.count(True) == 5  # 500 left under the cap, 100 each
        assert int(server.get(key)) == 1000
    finally:
        server.shutdown()


# --------------------------------------------------------------------------
# The CU v2 writer: a refusal stops the batch and is not an error
# --------------------------------------------------------------------------


class _RefuseAfter(MemoryBudgetLedger):
    def __init__(self, admitted: int):
        super().__init__()
        self.admitted = admitted
        self.asked = 0

    def reserve(self, day, task, micros, cap_micros):
        self.asked += 1
        if self.admitted <= 0:
            return False
        self.admitted -= 1
        return super().reserve(day, task, micros, cap_micros)


@pytest.mark.parametrize("admitted", [0, 1])
async def test_cu_v2_stops_at_the_first_refused_reservation(monkeypatch, admitted):
    import tests.test_llm_model_registry_11042 as reg
    from app.tasks.enrich_markets import enrich_cu_v2_profiles

    ledger = _RefuseAfter(admitted)
    llm_request.set_ledger(ledger)
    client, write_session = reg._install(monkeypatch, usage=_Usage(900, 260), rows=3)
    stats = await enrich_cu_v2_profiles(limit=3)
    assert len(client.calls) == admitted
    assert ledger.asked == admitted + 1, "the first refusal ends the batch; later rows are not tried"
    assert len(reg._profiles(write_session)) == admitted
    assert "shared daily budget" in stats["budget_stopped"]
    assert stats["errors"] == 0


async def test_cu_v2_with_room_to_spare_records_no_stop(monkeypatch):
    """Control for the stop test: the same three rows with an open ledger."""
    import tests.test_llm_model_registry_11042 as reg
    from app.tasks.enrich_markets import enrich_cu_v2_profiles

    client, _ = reg._install(monkeypatch, usage=_Usage(900, 260), rows=3)
    stats = await enrich_cu_v2_profiles(limit=3)
    assert len(client.calls) == 3 and stats["budget_stopped"] is None


async def test_cu_v2_reserves_against_its_own_per_run_cap(monkeypatch):
    """The $30 run cap is enforced before each call, not only after the spend."""
    import tests.test_llm_model_registry_11042 as reg
    from app.tasks import enrich_markets

    monkeypatch.setattr(enrich_markets, "CU_V2_COST_CAP_USD", 1e-6)
    client, write_session = reg._install(monkeypatch, usage=_Usage(900, 260), rows=3)
    stats = await enrich_markets.enrich_cu_v2_profiles(limit=3)
    assert client.calls == [] and reg._profiles(write_session) == []
    assert "job budget" in stats["budget_stopped"]
