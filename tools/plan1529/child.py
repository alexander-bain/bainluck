#!/usr/bin/env python3
"""#1529 native plan-only child. Launched only by supervisor.py; never by hand.

Reads ONE bounded JSON request on stdin: {credential, admission, owner}. The
credential never appears in argv, environment, stdout, stderr or any file.
Re-verifies the packet and the clock-free admission terms, and only then imports
the installed psycopg2 and opens ONE connection. Per sealed plan: BEGIN READ ONLY,
the two SET LOCALs, the guard check, the EXPLAIN, ROLLBACK. The first error stops
everything; no later plan starts after a failed one.

The parent owns the wall and the output ledger, and hands this process its share of
the ledger as `output_budget` in the request. Everything this process serializes to
its parent counts against that ONE budget and is checked BEFORE the write, so a byte
left unread in a pipe was still inside it: every stdout record, the refusal record
(its size is held back from the start), and every byte anything writes to fd 2 from
this file's first statement on. fd 2 is re-pointed at a private pipe that is drained
and forwarded within the budget at each record and before exit. libpq buffers each
result in full before this process sees it; that driver memory and wire traffic is
not serialized output and is not what the budget bounds.
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
OUTPUT_CAP = 524288
REQUEST_KEYS = {'credential', 'admission', 'owner', 'output_budget'}
REFUSAL = b'{"kind":"refusal","reason":"CHILD_REFUSED"}\n'
OWNED = None
# Until the request names a budget, only the refusal record may be written.
BUDGET = len(REFUSAL)
SPENT = 0
ERR_IN = REAL_ERR = None


def _contract():
    spec = importlib.util.spec_from_file_location('plan1529_contract', B / 'contract.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def spend(n):
    """Charge n bytes BEFORE writing them; the refusal record's size is never spendable."""
    global SPENT
    if SPENT + n > BUDGET - len(REFUSAL):
        raise ValueError('OUTPUT_REFUSED')
    SPENT += n


def own_stderr():
    """Point fd 2 at a private pipe, so no stderr byte reaches the parent unbudgeted."""
    global ERR_IN, REAL_ERR
    REAL_ERR = os.dup(2)
    r, w = os.pipe()
    os.dup2(w, 2)
    os.close(w)
    os.set_blocking(r, False)
    ERR_IN = r


def forward_stderr():
    # Anything written to fd 2 since the last check (Python warnings, the driver).
    # A writer that fills the private pipe between checks blocks; the parent's wall ends it.
    if ERR_IN is None:
        return
    sys.stderr.flush()  # a partial line held in Python's own buffer is fd 2 output too
    while True:
        try:
            raw = os.read(ERR_IN, 4096)
        except BlockingIOError:
            return
        if not raw:
            return
        spend(len(raw))
        view = memoryview(raw)
        while view:
            view = view[os.write(REAL_ERR, view):]


def emit(record):
    raw = (json.dumps(record, separators=(',', ':'), allow_nan=False, ensure_ascii=True) + '\n').encode('ascii')
    forward_stderr()
    spend(len(raw))
    sys.stdout.buffer.write(raw)
    sys.stdout.buffer.flush()


def refuse():
    # Fits by construction: its size was held back from every budget.
    if SPENT + len(REFUSAL) <= BUDGET:
        sys.stdout.buffer.write(REFUSAL)
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
    global BUDGET
    signal.signal(signal.SIGTERM, close_owned)
    signal.signal(signal.SIGINT, close_owned)
    try:
        own_stderr()
        if len(sys.argv) != 1:
            raise ValueError('ARGS_REFUSED')
        payload = sys.stdin.buffer.read(INPUT_CAP + 1)
        if len(payload) > INPUT_CAP:
            raise ValueError('INPUT_REFUSED')
        request = _contract().loads(payload)
        if type(request) is not dict or set(request) != REQUEST_KEYS:
            raise ValueError('INPUT_REFUSED')
        budget = request['output_budget']
        if type(budget) is not int or not len(REFUSAL) <= budget <= OUTPUT_CAP:
            raise ValueError('INPUT_REFUSED')
        BUDGET = budget
        collect(request)
        forward_stderr()
    except BaseException:
        # Never stringify an exception, print a traceback, a DSN or driver text.
        try:
            forward_stderr()
        except BaseException:
            pass
        try:
            refuse()
        finally:
            os._exit(1)
    os._exit(0)


if __name__ == '__main__':
    main()
