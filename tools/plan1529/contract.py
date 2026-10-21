"""#1529 plan-only binding contract: the four sealed phase-A census statements and nothing else.

PILLAR: TRUTH. SHIP: across sports, game pages put full-game winners in Game lines and
preserve player and segment questions in the correct sections. This file is the means:
it lets a separately admitted, attended run EXPLAIN the four frozen 30-day phase-A
statements of `scripts/capture_census.py --phase a --window 30` once, so Root can see
their estimated plans before deciding whether the census itself may run.

The supervisor and child beside this file are plan847's, rebound by name only (the
exact substitutions are pinned in `backend/tests/test_plan1529_binding.py`). This
contract is the only part written for #1529. It is plan847's contract with four
plans instead of two, a different subject, seal and source pin, a `WITH g AS (`
statement prefix, one shared game CTE, and its own protected-window exclusion.

Pure module. No application import, no driver import, no network, no clock writes,
no file writes. Everything a run may do is a constant here; there is no SQL, subject,
cap, window or timeout parameter anywhere in this tool.

What this contract can check: the packet bytes against the seal chain, the admission's
shape, its binding to these exact source files, its owner, its window on the local
clock, and the shape of the evidence the child returns.

What it cannot check: whether the declared prerequisite receipts (carrier identity,
source equality, quiet window, Measurement ownership) are TRUE. It records the
references and digests Root names, verbatim, as declarations. A boolean, or a name
with no digest, is refused outright, but a digest is not proof of the facts behind it.
Nor does it check that the sealed statements still equal what the census library
emits today: the contract imports no application code. That equality is a test
(`TestSourceEquality`), and a drift there retires this packet for review.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path

B = Path(__file__).resolve().parent
PACKET = B / 'packet'

SUBJECT = '1529-phase-a-census-plan-only'
MODE = 'plan_only'
DECISION = 'ROOT_ADMITTED_1529_PLAN_ONLY'
SOURCE_REF = '7e60a65a1433256b936f4600a52693c994ea408d'
SOURCE_BLOBS = {
    'backend/app/utils/capture_census.py': 'f56c31c1a5c7d08fbdca75e4adb7dd852f2a0c31',
    'backend/scripts/capture_census.py': 'd6cb6c9508afccd26614dca75a307be345d53ba7',
}
SEAL_SHA256 = 'a7774e43954754c54a0f7eefc59db26ae147aec21fc9ce713b3514660936e1c8'
MANIFEST_SHA256 = '7995facad96825ebad420860a4553e36a70c50eb916032a533efe011f59d3577'
WINDOW_DAYS = 30
# Order is execution order, which is the CLI's phase A order: games, markets, source
# split, fixture days. Stop at the first failure; all four plans or NO_RESULT.
PLANS = (
    ('games', 'games.plan-only.sql', '1bbeb6d018434eaa5ecaab58c08e3eaf2cdecb45982e9db9b764faa82be1d06f'),
    ('markets', 'markets.plan-only.sql', '8c047f4d0c97b8def47550760cfdda00e62f2f6d690809e7dada1562e005b240'),
    ('source_split', 'source_split.plan-only.sql', 'b409755755295fd7c45cbc1432dfd9b222ad097f1085d90dd5b2a297537dc2d4'),
    ('fixture_days', 'fixture_days.plan-only.sql', '53a4eae85077f76dc0b836500e541f3c12fdf10fd8adb1b74c730f5c44f7f105'),
)
BINDING_FILES = ('contract.py', 'child.py', 'supervisor.py')

LIMITS = {
    'total_seconds': 15,
    'combined_output_bytes': 524288,
    'statement_timeout': '2s',
    'lock_timeout': '500ms',
    'explain': 'FORMAT JSON',
    'analyze': False,
    'attempts': 1,
    'retry': False,
}

# The sealed envelope, line for line. The header comment is not executed.
HEADER = '-- INERT REVIEW MATERIAL: NOT ADMITTED; no caller exists for this packet.\n'
ENVELOPE = (
    'BEGIN TRANSACTION READ ONLY',
    "SET LOCAL statement_timeout = '2s'",
    "SET LOCAL lock_timeout = '500ms'",
    None,  # the EXPLAIN statement, checked below
    'ROLLBACK',
)
EXPLAIN_PREFIX = 'EXPLAIN (FORMAT JSON)\n'
# Every statement starts with this one game cohort, byte for byte: completed/closed
# events of the last 30 days joined to their sport. No sport, source, status, price or
# trade gate; no upper bound; games with no market stay in it.
GAME_CTE = (
    'WITH g AS (\n'
    '  SELECT e.id, s.key AS sport_key, e.home_team_name, e.away_team_name,\n'
    "         (e.commence_time AT TIME ZONE 'UTC')::date AS fixture_day\n"
    '  FROM events e\n'
    '  JOIN sports s ON s.id = e.sport_id\n'
    "  WHERE e.status IN ('completed', 'closed')\n"
    "    AND e.commence_time >= NOW() - INTERVAL '30 days'\n"
    ')\n'
)

# The only statement this tool adds to the sealed text: a control check that the
# database itself reports READ ONLY and the exact 2s / 500ms settings, run inside
# each sealed transaction before its EXPLAIN.
GUARD_SQL = ("SELECT current_setting('transaction_read_only'), "
             "current_setting('statement_timeout'), current_setting('lock_timeout')")
GUARD_ROW = ('on', '2s', '500ms')
# Session-level defaults on the one owned connection, before any sealed statement.
CONNECT_OPTIONS = '-c default_transaction_read_only=on -c statement_timeout=2000 -c lock_timeout=500'

# Admission window policy (local clock only; this is not overlap evidence).
MAX_WINDOW_SECONDS = 600
PREREQUISITE_MAX_AGE_SECONDS = 900
# Two hourly Heavy runs read the same tables: the accuracy rebuild
# (precompute_calibration_main, :15, 1560 s hard limit, so to :41) and the backfill
# status cache (precompute_backfill_winners_status, :35, 660 s, so to :46). A window
# touching [:14:00, :47:00) UTC of any hour is refused. The weekly calibration
# sentinel (Monday 06:20, 900 s), which runs these same four statements, falls
# inside it. Pinned against the beat schedule by TestProtectedWindow.
PRODUCER_EXCLUSION = (14 * 60, 47 * 60)
PREREQUISITES = ('main_carrier', 'heavy_carrier', 'source_equality', 'quiet_window', 'measurement_owner')
ADMISSION_KEYS = frozenset({
    'decision', 'subject', 'mode', 'admission_id', 'binding_sha256', 'seal_sha256',
    'manifest_sha256', 'source_ref', 'sql_sha256', 'limits', 'root_review_id',
    'admission_owner', 'controller_session', 'window', 'prerequisites',
})
ADMISSION_MAX_BYTES = 8192

_TOKEN = re.compile(r'[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}')
_ADMISSION_ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9._-]{7,63}')
_REF = re.compile(r'[A-Za-z0-9/][A-Za-z0-9._:/@+-]{0,255}')
_HEX64 = re.compile(r'[0-9a-f]{64}')
_FORBIDDEN_PLAN_KEYS = frozenset({'Execution Time', 'Planning Time', 'Planning', 'Triggers', 'JIT'})

# Fixed refusal codes. Nothing else is ever raised as a message.
CODES = frozenset({'PACKET_REFUSED', 'ADMISSION_REFUSED', 'BINDING_REFUSED', 'OWNER_REFUSED',
                   'WINDOW_REFUSED', 'EVIDENCE_REFUSED', 'PLAN_REFUSED', 'ANALYZE_REFUSED',
                   'ACCEPT_REFUSED', 'JSON_REFUSED'})


class Refused(ValueError):
    """Carries one fixed code from CODES; never a credential, DSN or driver text."""


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def loads(raw):
    """Strict JSON: no NaN/Infinity, no duplicate keys."""
    def constant(_):
        raise Refused('JSON_REFUSED')

    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise Refused('JSON_REFUSED')
            result[key] = value
        return result
    try:
        return json.loads(raw, parse_constant=constant, object_pairs_hook=unique)
    except Refused:
        raise
    except (ValueError, TypeError, RecursionError):
        raise Refused('JSON_REFUSED') from None


def _identity(raw: bytes) -> dict:
    return {'bytes': len(raw), 'sha256': sha256(raw)}


def packet():
    """Verify the vendored packet against the seal chain; return the executable plans.

    Returns ((name, file_sha256, (begin, set_statement, set_lock, explain, rollback)), ...).
    Every statement is an exact substring of the sealed bytes.
    """
    try:
        seal_raw = (PACKET / 'SEAL.json').read_bytes()
        manifest_raw = (PACKET / 'MANIFEST.json').read_bytes()
        if sha256(seal_raw) != SEAL_SHA256 or sha256(manifest_raw) != MANIFEST_SHA256:
            raise Refused('PACKET_REFUSED')
        seal = loads(seal_raw)
        manifest = loads(manifest_raw)
        if (seal.get('files', {}).get('MANIFEST.json') != _identity(manifest_raw)
                or seal.get('production_admitted') is not False
                or manifest.get('issue') != 1529
                or manifest.get('subject') != SUBJECT
                or manifest.get('window_days') != WINDOW_DAYS
                or manifest.get('source_ref') != SOURCE_REF
                or {path: blob.get('git_blob_sha1') for path, blob in manifest.get('blobs', {}).items()} != SOURCE_BLOBS):
            raise Refused('PACKET_REFUSED')
        plans = []
        for name, filename, digest in PLANS:
            raw = (PACKET / filename).read_bytes()
            identity = _identity(raw)
            if (identity['sha256'] != digest or seal['files'].get(filename) != identity
                    or manifest.get('files', {}).get(filename) != identity):
                raise Refused('PACKET_REFUSED')
            plans.append((name, digest, _statements(raw.decode('utf-8'))))
        return tuple(plans)
    except Refused:
        raise
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        raise Refused('PACKET_REFUSED') from None


def _statements(text: str):
    if not text.startswith(HEADER) or not text.endswith(';\n'):
        raise Refused('PACKET_REFUSED')
    parts = text[len(HEADER):].split(';\n')
    if len(parts) != len(ENVELOPE) + 1 or parts[-1] != '':
        raise Refused('PACKET_REFUSED')
    statements = tuple(parts[:-1])
    for expected, actual in zip(ENVELOPE, statements):
        if expected is not None and actual != expected:
            raise Refused('PACKET_REFUSED')
    explain = statements[3]
    if (not explain.startswith(EXPLAIN_PREFIX + GAME_CTE) or ';' in explain
            or explain.count('INTERVAL') != 1 or explain.count('WITH') != 1
            or re.search(r'\bANALY[SZ]E\b', explain, re.IGNORECASE)
            # No favorable sample: no row cap, offset or table sample anywhere.
            or re.search(r'\b(LIMIT|OFFSET|FETCH|TABLESAMPLE)\b', explain, re.IGNORECASE)
            or re.search(r'\b(INSERT|UPDATE|DELETE|MERGE|TRUNCATE|CREATE|ALTER|DROP|GRANT|COPY|CALL|DO|LOCK|FOR\s+UPDATE|FOR\s+SHARE)\b',
                         explain, re.IGNORECASE)):
        raise Refused('PACKET_REFUSED')
    return statements


def binding_sha256() -> str:
    """Digest of this tool's three executable files, in a fixed framing."""
    digest = hashlib.sha256()
    for name in BINDING_FILES:
        raw = (B / name).read_bytes()
        digest.update(name.encode() + b'\0' + str(len(raw)).encode() + b'\0' + raw)
    return digest.hexdigest()


def _is_str(value, pattern) -> bool:
    return type(value) is str and pattern.fullmatch(value) is not None


def _is_number(value) -> bool:
    return type(value) in (int, float) and math.isfinite(value)


def canonical_admission(admission):
    """Round-trip through strict JSON so only plain JSON values are judged."""
    if type(admission) is not dict:
        raise Refused('ADMISSION_REFUSED')
    try:
        raw = json.dumps(admission, allow_nan=False, sort_keys=True, separators=(',', ':')).encode()
    except (TypeError, ValueError, RecursionError):
        raise Refused('ADMISSION_REFUSED') from None
    if len(raw) > ADMISSION_MAX_BYTES:
        raise Refused('ADMISSION_REFUSED')
    return loads(raw), sha256(raw)


def admission_terms(admission, owner):
    """Every admission check that does not depend on the clock. Returns (admission, digest)."""
    admission, digest = canonical_admission(admission)
    if set(admission) != ADMISSION_KEYS:
        raise Refused('ADMISSION_REFUSED')
    if (admission['decision'] != DECISION or admission['subject'] != SUBJECT
            or admission['mode'] != MODE or admission['limits'] != LIMITS
            or admission['source_ref'] != SOURCE_REF
            or admission['seal_sha256'] != SEAL_SHA256
            or admission['manifest_sha256'] != MANIFEST_SHA256
            or admission['sql_sha256'] != {name: file_hash for name, _, file_hash in PLANS}
            or not _is_str(admission['admission_id'], _ADMISSION_ID)
            or any(not _is_str(admission[k], _TOKEN) for k in ('root_review_id', 'admission_owner', 'controller_session'))):
        raise Refused('ADMISSION_REFUSED')
    window = admission['window']
    if (type(window) is not dict or set(window) != {'start_unix', 'end_unix'}
            or not all(_is_number(window[k]) for k in window)):
        raise Refused('ADMISSION_REFUSED')
    prerequisites = admission['prerequisites']
    if type(prerequisites) is not dict or set(prerequisites) != set(PREREQUISITES):
        raise Refused('ADMISSION_REFUSED')
    for item in prerequisites.values():
        if (type(item) is not dict or set(item) != {'ref', 'sha256', 'observed_unix'}
                or not _is_str(item['ref'], _REF) or '..' in item['ref']
                or not _is_str(item['sha256'], _HEX64) or not _is_number(item['observed_unix'])):
            raise Refused('ADMISSION_REFUSED')
    if not _is_str(admission['binding_sha256'], _HEX64) or admission['binding_sha256'] != binding_sha256():
        raise Refused('BINDING_REFUSED')
    if not _is_str(owner, _TOKEN) or owner != admission['controller_session']:
        raise Refused('OWNER_REFUSED')
    return admission, digest


def _touches_producer(start: float, end: float) -> bool:
    low, high = PRODUCER_EXCLUSION
    for hour in range(int(start // 3600) - 1, int(end // 3600) + 2):
        if start < hour * 3600 + high and end > hour * 3600 + low:
            return True
    return False


def admit(admission, owner, now: float, total_seconds: float):
    """Full admission at local wall time `now`: terms, then window and freshness."""
    admission, digest = admission_terms(admission, owner)
    start, end = admission['window']['start_unix'], admission['window']['end_unix']
    if (not _is_number(now) or not start <= now or now + total_seconds > end
            or end - start > MAX_WINDOW_SECONDS or _touches_producer(start, end)):
        raise Refused('WINDOW_REFUSED')
    for item in admission['prerequisites'].values():
        if not start - PREREQUISITE_MAX_AGE_SECONDS <= item['observed_unix'] <= now:
            raise Refused('WINDOW_REFUSED')
    return admission, digest


def plan_json(value):
    if (type(value) is not list or len(value) != 1 or type(value[0]) is not dict
            or set(value[0]) != {'Plan'} or type(value[0]['Plan']) is not dict
            or type(value[0]['Plan'].get('Node Type')) is not str):
        raise Refused('PLAN_REFUSED')
    stack = [value]
    while stack:
        item = stack.pop()
        if type(item) is dict:
            for key, child in item.items():
                if key.startswith('Actual ') or key in _FORBIDDEN_PLAN_KEYS:
                    raise Refused('ANALYZE_REFUSED')
                stack.append(child)
        elif type(item) is list:
            stack.extend(item)
    return value


def records(items):
    """Validate the exact record sequence: per plan guard → plan → rollback, then complete."""
    expected = []
    for name, _, file_hash in PLANS:
        expected += [('guard', name, file_hash), ('plan', name, file_hash), ('rollback', name, file_hash)]
    if type(items) is not list or len(items) != len(expected) + 1:
        raise Refused('EVIDENCE_REFUSED')
    for (kind, name, file_hash), record in zip(expected, items):
        if type(record) is not dict:
            raise Refused('EVIDENCE_REFUSED')
        if kind == 'guard':
            ok = record == {'kind': 'guard', 'plan': name, 'row': list(GUARD_ROW)}
        elif kind == 'rollback':
            ok = record == {'kind': 'rollback', 'plan': name, 'status': 'ROLLBACK'}
        else:
            ok = (set(record) == {'kind', 'plan', 'sql_sha256', 'json'} and record['kind'] == 'plan'
                  and record['plan'] == name and record['sql_sha256'] == file_hash)
            if ok:
                plan_json(record['json'])
        if not ok:
            raise Refused('EVIDENCE_REFUSED')
    if items[-1] != {'kind': 'complete', 'mode': MODE, 'owned_connection_closed': True}:
        raise Refused('EVIDENCE_REFUSED')
    return items


def evidence(raw: bytes):
    """Parse the child's complete stdout. Partial, truncated or extra lines are refused."""
    if type(raw) is not bytes or not raw.endswith(b'\n') or b'\r' in raw:
        raise Refused('EVIDENCE_REFUSED')
    return records([loads(line) for line in raw[:-1].split(b'\n')])


def accept(owner_result, receipt_bytes: bytes):
    """The only way to read plans out of an attempt.

    Requires the owner's own timely return (never the disk receipt alone), a
    candidate digest that matches the receipt bytes exactly, and a receipt whose
    evidence still validates. Returns {'games', 'markets', 'source_split', 'fixture_days'} -> plan_json.
    """
    if (type(owner_result) is not dict or owner_result.get('owner_completed') is not True
            or owner_result.get('verdict') != 'PLAN_ONLY_PENDING_ROOT_REVIEW'
            or not _is_number(owner_result.get('elapsed_seconds'))
            or not 0 <= owner_result['elapsed_seconds'] <= LIMITS['total_seconds']
            or type(receipt_bytes) is not bytes or not receipt_bytes.endswith(b'\n')
            or owner_result.get('candidate_sha256') != sha256(receipt_bytes)):
        raise Refused('ACCEPT_REFUSED')
    receipt = loads(receipt_bytes)
    if (type(receipt) is not dict or receipt.get('verdict') != 'NO_RESULT'
            or receipt.get('reason') != 'OWNER_CONFIRMATION_REQUIRED'
            or receipt.get('subject') != SUBJECT or receipt.get('seal_sha256') != SEAL_SHA256
            or receipt.get('admission_id') != owner_result.get('admission_id')
            or receipt.get('binding_sha256') != binding_sha256()):
        raise Refused('ACCEPT_REFUSED')
    items = records(receipt.get('candidate_evidence'))
    return {item['plan']: item['json'] for item in items if item['kind'] == 'plan'}
