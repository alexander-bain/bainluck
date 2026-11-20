#!/usr/bin/env node
'use strict';
// #11674 qualification only: a scripted loopback arm for the recorder's
// negative controls. It is NOT the product: it serves a synthetic page that
// honors the same DOM contract (hero/chart #11673 attributes, the
// "Probability observed" readout) and opens ONE EventSource the way the
// product does, against a scripted SSE stream. The product-path controls run
// against the real product lab arm instead.
//   node fixture_arm.cjs --port N --page VARIANT --stream SCENARIO [--tls CERT_DIR]
const fs = require('fs');
const http = require('http');
const https = require('https');
const crypto = require('crypto');

const args = {};
for (let i = 2; i < process.argv.length; i += 2) args[process.argv[i].slice(2)] = process.argv[i + 1];
const PORT = Number(args.port), PAGE = args.page, STREAM = args.stream, EVENT = 1;
if (!PORT || !PAGE || !STREAM) { console.error('usage: --port N --page VARIANT --stream SCENARIO [--tls DIR]'); process.exit(2); }
const AUTH = {incarnation: '7', namespace: '3b4f1a52-8d7e-4c1a-9f0e-2a6b5c4d3e21'};
const log = [];
let reconnectSent = false; // the product-style reopen is exercised once per arm
const note = e => { log.push({at: Date.now(), ...e}); };

function page() {
  const proto = {missing: '', duplicate: '?preview_protocol=authority-v3&preview_protocol=authority-v3'}[PAGE] ?? '?preview_protocol=authority-v3';
  const heroStyle = PAGE === 'hidden-hero' ? 'display:none' : '';
  const heroAttrs = PAGE === 'unsupported' ? '' : 'data-display-basis="committed" data-display-state="fresh" data-display-received="0" data-display-observed-at="2026-10-28T00:00:00.000Z"';
  return `<!doctype html><html><head><meta charset="utf-8"><title>fixture</title></head><body>
<div data-testid="event-hero-probability" data-probability="0.60" style="${heroStyle}" ${heroAttrs}>60%</div>
<div data-testid="live-connection-status"><button type="button">Live</button>
 <div id="d" hidden><dl><div><dt>Probability observed</dt><dd><time datetime="2026-10-28T00:00:00.000Z">00:00:00.000</time></dd></div></dl></div></div>
<div data-testid="win-probability-card"><svg class="recharts-surface" width="360" height="200" viewBox="0 0 360 200">
 <g class="recharts-line"><path stroke="#000" d="M0,100L10,100"></path></g>
 <circle data-chart-endpoint-state="fresh" data-chart-endpoint-at="2026-10-28T00:00:00.000Z" data-chart-endpoint-basis="committed" data-chart-history="1" cx="10" cy="100" r="3"></circle></svg></div>
<script>
const btn=document.querySelector('[data-testid="live-connection-status"] button');btn.onclick=()=>{document.getElementById('d').hidden=false;};
const hero=document.querySelector('[data-testid="event-hero-probability"]'),time=document.querySelector('time'),path=document.querySelector('.recharts-line path'),dot=document.querySelector('[data-chart-endpoint-state]');
let pts=[[0,100],[10,100]];
function adopt(p,at){hero.textContent=Math.round(p*100)+'%';hero.setAttribute('data-probability',p.toFixed(2));if(hero.hasAttribute('data-display-observed-at'))hero.setAttribute('data-display-observed-at',at);time.setAttribute('datetime',at);time.textContent=at.slice(11,23);
 pts.push([pts.length*5,200-p*200]);path.setAttribute('d','M'+pts.map(q=>q.join(',')).join('L'));dot.setAttribute('data-chart-endpoint-at',at);dot.setAttribute('cx',String(pts.at(-1)[0]));}
function open(){const es=new EventSource('/api/events/${EVENT}/stream${proto}');
 es.addEventListener('folded_probability',e=>{try{const d=JSON.parse(e.data);adopt(d.p,d.observed_at);}catch{}});
 es.addEventListener('reconnect',()=>{es.close();setTimeout(open,50);});return es;}
open();
${PAGE === 'second-subscription' ? "setTimeout(open,3000);" : ''}
${PAGE === 'market-stream' ? "new EventSource('/api/markets/stream?ids=11,12');" : ''}
${PAGE === 'many-requests' ? "setInterval(()=>fetch('/api/ping').catch(()=>{}),200);" : ''}
${PAGE === 'big-fetch' ? "setTimeout(()=>fetch('/api/big').then(r=>r.arrayBuffer()).catch(()=>{}),2000);" : ''}
${PAGE === 'redirect' ? "setTimeout(()=>fetch('/api/redirect').catch(()=>{}),2000);" : ''}
${PAGE === 'busy' ? "setInterval(()=>{const t=performance.now();while(performance.now()-t<700){}},4000);" : ''}
${PAGE === 'replace-document' ? "if(!sessionStorage.getItem('r')){sessionStorage.setItem('r','1');setTimeout(()=>location.replace(location.href),Number(" + (args['replace-after-ms'] || 30000) + "));}" : ''}
</script></body></html>`;
}

function sse(req, res) {
  const session = crypto.randomUUID();
  note({kind: 'stream-open', url: req.url, session});
  if (STREAM === 'hung') return; // accept, never answer
  res.writeHead(200, {'content-type': 'text/event-stream', 'cache-control': 'no-cache'});
  const send = (type, data) => res.write(`event: ${type}\ndata: ${typeof data === 'string' ? data : JSON.stringify(data)}\n\n`);
  const env = (kind, extra) => ({protocol: 3, event_id: EVENT, authority: AUTH, stream_session: session, ...extra});
  if (STREAM === 'quiet') return;
  if (STREAM === 'endless') {
    const blob = 'x'.repeat(16 * 1024);
    let n = 0, stopped = false;
    const pump = () => { while (!stopped) { n++; if (!res.write(`event: heartbeat\ndata: ${blob}\n\n`)) return res.once('drain', pump); } };
    res.on('close', () => { stopped = true; note({kind: 'endless-closed', frames: n, bytes: n * blob.length}); });
    return pump();
  }
  const members = STREAM === 'wrong-members' ? [1, 2] : [EVENT];
  send('preview_open_v3', STREAM === 'wrong-domain' ? {...env(), authority: {incarnation: '8', namespace: AUTH.namespace}, members} : env('open', {members}));
  let rev = 100, i = 0;
  const timer = setInterval(() => {
    i++;
    const at = new Date().toISOString();
    const p = 0.55 + 0.1 * Math.sin(i / 3);
    send('folded_probability', {event_id: STREAM === 'wrong-event' && i === 5 ? 999 : EVENT, p, rev: ++rev, observed_at: at});
    if (STREAM === 'malformed' && i === 5) send('preview_v3', '{"protocol":3,"event_id":1,');
    else if (STREAM === 'dup-key' && i === 5) send('preview_v3', `{"protocol":3,"protocol":3,"event_id":1,"authority":${JSON.stringify(AUTH)},"stream_session":"${session}","frame":{}}`);
    else if (STREAM === 'missing-protocol-field' && i === 5) { const e = env('frame', {frame: {p}}); delete e.protocol; send('preview_v3', e); }
    else send('preview_v3', STREAM === 'wrong-session' && i === 5 ? {...env('frame', {frame: {p}}), stream_session: crypto.randomUUID()} : env('frame', {frame: {p, base_rev: rev}}));
    if (i % 2 === 0) send('heartbeat', '{}');
    if (STREAM === 'reconnect-event' && i === 30 && !reconnectSent) { reconnectSent = true; send('reconnect', '{}'); }
  }, 1000);
  res.on('close', () => { clearInterval(timer); note({kind: 'stream-closed', session}); });
}

function handler(req, res) {
  const u = new URL(req.url, 'http://x');
  note({kind: 'request', method: req.method, url: req.url});
  if (u.pathname === `/events/${EVENT}`) { res.writeHead(200, {'content-type': 'text/html'}); return res.end(page()); }
  if (u.pathname === `/api/events/${EVENT}/stream`) return sse(req, res);
  if (u.pathname === '/api/markets/stream') {
    // A second product subscription that is not the case stream (the real page holds one).
    res.writeHead(200, {'content-type': 'text/event-stream', 'cache-control': 'no-cache'});
    const t = setInterval(() => res.write('event: heartbeat\ndata: {}\n\n'), 2000);
    return res.on('close', () => clearInterval(t));
  }
  if (u.pathname === '/api/ping') { res.writeHead(200, {'content-type': 'application/json'}); return res.end('{"ok":true}'); }
  if (u.pathname === '/api/redirect') { res.writeHead(302, {location: '/api/ping'}); return res.end(); }
  if (u.pathname === '/api/big') {
    const total = 5 * 1024 * 1024;
    res.writeHead(200, {'content-type': 'application/octet-stream', 'content-length': String(total)});
    let sent = 0;
    const chunk = Buffer.alloc(32 * 1024, 0x61);
    const pump = () => { while (sent < total) { sent += chunk.length; if (!res.write(chunk)) return res.once('drain', pump); } res.end(); };
    res.on('close', () => note({kind: 'big-closed', sent}));
    return pump();
  }
  if (u.pathname === '/__fixture/log') { res.writeHead(200, {'content-type': 'application/json'}); return res.end(JSON.stringify(log)); }
  res.writeHead(404); res.end();
}

const server = args.tls
  ? https.createServer({key: fs.readFileSync(`${args.tls}/key.pem`), cert: fs.readFileSync(`${args.tls}/cert.pem`)}, handler)
  : http.createServer(handler);
server.listen(PORT, '127.0.0.1', () => console.log(`fixture ${args.tls ? 'https' : 'http'}://127.0.0.1:${PORT} page=${PAGE} stream=${STREAM}`));
const stop = () => { fs.writeFileSync(args.log || '/dev/null', JSON.stringify(log)); process.exit(0); };
process.on('SIGTERM', stop);
process.on('SIGINT', stop);
