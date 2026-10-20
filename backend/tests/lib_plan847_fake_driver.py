"""A fake `psycopg2` for the #847 plan-only binding tests. Never a production test mode.

The tests launch the REAL `tools/plan847/child.py` through a generated launcher that
installs this module as `psycopg2` first. The child cannot tell; the supervisor's
production argv never reaches this file.

Behaviour is a dict baked into the launcher. Statement kinds: begin, set_statement,
set_lock, guard, explain_query3, explain_candidateC, rollback; plus connect and close.
Per kind, an action list indexed by occurrence (0 = first time), each action may:
  bump     add N seconds to the shared virtual clock file (the supervisor's `_now`)
  stall    sleep forever (after any bump)
  raise    raise an error whose text CONTAINS the DSN (a leak the child must swallow)
  plan     replace the plan JSON; plan_pad: pad the plan with N bytes of text
  row      replace the guard row;  status: replace the cursor status message
  truncate write half a record to stdout and exit 0
  stderr   write text to stderr
  flood    write N bytes straight to fd 1 in 512-byte (atomic) writes, bypassing the
           child's records: what a library writing to stdout would do
  stderr_flood  write N bytes to fd 2: the first 4096, then any bump, then the rest
The log records events as JSON lines and stores only a SHA-256 of the DSN.
"""
import hashlib
import json
import os
import sys
import time
import types

POLL_OK, POLL_READ, POLL_WRITE = 0, 1, 2
_STATE = {}


def _log(event):
    with open(_STATE['log'], 'a') as f:
        f.write(json.dumps(event) + '\n')


def bump(seconds):
    path = _STATE['clock']
    current = float(open(path).read() or 0)
    tmp = path + '.tmp%d' % os.getpid()
    with open(tmp, 'w') as f:
        f.write(repr(current + seconds))
    os.replace(tmp, path)


def _kind(sql):
    if sql == 'BEGIN TRANSACTION READ ONLY':
        return 'begin'
    if sql.startswith('SET LOCAL statement_timeout'):
        return 'set_statement'
    if sql.startswith('SET LOCAL lock_timeout'):
        return 'set_lock'
    if sql.startswith("SELECT current_setting('transaction_read_only')"):
        return 'guard'
    if sql.startswith('EXPLAIN'):
        return 'explain_candidateC' if 'guess_family_outcomes' in sql else 'explain_query3'
    if sql == 'ROLLBACK':
        return 'rollback'
    return 'UNEXPECTED'


def _action(kind):
    seen = _STATE['seen']
    n = seen.get(kind, 0)
    seen[kind] = n + 1
    actions = _STATE['behavior'].get(kind, [])
    action = actions[n] if n < len(actions) else {}
    if action.get('stderr'):
        sys.stderr.write(action['stderr'])
        sys.stderr.flush()
    if action.get('stderr_flood'):
        n = action['stderr_flood']
        _log({'event': 'stderr_flood', 'kind': kind, 'bytes': n})
        os.write(2, b'e' * 4096)
        if action.get('bump'):
            bump(action['bump'])
        rest = memoryview(b'e' * (n - 4096))
        while rest:
            rest = rest[os.write(2, rest):]
    elif action.get('bump'):
        bump(action['bump'])
    if action.get('flood'):
        for _ in range(action['flood'] // 512):
            os.write(1, b'#' * 512)
    if action.get('stall'):
        _log({'event': 'stall', 'kind': kind})
        while True:
            time.sleep(3600)
    if action.get('raise'):
        raise RuntimeError('driver failure for %s' % _STATE['dsn'])
    if action.get('truncate'):
        sys.stdout.write('{"kind":"plan","plan":"cand')
        sys.stdout.flush()
        os._exit(0)
    return action


def _plan(action, name):
    if 'plan' in action:
        return action['plan']
    plan = [{'Plan': {'Node Type': 'Aggregate', 'Strategy': 'Plain', 'Total Cost': 1.0,
                      'Plan Rows': 1, 'Plans': [{'Node Type': 'Hash Join', 'Total Cost': 0.5}]}}]
    if action.get('plan_pad'):
        plan[0]['Plan']['Output'] = ['x' * action['plan_pad']]
    return plan


class Cursor:
    def __init__(self):
        self.statusmessage = None
        self._rows = None

    def execute(self, sql, binds=None):
        kind = _kind(sql)
        _log({'event': 'execute', 'kind': kind, 'sql_sha256': hashlib.sha256(sql.encode()).hexdigest()})
        action = _action(kind)
        if kind == 'guard':
            self._rows = [tuple(action.get('row', ('on', '2s', '500ms')))]
            self.statusmessage = 'SELECT 1'
        elif kind.startswith('explain'):
            self._rows = [(_plan(action, kind),)]
            self.statusmessage = 'EXPLAIN'
        else:
            self._rows = None
            self.statusmessage = action.get('status', {'begin': 'BEGIN', 'rollback': 'ROLLBACK'}.get(kind, 'SET'))

    def fetchall(self):
        return self._rows


class Connection:
    def __init__(self):
        self.closed = 0

    def poll(self):
        return POLL_OK

    def fileno(self):
        return 0

    def cursor(self):
        return Cursor()

    def close(self):
        _log({'event': 'close'})
        action = _action('close')
        self.closed = action.get('closed', 1)


def connect(dsn, **kwargs):
    _STATE['dsn'] = dsn
    _log({'event': 'connect', 'kwargs': kwargs, 'dsn_sha256': hashlib.sha256(dsn.encode()).hexdigest()})
    _action('connect')
    return Connection()


def meter(log, prestart=0):
    """Count what the child's writes COMPLETE into its parent's two pipes.

    Installed by the launcher before child.py runs. Records go through sys.stdout.buffer
    and are logged only after the real write and flush return; raw fd writes are matched
    to the parent's pipes by inode, so a write into the child's private fd 2 pipe is not
    a write to the parent and is never counted. An `_attempt` event precedes each write,
    so a write cut off by a signal is bracketed. `prestart` bytes go to the parent's
    stderr before child.py starts, as interpreter start-up diagnostics would.
    """
    targets = {os.fstat(1).st_ino: 'stdout', os.fstat(2).st_ino: 'stderr'}

    def note(event, n):
        with open(log, 'a') as f:
            f.write(json.dumps({'event': event, 'bytes': n}) + '\n')

    real_out = sys.stdout.buffer
    real_write = os.write

    class Meter:
        def write(self, raw):
            note('stdout_write_attempt', len(raw))
            n = real_out.write(raw)
            real_out.flush()
            note('stdout_write_complete', n)
            return n

        def flush(self):
            return real_out.flush()

    class Out:
        buffer = Meter()

    def write(fd, data):
        target = targets.get(os.fstat(fd).st_ino)
        if target:
            note(target + '_write_attempt', len(data))
        n = real_write(fd, data)
        if target:
            note(target + '_write_complete', n)
        return n

    sys.stdout = Out()
    os.write = write
    if prestart:
        write(2, b'p' * prestart)


def install(behavior, log, clock):
    _STATE.update(behavior=behavior, log=log, clock=clock, seen={})
    _log({'event': 'launch', 'argv': list(sys.argv), 'orig_argv': list(getattr(sys, 'orig_argv', [])), 'env_keys': sorted(os.environ), 'pid': os.getpid()})
    extensions = types.ModuleType('psycopg2.extensions')
    extensions.POLL_OK, extensions.POLL_READ, extensions.POLL_WRITE = POLL_OK, POLL_READ, POLL_WRITE
    module = types.ModuleType('psycopg2')
    module.connect = connect
    module.extensions = extensions
    sys.modules['psycopg2'] = module
    sys.modules['psycopg2.extensions'] = extensions
