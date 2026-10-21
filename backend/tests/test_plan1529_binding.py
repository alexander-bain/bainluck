"""#1529 plan-only binding (`tools/plan1529/`): the four sealed phase-A census statements, once.

PILLAR: TRUTH. SHIP: across sports, game pages put full-game winners in Game lines and
preserve player and segment questions in the correct sections. These tests are the
offline gate of the tool that would, under a separate attended admission, EXPLAIN the
four frozen 30-day statements of `scripts/capture_census.py --phase a`. Nothing here
touches a network or a database.

The supervisor and child are plan847's, rebound by name (TestMechanismIsPlan847), so
the whole of `test_plan847_binding.py` speaks for their mechanics. The end-to-end tests
here re-prove the parts the subject changes: four plans instead of two, the order, the
one wall and one ledger across all four, first-failure stop at each plan, and the
real 15 s wall, against the real supervisor/worker/child with plan847's fake driver.
"""
from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

from app.utils import capture_census as cc

TESTS = Path(__file__).resolve().parent
REPO = TESTS.parents[1]
TOOL = REPO / 'tools' / 'plan1529'
PLAN847 = REPO / 'tools' / 'plan847'
LEAK_MARKER = 'plan1529-leak-marker-not-a-password'
DSN = f'postgresql://reader:{LEAK_MARKER}@db.invalid:5432/fake'


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


contract = _load('plan1529_contract', TOOL / 'contract.py')
supervisor = _load('plan1529_supervisor', TOOL / 'supervisor.py')
assert supervisor.contract is contract
PRODUCTION_ARGV = supervisor._child_argv

# A fixed wall time at :50:00 UTC of some hour, clear of the :14-:47 exclusion.
HOUR = 1_792_000_000 - (1_792_000_000 % 3600)
BASE = HOUR + 50 * 60
OWNER = 'measurement-ctl-1529'
AID = 'adm-1529-test-0001'
NAMES = ['games', 'markets', 'source_split', 'fixture_days']
LIBRARY = {'games': cc.games_sql, 'markets': cc.market_rows_sql,
           'source_split': cc.source_split_sql, 'fixture_days': cc.fixture_days_sql}


def admission(**overrides):
    value = dict(
        decision=contract.DECISION, subject=contract.SUBJECT, mode='plan_only',
        admission_id=AID, binding_sha256=contract.binding_sha256(),
        seal_sha256=contract.SEAL_SHA256, manifest_sha256=contract.MANIFEST_SHA256,
        source_ref=contract.SOURCE_REF,
        sql_sha256={name: digest for name, _, digest in contract.PLANS},
        limits=dict(contract.LIMITS), root_review_id='root-review-1529-test',
        admission_owner='calibration-goal-root', controller_session=OWNER,
        window={'start_unix': BASE - 30, 'end_unix': BASE + 300},
        prerequisites={k: {'ref': f'artifacts/fake-1529/{k}.json', 'sha256': 'ab' * 32,
                           'observed_unix': BASE - 60} for k in contract.PREREQUISITES},
    )
    value.update(overrides)
    return value


# ─── the mechanism is plan847's, unchanged ───────────────────────────────────

# The ONLY differences allowed between plan847's mechanics files and these: applied in
# order to plan847's bytes, each with its exact occurrence count.
REBIND = {
    'supervisor.py': [('plan847', 'plan1529', 9), ('#847', '#1529', 2),
                      ('re-bound to #1529):', 're-bound to #847, then rebound unchanged to #1529):', 1),
                      ('connect, both plans, cleanup', 'connect, every plan, cleanup', 1)],
    'child.py': [('plan847', 'plan1529', 1), ('#847', '#1529', 1),
                 ('the second plan never starts after a failed first', 'no later plan starts after a failed one', 1)],
}


class TestMechanismIsPlan847:
    @pytest.mark.parametrize('name', sorted(REBIND))
    def test_the_file_is_plan847s_with_only_the_pinned_name_substitutions(self, name):
        text = (PLAN847 / name).read_text()
        for old, new, count in REBIND[name]:
            assert text.count(old) == count, (name, old)
            text = text.replace(old, new)
        assert (TOOL / name).read_text() == text, (
            f'tools/plan1529/{name} differs from plan847 beyond the name rebind: the mechanism '
            'was changed, so it needs its own review — do not widen REBIND to make this pass')

    def test_the_two_tools_never_share_a_module_key_receipt_directory_or_schema(self):
        p847 = (PLAN847 / 'supervisor.py').read_text()
        p1529 = (TOOL / 'supervisor.py').read_text()
        for marker in ("'plan847_contract'", "'plan847-attempts'", "'plan847-attempt-receipt/v1'", "'.plan847-'"):
            assert marker in p847 and marker not in p1529
        assert supervisor.RECEIPT_DIR.name == 'plan1529-attempts'

    def test_only_the_contract_and_packet_are_new(self):
        assert sorted(p.name for p in TOOL.iterdir() if p.name != '__pycache__') == ['README.md', 'child.py', 'contract.py', 'packet', 'supervisor.py']
        assert contract.BINDING_FILES == ('contract.py', 'child.py', 'supervisor.py')


# ─── packet, statements and source equality ──────────────────────────────────

class TestPacket:
    def test_vendored_packet_verifies_and_yields_four_sealed_envelopes_in_cli_order(self):
        plans = contract.packet()
        assert [name for name, _, _ in plans] == NAMES
        for name, digest, statements in plans:
            raw = (TOOL / 'packet' / f'{name}.plan-only.sql').read_text()
            assert hashlib.sha256(raw.encode()).hexdigest() == digest
            assert statements[:3] == contract.ENVELOPE[:3] and statements[4] == 'ROLLBACK'
            assert all(s in raw for s in statements)

    def test_packet_hashes_are_the_pinned_seal_chain(self):
        seal = (TOOL / 'packet' / 'SEAL.json').read_bytes()
        assert hashlib.sha256(seal).hexdigest() == 'a7774e43954754c54a0f7eefc59db26ae147aec21fc9ce713b3514660936e1c8'
        manifest = (TOOL / 'packet' / 'MANIFEST.json').read_bytes()
        assert hashlib.sha256(manifest).hexdigest() == '7995facad96825ebad420860a4553e36a70c50eb916032a533efe011f59d3577'
        assert json.loads(seal)['production_admitted'] is False

    @pytest.mark.parametrize('target,mutate', [
        ('games.plan-only.sql', lambda b: b.replace(b"'30 days'", b"'31 days'", 1)),
        ('markets.plan-only.sql', lambda b: b.replace(b'LEFT JOIN', b'JOIN', 1)),
        ('source_split.plan-only.sql', lambda b: b.replace(b'HAVING COUNT(fo.id) > 0', b'HAVING COUNT(fo.id) > 1', 1)),
        ('fixture_days.plan-only.sql', lambda b: b.replace(b"'500ms'", b"'5s'", 1)),
        ('SEAL.json', lambda b: b.replace(b'"production_admitted": false', b'"production_admitted": true')),
        ('MANIFEST.json', lambda b: b + b' '),
    ])
    def test_any_changed_packet_byte_is_refused(self, tmp_path, target, mutate):
        copy = tmp_path / 'plan1529'
        shutil.copytree(TOOL, copy)
        path = copy / 'packet' / target
        path.write_bytes(mutate(path.read_bytes()))
        other = _load('plan1529_contract_copy', copy / 'contract.py')
        try:
            with pytest.raises(other.Refused, match='PACKET_REFUSED'):
                other.packet()
        finally:
            sys.modules.pop('plan1529_contract_copy', None)

    CTE = contract.EXPLAIN_PREFIX + contract.GAME_CTE

    @pytest.mark.parametrize('explain,ok', [
        (CTE + 'SELECT sport_key, COUNT(*) FROM g GROUP BY sport_key', True),  # control
        (CTE + 'SELECT sport_key, COUNT(*) FROM g GROUP BY sport_key LIMIT 5', False),
        (CTE + 'SELECT sport_key, COUNT(*) FROM g GROUP BY sport_key OFFSET 1', False),
        (CTE + 'SELECT g.sport_key FROM g, futures_markets fm TABLESAMPLE SYSTEM (1)', False),
        (CTE + 'SELECT 1 FROM g FETCH FIRST 1 ROWS ONLY', False),
        (CTE.replace("'30 days'", "'7 days'") + 'SELECT 1 FROM g', False),
        (CTE.replace("('completed', 'closed')", "('completed')") + 'SELECT 1 FROM g', False),
        (CTE + ', h AS (SELECT 1) SELECT 1 FROM g, h WHERE NOW() > NOW() - INTERVAL \'1 day\'', False),
        ('EXPLAIN (ANALYZE, FORMAT JSON)\n' + contract.GAME_CTE + 'SELECT 1 FROM g', False),
        (CTE + 'SELECT analyze FROM g', False),
        (CTE + 'SELECT 1 FROM g; DELETE FROM futures_outcomes', False),
        (CTE + 'SELECT * FROM g FOR UPDATE', False),
    ])
    def test_the_grammar_admits_only_a_plain_explain_over_the_one_game_cohort(self, explain, ok):
        text = (contract.HEADER + 'BEGIN TRANSACTION READ ONLY;\n'
                "SET LOCAL statement_timeout = '2s';\nSET LOCAL lock_timeout = '500ms';\n"
                + explain + ';\nROLLBACK;\n')
        if ok:
            assert contract._statements(text)[3] == explain
        else:
            with pytest.raises(contract.Refused):
                contract._statements(text)


def _git_blob_sha1(raw: bytes) -> str:
    return hashlib.sha1(b'blob %d\0' % len(raw) + raw).hexdigest()


class TestSourceEquality:
    """The packet froze the census library's phase-A statements at 7e60a65a. If the
    library or the CLI's phase-A order changes, the packet is retired for review,
    never silently re-derived: these fail and say so."""

    MESSAGE = 'capture_census drifted from the #1529 sealed packet: retire tools/plan1529 for review; do not edit the packet to match'

    @pytest.mark.parametrize('name', NAMES)
    def test_each_sealed_statement_is_the_librarys_own_window_30_output(self, name):
        explain = dict((n, s) for n, _, s in contract.packet())[name][3]
        library = LIBRARY[name](contract.WINDOW_DAYS)
        assert library.strip().endswith(';') and library.count(';') == 1
        assert explain == 'EXPLAIN (FORMAT JSON)\n' + library.strip()[:-1], self.MESSAGE
        manifest = json.loads((TOOL / 'packet' / 'MANIFEST.json').read_text())
        assert manifest['statements'][name]['library_output_sha256'] == hashlib.sha256(library.encode()).hexdigest()

    def test_the_pinned_source_blobs_are_todays_files(self):
        for path, blob in contract.SOURCE_BLOBS.items():
            assert _git_blob_sha1((REPO / path).read_bytes()) == blob, self.MESSAGE

    def test_execution_order_is_the_cli_phase_a_order(self):
        tree = ast.parse((REPO / 'backend/scripts/capture_census.py').read_text())
        phase_a = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'phase_a')
        calls = [n.func.attr for n in ast.walk(phase_a) if isinstance(n, ast.Call)
                 and isinstance(n.func, ast.Attribute) and n.func.attr.endswith('_sql')]
        order = sorted(set(calls), key=lambda attr: next(
            n.lineno for n in ast.walk(phase_a) if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute) and n.func.attr == attr))
        assert order == ['games_sql', 'market_rows_sql', 'source_split_sql', 'fixture_days_sql']
        assert [LIBRARY[n].__name__ for n in NAMES] == order

    def test_the_issue_era_cohort_predicate_is_unchanged(self):
        """#1529 first shipped against 9776513964, whose CTE projected (id, sport_key)
        only. The statements differ by projection; the WHERE/JOIN cohort does not."""
        era_cte = ("\nWITH g AS (\n  SELECT e.id, s.key AS sport_key\n  FROM events e\n"
                   "  JOIN sports s ON s.id = e.sport_id\n  WHERE e.status IN ('completed', 'closed')\n"
                   "    AND e.commence_time >= NOW() - INTERVAL '%(window)s days'\n)\n")
        current = cc._GAME_CTE
        assert current.split('  FROM events e', 1)[1] == era_cte.split('  FROM events e', 1)[1]
        manifest = json.loads((TOOL / 'packet' / 'MANIFEST.json').read_text())
        assert manifest['issue_era']['ref'] == '977651396490b48ccf37fd2450de046689d2ecdd'
        assert manifest['statements']['fixture_days']['issue_era_output_sha256'] is None


# ─── protected window ────────────────────────────────────────────────────────

def _beat_and_limits():
    tree = ast.parse((REPO / 'backend/app/tasks/__init__.py').read_text())
    beats, limits = {}, {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            for k, v in zip(node.keys, node.values):
                if isinstance(k, ast.Constant) and isinstance(v, ast.Dict):
                    for kk, vv in zip(v.keys, v.values):
                        if (isinstance(kk, ast.Constant) and kk.value == 'schedule' and isinstance(vv, ast.Call)
                                and getattr(vv.func, 'id', None) == 'crontab'):
                            beats[k.value] = {kw.arg: getattr(kw.value, 'value', None) for kw in vv.keywords}
        if isinstance(node, ast.FunctionDef):
            for dec in node.decorator_list:
                if isinstance(dec, ast.Call):
                    kws = {kw.arg: getattr(kw.value, 'value', None) for kw in dec.keywords}
                    if 'name' in kws and 'time_limit' in kws:
                        limits[kws['name']] = kws['time_limit']
    return beats, limits


class TestProtectedWindow:
    def test_the_exclusion_covers_both_hourly_heavy_runs_and_their_hard_limits(self):
        beats, limits = _beat_and_limits()
        runs = [(beats['precompute-calibration-main']['minute'], limits['app.tasks.precompute_calibration_main']),
                (beats['precompute-backfill-winners-status']['minute'], limits['app.tasks.precompute_backfill_winners_status'])]
        assert runs == [(15, 1560), (35, 660)]
        low = min(m for m, _ in runs) * 60 - 60
        high = max(m * 60 + limit for m, limit in runs) + 60
        assert contract.PRODUCER_EXCLUSION == (low, high) == (14 * 60, 47 * 60)

    def test_the_weekly_sentinel_that_runs_these_statements_is_inside_the_exclusion(self):
        beats, limits = _beat_and_limits()
        weekly = beats['calibration-sentinel-weekly']
        assert (weekly['minute'], weekly['hour'], weekly['day_of_week']) == (20, 6, 1)
        start = weekly['minute'] * 60
        assert contract.PRODUCER_EXCLUSION[0] <= start
        assert start + limits['app.tasks.calibration_sentinel'] <= contract.PRODUCER_EXCLUSION[1]

    def test_boundaries(self):
        assert contract._touches_producer(HOUR + 14 * 60, HOUR + 14 * 60 + 1)
        assert contract._touches_producer(HOUR + 46 * 60 + 59, HOUR + 47 * 60)
        assert not contract._touches_producer(HOUR + 47 * 60, HOUR + 60 * 60 + 14 * 60)
        assert not contract._touches_producer(HOUR + 3 * 60, HOUR + 14 * 60)


# ─── admission ───────────────────────────────────────────────────────────────

def _missing(key):
    a = admission()
    del a[key]
    return a


def _window(start, end):
    a = admission(window={'start_unix': start, 'end_unix': end})
    for item in a['prerequisites'].values():
        item['observed_unix'] = start - 10
    return a


PLAN847_ADMISSION_TERMS = dict(
    subject='847-query3-candidateC-plan-only', decision='ROOT_ADMITTED_847_PLAN_ONLY',
    source_ref='0c544ac15d1eb9a0dbee8e81ff1e0062ea9576f4',
    seal_sha256='f3f2f3fdce4234203c33923fb992d6aa371cf5c00812a57b602629eb3e6657f8',
)


class TestAdmission:
    def test_control_a_fresh_exact_admission_is_admitted(self):
        admitted, digest = contract.admit(admission(), OWNER, BASE, 15)
        assert admitted['admission_id'] == AID and len(digest) == 64

    @pytest.mark.parametrize('bad,code', [
        (None, 'ADMISSION_REFUSED'),
        (_missing('window'), 'ADMISSION_REFUSED'),
        (admission(extra_sql='SELECT 1'), 'ADMISSION_REFUSED'),
        (admission(window_days=31), 'ADMISSION_REFUSED'),
        *[(admission(**{k: v}), 'ADMISSION_REFUSED') for k, v in PLAN847_ADMISSION_TERMS.items()],
        (admission(sql_sha256={'query3': 'bd54471ec2279ae71bfb358efbf7fadd11586cd0dd1265619d0786393cb2fc72'}), 'ADMISSION_REFUSED'),
        (admission(sql_sha256={n: d for n, _, d in contract.PLANS[:3]}), 'ADMISSION_REFUSED'),
        (admission(sql_sha256={**{n: d for n, _, d in contract.PLANS}, 'games': contract.PLANS[1][2]}), 'ADMISSION_REFUSED'),
        (admission(limits=dict(contract.LIMITS, total_seconds=35)), 'ADMISSION_REFUSED'),
        (admission(limits=dict(contract.LIMITS, statement_timeout='5s')), 'ADMISSION_REFUSED'),
        (admission(limits=dict(contract.LIMITS, combined_output_bytes=2097152)), 'ADMISSION_REFUSED'),
        (admission(limits=dict(contract.LIMITS, analyze=True)), 'ADMISSION_REFUSED'),
        (admission(binding_sha256='0' * 64), 'BINDING_REFUSED'),
    ])
    def test_wrong_subject_source_sql_seal_limits_or_shape_is_refused(self, bad, code):
        with pytest.raises(contract.Refused, match=code):
            contract.admit(bad, OWNER, BASE, 15)

    def test_plan847s_own_binding_digest_is_refused(self):
        p847 = _load('plan847_contract_for_1529', PLAN847 / 'contract.py')
        try:
            with pytest.raises(contract.Refused, match='BINDING_REFUSED'):
                contract.admit(admission(binding_sha256=p847.binding_sha256()), OWNER, BASE, 15)
        finally:
            sys.modules.pop('plan847_contract_for_1529', None)

    @pytest.mark.parametrize('owner', ['measurement-ctl-OTHER', None, True])
    def test_absent_or_mismatched_owner_is_refused(self, owner):
        with pytest.raises(contract.Refused, match='OWNER_REFUSED'):
            contract.admit(admission(), owner, BASE, 15)

    @pytest.mark.parametrize('bad,now', [
        (admission(), BASE + 300),                       # expired
        (admission(), BASE + 290),                       # too little window for 15 s
        (admission(), BASE - 31),                        # not yet open
        (_window(BASE - 100, BASE + 600), BASE),         # lease too long (700 s, clear of the band)
        (_window(HOUR + 3600 + 10 * 60, HOUR + 3600 + 15 * 60), HOUR + 3600 + 10 * 60 + 5),  # touches the rebuild
        (_window(HOUR + 3600 + 30 * 60, HOUR + 3600 + 33 * 60), HOUR + 3600 + 30 * 60 + 5),  # inside the band
    ])
    def test_expired_early_long_or_protected_window_admission_is_refused(self, bad, now):
        with pytest.raises(contract.Refused, match='WINDOW_REFUSED'):
            contract.admit(bad, OWNER, now, 15)

    def test_control_a_window_ending_exactly_at_14_is_admitted(self):
        start = HOUR + 3600 + 5 * 60
        contract.admit(_window(start, HOUR + 3600 + 14 * 60), OWNER, start + 5, 15)


# ─── evidence ────────────────────────────────────────────────────────────────

PLAN = [{'Plan': {'Node Type': 'Aggregate', 'Total Cost': 1.0}}]


def _good_records():
    out = []
    for name, _, digest in contract.PLANS:
        out += [{'kind': 'guard', 'plan': name, 'row': ['on', '2s', '500ms']},
                {'kind': 'plan', 'plan': name, 'sql_sha256': digest, 'json': PLAN},
                {'kind': 'rollback', 'plan': name, 'status': 'ROLLBACK'}]
    return out + [{'kind': 'complete', 'mode': 'plan_only', 'owned_connection_closed': True}]


def _raw(items):
    return b''.join(json.dumps(i).encode() + b'\n' for i in items)


class TestEvidence:
    def test_control_complete_evidence_for_all_four_is_accepted(self):
        assert contract.evidence(_raw(_good_records())) == _good_records()

    @pytest.mark.parametrize('items,code', [
        (_good_records()[:9] + _good_records()[-1:], 'EVIDENCE_REFUSED'),      # fourth plan missing
        (_good_records()[3:6] + _good_records()[:3] + _good_records()[6:], 'EVIDENCE_REFUSED'),  # order
        (_good_records()[:-1], 'EVIDENCE_REFUSED'),                             # no completion
        ([dict(r, json=[{'Plan': {'Node Type': 'Seq Scan', 'Actual Rows': 1}}]) if r['kind'] == 'plan' else r
          for r in _good_records()], 'ANALYZE_REFUSED'),
    ])
    def test_three_plans_reordered_unfinished_or_analyzed_evidence_is_refused(self, items, code):
        with pytest.raises(contract.Refused, match=code):
            contract.evidence(_raw(items))


# ─── end to end: real supervisor, real worker, real child, fake driver ───────

class Rig:
    def __init__(self, tmp_path, monkeypatch, behavior=None, virtual=True):
        tmp_path.mkdir(parents=True, exist_ok=True)
        self.log = tmp_path / 'driver.log'
        self.clock = tmp_path / 'clock'
        self.clock.write_text('0')
        self.receipts = tmp_path / 'receipts'
        launcher = tmp_path / 'launcher.py'
        launcher.write_text(textwrap.dedent(f'''
            import json, runpy, sys
            sys.path.insert(0, {str(TESTS)!r})
            import lib_plan1529_fake_driver as fake
            sys.argv = [{str(TOOL / 'child.py')!r}]
            fake.install(json.loads({json.dumps(behavior or {})!r}), {str(self.log)!r}, {str(self.clock)!r})
            runpy.run_path({str(TOOL / 'child.py')!r}, run_name='__main__')
        '''))
        monkeypatch.setattr(supervisor, '_child_argv', lambda: PRODUCTION_ARGV()[:-1] + [str(launcher), str(TOOL / 'child.py')])
        monkeypatch.setattr(supervisor, 'RECEIPT_DIR', self.receipts)
        monkeypatch.setattr(supervisor, '_wall', lambda: BASE)
        if virtual:
            clock = self.clock
            monkeypatch.setattr(supervisor, '_now', lambda: time.monotonic() + float(clock.read_text() or 0))

    def run(self, adm=None, owner=OWNER, credential=DSN):
        t0 = time.monotonic()
        result = supervisor.run_attempt(credential=credential, admission=admission() if adm is None else adm, owner=owner)
        self.real_seconds = time.monotonic() - t0
        return result

    def events(self):
        if not self.log.exists():
            return []
        return [json.loads(line) for line in self.log.read_text().splitlines()]

    def executed(self):
        return [e['kind'] for e in self.events() if e['event'] == 'execute']

    def receipt(self):
        return (self.receipts / f'{AID}.json').read_bytes()

    def child_pid(self):
        launches = [e for e in self.events() if e['event'] == 'launch']
        return launches[0]['pid'] if launches else None


def _plan_sequence(name):
    return ['begin', 'set_statement', 'set_lock', 'guard', f'explain_{name}', 'rollback']


FULL_SEQUENCE = [kind for name in NAMES for kind in _plan_sequence(name)]


def _assert_gone(pid):
    if pid is None:
        return
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return
        time.sleep(.01)
    raise AssertionError(f'child {pid} outlived the attempt')


class TestEndToEnd:
    def test_success_explains_exactly_the_four_sealed_statements_once_in_order(self, tmp_path, monkeypatch):
        rig = Rig(tmp_path, monkeypatch)
        result = rig.run()
        assert result['verdict'] == 'PLAN_ONLY_PENDING_ROOT_REVIEW', result
        assert result['owner_completed'] is True and result['reason'] is None
        assert 0 < result['elapsed_seconds'] < contract.LIMITS['total_seconds']
        assert result['combined_output_bytes'] <= contract.LIMITS['combined_output_bytes']
        assert rig.executed() == FULL_SEQUENCE
        explained = [e['sql_sha256'] for e in rig.events() if e['event'] == 'execute' and e['kind'].startswith('explain')]
        assert explained == [hashlib.sha256(s[3].encode()).hexdigest() for _, _, s in contract.packet()]
        connect = [e for e in rig.events() if e['event'] == 'connect']
        assert len(connect) == 1
        assert connect[0]['kwargs'] == {'async_': True, 'connect_timeout': 2, 'sslmode': 'require',
                                        'options': contract.CONNECT_OPTIONS}
        assert [e['event'] for e in rig.events()].count('close') == 1
        _assert_gone(rig.child_pid())
        raw = rig.receipt()
        disk = json.loads(raw)
        assert disk['schema'] == 'plan1529-attempt-receipt/v1' and disk['subject'] == contract.SUBJECT
        assert disk['verdict'] == 'NO_RESULT' and disk['reason'] == 'OWNER_CONFIRMATION_REQUIRED'
        assert set(contract.accept(result, raw)) == set(NAMES)

    def test_no_credential_reaches_argv_env_logs_receipts_or_return(self, tmp_path, monkeypatch, capfd):
        monkeypatch.setenv('DATABASE_URL', 'postgres://ambient@leak/db')
        monkeypatch.setenv('PGPASSWORD', 'ambient-password')
        rig = Rig(tmp_path, monkeypatch, {'explain_markets': [{'raise': True}]})
        result = rig.run()
        assert result['verdict'] == 'NO_RESULT' and result['reason'] == 'NONZERO_EXIT'
        launch = [e for e in rig.events() if e['event'] == 'launch'][0]
        assert 'DATABASE_URL' not in launch['env_keys'] and 'PGPASSWORD' not in launch['env_keys']
        out, err = capfd.readouterr()
        haystacks = [json.dumps(result), out, err, rig.log.read_text(), json.dumps(launch['orig_argv'])]
        haystacks += [p.read_bytes().decode('utf-8', 'replace') for p in rig.receipts.iterdir()]
        for text in haystacks:
            assert LEAK_MARKER not in text and 'reader:' not in text

    def test_default_entry_refuses_without_admission_and_never_launches(self, tmp_path, monkeypatch):
        rig = Rig(tmp_path, monkeypatch)
        result = supervisor.run_attempt(credential=DSN, admission=None, owner=OWNER)
        assert result['verdict'] == 'NO_RESULT' and result['reason'] == 'ADMISSION_REFUSED'
        assert result['attempt_consumed'] is False
        assert not rig.log.exists() and not rig.receipts.exists()

    def test_a_plan847_admission_is_refused_before_any_connection(self, tmp_path, monkeypatch):
        rig = Rig(tmp_path, monkeypatch)
        result = rig.run(adm=admission(**PLAN847_ADMISSION_TERMS))
        assert result['reason'] == 'ADMISSION_REFUSED' and result['attempt_consumed'] is False
        assert not rig.log.exists() and not rig.receipts.exists()

    def test_a_return_past_the_wall_or_a_changed_receipt_is_never_accepted(self, tmp_path, monkeypatch):
        rig = Rig(tmp_path, monkeypatch)
        result = rig.run()
        raw = rig.receipt()
        assert set(contract.accept(result, raw)) == set(NAMES)   # control
        with pytest.raises(contract.Refused, match='ACCEPT_REFUSED'):
            contract.accept(dict(result, elapsed_seconds=15.2), raw)
        with pytest.raises(contract.Refused, match='ACCEPT_REFUSED'):
            contract.accept(dict(result, owner_completed=False), raw)
        with pytest.raises(contract.Refused, match='ACCEPT_REFUSED'):
            contract.accept(result, raw + b' \n')

    def test_one_attempt_per_admission(self, tmp_path, monkeypatch):
        rig = Rig(tmp_path, monkeypatch)
        assert rig.run()['verdict'] == 'PLAN_ONLY_PENDING_ROOT_REVIEW'
        again = rig.run()
        assert again['verdict'] == 'NO_RESULT' and again['reason'] == 'SINGLE_USE_REFUSED'
        assert [e['event'] for e in rig.events()].count('connect') == 1

    @pytest.mark.parametrize('index,name', list(enumerate(NAMES)))
    def test_a_failed_plan_stops_every_later_one_and_three_plans_are_no_result(self, tmp_path, monkeypatch, index, name):
        rig = Rig(tmp_path, monkeypatch, {f'explain_{name}': [{'raise': True}]})
        result = rig.run()
        assert result['verdict'] == 'NO_RESULT' and result['candidate_sha256'] is None
        assert rig.executed() == FULL_SEQUENCE[:6 * index + 5]
        assert [e['event'] for e in rig.events()].count('close') == 1
        assert 'candidate_evidence' not in json.loads(rig.receipt())

    @pytest.mark.parametrize('name', NAMES)
    def test_a_stalled_plan_ends_in_no_result_within_the_wall(self, tmp_path, monkeypatch, name):
        rig = Rig(tmp_path, monkeypatch, {f'explain_{name}': [{'bump': 100, 'stall': True}]})
        result = rig.run()
        assert result['verdict'] == 'NO_RESULT' and result['candidate_sha256'] is None
        assert rig.real_seconds < 10
        assert rig.executed()[-1] == f'explain_{name}'
        _assert_gone(rig.child_pid())
        with pytest.raises(contract.Refused, match='ACCEPT_REFUSED'):
            contract.accept(result, rig.receipt())

    def test_the_wall_is_one_total_across_all_four_statements(self, tmp_path, monkeypatch):
        # Control: four 3 s plans (12 s) fit inside the child's share of the one wall.
        control = Rig(tmp_path / 'control', monkeypatch, {f'explain_{n}': [{'bump': 3}] for n in NAMES})
        assert control.run()['verdict'] == 'PLAN_ONLY_PENDING_ROOT_REVIEW'
        # Four 3.5 s plans (14 s) do not: no per-plan allowance, no late success.
        over = Rig(tmp_path / 'over', monkeypatch, {f'explain_{n}': [{'bump': 3.5}] for n in NAMES})
        result = over.run()
        assert result['verdict'] == 'NO_RESULT' and result['reason'] in ('WALL_EXPIRED', 'WALL_EXPIRED_OR_UNAVAILABLE')
        assert result['candidate_sha256'] is None

    def test_one_ledger_bounds_four_plans_and_their_receipt_together(self, tmp_path, monkeypatch):
        cap = contract.LIMITS['combined_output_bytes']
        ok = Rig(tmp_path / 'ok', monkeypatch, {f'explain_{n}': [{'plan_pad': 50_000}] for n in NAMES})
        result = ok.run()
        assert result['verdict'] == 'PLAN_ONLY_PENDING_ROOT_REVIEW', result
        assert result['combined_output_bytes'] <= cap
        # Four 70 KB plans fit the stream (280 KB) but not stream + receipt: refused, not truncated.
        big = Rig(tmp_path / 'big', monkeypatch, {f'explain_{n}': [{'plan_pad': 70_000}] for n in NAMES})
        result = big.run()
        assert result['verdict'] == 'NO_RESULT' and result['reason'] == 'OUTPUT_EXCEEDED', result
        assert result['combined_output_bytes'] <= cap
        assert 'candidate_evidence' not in json.loads(big.receipt())

    @pytest.mark.parametrize('behavior,reason', [
        ({'explain_fixture_days': [{'truncate': True}]}, 'EVIDENCE_REFUSED'),
        ({'guard': [{}, {}, {'row': ('off', '2s', '500ms')}]}, 'NONZERO_EXIT'),
        ({'rollback': [{}, {}, {}, {'status': 'COMMIT'}]}, 'NONZERO_EXIT'),
        ({'explain_source_split': [{'stderr': 'NOTICE: something\n'}]}, 'STDERR_REFUSED'),
        ({'explain_games': [{'plan': [{'Plan': {'Node Type': 'Aggregate', 'Actual Rows': 1}}]}]}, 'NONZERO_EXIT'),
    ])
    def test_truncated_unguarded_committed_noisy_or_analyzed_runs_are_no_result(self, tmp_path, monkeypatch, behavior, reason):
        rig = Rig(tmp_path, monkeypatch, behavior)
        result = rig.run()
        assert result['verdict'] == 'NO_RESULT' and result['reason'] == reason, result
        assert 'candidate_evidence' not in json.loads(rig.receipt())

    def test_the_real_15_second_wall_holds_on_a_real_stall(self, tmp_path, monkeypatch):
        """No virtual time: the worker's final receipt fsync hangs for real after all four
        plans ran. The owner must kill and reap its worker group inside the real 15 s."""
        rig = Rig(tmp_path, monkeypatch, virtual=False)
        real_fsync = os.fsync
        calls = {'n': 0}

        def hanging_fsync(fd):
            calls['n'] += 1
            if calls['n'] == 3:
                time.sleep(60)
            return real_fsync(fd)
        monkeypatch.setattr(supervisor.os, 'fsync', hanging_fsync)
        result = rig.run()
        assert result['verdict'] == 'NO_RESULT' and result['owner_completed'] is False
        assert result['worker_reaped'] is True
        assert 14.5 < result['elapsed_seconds'] <= 15.0
        assert rig.real_seconds <= 15.1
        assert rig.executed() == FULL_SEQUENCE
        _assert_gone(rig.child_pid())


def test_the_child_itself_refuses_a_bad_admission_before_importing_a_driver(tmp_path, monkeypatch):
    rig = Rig(tmp_path, monkeypatch)
    payload = json.dumps({'credential': DSN, 'admission': admission(subject='847'), 'owner': OWNER,
                          'output_budget': 100_000}).encode()
    proc = subprocess.run(supervisor._child_argv(), input=payload, capture_output=True,
                          env=supervisor.CHILD_ENV, timeout=10)
    assert proc.returncode == 1 and proc.stderr == b''
    assert proc.stdout == b'{"kind":"refusal","reason":"CHILD_REFUSED"}\n'
    assert [e['event'] for e in rig.events()] == ['launch']
