"""WrestleMania 42 prediction game API."""

import os
import secrets
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Header, Query
from pydantic import BaseModel
from sqlalchemy import select, delete, func, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.wrestlemania import (
    WrestlemaniaMatch,
    WrestlemaniaOutcome,
    WrestlemaniaOddsSnapshot,
    WrestlemaniaPlayer,
    WrestlemaniaPick,
)
from app.services import get_db
from app.services.wikipedia_images import resolve_wrestler_image
from app.utils.wrestlemania_scoring import compute_bankroll

router = APIRouter()

ADMIN_SECRET = os.getenv("ADMIN_SECRET", "") or os.getenv("ADMIN_TOKEN", "")


# ── Request/Response Models ──────────────────────────────────────────────

class RegisterRequest(BaseModel):
    display_name: str

class PickRequest(BaseModel):
    match_id: int
    outcome_id: int
    stake: float

class ResolveRequest(BaseModel):
    match_id: int
    winner_outcome_id: int

class AddMatchRequest(BaseModel):
    match_order: int
    night: int
    title: str
    match_type: str
    participants: list[str]
    lock_time: str
    outcomes: list[dict]


# ── Helpers ──────────────────────────────────────────────────────────────

def _verify_admin(secret: str = Query(None)):
    if not ADMIN_SECRET or secret != ADMIN_SECRET:
        raise HTTPException(403, "Invalid admin secret")


async def _get_player(session: AsyncSession, token: Optional[str]):
    if not token:
        return None
    result = await session.execute(
        select(WrestlemaniaPlayer).where(WrestlemaniaPlayer.player_token == token)
    )
    return result.scalar_one_or_none()


async def _player_picks(session: AsyncSession, player_id: int) -> list[dict]:
    result = await session.execute(
        select(WrestlemaniaPick).where(WrestlemaniaPick.player_id == player_id)
    )
    return [
        {
            "stake": float(p.stake),
            "decimal_odds_at_pick": float(p.decimal_odds_at_pick),
            "result": p.result,
        }
        for p in result.scalars().all()
    ]


# ── Card ─────────────────────────────────────────────────────────────────

@router.get("/card")
async def get_card(
    x_player_token: Optional[str] = Header(None),
    session: AsyncSession = Depends(get_db),
):
    player = await _get_player(session, x_player_token)

    matches_result = await session.execute(
        select(WrestlemaniaMatch).order_by(
            WrestlemaniaMatch.night, WrestlemaniaMatch.match_order
        )
    )
    matches = matches_result.scalars().all()

    picks_by_match = {}
    if player:
        picks_result = await session.execute(
            select(WrestlemaniaPick).where(
                WrestlemaniaPick.player_id == player.id
            )
        )
        for pick in picks_result.scalars().all():
            picks_by_match[pick.match_id] = pick

    # Pre-fetch all odds history for sparklines
    all_outcome_ids_result = await session.execute(
        select(WrestlemaniaOutcome.id, WrestlemaniaOutcome.match_id)
    )
    outcome_to_match = {r.id: r.match_id for r in all_outcome_ids_result.all()}
    all_snaps_result = await session.execute(
        select(WrestlemaniaOddsSnapshot)
        .where(WrestlemaniaOddsSnapshot.outcome_id.in_(list(outcome_to_match.keys())))
        .order_by(WrestlemaniaOddsSnapshot.recorded_at)
    )
    history_by_outcome: dict[int, list] = {}
    for s in all_snaps_result.scalars().all():
        history_by_outcome.setdefault(s.outcome_id, []).append({
            "p": float(s.probability),
            "t": s.recorded_at.isoformat(),
        })

    nights: dict[int, list] = {}
    for match in matches:
        outcomes_result = await session.execute(
            select(WrestlemaniaOutcome)
            .where(WrestlemaniaOutcome.match_id == match.id)
            .order_by(WrestlemaniaOutcome.id)
        )
        outcomes = outcomes_result.scalars().all()

        pick = picks_by_match.get(match.id)
        my_pick = None
        if pick:
            my_pick = {
                "id": pick.id,
                "outcome_id": pick.outcome_id,
                "stake": float(pick.stake),
                "decimal_odds_at_pick": float(pick.decimal_odds_at_pick),
                "result": pick.result,
                "payout": float(pick.payout) if pick.payout else None,
            }

        all_picks_result = await session.execute(
            select(
                WrestlemaniaPick.outcome_id,
                WrestlemaniaPlayer.display_name,
                WrestlemaniaPick.stake,
                WrestlemaniaPick.decimal_odds_at_pick,
                WrestlemaniaPick.result,
            ).join(WrestlemaniaPlayer).where(
                WrestlemaniaPick.match_id == match.id
            )
        )
        public_picks = [
            {
                "player": row.display_name,
                "outcome_id": row.outcome_id,
                "stake": float(row.stake),
                "decimal_odds_at_pick": float(row.decimal_odds_at_pick),
                "result": row.result,
            }
            for row in all_picks_result.all()
        ]

        match_data = {
            "id": match.id,
            "match_order": match.match_order,
            "night": match.night,
            "title": match.title,
            "match_type": match.match_type,
            "participants": match.participants,
            "lock_time": match.lock_time.isoformat() if match.lock_time else None,
            "status": match.status,
            "storyline": match.storyline,
            "outcomes": [
                {
                    "id": o.id,
                    "name": o.name,
                    "probability": float(o.probability) if o.probability else None,
                    "decimal_odds": float(o.decimal_odds) if o.decimal_odds else None,
                    "wikipedia_image_url": o.wikipedia_image_url,
                    "is_winner": o.is_winner,
                    "case_text": o.case_text,
                    "history": history_by_outcome.get(o.id, []),
                }
                for o in outcomes
            ],
            "my_pick": my_pick,
            "picks": public_picks,
        }
        nights.setdefault(match.night, []).append(match_data)

    player_data = None
    if player:
        picks = await _player_picks(session, player.id)
        player_data = {
            "id": player.id,
            "display_name": player.display_name,
            "player_token": player.player_token,
            "bankroll": compute_bankroll(picks),
        }

    return {
        "nights": [
            {"night": n, "matches": nights.get(n, [])}
            for n in sorted(nights.keys())
        ],
        "player": player_data,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


# ── Players ──────────────────────────────────────────────────────────────

@router.post("/players")
async def register_player(req: RegisterRequest, session: AsyncSession = Depends(get_db)):
    name = req.display_name.strip()
    if not name or len(name) > 50:
        raise HTTPException(400, "Name must be 1-50 characters")

    existing = await session.execute(
        select(WrestlemaniaPlayer).where(
            func.lower(WrestlemaniaPlayer.display_name) == name.lower()
        )
    )
    player = existing.scalar_one_or_none()

    if player:
        picks = await _player_picks(session, player.id)
        return {
            "id": player.id,
            "display_name": player.display_name,
            "player_token": player.player_token,
            "bankroll": compute_bankroll(picks),
        }

    token = secrets.token_hex(32)
    player = WrestlemaniaPlayer(display_name=name, player_token=token)
    session.add(player)
    await session.commit()
    await session.refresh(player)

    return {
        "id": player.id,
        "display_name": player.display_name,
        "player_token": player.player_token,
        "bankroll": 1_000_000,
    }


# ── Picks ────────────────────────────────────────────────────────────────

@router.post("/picks")
async def submit_pick(
    req: PickRequest,
    x_player_token: str = Header(),
    session: AsyncSession = Depends(get_db),
):
    if req.stake < 1:
        raise HTTPException(400, "Minimum stake is $1")

    player = await _get_player(session, x_player_token)
    if not player:
        raise HTTPException(401, "Invalid player token")

    match = await session.get(WrestlemaniaMatch, req.match_id)
    if not match:
        raise HTTPException(404, "Match not found")
    if match.status != "open":
        raise HTTPException(400, f"Match is {match.status}")

    outcome = await session.get(WrestlemaniaOutcome, req.outcome_id)
    if not outcome or outcome.match_id != match.id:
        raise HTTPException(400, "Invalid outcome for this match")

    picks = await _player_picks(session, player.id)
    bankroll = compute_bankroll(picks)
    if req.stake > bankroll:
        raise HTTPException(400, f"Insufficient bankroll (${bankroll:,.0f})")

    await session.execute(
        delete(WrestlemaniaPick).where(
            WrestlemaniaPick.player_id == player.id,
            WrestlemaniaPick.match_id == match.id,
        )
    )

    decimal_odds = float(outcome.decimal_odds) if outcome.decimal_odds else 2.0
    pick = WrestlemaniaPick(
        player_id=player.id,
        outcome_id=outcome.id,
        match_id=match.id,
        stake=req.stake,
        decimal_odds_at_pick=decimal_odds,
    )
    session.add(pick)
    await session.commit()
    await session.refresh(pick)

    return {
        "id": pick.id,
        "outcome_id": pick.outcome_id,
        "stake": float(pick.stake),
        "decimal_odds_at_pick": float(pick.decimal_odds_at_pick),
    }


@router.delete("/picks/{pick_id}")
async def delete_pick(
    pick_id: int,
    x_player_token: str = Header(),
    session: AsyncSession = Depends(get_db),
):
    player = await _get_player(session, x_player_token)
    if not player:
        raise HTTPException(401, "Invalid player token")

    pick = await session.get(WrestlemaniaPick, pick_id)
    if not pick or pick.player_id != player.id:
        raise HTTPException(404, "Pick not found")

    match = await session.get(WrestlemaniaMatch, pick.match_id)
    if match and match.status != "open":
        raise HTTPException(400, "Match is locked")

    await session.delete(pick)
    await session.commit()
    return {"deleted": True}


# ── Leaderboard ──────────────────────────────────────────────────────────

@router.get("/leaderboard")
async def get_leaderboard(session: AsyncSession = Depends(get_db)):
    players_result = await session.execute(
        select(WrestlemaniaPlayer).order_by(WrestlemaniaPlayer.id)
    )
    players = players_result.scalars().all()

    leaderboard = []
    for p in players:
        picks = await _player_picks(session, p.id)
        bankroll = compute_bankroll(picks)
        total_staked = sum(pk["stake"] for pk in picks)
        wins = sum(1 for pk in picks if pk["result"] == "won")
        losses = sum(1 for pk in picks if pk["result"] == "lost")
        pending = sum(1 for pk in picks if pk["result"] is None)
        leaderboard.append({
            "id": p.id,
            "display_name": p.display_name,
            "bankroll": bankroll,
            "total_staked": total_staked,
            "picks_count": len(picks),
            "wins": wins,
            "losses": losses,
            "pending": pending,
        })

    leaderboard.sort(key=lambda x: x["bankroll"], reverse=True)
    return {"leaderboard": leaderboard}


# ── Odds History ─────────────────────────────────────────────────────────

@router.get("/odds-history/{match_id}")
async def get_odds_history(match_id: int, session: AsyncSession = Depends(get_db)):
    outcomes_result = await session.execute(
        select(WrestlemaniaOutcome).where(
            WrestlemaniaOutcome.match_id == match_id
        )
    )
    outcomes = outcomes_result.scalars().all()
    outcome_ids = [o.id for o in outcomes]

    if not outcome_ids:
        raise HTTPException(404, "Match not found")

    snaps_result = await session.execute(
        select(WrestlemaniaOddsSnapshot)
        .where(WrestlemaniaOddsSnapshot.outcome_id.in_(outcome_ids))
        .order_by(WrestlemaniaOddsSnapshot.recorded_at)
    )
    snapshots = snaps_result.scalars().all()

    history: dict[int, list] = {o.id: [] for o in outcomes}
    for s in snapshots:
        history[s.outcome_id].append({
            "probability": float(s.probability),
            "recorded_at": s.recorded_at.isoformat(),
            "source": s.source,
        })

    return {
        "match_id": match_id,
        "outcomes": [
            {
                "id": o.id,
                "name": o.name,
                "history": history.get(o.id, []),
            }
            for o in outcomes
        ],
    }


# ── Admin ────────────────────────────────────────────────────────────────

@router.post("/admin/resolve")
async def resolve_match(
    req: ResolveRequest,
    secret: str = Query(),
    session: AsyncSession = Depends(get_db),
):
    _verify_admin(secret)

    match = await session.get(WrestlemaniaMatch, req.match_id)
    if not match:
        raise HTTPException(404, "Match not found")

    winner = await session.get(WrestlemaniaOutcome, req.winner_outcome_id)
    if not winner or winner.match_id != match.id:
        raise HTTPException(400, "Invalid winner outcome")

    await session.execute(
        update(WrestlemaniaMatch)
        .where(WrestlemaniaMatch.id == match.id)
        .values(status="resolved", winner_outcome_id=winner.id)
    )

    outcomes_result = await session.execute(
        select(WrestlemaniaOutcome).where(
            WrestlemaniaOutcome.match_id == match.id
        )
    )
    for o in outcomes_result.scalars().all():
        await session.execute(
            update(WrestlemaniaOutcome)
            .where(WrestlemaniaOutcome.id == o.id)
            .values(is_winner=(o.id == winner.id))
        )

    picks_result = await session.execute(
        select(WrestlemaniaPick).where(
            WrestlemaniaPick.match_id == match.id
        )
    )
    settled = 0
    for pick in picks_result.scalars().all():
        if pick.outcome_id == winner.id:
            payout = float(Decimal(str(pick.stake)) * Decimal(str(pick.decimal_odds_at_pick)))
            await session.execute(
                update(WrestlemaniaPick)
                .where(WrestlemaniaPick.id == pick.id)
                .values(result="won", payout=payout)
            )
        else:
            await session.execute(
                update(WrestlemaniaPick)
                .where(WrestlemaniaPick.id == pick.id)
                .values(result="lost", payout=0)
            )
        settled += 1

    await session.commit()
    return {"resolved": True, "match_id": match.id, "winner": winner.name, "settled_picks": settled}


@router.post("/admin/add-match")
async def add_match(
    req: AddMatchRequest,
    secret: str = Query(),
    session: AsyncSession = Depends(get_db),
):
    _verify_admin(secret)

    match = WrestlemaniaMatch(
        match_order=req.match_order,
        night=req.night,
        title=req.title,
        match_type=req.match_type,
        participants=req.participants,
        lock_time=datetime.fromisoformat(req.lock_time),
    )
    session.add(match)
    await session.flush()

    for out_data in req.outcomes:
        prob = out_data.get("probability", 0.5)
        session.add(
            WrestlemaniaOutcome(
                match_id=match.id,
                name=out_data["name"],
                probability=prob,
                decimal_odds=round(1.0 / prob, 3) if prob > 0.01 else 100.0,
            )
        )

    await session.commit()
    return {"match_id": match.id}


@router.post("/admin/refetch-images")
async def refetch_images(
    secret: str = Query(),
    session: AsyncSession = Depends(get_db),
):
    _verify_admin(secret)

    outcomes_result = await session.execute(select(WrestlemaniaOutcome))
    outcomes = outcomes_result.scalars().all()
    found = 0
    failed = []
    for o in outcomes:
        if "&" in o.name or "," in o.name:
            continue
        if o.wikipedia_image_url:
            continue
        url = await resolve_wrestler_image(o.name)
        if url:
            o.wikipedia_image_url = url
            found += 1
        else:
            failed.append(o.name)
    await session.commit()
    return {"found": found, "failed": failed}
