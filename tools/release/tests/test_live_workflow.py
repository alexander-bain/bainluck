import unittest
import os
import json
import subprocess
import sys
import tempfile
from pathlib import Path
import yaml
ROOT = Path(__file__).resolve().parents[3]

class WorkflowTests(unittest.TestCase):
    def test_fast_gate_must_finish_before_any_required_backend_context(self):
        jobs = yaml.safe_load((ROOT / '.github/workflows/ci.yml').read_text())['jobs']
        self.assertIn('fast-gate', jobs, 'bounded fast gate is missing')
        self.assertEqual(jobs['fast-gate']['timeout-minutes'], 2)
        self.assertEqual(jobs['e2e-contract']['timeout-minutes'], 5)
        self.assertIn('fast-gate', jobs['backend-tests']['needs'])
        self.assertEqual(jobs['backend-tests']['strategy']['matrix']['shard'], list(range(1, 9)))
        self.assertIn('fast-gate', jobs['deploy']['needs'])
        gate = str(jobs['fast-gate'])
        self.assertIn('3.11', gate)
        self.assertIn('compileall', gate)
        self.assertIn('test_startup', gate)

    def test_normal_ci_is_retained_and_live_deploy_cannot_ignore_failed_fast_gate(self):
        jobs = yaml.safe_load((ROOT / '.github/workflows/ci.yml').read_text())['jobs']
        self.assertIn("needs.fast-gate.result == 'success'", jobs['deploy']['if'])
        self.assertIn("github.event_name == 'push'", jobs['deploy']['if'])
        self.assertIn("github.ref == 'refs/heads/master'", jobs['deploy']['if'])
        for job in ['shard-completeness', 'database-integration', 'frontend-build']:
            self.assertIn("needs.change-scope.outputs.live != 'true'", jobs[job]['if'])

    def test_full_watchdog_has_original_shards_and_database_and_rolls_back_exact_sha(self):
        path = ROOT / '.github/workflows/live-path-watchdog.yml'
        self.assertTrue(path.exists(), 'post-deploy full-suite watchdog missing')
        jobs = yaml.safe_load(path.read_text())['jobs']
        self.assertEqual(jobs['backend-tests']['strategy']['matrix']['shard'], list(range(1, 9)))
        self.assertGreater(len(jobs['database-integration']['steps']), 200)
        self.assertNotIn('deploy', jobs)
        self.assertEqual(jobs['e2e-contract']['timeout-minutes'], 5)
        workflow = yaml.safe_load(path.read_text())
        self.assertEqual(workflow['permissions']['deployments'], 'write')
        rollback = jobs['rollback']
        self.assertIn('heroku-deploy', rollback['concurrency']['group'])
        self.assertNotIn('VERCEL_TOKEN', rollback['env'])
        self.assertEqual(rollback['steps'][-1]['env']['PROVIDER'], 'heroku')
        self.assertIn('veto', rollback['needs'])
        self.assertNotIn('concurrency', jobs['veto'])
        self.assertIn('tools/release/veto.py', str(jobs['veto']))
        self.assertIn('always()', rollback['if'])
        self.assertIn("needs.change-scope.result == 'success'", jobs['search-recall']['if'])
        command = str(rollback)
        self.assertIn('tools/release/rollback.py', command)
        self.assertIn('github.event.workflow_run.head_sha', command)
        self.assertNotIn('vercel', command)
        self.assertIn('heroku', command)

    def test_corrupt_or_missing_gate_record_cannot_skip_the_watchdog(self):
        jobs = yaml.safe_load((ROOT / '.github/workflows/live-path-watchdog.yml').read_text())['jobs']
        command = jobs['select']['steps'][0]['run']
        code = command.split("python3 - <<'MODE'\n", 1)[1].rsplit('\nMODE', 1)[0]
        with tempfile.TemporaryDirectory() as tmp:
            record = Path(tmp) / 'record.json'
            output = Path(tmp) / 'output'
            code = code.replace('/tmp/release-loop-mode/release-loop-mode.json', str(record))
            for content, expected_live in [('broken',True), ('null',True), ('{"sha":"abc","run_id":"7","run_attempt":"2","live":true}',True), ('{"sha":"abc","run_id":"7","run_attempt":"2","live":false}',False), ('{"sha":"abc","run_id":"7","run_attempt":"1","live":false}',True)]:
                record.write_text(content)
                output.write_text('')
                subprocess.run([sys.executable, '-c', code], env={**os.environ, 'CANDIDATE_SHA':'abc', 'RUN_ID':'7', 'RUN_ATTEMPT':'2', 'GITHUB_OUTPUT':str(output)}, check=True)
                self.assertEqual(output.read_text(), 'live=true\n' if expected_live else 'live=false\n')

    def test_heroku_push_refuses_a_durable_failed_source(self):
        workflow = yaml.safe_load((ROOT / '.github/workflows/ci.yml').read_text())
        job = workflow['jobs']['deploy']
        run = job['steps'][-1]['run']
        self.assertIn("python3 - <<'SOURCE_VETO'", run, 'Heroku release ignores failed-source receipts')
        code = run.split("python3 - <<'SOURCE_VETO'\n", 1)[1].split('\nSOURCE_VETO', 1)[0]
        self.assertLess(run.index("python3 - <<'SOURCE_VETO'"), run.index('if git push heroku'))
        self.assertGreaterEqual(run.count('check_source_veto'),4)
        self.assertEqual(workflow['permissions']['deployments'], 'read')
        self.assertEqual(job['env']['GH_TOKEN'], '${{ github.token }}')
        with tempfile.TemporaryDirectory() as tmp:
            module = Path(tmp) / 'tools/release/discover.py'
            module.parent.mkdir(parents=True)
            module.write_text('def receipt_rows(provider): return []\ndef failed_sources(rows): return {"' + 'a'*40 + '"}\n')
            result = subprocess.run([sys.executable, '-c', code], cwd=tmp, env={**os.environ, 'GITHUB_SHA':'a'*40}, capture_output=True)
            self.assertNotEqual(result.returncode, 0, 'failed source was admitted into Heroku')

    def test_watchdog_preserves_every_full_ci_test_command(self):
        ci = yaml.safe_load((ROOT / '.github/workflows/ci.yml').read_text())['jobs']
        watch = yaml.safe_load((ROOT / '.github/workflows/live-path-watchdog.yml').read_text())['jobs']
        for name in ['backend-tests', 'shard-completeness', 'database-integration', 'search-recall', 'frontend-build', 'e2e-contract']:
            commands = lambda job: [(step.get('uses'), step.get('run')) for step in job['steps'] if step.get('name') != "Require this run's change-scope attempt"]
            self.assertEqual(commands(ci[name]), commands(watch[name]), name + ' full-suite commands drifted')
        self.assertIn('scope=full', str(watch['change-scope']))

    def test_database_steps_continue_after_failure_but_stop_on_cancellation(self):
        for workflow in ['ci.yml', 'live-path-watchdog.yml']:
            job = yaml.safe_load((ROOT / '.github/workflows' / workflow).read_text())['jobs']['database-integration']
            steps = job['steps']
            summaries = [step for step in steps if step.get('id') == 'database_integration_summary']
            self.assertEqual(len(summaries), 1, workflow)
            self.assertIs(steps[-1], summaries[0])
            self.assertEqual(summaries[0]['if'], '${{ !cancelled() }}')
            self.assertTrue(summaries[0]['continue-on-error'], 'summary errors must not change the gate result')
            self.assertEqual(len({step['id'] for step in steps}), len(steps))
            self.assertNotIn('continue-on-error', job)
            for step in steps[:-1]:
                self.assertIn('!cancelled()', step['if'], step.get('name', step.get('uses')))
                self.assertNotIn('success()', step['if'])
                self.assertNotIn('continue-on-error', step, 'original failures must still fail the job')
                if 'pytest' in step.get('run', ''):
                    self.assertIn('matrix.group', step['if'])
                    self.assertIn("needs.change-scope.outputs.reuse != 'true'", step['if'])

    def test_database_summary_lists_both_failed_steps_and_leaves_successes_out(self):
        for workflow in ['ci.yml', 'live-path-watchdog.yml']:
            steps = yaml.safe_load((ROOT / '.github/workflows' / workflow).read_text())['jobs']['database-integration']['steps']
            code = steps[-1]['run'].split("python - <<'SUMMARY'\n", 1)[1].rsplit('\nSUMMARY', 1)[0]
            fixtures = [
                ({'first_integration': {'outcome': 'failure'}, 'passing': {'outcome': 'success'},
                  'second_integration': {'outcome': 'failure'}, 'skipped': {'outcome': 'skipped'}}, True),
                ({'passing': {'outcome': 'success'}, 'skipped': {'outcome': 'skipped'}}, False),
            ]
            with tempfile.TemporaryDirectory() as tmp:
                output = Path(tmp) / 'summary.md'
                for results, failed in fixtures:
                    output.write_text('')
                    result = subprocess.run([sys.executable, '-c', code], env={**os.environ,
                        'STEP_RESULTS': json.dumps(results), 'INTEGRATION_GROUP': 'shared',
                        'GITHUB_STEP_SUMMARY': str(output)}, capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    summary = output.read_text()
                    self.assertEqual(summary.count('## Database integration'), 1)
                    self.assertIn('shared', summary)
                    for name in ['first_integration', 'second_integration']:
                        self.assertEqual(name in summary, failed)
                    self.assertNotIn('passing', summary)
                    self.assertNotIn('skipped', summary)
                    self.assertEqual('No failed steps.' in summary, not failed)

if __name__ == '__main__': unittest.main()
