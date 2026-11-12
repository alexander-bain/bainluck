import copy
from datetime import datetime,timedelta,timezone
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace
import pytest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from current_source import load
bp,lbr=load()
from retention_input import prepare
spec=importlib.util.spec_from_file_location('baseline_preview_registry',ROOT/'reference/backend/app/utils/blend_preview.py')
base=importlib.util.module_from_spec(spec);sys.modules[spec.name]=base;spec.loader.exec_module(base)
T=datetime(2026,10,21,tzinfo=timezone.utc)
EVENT=SimpleNamespace(status='live',espn_win_prob_home=None,opening_home_probability=None)
BASE={'polymarket':{'value':.2,'updated_at':(T-timedelta(seconds=1)).isoformat()}}
KEYS=['epoch','owner','enabled','event','channel']
META={'lease_id','original_expires_at_ms','lease_issued_at_ms'}
class Clock:
 def __init__(self):self.t=0.;self.offset=0.;self.fail=False
 def mono(self):return 1000+self.t
 def wall(self):
  if self.fail:raise RuntimeError('optional clock unavailable')
  return T.timestamp()+self.t+self.offset

def reg(clock=None,**kw):
 c=clock or Clock();return bp.PreviewRegistry(clock=c.mono,wall_clock=c.wall,epoch=7,**kw),c

def propose(r,c,source='polymarket',value=.73,event_id=1,**kw):
 return r.propose(event_id,source,value=value,event=EVENT,row_sources=kw.pop('row_sources',BASE),
   row_rev=kw.pop('row_rev',0),observed_basis=kw.pop('observed_basis',{'101':T.timestamp()}),
   stamped_at=T+timedelta(seconds=c.t),**kw)

def only(frames):return next(f for f in frames if f['preview']['kind']=='blend')
def meta(f):return f['preview']
def strip(f):
 f=copy.deepcopy(f)
 for k in META:f['preview'].pop(k,None)
 return f

def test_all_original_fields_match_current_source_through_changed_and_same_value_observations():
 r,c=reg();b=base.PreviewRegistry(clock=c.mono,epoch=7)
 for t,val,basis in [(0,.73,T.timestamp()),(2,.73,T.timestamp()),(4,.81,T.timestamp()+1),(6,.73,T.timestamp()+2)]:
  c.t=t
  args=dict(value=val,observed_basis={'101':basis})
  assert [strip(f) for f in propose(r,c,**args)]==propose(b,c,**args)

def test_quiet_repeats_keep_identity_deadline_and_observation():
 r,c=reg();out=[]
 for t in [0,2,4,6,8]:c.t=t;out.append(only(propose(r,c)))
 assert len({meta(f)['lease_id'] for f in out})==1
 assert len({meta(f)['original_expires_at_ms'] for f in out})==1
 assert {f['display_observed_at'] for f in out}=={T.isoformat()}
 assert [meta(f)['ttl_ms'] for f in out]==[60000,58000,56000,54000,52000]
 assert [prepare(f,KEYS)[8] for f in out]==['offer']*5
 assert meta(out[0])['original_expires_at_ms']==int(T.timestamp()*1000)+59999

def test_changed_probability_and_new_observation_do_not_renew_chain():
 r,c=reg();a=only(propose(r,c));c.t=30;b=only(propose(r,c,value=.81,observed_basis={'101':T.timestamp()+20}))
 assert meta(a)['lease_id']==meta(b)['lease_id'];assert meta(a)['original_expires_at_ms']==meta(b)['original_expires_at_ms']
 assert a['display_observed_at']!=b['display_observed_at'];assert b['p']!=a['p']

def test_current_observation_only_admission_changes_freshness_not_lease():
 r,c=reg();stored={'polymarket':{'value':.73,'updated_at':(T-timedelta(seconds=1)).isoformat()}}
 a=only(propose(r,c,row_sources=stored,observation_only=True));c.t=2
 b=only(propose(r,c,row_sources=stored,observation_only=True,observed_basis={'101':T.timestamp()+1}))
 assert a['p']==b['p'];assert a['display_observed_at']!=b['display_observed_at']
 assert meta(a)['lease_id']==meta(b)['lease_id'];assert meta(a)['original_expires_at_ms']==meta(b)['original_expires_at_ms']
 assert propose(r,c,row_sources=stored,observation_only=True,observed_basis={'101':T.timestamp()+1})==[]

def test_same_started_sibling_chains_are_distinct_and_bounded():
 r,c=reg();propose(r,c);propose(r,c,source='kalshi',value=.4)
 pending=r._events[1].pending
 assert pending['polymarket'].since==pending['kalshi'].since
 assert pending['polymarket'].lease.identity!=pending['kalshi'].lease.identity
 assert len(pending)==2

def test_oldest_sibling_controls_deadline_and_removal_can_reveal_later_chain():
 r,c=reg();a=only(propose(r,c));c.t=5;b=only(propose(r,c,source='kalshi',value=.4))
 assert meta(a)['lease_id']==meta(b)['lease_id']
 c.t=10;remaining=only(r.refused(1,'polymarket','withdrawn'))
 assert meta(remaining)['lease_id']!=meta(a)['lease_id']
 assert meta(remaining)['original_expires_at_ms']==meta(a)['original_expires_at_ms']+5000
 assert meta(remaining)['ttl_ms']==55000

def test_sibling_commit_recomposes_without_changing_pending_chain():
 r,c=reg();a=only(propose(r,c));c.t=5
 new={'kalshi':{'value':.4,'updated_at':(T+timedelta(seconds=5)).isoformat()}}
 b=only(r.committed(1,'kalshi',seq=None,sources=new,rev=1,event=EVENT))
 assert meta(b)['base_rev']==1;assert meta(a)['lease_id']==meta(b)['lease_id']
 assert meta(a)['original_expires_at_ms']==meta(b)['original_expires_at_ms']

def test_commit_of_older_attempt_does_not_retire_later_pending_chain():
 r,c=reg();a=only(propose(r,c));c.t=2;b=only(propose(r,c,value=.8))
 c.t=3;r.committed(1,'polymarket',seq=meta(a)['seq'],sources=BASE,rev=1,event=EVENT)
 assert r.has_pending(1);assert r._events[1].pending['polymarket'].lease.identity==int(meta(b)['lease_id'].split(':')[1])

def test_true_commit_then_new_proposal_starts_new_identity():
 r,c=reg();a=only(propose(r,c));c.t=2
 assert r.committed(1,'polymarket',seq=meta(a)['seq'],sources=BASE,rev=1,event=EVENT)==[]
 b=only(propose(r,c,row_rev=1));assert meta(a)['lease_id']!=meta(b)['lease_id']
 assert meta(b)['original_expires_at_ms']>meta(a)['original_expires_at_ms']

def test_refusal_then_same_value_is_new_chain():
 r,c=reg();a=only(propose(r,c));revoke=r.refused(1,'polymarket','refused')[0]
 assert revoke['preview']['kind']=='revoke';assert META.isdisjoint(meta(revoke))
 c.t=2;b=only(propose(r,c));assert meta(a)['lease_id']!=meta(b)['lease_id']

def test_expired_same_value_cannot_reanchor_until_genuine_end():
 r,c=reg(max_uncommitted_s=3);a=only(propose(r,c));c.t=3
 assert r.expire()[0]['preview']['kind']=='revoke';assert propose(r,c)==[]
 c.t=4;b=only(propose(r,c,value=.8));assert meta(a)['lease_id']!=meta(b)['lease_id']

def test_metadata_failure_on_first_proposal_stays_live_only_for_chain():
 c=Clock();c.fail=True;r,c=reg(c);a=only(propose(r,c));assert META.isdisjoint(meta(a))
 c.fail=False;c.t=2;b=only(propose(r,c));assert META.isdisjoint(meta(b))
 assert prepare(b,KEYS)[8]=='uncached';assert b['p']==.73

def test_transient_compose_metadata_failure_does_not_destroy_original_anchor():
 r,c=reg();a=only(propose(r,c));c.fail=True;c.t=2;b=only(propose(r,c));assert META.isdisjoint(meta(b))
 c.fail=False;c.t=4;d=only(propose(r,c));assert meta(a)['original_expires_at_ms']==meta(d)['original_expires_at_ms']

@pytest.mark.parametrize('jump',[-86400,86400])
def test_wall_jump_never_reanchors_fixed_chain(jump):
 r,c=reg();a=only(propose(r,c));c.t=2;c.offset=jump;b=only(propose(r,c))
 assert meta(a)['original_expires_at_ms']==meta(b)['original_expires_at_ms']
 assert meta(a)['lease_id']==meta(b)['lease_id'];assert meta(b)['ttl_ms']==58000
 if jump<0:assert prepare(b,KEYS)[8]=='uncached'

def test_first_epoch_none_then_claim_does_not_change_lease():
 c=Clock();r=bp.PreviewRegistry(clock=c.mono,wall_clock=c.wall);a=only(propose(r,c));assert meta(a)['epoch'] is None
 r.epoch=7;a['preview']['epoch']=7;c.t=2;b=only(propose(r,c))
 assert meta(a)['lease_id']==meta(b)['lease_id'];assert prepare(a,KEYS)[8]=='offer'

def test_eviction_revoke_does_not_reuse_retired_token():
 r,c=reg(max_events=1);a=only(propose(r,c));out=propose(r,c,event_id=2)
 assert out[-1]['preview']['reason']=='evicted';assert len(r._events)==1
 c.t=2;b=only(propose(r,c,event_id=1));assert meta(a)['lease_id']!=meta(b)['lease_id']

def test_fractional_times_never_offer_deadline_later_than_original():
 r,c=reg();original=None
 for t in [.0001,.5002,1.2345,20.9999,59.999]:
  c.t=t;f=only(propose(r,c));p=meta(f)
  original=original or p['original_expires_at_ms'];assert p['original_expires_at_ms']==original
  cmd=prepare(f,KEYS)
  assert cmd[8] in {'offer','uncached'}
  if cmd[8]=='offer':assert p['original_expires_at_ms']<=p['lease_issued_at_ms']+p['ttl_ms']
