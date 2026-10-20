"""#847 plan-only binding contract: the sealed query3 / candidate C pair and nothing else.

PILLAR: TRUTH. SHIP: operators see the full stored guess-family count without losing
the winner-coverage cache to an unreviewed expensive query. This file is the means:
it lets a separately admitted, attended run EXPLAIN the two frozen statements once.

Pure module. No application import, no driver import, no network, no clock writes,
no file writes. Everything a run may do is a constant here; there is no SQL, subject,
cap or timeout parameter anywhere in this tool.

What this contract can check: the packet bytes against the seal chain, the admission's
shape, its binding to these exact source files, its owner, its window on the local
clock, and the shape of the evidence the child returns.

What it cannot check: whether the declared prerequisite receipts (carrier identity,
source equality, quiet window, Measurement ownership) are TRUE. It records the
references and digests Root names, verbatim, as declarations. A boolean, or a name
with no digest, is refused outright, but a digest is not proof of the facts behind it.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path

B = Path(__file__).resolve().parent
PACKET = B / 'packet'

SUBJECT = '847-query3-candidateC-plan-only'
MODE = 'plan_only'
DECISION = 'ROOT_ADMITTED_847_PLAN_ONLY'
SOURCE_REF = '0c544ac15d1eb9a0dbee8e81ff1e0062ea9576f4'
SOURCE_BLOBS = {
    'backend/app/tasks/precompute_backfill_winners_status.py': 'ed6a7a112258bce25910b36b7799b770f291f5d8',
    'backend/app/utils/resolution_authority.py': 'e0ce5f93e97a7000335744b8fc944ed19d875265',
}
SEAL_SHA256 = 'f3f2f3fdce4234203c33923fb992d6aa371cf5c00812a57b602629eb3e6657f8'
MANIFEST_SHA256 = '34d0e506522f791378bb387456c9f403a2d25998ab4a286f77178d2ad13eaf5c'
# Order is execution order: query3 first, candidate C second, stop at the first failure.
PLANS = (
    ('query3', 'query3.plan-only.sql', 'bd54471ec2279ae71bfb358efbf7fadd11586cd0dd1265619d0786393cb2fc72'),
    ('candidateC', 'candidateC.plan-only.sql', '7d5f57e5c0685fc1e62505215dc3d98af674f5ad1bb2f69e4d71b98be4095a1a'),
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
EXPLAIN_PREFIX = 'EXPLAIN (FORMAT JSON)\nSELECT\n'

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
# The pinned producer runs hourly at :35 on Heavy with a 660 s hard limit. A window
# touching [:34:00, :47:00) UTC of any hour is refused.
PRODUCER_EXCLUSION = (34 * 60, 47 * 60)
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
                or manifest.get('issue') != 847
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
    if (not explain.startswith(EXPLAIN_PREFIX) or ';' in explain
            or re.search(r'\bANALY[SZ]E\b', explain, re.IGNORECASE)
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
    evidence still validates. Returns {'query3': plan_json, 'candidateC': plan_json}.
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
