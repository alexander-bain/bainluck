import test from 'node:test';
import { randomBytes } from 'node:crypto';
import assert from 'node:assert/strict';
import { existsSync } from 'node:fs';
const secret=randomBytes(32).toString('hex');
const authorization='Basic '+Buffer.from('logplex:'+secret).toString('base64');
async function handler() {
 assert.ok(existsSync(new URL('../../lib/releaseLogDrain.mjs',import.meta.url)),'authenticated durable log ingress is missing');
 return (await import('../../lib/releaseLogDrain.mjs')).handleLogDrain;
}
function frame(message,proc='worker-ws.1') {
 const raw=Buffer.from('<190>1 2026-11-02T00:00:00.100Z host app '+proc+' - - '+message);
 return Buffer.concat([Buffer.from(raw.length+' '),raw]);
}
test('unauthorized drain cannot forward any logs',async()=>{
 const handle=await handler();let sent=false;
 const result=await handle({body:frame('gc thresholds'),authorization:'Basic invalid',secret,forward:async()=>{sent=true;}});
 assert.equal(result.status,401);assert.equal(sent,false);
});
test('router-only delivery stops the self-drain feedback loop',async()=>{
 const handle=await handler();let sent=false;
 const result=await handle({body:frame('at=info method=POST path=/api/release-logs/drain status=202','router'),authorization,secret,forward:async()=>{sent=true;}});
 assert.equal(result.status,202);assert.equal(sent,false);
});
test('worker frames reach the collector unchanged',async()=>{
 const handle=await handler();const body=frame('gc thresholds café');const saved=[];
 const result=await handle({body,authorization,secret,forward:async(raw)=>{saved.push(raw);}});
 assert.equal(result.status,202);assert.deepEqual(saved,[body]);
});
test('collector failure remains retryable without disclosing headers or body',async()=>{
 const handle=await handler();
 const result=await handle({body:frame('gc thresholds'),authorization,secret,forward:async()=>{throw new Error('private-token');}});
 assert.equal(result.status,503);assert.equal(JSON.stringify(result).includes('private-token'),false);
});
