import test from 'node:test';
import assert from 'node:assert/strict';
import {EventEmitter} from 'node:events';
import {BoundedSseWriter} from '../src/bounded-sse-writer.mjs';
import {createStreamServer} from '../src/stream-server.mjs';
class Response extends EventEmitter{
 constructor(){super();this.writes=[];this.writableLength=0;this.block=true;this.destroyed=false;this.writableEnded=false;}
 write(data){this.writes.push(data);this.writableLength+=Buffer.byteLength(data)+8;return !this.block;}
 drainNow(){this.writableLength=0;this.block=false;this.emit('drain');}
 destroy(){this.destroyed=true;this.emit('close');}
}
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
await test('false stops writes and one drain resumes exact ordered frames without duplicates',()=>{
 const res=new Response(),w=new BoundedSseWriter(res);try{for(let i=0;i<30;i++)w.enqueue(`${i}`);assert.equal(res.writes.length,1);assert.equal(w.queue.length,29);assert.equal(w.stats.writeFalse,1);res.drainNow();assert.deepEqual(res.writes,Array.from({length:30},(_,i)=>`${i}`));assert.equal(w.queue.length,0);assert.equal(w.queuedBytes,0);assert.equal(w.stats.drains,1);}finally{w.close('test');}
});
await test('queued-frame limit disconnects and never claims complete history',()=>{
 const res=new Response(),w=new BoundedSseWriter(res,{maxQueuedFrames:3});for(let i=0;i<5;i++)w.enqueue(`${i}`);assert.equal(w.stats.closeReason,'queue-limit');assert.equal(w.stats.discardedFrames,3);assert.equal(w.queue.length,0);assert.equal(res.writes.length,1);assert.equal(res.listenerCount('drain'),0);
});
await test('queued-byte and aggregate Node+queue byte limits are enforced before admission',()=>{
 for(const options of [{maxQueuedBytes:64},{maxBufferedBytes:256,maxFrameBytes:100,maxQueuedBytes:256}]){const res=new Response(),w=new BoundedSseWriter(res,options);for(let i=0;i<100&&!w.closed;i++)w.enqueue('x'.repeat(32));assert.equal(w.stats.closeReason,'queue-limit');assert.ok(w.stats.peakBufferedBytes<=w.maxBufferedBytes);assert.ok(w.stats.peakQueuedBytes<=w.maxQueuedBytes);}
});
await test('oversized frame never reaches response.write',()=>{const res=new Response(),w=new BoundedSseWriter(res,{maxFrameBytes:32});assert.equal(w.enqueue('x'.repeat(33)),false);assert.equal(w.stats.closeReason,'frame-byte-limit');assert.equal(res.writes.length,0);});
await test('no drain closes on finite timer; delayed drain cannot resurrect connection',async()=>{
 const res=new Response(),w=new BoundedSseWriter(res,{stallMs:30});const start=performance.now();w.enqueue('a');w.enqueue('b');await sleep(65);assert.equal(w.closed,true);assert.equal(w.stats.closeReason,'drain-timeout');assert.ok(performance.now()-start>=30);assert.equal(w.timer,null);res.emit('drain');assert.deepEqual(res.writes,['a']);assert.equal(w.stats.callbacksAfterClose,0);assert.equal(w.queuedBytes,0);
});
await test('abandon cancels timer, drops queue, and removes response callbacks',async()=>{
 const res=new Response(),w=new BoundedSseWriter(res,{stallMs:30});w.enqueue('a');w.enqueue('b');res.destroy();await sleep(50);assert.equal(w.stats.closeReason,'response-close');assert.equal(w.timer,null);assert.equal(w.queuedBytes,0);assert.equal(w.queue.length,0);assert.equal(w.enqueue('after-close'),false);assert.equal(res.listenerCount('drain'),0);assert.equal(w.stats.callbacksAfterClose,0);
});
await test('old owner queued before drain is disconnected, never flushed after handover',()=>{
 let epoch=1;const res=new Response(),w=new BoundedSseWriter(res,{isCurrent:m=>m.epoch===epoch});w.enqueue('already-sent',{message:{epoch:1}});w.enqueue('queued-old',{message:{epoch:1}});epoch=2;res.drainNow();assert.deepEqual(res.writes,['already-sent']);assert.equal(w.stats.closeReason,'stale-before-write');assert.equal(w.stats.discardedFrames,1);
});
await test('new fence does not wait behind old application backlog',()=>{
 let epoch=1;const res=new Response(),w=new BoundedSseWriter(res,{isCurrent:m=>m.epoch===epoch});w.enqueue('already-sent',{message:{epoch:1}});w.enqueue('old',{message:{epoch:1}});epoch=2;w.enqueue('fence',{message:{epoch:2}});assert.equal(w.stats.closeReason,'authority-changed-with-backlog');assert.deepEqual(res.writes,['already-sent']);
});
await test('write exception closes once and repeated close is idempotent',()=>{const res=new Response();res.write=()=>{throw Error('fixture');};let closes=0;const w=new BoundedSseWriter(res,{onClosed:()=>closes++});w.enqueue('a');w.close('again');assert.equal(closes,1);assert.equal(w.stats.closeReason,'write-error');});
await test('invalid or over-safety-cap configuration is refused before listeners',()=>{
 for(const options of [{stallMs:0},{maxQueuedFrames:0},{maxBufferedBytes:2*1024*1024+1},{maxFrameBytes:2*1024*1024}])assert.throws(()=>new BoundedSseWriter(new Response(),options));
});
await test('synchronous response close during write cannot create a post-close timer',()=>{const res=new Response();res.write=()=>{res.destroy();return false;};const w=new BoundedSseWriter(res);w.enqueue('a');assert.equal(w.closed,true);assert.equal(w.timer,null);assert.equal(w.blocked,false);});
await test('write-observer reentrant close cannot create a post-close timer',()=>{const res=new Response();let w;w=new BoundedSseWriter(res,{onEvent:kind=>{if(kind==='write')w.close('observer');}});w.enqueue('a');assert.equal(w.closed,true);assert.equal(w.timer,null);assert.equal(w.blocked,false);});
await test('synchronous enqueue inside write waits for outer false/drain result',()=>{const res=new Response();let w,calls=0;res.write=data=>{res.writes.push(data);res.writableLength+=data.length;if(++calls===1)w.enqueue('reentrant');return false;};w=new BoundedSseWriter(res);w.enqueue('first');assert.deepEqual(res.writes,['first']);assert.equal(w.queue.length,1);assert.equal(w.stats.writeFalse,1);w.close('test');assert.equal(w.timer,null);});
await test('terminal invalidates old same-token unsent publication backlog',()=>{let active=true;const res=new Response(),w=new BoundedSseWriter(res,{isCurrent:m=>m.kind==='snapshot'?m.status===(active?'active':'terminal'):active});w.enqueue('sent',{message:{kind:'publication'}});w.enqueue('pending',{message:{kind:'publication'}});active=false;w.enqueue('terminal',{message:{kind:'snapshot',status:'terminal'}});assert.equal(w.stats.closeReason,'authority-changed-with-backlog');assert.deepEqual(res.writes,['sent']);});

await test('invalid server writer settings fail before any lab or listener can open',()=>{assert.throws(()=>createStreamServer({writerOptions:{maxQueuedFrames:0}}),/invalid-maxQueuedFrames/);});
