#!/usr/bin/env python3
"""#847 native plan-only child. Launched only by supervisor.py; never by hand.

Reads ONE bounded JSON request on stdin: {credential, admission, owner}. The
credential never appears in argv, environment, stdout, stderr or any file.
Re-verifies the packet and the clock-free admission terms, and only then imports
the installed psycopg2 and opens ONE connection. Per sealed plan: BEGIN READ ONLY,
the two SET LOCALs, the guard check, the EXPLAIN, ROLLBACK. The first error stops
everything; the second plan never starts after a failed first.

The parent owns the wall and the output ledger. libpq buffers each result in full
before this process sees it, so the parent's byte ledger bounds what is serialized,
not the driver's internal or wire buffers.
"""
import importlib.util
import json
import os
import select
import signal
import sys
from pathlib import Path

B = Path(__file__).resolve().parent
INPUT_CAP = 16384
RECORD_CAP = 524288
OWNED = None


def _contract():
    spec = importlib.util.spec_from_file_location('plan847_contract', B / 'contract.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def emit(record):
    raw = (json.dumps(record, separators=(',', ':'), allow_nan=False, ensure_ascii=True) + '\n').encode('ascii')
    if len(raw) > RECORD_CAP:
        raise ValueError('RECORD_REFUSED')
    sys.stdout.buffer.write(raw)
    sys.stdout.buffer.flush()


def wait_ready(conn, extensions):
    # No timeout here: the parent's single wall is the bound, and it ends this process.
    while True:
        state = conn.poll()
        if state == extensions.POLL_OK:
            return
        if state == extensions.POLL_READ:
            select.select([conn.fileno()], [], [])
        elif state == extensions.POLL_WRITE:
            select.select([], [conn.fileno()], [])
        else:
            raise RuntimeError('POLL_REFUSED')


def collect(request):
    global OWNED
    contract = _contract()
    plans = contract.packet()
    contract.admission_terms(request['admission'], request['owner'])
    credential = request['credential']
    if type(credential) is not str or not credential or '\0' in credential or len(credential.encode()) > 12000:
        raise ValueError('INPUT_REFUSED')
    import psycopg2
    from psycopg2 import extensions
    OWNED = psycopg2.connect(credential, async_=True, connect_timeout=2, sslmode='require',
                             options=contract.CONNECT_OPTIONS)
    try:
        wait_ready(OWNED, extensions)
        cur = OWNED.cursor()

        def run(sql):
            cur.execute(sql)
            wait_ready(OWNED, extensions)

        for name, file_hash, (begin, set_statement, set_lock, explain, rollback) in plans:
            run(begin)
            run(set_statement)
            run(set_lock)
            run(contract.GUARD_SQL)
            if cur.fetchall() != [contract.GUARD_ROW]:
                raise RuntimeError('GUARD_REFUSED')
            emit({'kind': 'guard', 'plan': name, 'row': list(contract.GUARD_ROW)})
            run(explain)
            rows = cur.fetchall()
            if len(rows) != 1 or len(rows[0]) != 1:
                raise RuntimeError('PLAN_REFUSED')
            emit({'kind': 'plan', 'plan': name, 'sql_sha256': file_hash,
                  'json': contract.plan_json(rows[0][0])})
            run(rollback)
            if cur.statusmessage != 'ROLLBACK':
                raise RuntimeError('ROLLBACK_REFUSED')
            emit({'kind': 'rollback', 'plan': name, 'status': 'ROLLBACK'})
    finally:
        OWNED.close()
        if not OWNED.closed:
            raise RuntimeError('CLOSE_REFUSED')
    emit({'kind': 'complete', 'mode': contract.MODE, 'owned_connection_closed': True})


def close_owned(signum, frame):
    # Close only this process's own connection; no cancel(), no backend-PID SQL.
    try:
        if OWNED is not None:
            OWNED.close()
    finally:
        os._exit(125)


def main():
    signal.signal(signal.SIGTERM, close_owned)
    signal.signal(signal.SIGINT, close_owned)
    try:
        if len(sys.argv) != 1:
            raise ValueError('ARGS_REFUSED')
        payload = sys.stdin.buffer.read(INPUT_CAP + 1)
        if len(payload) > INPUT_CAP:
            raise ValueError('INPUT_REFUSED')
        request = _contract().loads(payload)
        if type(request) is not dict or set(request) != {'credential', 'admission', 'owner'}:
            raise ValueError('INPUT_REFUSED')
        collect(request)
    except BaseException:
        # Never stringify an exception, print a traceback, a DSN or driver text.
        try:
            emit({'kind': 'refusal', 'reason': 'CHILD_REFUSED'})
        finally:
            os._exit(1)
    os._exit(0)


if __name__ == '__main__':
    main()
