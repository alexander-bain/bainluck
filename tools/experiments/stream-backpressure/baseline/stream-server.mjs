import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {Broker, frame} from './broker.mjs';
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
export function createStreamServer({out = path.join(root, 'results'), leaseMs = 1500, maxRuntimeMs = 30 * 60 * 1000} = {}) {
  fs.mkdirSync(out, {recursive:true});
  const labs = new Map(), sockets = new Set();
  const startedAt = new Date().toISOString();
  let nextConnection = 0, stopping = false, timer, stopPromise;
  const receipt = (lab, kind, data = {}) => {
    const event = {n:lab.events.length+1, kind, serverMonoMs:performance.now(), ...data};
    if (lab.events.length < 20000) lab.events.push(event);
    return event;
  };
  function newLab() {
    if (labs.size >= 24) throw Error('lab-capacity: close a lab first');
    const lab = {id:crypto.randomUUID(), broker:new Broker({leaseMs, maxMailbox:128, maxSessions:8}), events:[], connections:new Map(), held:[], pausePump:false, holdWrites:false, skipNext:false, lastPublication:null, nextOpen:null, delayNextMs:0, timers:new Set(), readyTimes:new Map()};
    lab.token = lab.broker.claim('owner-a');
    labs.set(lab.id, lab); receipt(lab, 'lab-created', {token:lab.token, leaseMs}); return lab;
  }
  function write(lab, conn, m, reason = 'normal') {
    if (conn.closed || conn.res.destroyed || conn.res.writableEnded) {receipt(lab, 'write-discarded-closed-connection', {connection:conn.id, session:conn.session, message:m, reason});return false;}
    const writeReadyMs=performance.now(), producerReadyMs=lab.readyTimes.get(m.revision)??null;
    const transport={writeReadyMs,producerReadyMs,readyToWriteMs:producerReadyMs===null?null:writeReadyMs-producerReadyMs,clock:"server monotonic; write is enqueue, not network delivery"};
    const bytes = `id: ${m.revision}\nevent: authority\ndata: ${JSON.stringify({message:m,transport})}\n\n`;
    const ok = conn.res.write(bytes);
    receipt(lab, 'wire-write', {connection:conn.id, session:conn.session, message:m, reason, bytes:Buffer.byteLength(bytes), backpressure:!ok, transport});
    return true;
  }
  function pump(lab) {
    if (lab.pausePump) return;
    for (const conn of lab.connections.values()) {
      if (conn.closed) continue;
      let m, count = 0;
      while ((m = lab.broker.take(conn.session))) {
        if (++count > 512) throw Error('pump-limit');
        receipt(lab, 'broker-take', {connection:conn.id, message:m});
        if (m.kind === 'publication') lab.lastPublication = structuredClone(m);
        if (lab.skipNext && m.kind === 'publication') {lab.skipNext=false;receipt(lab, 'intentionally-omitted', {connection:conn.id, message:m});continue;}
        if (lab.delayNextMs) {
          const delayMs=lab.delayNextMs;lab.delayNextMs=0;receipt(lab,'delayed-write-scheduled',{connection:conn.id,message:m,delayMs});
          const timer=setTimeout(()=>{lab.timers.delete(timer);write(lab,conn,m,'delayed-timer');},delayMs);lab.timers.add(timer);
        } else if (lab.holdWrites) {
          if (lab.held.length >= 1024) {conn.res.destroy();throw Error('held-write-capacity');}
          lab.held.push({conn, message:m}); receipt(lab, 'held-after-take', {connection:conn.id, message:m});
        } else write(lab, conn, m);
        if (m.kind === 'disconnect') {conn.res.end();break;}
      }
    }
  }
  function offer(lab, seq, p) {const result=lab.broker.offer(lab.token, frame(seq, p));if(result.accepted)lab.readyTimes.set(lab.broker.revision,performance.now());receipt(lab, 'offer', {token:lab.token, seq, p, result});return result;}
  function claim(lab) {const old=lab.token;lab.token=lab.broker.claim(`owner-${lab.broker.epoch+1}`);receipt(lab, 'claim', {previous:old, token:lab.token});return old;}
  function drop(lab, reason) {for(const conn of lab.connections.values()) {receipt(lab, 'socket-destroy-requested', {connection:conn.id, reason});conn.res.destroy();}}
  function closeLab(lab, reason='lab-close') {drop(lab, reason);for(const h of lab.held)receipt(lab,'held-write-cancelled',{connection:h.conn.id,reason});lab.held=[];for(const timer of lab.timers)clearTimeout(timer);lab.timers.clear();labs.delete(lab.id);}
  function action(lab, data) {
    const b=lab.broker;let result={ok:true};receipt(lab, 'control', {action:data.action});
    switch(data.action) {
      case 'publish': result=offer(lab, data.seq ?? (b.latest?.seq||0)+1, data.p ?? .4);break;
      case 'handover': {const old=claim(lab);result={token:lab.token, oldRefusal:b.offer(old,frame(999,.99))};if(data.publish!==false)offer(lab,1,data.p??.2);break;}
      case 'pause-pump':lab.pausePump=true;break;
      case 'resume-pump':lab.pausePump=false;break;
      case 'delay-next-write':if(!Number.isFinite(data.ms)||data.ms<1||data.ms>5000)throw Error('delay-range');lab.delayNextMs=data.ms;break;
      case 'hold-writes':lab.holdWrites=true;break;
      case 'allow-writes':lab.holdWrites=false;break;
      case 'release-held': {const held=lab.held.splice(0,data.count??lab.held.length);for(const h of held)write(lab,h.conn,h.message,'delayed-outbound-release');result={released:held.length};break;}
      case 'drop-tcp':drop(lab,'explicit-loopback-TCP-drop');break;
      case 'disconnect-during-handover':claim(lab);offer(lab,1,.2);drop(lab,'handover-before-pump');break;
      case 'skip-next':lab.skipNext=true;break;
      case 'duplicate-last':if(!lab.lastPublication)throw Error('no-publication');for(const c of lab.connections.values())write(lab,c,{...lab.lastPublication,session:c.session},'duplicate-same-session-envelope');break;
      case 'replay-old-session':if(!lab.lastPublication)throw Error('no-publication');for(const c of lab.connections.values())write(lab,c,lab.lastPublication,'old-session-envelope-in-new-stream');break;
      case 'ack-latest':{const job=b.history.at(-1);if(!job)throw Error('no-job');result=b.ack(job,{hash:job.hash});if(result.accepted)lab.readyTimes.set(b.revision,performance.now());receipt(lab,'simulated-storage-ack',{job,result});break;}
      case 'renew':result=b.renew(data.session,data.challenge);break;
      case 'next-open':if(!['publish-before-open','publish-after-open','handover-after-open'].includes(data.mode))throw Error('invalid-open-hook');lab.nextOpen=data.mode;break;
      case 'terminal':result=b.terminal(lab.token);break;
      case 'close':closeLab(lab);return {closed:true};
      default:throw Error('unknown-action');
    }
    pump(lab);return {...result, currentToken:b.token(), revision:b.revision};
  }
  const json=(res,data,status=200)=>{res.writeHead(status,{'Content-Type':'application/json','Cache-Control':'no-store'});res.end(JSON.stringify(data));};
  const server=http.createServer(async(req,res)=>{
    try {
      const host=req.headers.host||'';
      if(!/^(127\.0\.0\.1|localhost)(:\d+)?$/.test(host))return json(res,{error:'loopback-host-required'},403);
      const origin=req.headers.origin;
      if(origin && origin!==`http://${host}`)return json(res,{error:'same-origin-required'},403);
      const url=new URL(req.url,`http://${host}`);
      if(url.pathname==='/health')return json(res,{ready:!stopping,scope:'synthetic loopback SSE only',leaseMs,labs:labs.size,connections:[...labs.values()].reduce((n,l)=>n+l.connections.size,0),startedAt});
      if(req.method==='POST') {
        if(!req.headers['content-type']?.startsWith('application/json'))return json(res,{error:'json-required'},415);
        let body='';for await(const chunk of req){body+=chunk;if(Buffer.byteLength(body)>4_000_000)throw Error('body-limit');}
        const data=JSON.parse(body||'{}');
        if(url.pathname==='/api/create'){const lab=newLab();return json(res,{id:lab.id,leaseMs,token:lab.token});}
        if(url.pathname==='/api/receipt'){const safe=String(data.kind||'browser').replace(/[^a-z0-9_-]/gi,'').slice(0,32);const file=`${safe}-${Date.now()}.json`;fs.writeFileSync(path.join(out,file),JSON.stringify(data,null,2)+'\n');return json(res,{saved:true,file});}
        if(url.pathname==='/api/shutdown'){json(res,{stopping:true});setImmediate(()=>stop('http-shutdown'));return;}
        const lab=labs.get(data.lab);if(!lab)throw Error('unknown-lab');
        if(url.pathname==='/api/action')return json(res,action(lab,data));
        if(url.pathname==='/api/events')return json(res,{events:lab.events,token:lab.broker.token(),status:lab.broker.status,held:lab.held.length,connections:lab.connections.size,stats:lab.broker.stats});
      }
      if(req.method==='GET' && url.pathname==='/stream') {
        const lab=labs.get(url.searchParams.get('lab'));if(!lab)throw Error('unknown-lab');
        const hello={session:url.searchParams.get('session'),challenge:url.searchParams.get('challenge')};
        const hook=lab.nextOpen;lab.nextOpen=null;
        if(hook==='publish-before-open')offer(lab,1,.1);
        const opened=lab.broker.open(hello);if(opened.error)return json(res,opened,409);
        const conn={id:++nextConnection,session:hello.session,res,closed:false};lab.connections.set(conn.id,conn);
        receipt(lab,'stream-open',{connection:conn.id,session:hello.session,opened,hook});
        res.writeHead(200,{'Content-Type':'text/event-stream','Cache-Control':'no-store, no-transform','Connection':'keep-alive','X-Accel-Buffering':'no'});res.flushHeaders();res.write(': synthetic loopback SSE\n\n');
        const onClose=()=>{if(conn.closed)return;conn.closed=true;lab.broker.close(conn.session);lab.connections.delete(conn.id);receipt(lab,'stream-close',{connection:conn.id,session:conn.session});};
        res.on('close',onClose);res.on('error',onClose);
        if(hook==='publish-after-open')offer(lab,1,.1);
        if(hook==='handover-after-open'){claim(lab);offer(lab,1,.2);}
        pump(lab);return;
      }
      const files={'/':'browser/index.html','/browser.mjs':'browser/browser.mjs','/wire-client.mjs':'src/wire-client.mjs','/scenarios.mjs':'src/scenarios.mjs','/client.mjs':'src/client.mjs','/protocol.mjs':'src/protocol.mjs'};
      if(req.method==='GET' && files[url.pathname]){res.writeHead(200,{'Content-Type':url.pathname==='/'?'text/html; charset=utf-8':'text/javascript; charset=utf-8','Cache-Control':'no-store','Content-Security-Policy':"default-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self'; script-src 'self'; frame-ancestors 'none'"});res.end(fs.readFileSync(path.join(root,files[url.pathname])));return;}
      json(res,{error:'not-found'},404);
    }catch(error){if(res.headersSent)res.destroy();else json(res,{error:error.message},400);}
  });
  server.on('connection',socket=>{sockets.add(socket);socket.on('close',()=>sockets.delete(socket));});
  server.requestTimeout=5000;server.headersTimeout=5000;
  function stop(reason='explicit') {
    if(stopPromise)return stopPromise;
    stopPromise=(async()=>{stopping=true;clearTimeout(timer);
    // server.close() may resolve before destroyed sockets emit their final close
    // events. Register those receipts BEFORE destruction and await both facts.
    const finalLabs=[...labs.values()], finalSockets=[...sockets];
    const socketClosed=finalSockets.map(socket=>new Promise(resolve=>socket.once('close',resolve)));
    const listenerClosed=new Promise(resolve=>server.close(resolve));
    for(const lab of finalLabs)closeLab(lab,'server-shutdown');
    for(const socket of finalSockets)socket.destroy();
    let cleanupTimedOut=false, cleanupTimer;
    await Promise.race([Promise.all([listenerClosed,...socketClosed]),new Promise(resolve=>{cleanupTimer=setTimeout(()=>{cleanupTimedOut=true;resolve();},2000);})]);
    clearTimeout(cleanupTimer);
    const report={kind:cleanupTimedOut||sockets.size?'incomplete-shutdown':'clean-shutdown',reason,startedAt,endedAt:new Date().toISOString(),remainingSockets:sockets.size,remainingLabs:labs.size,cleanupTimedOut,labs:finalLabs.map(l=>({id:l.id,events:l.events,held:l.held.length,connections:l.connections.size})),scope:'Bounded localhost synthetic server; no production, Internet partition, or physical-pixel claim'};
    fs.writeFileSync(path.join(out,`shutdown-${Date.now()}.json`),JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify({stopped:true,reason,remainingSockets:sockets.size,remainingLabs:labs.size,cleanupTimedOut}));return report;
    })();return stopPromise;
  }
  function listen(port=4660) {return new Promise((resolve,reject)=>{server.once('error',reject);server.listen(port,'127.0.0.1',()=>{server.off('error',reject);timer=setTimeout(()=>stop('30-minute-bound').then(report=>process.exit(report.remainingSockets||report.cleanupTimedOut?1:0)),Math.min(maxRuntimeMs,30*60*1000));timer.unref();resolve(server.address());});});}
  return {server,labs,listen,stop};
}
if(process.argv[1] && path.resolve(process.argv[1])===fileURLToPath(import.meta.url)) {
  const app=createStreamServer({out:process.env.STREAM_OUT,leaseMs:Number(process.env.LEASE_MS||1500)});
  const address=await app.listen(Number(process.env.STREAM_PORT||4660));console.log(`READY http://127.0.0.1:${address.port} (30 minute maximum)`);
  for(const signal of ['SIGINT','SIGTERM'])process.once(signal,()=>app.stop(signal).then(report=>process.exit(report.remainingSockets||report.cleanupTimedOut?1:0)));
}
