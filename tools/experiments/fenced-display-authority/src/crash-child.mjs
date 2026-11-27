import fs from 'node:fs';import {Broker,frame} from './broker.mjs';import {Journal} from './journal.mjs';
const emit=x=>fs.writeSync(1,JSON.stringify(x)+'\n'),mode=process.env.MODE,op=process.env.OP,target=process.env.STAGE,hello=JSON.parse(process.env.HELLO);const journal=mode==='journal-before'?new Journal(process.env.JOURNAL):null;
const b=new Broker({journal}),t=b.claim('old-owner');b.open(hello);const send=()=>{let m;while(m=b.take(hello.session))emit({type:'wire',message:m});};send();emit({type:'token',token:t});
if(op!=='publication'){b.offer(t,frame(1,.4));send();}
const hit=(where,data={})=>{emit({type:'stage',where,data});if(where===target){emit({type:'kill',where});process.kill(process.pid,'SIGKILL');}};
b.stage=(where,data)=>{if(where.includes('journal')||where==='after_fsync'){if(data.kind===({publication:'publication',handover:'claim',terminal:'terminal'})[op])hit(where,data);}else hit(where,data);};
if(op==='publication'){b.offer(t,frame(1,.7));send();hit('after_send');}
if(op==='handover'){b.claim('new-owner');send();hit('after_send');}
if(op==='terminal'){b.terminal(t);hit('after_terminal');send();hit('after_send');}
emit({type:'unexpected-completion'});process.exitCode=2;
