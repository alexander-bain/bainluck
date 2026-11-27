"""TEST ONLY explicit composition with the already-reviewed singleton adapter.

This prepares commands; it does not send them. It is NOT an atomic batched
publication implementation and must never replace the existing batch with a loop.
"""
from pathlib import Path
import importlib.util
ROOT=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('numeric_retention_adapter',ROOT.parent/'atomic-numeric-encoding/adapter.py')
adapter=importlib.util.module_from_spec(spec);spec.loader.exec_module(adapter)

def prepare(frame, keys):
 return adapter.Commands(keys,frame['event_id']).offer(
  frame,issued_at_ms=frame.get('preview',{}).get('lease_issued_at_ms'))
