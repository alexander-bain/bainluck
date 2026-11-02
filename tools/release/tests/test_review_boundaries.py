import datetime as dt
import json
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'tools/release'))
import discover
import health
import platforms


class PublicProbeRetries(unittest.TestCase):
    def test_one_proxy_failure_recovers_without_a_rollback(self):
        with patch.object(platforms, 'request', side_effect=[
            OSError('proxy unavailable'),
            {'status': 'ok', 'db': True, 'redis': True},
            {'items': [{'type': 'event'}]},
        ]) as request, patch.object(health.time, 'sleep') as sleep:
            health.probe('heroku')
        self.assertEqual(request.call_count, 3)
        sleep.assert_called_once_with(30)

    def test_three_failures_are_required_and_separated_by_thirty_seconds(self):
        with patch.object(platforms, 'request', side_effect=OSError('proxy unavailable')) as request, \
                patch.object(health.time, 'sleep') as sleep:
            with self.assertRaises(OSError):
                health.probe('heroku')
        self.assertEqual(request.call_count, 3)
        self.assertEqual([call.args for call in sleep.call_args_list], [(30,), (30,)])

    def test_failed_feed_also_gets_a_fresh_health_and_feed_attempt(self):
        healthy = {'status': 'ok', 'db': True, 'redis': True}
        with patch.object(platforms, 'request', side_effect=[
            healthy, {'items': []}, healthy, {'items': [{'type': 'event'}]},
        ]) as request, patch.object(health.time, 'sleep') as sleep:
            health.probe('heroku')
        self.assertEqual(request.call_count, 4)
        sleep.assert_called_once_with(30)


class ExistingHerokuLogs(unittest.TestCase):
    def read_window(self, stamps):
        raw = '\n'.join(stamp.isoformat() + ' app[worker-ws.1]: existing log' for stamp in stamps) + '\n'
        response = MagicMock()
        response.__enter__.return_value.read.return_value = raw.encode()
        now = dt.datetime.now(dt.timezone.utc)
        with patch.object(platforms, 'heroku', return_value={
            'logplex_url': 'https://logplex.heroku.com/sessions/fixture',
        }) as api, patch.object(health.urllib.request, 'urlopen', return_value=response):
            result = health.capture(now - dt.timedelta(minutes=30))
        api.assert_called_once_with('/log-sessions', 'POST', {
            'dyno': 'worker-ws', 'lines': 1500, 'tail': False,
        })
        return result

    def test_complete_retained_window_uses_the_existing_provider(self):
        now = dt.datetime.now(dt.timezone.utc)
        self.assertIn('existing log', self.read_window([now - dt.timedelta(minutes=31), now]))

    def test_missing_old_tail_or_stale_end_is_unknown(self):
        now = dt.datetime.now(dt.timezone.utc)
        for stamps in ([now], [now - dt.timedelta(minutes=31), now - dt.timedelta(minutes=2)], []):
            with self.subTest(stamps=stamps), self.assertRaises(ValueError):
                self.read_window(stamps)

    def test_foreign_session_url_is_refused_before_reading_it(self):
        with patch.object(platforms, 'heroku', return_value={'logplex_url': 'https://other.test/logs'}), \
                patch.object(health.urllib.request, 'urlopen') as read:
            with self.assertRaises(ValueError):
                health.capture(dt.datetime.now(dt.timezone.utc))
        read.assert_not_called()


class BootstrapReporting(unittest.TestCase):
    def run_unknown(self, rows):
        candidate = {'id': 'new', 'sha': 'b' * 40}
        with tempfile.TemporaryDirectory() as directory:
            output = pathlib.Path(directory) / 'health.json'
            with patch.object(sys, 'argv', ['health.py', '--provider', 'heroku', '--output', str(output)]), \
                    patch.object(platforms, 'current', return_value=candidate), \
                    patch.object(discover, 'receipt_rows', return_value=rows), \
                    patch.object(health, 'probe'), patch.object(health, 'require_speed_tools'), \
                    patch.object(health, 'watch', side_effect=ValueError('incomplete worker window')), \
                    patch.object(platforms, 'report') as report:
                self.assertEqual(health.main(), 2)
                self.assertFalse(json.loads(output.read_text())['rollback'])
            return report

    def test_unknown_before_baseline_does_not_write_now(self):
        self.run_unknown([]).assert_not_called()

    def test_unknown_after_baseline_remains_visible(self):
        rows = [{'payload': {'candidate_id': 'old', 'candidate_sha': 'a' * 40, 'verdict': 'VERDICT PASS'}}]
        report = self.run_unknown(rows)
        report.assert_called_once()
        self.assertIn('VERDICT UNKNOWN', report.call_args.args[0])


class ProductBoundary(unittest.TestCase):
    def test_release_observation_does_not_add_product_endpoints_or_disable_git_deploys(self):
        for path in (
            'backend/app/routes/release_logs.py',
            'backend/app/utils/release_log_store.py',
            'frontend/app/api/release-webhook/route.js',
            'frontend/app/api/release-log-drain/route.js',
            'tools/release/prepare_drain.py',
            'tools/release/prepare_webhook.py',
            'tools/release/vercel_release.py',
            '.github/workflows/vercel-release.yml',
        ):
            self.assertFalse((ROOT / path).exists(), path)
        config = json.loads((ROOT / 'frontend/vercel.json').read_text())
        self.assertIsNot(config.get('git', {}).get('deploymentEnabled', {}).get('master'), False)
        for name in ('post-deploy-health.yml', 'release-health-observer.yml'):
            text = (ROOT / '.github/workflows' / name).read_text()
            self.assertIn('ref: master', text)
            self.assertNotIn('VERCEL_', text)
            self.assertNotIn('ADMIN_TOKEN', text)
        workflow = (ROOT / '.github/workflows/post-deploy-health.yml').read_text()
        self.assertIn('workflow_run:', workflow)
        self.assertIn("cron: '*/5 * * * *'", workflow)
        self.assertNotIn('heroku-release', workflow)
