import {ownedPostgresConfig} from './context.mjs';
import {Pipeline,delay} from '../src/pipeline.mjs';
import {PgStore} from '../src/postgres.mjs';const store=new PgStore(ownedPostgresConfig());const p=new Pipeline({run:process.env.CRASH_RUN,arm:'display-first',store,publish:m=>console.log(JSON.stringify(m)),policy:()=>({delayMs:3000})});p.offer({status:'live',event_id:1,seq:1,p:.4,sources:{kalshi:{value:.4}}});await delay(10000);
