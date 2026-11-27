import asyncio
import json
from pathlib import Path
import sys
import pytest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from current_source import load
bp,lbr=load()
from producer_driver import ProducerDriver
from retention_input import prepare
pytestmark=pytest.mark.asyncio
KEYS=['epoch','owner','enabled','event','channel']
def blends(d):return [x['frame'] for x in d.frames if x['kind']=='preview' and x['frame']['preview']['kind']=='blend']
def direct(d,event_id=1,value=.73):
 return d.registry.propose(event_id,d.source,value=value,event=d.event,row_sources=d.stored,row_rev=d.base_rev,
   observed_basis={'101':d.outcomes[0].last_updated.timestamp()},stamped_at=d.clock.now())
def track(d):
 commands=[];old=d.connection.send_command
 async def send(*args):commands.append(args);return await old(*args)
 d.connection.send_command=send
 return commands

async def test_actual_current_quiet_retry_preserves_source_and_lease_before_real_commit_path():
 with ProducerDriver() as d:
  for t in [0,2,4,6,8]:await d.step(t,locked=t!=8)
  out=blends(d)
  assert [f['preview']['ttl_ms'] for f in out]==[60000,58000,56000,54000,52000]
  assert len({f['preview']['lease_id'] for f in out})==1
  assert len({f['preview']['original_expires_at_ms'] for f in out})==1
  assert len({f['display_observed_at'] for f in out})==1
  assert all(prepare(f,KEYS)[8]=='offer' for f in out)
  assert [x['kind'] for x in d.steps[-1]['publications']]==['preview','committed']
  assert d.frames[-1]['commits_before_publish']==1
  assert not d.registry.has_pending(1);assert d.refresher.preview_stats['publish_errors']==0

async def test_actual_current_expiry_refuses_quiet_reopening():
 with ProducerDriver(max_uncommitted_s=3) as d:
  for t in [0,2,4,6]:await d.step(t,locked=True)
  assert [f['preview']['ttl_ms'] for f in blends(d)]==[3000,1000]
  assert len([x for x in d.frames if x['frame']['preview']['kind']=='revoke'])==1
  assert d.steps[-1]['publications']==[]

async def test_entire_current_batch_claimed_once_and_serialized_in_original_order():
 with ProducerDriver() as d:
  commands=track(d);frames=direct(d)+direct(d,event_id=2)+d.registry.refused(1,d.source,'withdrawn')
  assert all(f['preview']['epoch'] is None for f in frames)
  await d.refresher._publish_previews(frames)
  assert len(commands)==2;assert commands[0][1]==bp.FENCE_CLAIM_SCRIPT;assert commands[1][1]==bp.FENCE_PUBLISH_SCRIPT
  wire=commands[1];assert wire[2]==1
  triples=wire[5:];payloads=[json.loads(triples[i+2]) for i in range(0,len(triples),3)]
  assert [(f['event_id'],f['preview']['kind']) for f in payloads]==[(1,'blend'),(2,'blend'),(1,'revoke')]
  assert all(f['preview']['epoch']==1 for f in payloads)
  assert all('lease_id' in f['preview'] for f in payloads[:2]);assert len(d.frames)==3

async def test_optional_metadata_failure_keeps_whole_healthy_batch_live():
 with ProducerDriver() as d:
  def fail():raise RuntimeError('optional wall clock failed')
  d.registry._wall_clock=fail;commands=track(d)
  frames=direct(d)+direct(d,event_id=2)
  await d.refresher._publish_previews(frames)
  assert len(commands)==2;assert len(d.frames)==2;assert d.refresher.preview_stats['publish_errors']==0
  assert all(prepare(f,KEYS)[8]=='uncached' for f in frames)

async def test_known_owner_loss_does_not_reclaim_or_retain():
 with ProducerDriver() as d:
  commands=track(d);await d.refresher._publish_previews(direct(d));commands.clear();d.frames.clear()
  d.connection.owner=None;d.clock.seconds=2
  await d.refresher._publish_previews(direct(d))
  assert len(commands)==1 and commands[0][1]==bp.FENCE_PUBLISH_SCRIPT
  assert not d.frames;assert d.registry.epoch==1;assert d.refresher.preview_stats['fenced']==1

async def test_superseded_owner_revoke_still_publishes_but_blend_is_fenced():
 with ProducerDriver() as d:
  await d.refresher._publish_previews(direct(d));d.frames.clear();d.connection.owner=2;commands=track(d)
  d.clock.seconds=2;frames=direct(d)+d.registry.refused(1,d.source,'withdrawn')
  await d.refresher._publish_previews(frames)
  assert len(commands)==1;assert len(d.frames)==1;assert d.frames[0]['frame']['preview']['kind']=='revoke'
  assert d.connection.owner==2 and d.registry.epoch==1

async def test_unknown_batch_ack_disconnects_without_resending_or_undoing_pending():
 with ProducerDriver() as d:
  await d.refresher.claim_preview_display();commands=track(d)
  async def ambiguous():raise ConnectionError('injected lost ACK after delivery')
  d.connection.read_response=ambiguous
  await d.refresher._publish_previews(direct(d)+direct(d,event_id=2))
  assert len(commands)==1;assert len(d.frames)==2;assert d.connection.disconnected
  assert d.registry.has_pending(1);assert d.registry.has_pending(2);assert d.refresher.preview_stats['publish_errors']==1

async def test_lost_initial_claim_ack_may_reclaim_but_old_known_epoch_may_not():
 with ProducerDriver() as d:
  original=d.connection.read_response
  async def lost():raise ConnectionError('injected first claim ACK loss')
  d.connection.read_response=lost
  await d.refresher.claim_preview_display();assert d.registry.epoch is None;assert d.connection.owner==1
  d.connection.read_response=original;d.refresher._redis=type('Client',(),{'connection_pool':type('Pool',(),{
   'get_connection':lambda self,*a: asyncio.sleep(0,result=d.connection),'release':lambda self,*a: asyncio.sleep(0)})()})()
  await d.refresher._publish_previews(direct(d));assert d.registry.epoch==2
  assert len(d.frames)==1 and d.frames[0]['frame']['preview']['epoch']==2

async def test_current_prepare_frames_runs_after_claim_and_can_abstain_without_mutation():
 with ProducerDriver() as d:
  commands=track(d);seen=[]
  async def prepare_frames():seen.append(d.registry.epoch);return []
  await d.refresher._publish_previews([],prepare_frames=prepare_frames)
  assert seen==[1];assert len(commands)==1;assert not d.registry.has_pending(1);assert not d.frames
