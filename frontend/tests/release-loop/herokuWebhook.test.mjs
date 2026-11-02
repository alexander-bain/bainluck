import test from 'node:test';
import assert from 'node:assert/strict';
import { createHmac } from 'node:crypto';
import { existsSync } from 'node:fs';
async function handler() {
 assert.ok(existsSync(new URL('../../lib/releaseWebhook.mjs',import.meta.url)), 'authenticated relay is missing');
 return (await import('../../lib/releaseWebhook.mjs')).handleReleaseWebhook;
}

const secret='test-signing-key';
const payload={id:'evt-1',resource:'release',action:'update',data:{id:'release-1',status:'succeeded',app:{name:'bainluck'}}};
const body=JSON.stringify(payload);
const signature=createHmac('sha256',secret).update(body).digest('base64');

test('unsigned or mismatched request cannot dispatch', async()=>{
 const handleReleaseWebhook=await handler();
 for(const invalid of ['', 'garbage', createHmac('sha256','wrong').update(body).digest('base64')]) {
  let dispatched=false;
  const result=await handleReleaseWebhook({body,signature:invalid,secret,dispatch:async()=>{
 const handleReleaseWebhook=await handler();dispatched=true;}});
  assert.equal(result.status,401);assert.equal(dispatched,false);
 }
});

test('signed successful release dispatches only provider identity',async()=>{
 const handleReleaseWebhook=await handler();
 const received=[];
 const result=await handleReleaseWebhook({body,signature,secret,dispatch:async(event)=>{received.push(event);}});
 assert.equal(result.status,202);
 assert.deepEqual(received,[{event_type:'heroku-release',client_payload:{provider:'heroku',candidate_id:'release-1',event_id:'evt-1'}}]);
});

test('wrong app or pending release is ignored',async()=>{
 const handleReleaseWebhook=await handler();
 for(const change of [{app:{name:'bainluck-heavy'}},{status:'pending'}]){
  const raw=JSON.stringify({...payload,data:{...payload.data,...change}});
  let called=false;
  const result=await handleReleaseWebhook({body:raw,signature:createHmac('sha256',secret).update(raw).digest('base64'),secret,dispatch:async()=>{
 const handleReleaseWebhook=await handler();called=true;}});
  assert.equal(result.status,202);assert.equal(called,false);
 }
});

test('malformed authenticated payload fails clearly',async()=>{
 const handleReleaseWebhook=await handler();
 const raw='{';
 const result=await handleReleaseWebhook({body:raw,signature:createHmac('sha256',secret).update(raw).digest('base64'),secret,dispatch:async()=>{assert.fail();}});
 assert.equal(result.status,400);
});

test('dispatch failure never reads as delivered and reveals no secret',async()=>{
 const handleReleaseWebhook=await handler();
 const result=await handleReleaseWebhook({body,signature,secret,dispatch:async()=>{throw new Error('TOKEN=do-not-expose');}});
 assert.equal(result.status,503);
 assert.equal(JSON.stringify(result).includes('TOKEN'),false);
});
