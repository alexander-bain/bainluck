"""UNEXECUTED real-Redis suite selecting corrected Lua AND adapter.

No server case has run. This file is not part of run-focused.sh. Future execution
needs separately permitted private Unix-only runtime; no transport fallback.
"""
import concurrent.futures
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
import redis
from redis.retry import Retry
from redis.backoff import NoBackoff

from selection import preflight, LUA_SHA256, ADAPTER_SHA256
from runtime_selection import validate_runtime_contract, verify_owned_runtime_version
ROOT=Path(__file__).resolve().parent
OUTPUT=ROOT.parent/'.work/real-redis'
BINARY=os.environ.get('DNPL_REDIS_BINARY')
ADAPTER,SCRIPT=preflight()
EXPECTED=LUA_SHA256
RESULTS={'script_sha256':EXPECTED,'adapter_sha256':ADAPTER_SHA256,'tests':[], 'observations':{},'status':'not executed'}

class RealRedis(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  if os.environ.get('DNPL_RUN_REAL_REDIS')!='1':
   raise RuntimeError('Unexecuted suite: explicit permitted runtime invocation required')
  preflight() # fail before any process or socket action if selected bytes changed
  contract=validate_runtime_contract(BINARY,os.environ.get('DNPL_REDIS_EXPECTED_VERSION'),os.environ.get('DNPL_REDIS_EXPECTED_SHA256'))
  RESULTS['runtime_contract']=contract
  OUTPUT.mkdir(parents=True,exist_ok=True)
  cls.tmp=tempfile.TemporaryDirectory(prefix='dot-redis-')
  cls.addClassCleanup(cls.tmp.cleanup)
  cls.path=Path(cls.tmp.name);cls.socket=cls.path/'redis.sock'
  cls.log=(OUTPUT/'server.log').open('w')
  cls.addClassCleanup(cls.log.close)
  cls.argv=[contract['binary_path'],'--port','0','--bind','127.0.0.1','--protected-mode','yes',
    '--unixsocket',str(cls.socket),'--unixsocketperm','700','--save','',
    '--appendonly','no','--daemonize','no','--dir',str(cls.path)]
  RESULTS['status']='runtime launch attempted'
  cls.proc=subprocess.Popen(cls.argv,stdout=cls.log,stderr=subprocess.STDOUT)
  cls.addClassCleanup(cls.cleanup_owned)
  cls.r=redis.Redis(unix_socket_path=str(cls.socket),decode_responses=True,
     socket_timeout=2,socket_connect_timeout=2,retry=Retry(NoBackoff(),0))
  for _ in range(100):
   if cls.proc.poll() is not None:raise RuntimeError(f'owned Redis exited {cls.proc.returncode}; see server.log')
   try:
    if cls.r.ping():break
   except redis.exceptions.ConnectionError:time.sleep(.02)
  else:raise RuntimeError('owned Redis did not start')
  info=cls.r.info('server');assert info['process_id']==cls.proc.pid
  RESULTS['actual_owned_runtime_version']=info.get('redis_version')
  verify_owned_runtime_version(contract,info)
  assert cls.r.config_get('port')['port']=='0'
  assert cls.r.config_get('appendonly')['appendonly']=='no'
  assert cls.r.config_get('save')['save']==''
  RESULTS['runtime']={**contract,'redis_version':info['redis_version'],'redis_git_sha1':info['redis_git_sha1'],
   'redis_build_id':info['redis_build_id'],'process_id':cls.proc.pid,'argv':cls.argv,
   'ownership_verified':True,'tcp_port':0,'socket_permissions':oct(cls.socket.stat().st_mode & 0o777),
   'maxmemory_initial':cls.r.config_get('maxmemory'),'maxmemory_policy':cls.r.config_get('maxmemory-policy')}
 @classmethod
 def cleanup_owned(cls):
  if getattr(cls,"cleaned",False):return
  cls.cleaned=True
  try:
   cls.r.config_set('maxmemory',0) # restore only this disposable instance before cleanup
  except redis.exceptions.RedisError as exc:
   RESULTS.setdefault('cleanup_warnings',[]).append({'operation':'restore disposable maxmemory','error':type(exc).__name__,'message':str(exc)})
  cls.r.close()
  if cls.proc.poll() is None:cls.proc.terminate()
  cls.proc.wait(timeout=5);cls.log.close()
  RESULTS['cleanup']={'process_exit_code':cls.proc.returncode,'stopped':cls.proc.poll() is not None,
      'persisted_rdb':list(str(p) for p in cls.path.glob('*.rdb')),'persisted_aof':list(str(p) for p in cls.path.glob('*aof*'))}
  cls.tmp.cleanup();RESULTS['cleanup']['temporary_directory_removed']=not cls.path.exists()
  (OUTPUT/'results.json').write_text(json.dumps(RESULTS,indent=2)+'\n')
 def setUp(self):
  self.r.config_set('maxmemory',0)
  self.name=self.id().rsplit('.',1)[-1]
  self.keys=[f'{self.name}:{n}' for n in ['counter','owner','enabled','record','channel']]
  self.r.delete(*self.keys)
  self.commands=ADAPTER.Commands(self.keys,1)
  self.pub=self.r.pubsub(ignore_subscribe_messages=False);self.pub.subscribe(self.keys[4])
  ack=self.pub.get_message(ignore_subscribe_messages=False,timeout=2)
  self.assertIsNotNone(ack);self.assertEqual(ack['type'],'subscribe');self.assertEqual(ack['channel'],self.keys[4])
  self.assertEqual(self.call('claim')[0],'claimed')
 def tearDown(self):
  self.r.config_set('maxmemory',0);self.pub.close()
  RESULTS['tests'].append(self.name)
 def raw_call(self,*args):
  """Explicit engine boundary / malformed-command tests only, not adapter path."""
  return self.r.eval(SCRIPT,len(self.keys),*self.keys,*args)
 def execute(self,command):
  self.assertEqual(command[0],'EVAL');self.assertEqual(command[1],SCRIPT)
  return self.r.execute_command(*command)
 def call(self,*args):
  if args[0]=='claim':return self.execute(self.commands.claim())
  if args[0]=='committed':
   frame={'event_id':1,'rev':{'1':args[1]},'p':.73,'fixture_label':args[2]}
   return self.execute(self.commands.committed(frame))
  if args[0]=='snapshot':return self.execute(self.commands.snapshot(database_revision=args[1],database_status=args[2]))
  raise AssertionError('Use explicit raw_call for non-adapter boundary tests')
 def offer(self,seq,epoch=None,kind='blend',base=0,chain='A',expiry=None,issued=None,ttl=5000):
  now=self.r.time();now=now[0]*1000+now[1]//1000
  if epoch is None:epoch=int(self.r.get(self.keys[1]))
  if issued is None:issued=now
  if expiry is None:expiry=issued+ttl
  meta={'kind':kind,'epoch':epoch,'seq':seq,'base_rev':base,'lease_id':chain,
    'original_expires_at_ms':expiry,'ttl_ms':ttl}
  if kind=='revoke':meta={'kind':kind,'epoch':epoch,'seq':seq,'through_seq':seq-1}
  frame={'event_id':1,'p':.73,'status':'live','provisional':True,'preview':meta}
  return self.execute(self.commands.offer(frame,issued_at_ms=issued))
 def snap(self,floor=0,status='live'):return self.call('snapshot',floor,status)
 def messages(self):
  out=[]
  while True:
   m=self.pub.get_message(timeout=.05)
   if m is None:break
   if m['type']=='message':
    raw=m['data']
    RESULTS['observations'].setdefault('wire_messages',[]).append(raw)
    try:
     f=json.loads(raw)
     label=f.get('fixture_label') or (f["preview"]["kind"]+'-'+str(f["preview"]["seq"]))
    except (ValueError,TypeError,KeyError):label=raw
    out.append(label)
  return out
 def test_accepted_owner_and_replay(self):
  self.assertEqual(self.offer(1)[0],'published_retained');s=self.snap();self.assertEqual(s[0],'valid');self.assertEqual(s[2],1)
  self.assertEqual(self.messages(),['blend-1'])
 def test_old_owner_revoke_keeps_new_owner(self):
  self.offer(1);self.call('claim');self.offer(2);self.assertEqual(self.offer(3,epoch=1,kind='revoke')[0],'old_revoke_published')
  self.assertEqual(self.snap()[2],2);self.assertEqual(self.messages(),['blend-1','blend-2','revoke-3'])
 def test_owner_claim_without_first_quote(self):
  self.offer(1);self.call('claim');self.assertEqual(self.snap()[0],'cold_or_replaced_owner');self.assertEqual(self.offer(2,epoch=1)[0],'fenced')
 def test_revoke_own_sequence_fences_older(self):
  self.offer(4);self.offer(5,kind='revoke');self.offer(4);self.assertEqual(self.snap()[:3],['revoked','1',5])
 def test_same_chain_deadline_not_renewed(self):
  self.offer(1);deadline=self.r.hget(self.keys[3],'expiry');self.offer(2,ttl=10000)
  self.assertEqual(self.r.hget(self.keys[3],'expiry'),deadline)
 def test_expired_snapshot_is_not_replayed(self):
  t=self.r.time();now=t[0]*1000+t[1]//1000;self.offer(1,issued=now-100,expiry=now-1,ttl=99)
  self.assertEqual(self.snap()[0],'expired')
 def test_future_issue_time_falls_back_live_only(self):
  t=self.r.time();now=t[0]*1000+t[1]//1000;self.offer(1,issued=now+100000)
  self.assertEqual(self.snap()[0],'replay_disabled');self.assertEqual(self.messages(),['blend-1'])
 def test_commit_floor_equal_base_and_cross_owner(self):
  self.offer(1,base=2);self.call('committed',2,'commit2');self.assertEqual(self.snap(2)[0],'valid')
  self.call('claim');self.offer(1,base=1);self.assertEqual(self.snap(2)[0],'newer_commit')
 def test_coverage_behind_commit_and_preview(self):
  self.offer(1,base=1);self.assertEqual(self.snap()[0],'coverage_behind_preview_base')
  self.call('committed',2,'commit2');self.assertEqual(self.snap(1)[0],'coverage_behind')
 def test_nonquote_status_same_revision_latches(self):
  self.offer(1);self.assertEqual(self.snap(0,'final')[0],'nonquote_latched');self.call('committed',0,'live0')
  self.call('claim');self.offer(2);self.assertEqual(self.snap()[0],'nonquote_latched')
 def test_retention_wrongtype_preserves_live(self):
  self.r.set(self.keys[3],'wrongtype');self.assertEqual(self.offer(1)[0],'published_replay_disabled')
  self.assertEqual(self.messages(),['blend-1']);self.assertEqual(self.snap()[0],'replay_disabled')
 def test_marker_wrongtype_preserves_proven_owner_live(self):
  self.r.delete(self.keys[2]);self.r.hset(self.keys[2],'x','x')
  self.assertEqual(self.offer(1)[0],'published_replay_disabled');self.assertEqual(self.messages(),['blend-1'])
  self.assertEqual(self.r.exists(self.keys[2]),0)
 def test_owner_wrongtype_stops_blend_but_not_commit(self):
  self.r.delete(self.keys[1]);self.r.hset(self.keys[1],'x','x')
  self.assertEqual(self.offer(1,epoch=1)[0],'authority_read_error');self.assertEqual(self.messages(),[])
  self.assertEqual(self.call('committed',1,'commit1')[0],'committed_replay_disabled');self.assertEqual(self.messages(),['commit1'])
 def test_real_lua_error_does_not_rollback(self):
  self.r.set(self.keys[3],'wrongtype')
  with self.assertRaises(redis.exceptions.ResponseError):
   self.r.eval("redis.call('DEL',KEYS[1]); redis.call('PUBLISH',KEYS[2],'delivered'); redis.call('HSET',KEYS[3],'x','y')",3,self.keys[2],self.keys[4],self.keys[3])
  self.assertEqual(self.r.exists(self.keys[2]),0);self.assertEqual(self.messages(),['delivered'])
 def test_concurrent_seq_revoke_commit_linearizations(self):
  for i in range(12):
   self.r.delete(self.keys[3]);self.r.set(self.keys[2],self.r.get(self.keys[1]))
   actions=[lambda:self.offer(1),lambda:self.offer(3),lambda:self.offer(4,kind='revoke'),lambda:self.call('committed',1,'commit')]
   actions=actions[i%4:]+actions[:i%4]
   with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:list(ex.map(lambda f:f(),actions))
   self.assertEqual(self.snap(1)[:3],['revoked','1',4])
 def test_independent_hash_loss_is_real_unsafe_prerequisite(self):
  self.offer(4);self.offer(5,kind='revoke');self.r.delete(self.keys[3]);self.offer(4)
  self.assertEqual(self.snap()[0],'valid')
  RESULTS['observations']['independent_hash_loss']={'old_seq_replayed':True,'scope':'explicit DEL simulates isolated key loss; not an eviction-policy claim'}
 def test_sql_status_gap_still_exists(self):
  self.offer(1);self.assertEqual(self.snap(0,'live')[0],'valid');self.assertEqual(self.snap(0,'final')[0],'nonquote_latched')
 def test_real_pcall_error_after_publish_keeps_barrier(self):
  self.r.set(self.keys[3],'wrongtype')
  value=self.r.eval("redis.call('DEL',KEYS[1]); redis.call('PUBLISH',KEYS[2],'delivered'); local r=redis.pcall('HSET',KEYS[3],'x','y'); return r.err",3,self.keys[2],self.keys[4],self.keys[3])
  self.assertIn('WRONGTYPE',value);self.assertEqual(self.r.exists(self.keys[2]),0);self.assertEqual(self.messages(),['delivered'])
 def test_counter_loss_is_unsafe_epoch_prerequisite(self):
  self.call('claim');self.r.delete(self.keys[0]);self.assertEqual(self.call('claim'),['claimed','1'])
  self.assertEqual(self.offer(1,epoch=1)[0],'published_retained')
  RESULTS['observations']['counter_loss']={'old_epoch_reaccepted':True,'scope':'explicit DEL, not a failover claim'}
 def test_numeric_owner_claims_remain_distinct_in_declared_safe_range(self):
  self.r.set(self.keys[0],100000000000000)
  first=self.call('claim');second=self.call('claim')
  RESULTS['observations']['large_epoch']={'first':first,'second':second,'counter':self.r.get(self.keys[0])}
  self.assertNotEqual(first[1],second[1], 'distinct safe-integer epochs must not stringify to same owner')
 def test_large_sequence_rejects_delayed_older_offer(self):
  self.offer(100000000000004);self.offer(100000000000003)
  self.assertEqual(self.r.hget(self.keys[3],'seq'),'100000000000004')
  self.assertEqual(self.snap()[2],100000000000004)
 def test_large_sequence_accepts_genuinely_newer_revoke(self):
  self.offer(100000000000006);self.offer(100000000000007,kind='revoke')
  self.assertEqual(self.snap()[:3],['revoked','1',100000000000007])
 def test_real_oom_admission_observation(self):
  self.offer(1);self.messages();before=self.r.hgetall(self.keys[3]);marker=self.r.get(self.keys[2])
  # This is only the disposable process. No eviction policy is changed.
  used=self.r.info('memory')['used_memory'];self.r.config_set('maxmemory',max(1,used-100000))
  error=None;result=None
  t=self.r.time();now=t[0]*1000+t[1]//1000
  memory_record_before=self.r.memory_usage(self.keys[3])
  try:result=self.raw_call('offer',1,'blend',2,0,'A',now+5000,now,5000,'live','x'*60000)
  except redis.exceptions.RedisError as exc:error={'type':type(exc).__name__,'message':str(exc)}
  messages=self.messages();after=self.r.hgetall(self.keys[3]);after_marker=self.r.get(self.keys[2])
  used_after=self.r.info('memory')['used_memory'];memory_record_after=self.r.memory_usage(self.keys[3])
  self.r.config_set('maxmemory',0)
  observation={'used_memory_before':used,'temporary_limit':max(1,used-100000),'result':result,'error':error,
   'new_publication_sizes':[len(m) for m in messages],'used_memory_after':used_after,'policy_at_observation':self.r.config_get('maxmemory-policy'),'record_memory_before':memory_record_before,'record_memory_after':memory_record_after,'record_changed':after!=before,'marker_before':marker,'marker_after':after_marker,
   'snapshot_after_restoring_limit':self.snap()}
  RESULTS['observations']['oom']=observation
  # An observation, NOT an assertion that actual OOM matches our in-script fake failure.
  self.assertTrue(error is not None or result is not None)

if __name__=='__main__':
 if os.environ.get('DNPL_RUN_REAL_REDIS')!='1':raise SystemExit('Not run: explicit permitted runtime invocation required')
 OUTPUT.mkdir(parents=True,exist_ok=True)
 result=unittest.main(verbosity=2,exit=False).result
 RESULTS['status']='completed successfully' if result.wasSuccessful() else 'failed or blocked'
 RESULTS['outcome']={'tests_run':result.testsRun,'failure_count':len(result.failures),'error_count':len(result.errors),'skipped':len(result.skipped),'successful':result.wasSuccessful(),'failures':[{'test':t.id(),'traceback':tb} for t,tb in result.failures],'errors':[{'test':t.id(),'traceback':tb} for t,tb in result.errors]}
 (OUTPUT/'results.json').write_text(json.dumps(RESULTS,indent=2)+'\n')
 raise SystemExit(0 if result.wasSuccessful() else 1)
