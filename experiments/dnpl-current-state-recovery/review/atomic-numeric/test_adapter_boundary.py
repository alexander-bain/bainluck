"""No network: real redis-py argument encoder plus isolated command adapter."""
import importlib.util
import json
from pathlib import Path
import unittest
from redis._parsers.encoders import Encoder
ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('numeric_review_adapter',ROOT/'atomic-numeric-encoding/adapter.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
MAX=2**53-1
class Boundary(unittest.TestCase):
 def setUp(self):
  self.c=m.Commands(['counter','owner','enabled','record','channel'],1)
  self.enc=Encoder('utf-8','strict',False)
 def frame(self):
  return {'event_id':1,'p':.73,'status':'live','provisional':True,'preview':{'kind':'blend','epoch':MAX,'seq':MAX,'base_rev':MAX,'ttl_ms':1000,'lease_id':'A','original_expires_at_ms':101000}}
 def test_maximum_metadata_reaches_lua_as_exact_decimal_bytes(self):
  command=self.c.offer(self.frame(),issued_at_ms=100000)
  self.assertEqual(command[1],(ROOT/'atomic-numeric-encoding/authority.lua').read_text())
  for i in (9,11,12):self.assertEqual(self.enc.encode(command[i]),b'9007199254740991')
  self.assertEqual(json.loads(command[-1])['preview']['seq'],MAX)
 def test_unsafe_or_noninteger_ordering_never_reaches_encoder(self):
  for field in ('epoch','seq','base_rev'):
   for value in (MAX+1, float(MAX), True, '1e14', -1):
    f=self.frame();f['preview'][field]=value
    with self.assertRaises(ValueError):self.c.offer(f,issued_at_ms=100000)
 def test_invalid_expiry_preserves_live_without_retention(self):
  for value in (MAX+1,float(MAX),True,'9007199254740991.4'):
   f=self.frame();f['preview']['original_expires_at_ms']=value
   self.assertEqual(self.c.offer(f,issued_at_ms=100000)[8],'uncached')
 def test_commit_and_coverage_floor_use_exact_bytes(self):
  cmd=self.c.committed({'event_id':1,'rev':{'1':MAX},'p':.73})
  self.assertEqual(self.enc.encode(cmd[9]),b'9007199254740991')
  cmd=self.c.snapshot(database_revision=MAX,database_status='live')
  self.assertEqual(self.enc.encode(cmd[9]),b'9007199254740991')
if __name__=='__main__':unittest.main(verbosity=2)
