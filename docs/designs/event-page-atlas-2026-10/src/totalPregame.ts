import {eventReaderTime} from './eventReaderTime.ts';
import capturedWire from './totalPregame.json' with {type:'json'};
import {withoutBaseline,nbaMountedBaselineUnavailable} from './basketballBaselineAvailability.ts';
const wire={...capturedWire,records:capturedWire.records.map(r=>withoutBaseline(r,nbaMountedBaselineUnavailable))};
export {wire as totalExpectation};
const fields=['source','_market_id','contributor_outcome_ids','market_type','market_name','outcome_name','period','threshold','category','source_file'];
const identity=(row:unknown)=>row&&typeof row==='object'?JSON.stringify(fields.map(f=>(row as Record<string,unknown>)[f])):null;
const bindings=wire.records.map(record=>({record,identity:identity(JSON.parse(record.originalJSON))}));
export function totalPregameRecord(row:unknown){const id=identity(row);const matches=bindings.filter(x=>x.identity===id);return matches.length===1?matches[0].record:null;}
export function totalPregame(row:unknown){const r=totalPregameRecord(row);return r?.value!=null&&r.at?{value:r.value,at:r.at}:null;}
export function totalPregameNote(row:unknown){const r=totalPregameRecord(row);return !r?undefined:r.at?`Recorded before tip-off · ${eventReaderTime.full(r.at,true)}.`:nbaMountedBaselineUnavailable?'Pregame chance is unavailable in this page response.':'No pregame observation in the retained history response.';}
