import fs from 'node:fs';
import {Store,Owner,WAL,frame} from './candidate.mjs';
const stage=process.env.CRASH_STAGE,mode=process.env.MODE,stream=process.env.STREAM;
const out=m=>fs.writeSync(1,JSON.stringify(m)+'\n');
const kill=(where,job)=>{out({type:'stage',where,seq:job?.seq});if(where===stage&&job?.seq===Number(process.env.TARGET_SEQ||1)){out({type:'kill',where});process.kill(process.pid,'SIGKILL');}};
const store=new Store();const token=await store.claim(stream);out({type:'token',token});const wal=mode.startsWith('wal')?new WAL(process.env.WAL_FILE):null;
const owner=new Owner({store,token,mode,wal,stage:kill,publish:m=>out({type:'message',message:m})});for(let seq=1;seq<=Number(process.env.COUNT||1);seq++)owner.offer(frame(seq,.42));await owner.drain();await store.close();wal?.close();
