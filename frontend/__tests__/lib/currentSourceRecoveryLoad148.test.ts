/** Actual page callbacks and scheduler; controlled promises, no network/DOM claim. */
import fs from 'fs';
import path from 'path';
import vm from 'vm';
import ts from 'typescript';
import { createReconnectCatchup } from '@/lib/reconnectCatchup';
import { createFoldedRefetchScheduler } from '@/lib/foldedRefetchScheduler';
import { createReconcileLedger } from '@/lib/reconcileControl';
import { canSubscribeEventQuotes } from '@/lib/eventQuoteStream';

const PAGE=fs.readFileSync(path.join(__dirname,'../../app/events/[id]/page.tsx'),'utf8');
const tree=ts.createSourceFile('page.tsx',PAGE,ts.ScriptTarget.Latest,true,ts.ScriptKind.TSX);
function extract(name:string) {
 let source:string|undefined;
 function walk(n:ts.Node) {
  if(ts.isVariableDeclaration(n)&&n.name.getText(tree)===name&&n.initializer&&ts.isCallExpression(n.initializer)) {
   source=n.initializer.arguments[0].getText(tree);
  }
  ts.forEachChild(n,walk);
 }
 walk(tree);if(!source)throw new Error(name);
 return new vm.Script(ts.transpileModule(`(${source})`,{compilerOptions:{target:ts.ScriptTarget.ES2020}}).outputText);
}
const CONTROL=extract('applyReconcileControl'),FACTORY=extract('[foldedRefetch]');
const windowMs=Number(PAGE.match(/const FOLDED_FRAME_REFETCH_MS = (\d+)/)![1]);
function rig() {
 const reconcileLedger=createReconcileLedger(),reconcileIntentRef={current:false};
 const heldEventRef={current:{id:1,status:'live'}},quoteTriggerRef={current:null},recoveryIntentRef={current:0};
 const starts:number[]=[];const pending:Array<{resolve:()=>void,reject:(e:unknown)=>void}>=[];
 let active=0,peak=0;
 const pairedQuoteReadRef={current:()=>{starts.push(Date.now());active++;peak=Math.max(peak,active);
  return new Promise<void>((resolve,reject)=>pending.push({resolve:()=>{active--;resolve();},reject:e=>{active--;reject(e);}}));}};
 const foldedRefetch=FACTORY.runInNewContext({createFoldedRefetchScheduler,reconcileLedger,reconcileIntentRef,
  quoteTriggerRef,recoveryIntentRef,pairedQuoteReadRef,heldEventRef,canSubscribeEventQuotes,
  freshNextEventReadRef:{current:false},refreshEventRef:{current:()=>{throw new Error('unexpected unpaired read');}},
  FOLDED_FRAME_REFETCH_MS:windowMs,Date,reconcileRetryDelayMs:()=>1000})();
 const catchup=createReconnectCatchup(()=>{reconcileIntentRef.current=true;foldedRefetch.request();},()=>4999);
 const send=CONTROL.runInNewContext({eventId:1,reconcileLedger,heldEventRef,canSubscribeEventQuotes,Date,
  reconcileCatchupRef:{current:catchup},reconcileOrdinalRef:{current:0}});
 return {starts,pending,reconcileLedger,peak:()=>peak,
  send:(rev:number,id=`normal-price:1:${rev}`)=>send({eventId:1,custodyId:id,floor:{'1':rev}}),
  stop:()=>{catchup.cancel();foldedRefetch.cancel();}};
}
beforeEach(()=>{jest.useFakeTimers();jest.setSystemTime(0);});
afterEach(()=>jest.useRealTimers());

test('1000 normal controls use one pending pair and obey the existing one-second request interval',async()=>{
 const r=rig();r.send(1);await jest.advanceTimersByTimeAsync(249);expect(r.starts).toEqual([]);
 await jest.advanceTimersByTimeAsync(1);expect(r.starts).toEqual([250]);
 for(let n=2;n<=1001;n++)r.send(n);
 await jest.advanceTimersByTimeAsync(1500);expect(r.starts).toEqual([250]);expect(r.peak()).toBe(1);
 r.pending[0].resolve();await jest.advanceTimersByTimeAsync(0);
 expect(r.starts).toHaveLength(2);expect(r.starts[1]-r.starts[0]).toBeGreaterThanOrEqual(windowMs);
 expect(r.peak()).toBe(1);
 r.reconcileLedger.settle(()=>true);r.pending[1].resolve();await jest.advanceTimersByTimeAsync(0);
 r.send(1001);await jest.advanceTimersByTimeAsync(5000);expect(r.starts).toHaveLength(2);r.stop();
});

test('prompt notifications cannot bypass a server retry-after or leave a post-teardown request',async()=>{
 const r=rig();r.send(1);await jest.advanceTimersByTimeAsync(250);
 r.pending[0].reject({retryAfterMs:2000});await jest.advanceTimersByTimeAsync(0);
 for(let n=2;n<20;n++)r.send(n);
 await jest.advanceTimersByTimeAsync(1999);expect(r.starts).toEqual([250]);
 await jest.advanceTimersByTimeAsync(1);expect(r.starts).toEqual([250,2250]);expect(r.peak()).toBe(1);
 r.send(20);r.stop();r.pending[1].resolve();await jest.advanceTimersByTimeAsync(10000);
 expect(r.starts).toHaveLength(2);
});
