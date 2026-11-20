"""Save actual current producer outputs for socket-free exact-Lua composition."""
import asyncio,json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from current_source import load
load()
from producer_driver import ProducerDriver
from retention_input import prepare,adapter
KEYS=['epoch','owner','enabled','event','channel']
def lua(value):
 if type(value) in (int,float):return repr(value)
 if type(value) is list:return '{'+','.join(lua(x) for x in value)+'}'
 s=str(value);assert ']=]' not in s;return '[=['+s+']=]'
async def main():
 cases=[]
 with ProducerDriver() as d:
  for t in [0,2,4,6,8]:
   step=await d.step(t,locked=t!=8)
   for item in step['publications']:
    f=item['frame'];command=prepare(f,KEYS) if item['kind']=='preview' else adapter.Commands(KEYS,1).committed(f)
    cases.append({'at_ms':int(d.clock.now().timestamp()*1000),'kind':item['kind'],'args':list(command[8:]),'frame':f})
 (ROOT/'composition/producer-commands.json').write_text(json.dumps(cases,indent=2)+'\n')
 (ROOT/'composition/producer-commands.lua').write_text('return '+lua([[x['at_ms'],x['args']] for x in cases])+'\n')
 print('Saved',len(cases),'ordered commands from current real producer with fixture boundaries')
asyncio.run(main())
