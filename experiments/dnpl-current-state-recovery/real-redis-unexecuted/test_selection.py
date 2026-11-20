"""No sockets/processes: preflight and actual adapter command dispatch only."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch
from selection import preflight, LUA_SHA256, ADAPTER_SHA256
ROOT=Path(__file__).resolve().parent
class Selection(unittest.TestCase):
 def load(self):
  with patch('subprocess.Popen',side_effect=AssertionError('no process allowed')),patch('socket.socket.connect',side_effect=AssertionError('no connection allowed')):
   spec=importlib.util.spec_from_file_location('unexecuted_redis_suite',ROOT/'test_real_redis.py')
   m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
  return m
 def test_corrected_hashes_and_adapter(self):
  m=self.load();a,s=preflight();self.assertEqual(a.SCRIPT,s);self.assertEqual(m.EXPECTED,LUA_SHA256)
  self.assertEqual(m.RESULTS['adapter_sha256'],ADAPTER_SHA256)
 def test_actual_adapter_tuples_selected_without_connection(self):
  m=self.load();case=m.RealRedis();case.keys=['counter','owner','enabled','record','channel'];case.commands=m.ADAPTER.Commands(case.keys,1)
  class Fake:
   def __init__(self):self.commands=[]
   def time(self):return [100,0]
   def get(self,key):return '1'
   def execute_command(self,*args):self.commands.append(args);return ['not executed']
  case.r=Fake();case.call('claim');case.offer(100000000000004);case.call('committed',1,'commit');case.snap(1)
  self.assertEqual([x[8] for x in case.r.commands],['claim','offer','committed','snapshot'])
  for x in case.r.commands:self.assertEqual(x[1],m.SCRIPT)
  self.assertEqual(case.r.commands[1][11],100000000000004)
 def test_real_case_count_is_only_syntax_inventory(self):
  m=self.load();names=[x for x in dir(m.RealRedis) if x.startswith('test_')];self.assertEqual(len(names),23)
  self.assertEqual(m.RESULTS['tests'],[])
if __name__=='__main__':unittest.main(verbosity=2)
