"""Pure receipt/identity guards: no application imports, services or timing."""
import ast
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).with_name('run.py')
spec = importlib.util.spec_from_file_location('linked_pair', SOURCE)
lab = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lab)


class QualificationControls(unittest.TestCase):
    def test_target_join_requires_real_exact_single_key_revision_map(self):
        self.assertTrue(lab.matches_target({'event_id':17,'rev':{'17':2},'p':.74},17,2,.74))
        for frame in ({'event_id':1,'rev':{'1':2},'p':.74},
                      {'event_id':17,'rev':{'17':1},'p':.74},
                      {'event_id':17,'rev':{'17':2},'p':.59},
                      {'event_id':17,'rev':2,'p':.74},
                      {'event_id':17,'rev':{'17':2,'1':2},'p':.74},
                      {'event_id':17,'rev':{'1':2},'p':.74}):
            self.assertFalse(lab.matches_target(frame,17,2,.74))

    def test_causal_batch_requires_whole_burst_disjoint_debt_and_live_membership(self):
        args = ({1:'a',2:'b'},{1:17,2:3},{18},{17},{1,2},18,17)
        self.assertIsNone(lab.affected_batch_error(*args))
        for index,value in ((0,{1:'a'}),(2,set()),(2,{18,17}),(3,set()),(1,{1:18,2:3}),(1,{1:None,2:3})):
            altered=list(args);altered[index]=value
            self.assertIsNotNone(lab.affected_batch_error(*altered))

    def test_ref_resolution_is_literal_git_argument_not_shell_interpolation(self):
        with patch.object(lab.subprocess,'check_output',return_value=lab.QUIET_PAIR[0]+'\n') as read:
            self.assertEqual(lab.resolve_application_ref('HEAD'),lab.QUIET_PAIR[0])
        self.assertEqual(read.call_args.args[0][-1],'HEAD^{commit}')
        self.assertNotIn('shell',read.call_args.kwargs)

    def test_parity_excludes_stamp_clock_but_preserves_values_revisions_and_chart_rows(self):
        def state(clock,p=.74):
            return {'all_prices':[[1,.74,1,None,None]],'snapshots':[[17,'kalshi',.74,.26]],'all_events':[{'id':17,'p':p,'rev':2,'sources':{'kalshi':{'value':p,'updated_at':clock}}}]}
        self.assertEqual(lab.parity_signature(state('a')),lab.parity_signature(state('b')))
        self.assertNotEqual(lab.parity_signature(state('a')),lab.parity_signature(state('b',.59)))

    def test_all_row_guard_rejects_loss_wrong_price_wrong_blend_or_resolution(self):
        prices={i:.62 for i in range(36)};events={i:.62 for i in range(18)}
        def state():
            return {'all_prices':[[i,.62,1,None,None] for i in prices],'all_events':[{'id':i,'p':.62,'rev':1,'sources':{'kalshi':{'value':.62}}} for i in events]}
        self.assertIsNone(lab.fixture_parity_error(state(),prices,events))
        bad=state();bad['all_prices'].pop();self.assertIsNotNone(lab.fixture_parity_error(bad,prices,events))
        for column,value in ((1,.61),(3,True),(4,'api_settlement')):
            bad=state();bad['all_prices'][0][column]=value;self.assertIsNotNone(lab.fixture_parity_error(bad,prices,events))
        bad=state();bad['all_events'][0]['p']=.59;self.assertIsNotNone(lab.fixture_parity_error(bad,prices,events))

    def test_subject_engine_factory_and_cadence_are_forwarded(self):
        tree=ast.parse(SOURCE.read_text())
        # Refuse restoring the six-pool substitute or an engine-factory assignment.
        for node in ast.walk(tree):
            if isinstance(node,ast.Assign):
                for target in node.targets:
                    self.assertFalse(isinstance(target,ast.Attribute) and target.attr=='_get_task_engine')
        replay=next(n for n in tree.body if isinstance(n,ast.AsyncFunctionDef) and n.name=='replay')
        self.assertNotIn('create_async_engine',ast.unparse(replay))
        observe=next(n for n in ast.walk(replay) if isinstance(n,ast.AsyncFunctionDef) and n.name=='observed')
        self.assertIn('await flush(started)',ast.unparse(observe))
        self.assertNotIn('sleep',ast.unparse(observe))
        planner=next(n for n in ast.walk(replay) if isinstance(n,ast.FunctionDef) and n.name=='observe_plan')
        self.assertIn('original_planner(',ast.unparse(planner))


if __name__ == '__main__':
    unittest.main()
