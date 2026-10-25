"""Review-only operation. No network at import; explicit fence/readback invocation required.
Run from the inventoried release's backend directory; external formation/owner interlock is mandatory.
"""
import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import sys

READBACK_SHA = '46981112b1b84c68ec66823710ee6c4fda9eed4eeb0eaff70df74478ff214c2f'
OLD_MODULE_SHA = '072e5f62ec791765a6fe0ac253f73ff2d017f7413c8a2ed6f68c029a97073c2b'
OLD_LUA_SHA = 'ff39632a9f8f6aaf63ef8a66423ba690998994e38a941c2d8c85069e4660282b'
SOURCES = ('kalshi', 'polymarket')  # Actual old ledger_sources(); environment does not narrow it.
KEYS = ('live:blend_preview:ledger', 'live:blend_preview:ledger:initialized',
        'live:blend_preview:epoch', 'live:blend_preview:owner:kalshi',
        'live:blend_preview:owner:polymarket')


# Raw evidence comes only from the hash-pinned metadata-only readback script.
# Cap retained characters; oversized output is explicitly truncated and cannot pass.
RAW_SNAPSHOT_MAX_CHARS = 65536
STOP_CODES = {
    'STOP: policy fields present; no reset or repair performed': 'POLICY_FIELDS_PRESENT',
    'STOP: namespace authority invalid': 'NAMESPACE_AUTHORITY_INVALID',
    'STOP: missing/malformed existing authority': 'EXISTING_AUTHORITY_INVALID',
    'STOP: resident bound invalid': 'RESIDENT_BOUND_INVALID',
    'STOP: old module mismatch': 'OLD_MODULE_MISMATCH',
    'STOP: loaded module/script mismatch': 'LOADED_MODULE_SCRIPT_MISMATCH',
    'STOP: sources/keys mismatch': 'SOURCES_KEYS_MISMATCH',
    'STOP: explicit Redis configuration required': 'REDIS_CONFIGURATION_REQUIRED',
    'STOP: readback script mismatch': 'READBACK_SCRIPT_MISMATCH',
    'STOP: unexpected write': 'UNEXPECTED_WRITE',
    'STOP: owner changed after fence; no repeat claim': 'OWNER_CHANGED_AFTER_FENCE',
    'STOP: unexpected resident/barrier change': 'RESIDENT_BARRIER_CHANGED',
    'STOP: raw snapshot oversized': 'RAW_SNAPSHOT_OVERSIZED',
    'STOP: raw snapshot wrong type': 'RAW_SNAPSHOT_WRONG_TYPE',
}


def emit_stop(exc):
    code = STOP_CODES.get(str(exc), 'UNEXPECTED_ERROR') if type(exc) is ValueError else 'UNEXPECTED_ERROR'
    print(json.dumps({'stage':'STOP_INCONCLUSIVE', 'stop_code':code,
                      'error_type':type(exc).__name__,
                      'instruction':'No retry/start/bootstrap; reconcile acknowledged and ambiguous claims.'}), flush=True)


def recorded_snapshot(raw, phase, release_identity):
    if not isinstance(raw, str):
        raise ValueError('STOP: raw snapshot wrong type')
    truncated = len(raw) > RAW_SNAPSHOT_MAX_CHARS
    print(json.dumps({'stage':'raw_snapshot', 'phase':phase,
                      'release_identity':release_identity,
                      'raw_snapshot':raw[:RAW_SNAPSHOT_MAX_CHARS],
                      'truncated':truncated}), flush=True)
    if truncated:
        raise ValueError('STOP: raw snapshot oversized')
    return checked_snapshot(raw)


def checked_snapshot(raw):
    snapshot = json.loads(raw)
    if snapshot['policy_field_count'] != 0:
        raise ValueError('STOP: policy fields present; no reset or repair performed')
    def uint(value):
        return isinstance(value, str) and value.isascii() and value.isdecimal() and str(int(value)) == value and int(value) <= 9007199254740991
    headers = snapshot['headers']
    if snapshot['initialized'] != '1' or not uint(snapshot['shared_epoch']):
        raise ValueError('STOP: namespace authority invalid')
    if not all(uint(headers[f]) for f in ('epoch','retired','nevents',
               'owner:kalshi','read_owner:kalshi','owner:polymarket','read_owner:polymarket')):
        raise ValueError('STOP: missing/malformed existing authority')
    if int(headers['nevents']) > 512:
        raise ValueError('STOP: resident bound invalid')
    return snapshot


async def fence_once(registry, call):
    """No retry. A partial/ambiguous pair has no success return."""
    epochs = {}
    for source in SOURCES:
        epochs[source] = await registry.claim(call, source)
        print(json.dumps({'stage':'claim_ack', 'source':source, 'epoch':epochs[source]}), flush=True)
    return epochs


async def operation(mode, release_identity):
    import redis.asyncio as aioredis
    bp = None
    if mode == 'fence':
        path = Path('app/utils/blend_preview.py').resolve()
        if hashlib.sha256(path.read_bytes()).hexdigest() != OLD_MODULE_SHA:
            raise ValueError('STOP: old module mismatch')
        from app.utils import blend_preview as bp
        if Path(bp.__file__).resolve() != path or hashlib.sha256(bp.LEDGER_SCRIPT.encode()).hexdigest() != OLD_LUA_SHA:
            raise ValueError('STOP: loaded module/script mismatch')
        if tuple(sorted(bp.ledger_sources())) != SOURCES or tuple(bp.ledger_keys()) != KEYS:
            raise ValueError('STOP: sources/keys mismatch')
    url = os.environ.get('REDIS_URL')
    if not url or not url.startswith(('redis://','rediss://')):
        raise ValueError('STOP: explicit Redis configuration required')
    script = Path(__file__).with_name('readback.lua').read_text()
    if hashlib.sha256(script.encode()).hexdigest() != READBACK_SHA:
        raise ValueError('STOP: readback script mismatch')
    kwargs = dict(socket_connect_timeout=5, socket_timeout=5, max_connections=1, decode_responses=True)
    if url.startswith('rediss://'):
        kwargs['ssl_cert_reqs'] = None  # Existing release's get_async_redis_client TLS setting.
    pool = aioredis.ConnectionPool.from_url(url, **kwargs)
    try:
        async with asyncio.timeout(20):
            try:
                connection = await pool.get_connection()
            except TypeError:  # redis-py5.0 requires command_name; pre-checkout signature fallback.
                connection = await pool.get_connection('EVAL')
            async def raw(*args):
                # Direct transport: no command retry after an ambiguous write/reply.
                await connection.send_command(*args, check_health=False)
                return await connection.read_response()
            async def readback(phase):
                return recorded_snapshot(await raw('EVAL', script, len(KEYS), *KEYS), phase, release_identity)
            before = await readback('before')
            print(json.dumps({'stage':'before', 'release_identity':release_identity, 'snapshot':before}), flush=True)
            if mode == 'readback':
                return
            registry = bp.LedgerRegistry(sources=frozenset(SOURCES))
            sent = set()
            async def claim_call(*args):
                # This adapter permits only one old-script claim invocation per source.
                expected = ('EVAL', bp.LEDGER_SCRIPT, len(KEYS), *KEYS, 'claim')
                if tuple(args[:-1]) != expected or args[-1] not in SOURCES or args[-1] in sent:
                    raise ValueError('STOP: unexpected write')
                sent.add(args[-1])
                return await raw(*args)
            epochs = await fence_once(registry, claim_call)
            after = await readback('after')
            print(json.dumps({'stage':'after', 'snapshot':after}), flush=True)
            if any(after['headers']['owner:'+s] != str(epochs[s]) or
                   after['headers']['read_owner:'+s] != str(epochs[s]) for s in SOURCES):
                raise ValueError('STOP: owner changed after fence; no repeat claim')
            if after['headers']['nevents'] != before['headers']['nevents'] or after['headers']['retired'] != before['headers']['retired']:
                raise ValueError('STOP: unexpected resident/barrier change')
            print(json.dumps({'stage':'fence_complete', 'epochs':epochs, 'snapshot':after}), flush=True)
    finally:
        # Cleanup is independently bounded; timeout/disconnect does not cancel server execution.
        async with asyncio.timeout(2):
            await pool.disconnect()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', choices=('fence','readback'), required=True)
    parser.add_argument('--release-identity', required=True, help='Externally inventoried release/slug receipt reference; not self-authentication')
    args = parser.parse_args()
    try:
        asyncio.run(operation(args.mode, args.release_identity))
    except Exception as exc:
        emit_stop(exc)
        sys.exit(2)  # Never print credential-bearing exception text.
