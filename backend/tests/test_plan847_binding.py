"""#847 plan-only binding (`tools/plan847/`): the sealed query3 / candidate C pair, once.

PILLAR: TRUTH. SHIP: operators see the full stored guess-family count without losing
the winner-coverage cache to an unreviewed expensive query. These tests are the
offline gate of the tool that would, under a separate attended admission, EXPLAIN
the two frozen statements. Nothing here touches a network or a database.

HOW THE END-TO-END TESTS WORK
-----------------------------
They call the REAL `supervisor.run_attempt`, which forks the REAL worker, which
spawns the REAL `child.py`. Three seams are replaced, all module attributes:
  * `_child_argv`: a generated launcher installs `lib_plan847_fake_driver` as
    `psycopg2`, then runs the real child file;
  * `_now`: monotonic time plus an offset read from a file the fake driver can
    advance, so "this EXPLAIN took 7 s" costs no real time and does not depend on
    runner speed;
  * `_wall` and `RECEIPT_DIR`: a fixed safe wall time and a per-test directory.
One test uses no virtual time at all and proves the real 15 s wall on a real stall.
"""
from __future__ import annotations

import ast
import hashlib
import importlib.util
import inspect
import json
import os
import shutil
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

TESTS = Path(__file__).resolve().parent
REPO = TESTS.parents[1]
TOOL = REPO / 'tools' / 'plan847'
LEAK_MARKER = 'plan847-leak-marker-not-a-password'
DSN = f'postgresql://reader:{LEAK_MARKER}@db.invalid:5432/fake'


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


contract = _load('plan847_contract', TOOL / 'contract.py')
supervisor = _load('plan847_supervisor', TOOL / 'supervisor.py')
assert supervisor.contract is contract
PRODUCTION_ARGV = supervisor._child_argv

# A fixed wall time at :10:00 UTC of some hour, far from the producer's :35 run.
BASE = 1_792_000_000 - (1_792_000_000 % 3600) + 600


def admission(**overrides):
    value = dict(
        decision=contract.DECISION, subject=contract.SUBJECT, mode='plan_only',
        admission_id='adm-847-test-0001', binding_sha256=contract.binding_sha256(),
        seal_sha256=contract.SEAL_SHA256, manifest_sha256=contract.MANIFEST_SHA256,
        source_ref=contract.SOURCE_REF,
        sql_sha256={name: digest for name, _, digest in contract.PLANS},
        limits=dict(contract.LIMITS), root_review_id='root-review-847-test',
        admission_owner='calibration-goal-root', controller_session='measurement-ctl-847',
        window={'start_unix': BASE - 30, 'end_unix': BASE + 300},
        prerequisites={k: {'ref': f'artifacts/fake-847/{k}.json', 'sha256': 'ab' * 32,
                           'observed_unix': BASE - 60} for k in contract.PREREQUISITES},
    )
    value.update(overrides)
    return value


OWNER = 'measurement-ctl-847'


# ─── packet and statements ───────────────────────────────────────────────────

class TestPacket:
    def test_vendored_packet_verifies_and_yields_exactly_the_sealed_envelopes(self):
        plans = contract.packet()
        assert [name for name, _, _ in plans] == ['query3', 'candidateC']
        for name, digest, statements in plans:
            raw = (TOOL / 'packet' / f'{name}.plan-only.sql').read_text()
            assert hashlib.sha256(raw.encode()).hexdigest() == digest
            assert statements[:3] == contract.ENVELOPE[:3] and statements[4] == 'ROLLBACK'
            # Every executed statement is a verbatim substring of the sealed bytes.
            assert all(s in raw for s in statements)

    def test_packet_hashes_are_the_pinned_seal_chain(self):
        raw = (TOOL / 'packet' / 'SEAL.json').read_bytes()
        assert hashlib.sha256(raw).hexdigest() == 'f3f2f3fdce4234203c33923fb992d6aa371cf5c00812a57b602629eb3e6657f8'
        manifest = (TOOL / 'packet' / 'MANIFEST.json').read_bytes()
        assert hashlib.sha256(manifest).hexdigest() == '34d0e506522f791378bb387456c9f403a2d25998ab4a286f77178d2ad13eaf5c'

    @pytest.mark.parametrize('target,mutate', [
        ('query3.plan-only.sql', lambda b: b.replace(b"'2s'", b"'9s'", 1)),
        ('candidateC.plan-only.sql', lambda b: b.replace(b'pass2_guess', b'pass2_guesz', 1)),
        ('SEAL.json', lambda b: b.replace(b'"production_admitted": false', b'"production_admitted": true')),
        ('MANIFEST.json', lambda b: b + b' '),
    ])
    def test_any_changed_packet_byte_is_refused(self, tmp_path, target, mutate):
        copy = tmp_path / 'plan847'
        shutil.copytree(TOOL, copy)
        path = copy / 'packet' / target
        path.write_bytes(mutate(path.read_bytes()))
        other = _load('plan847_contract_copy', copy / 'contract.py')
        try:
            with pytest.raises(other.Refused, match='PACKET_REFUSED'):
                other.packet()
        finally:
            sys.modules.pop('plan847_contract_copy', None)

    @pytest.mark.parametrize('explain', [
        'EXPLAIN (FORMAT JSON)\nSELECT\n 1',  # control: accepted
        'EXPLAIN (ANALYZE, FORMAT JSON)\nSELECT\n 1',
        'EXPLAIN (FORMAT JSON)\nSELECT\n 1; DELETE FROM futures_outcomes',
        'EXPLAIN (FORMAT JSON)\nSELECT\n * FROM futures_outcomes FOR UPDATE',
        'EXPLAIN (FORMAT JSON)\nSELECT\n analyze',
    ])
    def test_the_statement_grammar_admits_only_a_plain_explain_select(self, explain):
        text = (contract.HEADER + 'BEGIN TRANSACTION READ ONLY;\n'
                "SET LOCAL statement_timeout = '2s';\nSET LOCAL lock_timeout = '500ms';\n"
                + explain + ';\nROLLBACK;\n')
        if explain == 'EXPLAIN (FORMAT JSON)\nSELECT\n 1':
            assert contract._statements(text)[3] == explain
        else:
            with pytest.raises(contract.Refused):
                contract._statements(text)


class TestCanonicalPopulationUnchanged:
    """The packet froze the producer's query3 and the canonical guess family at
    0c544ac. If either changes in this repo, the packet is retired for review, not
    silently re-derived: these fail and say so."""

    def _producer_literal(self):
        tree = ast.parse((REPO / 'backend/app/tasks/precompute_backfill_winners_status.py').read_text())
        hits = [n for n in ast.walk(tree) if isinstance(n, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == 'cal_result' for t in n.targets)]
        assert len(hits) == 1
        return hits[0].value.value.args[0].args[0].value

    def _family(self):
        tree = ast.parse((REPO / 'backend/app/utils/resolution_authority.py').read_text())
        for node in tree.body:
            if isinstance(node, ast.AnnAssign) and getattr(node.target, 'id', None) == 'GUESS_FAMILY_SOURCES':
                return frozenset(ast.literal_eval(node.value.args[0]))
        raise AssertionError('GUESS_FAMILY_SOURCES not found')

    def test_query3_is_still_the_producers_statement(self):
        explain = dict((n, s) for n, _, s in contract.packet())['query3'][3]
        assert explain == 'EXPLAIN (FORMAT JSON)\n' + textwrap.dedent(self._producer_literal()).strip(), (
            'precompute_backfill_winners_status query3 drifted from the #847 sealed packet: '
            'retire tools/plan847 for review; do not edit the packet to match')

    def test_candidate_c_is_still_p_or_the_canonical_family(self):
        explain = dict((n, s) for n, _, s in contract.packet())['candidateC'][3]
        family = sorted(self._family())
        in_list = '(' + ', '.join(f"'{s}'" for s in family) + ')'
        where = self._producer_literal().rsplit('WHERE ', 1)[1]
        p = '(' + ' '.join(where.split()) + ')'
        assert explain.endswith(f'WHERE {p} OR (fo.resolution_source IN {in_list})'), (
            'canonical guess family or P drifted from the #847 sealed packet: retire it for review')
        for source in family:
            assert f"COUNT(*) FILTER (WHERE fo.resolution_source = '{source}') AS gf_{source}" in explain


# ─── admission ───────────────────────────────────────────────────────────────

def _bool_prereq():
    a = admission()
    a['prerequisites']['quiet_window'] = True
    return a


def _missing_digest():
    a = admission()
    del a['prerequisites']['heavy_carrier']['sha256']
    return a


def _bad_digest():
    a = admission()
    a['prerequisites']['main_carrier']['sha256'] = 'carrier-v5802-looks-fine'
    return a


def _stale_prereq():
    a = admission()
    a['prerequisites']['source_equality']['observed_unix'] = BASE - 30 - contract.PREREQUISITE_MAX_AGE_SECONDS - 1
    return a


def _future_prereq():
    a = admission()
    a['prerequisites']['measurement_owner']['observed_unix'] = BASE + 5
    return a


def _producer_window():
    # Fresh in every other respect, so only the :34-:47 exclusion can refuse it.
    a = admission(window={'start_unix': BASE + 1400, 'end_unix': BASE + 1500})
    for item in a['prerequisites'].values():
        item['observed_unix'] = BASE + 1390
    return a


def _missing(key):
    a = admission()
    del a[key]
    return a


class TestAdmission:
    def test_control_a_fresh_exact_admission_is_admitted(self):
        admitted, digest = contract.admit(admission(), OWNER, BASE, 15)
        assert admitted['admission_id'] == 'adm-847-test-0001' and len(digest) == 64

    @pytest.mark.parametrize('bad,code', [
        (None, 'ADMISSION_REFUSED'),
        ('ROOT_ADMITTED_847_PLAN_ONLY', 'ADMISSION_REFUSED'),
        (_missing('window'), 'ADMISSION_REFUSED'),
        (admission(extra_sql='SELECT 1'), 'ADMISSION_REFUSED'),
        (admission(subject='683-q683'), 'ADMISSION_REFUSED'),
        (admission(decision='ROOT_ADMITTED_PLAN_ONLY'), 'ADMISSION_REFUSED'),
        (admission(source_ref='d714d4a62318175bc750201ad42514eeee595f73'), 'ADMISSION_REFUSED'),
        (admission(seal_sha256='0' * 64), 'ADMISSION_REFUSED'),
        (admission(sql_sha256={'query3': contract.PLANS[0][2]}), 'ADMISSION_REFUSED'),
        (admission(sql_sha256={'query3': contract.PLANS[1][2], 'candidateC': contract.PLANS[0][2]}), 'ADMISSION_REFUSED'),
        (admission(limits=dict(contract.LIMITS, total_seconds=35)), 'ADMISSION_REFUSED'),
        (admission(limits=dict(contract.LIMITS, combined_output_bytes=2097152)), 'ADMISSION_REFUSED'),
        (admission(limits=dict(contract.LIMITS, attempts=2)), 'ADMISSION_REFUSED'),
        (admission(limits=dict(contract.LIMITS, analyze=True)), 'ADMISSION_REFUSED'),
        (admission(admission_id='x'), 'ADMISSION_REFUSED'),
        (admission(root_review_id=True), 'ADMISSION_REFUSED'),
        (_bool_prereq(), 'ADMISSION_REFUSED'),
        (_missing_digest(), 'ADMISSION_REFUSED'),
        (_bad_digest(), 'ADMISSION_REFUSED'),
        (admission(window={'start_unix': True, 'end_unix': BASE + 300}), 'ADMISSION_REFUSED'),
        (admission(window={'start_unix': float('nan'), 'end_unix': BASE + 300}), 'ADMISSION_REFUSED'),
        (admission(binding_sha256='0' * 64), 'BINDING_REFUSED'),
    ])
    def test_wrong_subject_source_sql_seal_limits_or_shape_is_refused(self, bad, code):
        with pytest.raises(contract.Refused, match=code):
            contract.admit(bad, OWNER, BASE, 15)

    @pytest.mark.parametrize('bad,owner', [
        (admission(), 'measurement-ctl-OTHER'),
        (admission(), None),
        (admission(), True),
        (_missing('controller_session'), OWNER),
    ])
    def test_absent_or_mismatched_owner_is_refused(self, bad, owner):
        with pytest.raises(contract.Refused, match='OWNER_REFUSED|ADMISSION_REFUSED'):
            contract.admit(bad, owner, BASE, 15)

    @pytest.mark.parametrize('bad,now', [
        (admission(), BASE + 300),  # expired
        (admission(), BASE + 290),  # too little window left for the whole 15 s attempt
        (admission(), BASE - 31),  # not yet open
        (admission(window={'start_unix': BASE - 400, 'end_unix': BASE + 300}), BASE),  # lease too long
        (_producer_window(), BASE + 1410),  # touches :34-:47
        (_stale_prereq(), BASE),
        (_future_prereq(), BASE),
    ])
    def test_expired_early_long_producer_overlapping_or_stale_admission_is_refused(self, bad, now):
        with pytest.raises(contract.Refused, match='WINDOW_REFUSED'):
            contract.admit(bad, OWNER, now, 15)

    def test_control_the_same_window_ten_minutes_earlier_is_admitted(self):
        a = _producer_window()
        a['window'] = {'start_unix': BASE + 800, 'end_unix': BASE + 900}  # :23:20-:25:00
        for item in a['prerequisites'].values():
            item['observed_unix'] = BASE + 790
        contract.admit(a, OWNER, BASE + 810, 15)

    def test_the_producer_exclusion_covers_its_whole_hard_limit(self):
        hour = BASE - 600
        assert contract._touches_producer(hour + 34 * 60, hour + 34 * 60 + 1)
        assert contract._touches_producer(hour + 46 * 60 + 59, hour + 47 * 60)
        assert not contract._touches_producer(hour + 47 * 60, hour + 60 * 60 + 33 * 60)


# ─── evidence and accept ─────────────────────────────────────────────────────

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


def _with(index, **changes):
    items = _good_records()
    items[index] = dict(items[index], **changes)
    return items


class TestEvidence:
    def test_control_complete_evidence_is_accepted(self):
        assert contract.evidence(_raw(_good_records())) == _good_records()

    @pytest.mark.parametrize('raw,code', [
        (_raw(_good_records())[:-1], 'EVIDENCE_REFUSED'),  # truncated: no final newline
        (_raw(_good_records()[:-1]), 'EVIDENCE_REFUSED'),  # no completion record
        (_raw(_good_records()[:4]), 'EVIDENCE_REFUSED'),  # second plan missing
        (_raw(_good_records() + [{'kind': 'complete'}]), 'EVIDENCE_REFUSED'),
        (_raw(_good_records()[3:6] + _good_records()[:3] + _good_records()[6:]), 'EVIDENCE_REFUSED'),  # order
        (_raw(_with(1, json=[{'Plan': {'Node Type': 'Seq Scan', 'Actual Rows': 5}}])), 'ANALYZE_REFUSED'),
        (_raw(_with(4, json=[{'Plan': {'Node Type': 'Aggregate'}, 'Execution Time': 2.0}])), 'PLAN_REFUSED'),
        (_raw(_with(4, json=[{'Plan': {'Node Type': 'Aggregate', 'Plans': [{'Execution Time': 1}]}}])), 'ANALYZE_REFUSED'),
        (_raw(_with(1, json=[{'Plan': {}}])), 'PLAN_REFUSED'),
        (_raw(_with(1, json=PLAN + PLAN)), 'PLAN_REFUSED'),
        (_raw(_with(1, json='[{"Plan": {}}]')), 'PLAN_REFUSED'),
        (_raw(_with(1, sql_sha256=contract.PLANS[1][2])), 'EVIDENCE_REFUSED'),
        (_raw(_with(0, row=['off', '2s', '500ms'])), 'EVIDENCE_REFUSED'),
        (_raw(_with(2, status='COMMIT')), 'EVIDENCE_REFUSED'),
        (_raw(_with(6, owned_connection_closed=False)), 'EVIDENCE_REFUSED'),
        (b'{"kind":"guard","kind":"guard"}\n', 'JSON_REFUSED'),
        (b'{"a": NaN}\n', 'JSON_REFUSED'),
        (b'{"kind":"plan","pl', 'EVIDENCE_REFUSED'),
    ])
    def test_partial_malformed_truncated_or_analyzed_evidence_is_refused(self, raw, code):
        with pytest.raises(contract.Refused, match=code):
            contract.evidence(raw)


# ─── end to end: real supervisor, real worker, real child, fake driver ───────

class Rig:
    def __init__(self, tmp_path, monkeypatch, behavior=None, virtual=True, meter=False, prestart=0):
        tmp_path.mkdir(parents=True, exist_ok=True)
        self.dir = tmp_path
        self.log = tmp_path / 'driver.log'
        self.clock = tmp_path / 'clock'
        self.clock.write_text('0')
        self.receipts = tmp_path / 'receipts'
        launcher = tmp_path / 'launcher.py'
        launcher.write_text(textwrap.dedent(f'''
            import json, runpy, sys
            sys.path.insert(0, {str(TESTS)!r})
            import lib_plan847_fake_driver as fake
            sys.argv = [{str(TOOL / 'child.py')!r}]
            fake.install(json.loads({json.dumps(behavior or {})!r}), {str(self.log)!r}, {str(self.clock)!r})
            if {meter!r}:
                fake.meter({str(self.log)!r}, {prestart!r})
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

    def written(self, kind='complete', stream=None):
        """Bytes the child's writes into its parent's pipes completed (or attempted)."""
        names = {f'{s}_write_{kind}' for s in ((stream,) if stream else ('stdout', 'stderr'))}
        return sum(e['bytes'] for e in self.events() if e['event'] in names)

    def disk(self):
        return sum(p.stat().st_size for p in self.receipts.iterdir())

    def receipt(self, aid='adm-847-test-0001'):
        return (self.receipts / f'{aid}.json').read_bytes()

    def child_pid(self):
        launches = [e for e in self.events() if e['event'] == 'launch']
        return launches[0]['pid'] if launches else None


FULL_SEQUENCE = ['begin', 'set_statement', 'set_lock', 'guard', 'explain_query3', 'rollback',
                 'begin', 'set_statement', 'set_lock', 'guard', 'explain_candidateC', 'rollback']


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
    def test_success_runs_exactly_the_sealed_pair_once_and_returns_in_time(self, tmp_path, monkeypatch):
        rig = Rig(tmp_path, monkeypatch)
        result = rig.run()
        assert result['verdict'] == 'PLAN_ONLY_PENDING_ROOT_REVIEW', result
        assert result['owner_completed'] is True and result['reason'] is None
        assert 0 < result['elapsed_seconds'] < contract.LIMITS['total_seconds']
        assert result['combined_output_bytes'] <= contract.LIMITS['combined_output_bytes']
        # Exactly the allowlisted statements, in order: nothing can change the population.
        assert rig.executed() == FULL_SEQUENCE
        connect = [e for e in rig.events() if e['event'] == 'connect']
        assert len(connect) == 1
        assert connect[0]['kwargs'] == {'async_': True, 'connect_timeout': 2, 'sslmode': 'require',
                                        'options': contract.CONNECT_OPTIONS}
        assert connect[0]['dsn_sha256'] == hashlib.sha256(DSN.encode()).hexdigest()
        # Owned close happened, once, and the child is gone.
        assert [e['event'] for e in rig.events()].count('close') == 1
        _assert_gone(rig.child_pid())
        raw = rig.receipt()
        disk = json.loads(raw)
        assert disk['verdict'] == 'NO_RESULT' and disk['reason'] == 'OWNER_CONFIRMATION_REQUIRED'
        plans = contract.accept(result, raw)
        assert set(plans) == {'query3', 'candidateC'}
        assert sum(p.stat().st_size for p in rig.receipts.iterdir()) <= contract.LIMITS['combined_output_bytes']

    def test_no_credential_reaches_argv_env_logs_receipts_or_return(self, tmp_path, monkeypatch, capfd):
        monkeypatch.setenv('DATABASE_URL', 'postgres://ambient@leak/db')
        monkeypatch.setenv('PGPASSWORD', 'ambient-password')
        rig = Rig(tmp_path, monkeypatch, {'explain_query3': [{'raise': True}]})
        result = rig.run()
        assert result['verdict'] == 'NO_RESULT' and result['reason'] == 'NONZERO_EXIT'
        launch = [e for e in rig.events() if e['event'] == 'launch'][0]
        assert launch['argv'] == [str(TOOL / 'child.py')]
        # Exactly what the interpreter itself shows for CHILD_ENV, nothing from this process.
        baseline = subprocess.run(PRODUCTION_ARGV()[:-1] + ['-c', 'import os,json;print(json.dumps(sorted(os.environ)))'],
                                  env=supervisor.CHILD_ENV, capture_output=True, timeout=10)
        assert launch['env_keys'] == json.loads(baseline.stdout)
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
        assert result['owner_completed'] is True and result['attempt_consumed'] is False
        assert not rig.log.exists() and not rig.receipts.exists()

    @pytest.mark.parametrize('adm,owner,code', [
        (admission(binding_sha256='1' * 64), OWNER, 'BINDING_REFUSED'),
        (admission(), 'measurement-ctl-OTHER', 'OWNER_REFUSED'),
        (admission(window={'start_unix': BASE - 400, 'end_unix': BASE - 100}), OWNER, 'WINDOW_REFUSED'),
    ])
    def test_a_refused_admission_makes_no_connection_and_consumes_nothing(self, tmp_path, monkeypatch, adm, owner, code):
        rig = Rig(tmp_path, monkeypatch)
        result = rig.run(adm=adm, owner=owner)
        assert result['reason'] == code and result['attempt_consumed'] is False
        assert not rig.log.exists() and not rig.receipts.exists()

    def test_the_child_itself_refuses_a_bad_admission_before_importing_a_driver(self, tmp_path, monkeypatch):
        rig = Rig(tmp_path, monkeypatch)
        payload = json.dumps({'credential': DSN, 'admission': admission(subject='683'), 'owner': OWNER,
                              'output_budget': 100_000}).encode()
        proc = subprocess.run(supervisor._child_argv(), input=payload, capture_output=True,
                              env=supervisor.CHILD_ENV, timeout=10)
        assert proc.returncode == 1 and proc.stderr == b''
        assert proc.stdout == b'{"kind":"refusal","reason":"CHILD_REFUSED"}\n'
        assert [e['event'] for e in rig.events()] == ['launch']  # no connect

    def test_one_attempt_per_admission(self, tmp_path, monkeypatch):
        rig = Rig(tmp_path, monkeypatch)
        assert rig.run()['verdict'] == 'PLAN_ONLY_PENDING_ROOT_REVIEW'
        again = rig.run()
        assert again['verdict'] == 'NO_RESULT' and again['reason'] == 'SINGLE_USE_REFUSED'
        assert [e['event'] for e in rig.events()].count('connect') == 1

    def test_a_first_plan_error_stops_before_the_second_plan(self, tmp_path, monkeypatch):
        rig = Rig(tmp_path, monkeypatch, {'explain_query3': [{'raise': True}]})
        result = rig.run()
        assert result['verdict'] == 'NO_RESULT' and result['candidate_sha256'] is None
        assert rig.executed() == FULL_SEQUENCE[:5]
        assert 'explain_candidateC' not in rig.executed()
        assert [e['event'] for e in rig.events()].count('close') == 1
        disk = json.loads(rig.receipt())
        assert disk['verdict'] == 'NO_RESULT' and 'candidate_evidence' not in disk

    @pytest.mark.parametrize('behavior,last', [
        ({'connect': [{'bump': 100, 'stall': True}]}, None),
        ({'explain_query3': [{'bump': 100, 'stall': True}]}, 'explain_query3'),
        ({'explain_candidateC': [{'bump': 100, 'stall': True}]}, 'explain_candidateC'),
        ({'rollback': [{}, {'bump': 100, 'stall': True}]}, 'rollback'),
        ({'close': [{'bump': 100, 'stall': True}]}, 'rollback'),
    ])
    def test_driver_planning_and_close_stalls_end_in_no_result_within_the_wall(self, tmp_path, monkeypatch, behavior, last):
        rig = Rig(tmp_path, monkeypatch, behavior)
        result = rig.run()
        assert result['verdict'] == 'NO_RESULT' and result['candidate_sha256'] is None
        assert rig.real_seconds < 10
        executed = rig.executed()
        assert (executed[-1] if executed else None) == last
        _assert_gone(rig.child_pid())
        with pytest.raises(contract.Refused, match='ACCEPT_REFUSED'):
            contract.accept(result, rig.receipt())

    def test_the_wall_is_one_total_across_both_statements(self, tmp_path, monkeypatch):
        # Control: one 7 s plan fits the one wall.
        control = Rig(tmp_path / 'control', monkeypatch, {'explain_query3': [{'bump': 7}]})
        assert control.run()['verdict'] == 'PLAN_ONLY_PENDING_ROOT_REVIEW'
        # Two 7 s plans do not: no per-plan allowance, no late success.
        both = Rig(tmp_path / 'both', monkeypatch, {'explain_query3': [{'bump': 7}], 'explain_candidateC': [{'bump': 7}]})
        result = both.run()
        assert result['verdict'] == 'NO_RESULT' and result['reason'] in ('WALL_EXPIRED', 'WALL_EXPIRED_OR_UNAVAILABLE')
        assert result['candidate_sha256'] is None

    def test_cleanup_reserve_is_not_spare_time_for_the_child(self, tmp_path, monkeypatch):
        """The child finishes complete and clean, but only after its share of the wall
        (deadline - cleanup reserve) has passed. The clock moves at the instant the worker
        first sees the exit, so no further loop pass can notice it: only the post-loop
        check stands between this and a success granted out of the cleanup reserve."""
        rig = Rig(tmp_path, monkeypatch)
        real_poll = subprocess.Popen.poll
        moved = {'done': False}

        def poll_sees_exit_late(self):
            code = real_poll(self)
            if code is not None and not moved['done']:
                moved['done'] = True
                rig.clock.write_text('13.6')
            return code
        monkeypatch.setattr(subprocess.Popen, 'poll', poll_sees_exit_late)
        result = rig.run()
        assert rig.executed() == FULL_SEQUENCE
        assert result['verdict'] == 'NO_RESULT' and result['reason'] == 'WALL_EXPIRED', result
        assert result['owner_completed'] is True  # refused in time, not killed
        assert 'candidate_evidence' not in json.loads(rig.receipt())

    def test_a_stalled_receipt_write_returns_no_result_and_kills_only_the_owned_group(self, tmp_path, monkeypatch):
        rig = Rig(tmp_path, monkeypatch)
        real_fsync = os.fsync
        calls = {'n': 0}

        def stalling_fsync(fd):
            calls['n'] += 1
            if calls['n'] == 3:  # initial receipt file + its directory, then the final receipt
                rig.clock.write_text('100')
                time.sleep(60)
            return real_fsync(fd)
        monkeypatch.setattr(supervisor.os, 'fsync', stalling_fsync)
        result = rig.run()
        assert result['verdict'] == 'NO_RESULT' and result['owner_completed'] is False
        assert rig.real_seconds < 10
        disk = json.loads(rig.receipt())
        assert disk['verdict'] == 'NO_RESULT' and disk['reason'] == 'INCOMPLETE'

    def test_a_receipt_published_after_the_owner_deadline_is_never_accepted(self, tmp_path, monkeypatch):
        rig = Rig(tmp_path, monkeypatch)
        real_replace = os.replace

        def late_replace(src, dst, *a, **k):
            real_replace(src, dst, *a, **k)
            if str(dst).endswith('adm-847-test-0001.json'):
                path = rig.clock
                path.write_text(repr(float(path.read_text()) + 100))
        monkeypatch.setattr(supervisor.os, 'replace', late_replace)
        result = rig.run()
        assert result['verdict'] == 'NO_RESULT' and result['owner_completed'] is False
        raw = rig.receipt()
        disk = json.loads(raw)
        # The candidate reached the disk, and still is not a result.
        assert disk['reason'] == 'OWNER_CONFIRMATION_REQUIRED' and 'candidate_evidence' in disk
        with pytest.raises(contract.Refused, match='ACCEPT_REFUSED'):
            contract.accept(result, raw)
        forged_late = dict(verdict='PLAN_ONLY_PENDING_ROOT_REVIEW', owner_completed=True, elapsed_seconds=15.2,
                           candidate_sha256=hashlib.sha256(raw).hexdigest(), admission_id='adm-847-test-0001')
        with pytest.raises(contract.Refused, match='ACCEPT_REFUSED'):
            contract.accept(forged_late, raw)
        with pytest.raises(contract.Refused, match='ACCEPT_REFUSED'):
            contract.accept(dict(forged_late, elapsed_seconds=3.0), raw + b' \n')

    def test_the_owner_itself_refuses_a_summary_that_arrives_after_its_stop(self, tmp_path, monkeypatch):
        """The worker checks the wall before writing its summary, so this isolates the
        OWNER's own check: the clock crosses the stop exactly when the owner observes
        the worker's exit. Only the owner process moves it (the worker reaps too)."""
        rig = Rig(tmp_path, monkeypatch)
        real_waitpid = os.waitpid
        owner_pid = os.getpid()

        def waitpid_observed_late(pid, options):
            got, status = real_waitpid(pid, options)
            if got and os.getpid() == owner_pid:
                rig.clock.write_text('100')
            return got, status
        monkeypatch.setattr(supervisor.os, 'waitpid', waitpid_observed_late)
        result = rig.run()
        assert result['verdict'] == 'NO_RESULT' and result['owner_completed'] is False
        assert rig.executed() == FULL_SEQUENCE
        disk = json.loads(rig.receipt())
        assert disk['reason'] == 'OWNER_CONFIRMATION_REQUIRED'  # complete on disk, still refused
        with pytest.raises(contract.Refused, match='ACCEPT_REFUSED'):
            contract.accept(result, rig.receipt())

    @pytest.mark.parametrize('behavior,reason', [
        ({'explain_query3': [{'plan': [{'Plan': {'Node Type': 'Aggregate', 'Actual Rows': 1}}]}]}, 'NONZERO_EXIT'),
        ({'explain_candidateC': [{'plan': {'Plan': {'Node Type': 'Aggregate'}}}]}, 'NONZERO_EXIT'),
        ({'explain_candidateC': [{'truncate': True}]}, 'EVIDENCE_REFUSED'),
        ({'guard': [{'row': ('off', '2s', '500ms')}]}, 'NONZERO_EXIT'),
        ({'rollback': [{'status': 'COMMIT'}]}, 'NONZERO_EXIT'),
        ({'close': [{'closed': 0}]}, 'NONZERO_EXIT'),
        ({'explain_candidateC': [{'stderr': 'NOTICE: something\n'}]}, 'STDERR_REFUSED'),
    ])
    def test_malformed_truncated_unguarded_or_noisy_runs_are_no_result(self, tmp_path, monkeypatch, behavior, reason):
        rig = Rig(tmp_path, monkeypatch, behavior)
        result = rig.run()
        assert result['verdict'] == 'NO_RESULT' and result['reason'] == reason, result
        assert 'candidate_evidence' not in json.loads(rig.receipt())

    def test_one_ledger_bounds_output_and_receipts_together(self, tmp_path, monkeypatch):
        cap = contract.LIMITS['combined_output_bytes']
        # Control: two 100 KB plans fit stream + receipt inside one 512 KiB ledger.
        ok = Rig(tmp_path / 'ok', monkeypatch, {'explain_query3': [{'plan_pad': 100_000}],
                                                'explain_candidateC': [{'plan_pad': 100_000}]})
        result = ok.run()
        assert result['verdict'] == 'PLAN_ONLY_PENDING_ROOT_REVIEW', result
        assert result['combined_output_bytes'] <= cap
        # Two 150 KB plans fit the stream but not stream + receipt: refused, not truncated.
        big = Rig(tmp_path / 'big', monkeypatch, {'explain_query3': [{'plan_pad': 150_000}],
                                                  'explain_candidateC': [{'plan_pad': 150_000}]})
        result = big.run()
        assert result['verdict'] == 'NO_RESULT' and result['reason'] == 'OUTPUT_EXCEEDED', result
        assert result['combined_output_bytes'] <= cap
        disk = json.loads(big.receipt())
        assert disk['reason'] == 'OUTPUT_EXCEEDED' and 'candidate_evidence' not in disk
        # One plan past the child's budget, unstalled: the child's budget is its share of
        # this ledger, so it refuses the record before writing it and candidate C never
        # runs. TestSerializedOutputBound meters this specimen's completed writes.
        huge = Rig(tmp_path / 'huge', monkeypatch, {'explain_query3': [{'plan_pad': 515_000}]})
        result = huge.run()
        assert result['verdict'] == 'NO_RESULT' and result['reason'] == 'NONZERO_EXIT', result
        assert result['received_bytes'] < 1000 and result['combined_output_bytes'] <= cap
        assert 'explain_candidateC' not in huge.executed()
        # One record past the child's own ceiling never reaches the pipe at all.
        over = Rig(tmp_path / 'over', monkeypatch, {'explain_query3': [{'plan_pad': 530_000}]})
        result = over.run()
        assert result['verdict'] == 'NO_RESULT' and result['reason'] == 'NONZERO_EXIT', result
        assert result['received_bytes'] < 1000

    def test_the_real_15_second_wall_holds_on_a_real_stall(self, tmp_path, monkeypatch):
        """No virtual time: the worker's own final receipt fsync hangs for real. The owner
        must kill and reap its worker group and return inside the real 15 s constant."""
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
        assert rig.executed() == FULL_SEQUENCE  # the plans ran; the late receipt still grants nothing
        _assert_gone(rig.child_pid())


# ─── serialized output: what the child WRITES, not what the worker read ─────────
#
# Root's 4bbe replay: completed child stdout writes reached 524,858 bytes (over the
# 524,288 cap) while the owner reported received 511,968 / combined 518,183, because
# the worker stopped reading at its allowance and the rest sat in the pipe. These
# tests meter writes the CHILD completes into its parent's pipes (after the real write
# returns), give the child free advance with one 150 ms worker-read delay, and never
# stall it. Nothing here widens the cap or the wall.

CAP = contract.LIMITS['combined_output_bytes']
# The most the child may ever write: its budget is this minus the first receipt.
STREAM = CAP - supervisor.OWNER_RESERVE - supervisor.REFUSAL_RESERVE - supervisor.PRESTART_RESERVE


def _delay_worker_read_once(rig, monkeypatch, at):
    """Root's scheduling control: one 150 ms sleep in the WORKER once it has read `at`
    bytes. The worker is a forked process, so the delay is recorded in the rig's log."""
    owner = os.getpid()
    real_read = os.read
    state = {'seen': 0, 'delayed': False}

    def read(fd, n):
        raw = real_read(fd, n)
        if os.getpid() != owner:
            state['seen'] += len(raw)
            if state['seen'] >= at and not state['delayed']:
                state['delayed'] = True
                with open(rig.log, 'a') as f:
                    f.write(json.dumps({'event': 'worker_read_delay', 'seen': state['seen']}) + '\n')
                time.sleep(.15)
        return raw
    monkeypatch.setattr(supervisor.os, 'read', read)


def _delayed(rig):
    return any(e['event'] == 'worker_read_delay' for e in rig.events())


def _assert_counted_and_bounded(rig, result):
    """Every byte the child wrote is inside its budget and inside the reported ledger."""
    written = rig.written()
    assert written <= STREAM, (written, STREAM)
    assert result['received_bytes'] == written, (result, written)
    assert written + rig.disk() + supervisor.OWNER_RESERVE <= result['combined_output_bytes'] <= CAP, result


class TestSerializedOutputBound:
    def test_roots_4bbe_replay_stops_inside_the_childs_budget(self, tmp_path, monkeypatch):
        rig = Rig(tmp_path, monkeypatch, {'explain_query3': [{'plan_pad': 523_000}],
                                          'explain_candidateC': [{'plan_pad': 1000}]}, meter=True)
        _delay_worker_read_once(rig, monkeypatch, 510_000)
        result = rig.run()
        assert result['verdict'] == 'NO_RESULT' and result['reason'] == 'NONZERO_EXIT', result
        assert result['exit_code'] == 1 and result['owner_completed'] is True
        # Root's delay point (510,000 bytes read) is never reached: nothing near it was written.
        assert not _delayed(rig)
        _assert_counted_and_bounded(rig, result)
        # The oversize record was refused before it was even attempted; the first error stops.
        assert rig.written('attempt') == rig.written() < 1000
        assert 'explain_candidateC' not in rig.executed()

    @pytest.mark.parametrize('pads,delay_at,reason,exit_code', [
        ((515_000, None), 1, 'NONZERO_EXIT', 1),            # the old specimen, without its stall
        ((300_000, 300_000), 250_000, 'NONZERO_EXIT', 1),   # each fits, the sum does not
        ((400_000, 110_000), 400_000, 'NONZERO_EXIT', 1),   # the sum crosses near the cap
        ((495_000, 1_000), 440_000, 'OUTPUT_EXCEEDED', 0),  # the stream fits; stream + receipt does not
    ])
    def test_an_unstalled_child_never_writes_past_its_budget(self, tmp_path, monkeypatch, pads, delay_at,
                                                             reason, exit_code):
        behavior = {'explain_query3': [{'plan_pad': pads[0]}]}
        if pads[1]:
            behavior['explain_candidateC'] = [{'plan_pad': pads[1]}]
        rig = Rig(tmp_path, monkeypatch, behavior, meter=True)
        _delay_worker_read_once(rig, monkeypatch, delay_at)
        result = rig.run()
        assert result['verdict'] == 'NO_RESULT' and result['reason'] == reason, result
        assert result['exit_code'] == exit_code
        assert _delayed(rig) and not any(e['event'] == 'stall' for e in rig.events())
        _assert_counted_and_bounded(rig, result)
        assert rig.written('attempt') == rig.written()
        if exit_code == 1:
            assert rig.executed()[-1] == ('explain_query3' if pads[1] is None else 'explain_candidateC')

    def test_control_a_large_run_within_budget_is_accepted_and_counted_exactly(self, tmp_path, monkeypatch):
        rig = Rig(tmp_path, monkeypatch, {'explain_query3': [{'plan_pad': 100_000}],
                                          'explain_candidateC': [{'plan_pad': 100_000}]}, meter=True)
        _delay_worker_read_once(rig, monkeypatch, 100_000)
        result = rig.run()
        assert result['verdict'] == 'PLAN_ONLY_PENDING_ROOT_REVIEW', result
        assert _delayed(rig) and result['exit_code'] == 0
        _assert_counted_and_bounded(rig, result)
        assert rig.written() > 200_000 and rig.executed() == FULL_SEQUENCE
        assert set(contract.accept(result, rig.receipt())) == {'query3', 'candidateC'}

    def test_stderr_spends_the_same_budget_as_the_records(self, tmp_path, monkeypatch):
        rig = Rig(tmp_path, monkeypatch, {'connect': [{'stderr': 'n' * 12_000}],
                                          'explain_query3': [{'plan_pad': 500_000}]}, meter=True)
        result = rig.run()
        # 500 KB fits the budget alone; after 12 KB of forwarded stderr it does not.
        assert result['verdict'] == 'NO_RESULT' and result['reason'] == 'NONZERO_EXIT', result
        assert rig.written(stream='stderr') == 12_000
        _assert_counted_and_bounded(rig, result)
        assert 'explain_candidateC' not in rig.executed()

    def test_control_small_stderr_still_reaches_the_worker_and_refuses(self, tmp_path, monkeypatch):
        rig = Rig(tmp_path, monkeypatch, {'connect': [{'stderr': 'n' * 12_000}]}, meter=True)
        result = rig.run()
        assert result['verdict'] == 'NO_RESULT' and result['reason'] == 'STDERR_REFUSED', result
        assert result['exit_code'] == 0 and rig.executed() == FULL_SEQUENCE
        assert rig.written(stream='stderr') == 12_000
        _assert_counted_and_bounded(rig, result)

    def test_a_stderr_flood_never_reaches_the_parent(self, tmp_path, monkeypatch):
        """300 KB on fd 2 lands in the child's private pipe; its writer blocks and the wall ends it."""
        # 13.6 s: past the child's share of the wall, inside the cleanup reserve. Whether the
        # worker's own receipt fsyncs then fit the reserve's real 1.35 s is the runner's disk,
        # not this property, so either wall outcome is accepted.
        rig = Rig(tmp_path, monkeypatch, {'begin': [{'stderr_flood': 300_000, 'bump': 13.6}]}, meter=True)
        result = rig.run()
        assert result['verdict'] == 'NO_RESULT', result
        assert result['reason'] in ('WALL_EXPIRED', 'WALL_EXPIRED_OR_UNAVAILABLE'), result
        assert any(e['event'] == 'stderr_flood' for e in rig.events())
        # Nothing was even attempted toward the parent, whichever way the wall ended it.
        assert rig.written('attempt') == rig.written() == 0
        if result['owner_completed']:
            _assert_counted_and_bounded(rig, result)
        _assert_gone(rig.child_pid())

    def test_a_library_writing_straight_to_stdout_is_counted_never_hidden(self, tmp_path, monkeypatch):
        """Residual: fd 1 writes that are not child.py records are not pre-charged. The worker
        refuses at its allowance and drains to EOF, so the report covers every byte written."""
        rig = Rig(tmp_path, monkeypatch, {'begin': [{'flood': 600_000}]}, meter=True)
        result = rig.run()
        assert result['verdict'] == 'NO_RESULT' and result['reason'] == 'OUTPUT_EXCEEDED', result
        assert rig.written() <= result['received_bytes'] <= rig.written('attempt')
        assert result['combined_output_bytes'] >= result['received_bytes'] + rig.disk() + supervisor.OWNER_RESERVE
        _assert_gone(rig.child_pid())

    def test_control_start_up_stderr_inside_its_reserve_is_counted_and_refused(self, tmp_path, monkeypatch):
        rig = Rig(tmp_path, monkeypatch, meter=True, prestart=100)
        result = rig.run()
        assert result['verdict'] == 'NO_RESULT' and result['reason'] == 'STDERR_REFUSED', result
        assert rig.written(stream='stderr') == 100
        _assert_counted_and_bounded(rig, result)

    def test_start_up_stderr_past_its_reserve_is_reported_as_an_overrun(self, tmp_path, monkeypatch):
        """Residual: interpreter output before child.py's first line is outside the child's
        budget. Past PRESTART_RESERVE it is still counted, and the report says over the cap."""
        rig = Rig(tmp_path, monkeypatch, {'explain_query3': [{'plan_pad': 300_000}],
                                          'explain_candidateC': [{'plan_pad': 200_000}]},
                  meter=True, prestart=30_000)
        result = rig.run()
        assert result['verdict'] == 'NO_RESULT' and result['reason'] == 'OUTPUT_EXCEEDED', result
        assert rig.written() <= result['received_bytes'] <= rig.written('attempt')
        assert result['combined_output_bytes'] >= result['received_bytes'] + rig.disk() + supervisor.OWNER_RESERVE
        assert result['combined_output_bytes'] > CAP
        _assert_gone(rig.child_pid())

    @pytest.mark.parametrize('budget', [None, True, 100_000.0, 43, CAP + 1, -1])
    def test_the_child_refuses_a_missing_or_invalid_budget_before_any_driver(self, tmp_path, monkeypatch, budget):
        rig = Rig(tmp_path, monkeypatch)
        request = {'credential': DSN, 'admission': admission(), 'owner': OWNER}
        if budget is not None:
            request['output_budget'] = budget
        proc = subprocess.run(supervisor._child_argv(), input=json.dumps(request).encode(), capture_output=True,
                              env=supervisor.CHILD_ENV, timeout=10)
        assert proc.returncode == 1 and proc.stderr == b''
        assert proc.stdout == b'{"kind":"refusal","reason":"CHILD_REFUSED"}\n'
        assert [e['event'] for e in rig.events()] == ['launch']

    def test_the_refusal_is_held_back_from_the_childs_budget(self, tmp_path, monkeypatch):
        rig = Rig(tmp_path, monkeypatch)
        guard = (json.dumps({'kind': 'guard', 'plan': 'query3', 'row': list(contract.GUARD_ROW)},
                            separators=(',', ':')) + '\n').encode()
        refusal = b'{"kind":"refusal","reason":"CHILD_REFUSED"}\n'
        # Room for the guard record, but then not for the refusal: so the guard is never written.
        request = {'credential': DSN, 'admission': admission(), 'owner': OWNER,
                   'output_budget': len(guard) + len(refusal) - 1}
        proc = subprocess.run(supervisor._child_argv(), input=json.dumps(request).encode(), capture_output=True,
                              env=supervisor.CHILD_ENV, timeout=10)
        assert proc.returncode == 1 and proc.stderr == b'' and proc.stdout == refusal
        # Control: one byte more and the guard fits beside the refusal.
        rig = Rig(tmp_path / 'control', monkeypatch)
        request['output_budget'] += 1
        proc = subprocess.run(supervisor._child_argv(), input=json.dumps(request).encode(), capture_output=True,
                              env=supervisor.CHILD_ENV, timeout=10)
        assert proc.returncode == 1 and proc.stdout == guard + refusal

    def test_the_child_alone_never_writes_more_than_its_budget(self, tmp_path, monkeypatch):
        rig = Rig(tmp_path, monkeypatch)
        request = {'credential': DSN, 'admission': admission(), 'owner': OWNER, 'output_budget': 200}
        proc = subprocess.run(supervisor._child_argv(), input=json.dumps(request).encode(), capture_output=True,
                              env=supervisor.CHILD_ENV, timeout=10)
        # The guard record fits; the plan does not; the refusal was held back from the start.
        assert proc.returncode == 1 and proc.stderr == b'' and len(proc.stdout) <= 200
        assert proc.stdout.startswith(b'{"kind":"guard"')
        assert proc.stdout.endswith(b'{"kind":"refusal","reason":"CHILD_REFUSED"}\n')
        assert 'explain_candidateC' not in rig.executed()


# ─── the owner's own setup and finalization ──────────────────────────────────
#
# The worker and child stall tests above never touch the CALLER's process. These
# fault only the owner (gated on its pid): its selector/pipe release after the
# success decision used to run in a `finally` after the elapsed stamp, and its
# setup after fork() used to sit outside every cleanup. Each adverse case has an
# unchanged positive control through the same seam.

def _owned_forks(monkeypatch):
    real_fork = os.fork
    owned = []

    def record_fork():
        pid = real_fork()
        if pid > 0:
            owned.append(pid)
        return pid
    monkeypatch.setattr(supervisor.os, 'fork', record_fork)
    return owned


def _assert_reaped(pid):
    # Reaped by the owner: the pid is no longer our child at all.
    with pytest.raises(ChildProcessError):
        os.waitpid(pid, os.WNOHANG)


class _FinalRelease:
    """Wraps the owner's selector; `fault` fires in the owner on its final close or on
    the pipe close that follows it. 'late' spends 20 s of the one wall there; 'raise'
    fails after really closing; None is the positive control."""

    def __init__(self, rig, monkeypatch, *, where, fault):
        self.rig, self.where, self.fault = rig, where, fault
        self.owner_pid = os.getpid()
        self.selector_closed = False
        self.fired = 0
        factory = supervisor.selectors.DefaultSelector
        real_close = os.close
        outer = self

        class Selector:
            def __init__(self):
                self.real = factory()

            def __getattr__(self, name):
                return getattr(self.real, name)

            def close(self):
                self.real.close()
                if os.getpid() == outer.owner_pid:
                    outer.selector_closed = True
                    if outer.where == 'selector':
                        outer.fire()

        def close(fd):
            real_close(fd)
            if (outer.where == 'pipe' and outer.selector_closed and not outer.fired
                    and os.getpid() == outer.owner_pid):
                outer.fire()
        monkeypatch.setattr(supervisor.selectors, 'DefaultSelector', Selector)
        monkeypatch.setattr(supervisor.os, 'close', close)

    def fire(self):
        self.fired += 1
        if self.fault == 'late':
            self.rig.clock.write_text(repr(float(self.rig.clock.read_text()) + 20))
        elif self.fault == 'raise':
            raise OSError('injected owner release failure')


class TestOwnerFinalization:
    @pytest.mark.parametrize('where', ['selector', 'pipe'])
    def test_control_the_same_release_seam_unfaulted_still_succeeds(self, tmp_path, monkeypatch, where):
        rig = Rig(tmp_path, monkeypatch)
        seam = _FinalRelease(rig, monkeypatch, where=where, fault=None)
        result = rig.run()
        assert seam.selector_closed
        assert result['verdict'] == 'PLAN_ONLY_PENDING_ROOT_REVIEW', result
        assert result['owner_completed'] is True and 0 < result['elapsed_seconds'] < 15
        assert set(contract.accept(result, rig.receipt())) == {'query3', 'candidateC'}

    @pytest.mark.parametrize('where', ['selector', 'pipe'])
    def test_a_late_owner_release_is_no_result_and_its_time_is_counted(self, tmp_path, monkeypatch, where):
        """Root d072 replay: 20 s spent in the owner's final close used to return
        PLAN_ONLY_PENDING_ROOT_REVIEW stamped ~0.08 s, and accept() took both plans."""
        rig = Rig(tmp_path, monkeypatch)
        seam = _FinalRelease(rig, monkeypatch, where=where, fault='late')
        began = supervisor._now()
        result = rig.run()
        actual = supervisor._now() - began
        assert seam.fired == 1 and actual > 15
        assert result['verdict'] == 'NO_RESULT' and result['reason'] == 'OWNER_FINALIZATION_LATE', result
        assert result['owner_completed'] is False and result['candidate_sha256'] is None
        assert result['elapsed_seconds'] > 15  # the stamp includes the release, not just the read
        assert actual - result['elapsed_seconds'] < 1
        # The worker had finished cleanly: the disk candidate exists and still is not a result.
        assert json.loads(rig.receipt())['reason'] == 'OWNER_CONFIRMATION_REQUIRED'
        with pytest.raises(contract.Refused, match='ACCEPT_REFUSED'):
            contract.accept(result, rig.receipt())
        _assert_gone(rig.child_pid())

    @pytest.mark.parametrize('where', ['selector', 'pipe'])
    def test_a_failed_owner_release_is_no_result(self, tmp_path, monkeypatch, where):
        rig = Rig(tmp_path, monkeypatch)
        seam = _FinalRelease(rig, monkeypatch, where=where, fault='raise')
        result = rig.run()
        assert seam.fired == 1
        assert result['verdict'] == 'NO_RESULT' and result['reason'] == 'OWNER_CLEANUP_FAILED', result
        assert result['owner_completed'] is False and result['elapsed_seconds'] < 15
        with pytest.raises(contract.Refused, match='ACCEPT_REFUSED'):
            contract.accept(result, rig.receipt())

    def test_control_recording_forks_alone_changes_nothing(self, tmp_path, monkeypatch):
        rig = Rig(tmp_path, monkeypatch)
        owned = _owned_forks(monkeypatch)
        result = rig.run()
        assert result['verdict'] == 'PLAN_ONLY_PENDING_ROOT_REVIEW', result
        assert len(owned) == 1
        _assert_reaped(owned[0])

    @pytest.mark.parametrize('seam,phase', [
        ('DefaultSelector', 'OWNER_SETUP_FAILED'),   # Root d072 setup replay
        ('set_blocking', 'OWNER_SETUP_FAILED'),
        ('read', 'OWNER_READ_FAILED'),
    ])
    def test_an_owner_exception_after_fork_reclaims_the_worker_and_returns_no_result(
            self, tmp_path, monkeypatch, seam, phase):
        """The worker exists once fork() returns: an owner exception from there on is
        NO_RESULT, never an escape, and the owned group (worker + stalled child) dies."""
        rig = Rig(tmp_path, monkeypatch, {'connect': [{'stall': True}]})
        owned = _owned_forks(monkeypatch)
        owner_pid = os.getpid()
        target = supervisor.selectors if seam == 'DefaultSelector' else supervisor.os
        real = getattr(target, seam)

        def broken(*a, **k):
            if os.getpid() == owner_pid:
                raise OSError(f'injected owner {seam} failure')
            return real(*a, **k)
        if seam == 'read':
            # Fail the owner's read only once the child is stalled, so its group is real.
            def broken(*a, **k):  # noqa: F811
                if os.getpid() == owner_pid and any(e['event'] == 'stall' for e in rig.events()):
                    raise OSError('injected owner read failure')
                return real(*a, **k)
            real_select = supervisor.selectors.DefaultSelector

            class Ready:
                def __init__(self):
                    self.real = real_select()

                def __getattr__(self, name):
                    return getattr(self.real, name)

                def select(self, timeout=None):
                    got = self.real.select(timeout)
                    if os.getpid() == owner_pid and any(e['event'] == 'stall' for e in rig.events()):
                        return got or [(None, 0)]
                    return got
            monkeypatch.setattr(supervisor.selectors, 'DefaultSelector', Ready)
        monkeypatch.setattr(target, seam, broken)
        result = rig.run()
        assert result['verdict'] == 'NO_RESULT' and result['reason'] == phase, result
        assert result['owner_completed'] is False and result['candidate_sha256'] is None
        assert result['worker_reaped'] is True and rig.real_seconds < 10
        assert len(owned) == 1
        _assert_reaped(owned[0])
        _assert_gone(rig.child_pid())
        settled = len(rig.events())
        time.sleep(.3)
        assert len(rig.events()) == settled  # nothing owned is still running

    def test_the_first_owner_failure_is_kept_when_cleanup_also_fails(self, tmp_path, monkeypatch):
        rig = Rig(tmp_path, monkeypatch)
        owned = _owned_forks(monkeypatch)
        owner_pid = os.getpid()
        real_blocking = os.set_blocking
        real_close = os.close

        def broken_blocking(fd, flag):
            if os.getpid() == owner_pid:
                raise OSError('first')
            return real_blocking(fd, flag)
        failed_closes = []

        def broken_close(fd):
            real_close(fd)
            if os.getpid() == owner_pid and owned:
                failed_closes.append(fd)
                raise OSError('second')
        monkeypatch.setattr(supervisor.os, 'set_blocking', broken_blocking)
        monkeypatch.setattr(supervisor.os, 'close', broken_close)
        result = rig.run()
        assert failed_closes  # the release did fail too
        assert result['verdict'] == 'NO_RESULT' and result['reason'] == 'OWNER_SETUP_FAILED', result
        _assert_reaped(owned[0])

    def test_a_refused_pipe_never_forks(self, tmp_path, monkeypatch):
        rig = Rig(tmp_path, monkeypatch)
        owned = _owned_forks(monkeypatch)

        def no_pipe():
            raise OSError('EMFILE')
        monkeypatch.setattr(supervisor.os, 'pipe', no_pipe)
        result = rig.run()
        assert result['verdict'] == 'NO_RESULT' and result['reason'] == 'PIPE_REFUSED'
        assert result['attempt_consumed'] is False and owned == []
        assert not rig.log.exists() and not rig.receipts.exists()

    def test_a_refused_fork_closes_both_pipe_ends_and_says_fork(self, tmp_path, monkeypatch):
        rig = Rig(tmp_path, monkeypatch)
        real_pipe = os.pipe
        made = []

        def pipe():
            made.extend(real_pipe())
            return tuple(made)

        def no_fork():
            raise OSError('EAGAIN')
        monkeypatch.setattr(supervisor.os, 'pipe', pipe)
        monkeypatch.setattr(supervisor.os, 'fork', no_fork)
        result = rig.run()
        assert result['verdict'] == 'NO_RESULT' and result['reason'] == 'FORK_REFUSED'
        assert result['attempt_consumed'] is False and len(made) == 2
        for fd in made:
            with pytest.raises(OSError):
                os.fstat(fd)
        assert not rig.log.exists() and not rig.receipts.exists()


# ─── entry surface ───────────────────────────────────────────────────────────

class TestEntrySurface:
    def test_run_attempt_takes_only_credential_admission_and_owner(self):
        params = inspect.signature(supervisor.run_attempt).parameters
        assert list(params) == ['credential', 'admission', 'owner']
        assert all(p.kind is inspect.Parameter.KEYWORD_ONLY and p.default is inspect.Parameter.empty
                   for p in params.values())

    def test_importing_or_invoking_the_tool_launches_nothing(self, tmp_path):
        env = {'PATH': '/usr/bin:/bin', 'HOME': str(tmp_path)}
        for script in ('supervisor.py', 'contract.py'):
            proc = subprocess.run([sys.executable, '-I', str(TOOL / script)], capture_output=True,
                                  env=env, cwd=tmp_path, timeout=10)
            assert proc.stdout == b'' and proc.stderr == b''
            assert proc.returncode == (2 if script == 'supervisor.py' else 0)
        importer = ('import importlib.util as u;'
                    f's=u.spec_from_file_location("s",{str(TOOL / "supervisor.py")!r});'
                    'm=u.module_from_spec(s);s.loader.exec_module(m)')
        proc = subprocess.run([sys.executable, '-I', '-c', importer], capture_output=True, env=env,
                              cwd=tmp_path, timeout=10)
        assert proc.returncode == 0 and proc.stdout == b'' and proc.stderr == b''
        proc = subprocess.run([sys.executable, '-I', str(TOOL / 'child.py')], input=b'', capture_output=True,
                              env=env, cwd=tmp_path, timeout=10)
        assert proc.returncode == 1 and proc.stdout == b'{"kind":"refusal","reason":"CHILD_REFUSED"}\n'
        assert list(tmp_path.iterdir()) == []  # no ~/.bainluck, no receipt, no marker

    def test_the_child_interpreter_cannot_be_shadowed_from_beside_the_script(self, tmp_path):
        argv = PRODUCTION_ARGV()
        assert argv == [sys.executable, '-E', '-P', str(TOOL / 'child.py')]
        (tmp_path / 'psycopg2.py').write_text("raise SystemExit('SHADOWED')\n")
        (tmp_path / 'probe.py').write_text("import sys\nprint(sys.path[0] != %r)\n" % str(tmp_path))
        proc = subprocess.run(argv[:-1] + [str(tmp_path / 'probe.py')], capture_output=True,
                              env=supervisor.CHILD_ENV, timeout=10)
        assert proc.stdout == b'True\n' and proc.returncode == 0

    def test_libpq_defaults_point_at_paths_that_cannot_exist(self):
        # /dev/null made real libpq print "password file ... is not a plain file" on
        # stderr, which (correctly) refused every real attempt in the local rig.
        for key in ('PGPASSFILE', 'PGSERVICEFILE'):
            assert not os.path.lexists(supervisor.CHILD_ENV[key])

    def test_no_docstring_promises_an_owner_return_the_os_cannot_guarantee(self):
        # README: an OS-level stall in the owner's own close/kill/waitpid can make a
        # NO_RESULT return late. No public text may promise otherwise.
        texts = (supervisor.__doc__, supervisor.run_attempt.__doc__, (TOOL / 'README.md').read_text())
        for text in texts:
            assert 'whatever happens' not in text and 'returns within it' not in text

    def test_no_generic_sql_or_cap_override_exists(self):
        text = (TOOL / 'supervisor.py').read_text() + (TOOL / 'child.py').read_text()
        for word in ('argparse', 'sys.argv[1', 'os.environ[', 'os.getenv', 'DATABASE_URL', 'ANALYZE', 'heroku', 'curl'):
            assert word not in text
