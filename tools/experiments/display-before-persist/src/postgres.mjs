import pg from 'pg';
const { Pool } = pg;

export class PgStore {
 constructor(config){this.pool=new Pool({...config,max:10,connectionTimeoutMillis:1500,query_timeout:5500});}
 async init(){await this.pool.query(`CREATE TABLE IF NOT EXISTS publication_log(run text NOT NULL,arm text NOT NULL,epoch text NOT NULL,event integer NOT NULL,seq integer NOT NULL,payload jsonb NOT NULL,hash text NOT NULL,recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),PRIMARY KEY(run,arm,epoch,event,seq));ALTER TABLE publication_log ADD COLUMN IF NOT EXISTS recorded_at timestamptz NOT NULL DEFAULT clock_timestamp();CREATE TABLE IF NOT EXISTS latest_publication(run text NOT NULL,arm text NOT NULL,epoch text NOT NULL,event integer NOT NULL,seq integer NOT NULL,hash text NOT NULL,PRIMARY KEY(run,arm,epoch,event));`);}
 async persist(job,{delayMs=0,fail=false,ambiguous=false}={}){
  const c=await this.pool.connect();let committed=false,commitAttempted=false;
  try{await c.query('BEGIN');await c.query("SET LOCAL statement_timeout='5000ms'");
   if(delayMs)await c.query('SELECT pg_sleep($1)',[delayMs/1000]);
   if(fail)await c.query('SELECT 1/0');
   const id=[job.run,job.arm,job.epoch,job.event,job.seq];
   await c.query('INSERT INTO publication_log(run,arm,epoch,event,seq,payload,hash) VALUES($1,$2,$3,$4,$5,$6,$7) ON CONFLICT DO NOTHING',[...id,job.payload,job.hash]);
   const row=(await c.query('SELECT hash,recorded_at FROM publication_log WHERE run=$1 AND arm=$2 AND epoch=$3 AND event=$4 AND seq=$5',id)).rows[0];
   if(row.hash!==job.hash)throw new Error('identity-payload-conflict');
   await c.query('INSERT INTO latest_publication(run,arm,epoch,event,seq,hash) VALUES($1,$2,$3,$4,$5,$6) ON CONFLICT(run,arm,epoch,event) DO UPDATE SET seq=EXCLUDED.seq,hash=EXCLUDED.hash WHERE latest_publication.seq<EXCLUDED.seq',[...id,job.hash]);
   commitAttempted=true;await c.query('COMMIT');committed=true;
   if(ambiguous)throw new Error('injected-commit-ack-loss');
   return {recordedAt:row.recorded_at,hash:row.hash};
  }catch(e){if(!committed)await c.query('ROLLBACK').catch(()=>{});e.outcomeUnknown=commitAttempted;throw e;}finally{c.release();}
 }
 async reconcile(job){const rows=(await this.pool.query('SELECT hash,recorded_at FROM publication_log WHERE run=$1 AND arm=$2 AND epoch=$3 AND event=$4 AND seq=$5',[job.run,job.arm,job.epoch,job.event,job.seq])).rows;if(!rows.length)return null;if(rows[0].hash!==job.hash)throw new Error('identity-payload-conflict');return {hash:rows[0].hash,recordedAt:rows[0].recorded_at,reconciled:true};}
 async rows(run,arm){return (await this.pool.query('SELECT * FROM publication_log WHERE run=$1 AND arm=$2 ORDER BY seq',[run,arm])).rows;}
 async latest(run,arm){return (await this.pool.query('SELECT * FROM latest_publication WHERE run=$1 AND arm=$2',[run,arm])).rows;}
 async close(){await this.pool.end();}
}
