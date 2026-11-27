import json
import unittest
from adapter import Commands

class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.c=Commands(('counter','owner','enabled','record','channel'), 1)
        self.frame={'event_id':1,'p':.73,'status':'live','provisional':True,
                    'preview':{'kind':'blend','epoch':1,'seq':2,'base_rev':0,'ttl_ms':60000,
                    'lease_id':'chain-A','original_expires_at_ms':160000}}
    def offer(self):return self.c.offer(self.frame,issued_at_ms=100000)
    def test_payload_and_metadata_same_object(self):
        a=self.offer();self.assertEqual(a[8],'offer');p=json.loads(a[-1]);self.assertEqual(p,self.frame)
        self.assertEqual(a[11],p['preview']['seq']);self.assertEqual(a[13],p['preview']['lease_id'])
    def test_mutating_caller_does_not_change_built_payload(self):
        a=self.offer();self.frame['p']=.2;self.assertEqual(json.loads(a[-1])['p'],.73)
    def test_production_frame_without_original_deadline_is_uncached_not_dropped(self):
        del self.frame['preview']['original_expires_at_ms'];self.assertEqual(self.offer()[8],'uncached')
    def test_no_lease_id_is_uncached(self):
        del self.frame['preview']['lease_id'];self.assertEqual(self.offer()[8],'uncached')
    def test_later_than_original_budget_is_uncached(self):
        self.frame['preview']['original_expires_at_ms']=170000;self.assertEqual(self.offer()[8],'uncached')
    def test_nan_probability_rejected(self):
        self.frame['p']=float('nan')
        with self.assertRaises(ValueError):self.offer()
    def test_wrong_event_rejected(self):
        self.frame['event_id']=2
        with self.assertRaises(ValueError):self.offer()
    def test_committed_disguise_rejected(self):
        self.frame['rev']={'1':2}
        with self.assertRaises(ValueError):self.offer()
    def test_revoke_orders_on_own_seq(self):
        self.frame['preview']={'kind':'revoke','epoch':1,'seq':9,'through_seq':3}
        a=self.offer();self.assertEqual(a[11],9)
    def test_invalid_revoke_rejected(self):
        self.frame['preview']={'kind':'revoke','epoch':1,'seq':9,'through_seq':9}
        with self.assertRaises(ValueError):self.offer()
    def test_committed_status_not_passed_as_authority(self):
        a=self.c.committed({'event_id':1,'rev':{'1':4},'status':'final','p':.73})
        self.assertEqual(a[8:10],('committed',4));self.assertEqual(len(a),11)
    def test_snapshot_requires_complete_coverage(self):
        for rev,status in [(None,'live'),(0,None),(True,'live'),(0,'')]:
            with self.assertRaises(ValueError):self.c.snapshot(database_revision=rev,database_status=status)
    def test_snapshot_supplies_status_separately(self):
        self.assertEqual(self.c.snapshot(database_revision=3,database_status='final')[8:],('snapshot',3,'final'))
    def test_boolean_epoch_rejected(self):
        self.frame['preview']['epoch']=True
        with self.assertRaises(ValueError):self.offer()
    def test_retained_payload_is_bounded_without_dropping_healthy_live(self):
        self.frame['pad']='x'*70000
        self.assertEqual(self.offer()[8],'uncached')

if __name__=='__main__':unittest.main()
