"""Server logic for the daily /guess challenge and group boards (#12619, 443: A).

Freezes once per Pacific Time calendar day from real open FuturesMarket +
FuturesOutcome rows (never fabricated numbers, no LLM calls). Groups are
isolated by random URL group codes with strict privacy-only persistence:
(day_pt, group_code, nickname, answers, step_times), swept after 30 days.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence
from zoneinfo import ZoneInfo

from sqlalchemy import delete, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.models import FuturesMarket, GuessDailyEdition, GuessGroupEntry

PT_TZ = ZoneInfo("America/Los_Angeles")
SCHEDULE_PATH = Path(__file__).resolve().parents[2] / "data" / "guess" / "daily_schedule.json"

FULL_POINTS = 20
TWO_WAY_POINTS = 10
FOUR_WAY_POINTS = 15
DUO_BASE = 101
MAX_CARD_SECONDS = 120

SIDE_GAP = 8
VERSUS_GAP = 8
LEAD_GAP = 5
OPTION_GAP = 10

RETENTION_DAYS = 30
MAX_GROUP_ENTRIES = 30
GROUP_CODE_RE = re.compile(r"^[a-z0-9]{8,24}$")

_TAP_KINDS = frozenset({"side", "versus", "four", "leader"})
_RESERVED_NICKNAMES = frozenset({"the coin", "together"})
_EDITION_LOCK_NS = 0x47554553  # 'GUES'
_GROUP_LOCK_NS = 0x47525053  # 'GRPS'
_BASE36_ALPHABET = "0123456789abcdefghijklmnopqrstuvwxyz"


class GuessError(Exception):
    """Base domain error for daily /guess."""


class GuessEditionNotFoundError(GuessError):
    """Requested PT day is outside the active window or has no stored edition."""


class GuessEditionUnavailableError(GuessError):
    """Daily schedule cannot produce 15 playable live cards without fabricating."""


class GuessInvalidGroupCodeError(GuessError):
    """Group code fails format requirements."""


class GuessInvalidSubmissionError(GuessError):
    """Submission fails nickname, answers, or step_times validation."""


class GuessGroupFullError(GuessError):
    """Group already holds the daily per-group ceiling of finished entries."""


class GuessNicknameConflictError(GuessError):
    """Nickname is already taken in this (day, group) with different answers."""


def today_pt(now_utc: Optional[datetime] = None) -> date:
    """Return current Pacific Time calendar date."""
    now = now_utc or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return now.astimezone(PT_TZ).date()


def _to_base36(value: int) -> str:
    if value < 0:
        raise ValueError("negative value")
    if value == 0:
        return "0"
    digits: list[str] = []
    n = value
    while n:
        n, rem = divmod(n, 36)
        digits.append(_BASE36_ALPHABET[rem])
    return "".join(reversed(digits))


def edition_code_for_day(day_pt: date) -> str:
    """Short [a-z0-9]{4,6} daily edition code, disjoint from 2-char legacy codes."""
    offset = (day_pt - date(2026, 1, 1)).days
    if offset >= 0:
        return f"p{_to_base36(offset).rjust(3, '0')}"
    return f"q{_to_base36(-offset).rjust(3, '0')}"


def format_as_of_pt(frozen_at: datetime) -> str:
    """Format timestamp in Pacific Time matching `guessPack.test.ts` (`... PT`)."""
    if frozen_at.tzinfo is None:
        frozen_at = frozen_at.replace(tzinfo=timezone.utc)
    local = frozen_at.astimezone(PT_TZ)
    hour_12 = local.hour % 12 or 12
    ampm = "AM" if local.hour < 12 else "PM"
    return local.strftime(f"%a %b {local.day}, {hour_12}:%M {ampm} PT")


def clean_nickname(raw: Any) -> str:
    """Mirror `cleanName` in `frontend/lib/guess/engine.ts`."""
    if not isinstance(raw, str):
        return ""
    # Replace control chars and collapse whitespace identically to JS `.replace(/\s+/g, " ").trim()`.
    stripped = re.sub(r"[\x00-\x1f\x7f]+", " ", raw)
    collapsed = re.sub(r"\s+", " ", stripped).strip()
    if not collapsed:
        return ""
    clipped = collapsed[:12].strip()
    if clipped.lower() in _RESERVED_NICKNAMES:
        return ""
    return clipped


def validate_group_code(group_code: str) -> str:
    """Validate and return canonical lowercase group code."""
    if not isinstance(group_code, str) or not GROUP_CODE_RE.fullmatch(group_code):
        raise GuessInvalidGroupCodeError(
            "Group code must be 8 to 24 lowercase letters or digits."
        )
    return group_code


def load_daily_schedule(path: Path = SCHEDULE_PATH) -> dict[str, Any]:
    """Load the repo-checked weekly schedule JSON."""
    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict) or not isinstance(data.get("days"), dict):
        raise GuessEditionUnavailableError("Invalid daily schedule structure.")
    return data


def _seeded_rng(seed_str: str):
    """Mulberry32-style seeded pseudo-random generator for reproducible draws."""
    digest = hashlib.sha256(seed_str.encode("utf-8")).digest()
    state = int.from_bytes(digest[:4], "big")

    def _next() -> float:
        nonlocal state
        state = (state + 0x6D2B79F5) & 0xFFFFFFFF
        t = state
        t = ((t ^ (t >> 15)) * (t | 1)) & 0xFFFFFFFF
        t = (t ^ ((t + (((t ^ (t >> 7)) * (t | 61)) & 0xFFFFFFFF)) & 0xFFFFFFFF)) & 0xFFFFFFFF
        return ((t ^ (t >> 14)) & 0xFFFFFFFF) / 4294967296.0

    return _next


# ---------------------------------------------------------------------------
# Scoring — exact mirror of frontend/lib/guess/engine.ts
# ---------------------------------------------------------------------------


def is_tap(card: Mapping[str, Any]) -> bool:
    return card.get("kind") in _TAP_KINDS


def option_count(card: Mapping[str, Any]) -> int:
    if card.get("kind") == "side":
        return 2
    return len(card.get("options") or ())


def full_points(card: Mapping[str, Any]) -> int:
    if not is_tap(card):
        return FULL_POINTS
    return TWO_WAY_POINTS if option_count(card) <= 2 else FOUR_WAY_POINTS


def max_guess(card: Mapping[str, Any]) -> int:
    if is_tap(card):
        return option_count(card) - 1
    kind = card.get("kind")
    if kind == "chance":
        return 100
    if kind == "count":
        return int(card["max"])
    if kind == "duo":
        return 100 * DUO_BASE + 100
    raise ValueError(f"Unknown card kind: {kind!r}")


def is_valid_guess(card: Mapping[str, Any], guess: Any) -> bool:
    if isinstance(guess, bool) or not isinstance(guess, int):
        return False
    if guess < 0 or guess > max_guess(card):
        return False
    if card.get("kind") == "duo":
        return (guess // DUO_BASE) <= 100 and (guess % DUO_BASE) <= 100
    return True


def full_guess(card: Mapping[str, Any]) -> int:
    kind = card.get("kind")
    if kind == "side":
        return 1 if int(card["answer"]) > 50 else 0
    if kind in {"versus", "leader"}:
        options = card["options"]
        best = 0
        for idx, opt in enumerate(options):
            if int(opt["percent"]) > int(options[best]["percent"]):
                best = idx
        return best
    if kind == "four":
        return list(card["options"]).index(int(card["answer"]))
    if kind == "duo":
        parts = card["parts"]
        return int(parts[0]["answer"]) * DUO_BASE + int(parts[1]["answer"])
    return int(card["answer"])


def _slider_points(miss: int, step: int) -> int:
    return max(0, FULL_POINTS - step * miss)


def points_for(card: Mapping[str, Any], guess: Any) -> int:
    if not is_valid_guess(card, guess):
        return 0
    if is_tap(card):
        return full_points(card) if guess == full_guess(card) else 0
    kind = card.get("kind")
    if kind == "chance":
        return _slider_points(abs(guess - int(card["answer"])), 1)
    if kind == "count":
        return _slider_points(abs(guess - int(card["answer"])), int(card["step"]))
    if kind == "duo":
        a, b = divmod(guess, DUO_BASE)
        first = _slider_points(abs(a - int(card["parts"][0]["answer"])), 1)
        second = _slider_points(abs(b - int(card["parts"][1]["answer"])), 1)
        # Match JS Math.round((first + second) / 2) half-up behavior.
        return (first + second + 1) // 2
    return 0


def clean_step_times(pack: Mapping[str, Any], raw_times: Any) -> list[int]:
    """Validate and cap per-step decision seconds to MAX_CARD_SECONDS per card."""
    steps = pack.get("steps") or []
    per_round = int(pack.get("perRound") or 5)
    cap = per_round * MAX_CARD_SECONDS
    if not isinstance(raw_times, Sequence) or isinstance(raw_times, (str, bytes)):
        raise GuessInvalidSubmissionError("step_times must be a list of integers.")
    if len(raw_times) != len(steps):
        raise GuessInvalidSubmissionError(f"Expected {len(steps)} step_times.")
    cleaned: list[int] = []
    for val in raw_times:
        if isinstance(val, bool) or not isinstance(val, int) or val < 0:
            raise GuessInvalidSubmissionError("Each step time must be a non-negative integer.")
        cleaned.append(min(cap, val))
    return cleaned


def score_answers(
    pack: Mapping[str, Any],
    answers: Sequence[Any],
    step_times: Sequence[Any],
) -> dict[str, Any]:
    """Server-side validation and scoring of a completed game submission."""
    cards = pack.get("cards") or []
    steps = pack.get("steps") or []
    per_round = int(pack.get("perRound") or 5)
    if (
        not isinstance(answers, Sequence)
        or isinstance(answers, (str, bytes))
        or len(answers) != len(cards)
    ):
        raise GuessInvalidSubmissionError(f"Expected exactly {len(cards)} answers.")

    validated_answers: list[int] = []
    card_points: list[int] = []
    for idx, (card, guess) in enumerate(zip(cards, answers, strict=True)):
        if not is_valid_guess(card, guess):
            raise GuessInvalidSubmissionError(f"Invalid answer at card index {idx}.")
        validated_answers.append(guess)
        card_points.append(points_for(card, guess))

    validated_times = clean_step_times(pack, step_times)
    step_points = [
        sum(card_points[s * per_round : (s + 1) * per_round])
        for s in range(len(steps))
    ]
    return {
        "answers": validated_answers,
        "step_times": validated_times,
        "card_points": card_points,
        "step_points": step_points,
        "points": sum(step_points),
        "total_time_seconds": sum(validated_times),
    }


# ---------------------------------------------------------------------------
# Resolving live markets into a frozen daily pack
# ---------------------------------------------------------------------------


def _norm_outcome_name(name: Any) -> str:
    if not isinstance(name, str):
        return ""
    return re.sub(r"\s+", " ", name.replace("’", "'").replace("‘", "'")).strip().casefold()


def _market_is_open(market: FuturesMarket, reference_time: datetime) -> bool:
    if getattr(market, "status", None) != "open":
        return False
    end_dt = getattr(market, "end_date", None)
    if isinstance(end_dt, datetime):
        if end_dt.tzinfo is None:
            end_dt = end_dt.replace(tzinfo=timezone.utc)
        if end_dt <= reference_time:
            return False
    return True


def _read_outcome_percent(
    markets_by_id: Mapping[int, FuturesMarket],
    market_id: int,
    outcome_name: str,
    reference_time: datetime,
) -> Optional[tuple[int, float, int]]:
    """Return `(pct_1_99, raw_prob, outcome_id)` or None if closed/missing/unpriced."""
    market = markets_by_id.get(int(market_id))
    if market is None or not _market_is_open(market, reference_time):
        return None
    target_norm = _norm_outcome_name(outcome_name)
    if not target_norm:
        return None
    for outcome in getattr(market, "outcomes", None) or ():
        status = getattr(outcome, "status", None)
        if status in {"settled", "closed", "voided", "cancelled"}:
            continue
        if _norm_outcome_name(getattr(outcome, "name", None)) != target_norm:
            continue
        raw_p = getattr(outcome, "probability", None)
        if raw_p is None:
            raw_p = getattr(outcome, "current_probability", None)
        if (
            raw_p is None
            or isinstance(raw_p, bool)
            or not isinstance(raw_p, (int, float, Decimal))
            or not math.isfinite(float(raw_p))
        ):
            return None
        prob = float(raw_p)
        if not (0.0 < prob < 1.0):
            return None
        pct = int(math.floor(prob * 100.0 + 0.5))
        if not (1 <= pct <= 99):
            return None
        return pct, prob, int(getattr(outcome, "id", 0) or 0)
    return None


def _build_four_options(answer: int, seed_str: str) -> Optional[list[int]]:
    """Build 4 ascending percentages in [2..98] with >= OPTION_GAP separation."""
    if not (2 <= answer <= 98):
        return None
    rng = _seeded_rng(f"four:{seed_str}:{answer}")
    valid_slots = [
        slot
        for slot in range(4)
        if answer - slot * OPTION_GAP >= 2 and answer + (3 - slot) * OPTION_GAP <= 98
    ]
    if not valid_slots:
        return None
    slot = valid_slots[int(rng() * len(valid_slots)) % len(valid_slots)]
    opts = [0, 0, 0, 0]
    opts[slot] = answer
    for i in range(slot - 1, -1, -1):
        max_here = opts[i + 1] - OPTION_GAP
        min_here = 2 + i * OPTION_GAP
        span = max(0, max_here - min_here)
        step_down = min(span, 3 + int(rng() * 10))
        opts[i] = max(min_here, max_here - step_down)
    for i in range(slot + 1, 4):
        min_here = opts[i - 1] + OPTION_GAP
        max_here = 98 - (3 - i) * OPTION_GAP
        span = max(0, max_here - min_here)
        step_up = min(span, 3 + int(rng() * 10))
        opts[i] = min(max_here, min_here + step_up)
    if len(set(opts)) != 4 or any(b - a < OPTION_GAP for a, b in zip(opts, opts[1:])):
        return None
    return opts


def _base_card_dict(template: Mapping[str, Any]) -> dict[str, Any]:
    card: dict[str, Any] = {
        "id": str(template["id"]),
        "kind": str(template["kind"]),
        "flavor": str(template.get("flavor") or template["kind"]),
        "ours": bool(template.get("ours", False)),
        "topic": str(template["topic"]),
        "emoji": str(template["emoji"]),
        "prompt": str(template["prompt"]),
        "short": str(template["short"]),
        "context": str(template["context"]),
    }
    if template.get("sub"):
        card["sub"] = str(template["sub"])
    return card


def resolve_card_from_markets(
    template: Mapping[str, Any],
    markets_by_id: Mapping[int, FuturesMarket],
    reference_time: datetime,
    *,
    day_seed: str,
) -> Optional[tuple[dict[str, Any], list[dict[str, Any]]]]:
    """Resolve one scheduled card template against live DB markets, or None if unplayable."""
    kind = str(template["kind"])
    card = _base_card_dict(template)
    provenance: list[dict[str, Any]] = []

    if kind == "side":
        src = template["source"]
        resolved = _read_outcome_percent(
            markets_by_id, int(src["market_id"]), str(src["outcome_name"]), reference_time
        )
        if resolved is None:
            return None
        pct, raw_prob, outcome_id = resolved
        if abs(pct - 50) < SIDE_GAP:
            return None
        card["extras"] = list(template.get("extras") or [])
        card["answer"] = pct
        provenance.append(
            {
                "card_id": card["id"],
                "market_id": int(src["market_id"]),
                "outcome_id": outcome_id,
                "outcome_name": str(src["outcome_name"]),
                "probability": raw_prob,
                "percent": pct,
            }
        )
        return card, provenance

    if kind == "versus":
        raw_opts = template.get("options") or []
        if len(raw_opts) != 2:
            return None
        built_opts: list[dict[str, Any]] = []
        for opt in raw_opts:
            resolved = _read_outcome_percent(
                markets_by_id, int(opt["market_id"]), str(opt["outcome_name"]), reference_time
            )
            if resolved is None:
                return None
            pct, raw_prob, outcome_id = resolved
            built_opts.append(
                {
                    "label": str(opt["label"]),
                    "short": str(opt["short"]),
                    "emoji": str(opt["emoji"]),
                    "percent": pct,
                }
            )
            provenance.append(
                {
                    "card_id": card["id"],
                    "market_id": int(opt["market_id"]),
                    "outcome_id": outcome_id,
                    "outcome_name": str(opt["outcome_name"]),
                    "probability": raw_prob,
                    "percent": pct,
                }
            )
        if abs(built_opts[0]["percent"] - built_opts[1]["percent"]) < VERSUS_GAP:
            return None
        card["options"] = built_opts
        return card, provenance

    if kind == "four":
        src = template["source"]
        resolved = _read_outcome_percent(
            markets_by_id, int(src["market_id"]), str(src["outcome_name"]), reference_time
        )
        if resolved is None:
            return None
        pct, raw_prob, outcome_id = resolved
        four_opts = _build_four_options(pct, f"{day_seed}:{card['id']}")
        if four_opts is None:
            return None
        card["extras"] = list(template.get("extras") or [])
        card["answer"] = pct
        card["options"] = four_opts
        provenance.append(
            {
                "card_id": card["id"],
                "market_id": int(src["market_id"]),
                "outcome_id": outcome_id,
                "outcome_name": str(src["outcome_name"]),
                "probability": raw_prob,
                "percent": pct,
            }
        )
        return card, provenance

    if kind == "leader":
        market_id = int(template["market_id"])
        raw_opts = template.get("options") or []
        if len(raw_opts) != 4:
            return None
        built_opts = []
        for opt in raw_opts:
            resolved = _read_outcome_percent(
                markets_by_id, market_id, str(opt["outcome_name"]), reference_time
            )
            if resolved is None:
                return None
            pct, raw_prob, outcome_id = resolved
            built_opts.append(
                {
                    "label": str(opt["label"]),
                    "short": str(opt["short"]),
                    "emoji": str(opt["emoji"]),
                    "percent": pct,
                }
            )
            provenance.append(
                {
                    "card_id": card["id"],
                    "market_id": market_id,
                    "outcome_id": outcome_id,
                    "outcome_name": str(opt["outcome_name"]),
                    "probability": raw_prob,
                    "percent": pct,
                }
            )
        top_two = sorted((o["percent"] for o in built_opts), reverse=True)[:2]
        if top_two[0] - top_two[1] < LEAD_GAP:
            return None
        card["independent"] = bool(template.get("independent", False))
        card["options"] = built_opts
        return card, provenance

    if kind == "chance":
        src = template["source"]
        resolved = _read_outcome_percent(
            markets_by_id, int(src["market_id"]), str(src["outcome_name"]), reference_time
        )
        if resolved is None:
            return None
        pct, raw_prob, outcome_id = resolved
        card["extras"] = list(template.get("extras") or [])
        card["answer"] = pct
        # Keep only roast lines a guess in [0..100] can actually earn (miss >= 20).
        if pct <= 80 and template.get("roastHigh"):
            card["roastHigh"] = str(template["roastHigh"])
        if pct >= 20 and template.get("roastLow"):
            card["roastLow"] = str(template["roastLow"])
        if not card.get("roastHigh") and not card.get("roastLow"):
            return None
        provenance.append(
            {
                "card_id": card["id"],
                "market_id": int(src["market_id"]),
                "outcome_id": outcome_id,
                "outcome_name": str(src["outcome_name"]),
                "probability": raw_prob,
                "percent": pct,
            }
        )
        return card, provenance

    return None


def _draw_coin_taps(cards: Sequence[Mapping[str, Any]], seed_str: str) -> list[Optional[int]]:
    """Draw fair ordinary coin flips (2-3/5 Easy, 1-2/5 Medium, None Hard)."""
    rng = _seeded_rng(f"coin:{seed_str}")
    # Step 0: indices 0..4 (2-way taps)
    for _ in range(128):
        easy = [1 if rng() >= 0.5 else 0 for _ in range(5)]
        right = sum(1 for i in range(5) if easy[i] == full_guess(cards[i]))
        if right in (2, 3) and 0 < sum(easy) < 5:
            break
    else:
        easy = [full_guess(cards[0]), full_guess(cards[1]), 1 - full_guess(cards[2]), 1 - full_guess(cards[3]), full_guess(cards[4])]

    # Step 1: indices 5..9 (4-way taps)
    for _ in range(128):
        med = [int(rng() * 4) % 4 for _ in range(5)]
        right = sum(1 for i in range(5, 10) if med[i - 5] == full_guess(cards[i]))
        if right in (1, 2):
            break
    else:
        f5 = full_guess(cards[5])
        med = [f5, (f5 + 1) % 4, (full_guess(cards[7]) + 2) % 4, (full_guess(cards[8]) + 3) % 4, (full_guess(cards[9]) + 1) % 4]

    return [*easy, *med, None, None, None, None, None]


def build_daily_pack(
    day_pt: date,
    schedule_day: Mapping[str, Any],
    markets_by_id: Mapping[int, FuturesMarket],
    frozen_at: datetime,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Resolve 15 live cards (5 per step), swapping spares for closed/unpriced primaries."""
    steps = list(schedule_day.get("steps") or [])
    if len(steps) != 3:
        raise GuessEditionUnavailableError(f"Schedule for {day_pt} must define 3 steps.")
    step_cards = schedule_day.get("step_cards") or {}
    spares = schedule_day.get("spares") or {}

    resolved_cards: list[dict[str, Any]] = []
    provenance: list[dict[str, Any]] = []
    day_str = day_pt.isoformat()

    for step_idx, step_key in enumerate(("easy", "medium", "hard")):
        primaries = list(step_cards.get(step_key) or [])
        spare_pool = list(spares.get(step_key) or [])
        spare_cursor = 0
        kept_in_step: list[dict[str, Any]] = []
        used_ids: set[str] = {c["id"] for c in resolved_cards}

        for primary_idx, tmpl in enumerate(primaries):
            outcome = resolve_card_from_markets(
                tmpl, markets_by_id, frozen_at, day_seed=day_str
            )
            if outcome is not None:
                card, prov = outcome
                kept_in_step.append(card)
                provenance.extend(prov)
                used_ids.add(card["id"])
                continue

            # Primary closed, unpriced, or drifted too close to call: swap for step spare.
            swapped = False
            while spare_cursor < len(spare_pool):
                candidate = spare_pool[spare_cursor]
                spare_cursor += 1
                spare_outcome = resolve_card_from_markets(
                    candidate, markets_by_id, frozen_at, day_seed=day_str
                )
                if spare_outcome is None:
                    continue
                card, prov = spare_outcome
                if card["id"] in used_ids:
                    card["id"] = f"{card['id']}_{step_idx}_{primary_idx}"
                for p in prov:
                    p["swapped_from_slot"] = str(tmpl.get("id") or "")
                kept_in_step.append(card)
                provenance.extend(prov)
                used_ids.add(card["id"])
                swapped = True
                break

            if not swapped:
                raise GuessEditionUnavailableError(
                    f"Insufficient live playable cards for {day_str} step '{step_key}'."
                )

        if len(kept_in_step) != 5:
            raise GuessEditionUnavailableError(
                f"Expected 5 cards for {day_str} step '{step_key}', got {len(kept_in_step)}."
            )
        resolved_cards.extend(kept_in_step)

    code = edition_code_for_day(day_pt)
    pack: dict[str, Any] = {
        "id": day_str,
        "code": code,
        "asOf": format_as_of_pt(frozen_at),
        "perRound": 5,
        "steps": [
            {"name": str(s["name"]), "how": str(s["how"])} for s in steps
        ],
        "coinTaps": _draw_coin_taps(resolved_cards, day_str),
        "topics": list(schedule_day["topics"]),
        "cards": resolved_cards,
    }
    return pack, provenance


def _schedule_market_ids(schedule_day: Mapping[str, Any]) -> list[int]:
    ids: set[int] = set()
    for bucket_name in ("step_cards", "spares"):
        bucket = schedule_day.get(bucket_name) or {}
        for tmpls in bucket.values():
            for tmpl in tmpls or ():
                if "market_id" in tmpl:
                    ids.add(int(tmpl["market_id"]))
                src = tmpl.get("source")
                if isinstance(src, Mapping) and "market_id" in src:
                    ids.add(int(src["market_id"]))
                for opt in tmpl.get("options") or ():
                    if isinstance(opt, Mapping) and "market_id" in opt:
                        ids.add(int(opt["market_id"]))
    return sorted(ids)


async def _acquire_advisory_lock(db: AsyncSession, ns: int, key_int: int) -> None:
    try:
        bind = db.get_bind()
    except Exception:
        bind = None
    if bind is not None and bind.dialect.name != "postgresql":
        return
    try:
        await db.execute(
            text("SELECT pg_advisory_xact_lock(:ns, :key)"),
            {"ns": int(ns), "key": int(key_int)},
        )
    except Exception:
        # Non-Postgres test stubs may not implement pg_advisory_xact_lock.
        return


def group_lock_key(day_pt: date, group_code: str) -> int:
    digest = hashlib.sha256(f"{day_pt.isoformat()}:{group_code}".encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big") & 0x7FFFFFFF


async def get_or_freeze_daily_edition(
    db: AsyncSession,
    requested_day: Optional[date] = None,
    *,
    now_utc: Optional[datetime] = None,
    schedule: Optional[Mapping[str, Any]] = None,
) -> GuessDailyEdition:
    """Return the frozen edition for `requested_day`, freezing today on first read."""
    now = now_utc or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    today = today_pt(now)
    day = requested_day or today
    oldest_kept = today - timedelta(days=RETENTION_DAYS)
    if day > today or day < oldest_kept:
        raise GuessEditionNotFoundError(f"Edition day {day} is outside the active window.")

    existing = await db.scalar(
        select(GuessDailyEdition).where(GuessDailyEdition.day_pt == day)
    )
    if existing is not None:
        return existing

    if day != today:
        raise GuessEditionNotFoundError(f"No edition stored for {day}.")

    await _acquire_advisory_lock(
        db, _EDITION_LOCK_NS, int(day.strftime("%Y%m%d"))
    )
    existing = await db.scalar(
        select(GuessDailyEdition).where(GuessDailyEdition.day_pt == day)
    )
    if existing is not None:
        return existing

    sched = schedule or load_daily_schedule()
    day_entry = (sched.get("days") or {}).get(day.isoformat())
    if not isinstance(day_entry, Mapping):
        raise GuessEditionUnavailableError(
            f"No daily schedule configured for {day.isoformat()} PT."
        )

    market_ids = _schedule_market_ids(day_entry)
    markets_by_id: dict[int, FuturesMarket] = {}
    if market_ids:
        rows = (
            await db.scalars(
                select(FuturesMarket)
                .options(selectinload(FuturesMarket.outcomes))
                .where(FuturesMarket.id.in_(market_ids))
            )
        ).all()
        markets_by_id = {int(m.id): m for m in rows}

    pack, provenance = build_daily_pack(day, day_entry, markets_by_id, now)
    code = str(pack["code"])

    try:
        bind = db.get_bind()
    except Exception:
        bind = None
    dialect_name = bind.dialect.name if bind is not None else ""

    if dialect_name == "postgresql":
        stmt = (
            pg_insert(GuessDailyEdition)
            .values(
                day_pt=day,
                edition_code=code,
                frozen_at=now,
                pack_json=pack,
                source_snapshot=provenance,
            )
            .on_conflict_do_nothing(index_elements=["day_pt"])
        )
        await db.execute(stmt)
        await db.commit()
    else:
        try:
            async with db.begin_nested():
                db.add(
                    GuessDailyEdition(
                        day_pt=day,
                        edition_code=code,
                        frozen_at=now,
                        pack_json=pack,
                        source_snapshot=provenance,
                    )
                )
            await db.commit()
        except IntegrityError:
            await db.rollback()

    edition = await db.scalar(
        select(GuessDailyEdition).where(GuessDailyEdition.day_pt == day)
    )
    if edition is None:
        raise GuessEditionUnavailableError(f"Failed to freeze edition for {day}.")
    return edition


async def build_group_board_payload(
    db: AsyncSession,
    edition: GuessDailyEdition,
    group_code: str,
) -> dict[str, Any]:
    """Load one group's stored entries and score them server-side from answers."""
    rows = (
        await db.scalars(
            select(GuessGroupEntry)
            .where(
                GuessGroupEntry.day_pt == edition.day_pt,
                GuessGroupEntry.group_code == group_code,
            )
            .order_by(GuessGroupEntry.id.asc())
        )
    ).all()
    pack = edition.pack_json
    entries_out: list[dict[str, Any]] = []
    for row in rows:
        scored = score_answers(pack, row.answers, row.step_times)
        entries_out.append(
            {
                "nickname": row.nickname,
                "answers": scored["answers"],
                "step_times": scored["step_times"],
                "points": scored["points"],
                "step_points": scored["step_points"],
                "total_time_seconds": scored["total_time_seconds"],
            }
        )
    entries_out.sort(key=lambda e: (-e["points"], e["total_time_seconds"], e["nickname"].casefold()))
    return {
        "day": edition.day_pt.isoformat(),
        "edition_code": edition.edition_code,
        "group_code": group_code,
        "entries": entries_out,
    }


async def sweep_expired_guess_data(
    db: AsyncSession,
    *,
    today: Optional[date] = None,
) -> dict[str, int]:
    """Delete stored editions and group entries strictly older than 30 days PT."""
    cutoff = (today or today_pt()) - timedelta(days=RETENTION_DAYS)
    del_entries = await db.execute(
        delete(GuessGroupEntry).where(GuessGroupEntry.day_pt < cutoff)
    )
    del_editions = await db.execute(
        delete(GuessDailyEdition).where(GuessDailyEdition.day_pt < cutoff)
    )
    await db.commit()
    return {
        "cutoff_day_pt": cutoff.isoformat(),
        "deleted_entries": int(del_entries.rowcount or 0),
        "deleted_editions": int(del_editions.rowcount or 0),
    }
