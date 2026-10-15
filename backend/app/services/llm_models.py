"""The one place a backend LLM model id, its request shape and its price live (#11042).

OpenAI retires ``gpt-4o-mini`` on 2027-01-14 (official deprecation page, checked
2026-10-14; replacement ``gpt-6-luna``). Before this module every call site
hard-coded the old id, so a model change was a 24-site string substitution, and
the CU v2 cost cap multiplied by the old prices inline.

Three rules, each enforced by ``tests/test_llm_model_registry_11042.py``:

1. **Every production completion call builds its arguments here**
   (``chat_request_kwargs``). No call site passes ``model=``, ``max_tokens=`` or
   ``temperature=`` itself, and no model id appears as a string literal anywhere
   else in ``backend/app``.
2. **Selection is task-scoped and attended.** ``LLM_MODEL_<TASK>`` overrides one
   task, ``LLM_MODEL`` overrides all, and with neither set the task keeps today's
   model. Merging this module changes NO production request: the replacement is
   enabled by a config var after the frozen-input comparison and a bounded canary
   (#11042 slice 5), and undone with ``heroku config:unset``.
3. **Unknown fails closed.** A configured model with no recorded request shape or
   price raises ``UnsupportedModelError`` — every call site already turns an
   exception into its existing deterministic/no-copy fallback — and a response
   with no usage has an UNKNOWN cost (``None``), never a zero one.

The January fallback is rule 2's date check: once a model's shutdown date has
passed, ``resolve_model`` stops asking for it and uses its recorded replacement,
so a forgotten config var cannot turn every LLM feature into an error on
2027-01-14. That is the supported floor, not the migration — the migration is
the attended flip before December 1.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)


class UnsupportedModelError(RuntimeError):
    """A configured model has no recorded request shape or price."""


@dataclass(frozen=True)
class ModelSpec:
    """What the request layer must know about a model before it may call it.

    ``reasoning`` models take ``max_completion_tokens`` and an explicit
    ``reasoning_effort``; legacy chat models take ``max_tokens``. Prices are USD
    per million tokens at the standard (non-batch) tier. No cached-input rate is
    recorded, so cached prompt tokens are charged at the full input rate — an
    upper bound, never an undercount.
    """

    model: str
    reasoning: bool
    input_per_m: float
    output_per_m: float
    #: Reasoning models only. ``"none"`` preserves today's non-reasoning
    #: behaviour; the replacement otherwise defaults to ``medium`` and would bill
    #: hidden reasoning tokens the old model never spent.
    reasoning_effort: Optional[str] = None
    #: After this date the provider no longer serves the model.
    shutdown: Optional[date] = None
    replacement: Optional[str] = None


LEGACY_MODEL = "gpt-4o-mini"
REPLACEMENT_MODEL = "gpt-6-luna"

#: Rates from the provider model pages as recorded in #11042 (2026-10-14).
#: Re-check them at the canary: a lower listed rate does not prove a lower task
#: cost, and an unrecorded rate is a refusal, not a guess.
MODELS: dict[str, ModelSpec] = {
    LEGACY_MODEL: ModelSpec(
        model=LEGACY_MODEL,
        reasoning=False,
        input_per_m=0.15,
        output_per_m=0.60,
        shutdown=date(2027, 1, 14),
        replacement=REPLACEMENT_MODEL,
    ),
    REPLACEMENT_MODEL: ModelSpec(
        model=REPLACEMENT_MODEL,
        reasoning=True,
        input_per_m=0.10,
        output_per_m=0.50,
        reasoning_effort="none",
    ),
}

#: The active-call inventory (#11042 slice 1): task -> the reader it feeds.
#: A task name is also its override suffix (``LLM_MODEL_HOOKS``). Adding a call
#: site means adding a row; the guard test refuses an unregistered task.
TASKS: dict[str, str] = {
    # services/llm.py
    "classify": "sport/category classification for events and futures",
    "classify_open_ended": "futures category when the closed list declines",
    "generate_tags": "futures market tags",
    "match_team_names": "admin provider team-name match",
    "normalize_team_name": "team identity normalisation",
    "classify_player_team": "player-to-team linking",
    "line_movement_explanation": "dormant: no caller in backend/app",
    "golf_live_commentary": "live golf commentary box",
    "market_disagreement_explanation": "event page source-disagreement note",
    "oscars_category_preview": "Oscars category previews",
    "oscars_movers_summary": "Oscars movers summary",
    "related_futures_summary": "dormant: no caller in backend/app",
    "audit_match": "matching audit verdicts",
    "event_taxonomy": "event taxonomy tags",
    "market_taxonomy": "futures market taxonomy tags",
    # tasks/enrich_markets.py
    "hooks": "Discover card hooks",
    "discover_metadata": "Discover LLM metadata (schema v1)",
    "cu_v2": "Content Understanding v2 profiles",
    "comparison_candidates": "Discover comparison pairs",
    "discover_eval": "Discover LLM review",
    "snippet_rephrase": "snippet angle rephrasing",
    # other
    "admin_diagnosis": "admin ops diagnosis panel",
    "bug_fixed_email": "bug-fixed notification email body",
}

#: Pre-registry per-family override, still honoured so an existing deployment
#: setting keeps its meaning. Neither production app sets it (2026-10-14 read).
_LEGACY_ENV: dict[str, str] = {
    task: "DISCOVER_LLM_MODEL"
    for task in ("discover_metadata", "cu_v2", "comparison_candidates", "discover_eval")
}


def _today_utc() -> date:
    return datetime.now(timezone.utc).date()


def resolve_model(task: str, *, today: Optional[date] = None) -> str:
    """The model ``task`` should call now.

    Order: ``LLM_MODEL_<TASK>``, the task's pre-registry variable, ``LLM_MODEL``,
    then ``LEGACY_MODEL`` (today's behaviour). Raises ``UnsupportedModelError``
    for an unregistered task or an unrecorded model.
    """
    if task not in TASKS:
        raise UnsupportedModelError(f"unregistered LLM task {task!r}")
    candidates = (
        os.getenv(f"LLM_MODEL_{task.upper()}"),
        os.getenv(_LEGACY_ENV[task]) if task in _LEGACY_ENV else None,
        os.getenv("LLM_MODEL"),
    )
    model = next((c.strip() for c in candidates if c and c.strip()), LEGACY_MODEL)
    spec = MODELS.get(model)
    if spec is None:
        raise UnsupportedModelError(f"no recorded request shape/price for model {model!r}")
    day = today or _today_utc()
    if spec.shutdown is not None and day >= spec.shutdown:
        logger.warning(
            "LLM task %s configured for %s, shut down %s; using %s",
            task, model, spec.shutdown.isoformat(), spec.replacement,
        )
        model = spec.replacement or ""
        if model not in MODELS:
            raise UnsupportedModelError(f"{spec.model} is shut down and has no recorded replacement")
    return model


def chat_request_kwargs(
    task: str,
    *,
    max_output_tokens: int,
    temperature: float,
    today: Optional[date] = None,
) -> dict[str, Any]:
    """Chat Completions arguments for ``task``: model, token limit, sampling.

    The caller adds ``messages`` and, where it already uses one,
    ``response_format``. ``max_output_tokens`` is the visible-output budget the
    call site has always had; with ``reasoning_effort="none"`` no hidden
    reasoning tokens compete for it.
    """
    model = resolve_model(task, today=today)
    spec = MODELS[model]
    if spec.reasoning:
        kwargs: dict[str, Any] = {
            "model": model,
            "max_completion_tokens": max_output_tokens,
            "reasoning_effort": spec.reasoning_effort,
        }
        # Sampling parameters are accepted only without reasoning; with any
        # other effort they are dropped rather than sent to be refused.
        if spec.reasoning_effort == "none":
            kwargs["temperature"] = temperature
        return kwargs
    return {"model": model, "max_tokens": max_output_tokens, "temperature": temperature}


#: Chat Completions frames each message with a few special tokens and primes
#: the reply with a few more (3-4 each today). Both are over-provisioned: the
#: bound below is a reservation, and a low bound would undercount.
_MESSAGE_FRAME_TOKENS = 8
_REPLY_PRIMER_TOKENS = 8


def prompt_tokens_upper_bound(messages: Any) -> int:
    """An upper bound on the prompt tokens ``messages`` will be billed for.

    Byte-level BPE tokens each cover at least one byte, so a message's UTF-8
    byte count bounds its token count without loading a tokenizer. Non-string
    fields are counted as their JSON text, which is longer than what is sent.
    """
    import json

    total = _REPLY_PRIMER_TOKENS
    for message in messages:
        total += _MESSAGE_FRAME_TOKENS
        for value in message.values():
            text = value if isinstance(value, str) else json.dumps(value, default=str)
            total += len(text.encode("utf-8"))
    return total


def cost_upper_bound_usd(model: str, messages: Any, max_output_tokens: int) -> float:
    """The most one request can be billed: the prompt bound plus a full answer.

    With ``max_completion_tokens`` the output limit caps reasoning and visible
    tokens together, so it bounds both. Raises ``UnsupportedModelError`` for an
    unrecorded model — an unpriced call cannot be reserved.
    """
    spec = MODELS.get(model)
    if spec is None:
        raise UnsupportedModelError(f"no recorded price for model {model!r}")
    prompt = prompt_tokens_upper_bound(messages)
    return (prompt * spec.input_per_m + max_output_tokens * spec.output_per_m) / 1_000_000


def estimate_cost_usd(model: str, usage: Any) -> Optional[float]:
    """USD for one response's ``usage``, or ``None`` when it cannot be known.

    ``None`` for an unrecorded model or a response with no usable token counts.
    Reasoning tokens are billed as output and are already inside
    ``completion_tokens``; cached prompt tokens are charged at the full input
    rate (see ``ModelSpec``).
    """
    spec = MODELS.get(model)
    if spec is None or usage is None:
        return None
    prompt = getattr(usage, "prompt_tokens", None)
    completion = getattr(usage, "completion_tokens", None)
    if not isinstance(prompt, int) or not isinstance(completion, int):
        return None
    if prompt < 0 or completion < 0:
        return None
    return (prompt * spec.input_per_m + completion * spec.output_per_m) / 1_000_000
