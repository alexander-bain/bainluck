import assert from 'node:assert/strict';
import {EventEmitter} from 'node:events';
import fs from 'node:fs';
import {createStreamServer} from '../baseline/stream-server.mjs';
import {frame} from '../src/broker.mjs';
class Response extends EventEmitter {
 constructor({blocked=false}={}){super();this.blocked=blocked;this.writes=[];this.bytes=0;this.headersSent=false;this.destroyed=false;this.writableEnded=false;this.writableLength=0;}
 writeHead(status,headers){this.status=status;this.headers=headers;this.headersSent=true;return this;} flushHeaders(){}
 write(text){this.writes.push(text);this.bytes+=Buffer.byteLength(text);this.writableLength+=Buffer.byteLength(text);return !this.blocked;}
 end(text){this.body=text;this.writableEnded=true;this.emit('finish');}
 destroy(){this.destroyed=true;this.emit('close');}
}
async function request(app,pathname,body,res=new Response()){
 const req={method:body===undefined?'GET':'POST',url:pathname,headers:{host:'127.0.0.1:1','content-type':'application/json'},async *[Symbol.asyncIterator](){yield JSON.stringify(body);}};
 app.server.emit('request',req,res);await new Promise(resolve=>setImmediate(resolve));return res;
}
const app=createStreamServer({out:'results/baseline',leaseMs:1500});const rows=[];
try{
 const created=JSON.parse((await request(app,'/api/create',{})).body),lab=app.labs.get(created.id),res=new Response({blocked:true});
 await request(app,`/stream?lab=${lab.id}&session=baseline-slow&challenge=initial`,undefined,res);
 for(let i=1;i<=256;i++){assert.ok(lab.broker.offer(lab.token,frame(i)).accepted);await request(app,'/api/action',{lab:lab.id,action:'resume-pump'});assert.ok(res.bytes<2*1024*1024,'harness safety cap');}
 let stoppedAfterFalse=true;try{assert.equal(res.writes.length,1,'must not write again until drain');}catch(error){stoppedAfterFalse=false;rows.push({kind:'preserved-expected-failure',invariant:'Stop writing after first false until drain',message:error.message});}
 const pendingBefore=res.writes.length;
 await new Promise(resolve=>setTimeout(resolve,50));
 let drainDeadline=true;try{assert.equal(res.destroyed,true,'no-drain connection must disconnect on configured finite deadline (baseline has none)');}catch(error){drainDeadline=false;rows.push({kind:'preserved-expected-failure',invariant:'Bound no-drain wait',message:error.message});}
 const report={scope:'No socket mock: exact unchanged baseline HTTP handler and pump, response.write always false, no drain emitted; checks intentionally expose absent protection',source:'baseline/stream-server.mjs',pass:false,expectedFailures:rows.length,framesWritten:res.writes.length,bufferedBytes:res.writableLength,pendingBefore,noDrainObservationMs:50,stoppedAfterFalse,drainDeadline,failures:rows};
 fs.mkdirSync('results',{recursive:true});fs.writeFileSync('results/baseline-failures.json',JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify(report));assert.equal(rows.length,2);
}finally{await app.stop('baseline-mock-failures-preserved');}
