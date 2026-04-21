"""
Oscars Pool game endpoints.

Private family/friend prediction pools for the Academy Awards.
Points are odds-adjusted: picking a longshot that wins = more points.
"""

import logging
import secrets
import unicodedata
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import OscarsPool, OscarsPoolMember, OscarsPoolPick
from app.services import get_db

logger = logging.getLogger(__name__)

router = APIRouter()

# ─── Fun bonus market templates ──────────────────────────────────────────────
# These are "house" bonus questions the pool includes automatically.
# They pull from real prediction market trivia when available, plus fun custom ones.
BONUS_MARKET_TEMPLATES = [
    {
        "key": "bonus_longest_speech",
        "question": "Which winner will give the longest acceptance speech?",
        "options": ["Best Picture producer", "Best Director", "Best Actor", "Best Actress", "Best Supporting Actor", "Best Supporting Actress"],
        "points_value": 3,
        "emoji": "🎤",
    },
    {
        "key": "bonus_first_tears",
        "question": "Who will cry first during their acceptance speech?",
        "options": ["Best Actor winner", "Best Actress winner", "Best Supporting Actress winner", "Best Supporting Actor winner", "Best Director winner", "Nobody cries"],
        "points_value": 3,
        "emoji": "😭",
    },
    {
        "key": "bonus_standing_ovation",
        "question": "Which winner will get the longest standing ovation?",
        "options": ["Best Picture", "Best Director", "Best Actor", "Best Actress", "In Memoriam segment", "Musical performance"],
        "points_value": 3,
        "emoji": "👏",
    },
    {
        "key": "bonus_play_off_music",
        "question": "How many winners will get played off by the orchestra?",
        "options": ["0", "1", "2", "3", "4 or more"],
        "points_value": 2,
        "emoji": "🎵",
    },
    {
        "key": "bonus_host_joke",
        "question": "What topic will the host's opening monologue joke about FIRST?",
        "options": ["A nominated film", "Politics", "Hollywood/industry", "Another celebrity in audience", "The host themselves", "Social media/AI"],
        "points_value": 2,
        "emoji": "😂",
    },
    {
        "key": "bonus_red_carpet_color",
        "question": "What will be the most common dress color on the red carpet?",
        "options": ["Black", "White/Ivory", "Red", "Blue/Navy", "Gold/Yellow", "Pink/Rose"],
        "points_value": 2,
        "emoji": "👗",
    },
    {
        "key": "bonus_ceremony_length",
        "question": "How long will the ceremony run? (scheduled 3h 30m)",
        "options": ["Under 3 hours", "3:00 - 3:29", "3:30 - 3:59 (on time-ish)", "4:00 - 4:29", "4:30 or longer"],
        "points_value": 2,
        "emoji": "⏱️",
    },
    {
        "key": "bonus_sweep",
        "question": "Will any film win 4 or more awards?",
        "options": ["Yes — and I think it'll be the Best Picture winner", "Yes — but NOT the Best Picture winner", "No film wins 4+"],
        "points_value": 4,
        "emoji": "🧹",
    },
    {
        "key": "bonus_political_speech",
        "question": "How many acceptance speeches will mention a political or social cause?",
        "options": ["0-2", "3-5", "6-8", "9 or more"],
        "points_value": 2,
        "emoji": "📢",
    },
    {
        "key": "bonus_viral_moment",
        "question": "What will be the night's biggest viral moment?",
        "options": ["Surprise upset winner", "Emotional speech", "Wardrobe moment", "Presenter flub/joke", "Political statement", "Unexpected duo presenting together"],
        "points_value": 3,
        "emoji": "📱",
    },
]

# Emoji avatar options for pool members
AVATAR_EMOJIS = ["🎬", "🍿", "⭐", "🎭", "🏆", "🎪", "🎯", "🎲", "👑", "🎸", "🌟", "🎩", "💎", "🦋", "🔮"]


# ─── Request/Response models ────────────────────────────────────────────────

class CreatePoolRequest(BaseModel):
    pool_name: str
    creator_name: str
    avatar_emoji: str = "🎬"


class JoinPoolRequest(BaseModel):
    display_name: str
    avatar_emoji: str = "🎬"


class PickItem(BaseModel):
    category_key: str
    nominee_name: str
    probability_at_pick: float


class SubmitPicksRequest(BaseModel):
    picks: list[PickItem]
    confidence_picks: list[str] = []  # Up to 3 category_keys


class RevealWinnerRequest(BaseModel):
    category_key: str
    winner_name: str


class BonusPickItem(BaseModel):
    bonus_key: str
    selected_option: str


class SubmitBonusPicksRequest(BaseModel):
    picks: list[BonusPickItem]


class RevealBonusRequest(BaseModel):
    bonus_key: str
    correct_option: str


# ─── Helper functions ────────────────────────────────────────────────────────

def _generate_pool_code() -> str:
    """Generate a short, human-friendly pool code."""
    # Use only uppercase + digits, no ambiguous chars (0/O, 1/I/L)
    alphabet = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(alphabet) for _ in range(6))


from app.utils.name_normalization import strip_diacritics as _strip_diacritics


def _match_name(a: str, b: str) -> bool:
    """Fuzzy name match for scoring (strips diacritics, case-insensitive)."""
    return _strip_diacritics(a).lower().strip() == _strip_diacritics(b).lower().strip()


def _compute_points(probability: float, is_confidence: bool, is_correct: bool) -> float:
    """
    Compute odds-adjusted points for a pick.

    Points = 1 / probability (capped at 20 for very long longshots).
    Confidence pick: 1.5x multiplier.
    Dark horse bonus (prob < 0.15): additional 2x multiplier.
    Wrong pick: 0 points.
    """
    if not is_correct:
        return 0.0

    prob = max(probability, 0.05)  # Floor at 5% to cap max points at 20
    base_points = round(1.0 / prob, 2)

    multiplier = 1.0
    if is_confidence:
        multiplier *= 1.5
    if probability < 0.15:
        multiplier *= 2.0  # Dark horse bonus

    return round(base_points * multiplier, 2)


def _compute_boldness(picks: list[dict]) -> float:
    """
    Compute a 'boldness' score (0-100) for a set of picks.
    Higher = more contrarian (picking more underdogs).
    """
    if not picks:
        return 0.0
    avg_prob = sum(p.get("probability_at_pick", 0.5) for p in picks) / len(picks)
    # Boldness = inverse of average probability picked
    # If you always pick favorites (avg_prob ~0.6), boldness ~40
    # If you always pick underdogs (avg_prob ~0.15), boldness ~85
    boldness = max(0, min(100, (1 - avg_prob) * 100))
    return round(boldness, 1)


# ─── Endpoints ───────────────────────────────────────────────────────────────

@router.post("/pool")
async def create_pool(
    request: CreatePoolRequest,
    db: AsyncSession = Depends(get_db),
):
    """Create a new Oscars pool and join as the first member."""
    code = _generate_pool_code()

    pool = OscarsPool(
        name=request.pool_name,
        code=code,
        created_by_name=request.creator_name,
        ceremony_year=2026,
        bonus_markets=BONUS_MARKET_TEMPLATES,
        results={},
    )
    db.add(pool)
    await db.flush()

    # Auto-join creator as first member
    member_token = secrets.token_urlsafe(32)
    member = OscarsPoolMember(
        pool_id=pool.id,
        display_name=request.creator_name,
        avatar_emoji=request.avatar_emoji,
        member_token=member_token,
    )
    db.add(member)
    await db.flush()

    return {
        "pool_code": code,
        "pool_name": pool.name,
        "member_token": member_token,
        "member_id": member.id,
        "display_name": member.display_name,
        "avatar_emoji": member.avatar_emoji,
        "avatar_options": AVATAR_EMOJIS,
    }


@router.post("/pool/{code}/join")
async def join_pool(
    code: str,
    request: JoinPoolRequest,
    db: AsyncSession = Depends(get_db),
):
    """Join an existing Oscars pool."""
    pool = await _get_pool(db, code)

    # Check for duplicate name
    existing = await db.execute(
        select(OscarsPoolMember).where(
            OscarsPoolMember.pool_id == pool.id,
            func.lower(OscarsPoolMember.display_name) == request.display_name.lower(),
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(400, "Someone with that name is already in the pool!")

    # Max 20 members per pool
    count_result = await db.execute(
        select(func.count()).where(OscarsPoolMember.pool_id == pool.id)
    )
    if count_result.scalar() >= 20:
        raise HTTPException(400, "Pool is full (max 20 members)")

    member_token = secrets.token_urlsafe(32)
    member = OscarsPoolMember(
        pool_id=pool.id,
        display_name=request.display_name,
        avatar_emoji=request.avatar_emoji,
        member_token=member_token,
    )
    db.add(member)
    await db.flush()

    return {
        "pool_code": code,
        "pool_name": pool.name,
        "member_token": member_token,
        "member_id": member.id,
        "display_name": member.display_name,
        "avatar_emoji": member.avatar_emoji,
    }


@router.get("/pool/{code}")
async def get_pool(
    code: str,
    db: AsyncSession = Depends(get_db),
    x_member_token: str | None = Header(None),
):
    """Get full pool state: members, picks (hidden until locked), leaderboard, results."""
    pool = await _get_pool(db, code, load_members=True)

    # Determine if the requester is a member
    current_member = None
    if x_member_token:
        for m in pool.members:
            if m.member_token == x_member_token:
                current_member = m
                break

    # Build member data with picks and scores
    members_data = []
    for member in sorted(pool.members, key=lambda m: m.joined_at):
        picks_data = []
        total_points = 0.0
        correct_count = 0
        bonus_picks_data = []

        for pick in member.picks:
            is_bonus = pick.category_key.startswith("bonus_")

            pick_info = {
                "category_key": pick.category_key,
                "nominee_name": pick.nominee_name,
                "probability_at_pick": float(pick.probability_at_pick) if pick.probability_at_pick else 0,
                "is_confidence_pick": pick.is_confidence_pick,
                "is_correct": pick.is_correct,
                "points_earned": float(pick.points_earned) if pick.points_earned is not None else None,
            }

            # Only show other people's picks after lock
            if member.id == (current_member.id if current_member else None) or pool.picks_locked:
                if is_bonus:
                    bonus_picks_data.append(pick_info)
                else:
                    picks_data.append(pick_info)
            # Always count points if scored
            if pick.points_earned is not None:
                total_points += float(pick.points_earned)
            if pick.is_correct:
                correct_count += 1

        members_data.append({
            "id": member.id,
            "display_name": member.display_name,
            "avatar_emoji": member.avatar_emoji,
            "is_current_user": member.id == (current_member.id if current_member else None),
            "picks": picks_data,
            "bonus_picks": bonus_picks_data,
            "total_points": round(total_points, 2),
            "correct_count": correct_count,
            "picks_submitted": len([p for p in member.picks if not p.category_key.startswith("bonus_")]),
            "bonus_submitted": len([p for p in member.picks if p.category_key.startswith("bonus_")]),
            "boldness": _compute_boldness([
                {"probability_at_pick": float(p.probability_at_pick) if p.probability_at_pick else 0.5}
                for p in member.picks if not p.category_key.startswith("bonus_")
            ]),
        })

    # Sort leaderboard by points (descending), then correct count
    leaderboard = sorted(
        members_data,
        key=lambda m: (m["total_points"], m["correct_count"]),
        reverse=True,
    )
    for rank, m in enumerate(leaderboard, 1):
        m["rank"] = rank

    # Count how many results have been revealed
    results = pool.results or {}
    categories_revealed = len([k for k in results if not k.startswith("bonus_")])
    bonus_revealed = len([k for k in results if k.startswith("bonus_")])

    return {
        "pool_name": pool.name,
        "pool_code": pool.code,
        "ceremony_year": pool.ceremony_year,
        "picks_locked": pool.picks_locked,
        "created_by": pool.created_by_name,
        "member_count": len(pool.members),
        "current_member_id": current_member.id if current_member else None,
        "members": members_data,
        "leaderboard": leaderboard,
        "results": results,
        "categories_revealed": categories_revealed,
        "bonus_revealed": bonus_revealed,
        "total_categories": 24,
        "bonus_markets": pool.bonus_markets or BONUS_MARKET_TEMPLATES,
        "avatar_options": AVATAR_EMOJIS,
    }


@router.post("/pool/{code}/picks")
async def submit_picks(
    code: str,
    request: SubmitPicksRequest,
    db: AsyncSession = Depends(get_db),
    x_member_token: str = Header(...),
):
    """Submit or update category picks. Max 3 confidence picks."""
    pool = await _get_pool(db, code)

    if pool.picks_locked:
        raise HTTPException(400, "Picks are locked! The ceremony has started.")

    member = await _get_member(db, x_member_token, pool.id)

    # Validate confidence picks (max 3)
    if len(request.confidence_picks) > 3:
        raise HTTPException(400, "Maximum 3 confidence picks allowed")

    # Delete existing non-bonus picks for this member
    existing = await db.execute(
        select(OscarsPoolPick).where(
            OscarsPoolPick.member_id == member.id,
            ~OscarsPoolPick.category_key.startswith("bonus_"),
        )
    )
    for pick in existing.scalars().all():
        await db.delete(pick)
    await db.flush()

    # Insert new picks
    for pick_item in request.picks:
        pick = OscarsPoolPick(
            member_id=member.id,
            category_key=pick_item.category_key,
            nominee_name=pick_item.nominee_name,
            probability_at_pick=pick_item.probability_at_pick,
            is_confidence_pick=pick_item.category_key in request.confidence_picks,
        )
        db.add(pick)

    await db.flush()

    return {
        "status": "picks_saved",
        "picks_count": len(request.picks),
        "confidence_picks": request.confidence_picks,
    }


@router.post("/pool/{code}/bonus-picks")
async def submit_bonus_picks(
    code: str,
    request: SubmitBonusPicksRequest,
    db: AsyncSession = Depends(get_db),
    x_member_token: str = Header(...),
):
    """Submit bonus market picks."""
    pool = await _get_pool(db, code)

    if pool.picks_locked:
        raise HTTPException(400, "Picks are locked!")

    member = await _get_member(db, x_member_token, pool.id)

    # Delete existing bonus picks
    existing = await db.execute(
        select(OscarsPoolPick).where(
            OscarsPoolPick.member_id == member.id,
            OscarsPoolPick.category_key.startswith("bonus_"),
        )
    )
    for pick in existing.scalars().all():
        await db.delete(pick)
    await db.flush()

    bonus_markets = pool.bonus_markets or BONUS_MARKET_TEMPLATES
    bonus_by_key = {b["key"]: b for b in bonus_markets}

    for bp in request.picks:
        bonus = bonus_by_key.get(bp.bonus_key)
        if not bonus:
            continue
        # For bonus markets, probability is 1/num_options (equal odds)
        num_options = len(bonus.get("options", []))
        pick = OscarsPoolPick(
            member_id=member.id,
            category_key=bp.bonus_key,
            nominee_name=bp.selected_option,
            probability_at_pick=round(1.0 / max(num_options, 1), 6),
            is_confidence_pick=False,
        )
        db.add(pick)

    await db.flush()

    return {"status": "bonus_picks_saved", "count": len(request.picks)}


@router.post("/pool/{code}/lock")
async def lock_picks(
    code: str,
    db: AsyncSession = Depends(get_db),
    x_member_token: str = Header(...),
):
    """Lock picks (only pool creator can do this). Reveals everyone's picks."""
    pool = await _get_pool(db, code)
    member = await _get_member(db, x_member_token, pool.id)

    if member.display_name != pool.created_by_name:
        raise HTTPException(403, "Only the pool creator can lock picks")

    pool.picks_locked = True
    await db.flush()

    return {"status": "picks_locked", "message": "All picks are now locked and visible!"}


@router.post("/pool/{code}/reveal")
async def reveal_winner(
    code: str,
    request: RevealWinnerRequest,
    db: AsyncSession = Depends(get_db),
    x_member_token: str = Header(...),
):
    """Reveal a category winner and score all picks. Only pool creator."""
    pool = await _get_pool(db, code, load_members=True)
    member = await _get_member(db, x_member_token, pool.id)

    if member.display_name != pool.created_by_name:
        raise HTTPException(403, "Only the pool creator can reveal winners")

    # Auto-lock if not locked yet
    if not pool.picks_locked:
        pool.picks_locked = True

    # Store result
    results = pool.results or {}
    results[request.category_key] = request.winner_name
    pool.results = results
    # Force SQLAlchemy to detect JSONB mutation
    from sqlalchemy.orm.attributes import flag_modified
    flag_modified(pool, "results")

    # Score all members' picks for this category
    scored_members = []
    for m in pool.members:
        for pick in m.picks:
            if pick.category_key == request.category_key:
                is_correct = _match_name(pick.nominee_name, request.winner_name)
                pick.is_correct = is_correct
                pick.points_earned = Decimal(str(
                    _compute_points(
                        float(pick.probability_at_pick) if pick.probability_at_pick else 0.5,
                        pick.is_confidence_pick,
                        is_correct,
                    )
                ))
                scored_members.append({
                    "display_name": m.display_name,
                    "avatar_emoji": m.avatar_emoji,
                    "picked": pick.nominee_name,
                    "is_correct": is_correct,
                    "points_earned": float(pick.points_earned),
                    "was_confidence_pick": pick.is_confidence_pick,
                    "was_dark_horse": (float(pick.probability_at_pick) if pick.probability_at_pick else 0.5) < 0.15,
                })

    await db.flush()

    return {
        "category_key": request.category_key,
        "winner": request.winner_name,
        "scored_members": scored_members,
    }


@router.post("/pool/{code}/reveal-bonus")
async def reveal_bonus(
    code: str,
    request: RevealBonusRequest,
    db: AsyncSession = Depends(get_db),
    x_member_token: str = Header(...),
):
    """Reveal a bonus market answer and score picks. Only pool creator."""
    pool = await _get_pool(db, code, load_members=True)
    member = await _get_member(db, x_member_token, pool.id)

    if member.display_name != pool.created_by_name:
        raise HTTPException(403, "Only the pool creator can reveal answers")

    # Store result
    results = pool.results or {}
    results[request.bonus_key] = request.correct_option
    pool.results = results
    from sqlalchemy.orm.attributes import flag_modified
    flag_modified(pool, "results")

    # Find the bonus market config for point value
    bonus_markets = pool.bonus_markets or BONUS_MARKET_TEMPLATES
    bonus = next((b for b in bonus_markets if b["key"] == request.bonus_key), None)
    points_value = bonus.get("points_value", 2) if bonus else 2

    # Score all members
    scored = []
    for m in pool.members:
        for pick in m.picks:
            if pick.category_key == request.bonus_key:
                is_correct = pick.nominee_name.strip().lower() == request.correct_option.strip().lower()
                pick.is_correct = is_correct
                pick.points_earned = Decimal(str(points_value)) if is_correct else Decimal("0")
                scored.append({
                    "display_name": m.display_name,
                    "avatar_emoji": m.avatar_emoji,
                    "picked": pick.nominee_name,
                    "is_correct": is_correct,
                    "points_earned": float(pick.points_earned),
                })

    await db.flush()

    return {
        "bonus_key": request.bonus_key,
        "correct_option": request.correct_option,
        "scored_members": scored,
    }


# ─── Internal helpers ────────────────────────────────────────────────────────

async def _get_pool(
    db: AsyncSession, code: str, load_members: bool = False
) -> OscarsPool:
    """Fetch pool by code, optionally eager-loading members + picks."""
    stmt = select(OscarsPool).where(OscarsPool.code == code.upper())
    if load_members:
        stmt = stmt.options(
            selectinload(OscarsPool.members).selectinload(OscarsPoolMember.picks)
        )
    result = await db.execute(stmt)
    pool = result.scalar_one_or_none()
    if not pool:
        raise HTTPException(404, "Pool not found. Check your code!")
    return pool


async def _get_member(
    db: AsyncSession, token: str, pool_id: int
) -> OscarsPoolMember:
    """Fetch member by token, confirming pool membership."""
    result = await db.execute(
        select(OscarsPoolMember).where(
            OscarsPoolMember.member_token == token,
            OscarsPoolMember.pool_id == pool_id,
        )
    )
    member = result.scalar_one_or_none()
    if not member:
        raise HTTPException(403, "Invalid member token")
    return member
