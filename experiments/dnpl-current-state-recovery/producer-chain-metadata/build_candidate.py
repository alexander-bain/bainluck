"""Create an isolated, exact-seam prototype; never edits the source checkout."""
from pathlib import Path
import difflib
ROOT=Path(__file__).resolve().parent
src=ROOT/'reference/backend/app/utils/blend_preview.py'
s=src.read_text()
def replace(old,new):
 global s
 assert s.count(old)==1, old[:100]
 s=s.replace(old,new)
replace('@dataclass\nclass _Pending:', '''@dataclass(frozen=True)
class _ChainLease:
    # TEST-ONLY additive protocol metadata, never a new observation clock.
    identity: int
    original_expires_at_ms: Optional[int]


@dataclass
class _Pending:''')
replace('    since: float\n','    since: float\n    lease: _ChainLease\n')
replace('        clock: Callable[[], float] = time.monotonic,\n','        clock: Callable[[], float] = time.monotonic,\n        wall_clock: Callable[[], float] = time.time,\n')
replace('        self._clock = clock\n','        self._clock = clock\n        self._wall_clock = wall_clock\n        self._chain_identity = itertools.count(1)\n')
replace('    # ── state ────────────────────────────────────────────────────────────\n', '''    def _new_chain_lease(self, since: float) -> _ChainLease:
        identity = next(self._chain_identity)
        try:
            # Anchor once. Sampling monotonic AFTER wall time conservatively
            # charges time spent obtaining the pair. Server clock alignment is
            # still a protocol prerequisite, not established by this adapter.
            wall = self._wall_clock()
            after = self._clock()
            remaining = self.max_uncommitted_s - (after - since)
            expiry = math.floor(wall * 1000 + remaining * 1000) - 1
            if not (0 <= expiry <= 2**53 - 1) or after < since:
                expiry = None
        except Exception:
            expiry = None
        return _ChainLease(identity, expiry)

    def _chain_metadata(self, event_id: int, state: _EventState) -> dict:
        try:
            # Mirrors the producer's oldest-pending-since lease. A changed
            # probability, observation, seq or base is NOT a new chain.
            _, oldest = min(state.pending.items(), key=lambda item: (item[1].since, item[0]))
            expiry = oldest.lease.original_expires_at_ms
            issued = math.floor(self._wall_clock() * 1000)
            if expiry is None or not (0 <= issued <= 2**53 - 1):
                return {}
            return {"lease_id": "pending:" + str(oldest.lease.identity),
                    "original_expires_at_ms": expiry,
                    "lease_issued_at_ms": issued}
        except Exception:
            # Optional metadata must never suppress an independently accepted
            # live preview. Absence means live-only, not reconstructed expiry.
            return {}

    # ── state ────────────────────────────────────────────────────────────
''')
replace('                "ttl_ms": ttl_ms,\n','                "ttl_ms": ttl_ms,\n                **self._chain_metadata(event_id, state),\n')
replace('            seq=0, since=prior.since if prior is not None else now,\n','            seq=0, since=prior.since if prior is not None else now,\n            lease=prior.lease if prior is not None else self._new_chain_lease(now),\n')
out=ROOT/'candidate/backend/app/utils/blend_preview.py';out.parent.mkdir(parents=True,exist_ok=True);out.write_text(s)
(ROOT/'producer-chain.patch').write_text(''.join(difflib.unified_diff(src.read_text().splitlines(True),s.splitlines(True),fromfile='a/backend/app/utils/blend_preview.py',tofile='b/backend/app/utils/blend_preview.py',n=0)))
print(out)
