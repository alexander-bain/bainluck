"""#10090 — start, stop and read a speed-switch trial (`app.tasks.speed_switches`).

``POST /api/admin/speed-switch`` writes or clears one switch's Redis key:

* ``{name, mode: "off"}`` ends a trial now.
* ``{name, mode: "ab", ttl_s, half}`` turns a boolean switch on for the live
  events whose id parity equals ``half`` (default 0).
* ``{name, mode: "alternate", ttl_s, a, b, period_s}`` switches between values
  ``a`` and ``b`` every ``period_s`` (whole minutes, 60..900) of wall-clock
  time from the current minute, ``a`` first. One of ``a``/``b`` must be today's
  value and ``ttl_s`` a whole number of a/b pairs; the trial ends ``ttl_s``
  after its start minute, so exactly half its minutes differ from today.

``ttl_s`` is at most 1800 — Alex's standing limits for a trial without a
release. There is no "all games on". The key carries the same TTL, so Redis
drops it when the trial ends even if nobody clears it. Every worker process
reads it within a few seconds and logs its own mode change and arm boundaries.
``GET /api/admin/speed-switch`` reads every switch's stored trial.

Workers obey a trial only with ``SPEED_SWITCH_TRIALS=1`` in their config
(``trials_enabled`` reports the answering process's setting; Heroku config is
per app, so the web dyno's value is the worker's when both run on one app).
"""

import logging
import math
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
    a: Optional[int] = None
    b: Optional[int] = None
    period_s: Optional[int] = None


def _stored(client, now: float) -> dict:
    values = client.mget([sw.key(name) for name in sw.SWITCHES])
    return {name: sw.parse(raw, now, name).describe()
            for name, raw in zip(sw.SWITCHES, values)}


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
                                detail=f"a trial needs ttl_s between 1 and {sw.MAX_TTL_S}")
        problem = sw.validate(body.name, body.mode, body.half, body.a, body.b, body.period_s,
                              span_s=body.ttl_s if body.mode == "alternate" else None)
        if problem is not None:
            raise HTTPException(status_code=422, detail=problem)
        expires_at = sw.expiry(body.mode, body.ttl_s, now)
        client.set(sw.key(body.name),
                   sw.encode(body.name, body.mode, expires_at, now, half=body.half,
                             a=body.a, b=body.b, period_s=body.period_s),
                   ex=max(1, math.ceil(expires_at - now)))
    stored = _stored(client, now)[body.name]
    # Only allowlisted constants reach the log: CodeQL grades the request body and
    # a Redis read alike as py/log-injection. Each worker logs its arm and expiry.
    logger.info("speed_switch: admin set %s mode=%s",
                next(n for n in sw.SWITCHES if n == body.name),
                next(m for m in sw.MODES if m == body.mode))
    return {"name": body.name, "now": now, "trials_enabled": sw.trials_enabled(), **stored}
