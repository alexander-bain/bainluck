import {Client} from './client.mjs';
export const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
export async function until(predicate,label,{timeout=5000}={}){const start=performance.now();while(!predicate()){if(performance.now()-start>timeout)throw Error(`Timed out: ${label}`);await sleep(5);}return predicate();}
export class WireClient {
  constructor({base='',lab,leaseMs=1500,onObserve=()=>{}}={}){this.base=base;this.lab=lab;this.client=new Client({leaseMs});this.trace=[];this.onObserve=onObserve;this.generation=0;this.closed=true;}
  log(kind,data={}){const row={n:this.trace.length+1,kind,clientMonoMs:performance.now(),...data};this.trace.push(row);this.onObserve(row,this.client);return row;}
  async api(action,extra={}){this.log('control-request',{action,...extra});const response=await fetch(`${this.base}/api/action`,{method:'POST',headers:{'Content-Type':'application/json'},signal:AbortSignal.timeout(5000),body:JSON.stringify({lab:this.lab,action,...extra})});const result=await response.json();if(!response.ok||result.error)throw Error(result.error||response.status);this.log('control-response',{action,result});return result;}
  async open(){this.abort?.abort();const generation=++this.generation;this.closed=false;const hello=this.client.start();this.abort=new AbortController();this.log('connect-request',{hello,generation});
    const stream=new URL(`${this.base||location.origin}/stream`);for(const [k,v] of Object.entries({lab:this.lab,...hello}))stream.searchParams.set(k,v);
    this.task=(async()=>{let reader;try{
      const response=await fetch(stream,{signal:this.abort.signal,cache:'no-store'});if(!response.ok)throw Error(`stream-http-${response.status}`);
      if(generation!==this.generation)return;this.log('http-stream-open',{generation});reader=response.body.getReader();const decoder=new TextDecoder();let buffer='';
      while(true){const {done,value}=await reader.read();if(done)break;if(generation!==this.generation)break;buffer+=decoder.decode(value,{stream:true});if(buffer.length>1_000_000)throw Error('sse-buffer-limit');let boundary;
        while((boundary=buffer.indexOf('\n\n'))>=0){const event=buffer.slice(0,boundary);buffer=buffer.slice(boundary+2);const data=event.split('\n').filter(line=>line.startsWith('data:')).map(line=>line.slice(5).trimStart()).join('\n');if(!data)continue;const receivedMs=performance.now();const envelope=JSON.parse(data),message=envelope.message;const result=this.client.accept(message);const acceptedMs=performance.now();this.log('authority-envelope',{message,transport:envelope.transport,receivedMs,acceptedMs,validationMs:acceptedMs-receivedMs,result,current:this.client.current?{epoch:this.client.current.epoch,seq:this.client.current.seq,p:this.client.current.p,state:this.client.current.state}:null,deadlineMs:this.client.deadline,pointCount:this.client.points.length});}
      }
      this.log('http-stream-eof',{generation});
    }catch(error){this.log('http-stream-error',{generation,error:error.name==='AbortError'?'local-abort':error.message});}
    finally{try{await reader?.cancel();}catch{}if(generation===this.generation){this.closed=true;this.client.disconnect();this.log('disconnected',{generation});}}
    })();
    try{
      await until(()=>this.trace.some(r=>r.kind==='authority-envelope'&&r.message.session===hello.session&&r.result.snapshot)||this.closed,'initial authority snapshot');
      if(this.closed)throw Error('stream-closed-before-handshake');
      if(generation!==this.generation||this.client.session!==hello.session)throw Error('handshake-superseded');
      if(this.client.now()>=this.client.deadline)throw Error('initial-handshake-arrived-expired');
      // A fresh terminal/fatal snapshot is a valid handshake, not active authority.
      return hello;
    }catch(error){if(generation===this.generation)await this.close();throw error;}
  }
  renew(){
    if(this.renewal)return this.renewal;
    const session=this.client.session,challenge=this.client.challenge(),from=this.trace.length;
    if(!challenge)return Promise.reject(Error('challenge-capacity'));
    this.renewal=(async()=>{
      const result=await this.api('renew',{session,challenge});
      await until(()=>this.closed||this.client.session!==session||this.trace.slice(from).some(r=>r.kind==='authority-envelope'&&r.message.lease?.nonce===challenge),'renewal snapshot');
      if(this.closed||this.client.session!==session)throw Error('renewal-session-changed');
      const response=this.trace.slice(from).find(r=>r.kind==='authority-envelope'&&r.message.lease?.nonce===challenge);
      if(!response?.result.snapshot)throw Error('renewal-snapshot-rejected');
      if(this.client.now()>=this.client.deadline)throw Error('renewal-arrived-expired');
      this.log('renewal-complete',{challenge,deadlineMs:this.client.deadline});return {...result,challenge};
    })().finally(()=>{this.renewal=null;});
    return this.renewal;
  }
  async ensureAuthority(){
    if(this.client.status!=='active'||this.client.now()>=this.client.deadline-this.client.maxLeaseMs*.75){
      this.log('renewal-policy-trigger',{reason:this.client.now()>=this.client.deadline?'expired-recovery':'remaining-lease-under-75-percent',deadlineMs:this.client.deadline});
      await this.renew();return true;
    }return false;
  }
  tick(){const before=this.client.current;const value=this.client.tick();if(before&&!value)this.log('lease-expiry-observed',{deadlineMs:this.client.deadline});return value;}
  async close(){this.generation++;this.abort?.abort();this.client.disconnect();this.closed=true;await this.task;this.log('local-close');}
}
