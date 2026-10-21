"""Load only the saved current producer modules over pinned fixture dependencies."""
import importlib.util
import os
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parent
WORK=ROOT.parent
SOURCE=Path(os.environ.get('PRODUCER_DEPENDENCY_SOURCE',str(WORK/'source')))
sys.dont_write_bytecode=True
sys.path.insert(0,str(SOURCE/'backend'))
os.environ.setdefault('DATABASE_URL','postgresql+asyncpg://fixture:fixture@127.0.0.1:1/fixture')

_loaded = None

def load(candidate=True):
 global _loaded
 if _loaded is not None:
  if candidate != _loaded[0]:
   raise RuntimeError("Use a fresh process to compare another source alias")
  return _loaded[1]
 import app.utils, app.tasks
 for name,folder,rel in [('app.utils.blend_preview','candidate' if candidate else 'reference','backend/app/utils/blend_preview.py'),
                         ('app.tasks.live_blend_refresh','reference','backend/app/tasks/live_blend_refresh.py')]:
  path=ROOT/folder/rel
  spec=importlib.util.spec_from_file_location(name,path)
  module=importlib.util.module_from_spec(spec);sys.modules[name]=module;spec.loader.exec_module(module)
  setattr(sys.modules[name.rsplit('.',1)[0]],name.rsplit('.',1)[1],module)
 modules = (sys.modules['app.utils.blend_preview'],sys.modules['app.tasks.live_blend_refresh'])
 _loaded = (candidate, modules)
 return modules
