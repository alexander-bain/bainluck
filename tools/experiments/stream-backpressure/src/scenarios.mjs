import {WireClient,sleep,until} from './wire-client.mjs';
export const CASES=[
  ['ordered-delivery','Ordered updates, duplicate and receipt ACK'],
  ['renew-before-deadline','Slow work before seq 10 triggers proactive lease renewal'],
  ['expired-renew-latest','Expired authority recovers latest only, without inventing skipped points'],
  ['normal-handover','Normal handover and rejected stale owner'],
  ['queue-before-take','Queued old publication purged before take'],
  ['held-old-before-fence','Held old frame is refused before writing, then fresh snapshot'],
  ['held-old-after-fence','Held old frame after fence closes original stream, then snapshot'],
  ['drop-reconnect','Actual TCP close and fresh-session reconnect (75 ms retry timer)'],
  ['drop-reconnect-immediate','Same TCP close with zero retry timer'],
  ['delayed-old-connection','Delayed old-connection callback (75 ms retry timer)'],
  ['delayed-old-connection-immediate','Same delayed old-connection callback with zero retry timer'],
  ['disconnect-handover','TCP disconnect during handover (75 ms retry timer)'],
  ['disconnect-handover-immediate','Same disconnect during handover with zero retry timer'],
  ['atomic-before','Publish immediately before subscribe snapshot'],
  ['atomic-after','Publish immediately after atomic subscribe snapshot'],
  ['atomic-handover','Handover between subscribe and stream pump'],
  ['skipped-intermediate','Intentional omitted intermediate update is not full-history recovery'],
  ['omitted-final','Omitted final update recovered by renewal snapshot'],
  ['expiry-no-renew','No renewal: fail unavailable at observed lease expiry'],
  ['main-thread-stall','Intentional main-thread stall across lease expiry']
];
const check=(condition,message)=>{if(!condition)throw Error(message);};
const stat=values=>{const a=[...values].sort((x,y)=>x-y);return {count:a.length,minMs:a[0],medianMs:a[Math.floor(a.length/2)],p95Ms:a[Math.min(a.length-1,Math.ceil(a.length*.95)-1)],maxMs:a.at(-1)};};
export async function post(base,path,data){const response=await fetch(`${base}${path}`,{method:'POST',headers:{'Content-Type':'application/json'},signal:AbortSignal.timeout(5000),body:JSON.stringify(data)});const value=await response.json();if(!response.ok||value.error)throw Error(value.error||response.status);return value;}
export async function runCase(name,{base='',onObserve=()=>{},allowStall=true}={}){
  const faultName=name.replace(/-immediate$/,'');
  const lab=await post(base,'/api/create',{}),wire=new WireClient({base,lab:lab.id,leaseMs:lab.leaseMs,onObserve});const c=wire.client;let conclusion='',metrics={},events;
  const value=async(p,epoch)=>until(()=>c.current?.p===p&&(epoch===undefined||c.current.epoch===epoch),`value ${p} epoch ${epoch}`);
  const seq=async(n)=>until(()=>c.current?.seq===n,`sequence ${n}`);
  const lastObservation=()=>wire.trace.findLast(r=>r.kind==='authority-envelope'&&(r.result.displayed||r.result.snapshot)&&r.current);
  try {
    if(name.startsWith('atomic-')){await wire.api('next-open',{mode:{'atomic-before':'publish-before-open','atomic-after':'publish-after-open','atomic-handover':'handover-after-open'}[name]});await wire.open();await value(name==='atomic-handover'?.2:.1);await wire.api('publish',{seq:2,p:.3});await seq(2);check(c.points.length===2,'Snapshot/live boundary missed or duplicated an observation');conclusion='Atomic registration + snapshot retained the latest value and subsequent live update; no full-log replay claim.';}
    else {
      await wire.open();
      if(name==='ordered-delivery') {
        const latencies=[];let proactiveRenewals=0,expiredRecoveries=0;
        for(let n=1;n<=30;n++){
          if(await wire.ensureAuthority())proactiveRenewals++;
          const start=performance.now();await wire.api('publish',{seq:n,p:n/100});
          await until(()=>c.current?.seq===n||c.now()>=c.deadline||c.status!=='active',`sequence ${n} or observable lease expiry`);
          if(c.current?.seq!==n){wire.tick();wire.log('expired-publication-recovery',{seq:n,deadlineMs:c.deadline});expiredRecoveries++;await wire.renew();}
          await seq(n);latencies.push(lastObservation().clientMonoMs-start);
        }
        metrics.renewalPolicy={proactiveRenewals,expiredRecoveries,leaseMs:lab.leaseMs,renewWhenRemainingBelowFraction:.75};
        await wire.api('duplicate-last');await sleep(20);check(c.points.length===30,'Duplicate envelope or renewal created numeric evidence');
        await wire.api('ack-latest');await until(()=>c.current?.state==='durable','simulated receipt acknowledgement');check(c.points.length===30,'ACK created numeric evidence');
        metrics.publishRequestToAccept=stat(latencies);metrics.publicationReadyToWriterEnqueue=stat(wire.trace.filter(r=>r.kind==='authority-envelope'&&r.message.kind==='publication'&&r.result.displayed&&r.transport?.readyToWriteMs!==null).map(r=>r.transport.readyToWriteMs));conclusion='30 ordered updates retained once each; duplicate and simulated persistence ACK added no numeric points. ACK is not disk/DB durability.';
      }else if(name==='renew-before-deadline') {
        for(let n=1;n<=9;n++){await wire.ensureAuthority();await wire.api('publish',{seq:n,p:n/100});await seq(n);}
        const oldDeadline=c.deadline;await sleep(Math.max(0,oldDeadline-performance.now()-lab.leaseMs/2));
        const triggerAt=performance.now();check(triggerAt<oldDeadline,'Scheduled proactive renewal resumed after lease expiry; scheduler stall is not hidden');
        const triggered=await wire.ensureAuthority();check(triggered,'Slow-work boundary did not trigger time-based renewal');check(c.deadline>oldDeadline,'Renewal did not obtain a new challenge-origin deadline');
        await wire.api('publish',{seq:10,p:.1});await seq(10);check(JSON.stringify(c.points.map(p=>p.seq))===JSON.stringify(Array.from({length:10},(_,i)=>i+1)),'Renewal duplicated or skipped observed sequence');
        metrics={oldDeadlineMs:oldDeadline,newDeadlineMs:c.deadline,renewalTriggeredMs:triggerAt,leaseMs:lab.leaseMs};conclusion='Slow pre-seq-10 work triggered renewal based on remaining lease time, not an accepted-message count. TTL remains unchanged.';
      }else if(name==='expired-renew-latest') {
        await wire.api('publish',{seq:1,p:.1});await seq(1);const deadline=c.deadline;await sleep(Math.max(0,deadline-performance.now()+20));wire.tick();wire.log('intentional-expiry-before-recovery',{deadlineMs:deadline});check(c.current===null,'Expired authority was not visibly unavailable');
        await wire.api('publish',{seq:2,p:.2});await wire.api('publish',{seq:3,p:.3});await until(()=>wire.trace.filter(r=>r.message?.kind==='publication'&&r.result?.error==='fenced-or-expired').length===2,'two publications rejected during expiry');
        const first=wire.renew(),second=wire.renew();check(first===second,'Concurrent renewal did not share a single request');await first;await seq(3);check(JSON.stringify(c.points.map(p=>p.seq))==='[1,3]','Missed seq 2 was fabricated as observed evidence');
        metrics={leaseMs:lab.leaseMs,expiredDeadlineMs:deadline,recoveredDeadlineMs:c.deadline};conclusion='Expiry remained observable; seqs 2 and 3 were rejected while expired, then one serialized fresh-nonce renewal recovered snapshot seq 3 only. Seq 2 was not invented.';
      }else if(name==='normal-handover') {
        await wire.api('publish',{seq:1,p:.9});await value(.9);const result=await wire.api('handover');await value(.2,2);check(result.oldRefusal?.error==='fenced-or-terminal','Old owner offer was not fenced');conclusion='Old owner refused; observed new epoch replaced the prior authority.';
      }else if(name==='queue-before-take') {
        await wire.api('pause-pump');await wire.api('publish',{seq:1,p:.9});await wire.api('handover');await wire.api('resume-pump');await value(.2,2);check(!c.points.some(p=>p.p===.9),'Queued old value escaped before take');conclusion='Old publication queued inside broker was purged at handover; only 0.200 observed.';
      }else if(name==='held-old-before-fence') {
        await wire.api('hold-writes');await wire.api('publish',{seq:1,p:.9});await wire.api('handover');await wire.api('release-held',{count:1});await until(()=>wire.closed,'stale held frame disconnect');check(!c.points.some(p=>p.p===.9),'Unsent old value escaped');await wire.api('release-held');await wire.api('allow-writes');await wire.open();await value(.2,2);check(c.points.length===1,'Recovery fabricated old history');conclusion='Candidate revalidates before response.write, closes instead of writing unsent stale frame, then fresh-session snapshot restores epoch 2 only. Already-written kernel/network bytes are not retracted.';
      }else if(name==='held-old-after-fence') {
        await wire.api('hold-writes');await wire.api('publish',{seq:1,p:.9});await wire.api('allow-writes');await wire.api('handover');await value(.2,2);await wire.api('release-held');await until(()=>wire.closed,'old held frame disconnect');check(!c.points.some(p=>p.p===.9),'Old frame entered observations after fence');await wire.open();await value(.2,2);check(c.points.length===1,'Resnapshot duplicated latest');conclusion='Candidate refuses unsent old frame even after new-epoch fence; explicit reconnect recovers latest without duplicate points.';
      }else if(['drop-reconnect','disconnect-handover','delayed-old-connection'].includes(faultName)) {
        await wire.api('publish',{seq:1,p:.9});await value(.9);const oldSession=c.session;const reconnectDelayMs=name.endsWith('-immediate')?0:75;
        if(faultName==='delayed-old-connection'){await wire.api('delay-next-write',{ms:300});await wire.api('publish',{seq:2,p:.8});}
        const dropRequestMs=performance.now();await wire.api(faultName==='disconnect-handover'?'disconnect-during-handover':'drop-tcp');await until(()=>wire.closed,'actual TCP stream close');const disconnected=wire.trace.findLast(r=>r.kind==='disconnected').clientMonoMs;
        check(c.current===null,'Disconnected transport retained current authority');
        if(faultName!=='disconnect-handover')await wire.api('handover');
        const retryWaitStart=performance.now();if(reconnectDelayMs>0)await sleep(reconnectDelayMs);const reconnectStart=performance.now();await wire.open();await value(.2,2);const restored=lastObservation().clientMonoMs;check(c.session!==oldSession,'Reconnect reused session');
        metrics={dropRequestToDisconnectMs:disconnected-dropRequestMs,authorityUnavailableMs:restored-disconnected,explicitRetrySleepMs:reconnectStart-retryWaitStart,reconnectRequestToAcceptMs:restored-reconnectStart,configuredRetryDelayMs:reconnectDelayMs,postDisconnectControlMs:retryWaitStart-disconnected};
        if(faultName==='delayed-old-connection'){await sleep(330);events=await post(base,'/api/events',{lab:lab.id});check(events.events.some(e=>e.kind==='write-discarded-closed-connection'&&e.reason==='delayed-timer'),'Old delayed callback was not discarded');check(c.current?.p===.2,'Old connection timer corrupted replacement');}
        conclusion=`Real loopback TCP stream destroyed; fresh session recovered current epoch with ${reconnectDelayMs} ms retry timer. Post-disconnect authority-control time is separate; samples are not a guaranteed latency bound.`;
      }else if(name==='skipped-intermediate') {
        await wire.api('publish',{seq:1,p:.1});await seq(1);await wire.api('skip-next');await wire.api('publish',{seq:2,p:.2});await wire.api('publish',{seq:3,p:.3});await seq(3);check(JSON.stringify(c.points.map(p=>p.seq))==='[1,3]','Expected explicit missing intermediate');await wire.renew();await sleep(25);check(c.points.length===2,'Latest-state renewal invented missing history');conclusion='Latest value recovers, but intentionally omitted seq 2 remains absent. This protocol does not guarantee full history under arbitrary drops.';
      }else if(name==='omitted-final') {
        await wire.api('publish',{seq:1,p:.1});await seq(1);await wire.api('skip-next');const finalOfferMs=performance.now();await wire.api('publish',{seq:2,p:.2});await sleep(70);check(c.current?.seq===1,'Final-update omission was not reproduced');const renewMs=performance.now();await wire.renew();await seq(2);const accepted=lastObservation().clientMonoMs;metrics={finalOfferRequestToRecoveryMs:accepted-finalOfferMs,renewRequestToRecoveryMs:accepted-renewMs,intentionalRenewalWaitMs:renewMs-finalOfferMs};conclusion='Silent final-update omission left a stale latest value until renewal snapshot. No zero-delay or arbitrary-drop guarantee is claimed.';
      }else if(['expiry-no-renew','main-thread-stall'].includes(name)) {
        await wire.api('publish',{seq:1,p:.9});await value(.9);await wire.api('hold-writes');await wire.api('handover');const deadline=c.deadline;
        if(name==='main-thread-stall'&&allowStall){await sleep(Math.max(0,deadline-performance.now()-60));const start=performance.now();while(performance.now()<deadline+180){}wire.log('intentional-main-thread-stall',{startMs:start,endMs:performance.now(),deadlineMs:deadline});}else await sleep(Math.max(0,deadline-performance.now()+1));
        wire.tick();check(c.current===null,'Observed expired authority was not cleared');const observed=performance.now();metrics={deadlineMs:deadline,logicalExpiryObservedLateMs:observed-deadline};conclusion=name==='main-thread-stall'?'Expected scheduler limit: JS could not observe expiry during the intentional stall. DOM callbacks are not physical pixel-clearing proof.':'Withheld fence/renewal made current authority unavailable when client execution observed lease expiry. This is not an Internet partition simulation.';
      }else throw Error('unknown-case');
    }
    events??=await post(base,'/api/events',{lab:lab.id});
    return {name,passed:true,conclusion,metrics,clientTrace:wire.trace,server:events,points:c.points};
  }catch(error){events??=await post(base,'/api/events',{lab:lab.id}).catch(()=>null);return {name,passed:false,error:error.message,metrics,clientTrace:wire.trace,server:events,points:c.points};}
  finally{await wire.close();await post(base,'/api/action',{lab:lab.id,action:'close'}).catch(()=>{});}
}
export async function runSuite(options={}){const results=[];for(const [name,label] of CASES){options.onCase?.({name,label,phase:'start'});const result=await runCase(name,options);results.push(result);options.onCase?.({...result,label,phase:'finish'});}return {kind:options.kind||'wire',wallClock:new Date().toISOString(),scope:'Real HTTP SSE over 127.0.0.1, shared frozen Client/protocol. Synthetic probabilities and application fault scheduling, no external network or production. Browser DOM writes/rAF are not physical display proof.',results};}
