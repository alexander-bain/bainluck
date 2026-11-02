"""Bounded, deduplicated worker log history for unattended release health checks."""
from datetime import datetime, timezone
import re
import time
from typing import Any

MAX_BODY_BYTES = 262144
MAX_FRAME_BYTES = 8192
MAX_RECORDS = 5000
MAX_LINE_BYTES = 2048
RETENTION_SECONDS = 7200
DRAIN_STALE_SECONDS = 180
LOG_KEY = 'release-loop:worker-logs:v1'
LOSS_KEY = LOG_KEY + ':loss'
RECEIPT_KEY = LOG_KEY + ':received'
SOURCE_KEY = LOG_KEY + ':source'
WORKER = re.compile(r'^worker-ws(?:\.\d+)?$')
ERROR = re.compile(r'"level"\s*:\s*"(?:ERROR|CRITICAL)"|Traceback|LockNotAvailable|lock timeout|lock_timeout')
LIFECYCLE = re.compile(r'Starting process with command|State changed|Process exited|Error [RH]\d+')
LOG_LOSS = re.compile(r'Error L\d+|logplex.*(?:drop|overflow)', re.I)


def redact(message: str) -> str:
    message = re.sub(r'([a-z][a-z0-9+.-]*://)[^\s/@]+:[^\s/@]+@', r'\1[redacted]@', message, flags=re.I)
    message = re.sub(r'((?:api_?key|access_token|token|secret|password)=)[^\s&"\']+', r'\1[redacted]', message, flags=re.I)
    message = re.sub(r'("(?:authorization|token|api_?key|secret|password)"\s*:\s*)"[^"\n]*"', r'\1"[redacted]"', message, flags=re.I)
    return re.sub(r'Bearer\s+[A-Za-z0-9._~-]+', 'Bearer [redacted]', message, flags=re.I)


def parse_frame(raw: bytes) -> dict[str, Any] | None:
    parts = raw.decode('utf-8', 'replace').split(' ', 7)
    if len(parts) != 8 or not re.fullmatch(r'<\d{1,3}>1', parts[0]):
        raise ValueError('invalid Logplex syslog header')
    _version, stamp, _host, app, process, _message_id, structured, message = parts
    # Heroku uses NILVALUE structured data. Preserve explicit RFC5424 SD too.
    if structured != '-':
        combined = structured + ' ' + message
        if not combined.startswith('['): raise ValueError('invalid structured data')
        match = re.match(r'(?:\[(?:[^\\\]]|\\.)*\])+\s(.*)$', combined, re.S)
        if not match: raise ValueError('invalid structured data')
        message = match.group(1)
    stamp_dt = datetime.fromisoformat(stamp.replace('Z', '+00:00'))
    if stamp_dt.tzinfo is None: raise ValueError('syslog timestamp needs a timezone')
    stamp_dt = stamp_dt.astimezone(timezone.utc)
    timestamp = stamp_dt.timestamp()
    if app == 'heroku' and process == 'logplex' and LOG_LOSS.search(message):
        return {'timestamp': timestamp, 'loss': True}
    if app not in ('app', 'heroku') or not WORKER.fullmatch(process): return None
    keep = (LIFECYCLE.search(message) if app == 'heroku' else
            ERROR.search(message) or 'gc thresholds' in message or
            'startup recovery scan complete' in message or 'headline-clock' in message or
            ('msgs' in message and ('Kalshi WS:' in message or 'Polymarket WS:' in message)))
    if not keep: return {'timestamp': timestamp, 'heartbeat': True}
    canonical = stamp_dt.strftime('%Y-%m-%dT%H:%M:%S.%f+00:00') + ' ' + app + '[' + process + ']: ' + redact(message)
    encoded = canonical.encode()
    truncated = len(encoded) > MAX_LINE_BYTES
    canonical = encoded[:MAX_LINE_BYTES].decode('utf-8', 'ignore')
    return {'timestamp': timestamp, 'line': canonical, 'loss': truncated}


def parse_logplex(body: bytes) -> list[dict[str, Any]]:
    if len(body) > MAX_BODY_BYTES: raise ValueError('Logplex body exceeds limit')
    rows = []; offset = 0; frames = 0
    while offset < len(body):
        space = body.find(b' ', offset, offset + 9)
        if space < 0 or not body[offset:space].isdigit(): raise ValueError('invalid Logplex length')
        count = int(body[offset:space]); start = space + 1; end = start + count
        if count < 1 or count > MAX_FRAME_BYTES or end > len(body): raise ValueError('invalid Logplex frame size')
        frames += 1
        if frames > 1000: raise ValueError('too many Logplex frames')
        try:
            row = parse_frame(body[start:end])
            if row: rows.append(row)
        except ValueError:
            # Keep healthy siblings, but make lost diagnostic coverage explicit.
            rows.append({'timestamp': time.time(), 'loss': True})
        offset = end
    return rows


def _client():
    # Use the existing bounded pool/signature; no new Redis client or timeout tier.
    from app.tasks.redis_state import get_redis_client
    return get_redis_client()


def store(rows: list[dict[str, Any]], *, client=None, now: float | None = None) -> int:
    client = client if client is not None else _client()
    now = time.time() if now is None else now
    valid = [row for row in rows if now - RETENTION_SECONDS <= row['timestamp'] <= now + 60]
    logs = {row['line']: row['timestamp'] for row in valid if row.get('line')}
    losses = {str(row['timestamp']): row['timestamp'] for row in valid if row.get('loss')}
    sources = {str(row['timestamp']): row['timestamp'] for row in valid if row.get('line') or row.get('heartbeat')}
    if not logs and not losses and not sources: return 0
    pipe = client.pipeline(transaction=True)
    if logs: pipe.zadd(LOG_KEY, logs)
    if losses: pipe.zadd(LOSS_KEY, losses)
    if sources: pipe.zadd(SOURCE_KEY, sources)
    pipe.zremrangebyrank(SOURCE_KEY, 0, -2)
    pipe.expire(SOURCE_KEY, RETENTION_SECONDS)
    pipe.zremrangebyscore(LOG_KEY, '-inf', now - RETENTION_SECONDS)
    pipe.zremrangebyrank(LOG_KEY, 0, -MAX_RECORDS - 1)
    pipe.zremrangebyscore(LOSS_KEY, '-inf', now - RETENTION_SECONDS)
    pipe.zremrangebyrank(LOSS_KEY, 0, -101)
    pipe.expire(LOG_KEY, RETENTION_SECONDS)
    pipe.expire(LOSS_KEY, RETENTION_SECONDS)
    pipe.set(RECEIPT_KEY, str(now), ex=RETENTION_SECONDS)
    pipe.execute()
    return len(logs)


def read_window(since: float, *, client=None, now: float | None = None) -> dict[str, Any]:
    client = client if client is not None else _client()
    now = time.time() if now is None else now
    pipe = client.pipeline(transaction=True)
    pipe.zrange(LOG_KEY, 0, 0, withscores=True)
    pipe.zrangebyscore(LOG_KEY, since, '+inf', start=0, num=MAX_RECORDS)
    pipe.zrangebyscore(LOSS_KEY, since, '+inf', start=0, num=1)
    pipe.get(RECEIPT_KEY)
    pipe.zrange(SOURCE_KEY, -1, -1, withscores=True)
    first, lines, losses, receipt, source = pipe.execute()
    received = float(receipt) if receipt else None
    last_source = source[0][1] if source else None
    live = last_source is not None and now - last_source <= DRAIN_STALE_SECONDS
    complete = bool(first) and first[0][1] <= since and since >= now - RETENTION_SECONDS and not losses and live
    return {'lines': [line.decode() if isinstance(line, bytes) else line for line in lines],
            'complete': bool(complete), 'live': live, 'received_at': received, 'last_source_at': last_source,
            'available_since': first[0][1] if first else None,
            'loss_detected': bool(losses), 'retention_seconds': RETENTION_SECONDS, 'max_records': MAX_RECORDS}
