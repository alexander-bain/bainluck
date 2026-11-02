"""Private release log ingestion and authorized durable health-check input."""
import asyncio
from datetime import datetime
import hmac
import os
import time

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from app.routes.admin_utils import _check_admin_secret, bearer_credentials
from app.utils import release_log_store

router = APIRouter()


async def _record_rejected_batch():
    try:
        await asyncio.to_thread(release_log_store.store, [{'timestamp': time.time(), 'loss': True}])
    except Exception:
        raise HTTPException(status_code=503, detail='Release log store unavailable') from None


@router.post('/release-logs/drain')
async def ingest_release_logs(request: Request):
    expected = os.getenv('RELEASE_LOG_DRAIN_TOKEN')
    actual = bearer_credentials(request)
    if not expected or not hmac.compare_digest(expected.encode(), actual.encode()):
        raise HTTPException(status_code=403, detail='Invalid drain authorization')
    if request.headers.get('x-release-log-loss') == '1':
        await _record_rejected_batch()
        return JSONResponse({'accepted': 0, 'loss_recorded': True}, status_code=202, headers={'Cache-Control': 'no-store'})
    payload = bytearray()
    async for chunk in request.stream():
        payload.extend(chunk)
        if len(payload) > release_log_store.MAX_BODY_BYTES:
            await _record_rejected_batch()
            raise HTTPException(status_code=413, detail='Drain body exceeds limit')
    try:
        rows = await asyncio.to_thread(release_log_store.parse_logplex, bytes(payload))
    except ValueError:
        await _record_rejected_batch()
        raise HTTPException(status_code=400, detail='Invalid Logplex frames') from None
    try:
        accepted = await asyncio.to_thread(release_log_store.store, rows)
    except Exception:
        # No payload/headers/credential-bearing exception strings in logs or HTTP.
        raise HTTPException(status_code=503, detail='Release log store unavailable') from None
    return JSONResponse({'accepted': accepted}, status_code=202, headers={'Cache-Control': 'no-store'})


@router.get('/admin/release-logs')
async def read_release_logs(request: Request, since: datetime):
    _check_admin_secret(request=request, allow_account=False)
    if since.tzinfo is None:
        raise HTTPException(status_code=400, detail='since requires a timezone')
    try:
        result = await asyncio.to_thread(release_log_store.read_window, since.timestamp())
    except Exception:
        raise HTTPException(status_code=503, detail='Release log store unavailable') from None
    return JSONResponse(result, headers={'Cache-Control': 'no-store'})
