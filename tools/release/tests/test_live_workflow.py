import unittest
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
        rollback = jobs['rollback']
        self.assertIn('always()', rollback['if'])
        command = str(rollback)
        self.assertIn('tools/release/rollback.py', command)
        self.assertIn('github.event.workflow_run.head_sha', command)
        self.assertIn('vercel', command)
        self.assertIn('heroku', command)

    def test_watchdog_preserves_every_full_ci_test_command(self):
        ci = yaml.safe_load((ROOT / '.github/workflows/ci.yml').read_text())['jobs']
        watch = yaml.safe_load((ROOT / '.github/workflows/live-path-watchdog.yml').read_text())['jobs']
        for name in ['backend-tests', 'shard-completeness', 'database-integration', 'search-recall', 'frontend-build', 'e2e-contract']:
            commands = lambda job: [(step.get('uses'), step.get('run')) for step in job['steps']]
            self.assertEqual(commands(ci[name]), commands(watch[name]), name + ' full-suite commands drifted')
        self.assertIn('scope=full', str(watch['change-scope']))

if __name__ == '__main__': unittest.main()
