"""Independent source-seam checks; in-memory boundaries, no sockets or services."""
import copy
from datetime import datetime, timezone
from pathlib import Path
import sys
from types import SimpleNamespace
import pytest
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'producer-chain-metadata'))
import current_source
bp,lbr=current_source.load(candidate=True)
from producer_driver import ProducerDriver
import retention_input
WALL=1792540800.0
META={'lease_id','original_expires_at_ms','lease_issued_at_ms'}
class Clock:
 def __init__(self):self.t=0.;self.offset=0.;self.failed=False
 def mono(self):return 1000+self.t
 def wall(self):
  if self.failed:raise RuntimeError('optional wall sample failed')
  return WALL+self.t+self.offset
 def date(self):return datetime.fromtimestamp(WALL+self.t,timezone.utc)
def registry(clock=None,**kw):
 c=clock or Clock();return bp.PreviewRegistry(clock=c.mono,wall_clock=c.wall,max_uncommitted_s=10,epoch=7,**kw),c
def event(status='live'):return SimpleNamespace(status=status,espn_win_prob_home=None,opening_home_probability=None)
def base():return {'kalshi':{'value':.5,'updated_at':datetime.fromtimestamp(WALL-1,timezone.utc).isoformat()}}
def propose(r,c,source='kalshi',value=.73,**kw):
 return r.propose(1,source,value=value,event=event(),row_sources=base(),row_rev=0,stamped_at=c.date(),observed_basis={'101':WALL},**kw)
def metadata(frame):return {k:frame['preview'][k] for k in META if k in frame['preview']}
def test_changed_value_and_attempt_clock_do_not_start_new_lease():
 r,c=registry();a=propose(r,c)[0];c.t=4;b=propose(r,c,value=.74)[0]
 assert a['preview']['lease_id']==b['preview']['lease_id']
 assert a['preview']['original_expires_at_ms']==b['preview']['original_expires_at_ms']==int((WALL+10)*1000)-1
 assert [a['preview']['ttl_ms'],b['preview']['ttl_ms']]==[10000,6000]
 assert a['observed_at']!=b['observed_at']
 assert a['display_observed_at']==b['display_observed_at']
def test_local_wall_jumps_do_not_restamp_original_deadline():
 r,c=registry();a=propose(r,c)[0];deadline=a['preview']['original_expires_at_ms'];identity=a['preview']['lease_id']
 for offset in (3600,-3600,0):
  c.t+=1;c.offset=offset;b=propose(r,c)[0]
  assert b['preview']['original_expires_at_ms']==deadline and b['preview']['lease_id']==identity
 c.offset=-3600;cmd=retention_input.prepare(propose(r,c)[0],['counter','owner','marker','record','channel'])
 assert cmd[8]=='uncached','backward wall offset cannot synthesize a longer retained budget'
def test_initial_metadata_failure_remains_live_only_for_entire_chain():
 r,c=registry();c.failed=True;a=propose(r,c)[0];assert not metadata(a)
 c.failed=False;c.t=2;b=propose(r,c)[0];assert not metadata(b)
 assert retention_input.prepare(b,['counter','owner','marker','record','channel'])[8]=='uncached'
 r.refused(1,'kalshi','stale');d=propose(r,c)[0];assert metadata(d)
def test_equal_start_siblings_have_distinct_chains_and_drop_selects_remaining():
 r,c=registry();a=propose(r,c)[0];propose(r,c,source='polymarket',value=.8)
 k=r._events[1].pending['kalshi'].lease;p=r._events[1].pending['polymarket'].lease
 assert k.identity!=p.identity
 b=r.refused(1,'kalshi','stale')[0]
 assert b['preview']['lease_id']!='pending:'+str(k.identity)
 assert b['preview']['lease_id']=='pending:'+str(p.identity)
 assert b['preview']['original_expires_at_ms']==a['preview']['original_expires_at_ms']
def test_expiring_oldest_reveals_siblings_original_not_fresh_deadline():
 r,c=registry();a=propose(r,c)[0];c.t=5;propose(r,c,source='polymarket',value=.8)
 sibling=r._events[1].pending['polymarket'].lease;c.t=10;b=r.expire()[0]
 assert b['preview']['ttl_ms']==5000
 assert b['preview']['lease_id']=='pending:'+str(sibling.identity)
 assert b['preview']['original_expires_at_ms']==int((WALL+15)*1000)-1
 assert b['preview']['original_expires_at_ms']!=int((WALL+c.t+10)*1000)-1
 assert propose(r,c)==[], 'expired same value cannot reopen the chain'
def test_older_commit_does_not_retire_newer_pending_identity():
 r,c=registry();a=propose(r,c)[0];c.t=1;b=propose(r,c,value=.75)[0]
 held=r._events[1].pending['kalshi'].lease
 frames=r.committed(1,'kalshi',seq=a['preview']['seq'],sources=base(),rev=1,event=event())
 assert frames and frames[0]['preview']['base_rev']==1
 assert r._events[1].pending['kalshi'].lease is held
 assert frames[0]['preview']['lease_id']==b['preview']['lease_id']
 r.committed(1,'kalshi',seq=b['preview']['seq'],sources=base(),rev=2,event=event())
 assert not r.has_pending(1)
 d=propose(r,c)[0];assert d['preview']['lease_id']!=b['preview']['lease_id']
def test_metadata_state_is_bounded_with_event_state():
 r,c=registry(max_events=1);propose(r,c)
 frames=r.propose(2,'kalshi',value=.8,event=event(),row_sources=base(),row_rev=0,stamped_at=c.date())
 assert len(r._events)==1 and 1 not in r._events
 assert frames[-1]['preview']['kind']=='revoke'
 assert not any(k in frames[-1]['preview'] for k in META)
@pytest.mark.asyncio
async def test_actual_current_quiet_retry_and_commit_preserve_chain_and_observation():
 with ProducerDriver(base_rev=0) as d:
  assert type(d.registry) is bp.PreviewRegistry
  d.registry._wall_clock=lambda:d.clock.now().timestamp()
  for t,locked in ((0,True),(2,True),(4,False)):
   await d.step(t,locked=locked)
  previews=[x['frame'] for x in d.frames if x['kind']=='preview' and x['frame']['preview']['kind']=='blend']
  assert len(previews)==3
  assert len({f['preview']['lease_id'] for f in previews})==1
  assert len({f['preview']['original_expires_at_ms'] for f in previews})==1
  assert [f['preview']['ttl_ms'] for f in previews]==[60000,58000,56000]
  assert len({f['display_observed_at'] for f in previews})==1
  assert [f['preview']['epoch'] for f in previews]==[1,1,1]
  assert d.frames[-1]['kind']=='committed' and not d.registry.has_pending(1)
  assert not any(f['preview']['kind']=='revoke' for f in previews)
  for f in previews:
   cmd=retention_input.prepare(f,['counter','owner','marker','record','channel'])
   assert cmd[8]=='offer'
  assert d.steps[1]['method'].startswith('refresh_pending') and not d.steps[1]['fresh_input']

def driver_frame(d):
 return d.registry.propose(d.event_id,d.source,value=d.value,event=d.event,row_sources=d.stored,row_rev=d.base_rev,
   observed_basis={'101':d.outcomes[0].last_updated.timestamp()},stamped_at=d.clock.now())[0]

def trace_commands(d):
 trace=[];send=d.connection.send_command
 async def record(*args):
  trace.append(args)
  await send(*args)
 d.connection.send_command=record
 return trace

@pytest.mark.asyncio
async def test_current_publisher_keeps_one_ordered_batch_and_fills_preclaim_epoch():
 with ProducerDriver(base_rev=0) as d:
  d.registry._wall_clock=lambda:d.clock.now().timestamp()
  a=driver_frame(d);b=d.registry.refused(1,d.source,'stale')[0]
  original_id=a['preview']['lease_id'];assert a['preview']['epoch'] is None
  trace=trace_commands(d);await d.refresher._publish_previews([a,b])
  assert [x[1] for x in trace]==[bp.FENCE_CLAIM_SCRIPT,bp.FENCE_PUBLISH_SCRIPT]
  assert [x['frame']['preview']['kind'] for x in d.frames]==['blend','revoke']
  assert [x['frame']['preview']['epoch'] for x in d.frames]==[1,1]
  assert d.frames[0]['frame']['preview']['lease_id']==original_id
  assert d.refresher.preview_stats['published']==1 and d.refresher.preview_stats['revoked']==1

@pytest.mark.asyncio
async def test_lost_owner_with_known_epoch_fences_blend_without_reclaim_but_passes_revoke():
 with ProducerDriver(base_rev=0) as d:
  d.registry._wall_clock=lambda:d.clock.now().timestamp();trace=trace_commands(d)
  await d.refresher._publish_previews([driver_frame(d)])
  d.connection.owner=None;d.clock.seconds=2
  a=driver_frame(d);b=d.registry.refused(1,d.source,'stale')[0]
  await d.refresher._publish_previews([a,b])
  assert sum(x[1]==bp.FENCE_CLAIM_SCRIPT for x in trace)==1
  assert d.registry.epoch==1 and d.connection.owner is None
  assert [x['frame']['preview']['kind'] for x in d.frames]==['blend','revoke']
  assert d.refresher.preview_stats['fenced']==1

@pytest.mark.asyncio
async def test_unknown_publish_ack_disconnects_without_retry_or_lease_reset():
 with ProducerDriver(base_rev=0) as d:
  d.registry._wall_clock=lambda:d.clock.now().timestamp();trace=trace_commands(d)
  a=driver_frame(d);lease=d.registry._events[1].pending[d.source].lease
  read=d.connection.read_response
  async def lost_ack():
   if trace and trace[-1][1]==bp.FENCE_PUBLISH_SCRIPT:raise RuntimeError('lost publication acknowledgement')
   return await read()
  d.connection.read_response=lost_ack
  await d.refresher._publish_previews([a])
  assert len(d.frames)==1,'modeled publish occurred before lost acknowledgement'
  assert sum(x[1]==bp.FENCE_PUBLISH_SCRIPT for x in trace)==1
  assert d.connection.disconnected and d.refresher._redis is None
  assert d.registry._events[1].pending[d.source].lease is lease
  assert d.refresher.preview_stats['publish_errors']==1
  assert d.refresher.preview_stats['published']==0,'no claimed acknowledgement after ambiguous outcome'

@pytest.mark.asyncio
async def test_prepare_frames_is_after_claim_and_empty_callback_does_not_publish():
 with ProducerDriver(base_rev=0) as d:
  trace=trace_commands(d);called=[]
  async def prepare():
   called.append(d.registry.epoch)
   return []
  await d.refresher._publish_previews([],prepare_frames=prepare)
  assert called==[1]
  assert len(trace)==1 and trace[0][1]==bp.FENCE_CLAIM_SCRIPT
  assert not d.frames and not d.registry._events
