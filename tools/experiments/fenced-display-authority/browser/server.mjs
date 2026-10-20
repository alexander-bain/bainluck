import http from 'node:http';import fs from 'node:fs';import path from 'node:path';import {fileURLToPath} from 'node:url';import {Broker,frame} from '../src/broker.mjs';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');const port=Number(process.env.BROWSER_PORT||4658);const out=process.env.BROWSER_OUT||path.join(root,'results/browser');fs.mkdirSync(out,{recursive:true});let last=null;
const drain=(b,s)=>{const a=[];let m;while(m=b.take(s))a.push(m);return a;};
function scenario(name,hello){const b=new Broker({leaseMs:400}),old=b.claim('old-owner'),events=[];let initial=[],late=[],fence=[],refusal=null;
 if(name==='reconnect'){b.offer(old,frame(1,.9));const newer=b.claim('new-owner');b.offer(newer,frame(1,.2));b.open(hello);initial=drain(b,hello.session);}
 else if(name==='queued'){b.open(hello);b.offer(old,frame(1,.9));const newer=b.claim('new-owner');b.offer(newer,frame(1,.2));initial=drain(b,hello.session);}
 else {b.open(hello);initial=drain(b,hello.session);if(name==='stale-owner'){const newer=b.claim('new-owner');refusal=b.offer(old,frame(1,.9));b.offer(newer,frame(1,.2));late=drain(b,hello.session);}
 else if(['in-flight','partition','stalled-expiry'].includes(name)){b.offer(old,frame(1,.9));late=drain(b,hello.session);b.claim('new-owner');fence=drain(b,hello.session);}
 else throw Error('unknown-scenario');}
 events.push({kind:'server-final-authority',token:b.token(),status:b.status});return {name,leaseMs:400,initial,late,fence,refusal,events};}
const server=http.createServer(async(req,res)=>{try{const url=new URL(req.url,'http://localhost');res.setHeader('Cache-Control','no-store');if(url.pathname==='/health'){res.setHeader('Content-Type','application/json');res.end(JSON.stringify({ready:true,port,scope:'isolated synthetic browser authority test'}));return;}
 if(req.method==='POST'&&['/scenario','/receipt'].includes(url.pathname)){let body='';for await(const chunk of req){body+=chunk;if(body.length>1000000)throw Error('body-limit');}const data=JSON.parse(body);res.setHeader('Content-Type','application/json');if(url.pathname==='/scenario')res.end(JSON.stringify(scenario(data.name,data.hello)));else {last={...data,savedAt:new Date().toISOString()};const file=path.join(out,'browser-receipt-'+Date.now()+'.json');fs.writeFileSync(file,JSON.stringify(last,null,2)+'\n');res.end(JSON.stringify({saved:true,file:path.basename(file)}));}return;}
 if(url.pathname==='/results'){res.setHeader('Content-Type','application/json');res.end(JSON.stringify(last));return;}
 const files={'/':'browser/index.html','/client.mjs':'src/client.mjs','/protocol.mjs':'src/protocol.mjs'};if(files[url.pathname]){res.setHeader('Content-Type',url.pathname==='/'?'text/html':'application/javascript');res.end(fs.readFileSync(path.join(root,files[url.pathname])));return;}res.writeHead(404);res.end();
 }catch(e){res.writeHead(400);res.end(JSON.stringify({error:e.message}));}});
server.listen(port,'127.0.0.1',()=>console.log(`READY http://127.0.0.1:${port}`));
let stopping=false;function stop(){if(stopping)return;stopping=true;server.close(()=>process.exit(0));setTimeout(()=>process.exit(0),2000).unref();}process.on('SIGTERM',stop);process.on('SIGINT',stop);setTimeout(stop,30*60*1000).unref();
