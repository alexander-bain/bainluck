"""Corrected artifact selection only. Import/preflight does not launch or connect."""
import hashlib
import importlib.util
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
LUA=ROOT/'atomic-numeric-encoding/authority.lua'
ADAPTER=ROOT/'atomic-numeric-encoding/adapter.py'
LUA_SHA256='5b762702f38792028eb13887b9684711e4026839b9a4c6ae808971b538e3a4ca'
ADAPTER_SHA256='28048285a63c374b29c99a93862e7d73ec08b5b81f2486fc5183b4b128767427'
def preflight():
 for p,expected in [(LUA,LUA_SHA256),(ADAPTER,ADAPTER_SHA256)]:
  actual=hashlib.sha256(p.read_bytes()).hexdigest()
  if actual!=expected:raise RuntimeError(f'Corrected input hash mismatch: {p.name}')
 spec=importlib.util.spec_from_file_location('selected_authority_adapter',ADAPTER)
 adapter=importlib.util.module_from_spec(spec);spec.loader.exec_module(adapter)
 script=LUA.read_text()
 if adapter.SCRIPT!=script:raise RuntimeError('Adapter selects a different Lua script')
 return adapter,script
