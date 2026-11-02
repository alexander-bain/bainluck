import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]

class RepositoryPolicyTest(unittest.TestCase):
    def test_protection_requires_pr_and_no_admin_bypass(self):
        spec = importlib.util.spec_from_file_location('policy', ROOT / 'tools/release/repository_policy.py')
        self.assertIsNotNone(spec)
        self.assertTrue(Path(spec.origin).exists(), 'repository policy has not been implemented')
        policy = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(policy)
        body = policy.protection(['backend-tests (1)', 'Tier-B approval'])
        self.assertTrue(body['enforce_admins'])
        self.assertTrue(body['required_status_checks']['strict'])
        self.assertIn('Tier-B approval', body['required_status_checks']['contexts'])
        self.assertIsInstance(body['required_pull_request_reviews'], dict)
        self.assertFalse(body['allow_force_pushes'])
        self.assertFalse(body['allow_deletions'])

if __name__ == '__main__': unittest.main()
