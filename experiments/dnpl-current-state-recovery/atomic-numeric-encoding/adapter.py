"""TEST ONLY command builders. Not imported by production or connected to Redis.

The production producer must supply stable lease_id, ORIGINAL expiry and issued
clock; this adapter intentionally cannot infer them from a freshly received TTL.
"""
from copy import deepcopy
import json
import math
from pathlib import Path

SCRIPT = Path(__file__).with_name('authority.lua').read_text()
MAX = 2**53 - 1
QUOTE_STATUSES = {'live', 'scheduled', 'suspended'}


def uint(value):
    return type(value) is int and 0 <= value <= MAX


class Commands:
    def __init__(self, keys, event_id):
        if len(keys) != 5 or not all(type(k) is str and k for k in keys):
            raise ValueError('five explicit colocated test keys required')
        if not uint(event_id) or event_id == 0:
            raise ValueError('event id required')
        self.keys, self.event_id = tuple(keys), event_id

    def command(self, *args):
        return ('EVAL', SCRIPT, 5, *self.keys, *args)

    def claim(self):
        return self.command('claim')

    def offer(self, frame, *, issued_at_ms=None):
        if (type(frame) is not dict or frame.get('event_id') != self.event_id
                or frame.get('provisional') is not True or 'rev' in frame):
            raise ValueError('wrong preview scope or authority')
        frame = deepcopy(frame)
        meta = frame.get('preview')
        if type(meta) is not dict or not uint(meta.get('epoch')) or not uint(meta.get('seq')) or meta['seq'] == 0:
            raise ValueError('epoch and sequence required')
        kind = meta.get('kind')
        if kind == 'blend':
            p, ttl, base = frame.get('p'), meta.get('ttl_ms'), meta.get('base_rev')
            chain, expiry = meta.get('lease_id'), meta.get('original_expires_at_ms')
            if (type(p) not in (int, float) or not math.isfinite(p) or not 0 <= p <= 1
                    or frame.get('status') not in QUOTE_STATUSES or not uint(base) or not uint(ttl)):
                raise ValueError('invalid source blend')
            if (not uint(ttl) or ttl > 60000 or not uint(expiry) or not uint(issued_at_ms)
                    or expiry > issued_at_ms + ttl
                    or type(chain) is not str or not 0 < len(chain) <= 160):
                payload = json.dumps(frame, allow_nan=False, separators=(',', ':'), sort_keys=True)
                return self.command('uncached', meta['epoch'], kind, payload)
            # Encoded metadata is derived from exactly the validated object, not a
            # caller-provided payload with independently supplied ordering fields.
        elif kind == 'revoke':
            through = meta.get('through_seq')
            if not uint(through) or through >= meta['seq']:
                raise ValueError('revoke own seq must exceed through_seq')
            base, chain, expiry, issued_at_ms, ttl = 0, '', 0, 0, 0
        else:
            raise ValueError('unsupported preview kind')
        payload = json.dumps(frame, allow_nan=False, separators=(',', ':'), sort_keys=True)
        if len(payload.encode()) > 65536:
            return self.command('uncached', meta['epoch'], kind, payload)
        return self.command('offer', meta['epoch'], kind, meta['seq'], base, chain,
                            expiry, issued_at_ms, ttl, frame.get('status', ''), payload)

    def committed(self, frame):
        if type(frame) is not dict or frame.get('event_id') != self.event_id:
            raise ValueError('wrong commit scope')
        rev = frame.get('rev')
        if type(rev) is not dict or set(rev) != {str(self.event_id)} or not uint(rev[str(self.event_id)]):
            raise ValueError('singleton revision required')
        # Status is deliberately not supplied as authority. WPS revision does not order it.
        return self.command('committed', rev[str(self.event_id)],
                            json.dumps(frame, allow_nan=False, separators=(',', ':'), sort_keys=True))

    def snapshot(self, *, database_revision, database_status):
        """Caller MUST obtain both columns in a fresh authoritative SQL read.

        This validates shape, not freshness or a cross-system atomic transaction.
        """
        if not uint(database_revision) or type(database_status) is not str or not database_status:
            raise ValueError('fresh complete DB coverage required')
        return self.command('snapshot', database_revision, database_status)
