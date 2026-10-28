"""#10090 — start, stop and read a speed-switch trial (`app.tasks.speed_switches`).

``POST /api/admin/speed-switch {name, mode, ttl_s, half}`` writes or clears
one switch's Redis key. ``mode`` is ``off`` or ``ab``; there is no "all games
on". ``ab`` turns the switch on for the live events whose id parity equals
``half`` (default 0) until ``ttl_s`` seconds from now, at most 1800 — Alex's
standing limits for a trial without a release. The key carries the same TTL,
so Redis drops it when the trial ends even if nobody clears it. Every worker
process reads it within a few seconds and logs its own mode change.
``GET /api/admin/speed-switch`` reads every switch's stored trial.

Workers obey a trial only with ``SPEED_SWITCH_TRIALS=1`` in their config
(``trials_enabled`` reports the answering process's setting; Heroku config is
per app, so the web dyno's value is the worker's when both run on one app).
"""

import logging
import time
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from app.routes.admin_utils import _check_admin_secret
from app.tasks import speed_switches as sw

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/speed-switch", tags=["admin-speed-switch"])


class SpeedSwitchRequest(BaseModel):
    name: str
    mode: str
    ttl_s: Optional[int] = None
    half: int = 0


def _stored(client, now: float) -> dict:
    values = client.mget([sw.key(name) for name in sw.SWITCHES])
    return {name: sw.parse(raw, now).describe() for name, raw in zip(sw.SWITCHES, values)}


def _client():
    from app.tasks.redis_state import get_redis_client

    return get_redis_client()


@router.get("")
async def get_speed_switches(request: Request, secret: str = Query(None)) -> dict:
    _check_admin_secret(secret, request=request)
    now = time.time()
    return {"now": now, "max_ttl_s": sw.MAX_TTL_S, "trials_enabled": sw.trials_enabled(),
            "switches": _stored(_client(), now)}


@router.post("")
async def set_speed_switch(body: SpeedSwitchRequest, request: Request,
                           secret: str = Query(None)) -> dict:
    _check_admin_secret(secret, request=request)
    if body.name not in sw.SWITCHES:
        raise HTTPException(status_code=422, detail=f"unknown switch; allowed: {list(sw.SWITCHES)}")
    if body.mode not in sw.MODES:
        raise HTTPException(status_code=422, detail=f"mode must be one of {list(sw.MODES)}")
    client = _client()
    now = time.time()
    if body.mode == "off":
        client.delete(sw.key(body.name))
    else:
        if body.ttl_s is None or not 1 <= body.ttl_s <= sw.MAX_TTL_S:
            raise HTTPException(status_code=422,
                                detail=f"ab needs ttl_s between 1 and {sw.MAX_TTL_S}")
        if body.half not in (0, 1):
            raise HTTPException(status_code=422, detail="half must be 0 or 1")
        client.set(sw.key(body.name), sw.encode(body.half, now + body.ttl_s, now),
                   ex=body.ttl_s)
    stored = _stored(client, now)[body.name]
    logger.info("speed_switch: admin set %s mode=%s half=%s expires_at=%s",
                body.name, stored["mode"], stored["half"], stored["expires_at"])
    return {"name": body.name, "now": now, "trials_enabled": sw.trials_enabled(), **stored}
