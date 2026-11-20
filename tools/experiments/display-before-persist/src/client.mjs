const probability=x=>typeof x==='number'&&Number.isFinite(x)&&x>=0&&x<=1;
export function validPayload(f){return !!f&&Number.isSafeInteger(f.seq)&&f.seq>0&&f.event_id===1&&f.status==='live'&&f.completed_at==null&&probability(f.p)&&f.sources&&typeof f.sources==='object'&&!Array.isArray(f.sources)&&Object.keys(f.sources).length>0&&Object.keys(f.sources).length<=2&&Object.entries(f.sources).every(([k,v])=>['kalshi','polymarket'].includes(k)&&v&&typeof v==='object'&&probability(v.value)&&(v.updated_at===undefined||(typeof v.updated_at==='string'&&Number.isFinite(Date.parse(v.updated_at)))));}
export function createModel(){let epoch=null,run=null,seq=0,current=null,terminal=false;const points=[],statuses=new Map(),known=new Map();return {
 reset(next,nextRun){epoch=next;run=nextRun;seq=0;current=null;terminal=false;points.length=0;statuses.clear();known.clear();},
 stop(){terminal=true;current=null;points.length=0;},
 accept(message){if(terminal||message.epoch!==epoch||message.run!==run||message.event!==1)return {error:'stale-identity-or-terminal'};
  if(!Number.isSafeInteger(message.seq)||message.seq<1||typeof message.hash!=='string'||!/^[0-9a-f]{64}$/.test(message.hash))return {error:'bad-identity'};
  if(!['pending','durable','failed','not-queued','outcome-unknown'].includes(message.state))return {error:'bad-state'};
  const old=known.get(message.seq);
  if(message.kind==='persistence'){if(!old||old.hash!==message.hash)return {error:'unknown-or-conflicting-ack'};if(old.state==='durable'&&message.state!=='durable')return {error:'durable-regression'};old.state=message.state;statuses.set(message.seq,message.state);if(message.seq===seq){current={...current,state:message.state,failure:message.failure};return {statusOnly:true,current};}return {ignoredOldStatus:true};}
  if(message.kind!=='publication'||!validPayload(message.payload)||message.payload.seq!==message.seq)return {error:'bad-payload'};
  if(old&&old.hash!==message.hash)return {error:'same-sequence-conflict'};
  if(message.seq<=seq)return {error:'duplicate-or-older'};
  seq=message.seq;current={seq,p:message.payload.p,state:message.state,failure:message.failure,epoch};known.set(seq,{hash:message.hash,state:message.state});points.push(current);statuses.set(seq,message.state);return {current};
 },state:()=>({epoch,run,seq,current,points:points.slice(),statuses:Object.fromEntries(statuses),terminal})};}
