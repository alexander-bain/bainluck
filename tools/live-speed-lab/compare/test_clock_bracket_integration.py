import json, pathlib, shutil, tempfile, unittest
import compare
ROOT=pathlib.Path(__file__).resolve().parent
# Repo layout: the patch is applied to compare.py in place and the consume spec
# is the existing admission-retained.json. Its arms are retained evidence outside
# the repo; the controls skip, never pass, on a machine that does not hold them.
SPEC=ROOT/'admission-retained.json'

class IntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec=json.loads(SPEC.read_text())
        cls.arms=[pathlib.Path(spec[k]) for k in ('baseline','candidate')]
        missing=[str(a) for a in cls.arms if not (a/'backend-receipt.json').is_file()]
        if missing:raise unittest.SkipTest('retained admission arms named by admission-retained.json are absent: '+', '.join(missing))
        cls.tmp=tempfile.TemporaryDirectory(); cls.work=pathlib.Path(cls.tmp.name)
        cls.module=compare
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def test_default_arm_unknown(self):
        with self.assertRaisesRegex(ValueError,'timing_unknown'):self.module.admission_arm(self.arms[0])
    def test_default_consume_unknown(self):
        spec=json.loads(SPEC.read_text())
        with self.assertRaisesRegex(ValueError,'timing_unknown'):self.module.consume(spec,self.work/'consume')
        self.assertIn('timing_unknown',json.loads((self.work/'consume/INVALID.json').read_text())['reason'])
    def test_retained_opt_in(self):
        for arm, upper in zip(self.arms,[1125.155029296875,827.46484375]):
            result=self.module.admission_arm(arm,stable_backend_clock=True)
            self.assertAlmostEqual(result['score']['surfaces']['headline']['worst_delay_ms'][1],upper)
            self.assertIn('assumption',result['trace']['coverage']['backend_anchor'])
    def test_delayed_send_through_actual_adapter(self):
        arm=self.work/'synthetic-delay';shutil.copytree(self.arms[1],arm)
        receipt=json.loads((arm/'backend-receipt.json').read_text());receipt['runs'][0]['target_sent_wall_ms']+=300
        (arm/'backend-receipt.json').write_text(json.dumps(receipt))
        rows=[json.loads(x) for x in (arm/'reader.jsonl').read_text().splitlines()]
        for row in rows:row['wall']+=300
        (arm/'reader.jsonl').write_text('\n'.join(json.dumps(x) for x in rows))
        result=self.module.admission_arm(arm,stable_backend_clock=True)
        surface=result['score']['surfaces']['headline']
        self.assertEqual(surface['under_one_second']['definite'],0)
        self.assertEqual(surface['under_one_second']['uncertain'],1)
        self.assertGreater(surface['worst_delay_ms'][1],1000)
if __name__=='__main__':unittest.main()
