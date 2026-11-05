import {eventReaderTime} from './eventReaderTime.ts';
import wire from './nflTotalPregame.json' with {type:'json'};
export {wire as nflTotalExpectation};
const fields=['source','_market_id','_external_id','market_type','market_name','outcome_name','period','threshold','category'];
const identity=(row:unknown)=>row&&typeof row==='object'?JSON.stringify(fields.map(f=>(row as Record<string,unknown>)[f])):null;
const bindings=wire.records.map(record=>({record,identity:identity(JSON.parse(record.originalJSON))}));
export function nflTotalPregameRecord(row:unknown){const id=identity(row);const matches=bindings.filter(x=>x.identity===id);return matches.length===1?matches[0].record:null;}
export function nflTotalPregame(row:unknown){const r=nflTotalPregameRecord(row);return r?.value!=null&&r.at?{value:r.value,at:r.at}:null;}
export function nflTotalPregameNote(row:unknown){const r=nflTotalPregameRecord(row);return !r?undefined:r.at?`Recorded before kickoff · ${eventReaderTime.full(r.at,true)}.`:'No pregame observation in the retained history response.';}
