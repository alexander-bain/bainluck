"""Fresh remaining-duration contract over the actual isolated store implementation."""
from pathlib import Path
import importlib.util
import pytest
p=Path(__file__).resolve().parents[1]/'fixtures/authority_model.py'
spec=importlib.util.spec_from_file_location('monotonic_store',p);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

def test_remaining_is_recomputed_without_changing_original_expiry():
 clock=[1000.0];store=m.CurrentPreviewStore(lambda:clock[0]);store.claim_epoch(7)
 frame={'event_id':1,'p':.73,'status':'live','provisional':True,'preview':{'kind':'blend','epoch':7,'seq':1,'base_rev':0,'ttl_ms':6000}}
 assert store.publish(frame,1000,7000)
 a=store.snapshot(1);clock[0]=3000;b=store.snapshot(1)
 assert(a['lease_remaining_ms'],b['lease_remaining_ms'])==(6000,4000)
 assert a['frame']['preview']['lease_id']==b['frame']['preview']['lease_id']
 assert b['frame']['preview']['original_expires_at_ms']==7000
 clock[0]=7000;c=store.snapshot(1)
 assert c['lease_remaining_ms']==0 and c['frame'] is None

@pytest.mark.parametrize('elapsed',[0,1,200,1000,5999,6000,9000])
def test_fresh_budget_never_exceeds_original_deadline(elapsed):
 clock=[1000.0];store=m.CurrentPreviewStore(lambda:clock[0]);store.claim_epoch(1)
 frame={'event_id':1,'p':.73,'status':'live','provisional':True,'preview':{'kind':'blend','epoch':1,'seq':1,'base_rev':0,'ttl_ms':6000}}
 assert store.publish(frame,1000,7000)
 clock[0]+=elapsed;snapshot=store.snapshot(1)
 assert snapshot['lease_remaining_ms']==max(0,6000-elapsed)
