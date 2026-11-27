"""Server logic for the daily /guess challenge and group boards (#12619, 443: A).

Freezes once per Pacific Time calendar day from live site-formatted futures
details (`get_futures_market(..., representation="verified_title")`), never
fabricated numbers, with zero LLM calls. Groups are isolated by random URL
group codes with strict privacy-only persistence:
`(day_pt, group_code, nickname, answers, step_times)`, swept after 30 days.
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

from fastapi import HTTPException
from sqlalchemy import delete, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import GuessDailyEdition, GuessGroupEntry
from app.utils.kalshi_retention import PROVABLY_PURGED_AGE_DAYS
from app.utils.market_staleness import is_title_implied_stale

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
CHANCE_MID_GAP = 5
EARNED_MISS = 20
LONGEST_LINE = 110

RETENTION_DAYS = 30
MAX_GROUP_ENTRIES = 30
GROUP_CODE_RE = re.compile(r"^[a-z0-9]{8,24}$")

_TAP_KINDS = frozenset({"side", "versus", "four", "leader"})
_RESERVED_NICKNAMES = frozenset({"the coin", "together"})
_LEGACY_EDITION_CODES = frozenset({"c1", "d1"})
_NON_PLAYABLE_OUTCOME_STATUSES = frozenset({"settled", "closed", "voided", "cancelled"})
_EXTREME_RENDERED_PERCENTS = frozenset({"<1%", ">99%"})
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
    """Short [a-z0-9]{4,6} daily edition code, strictly disjoint from c1/d1."""
    offset = (day_pt - date(2026, 1, 1)).days
    if offset >= 0:
        code = f"p{_to_base36(offset).rjust(3, '0')}"
    else:
        code = f"q{_to_base36(-offset).rjust(3, '0')}"
    if code in _LEGACY_EDITION_CODES or len(code) < 4:
        raise AssertionError(f"Invalid edition code generated: {code!r}")
    return code


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
# Resolving live site-printed market details into a frozen daily pack
# ---------------------------------------------------------------------------


async def load_site_market_details(
    db: AsyncSession, market_ids: Sequence[int]
) -> dict[int, dict[str, Any]]:
    """Fetch each referenced market via the site's verified-title detail reader."""
    from app.routes.futures import REPRESENTATION_VERIFIED_TITLE, get_futures_market

    details: dict[int, dict[str, Any]] = {}
    for mid in sorted({int(m) for m in market_ids}):
        try:
            detail = await get_futures_market(
                market_id=mid, db=db, representation=REPRESENTATION_VERIFIED_TITLE
            )
        except HTTPException as exc:
            if exc.status_code == 404:
                continue
            raise
        if isinstance(detail, dict):
            details[mid] = detail
    return details


def _parse_utc_datetime(raw: Any) -> Optional[datetime]:
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw if raw.tzinfo is not None else raw.replace(tzinfo=timezone.utc)
    if isinstance(raw, str):
        text_val = raw.strip()
        if not text_val:
            return None
        try:
            parsed = datetime.fromisoformat(text_val.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)
    return None


def _norm_outcome_name(name: Any) -> str:
    if not isinstance(name, str):
        return ""
    return re.sub(r"\s+", " ", name.replace("’", "'").replace("‘", "'")).strip().casefold()


def _detail_is_open(detail: Mapping[str, Any], reference_time: datetime) -> bool:
    if detail.get("status") != "open":
        return False
    for key in ("end_date", "resolution_date"):
        dt = _parse_utc_datetime(detail.get(key))
        if dt is not None and dt <= reference_time:
            return False
    sport_cat = detail.get("sport_category") or detail.get("llm_sport_category")
    if is_title_implied_stale(detail.get("name"), sport_cat, reference_time) is not None:
        return False
    return True


def _read_outcome_percent(
    market_details: Mapping[int, Mapping[str, Any]],
    market_id: int,
    outcome_name: str,
    reference_time: datetime,
) -> Optional[tuple[int, float, int, str]]:
    """Return `(pct_1_99, raw_prob, outcome_id, representation)` from site detail."""
    detail = market_details.get(int(market_id))
    if not isinstance(detail, Mapping) or not _detail_is_open(detail, reference_time):
        return None

    target_norm = _norm_outcome_name(outcome_name)
    if not target_norm:
        return None

    purged_cutoff = reference_time - timedelta(days=PROVABLY_PURGED_AGE_DAYS)
    for outcome in detail.get("outcomes") or ():
        if not isinstance(outcome, Mapping):
            continue
        if _norm_outcome_name(outcome.get("name")) != target_norm:
            continue
        if outcome.get("is_winner") is True or outcome.get("is_out") is True:
            return None
        if outcome.get("status") in _NON_PLAYABLE_OUTCOME_STATUSES:
            return None
        if outcome.get("kalshi_no_bid"):
            return None
        if outcome.get("rendered_percent") in _EXTREME_RENDERED_PERCENTS:
            return None
        source_mark = outcome.get("source_mark")
        if isinstance(source_mark, Mapping) and source_mark.get("state") in {
            "unsupported",
            "settled",
        }:
            return None
        last_updated = _parse_utc_datetime(outcome.get("last_updated"))
        if last_updated is not None and last_updated < purged_cutoff:
            return None

        raw_p = outcome.get("probability")
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
        rep = str(detail.get("representation") or "source")
        return pct, prob, int(outcome.get("id") or 0), rep
    return None


def _build_four_options(
    answer: int, seed_str: str, answer_slot: Optional[int] = None
) -> Optional[list[int]]:
    """Build 4 ascending percentages in [1..99] with >= OPTION_GAP separation."""
    if not (1 <= answer <= 99):
        return None

    def _fits_slot(slot: int) -> bool:
        return answer - slot * OPTION_GAP >= 1 and answer + (3 - slot) * OPTION_GAP <= 99

    if answer_slot is not None:
        if (
            isinstance(answer_slot, bool)
            or not isinstance(answer_slot, int)
            or not (0 <= answer_slot <= 3)
            or not _fits_slot(answer_slot)
        ):
            return None
        slot = answer_slot
    else:
        valid_slots = [s for s in range(4) if _fits_slot(s)]
        if not valid_slots:
            return None
        rng_pick = _seeded_rng(f"four-slot:{seed_str}:{answer}")
        slot = valid_slots[int(rng_pick() * len(valid_slots)) % len(valid_slots)]

    rng = _seeded_rng(f"four:{seed_str}:{answer}:{slot}")
    opts = [0, 0, 0, 0]
    opts[slot] = answer
    for i in range(slot - 1, -1, -1):
        max_here = opts[i + 1] - OPTION_GAP
        min_here = 1 + i * OPTION_GAP
        span = max(0, max_here - min_here)
        step_down = min(span, 2 + int(rng() * 10))
        opts[i] = max(min_here, max_here - step_down)
    for i in range(slot + 1, 4):
        min_here = opts[i - 1] + OPTION_GAP
        max_here = 99 - (3 - i) * OPTION_GAP
        span = max(0, max_here - min_here)
        step_up = min(span, 2 + int(rng() * 10))
        opts[i] = min(max_here, min_here + step_up)
    if (
        len(set(opts)) != 4
        or opts.count(answer) != 1
        or any(not (1 <= x <= 99) for x in opts)
        or any(b - a < OPTION_GAP for a, b in zip(opts, opts[1:]))
    ):
        return None
    return opts


def _base_card_dict(template: Mapping[str, Any]) -> dict[str, Any]:
    card: dict[str, Any] = {
        "id": str(template["id"]),
        "kind": str(template["kind"]),
        "flavor": "straight" if template["kind"] == "chance" else str(template["kind"]),
        "ours": str(template["kind"]) == "versus",
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
    market_details: Mapping[int, Mapping[str, Any]],
    reference_time: datetime,
    *,
    day_seed: str,
    answer_slot_override: Optional[int] = None,
) -> Optional[tuple[dict[str, Any], list[dict[str, Any]]]]:
    """Resolve one scheduled card template against live site-printed market details."""
    kind = str(template["kind"])
    card = _base_card_dict(template)
    provenance: list[dict[str, Any]] = []

    if kind == "side":
        extras = list(template.get("extras") or [])
        if len(extras) != 2:
            return None
        src = template["source"]
        resolved = _read_outcome_percent(
            market_details, int(src["market_id"]), str(src["outcome_name"]), reference_time
        )
        if resolved is None:
            return None
        pct, raw_prob, outcome_id, rep = resolved
        if abs(pct - 50) < SIDE_GAP:
            return None
        card["extras"] = [str(e) for e in extras]
        card["answer"] = pct
        provenance.append(
            {
                "card_id": card["id"],
                "market_id": int(src["market_id"]),
                "outcome_id": outcome_id,
                "outcome_name": str(src["outcome_name"]),
                "probability": raw_prob,
                "percent": pct,
                "representation": rep,
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
                market_details, int(opt["market_id"]), str(opt["outcome_name"]), reference_time
            )
            if resolved is None:
                return None
            pct, raw_prob, outcome_id, rep = resolved
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
                    "representation": rep,
                }
            )
        if abs(built_opts[0]["percent"] - built_opts[1]["percent"]) < VERSUS_GAP:
            return None
        card["options"] = built_opts
        return card, provenance

    if kind == "four":
        extras = list(template.get("extras") or [])
        if len(extras) != 2:
            return None
        src = template["source"]
        resolved = _read_outcome_percent(
            market_details, int(src["market_id"]), str(src["outcome_name"]), reference_time
        )
        if resolved is None:
            return None
        pct, raw_prob, outcome_id, rep = resolved
        slot = answer_slot_override if answer_slot_override is not None else template.get("answer_slot")
        four_opts = _build_four_options(pct, f"{day_seed}:{card['id']}", answer_slot=slot)
        if four_opts is None:
            return None
        card["extras"] = [str(e) for e in extras]
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
                "representation": rep,
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
                market_details, market_id, str(opt["outcome_name"]), reference_time
            )
            if resolved is None:
                return None
            pct, raw_prob, outcome_id, rep = resolved
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
                    "representation": rep,
                }
            )
        if len({o["label"] for o in built_opts}) != 4:
            return None
        independent = bool(template.get("independent", False))
        if not independent and sum(o["percent"] for o in built_opts) > 100:
            return None
        top_two = sorted((o["percent"] for o in built_opts), reverse=True)[:2]
        if top_two[0] - top_two[1] < LEAD_GAP:
            return None
        card["independent"] = independent
        card["options"] = built_opts
        return card, provenance

    if kind == "chance":
        extras = list(template.get("extras") or [])
        if len(extras) != 2:
            return None
        src = template["source"]
        resolved = _read_outcome_percent(
            market_details, int(src["market_id"]), str(src["outcome_name"]), reference_time
        )
        if resolved is None:
            return None
        pct, raw_prob, outcome_id, rep = resolved
        if abs(pct - 50) < CHANCE_MID_GAP:
            return None
        want_high = pct + EARNED_MISS <= 100
        want_low = pct - EARNED_MISS >= 0
        raw_high = str(template.get("roastHigh") or "").strip()
        raw_low = str(template.get("roastLow") or "").strip()
        if want_high and (not raw_high or len(raw_high) > LONGEST_LINE):
            return None
        if want_low and (not raw_low or len(raw_low) > LONGEST_LINE):
            return None
        card["extras"] = [str(e) for e in extras]
        card["answer"] = pct
        if want_high:
            card["roastHigh"] = raw_high
        if want_low:
            card["roastLow"] = raw_low
        provenance.append(
            {
                "card_id": card["id"],
                "market_id": int(src["market_id"]),
                "outcome_id": outcome_id,
                "outcome_name": str(src["outcome_name"]),
                "probability": raw_prob,
                "percent": pct,
                "representation": rep,
            }
        )
        return card, provenance

    return None


def _draw_coin_taps(cards: Sequence[Mapping[str, Any]], seed_str: str) -> list[Optional[int]]:
    """Draw fair ordinary coin flips (2-3/5 Easy, exact 1/5 Medium, None Hard)."""
    rng = _seeded_rng(f"coin:{seed_str}")
    # Step 0: indices 0..4 (2-way taps)
    for _ in range(128):
        easy = [1 if rng() >= 0.5 else 0 for _ in range(5)]
        right = sum(1 for i in range(5) if easy[i] == full_guess(cards[i]))
        if right in (2, 3) and 0 < sum(easy) < 5:
            break
    else:
        easy = [
            full_guess(cards[0]),
            full_guess(cards[1]),
            1 - full_guess(cards[2]),
            1 - full_guess(cards[3]),
            1 - full_guess(cards[4]),
        ]

    # Step 1: indices 5..9 (4-way taps) -> ordinary coin gets 1 of 5 right.
    for _ in range(256):
        med = [int(rng() * 4) % 4 for _ in range(5)]
        right = sum(1 for i in range(5, 10) if med[i - 5] == full_guess(cards[i]))
        if right == 1:
            break
    else:
        med = [
            full_guess(cards[5]),
            *((full_guess(cards[i]) + 1) % 4 for i in range(6, 10)),
        ]

    return [*easy, *med, None, None, None, None, None]


def _resolve_with_step_fit(
    template: Mapping[str, Any],
    market_details: Mapping[int, Mapping[str, Any]],
    frozen_at: datetime,
    *,
    day_seed: str,
    step_key: str,
    kept_in_step: Sequence[Mapping[str, Any]],
    prev_global_card: Optional[Mapping[str, Any]],
) -> Optional[tuple[dict[str, Any], list[dict[str, Any]]]]:
    kind = str(template.get("kind") or "")
    if step_key == "easy" and kind not in {"side", "versus"}:
        return None
    if step_key == "medium" and kind not in {"four", "leader"}:
        return None
    if step_key == "hard" and kind != "chance":
        return None
    if kind == "versus" and prev_global_card is not None and prev_global_card.get("ours"):
        return None

    used_versus = {full_guess(c) for c in kept_in_step if c["kind"] == "versus"}
    used_leader = {full_guess(c) for c in kept_in_step if c["kind"] == "leader"}
    used_four = {full_guess(c) for c in kept_in_step if c["kind"] == "four"}

    if kind == "four" and template.get("answer_slot") is None:
        # Spare `four` cards pick a valid slot not yet used in this step when available.
        for candidate_slot in range(4):
            if candidate_slot in used_four:
                continue
            outcome = resolve_card_from_markets(
                template,
                market_details,
                frozen_at,
                day_seed=day_seed,
                answer_slot_override=candidate_slot,
            )
            if outcome is not None:
                return outcome
        return None

    outcome = resolve_card_from_markets(
        template, market_details, frozen_at, day_seed=day_seed
    )
    if outcome is None:
        return None
    card, prov = outcome
    ans = full_guess(card)
    if kind == "versus" and ans in used_versus:
        return None
    if kind == "leader" and ans in used_leader:
        return None
    if kind == "four" and ans in used_four:
        return None
    return card, prov


def _validate_pack_invariants(pack: Mapping[str, Any], day_str: str) -> None:
    cards = list(pack.get("cards") or [])
    topics = list(pack.get("topics") or [])
    if len(cards) != 15 or len(topics) != 3:
        raise GuessEditionUnavailableError(f"Pack {day_str} must have 15 cards and 3 topics.")
    for topic in topics:
        if sum(1 for c in cards if c.get("topic") == topic) < 3:
            raise GuessEditionUnavailableError(f"Pack {day_str} topic '{topic}' fell below 3 cards.")
    ours_count = sum(1 for c in cards if c.get("ours"))
    if ours_count < 1 or ours_count > 7:
        raise GuessEditionUnavailableError(f"Pack {day_str} has invalid ours count {ours_count}.")
    for a, b in zip(cards, cards[1:]):
        if a.get("ours") and b.get("ours"):
            raise GuessEditionUnavailableError(f"Pack {day_str} places two ours cards in a row.")

    sides = [c for c in cards[:5] if c.get("kind") == "side"]
    if len(sides) < 2 or len({full_guess(c) for c in sides}) != 2:
        raise GuessEditionUnavailableError(f"Pack {day_str} Easy step must have both <50 and >50 sides.")


def build_daily_pack(
    day_pt: date,
    schedule_day: Mapping[str, Any],
    market_details: Mapping[int, Mapping[str, Any]],
    frozen_at: datetime,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Resolve 15 live cards (5 per step), swapping spares for closed/unplayable primaries."""
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
        consumed_spares: set[int] = set()
        kept_in_step: list[dict[str, Any]] = []
        used_ids: set[str] = {c["id"] for c in resolved_cards}

        for primary_idx, tmpl in enumerate(primaries):
            prev_card = kept_in_step[-1] if kept_in_step else (resolved_cards[-1] if resolved_cards else None)
            outcome = _resolve_with_step_fit(
                tmpl,
                market_details,
                frozen_at,
                day_seed=day_str,
                step_key=step_key,
                kept_in_step=kept_in_step,
                prev_global_card=prev_card,
            )
            if outcome is not None:
                card, prov = outcome
                kept_in_step.append(card)
                provenance.extend(prov)
                used_ids.add(card["id"])
                continue

            swapped = False
            for s_idx, candidate in enumerate(spare_pool):
                if s_idx in consumed_spares:
                    continue
                spare_outcome = _resolve_with_step_fit(
                    candidate,
                    market_details,
                    frozen_at,
                    day_seed=day_str,
                    step_key=step_key,
                    kept_in_step=kept_in_step,
                    prev_global_card=prev_card,
                )
                if spare_outcome is None:
                    continue
                consumed_spares.add(s_idx)
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
    _validate_pack_invariants(pack, day_str)
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
    market_details: Optional[Mapping[int, Mapping[str, Any]]] = None,
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
    resolved_details = (
        market_details
        if market_details is not None
        else await load_site_market_details(db, market_ids)
    )

    pack, provenance = build_daily_pack(day, day_entry, resolved_details, now)
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
