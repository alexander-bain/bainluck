import unittest
import os
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
        self.assertIn('fast-gate', jobs['backend-tests']['needs'])
        self.assertEqual(jobs['backend-tests']['strategy']['matrix']['shard'], [1,2,3,4])
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
        self.assertEqual(jobs['backend-tests']['strategy']['matrix']['shard'], [1,2,3,4])
        self.assertGreater(len(jobs['database-integration']['steps']), 200)
        self.assertNotIn('deploy', jobs)
        workflow = yaml.safe_load(path.read_text())
        self.assertEqual(workflow['permissions']['deployments'], 'write')
        rollback = jobs['rollback']
        self.assertFalse(rollback['strategy']['fail-fast'])
        self.assertEqual(rollback['strategy']['matrix']['provider'], ['heroku', 'vercel'])
        self.assertIn('heroku-deploy', rollback['concurrency']['group'])
        self.assertIn('vercel-production', rollback['concurrency']['group'])
        self.assertEqual(rollback['env']['VERCEL_PROJECT_ID'], '${{ vars.VERCEL_PROJECT_ID }}')
        self.assertIn('veto', rollback['needs'])
        self.assertNotIn('concurrency', jobs['veto'])
        self.assertIn('tools/release/veto.py', str(jobs['veto']))
        self.assertIn('always()', rollback['if'])
        self.assertIn("needs.change-scope.result == 'success'", jobs['search-recall']['if'])
        command = str(rollback)
        self.assertIn('tools/release/rollback.py', command)
        self.assertIn('github.event.workflow_run.head_sha', command)
        self.assertIn('vercel', command)
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

    def test_watchdog_preserves_every_full_ci_test_command(self):
        ci = yaml.safe_load((ROOT / '.github/workflows/ci.yml').read_text())['jobs']
        watch = yaml.safe_load((ROOT / '.github/workflows/live-path-watchdog.yml').read_text())['jobs']
        for name in ['backend-tests', 'shard-completeness', 'database-integration', 'search-recall', 'frontend-build', 'e2e-contract']:
            commands = lambda job: [(step.get('uses'), step.get('run')) for step in job['steps']]
            self.assertEqual(commands(ci[name]), commands(watch[name]), name + ' full-suite commands drifted')
        self.assertIn('scope=full', str(watch['change-scope']))

if __name__ == '__main__': unittest.main()
