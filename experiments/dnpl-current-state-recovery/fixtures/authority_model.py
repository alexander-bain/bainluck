"""TEST ONLY: linearizable retained preview authority, not a production Redis client.

The publisher supplies the ORIGINAL producer-chain deadline. Storage acceptance,
owner epoch and snapshot are atomic only in this in-memory model. A production
implementation needs the same fenced atomic write/read contract, not GET+SET.
"""
from copy import deepcopy
import math


def integer(value):
    return type(value) is int and 0 <= value <= 9007199254740991


class CurrentPreviewStore:
    def __init__(self, clock_ms, max_clock_skew_ms=250, capacity=128):
        self.clock_ms = clock_ms
        self.max_clock_skew_ms = max_clock_skew_ms
        self.capacity = capacity
        self.owner_epoch = None
        self.epoch_floor = -1
        self.records = {}
        self.committed = {}
        self.status = {}
        self.log = []

    def claim_epoch(self, epoch):
        if epoch is None:
            self.owner_epoch = None
            self.records.clear()
            self.log.append({'kind': 'owner_missing', 'at': self.clock_ms()})
            return True
        if (not integer(epoch) or epoch < self.epoch_floor
                or (epoch == self.epoch_floor and self.owner_epoch is None)):
            return False
        if epoch > self.epoch_floor:
            self.records.clear()
        self.epoch_floor = epoch
        self.owner_epoch = epoch
        self.log.append({'kind': 'owner', 'epoch': epoch, 'at': self.clock_ms()})
        return True

    def commit(self, event_id, revision, status='live'):
        if not integer(event_id) or not integer(revision):
            return False
        if revision < self.committed.get(event_id, -1):
            return False
        if revision == self.committed.get(event_id) and status != self.status.get(event_id):
            self.status[event_id] = 'unknown'  # equal-version conflict is abstention
            return False
        self.committed[event_id] = revision
        self.status[event_id] = status
        self.log.append({'kind': 'commit_floor', 'event_id': event_id,
                         'revision': self.committed[event_id], 'at': self.clock_ms()})
        return True

    def publish(self, frame, issued_at_ms, expires_at_ms=None):
        eid = frame.get('event_id')
        meta = frame.get('preview', {})
        epoch, seq = meta.get('epoch'), meta.get('seq')
        if (not integer(eid) or not integer(epoch) or not integer(seq)
                or epoch != self.owner_epoch or 'rev' in frame
                or frame.get('provisional') is not True):
            return False
        prior = self.records.get(eid)
        if prior is not None and seq <= prior['seq']:
            return False  # equal offers cannot renew any deadline
        kind = meta.get('kind')
        if kind == 'blend':
            ttl, base = meta.get('ttl_ms'), meta.get('base_rev')
            p = frame.get('p')
            if (not integer(ttl) or not integer(base) or type(p) not in (int, float)
                    or not math.isfinite(p) or not 0 <= p <= 1
                    or frame.get('status') not in ('live', 'scheduled', 'suspended')
                    or not isinstance(expires_at_ms, (int, float))
                    or not math.isfinite(expires_at_ms)
                    or not isinstance(issued_at_ms, (int, float))
                    or not math.isfinite(issued_at_ms)
                    or issued_at_ms > self.clock_ms() + self.max_clock_skew_ms
                    or expires_at_ms > issued_at_ms + ttl + 1):
                return False
        elif kind == 'revoke':
            if not integer(meta.get('through_seq')) or meta['through_seq'] >= seq:
                return False
            expires_at_ms = None
        else:
            return False
        if eid not in self.records and len(self.records) >= self.capacity:
            # Never evict the ordering watermark and thereby admit an old offer.
            # Bounded model refuses new scopes when full; no production sizing claim.
            return False
        self.records[eid] = {'epoch': epoch, 'seq': seq, 'frame': deepcopy(frame),
                             'issued_at_ms': issued_at_ms, 'expires_at_ms': expires_at_ms}
        self.log.append({'kind': 'store', 'event_id': eid, 'epoch': epoch, 'seq': seq,
                         'expires_at_ms': expires_at_ms, 'at': self.clock_ms()})
        return True

    def snapshot(self, event_id):
        now = self.clock_ms()
        rec = self.records.get(event_id)
        out = {'event_id': event_id, 'owner_epoch': self.owner_epoch,
               'committed_floor': self.committed.get(event_id, 0),
               'status': self.status.get(event_id, 'live'), 'read_at_ms': now,
               'seq_floor': rec['seq'] if rec else None, 'frame': None,
               'lease_id': f"{event_id}:{rec['epoch']}:{rec['expires_at_ms']}" if rec and rec['expires_at_ms'] is not None else None,
               'lease_remaining_ms': max(0, int(rec['expires_at_ms'] - now)) if rec and rec['expires_at_ms'] is not None else 0}
        if rec is None or rec['epoch'] != self.owner_epoch:
            out['reason'] = 'cold_or_owner_missing'
        elif rec['frame']['preview']['kind'] == 'revoke':
            out['reason'] = 'revoked'
            out['frame'] = deepcopy(rec['frame'])
        elif (out['status'] not in ('live', 'scheduled', 'suspended')
              or rec['frame'].get('status') != out['status']):
            out['reason'] = 'terminal'
        elif rec['frame']['preview']['base_rev'] < out['committed_floor']:
            out['reason'] = 'newer_commit'
        elif rec['expires_at_ms'] - now <= self.max_clock_skew_ms:
            out['reason'] = 'expired_or_uncertain'
        else:
            out['reason'] = 'valid'
            frame = deepcopy(rec['frame'])
            frame['preview'].update({
                'ttl_ms': max(0, int(rec['expires_at_ms'] - now)),
                'lease_id': f"{event_id}:{rec['epoch']}:{rec['expires_at_ms']}",
                'original_expires_at_ms': rec['expires_at_ms'],
                'recovery_emitted_at_ms': now,
                'clock_uncertainty_ms': self.max_clock_skew_ms,
            })
            out['frame'] = frame
        self.log.append({'kind': 'snapshot', 'event_id': event_id, 'reason': out['reason'],
                         'seq_floor': out['seq_floor'], 'at': now})
        return out


class PreviewGate:
    def __init__(self, store, event_id):
        self.store, self.event_id = store, event_id
        self.watermark = (-1, -1)
        self.ready = False

    def recover(self):
        self.ready = True
        return self._take(self.store.snapshot(self.event_id))

    def recover_snapshot(self):
        self.ready = True
        snapshot = self.store.snapshot(self.event_id)
        self._take(snapshot)
        return snapshot

    def live(self, frame):
        if frame.get('event_id') != self.event_id:
            return None
        meta = frame.get('preview', {})
        epoch, seq = meta.get('epoch'), meta.get('seq')
        if not integer(epoch) or not integer(seq):
            return None
        if meta.get('kind') == 'revoke':
            # Source permits a superseded writer's revoke. It can withdraw its
            # own already-held epoch, but never a newer epoch seen by this gate.
            if not integer(meta.get('through_seq')) or meta['through_seq'] >= seq:
                return None
            self.watermark = max(self.watermark, (epoch, seq))
            return deepcopy(frame)
        if (epoch, seq) <= self.watermark:
            return None
        if epoch != self.store.owner_epoch:
            return None
        rec = self.store.records.get(self.event_id)
        if rec is not None and rec['epoch'] == epoch and rec['seq'] > seq:
            return None
        if rec is not None and rec['epoch'] == epoch and rec['seq'] == seq:
            return self._take(self.store.snapshot(self.event_id))
        # Retention failure must not suppress independently accepted live data.
        # Candidate publisher supplies original deadline on the live payload too.
        now = self.store.clock_ms()
        deadline = meta.get('original_expires_at_ms')
        if (meta.get('kind') != 'blend' or not isinstance(deadline, (int, float))
                or not math.isfinite(deadline) or deadline - now <= self.store.max_clock_skew_ms
                or not integer(meta.get('base_rev'))
                or meta['base_rev'] < self.store.committed.get(self.event_id, 0)
                or frame.get('status') != self.store.status.get(self.event_id, 'live')):
            return None
        value = deepcopy(frame)
        value['preview'].update({'ttl_ms': max(0, int(deadline - now)),
            'recovery_emitted_at_ms': now, 'clock_uncertainty_ms': self.store.max_clock_skew_ms,
            'lease_id': f"{self.event_id}:{epoch}:{deadline}"})
        self.watermark = (epoch, seq)
        return value

    def _take(self, snapshot):
        key = (snapshot['owner_epoch'] if snapshot['owner_epoch'] is not None else -1,
               snapshot['seq_floor'] if snapshot['seq_floor'] is not None else -1)
        if key <= self.watermark:
            return None
        self.watermark = key  # includes revoke/expired/commit-invalidated watermarks
        return snapshot['frame']
