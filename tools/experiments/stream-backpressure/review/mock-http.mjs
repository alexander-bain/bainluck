import {EventEmitter} from 'node:events';
export class FakeResponse extends EventEmitter {
 constructor({blocked=false,asyncClose=false,throwOnWrite=false}={}) {super();this.blocked=blocked;this.asyncClose=asyncClose;this.throwOnWrite=throwOnWrite;this.writes=[];this.writeCalls=0;this.totalBytes=0;this.headersSent=false;this.destroyed=false;this.writableEnded=false;this.writableLength=0;this.writableHighWaterMark=16384;this.destroyCalls=0;this.endCalls=0;this.status=0;}
 writeHead(status,headers){this.status=status;this.headers=headers;this.headersSent=true;return this;}
 flushHeaders(){}
 write(text){this.writeCalls++;if(this.destroyed||this.writableEnded)throw Error('write-after-closed');if(this.throwOnWrite)throw Error('synthetic-write-error');this.writes.push(String(text));const bytes=Buffer.byteLength(text);this.totalBytes+=bytes;if(this.blocked)this.writableLength+=bytes;return !this.blocked;}
 end(text){this.endCalls++;this.body=text;this.writableEnded=true;this.emit('finish');}
 destroy(error){this.destroyCalls++;if(this.destroyed)return this;this.destroyed=true;this.destroyError=error;const emit=()=>this.emit('close');if(this.asyncClose)setImmediate(emit);else emit();return this;}
 drain({blocked=false}={}){this.writableLength=0;this.blocked=blocked;this.emit('drain');}
 messages(){return this.writes.flatMap(chunk=>chunk.split('\n\n')).filter(x=>x.includes('data: ')).map(x=>JSON.parse(x.split('\n').find(l=>l.startsWith('data: ')).slice(6)).message);}
}
export async function request(app,pathname,body,res=new FakeResponse()) {
 const req={method:body===undefined?'GET':'POST',url:pathname,headers:{host:'127.0.0.1:1','content-type':'application/json'},async *[Symbol.asyncIterator](){if(body!==undefined)yield JSON.stringify(body);}};
 app.server.emit('request',req,res);await new Promise(resolve=>setImmediate(resolve));return res;
}
export async function createLab(app) {const response=await request(app,'/api/create',{});if(response.status!==200)throw Error(`create-lab failed: ${response.body}`);return app.labs.get(JSON.parse(response.body).id);}
export async function open(app,lab,session,res,challenge='test-challenge'){await request(app,`/stream?lab=${lab.id}&session=${session}&challenge=${challenge}`,undefined,res);return res;}
export async function action(app,lab,data){const response=await request(app,'/api/action',{lab:lab.id,...data});if(response.status!==200)throw Error(`action failed: ${response.body}`);return JSON.parse(response.body);}
export const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
