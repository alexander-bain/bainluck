"""Authenticate GitHub review events and dispatch reviewed default-branch policy."""
import hashlib
import hmac
import json
import os

import httpx
from fastapi import APIRouter, HTTPException, Request

router = APIRouter()
REPOSITORY = 'alexander-bain/bainluck'
MAX_BODY_BYTES = 512 * 1024


def dispatch_payload(number: int) -> dict:
    return {'event_type': 'tier-b-review', 'client_payload': {'pull_number': number}}


async def dispatch_review(number: int) -> None:
    token = os.environ.get('RELEASE_DISPATCH_TOKEN')
    if not token:
        raise HTTPException(status_code=503, detail='Review dispatch is not configured')
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f'https://api.github.com/repos/{REPOSITORY}/dispatches',
                json=dispatch_payload(number),
                headers={'Authorization': f'Bearer {token}',
                         'Accept': 'application/vnd.github+json',
                         'X-GitHub-Api-Version': '2022-11-28'},
            )
        if response.status_code != 204:
            raise HTTPException(status_code=502, detail='Review dispatch was not accepted')
    except httpx.HTTPError:
        # Transport errors can include request headers; never publish the text.
        raise HTTPException(status_code=502, detail='Review dispatch transport failed') from None


@router.post('/api/release-loop/tier-b-review', status_code=202)
async def review_webhook(request: Request) -> dict:
    secret = os.environ.get('TIER_B_REVIEW_WEBHOOK_SECRET')
    if not secret:
        raise HTTPException(status_code=503, detail='Review webhook is not configured')
    size = 0
    chunks = []
    async for chunk in request.stream():
        size += len(chunk)
        if size > MAX_BODY_BYTES:
            raise HTTPException(status_code=413, detail='Webhook body is too large')
        chunks.append(chunk)
    body = b''.join(chunks)
    expected = 'sha256=' + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    supplied = request.headers.get('X-Hub-Signature-256', '')
    if not supplied.isascii() or not hmac.compare_digest(expected, supplied):
        raise HTTPException(status_code=401, detail='Webhook signature is invalid')
    event = request.headers.get('X-GitHub-Event')
    if event == 'ping':
        if not os.environ.get('RELEASE_DISPATCH_TOKEN'):
            raise HTTPException(status_code=503, detail='Review dispatch is not configured')
        return {'accepted': True, 'event': 'ping'}
    if event != 'pull_request_review':
        return {'accepted': False, 'event': 'ignored'}
    try:
        data = json.loads(body)
        repository = data['repository']['full_name']
        number = data['pull_request']['number']
        action = data['action']
    except (ValueError, TypeError, KeyError):
        raise HTTPException(status_code=400, detail='Webhook payload is invalid') from None
    if repository != REPOSITORY:
        raise HTTPException(status_code=403, detail='Webhook repository is not allowed')
    if not isinstance(action, str):
        raise HTTPException(status_code=400, detail='Webhook action is invalid')
    if action not in {'submitted', 'edited', 'dismissed'}:
        return {'accepted': False, 'event': 'ignored'}
    if isinstance(number, bool) or not isinstance(number, int) or number < 1:
        raise HTTPException(status_code=400, detail='Pull request number is invalid')
    await dispatch_review(number)
    return {'accepted': True, 'pull_number': number}
