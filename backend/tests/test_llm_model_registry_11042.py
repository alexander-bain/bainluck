"""#11042 — every backend LLM call gets its model, request shape and price from one place.

OpenAI shuts ``gpt-4o-mini`` down on 2027-01-14. Before this, 24 call sites
hard-coded it and the CU v2 cost cap multiplied by its prices inline. These tests
pin the three rules in ``app.services.llm_models``:

* the call sites cannot name a model or a token limit themselves (static guard,
  read from the AST of every ``backend/app`` file, so a new call site is caught
  the day it lands);
* with no config var set, every task keeps the model it called before — merging
  changes no production request — and the replacement gets a reasoning-model
  request shape when it is selected;
* an unknown model refuses and a response with no usage has an unknown cost,
  which stops the CU v2 batch instead of counting as free.

No test makes a network call. Dates are passed in, never read from the clock.
"""

from __future__ import annotations

import ast
import json
import pathlib
import re
from contextlib import asynccontextmanager
from datetime import date

import pytest

from app.services import llm_models
from app.services.llm_models import (
    LEGACY_MODEL,
    MODELS,
    REPLACEMENT_MODEL,
    TASKS,
    UnsupportedModelError,
    chat_request_kwargs,
    estimate_cost_usd,
    resolve_model,
)
from app.tasks.enrich_markets import DISCOVER_LLM_METADATA_KEY, enrich_cu_v2_profiles
from tests.test_cu_frame_grounding import (
    T_CLARK,
    _FakeResult,
    _FakeSession,
    _llm_payload,
)

APP = pathlib.Path(__file__).resolve().parents[1] / "app"
REGISTRY = APP / "services" / "llm_models.py"
BEFORE_SHUTDOWN = date(2026, 12, 1)
SHUTDOWN = date(2027, 1, 14)

_ENV = ("LLM_MODEL", "DISCOVER_LLM_MODEL", *(f"LLM_MODEL_{t.upper()}" for t in TASKS))


@pytest.fixture(autouse=True)
def _clean_model_env(monkeypatch):
    for name in _ENV:
        monkeypatch.delenv(name, raising=False)


# --------------------------------------------------------------------------
# Static guard: call sites cannot choose a model, and the inventory is complete
# --------------------------------------------------------------------------

_FORBIDDEN_KWARGS = {"model", "max_tokens", "max_completion_tokens", "temperature", "reasoning_effort"}
_MODEL_ID = re.compile(r"(gpt-\d[\w.\-]*|o\d(-mini|-pro)?|chatgpt-[\w.\-]+)")


def _app_files():
    return sorted(p for p in APP.rglob("*.py") if p != REGISTRY)


def _is_completion_call(node: ast.AST) -> bool:
    if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
        return False
    chain = ast.unparse(node.func)
    return node.func.attr == "create" and ("completions" in chain or "responses" in chain)


def _registry_task(call: ast.AST) -> str | None:
    """The literal task of a ``chat_request_kwargs("<task>", ...)`` call, else None."""
    if (
        isinstance(call, ast.Call)
        and isinstance(call.func, ast.Name)
        and call.func.id == "chat_request_kwargs"
        and call.args
        and isinstance(call.args[0], ast.Constant)
        and isinstance(call.args[0].value, str)
    ):
        return call.args[0].value
    return None


def _completion_sites():
    """(path, line, task-or-None, forbidden kwargs) for every completion call."""
    sites = []
    for path in _app_files():
        tree = ast.parse(path.read_text())
        for func in ast.walk(tree):
            if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            assigned = {}
            for node in ast.walk(func):
                if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                    task = _registry_task(node.value)
                    if task:
                        assigned[node.targets[0].id] = task
            for node in ast.walk(func):
                if not _is_completion_call(node):
                    continue
                forbidden = sorted(k.arg for k in node.keywords if k.arg in _FORBIDDEN_KWARGS)
                task = None
                for k in node.keywords:
                    if k.arg is None:
                        task = _registry_task(k.value) or (
                            assigned.get(k.value.id) if isinstance(k.value, ast.Name) else None
                        )
                sites.append((path.relative_to(APP.parent), node.lineno, task, forbidden))
    # A call nested in two functions is visited once per enclosing def; keep one.
    return sorted(set((str(p), ln, t, tuple(f)) for p, ln, t, f in sites))


def test_every_completion_call_builds_its_arguments_in_the_registry():
    sites = _completion_sites()
    assert len(sites) >= 23, sites  # the 2026-10-14 inventory; fewer means the walk broke
    offenders = [s for s in sites if s[2] is None or s[3]]
    assert offenders == [], (
        "completion calls must take **chat_request_kwargs(<registered task>, ...) and pass "
        f"no model/token/sampling kwargs themselves: {offenders}"
    )


def test_the_task_inventory_matches_the_call_sites_both_ways():
    used = {task for _, _, task, _ in _completion_sites()}
    assert used - set(TASKS) == set(), "call site names an unregistered task"
    assert set(TASKS) - used == set(), "registry lists a task no call site uses"


def test_no_model_id_literal_outside_the_registry():
    hits = []
    for path in _app_files():
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if node.value in MODELS or _MODEL_ID.fullmatch(node.value):
                    hits.append((str(path.relative_to(APP.parent)), node.lineno, node.value))
    assert hits == [], f"model ids belong in app/services/llm_models.py only: {hits}"


def test_direct_openai_clients_have_a_finite_timeout():
    missing = []
    for path in _app_files():
        for node in ast.walk(ast.parse(path.read_text())):
            if (
                isinstance(node, ast.Call)
                and ast.unparse(node.func) in {"OpenAI", "openai.OpenAI"}
                and not any(k.arg == "timeout" for k in node.keywords)
            ):
                missing.append((str(path.relative_to(APP.parent)), node.lineno))
    assert missing == []


def test_the_static_guard_bites_on_a_hard_coded_call(tmp_path, monkeypatch):
    """Strawman: the old shape, verbatim, must be reported by both guards."""
    bad = tmp_path / "app" / "bad.py"
    bad.parent.mkdir()
    bad.write_text(
        "def f(client):\n"
        "    return client.chat.completions.create(\n"
        '        model="gpt-4o-mini", messages=[], max_tokens=10, temperature=0,\n'
        "    )\n"
    )
    monkeypatch.setattr(__import__(__name__, fromlist=["APP"]), "APP", bad.parent)
    sites = _completion_sites()
    assert sites == [("app/bad.py", 2, None, ("max_tokens", "model", "temperature"))]
    with pytest.raises(AssertionError):
        test_no_model_id_literal_outside_the_registry()


# --------------------------------------------------------------------------
# Selection: unchanged by default, task-scoped when configured, fails closed
# --------------------------------------------------------------------------


def test_with_no_config_every_task_keeps_todays_model_and_request_shape():
    for task in TASKS:
        assert chat_request_kwargs(task, max_output_tokens=50, temperature=0, today=BEFORE_SHUTDOWN) == {
            "model": LEGACY_MODEL, "max_tokens": 50, "temperature": 0,
        }


def test_replacement_gets_a_non_reasoning_reasoning_model_request(monkeypatch):
    monkeypatch.setenv("LLM_MODEL", REPLACEMENT_MODEL)
    kwargs = chat_request_kwargs("cu_v2", max_output_tokens=500, temperature=0.1, today=BEFORE_SHUTDOWN)
    assert kwargs == {
        "model": REPLACEMENT_MODEL,
        "max_completion_tokens": 500,
        "reasoning_effort": "none",
        "temperature": 0.1,
    }
    assert "max_tokens" not in kwargs


def test_a_reasoning_effort_other_than_none_drops_sampling(monkeypatch):
    spec = MODELS[REPLACEMENT_MODEL]
    monkeypatch.setitem(
        llm_models.MODELS, REPLACEMENT_MODEL,
        llm_models.ModelSpec(**{**spec.__dict__, "reasoning_effort": "low"}),
    )
    monkeypatch.setenv("LLM_MODEL", REPLACEMENT_MODEL)
    kwargs = chat_request_kwargs("hooks", max_output_tokens=150, temperature=0.7, today=BEFORE_SHUTDOWN)
    assert "temperature" not in kwargs and kwargs["reasoning_effort"] == "low"


def test_override_precedence_task_then_family_then_global(monkeypatch):
    monkeypatch.setenv("LLM_MODEL", REPLACEMENT_MODEL)
    monkeypatch.setenv("DISCOVER_LLM_MODEL", LEGACY_MODEL)
    assert resolve_model("cu_v2", today=BEFORE_SHUTDOWN) == LEGACY_MODEL  # family beats global
    assert resolve_model("hooks", today=BEFORE_SHUTDOWN) == REPLACEMENT_MODEL  # not in the family
    monkeypatch.setenv("LLM_MODEL_CU_V2", REPLACEMENT_MODEL)
    assert resolve_model("cu_v2", today=BEFORE_SHUTDOWN) == REPLACEMENT_MODEL  # task beats family
    assert resolve_model("discover_eval", today=BEFORE_SHUTDOWN) == LEGACY_MODEL


def test_an_unrecorded_model_or_task_refuses(monkeypatch):
    with pytest.raises(UnsupportedModelError):
        resolve_model("not_a_task", today=BEFORE_SHUTDOWN)
    monkeypatch.setenv("LLM_MODEL_HOOKS", "gpt-6-lunaa")
    with pytest.raises(UnsupportedModelError):
        chat_request_kwargs("hooks", max_output_tokens=10, temperature=0, today=BEFORE_SHUTDOWN)


def test_a_shut_down_model_is_never_requested_on_or_after_its_date(monkeypatch):
    assert resolve_model("classify", today=date(2027, 1, 13)) == LEGACY_MODEL
    assert resolve_model("classify", today=SHUTDOWN) == REPLACEMENT_MODEL
    monkeypatch.setenv("LLM_MODEL", LEGACY_MODEL)  # an explicit pin does not survive it either
    assert resolve_model("classify", today=SHUTDOWN) == REPLACEMENT_MODEL


def test_every_retiring_model_names_a_live_replacement():
    for spec in MODELS.values():
        if spec.shutdown is None:
            continue
        repl = MODELS.get(spec.replacement)
        assert repl is not None, spec.model
        assert repl.shutdown is None or repl.shutdown > spec.shutdown


# --------------------------------------------------------------------------
# Accounting: model-aware, and unknown is never zero
# --------------------------------------------------------------------------


class _Usage:
    def __init__(self, prompt_tokens, completion_tokens):
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens


def test_cost_uses_the_answering_models_rates():
    assert estimate_cost_usd(LEGACY_MODEL, _Usage(1_000_000, 1_000_000)) == pytest.approx(0.75)
    assert estimate_cost_usd(REPLACEMENT_MODEL, _Usage(1_000_000, 1_000_000)) == pytest.approx(0.60)
    assert estimate_cost_usd(LEGACY_MODEL, _Usage(900, 260)) == pytest.approx((900 * 0.15 + 260 * 0.60) / 1e6)


@pytest.mark.parametrize("usage", [None, _Usage(None, 10), _Usage(10, None), _Usage(-1, 10), _Usage("9", 1)])
def test_missing_or_malformed_usage_is_unknown_not_free(usage):
    assert estimate_cost_usd(LEGACY_MODEL, usage) is None


def test_an_unpriced_model_has_unknown_cost():
    assert estimate_cost_usd("gpt-9-unpriced", _Usage(10, 10)) is None


# --------------------------------------------------------------------------
# The CU v2 writer end to end: provenance, request shape, unknown-cost stop
# --------------------------------------------------------------------------


class _RecordingClient:
    """``contents``: one answer per call, cycling; the default is a valid profile."""

    def __init__(self, usage, contents=None):
        self.calls = []
        outer = self
        answers = list(contents or [json.dumps(_llm_payload())])

        class _Completions:
            def create(self, **kwargs):
                content = answers[len(outer.calls) % len(answers)]
                outer.calls.append(kwargs)
                return type("R", (), {
                    "choices": [type("C", (), {
                        "message": type("M", (), {"content": content})()
                    })()],
                    "usage": usage,
                })()

        self.chat = type("Chat", (), {"completions": _Completions()})()


@asynccontextmanager
async def _cm(session):
    yield session


def _install(monkeypatch, *, usage, rows=1, contents=None):
    read_rows = [{
        "id": 1234 + i, "name": T_CLARK, "source": "kalshi", "status": "open",
        "category": "basketball", "resolution_date": None, "market_metadata": {},
        "outcomes": [{"name": "Yes", "prob": 0.4, "move": 0.0}],
    } for i in range(rows)]
    write_session = _FakeSession()
    sessions = iter([_FakeSession([_FakeResult(read_rows)]), write_session, _FakeSession()])
    monkeypatch.setattr("app.tasks.enrich_markets.get_task_session", lambda: _cm(next(sessions)))
    client = _RecordingClient(usage, contents)
    monkeypatch.setattr("app.services.llm._get_client", lambda: client)

    async def no_aliases(session, names, **kw):
        return {}

    async def no_sleep(_s):
        return None

    monkeypatch.setattr("app.services.entity_registry.resolve_aliases", no_aliases)
    monkeypatch.setattr("app.tasks.enrich_markets.asyncio.sleep", no_sleep)
    return client, write_session


def _profiles(write_session):
    out = []
    for stmt, _ in write_session.executed:
        try:
            md = stmt.compile().params.get("market_metadata")
        except Exception:
            continue
        if isinstance(md, dict) and DISCOVER_LLM_METADATA_KEY in md:
            out.append(md[DISCOVER_LLM_METADATA_KEY])
    return out


async def test_cu_v2_default_records_the_legacy_model_and_its_cost(monkeypatch):
    client, write_session = _install(monkeypatch, usage=_Usage(900, 260))
    stats = await enrich_cu_v2_profiles(limit=1)
    assert client.calls[0]["model"] == LEGACY_MODEL and client.calls[0]["max_tokens"] == 500
    assert [p["model"] for p in _profiles(write_session)] == [LEGACY_MODEL]
    assert stats["estimated_cost_usd"] == pytest.approx((900 * 0.15 + 260 * 0.60) / 1e6)
    assert stats["cost_unknown_responses"] == 0


async def test_cu_v2_on_the_replacement_records_it_and_prices_it(monkeypatch):
    monkeypatch.setenv("LLM_MODEL_CU_V2", REPLACEMENT_MODEL)
    client, write_session = _install(monkeypatch, usage=_Usage(900, 260))
    stats = await enrich_cu_v2_profiles(limit=1)
    call = client.calls[0]
    assert call["model"] == REPLACEMENT_MODEL
    assert call["max_completion_tokens"] == 500 and call["reasoning_effort"] == "none"
    assert "max_tokens" not in call
    assert call["response_format"] == {"type": "json_object"}
    assert [p["model"] for p in _profiles(write_session)] == [REPLACEMENT_MODEL]
    assert stats["estimated_cost_usd"] == pytest.approx((900 * 0.10 + 260 * 0.50) / 1e6)


async def test_cu_v2_stops_after_a_response_with_unknown_cost(monkeypatch):
    client, write_session = _install(monkeypatch, usage=None, rows=3)
    stats = await enrich_cu_v2_profiles(limit=3)
    assert len(client.calls) == 1, "unknown cost must stop the batch, not count as $0"
    assert stats["cost_unknown_responses"] == 1
    assert stats["estimated_cost_usd"] == 0.0
    assert len(_profiles(write_session)) == 1  # the answer already paid for is kept


async def test_cu_v2_with_known_cost_processes_every_item(monkeypatch):
    """Control for the stop test: same three rows, usage present, all three called."""
    client, _ = _install(monkeypatch, usage=_Usage(900, 260), rows=3)
    stats = await enrich_cu_v2_profiles(limit=3)
    assert len(client.calls) == 3
    assert stats["cost_unknown_responses"] == 0


# CERT-4125's counterexamples: the answer's content is read AFTER it is paid for.
_MALFORMED = "not json at all"


async def test_cu_v2_malformed_answers_with_no_usage_still_stop_the_batch(monkeypatch):
    client, write_session = _install(monkeypatch, usage=None, rows=3, contents=[_MALFORMED])
    stats = await enrich_cu_v2_profiles(limit=3)
    assert len(client.calls) == 1
    assert stats["cost_unknown_responses"] == 1 and stats["errors"] == 1
    assert _profiles(write_session) == []


async def test_cu_v2_first_answer_malformed_with_no_usage_stops_before_the_second(monkeypatch):
    client, write_session = _install(
        monkeypatch, usage=None, rows=3, contents=[_MALFORMED, json.dumps(_llm_payload())]
    )
    stats = await enrich_cu_v2_profiles(limit=3)
    assert len(client.calls) == 1
    assert stats["cost_unknown_responses"] == 1


async def test_cu_v2_a_malformed_answer_with_known_usage_is_still_paid_for(monkeypatch):
    client, _ = _install(monkeypatch, usage=_Usage(900, 260), rows=1, contents=[_MALFORMED])
    stats = await enrich_cu_v2_profiles(limit=1)
    assert len(client.calls) == 1 and stats["errors"] == 1
    assert stats["estimated_cost_usd"] == pytest.approx((900 * 0.15 + 260 * 0.60) / 1e6)
    assert (stats["input_tokens"], stats["output_tokens"]) == (900, 260)


@pytest.mark.parametrize("usage", [_Usage(900, None), _Usage(None, 260)])
async def test_cu_v2_incomplete_usage_stops_the_batch(monkeypatch, usage):
    client, write_session = _install(monkeypatch, usage=usage, rows=3)
    stats = await enrich_cu_v2_profiles(limit=3)
    assert len(client.calls) == 1
    assert stats["cost_unknown_responses"] == 1 and stats["estimated_cost_usd"] == 0.0
    assert len(_profiles(write_session)) == 1
