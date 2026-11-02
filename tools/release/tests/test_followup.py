import json
import pathlib
import sys
import tempfile
import unittest

ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import discover
import platforms
import rollback


def receipt(candidate_id,sha,verdict):
    return {'payload':{'candidate_id':candidate_id,'candidate_sha':sha,'verdict':verdict}}

class ExactEvents(unittest.TestCase):
    def test_dispatch_keeps_the_exact_release_id(self):
        self.assertTrue(hasattr(discover,'event_candidate'),'event-specific discovery is missing')
        with tempfile.TemporaryDirectory() as directory:
            path=pathlib.Path(directory)/'event.json'
            path.write_text(json.dumps({'client_payload':{'provider':'heroku','candidate_id':'old-release','event_id':'e1'}}))
            self.assertEqual(discover.event_candidate('repository_dispatch',path),('heroku','old-release'))

    def test_receipts_after_page_100_are_not_lost(self):
        self.assertTrue(hasattr(platforms,'github_pages'),'receipt pagination is missing')
        def read(path):
            return [{'id':n} for n in range(100)] if '&page=1' in path else [{'id':100}]
        self.assertEqual(len(platforms.github_pages('/deployments?environment=test',read=read)),101)

    def test_latest_failed_receipt_overrides_earlier_pass(self):
        self.assertTrue(hasattr(discover,'receipt_index'),'receipt state reduction is missing')
        rows=[receipt('b','b'*40,'ROLLED BACK'),receipt('b','b'*40,'VERDICT PASS')]
        self.assertEqual(discover.receipt_index(rows)['b']['verdict'],'ROLLED BACK')

class GoodTargets(unittest.TestCase):
    def test_failed_source_cannot_be_selected_from_an_older_pass(self):
        self.assertTrue(hasattr(rollback,'known_good_targets'),'known-good rollback selection is missing')
        rows=[receipt('bad-b','b'*40,'ROLLED BACK'),receipt('pass-b','b'*40,'VERDICT PASS'),receipt('good-a','a'*40,'VERDICT PASS')]
        self.assertEqual(rollback.known_good_targets(rows,'c'*40),[('good-a','a'*40)])

    def test_rolled_back_baseline_is_not_selected_again(self):
        self.assertTrue(hasattr(rollback,'known_good_targets'),'known-good rollback selection is missing')
        rows=[receipt('restored-a','a'*40,'ROLLED BACK'),receipt('good-a','a'*40,'VERDICT PASS'),receipt('bad-b','b'*40,'ROLLED BACK')]
        self.assertEqual(rollback.known_good_targets(rows,'a'*40),[])

    def test_unverified_previous_provider_release_is_never_a_baseline(self):
        self.assertTrue(hasattr(rollback,'known_good_targets'),'known-good rollback selection is missing')
        self.assertEqual(rollback.known_good_targets([receipt('previous','d'*40,'SUPERSEDED')],'c'*40),[])

if __name__=='__main__': unittest.main()

class VercelPromotion(unittest.TestCase):
    def test_skipped_fast_gate_does_not_allow_an_unfinished_full_run(self):
        self.assertTrue((ROOT/'vercel_release.py').exists(),'Actions promotion owner is missing')
        import vercel_release
        run={'status':'in_progress','conclusion':None}
        jobs=[{'name':'fast-gate','conclusion':'success','steps':[{'name':'Python 3.11 syntax, smoke test and change-scope selected tests','conclusion':'skipped'}]}]
        self.assertFalse(vercel_release.ci_ready(run,jobs))

    def test_executed_fast_gate_allows_the_live_path(self):
        self.assertTrue((ROOT/'vercel_release.py').exists(),'Actions promotion owner is missing')
        import vercel_release
        run={'status':'in_progress','conclusion':None}
        jobs=[{'name':'fast-gate','conclusion':'success','steps':[{'name':'Python 3.11 syntax, smoke test and change-scope selected tests','conclusion':'success'},{'name':'Recheck current fast eligibility','conclusion':'success'},{'name':"Require this run's change-scope attempt",'conclusion':'success'}]}]
        self.assertTrue(vercel_release.ci_ready(run,jobs))

    def test_finished_failed_ci_cannot_promote(self):
        self.assertTrue((ROOT/'vercel_release.py').exists(),'Actions promotion owner is missing')
        import vercel_release
        self.assertFalse(vercel_release.ci_ready({'status':'completed','conclusion':'failure'},[]))

class BaselineProof(unittest.TestCase):
    def test_unknown_or_wrong_live_source_cannot_be_bootstrapped(self):
        self.assertTrue((ROOT/'arm.py').exists(),'reviewable activation tool is missing')
        import arm
        for proof in [{'verdict':'UNKNOWN'},{'verdict':'VERDICT PASS','provider':'heroku','candidate_id':'r1','candidate_sha':'a'*40}]:
            with self.assertRaises(ValueError):arm.validate_baseline(proof,{'id':'r2','sha':'b'*40})

    def test_exact_pass_baseline_can_be_seeded(self):
        self.assertTrue((ROOT/'arm.py').exists(),'reviewable activation tool is missing')
        import arm
        proof={'verdict':'VERDICT PASS','provider':'heroku','candidate_id':'r1','candidate_sha':'a'*40}
        arm.validate_baseline(proof,{'id':'r1','sha':'a'*40})

class WorkerBootstrap(unittest.TestCase):
    def test_missing_startup_and_partial_a10_never_become_healthy(self):
        import health
        self.assertTrue(hasattr(health,'worker_complete'),'worker verdict completion guard is missing')
        self.assertFalse(health.worker_complete('VERDICT PENDING no worker-ws start after release'))
        self.assertFalse(health.worker_complete('VERDICT PENDING A10 window not covered yet; 3-min health PASS'))
        self.assertTrue(health.worker_complete('VERDICT PASS A10 0 < 15'))

class FailedSourceVeto(unittest.TestCase):
    def test_future_vercel_deployment_is_vetoed_before_any_provider_write(self):
        self.assertTrue((ROOT/'veto.py').exists(),'durable source veto is missing')
        import veto
        calls=[]
        veto.mark_failed('a'*40,'watchdog failed',record=lambda provider,candidate,verdict:calls.append((provider,candidate,verdict)))
        self.assertEqual([call[0] for call in calls],['heroku','vercel'])
        self.assertTrue(all(call[1]['sha']=='a'*40 and call[2]=='VERDICT FAIL' for call in calls))

    def test_unrelated_pass_cannot_erase_a_failed_source_veto(self):
        self.assertTrue(hasattr(discover,'failed_sources'),'failed source index is missing')
        rows=[receipt('pass-a','a'*40,'VERDICT PASS'),receipt('source-a','a'*40,'VERDICT FAIL')]
        self.assertIn('a'*40,discover.failed_sources(rows))

class ReceiptAndCommentReplay(unittest.TestCase):
    def test_superseded_event_records_the_old_candidate_without_touching_production(self):
        import health
        from unittest.mock import patch
        old={'id':'old','sha':'a'*40};live={'id':'new','sha':'b'*40}
        receipts=[];comments=[]
        with tempfile.TemporaryDirectory() as directory:
            out=pathlib.Path(directory)/'health.json'
            args=['health.py','--provider','heroku','--candidate-id','old','--candidate-sha','a'*40,'--output',str(out)]
            with patch.object(sys,'argv',args),patch.object(platforms,'candidate',return_value=old),patch.object(platforms,'current',return_value=live),patch.object(discover,'receipt_rows',return_value=[]),patch.object(discover,'record',side_effect=lambda provider,candidate,result:receipts.append((candidate['id'],result))),patch.object(platforms,'report',side_effect=lambda line,key:comments.append((line,key))),patch.object(health,'watch',side_effect=AssertionError('stale event must never probe or roll back')):
                self.assertEqual(health.main(),0)
            result=json.loads(out.read_text())
        self.assertEqual(result['candidate_id'],'old')
        self.assertEqual(result['verdict'],'SUPERSEDED')
        self.assertEqual(receipts,[('old','SUPERSEDED')])
        self.assertIn('old',comments[0][0]);self.assertEqual(comments[0][1],'heroku:old')

    def test_keyed_now_comment_is_updated_instead_of_reposted_after_page_100(self):
        from unittest.mock import patch
        import os
        saved={'id':101,'body':'old\n<!-- release-loop:heroku:old -->'};writes=[]
        def github(path,method='GET',body=None):
            if method=='GET': return [{'id':n,'body':'unrelated'} for n in range(100)] if '&page=1' in path else [saved]
            writes.append((path,method));saved['body']=body['body']
        with patch.dict(os.environ,{'NOW_ISSUE':'1'}),patch.object(platforms,'github',side_effect=github):
            platforms.report('old release SUPERSEDED',key='heroku:old')
            platforms.report('old release SUPERSEDED',key='heroku:old')
        self.assertEqual(writes,[('/issues/comments/101','PATCH')])

class PromotionFailureBoundary(unittest.TestCase):
    def test_a_completed_draft_cannot_promote_after_the_watchdog_veto(self):
        import vercel_release
        from unittest.mock import patch
        rows=[receipt('failed-source:a','a'*40,'VERDICT FAIL')]
        with patch.object(discover,'receipt_rows',return_value=rows),patch('policy.require_enabled'),patch.object(platforms,'vercel') as writes:
            with self.assertRaises(ValueError):vercel_release.promote('a'*40,'ready-draft')
            writes.assert_not_called()

class EmptyProviderResponse(unittest.TestCase):
    def test_successful_204_does_not_break_variable_activation(self):
        from unittest.mock import patch
        class Response:
            status=204
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self):return b''
        with patch('urllib.request.urlopen',return_value=Response()):
            self.assertEqual(platforms.request('https://api.github.com/test',method='PATCH',body={'value':'true'}),{})

class CachedPassVeto(unittest.TestCase):
    def test_cached_pass_cannot_override_a_failure_under_another_candidate_id(self):
        import health
        from unittest.mock import patch
        candidate={'id':'old-pass','sha':'a'*40}
        rows=[receipt('failed-source:a','a'*40,'VERDICT FAIL'),receipt('old-pass','a'*40,'VERDICT PASS')]
        with tempfile.TemporaryDirectory() as directory:
            out=pathlib.Path(directory)/'health.json'
            args=['health.py','--provider','heroku','--candidate-id','old-pass','--output',str(out)]
            with patch.object(sys,'argv',args),patch.object(platforms,'candidate',return_value=candidate),patch.object(platforms,'current',return_value=candidate),patch.object(discover,'receipt_rows',return_value=rows),patch.object(discover,'record'),patch.object(platforms,'report'),patch.object(health,'watch',side_effect=AssertionError('failed source cannot be replayed as healthy')):
                self.assertNotEqual(health.main(),0)
            self.assertNotEqual(json.loads(out.read_text())['verdict'],'VERDICT PASS')

class LateBaselineVeto(unittest.TestCase):
    def test_target_failure_arriving_after_selection_prevents_the_rollback_post(self):
        from unittest.mock import patch
        live={'id':'bad','sha':'b'*40};target={'id':'good','sha':'a'*40}
        passed=[receipt('good','a'*40,'VERDICT PASS')]
        failed=[receipt('failed-source:a','a'*40,'VERDICT FAIL'),*passed]
        with patch.object(platforms,'current',return_value=live),patch.object(discover,'receipt_rows',side_effect=[passed,failed]),patch.object(discover,'record'),patch.object(platforms,'candidate',return_value=target),patch.object(platforms,'heroku') as writes,patch.object(rollback,'verify_rollback'):
            with self.assertRaises(ValueError):rollback.rollback('heroku','b'*40,'bad')
            writes.assert_not_called()

class DurableCaptureAdapter(unittest.TestCase):
    def test_missing_history_is_unknown_instead_of_recent_snapshot_fallback(self):
        import health
        from unittest.mock import patch
        from datetime import datetime,timezone
        with patch.object(platforms,'request',return_value={'complete':False,'live':True,'lines':['startup']}),patch.dict(__import__('os').environ,{'ADMIN_TOKEN':'fixture-token','RELEASE_LOG_API_ORIGIN':'https://collector.test'}):
            with self.assertRaises(ValueError):health.capture(datetime(2026,11,2,tzinfo=timezone.utc))

    def test_complete_persisted_history_is_used_after_a_queued_release(self):
        import health
        from unittest.mock import patch
        from datetime import datetime,timezone
        calls=[]
        def request(url,token=None,*args,**kwargs):
            calls.append((url,token));return {'complete':True,'live':True,'lines':['older startup','later headline']}
        with patch.object(platforms,'request',side_effect=request),patch.dict(__import__('os').environ,{'ADMIN_TOKEN':'fixture-token','RELEASE_LOG_API_ORIGIN':'https://collector.test'}):
            self.assertEqual(health.capture(datetime(2026,11,2,tzinfo=timezone.utc)), 'older startup\nlater headline\n')
        self.assertIn('/api/admin/release-logs?since=',calls[0][0]);self.assertEqual(calls[0][1],'fixture-token')

class CurrentAttemptGate(unittest.TestCase):
    def test_retained_selected_tests_without_fresh_eligibility_are_not_a_release_gate(self):
        import vercel_release
        run={'status':'in_progress','conclusion':None}
        jobs=[{'name':'fast-gate','conclusion':'success','steps':[{'name':vercel_release.FAST_STEP,'conclusion':'success'},{'name':'Recheck current fast eligibility','conclusion':'skipped'}]}]
        self.assertFalse(vercel_release.ci_ready(run,jobs))

    def test_jobs_are_read_from_the_current_attempt(self):
        import vercel_release
        from unittest.mock import patch
        calls=[]
        proof=[{'name':'fast-gate','conclusion':'success','steps':[{'name':vercel_release.FAST_STEP,'conclusion':'success'},{'name':'Recheck current fast eligibility','conclusion':'success'},{'name':"Require this run's change-scope attempt",'conclusion':'success'}]}]
        def read(path):
            calls.append(path)
            if '/jobs' in path:return {'jobs':[] if '/attempts/2/' in path else proof}
            return {'head_branch':'master','event':'push','head_sha':'a'*40,'run_attempt':2,'status':'in_progress','conclusion':None}
        with patch.object(platforms,'github',side_effect=read),patch.object(vercel_release.time,'monotonic',side_effect=[0,1,2401]),patch.object(vercel_release.time,'sleep'):
            with self.assertRaises(TimeoutError):vercel_release.await_ci('1','a'*40)
        self.assertIn('/actions/runs/1/attempts/2/jobs?per_page=100',calls)

class DrainPreparation(unittest.TestCase):
    def test_setup_preview_never_creates_a_drain(self):
        self.assertTrue((ROOT/'prepare_drain.py').exists(),'durable drain setup tool is missing')
        import prepare_drain
        self.assertEqual(prepare_drain.prepare(False,False,None)['activation'],'held')

    def test_drain_setup_requires_master_current_and_an_explicit_origin(self):
        self.assertTrue((ROOT/'prepare_drain.py').exists(),'durable drain setup tool is missing')
        import prepare_drain
        with self.assertRaises(ValueError):prepare_drain.prepare(True,False,'https://collector.test')
        with self.assertRaises(ValueError):prepare_drain.prepare(True,True,None)

class ArmingPolicy(unittest.TestCase):
    def test_disable_publishes_fresh_false_before_touching_coarse_flags(self):
        import arm
        from unittest.mock import patch
        calls=[]
        def api(path,method='GET',body=None):
            if path=='/branches/master':return {'commit':{'sha':'a'*40}}
            calls.append((path,method,body));return {'id':1}
        with patch.object(platforms,'github',side_effect=api):
            result=arm.arm({},False,False,True,disable=True)
        self.assertEqual(result['activation'],'disabled')
        self.assertEqual(calls[0][0],'/deployments')
        self.assertEqual(calls[0][2]['environment'],'release-loop-policy')
        self.assertEqual(calls[0][2]['payload'],{'authority':'release-loop-policy-v1','fast_enabled':False,'master_sha':'a'*40})

class SeedBaselines(unittest.TestCase):
    def test_seeding_requires_current_confirmation_and_reviewed_conclusive_proof(self):
        self.assertTrue((ROOT/'seed_baselines.py').exists(),'baseline seeding entry is missing')
        import seed_baselines
        with self.assertRaises(ValueError):seed_baselines.seed({},False,False,True)

    def test_a_source_veto_blocks_seeding_even_when_the_proof_says_pass(self):
        self.assertTrue((ROOT/'seed_baselines.py').exists(),'baseline seeding entry is missing')
        import seed_baselines
        from unittest.mock import patch
        proof={'heroku':{'provider':'heroku','candidate_id':'r','candidate_sha':'a'*40,'verdict':'VERDICT PASS','evidence':{'worker_check':'VERDICT PASS','guard2':'VERDICT PASS','guard3':'VERDICT PASS'}}}
        with patch.object(platforms,'current',return_value={'id':'r','sha':'a'*40}),patch.object(discover,'receipt_rows',return_value=[receipt('failed-source:a','a'*40,'VERDICT FAIL')]),patch.object(discover,'record') as writes:
            with self.assertRaises(ValueError):seed_baselines.seed(proof,True,True,True)
            writes.assert_not_called()

class BootstrapGate(unittest.TestCase):
    def test_bootstrap_never_bypasses_the_master_current_hold(self):
        self.assertTrue((ROOT/'bootstrap.py').exists(),'serialized bootstrap entry is missing')
        import bootstrap
        with self.assertRaises(ValueError):bootstrap.verify_bootstrap_confirmation(False)

    def test_successful_fast_only_ci_cannot_bootstrap(self):
        self.assertTrue((ROOT/'bootstrap.py').exists(),'serialized bootstrap entry is missing')
        import bootstrap
        run={'status':'completed','conclusion':'success'}
        jobs=[{'name':'fast-gate','conclusion':'success','steps':[{'name':'Python 3.11 syntax, smoke test and change-scope selected tests','conclusion':'success'}]}]
        self.assertFalse(bootstrap.full_ci(run,jobs))

    def test_four_executed_full_shards_can_bootstrap(self):
        self.assertTrue((ROOT/'bootstrap.py').exists(),'serialized bootstrap entry is missing')
        import bootstrap
        run={'status':'completed','conclusion':'success'}
        jobs=[{'name':'backend-tests ('+str(i)+')','conclusion':'success','steps':[{'name':'Run tests (shard '+str(i)+'/4)','conclusion':'success'}]} for i in range(1,5)]
        self.assertTrue(bootstrap.full_ci(run,jobs))
