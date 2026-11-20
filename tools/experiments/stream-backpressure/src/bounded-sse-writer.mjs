// Per-response application/Node queue bound. Kernel, proxy, and peer buffers are not measured.
export function validateWriterOptions({maxQueuedBytes=128*1024,maxQueuedFrames=64,maxFrameBytes=16*1024,maxBufferedBytes=256*1024,stallMs=250}={}){
 for(const [k,v] of Object.entries({maxQueuedBytes,maxQueuedFrames,maxFrameBytes,maxBufferedBytes,stallMs}))if(!Number.isSafeInteger(v)||v<1)throw Error(`invalid-${k}`);
 if(maxBufferedBytes>2*1024*1024||maxQueuedBytes>maxBufferedBytes||maxFrameBytes+32>maxBufferedBytes)throw Error('buffer-safety-cap');
 return {maxQueuedBytes,maxQueuedFrames,maxFrameBytes,maxBufferedBytes,stallMs};
}
export class BoundedSseWriter {
 constructor(res,{maxQueuedBytes=128*1024,maxQueuedFrames=64,maxFrameBytes=16*1024,maxBufferedBytes=256*1024,stallMs=250,isCurrent=()=>true,onEvent=()=>{},onClosed=()=>{}}={}){
  validateWriterOptions({maxQueuedBytes,maxQueuedFrames,maxFrameBytes,maxBufferedBytes,stallMs});
  Object.assign(this,{res,maxQueuedBytes,maxQueuedFrames,maxFrameBytes,maxBufferedBytes,stallMs,isCurrent,onEvent,onClosed});
  this.queue=[];this.queuedBytes=0;this.blocked=false;this.closed=false;this.timer=null;this.blockedAt=null;
  this.stats={writes:0,writeFalse:0,drains:0,peakQueuedBytes:0,peakQueuedFrames:0,peakNodeBytes:0,peakBufferedBytes:0,discardedFrames:0,discardedBytes:0,maxWriteCallMs:0,maxQueueWaitMs:0,maxDrainWaitMs:0,callbacksAfterClose:0,closeReason:null};
  this.drain=()=>{if(this.closed){this.stats.callbacksAfterClose++;return;}this.stats.drains++;this.stats.maxDrainWaitMs=Math.max(this.stats.maxDrainWaitMs,performance.now()-this.blockedAt);this.event('drain',{waitMs:performance.now()-this.blockedAt});this.blocked=false;this.blockedAt=null;clearTimeout(this.timer);this.timer=null;this.flush();};
  this.responseClose=()=>this.close('response-close',false);
  res.on('drain',this.drain);res.once('close',this.responseClose);res.once('error',this.responseClose);
 }
 sample(){const nodeBytes=this.res.writableLength||0;this.stats.peakQueuedBytes=Math.max(this.stats.peakQueuedBytes,this.queuedBytes);this.stats.peakQueuedFrames=Math.max(this.stats.peakQueuedFrames,this.queue.length);this.stats.peakNodeBytes=Math.max(this.stats.peakNodeBytes,nodeBytes);this.stats.peakBufferedBytes=Math.max(this.stats.peakBufferedBytes,this.queuedBytes+nodeBytes);return {queuedBytes:this.queuedBytes,queuedFrames:this.queue.length,nodeBytes,bufferedBytes:this.queuedBytes+nodeBytes};}
 event(kind,data={}){this.onEvent(kind,{...this.sample(),...data});}
 enqueue(bytes,{message=null,reason='normal',transport=null}={}){
  if(this.closed||this.res.destroyed||this.res.writableEnded)return false;
  const size=Buffer.byteLength(bytes);
  if(size>this.maxFrameBytes){this.close('frame-byte-limit');return false;}
  // Reserve 32 bytes for a Node HTTP chunk header/trailer on each pending frame.
  if(this.queue.length+1>this.maxQueuedFrames||this.queuedBytes+size>this.maxQueuedBytes||this.queuedBytes+(this.res.writableLength||0)+size+32*(this.queue.length+1)>this.maxBufferedBytes){this.close('queue-limit');return false;}
  // A fence must not sit behind a stale application backlog. End this session and resnapshot.
  if(message&&!this.isCurrent(message)){this.close('stale-before-write');return false;}
  if((this.blocked||this.queue.length)&&this.queue.some(entry=>entry.message&&!this.isCurrent(entry.message))){this.close('authority-changed-with-backlog');return false;}
  this.queue.push({bytes,size,message,reason,transport,queuedAt:performance.now()});this.queuedBytes+=size;this.event('enqueue');this.flush();return !this.closed;
 }
 flush(){
  if(this.flushing)return;this.flushing=true;
  try{while(!this.closed&&!this.blocked&&this.queue.length){
   const entry=this.queue[0];
   if(entry.message&&!this.isCurrent(entry.message)){this.close('stale-before-write');return;}
   this.queue.shift();this.queuedBytes-=entry.size;const begin=performance.now();let ok;
   try{ok=this.res.write(entry.bytes);}catch(error){this.event('write-error',{error:error.message});this.close('write-error');return;}
   if(this.closed)return;
   this.stats.writes++;const duration=performance.now()-begin,waitMs=begin-entry.queuedAt;this.stats.maxWriteCallMs=Math.max(this.stats.maxWriteCallMs,duration);this.stats.maxQueueWaitMs=Math.max(this.stats.maxQueueWaitMs,waitMs);
   this.event('write',{message:entry.message,reason:entry.reason,transport:entry.transport?{...entry.transport,actualResponseWriteMs:begin,enqueueToResponseWriteMs:waitMs,readyToResponseWriteMs:entry.transport.producerReadyMs===null?null:begin-entry.transport.producerReadyMs}:null,bytes:entry.size,backpressure:!ok,writeDurationMs:duration,queueWaitMs:waitMs});
   if(this.closed)return;
   if(!ok){this.stats.writeFalse++;this.blocked=true;this.blockedAt=performance.now();this.timer=setTimeout(()=>{this.timer=null;if(!this.closed)this.close('drain-timeout');},this.stallMs);this.timer.unref?.();this.event('blocked');}
  }}finally{this.flushing=false;}
 }
 close(reason,destroy=true){
  if(this.closed)return;
  this.closed=true;clearTimeout(this.timer);this.timer=null;this.res.off('drain',this.drain);this.res.off('close',this.responseClose);this.res.off('error',this.responseClose);
  this.stats.closeReason=reason;this.stats.discardedFrames=this.queue.length;this.stats.discardedBytes=this.queuedBytes;this.event('closed',{reason,blockedForMs:this.blockedAt===null?null:performance.now()-this.blockedAt});
  this.queue=[];this.queuedBytes=0;this.blocked=false;this.blockedAt=null;this.onClosed(reason);if(destroy&&!this.res.destroyed)this.res.destroy();
 }
}
