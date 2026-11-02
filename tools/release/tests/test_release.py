import importlib.util
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

class ReleaseSafety(unittest.TestCase):
    def setUp(self):
        self.assertTrue((ROOT / 'rollback.py').exists(), 'shared rollback entry is missing')
        import rollback
        self.rollback = rollback

    def test_stale_heroku_failure_does_not_undo_new_release(self):
        writes = []
        current = {'id':'newer', 'sha':'b'*40}
        self.assertFalse(self.rollback.rollback_if_current('heroku', 'a'*40, 'bad', current, 'good', writes.append))
        self.assertEqual(writes, [])

    def test_matching_heroku_release_uses_explicit_prior_release(self):
        writes = []
        current = {'id':'bad', 'sha':'a'*40}
        self.assertTrue(self.rollback.rollback_if_current('heroku', 'a'*40, 'bad', current, 'good', writes.append))
        self.assertEqual(writes, [{'release':'good'}])

    def test_unknown_candidate_never_rolls_back(self):
        with self.assertRaises(ValueError):
            self.rollback.rollback_if_current('heroku', '', 'bad', {'id':'bad', 'sha':''}, 'good', lambda _:None)

    def test_vercel_rollback_pins_previous_deployment(self):
        writes=[]
        self.assertTrue(self.rollback.rollback_if_current('vercel','a'*40,'bad',{'id':'bad','sha':'a'*40},'good',writes.append))
        self.assertEqual(writes,[{'deploymentId':'good'}])

class AnonymousHealth(unittest.TestCase):
    def test_healthy_status_rejects_partial_database_failure(self):
        self.assertTrue((ROOT / 'health.py').exists(), 'health adapter is missing')
        import health
        with self.assertRaises(ValueError): health.validate_health({'status':'degraded','db':False,'redis':True})

    def test_html_empty_shape_and_empty_feed_fail(self):
        self.assertTrue((ROOT / 'health.py').exists(), 'health adapter is missing')
        import health
        for body in ({}, {'items':[]}, {'items':[None]}, '<html>'):
            with self.subTest(body=body), self.assertRaises(ValueError): health.validate_feed(body)

    def test_legitimate_feed_is_accepted(self):
        self.assertTrue((ROOT / 'health.py').exists(), 'health adapter is missing')
        import health
        health.validate_feed({'items':[{'type':'event','id':'e1'}]})
        health.validate_health({'status':'ok','db':True,'redis':True})

class GuardContract(unittest.TestCase):
    def test_missing_builder_tools_fail_closed(self):
        self.assertTrue((ROOT / 'health.py').exists(), 'health adapter is missing')
        import health
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(FileNotFoundError): health.require_speed_tools(pathlib.Path(directory))

    def test_only_last_verdict_is_used(self):
        self.assertTrue((ROOT / 'health.py').exists(), 'health adapter is missing')
        import health
        self.assertEqual(health.verdict('VERDICT PASS old\nVERDICT ROLLBACK crash\n'), 'VERDICT ROLLBACK crash')
        with self.assertRaises(ValueError): health.verdict('no result')

if __name__ == '__main__': unittest.main()

class HeadlineInput(unittest.TestCase):
    def test_no_price_is_filtered_before_guards(self):
        import health
        self.assertEqual(health.effective(10,9000,'1:9000:stamp_no_reading,2:400:returned'),(400,True))

    def test_midnight_rows_keep_date_order(self):
        import health
        def row(stamp,venue,ms):
            return stamp+' app[worker-ws.1]: '+__import__('json').dumps({'message':'live_blend_refresh['+venue+'] headline-clock n=10 max_ms='+str(ms)+' worst=1:'+str(ms)+':returned'})
        raw='\n'.join([row('2026-11-02T00:00:01.000+00:00','kalshi',200),row('2026-11-01T23:59:01.000+00:00','polymarket',300),row('2026-11-02T00:00:01.000+00:00','polymarket',400),row('2026-11-01T23:59:01.000+00:00','kalshi',100)])
        lines=health.streak_lines(raw)
        self.assertTrue(lines[0].startswith('23:59 PASS K=100ms P=300ms'))
        self.assertTrue(lines[1].startswith('00:00 PASS K=200ms P=400ms'))

    def test_only_one_venue_cannot_make_pass(self):
        import health
        self.assertEqual(health.streak_lines('2026-11-02T00:00:01.000+00:00 app[worker-ws.1]: '+__import__('json').dumps({'message':'live_blend_refresh[kalshi] headline-clock n=10 max_ms=10 worst=1:10:returned'})),[])

class ConfirmedRollback(unittest.TestCase):
    def test_api_success_is_not_enough_when_live_source_does_not_change(self):
        import rollback
        clock=[0]
        def advance(seconds): clock[0]+=seconds
        with self.assertRaises(RuntimeError):
            rollback.verify_rollback('heroku','b'*40,read=lambda:{'sha':'a'*40},sleep=advance,now=lambda:clock[0])

    def test_live_target_confirms_a_rollback(self):
        import rollback
        rows=iter([{'sha':'a'*40},{'sha':'b'*40}])
        clock=[0]
        def advance(seconds): clock[0]+=seconds
        rollback.verify_rollback('heroku','b'*40,read=lambda:next(rows),sleep=advance,now=lambda:clock[0])
        self.assertEqual(clock[0],2)
