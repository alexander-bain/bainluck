import {eventReaderTime} from './eventReaderTime.ts';
import wire from './seriesPregame.json' with {type:'json'};
const identity=(row:unknown)=>{
 if(!row||typeof row!=='object')return null;
 const r=row as Record<string,unknown>;
 return JSON.stringify([r.source,r._market_id,r.outcome_id,r.contributor_outcome_ids,r.market_name,r.outcome_name,r._display_scope]);
};
const bindings=wire.records.map(record=>({record,identity:identity(JSON.parse(record.originalJSON))}));
export function seriesPregameRecord(row:unknown){const id=identity(row);const matches=bindings.filter(x=>x.identity===id);return matches.length===1?matches[0].record:null;}
export function seriesPregame(row:unknown){const r=seriesPregameRecord(row);return r?.value!=null&&r.at?{value:r.value,at:r.at}:null;}
export function seriesPregameNote(row:unknown){const r=seriesPregameRecord(row);if(!r)return undefined;return r.at?`Recorded before Game 1 · ${eventReaderTime.full(r.at,true)}.`:r.reason??undefined;}
