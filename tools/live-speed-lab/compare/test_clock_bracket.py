import unittest
from clock_bracket import eligible_interval

class ClockBracketTests(unittest.TestCase):
    def evidence(self, post=1000.5):
        return ({'source':'polymarket','mono':1.0,'frames':[{'event_type':'best_bid_ask','timestamp':'1000'}]*2},
                {'target_sent_mono':1.0,'target_sent_wall_ms':post})
    def call(self, **kw):
        t,r=self.evidence();return eligible_interval(t,r,20,1,stable_backend_clock=True,**kw)
    def test_asymmetric(self): self.assertEqual(self.call()['at_ms'],[18.5,21])
    def test_assumption_required(self):
        t,r=self.evidence();self.assertEqual(eligible_interval(t,r,20,1)['status'],'timing_unknown')
    def test_delayed_send_no_false_fast(self):
        t,r=self.evidence(1300); result=eligible_interval(t,r,400,1,stable_backend_clock=True)
        # First display at1200: old estimate max801ms; corrected max1101ms.
        self.assertEqual(1200-result['at_ms'][0],1101)
        self.assertGreater(1200-result['at_ms'][0],1000)
    def test_inverted(self):
        t,r=self.evidence(999);self.assertEqual(eligible_interval(t,r,20,1,stable_backend_clock=True)['status'],'timing_unknown')
    def test_mono_mismatch(self):
        t,r=self.evidence();t['mono']=2;self.assertEqual(eligible_interval(t,r,20,1,stable_backend_clock=True)['status'],'timing_unknown')
    def test_missing_timestamp(self):
        t,r=self.evidence();t['frames']=[{}]*2;self.assertEqual(eligible_interval(t,r,20,1,stable_backend_clock=True)['status'],'timing_unknown')
    def test_boundary_unknown(self):
        t,r=self.evidence();self.assertEqual(eligible_interval(t,r,0,1,stable_backend_clock=True)['status'],'timing_unknown')
    def test_malformed_dicts(self):
        for bad in (None, 'bad'):
            t,r=self.evidence();t['frames']=[bad,bad]
            self.assertEqual(eligible_interval(t,r,20,1,stable_backend_clock=True)['status'],'timing_unknown')
            self.assertEqual(eligible_interval(bad,r,20,1,stable_backend_clock=True)['status'],'timing_unknown')
    def test_nonfinite(self):
        t,r=self.evidence(float('nan'));self.assertEqual(eligible_interval(t,r,20,1,stable_backend_clock=True)['status'],'timing_unknown')
if __name__=='__main__':unittest.main()
