"""Attended worker for the frozen #1809 coverage roster."""

from __future__ import annotations

import asyncio
import base64
from collections import Counter
from datetime import datetime, timezone
import gzip
from hashlib import sha256
import json
from math import ceil
import os
from pathlib import Path
from threading import Event
from time import monotonic
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.llm import _get_client
from app.services.llm_models import MODELS, cost_upper_bound_usd, resolve_model
from app.services.llm_request import (
    LLMCallRefused,
    LLMBudgetExceeded,
    LLMBudgetUnavailable,
    RedisBudgetLedger,
    _get_ledger,
    complete_chat_detailed,
    daily_budget_micros,
    set_ledger,
)
from app.tasks import enrich_markets as writer
from app.tasks.base import _get_task_engine, get_task_session
from app.tasks.task_checkpoint import release_overlap_lock, try_acquire_overlap_lock

from . import budget, store
from .frozen import (
    BLOCK_SIZE,
    PILOT_SHA256,
    PROMPT_SHA256,
    ROSTER_SHA256,
    SOURCE_SHA256,
    approved_block,
)


INPUT = text(
    """
    SELECT fm.id, fm.name, fm.source, fm.status, fm.resolution_date,
           COALESCE(fm.llm_sport_category, fm.category, 'other') AS category,
           CAST(fm.market_metadata -> 'discover_llm' AS text) AS profile_json,
           fm.event_id AS linked_game_id, e.commence_time AS linked_start,
           e.commence_time_source AS start_source, league.key AS linked_league,
           home_league.key AS home_team_league, away_league.key AS away_team_league,
           (SELECT json_agg(json_build_object(
                'name', fo.name, 'prob', fo.current_probability,
                'move', fo.probability_change_24h
            ) ORDER BY fo.rank ASC NULLS LAST, fo.id)
            FROM futures_outcomes AS fo WHERE fo.market_id = fm.id) AS outcomes
    FROM futures_markets AS fm
    LEFT JOIN events e ON e.id = fm.event_id
    LEFT JOIN sports league ON league.id = e.sport_id
    LEFT JOIN teams home_team ON home_team.id = e.home_team_id
    LEFT JOIN teams away_team ON away_team.id = e.away_team_id
    LEFT JOIN sports home_league ON home_league.id = home_team.sport_id
    LEFT JOIN sports away_league ON away_league.id = away_team.sport_id
    WHERE fm.id = :market_id
"""
)
OUTPUT_TOKENS = 500
TASK = "cu_v2"
MODEL = "gpt-4o-mini"
RATES = (0.15, 0.60)


class PilotStopped(RuntimeError):
    """A planned or protective stop with no additional requests."""


class CoverageLedger(RedisBudgetLedger):
    """Treat a failed shared settlement as a stop for this attended run."""

    def __init__(self):
        super().__init__()
        self.adjustment_failed = Event()

    def reserve(self, day, task, micros, cap_micros):
        if self.adjustment_failed.is_set():
            raise LLMBudgetUnavailable(
                "an earlier coverage settlement could not reach the ledger"
            )
        return super().reserve(day, task, micros, cap_micros)

    def adjust(self, day, task, delta):
        try:
            super().adjust(day, task, delta)
        except Exception:
            self.adjustment_failed.set()
            raise


def prompt_hash() -> str:
    return sha256(writer._CU_V2_PROMPT.encode()).hexdigest()


def validate_payload(payload: dict) -> None:
    ids = payload["roster_ids"]
    excluded = payload["excluded_sample_ids"]
    recover = payload.get("recover_failed_ids", [])
    if not (
        payload["manifest_sha256"] == ROSTER_SHA256
        and payload["pilot_sha256"] == PILOT_SHA256
        and payload["model"] == MODEL
        and approved_block(payload["start"], payload["end"], ids)
        and len(recover) <= budget.MAX_IN_FLIGHT
        and set(recover).issubset(ids)
        and len(excluded) == len(set(excluded)) == 50
        and bool(payload["sample_seed"])
        and type(payload.get("use_elevated_cap", False)) is bool
    ):
        raise PilotStopped("the frozen coverage roster failed validation")
    if writer.CU_WRITER_REV != store.WRITER_REV or prompt_hash() != PROMPT_SHA256:
        raise PilotStopped(
            "the deployed writer differs from the approved prompt or revision"
        )
    require_approved_source()


def require_approved_source() -> None:
    import app.utils.cu_junk_flags as flags
    import app.utils.cu_event_facts as facts

    modules = {"writer": writer, "junk_flags": flags, "event_facts": facts}
    for name, module in modules.items():
        if (
            sha256(Path(module.__file__).read_bytes()).hexdigest()
            != SOURCE_SHA256[name]
        ):
            raise PilotStopped(f"live {name} source differs from the approved release")


def preflight(payload: dict) -> None:
    model = resolve_model(TASK)
    spec = MODELS[model]
    if model != MODEL or (spec.input_per_m, spec.output_per_m) != RATES:
        raise PilotStopped("the worker model or rates differ from the approved plan")
    shared_cap = daily_budget_micros()
    redis = _get_ledger()._client()
    if not redis.ping():
        raise PilotStopped("the shared spend ledger is unavailable")
    day = datetime.now(timezone.utc).date().isoformat()
    int(redis.get(f"bainluck:llm_budget:{day}") or 0)
    if payload["use_elevated_cap"] and shared_cap != budget.ELEVATED_SHARED_MICROS:
        raise PilotStopped("the shared allowance for the elevated run is unavailable")


async def read_market(
    engine, market_id: int
) -> tuple[dict | None, dict | None, dict | None]:
    async with get_task_session(engine=engine) as db, db.begin():
        await db.execute(text("SET TRANSACTION READ ONLY"))
        row = (
            (await db.execute(INPUT, {"market_id": market_id})).mappings().one_or_none()
        )
        if row is None:
            return None, None, None
        before_image = await store._read_undo(db, market_id)
        attempt = await budget.read_attempt(db, market_id)
        return dict(row), before_image, attempt


def market_prompt(row: dict) -> tuple[str, list[float], dict, dict]:
    outcomes = row["outcomes"] or []
    if isinstance(outcomes, str):
        outcomes = json.loads(outcomes)
    lines = [writer._cu_prompt_outcome(outcome) for outcome in outcomes[:8]]
    source = {
        "name": row["name"] or "",
        "category": row["category"],
        "source": row["source"] or "",
        "resolution_date": (
            row["resolution_date"].isoformat() if row["resolution_date"] else "unknown"
        ),
        "outcomes": "\n".join(lines) if lines else "- unknown",
    }
    prompt = writer._CU_V2_PROMPT.format(
        **source,
        measure_vocabulary=", ".join(sorted(writer.CU_FRAME_MEASURES)),
    )
    event_facts = writer.cu_event_facts(
        row["name"] or "",
        linked_game_id=row.get("linked_game_id"),
        linked_start=row.get("linked_start"),
        start_source=row.get("start_source"),
        **fixture_leagues(row),
    )
    if event_facts:
        prompt += (
            f"\n\nOmit these fields. Bain Luck supplies them: {', '.join(event_facts)}."
        )
    source["option_names"] = [outcome.get("name") for outcome in outcomes]
    source["event_facts"] = event_facts
    probabilities = [
        float(outcome["prob"])
        for outcome in outcomes
        if outcome.get("prob") is not None
    ]
    return prompt, probabilities, source, event_facts


def fixture_leagues(row: dict) -> dict:
    return {
        key: row.get(key)
        for key in ("linked_league", "home_team_league", "away_team_league")
    }


async def journal_write(engine, journal_lock, operation, **kwargs):
    # Four provider calls can overlap. The local worker has only one spend row.
    async with journal_lock:
        for number in range(3):
            try:
                async with get_task_session(engine=engine) as db:
                    return await operation(db, **kwargs)
            except (DBAPIError, budget.CoverageJournalWriteError) as error:
                if isinstance(error, DBAPIError) and not (
                    error.connection_invalidated
                    or getattr(error.orig, "sqlstate", None)
                    in {"55P03", "57014", "40P01", "40001"}
                ):
                    raise
                if number == 2:
                    raise
                await asyncio.sleep(0.05 * (number + 1))


async def request_profile(
    engine, client, payload, market_id, prompt, previous, journal_lock
) -> str:
    model = payload["model"]
    digest = sha256(prompt.encode()).hexdigest()
    if previous is not None and previous["status"] == "charged":
        if previous["prompt_sha256"] != digest or previous["model"] != model:
            raise PilotStopped(f"input changed after a paid call for {market_id}")
        return previous["content"]
    messages = [{"role": "user", "content": prompt}]
    today = datetime.now(timezone.utc).date()
    if resolve_model(TASK, today=today) != model:
        raise PilotStopped("the resolved CU model differs from the pinned model")
    reservation = budget.Reservation(
        market_id,
        today.isoformat(),
        model,
        digest,
        ceil(cost_upper_bound_usd(model, messages, OUTPUT_TOKENS) * 1_000_000),
    )
    await journal_write(
        engine,
        journal_lock,
        budget.reserve,
        manifest_sha256=payload["manifest_sha256"],
        reservation=reservation,
        shared_daily_micros=daily_budget_micros(),
        use_elevated_cap=payload.get("use_elevated_cap", False),
    )

    async def settle(actual, content=None, *, refused=False, provider_id=None):
        return await journal_write(
            engine,
            journal_lock,
            budget.settle,
            manifest_sha256=payload["manifest_sha256"],
            reservation=reservation,
            actual_micros=actual,
            content=content,
            refused=refused,
            provider_response_id=provider_id,
        )

    try:
        result = await asyncio.to_thread(
            complete_chat_detailed,
            TASK,
            client,
            messages=messages,
            max_output_tokens=OUTPUT_TOKENS,
            temperature=0.1,
            max_retries=0,
            today=today,
            response_format={"type": "json_object"},
        )
    except LLMCallRefused as error:
        # The standard request ledger refused before send.
        await settle(0, refused=True)
        if isinstance(error, LLMBudgetExceeded):
            raise budget.CoverageBudgetStopped(
                "shared daily budget exhausted"
            ) from error
        raise PilotStopped(
            f"request refused for {market_id}: {type(error).__name__}"
        ) from error
    except BaseException:
        await settle(None)
        raise

    billed = None if result.cost_usd is None else ceil(result.cost_usd * 1_000_000)
    choices = result.response.choices
    content = (choices[0].message.content or "{}") if choices else "{}"
    totals = await settle(
        billed, content, provider_id=getattr(result.response, "id", None)
    )
    if result.model != model or totals["uncertain"]:
        raise PilotStopped(f"unreconciled spend at {market_id}")
    ledger = _get_ledger()
    if isinstance(ledger, CoverageLedger) and ledger.adjustment_failed.is_set():
        raise PilotStopped("shared spend ledger became unavailable during settlement")
    return content


async def build_profile(
    engine,
    row: dict,
    content: str,
    probabilities: list[float],
    model: str,
    source: dict,
    event_facts: dict,
) -> dict:
    raw = writer._json_from_llm_response(content)
    slot_drops: dict[str, str] = {}
    frame, drop = writer.sanitize_cu_frame(
        raw.get("frame"), title=row["name"] or "", slot_drops=slot_drops
    )
    mentions = writer.clean_entity_mentions(raw.get("entities"))
    async with get_task_session(engine=engine) as db, db.begin():
        await db.execute(text("SET TRANSACTION READ ONLY"))
        resolved = await writer._resolve_entity_refs(
            db,
            [mention["name"] for mention in mentions],
            mention_types={mention["name"]: mention["type"] for mention in mentions},
        )
    subjects, subject_ref, subject_id, subject_resolved = writer.ground_subjects(
        mentions, resolved
    )
    return {
        "schema_version": writer.CU_V2_SCHEMA_VERSION,
        "writer_rev": writer.CU_WRITER_REV,
        "model": model,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "topic": raw.get("topic"),
        "subtopic": raw.get("subtopic"),
        "entities": raw.get("entities", []),
        "geography": writer.cu_model_geography(
            raw.get("geography"), **fixture_leagues(row)
        ),
        "story_key": raw.get("story_key"),
        "series_key": writer._cu_series_key(raw.get("series_key")),
        "temporal_class": raw.get("temporal"),
        "event_date": writer.cu_unlinked_event_date(
            raw.get("event_date"), row["resolution_date"]
        ),
        "recurrence": raw.get("recurrence"),
        "stakes": raw.get("stakes"),
        "breadth": raw.get("breadth"),
        "oddity": raw.get("oddity"),
        "arc": raw.get("arc"),
        "hook_facts": raw.get("hook_facts", []),
        "junk_flags": writer.cu_junk_flags(
            source["option_names"], raw.get("junk_flags")
        ),
        "confidence": raw.get("confidence"),
        "liveness": writer._compute_liveness(probabilities, row["status"]),
        "frame": frame,
        "frame_drop_reason": drop,
        "frame_slot_drops": slot_drops,
        "subjects": subjects,
        "subject_ref": subject_ref,
        "subject_entity_id": subject_id,
        "subject_resolved": subject_resolved,
    } | event_facts


def sample_rank(seed: str, market_id: int) -> str:
    return sha256(f"{seed}:{market_id}".encode()).hexdigest()


async def process_market(
    engine, client, payload, market_id: int, journal_lock, examples: list
) -> str:
    row, before_image, attempt = await read_market(engine, market_id)
    if row is None or row["status"] != "open":
        return "market_left_cohort"
    if before_image is not None:
        if store.profile_hash(row["profile_json"]) != before_image["written_sha256"]:
            return "later_writer"
        return "already_written"
    prompt, probabilities, source, event_facts = market_prompt(row)
    content = await request_profile(
        engine, client, payload, market_id, prompt, attempt, journal_lock
    )
    profile = await build_profile(
        engine, row, content, probabilities, payload["model"], source, event_facts
    )
    cutoff = payload["sample_cutoff"]
    sample_candidate = market_id not in payload["excluded_sample_ids"] and (
        cutoff is None or sample_rank(payload["sample_seed"], market_id) <= cutoff
    )
    async with get_task_session(engine=engine) as db:
        result = await store.write_profile(
            db,
            market_id,
            expected_source=row["source"],
            expected_title=row["name"],
            expected_profile_json=row["profile_json"],
            profile=profile,
            pilot_source=source if sample_candidate else None,
        )
    if result == "written" and len(examples) < 3:
        examples.append(
            {
                "id": market_id,
                "title": str(row["name"] or "")[:220],
                "topic": str(profile.get("topic") or "")[:80],
                "subtopic": str(profile.get("subtopic") or "")[:80],
                "date": profile.get("event_date"),
            }
        )
    return result


async def run_chunk(payload: dict, engine, client) -> dict[str, Any]:
    manifest = payload["manifest_sha256"]
    if payload.get("recover_failed_ids"):
        async with get_task_session(engine=engine) as db:
            await budget.recover_stopped_attempts(
                db,
                manifest_sha256=manifest,
                market_ids=payload["recover_failed_ids"],
            )
    async with get_task_session(engine=engine) as db:
        await budget.initialize(
            db,
            manifest_sha256=manifest,
            model=payload["model"],
            pilot_sha256=payload["pilot_sha256"],
        )
    counts: Counter[str] = Counter()
    completed = []
    failures = []
    examples = []
    ids = payload["roster_ids"]
    first, end = payload["start"], payload["end"]
    block_start = first // BLOCK_SIZE * BLOCK_SIZE
    next_index = first
    pause = None
    journal_lock = asyncio.Lock()
    deadline = monotonic() + 1_800
    for start in range(first, end, budget.MAX_IN_FLIGHT):
        if monotonic() >= deadline:
            pause = "worker chunk time limit"
            break
        batch = ids[
            start - block_start : min(end, start + budget.MAX_IN_FLIGHT) - block_start
        ]
        results = await asyncio.gather(
            *(
                process_market(engine, client, payload, mid, journal_lock, examples)
                for mid in batch
            ),
            return_exceptions=True,
        )
        paused_batch = False
        for mid, result in zip(batch, results, strict=True):
            if isinstance(result, budget.CoverageBudgetStopped) and str(result) in {
                "coverage daily budget exhausted",
                "shared daily budget exhausted",
                "coverage run budget exhausted",
            }:
                pause = str(result)
                paused_batch = True
                continue
            if isinstance(result, BaseException):
                failure = {"id": mid, "error": type(result).__name__}
                if isinstance(result, (PilotStopped, budget.CoverageBudgetStopped)):
                    failure["reason"] = str(result)
                if isinstance(result, DBAPIError):
                    failure["sqlstate"] = getattr(result.orig, "sqlstate", None)
                failures.append(failure)
            else:
                counts[result] += 1
                completed.append([mid, result])
        if failures or paused_batch:
            break
        next_index = start + len(batch)
        if start == first or next_index % 100 == 0:
            print(
                "COVERAGE_PROGRESS",
                json.dumps({"cursor": next_index, "counts": dict(counts)}),
                flush=True,
            )

    async with get_task_session(engine=engine) as db:
        snapshot = await budget._load(db, budget.BUDGET_ID)
        if snapshot is None:
            raise PilotStopped("coverage spend ledger missing at stop")
        totals = snapshot.payload
    spent = totals["spent_micros"] / 1_000_000
    held = totals["held_micros"] / 1_000_000
    return {
        "next_index": next_index,
        "completed": completed,
        "pause": pause,
        "counts": dict(counts),
        "failures": failures,
        "actual_usd": spent,
        "held_usd": held,
        "retained_usd": totals.get("retained_micros", 0) / 1_000_000,
        "reserved_unreconciled_usd": held - spent,
        "in_flight": totals["in_flight"],
        "uncertain": totals["uncertain"],
        "per_utc_day_micros": totals["days"],
        "manifest_sha256": manifest,
        "pilot_sha256": payload["pilot_sha256"],
        "changed_timestamps": 0,
        "changed_story_keys": 0,
        "examples": examples,
    }


def emit(kind: str, data: dict) -> None:
    print("CU1809_" + kind, json.dumps(data, ensure_ascii=True), flush=True)


async def main(payload: dict) -> None:
    if not os.getenv("DYNO", "").startswith("run.") or os.getenv("HEAVY_APP") != "1":
        raise PilotStopped("coverage writes need a heavy worker one-off")
    validate_payload(payload)
    set_ledger(CoverageLedger())
    preflight(payload)
    client = _get_client()
    if client is None:
        raise PilotStopped("the worker has no configured completion client")
    engine = _get_task_engine(statement_timeout_ms=5_000, lock_timeout_ms=250)
    started = monotonic()
    try:
        async with engine.connect() as connection, AsyncSession(
            bind=connection
        ) as session:
            if not await try_acquire_overlap_lock(session, store.RUN_ID):
                raise PilotStopped("another coverage chunk owns the run lock")
            try:
                await session.commit()
                emit(
                    "WRITER_START",
                    {
                        "commit": os.getenv("GIT_COMMIT")
                        or os.getenv("HEROKU_SLUG_COMMIT"),
                        "start": payload["start"],
                        "end": payload["end"],
                        "manifest_sha256": ROSTER_SHA256,
                        "model": MODEL,
                    },
                )
                result = await run_chunk(payload, engine, client)
            finally:
                await release_overlap_lock(session, store.RUN_ID)
        completed = result.pop("completed")
        for index in range(0, len(completed), 100):
            emit(
                "WRITER_ROWS", {"start": index, "rows": completed[index : index + 100]}
            )
        emit(
            "WRITER_STOP",
            result
            | {
                "active_seconds": round(monotonic() - started, 2),
                "rows_reported": len(completed),
            },
        )
        if result["failures"] or result["uncertain"] or result["in_flight"]:
            raise SystemExit(1)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    try:
        raw = gzip.decompress(
            base64.b64decode(os.environ.pop("CU1809_CHUNK"), validate=True)
        )
        asyncio.run(main(json.loads(raw)))
    except PilotStopped as error:
        print("CU1809_WRITER_REASON", str(error), flush=True)
        raise SystemExit(1) from None
    except Exception as error:
        print("CU1809_WRITER_ABORT", type(error).__name__, flush=True)
        raise SystemExit(1) from None
