import {eventReaderTime} from './eventReaderTime.ts';
import capturedWire from './marginPregame.json' with {type:'json'};
import {withoutBaseline,nbaMountedBaselineUnavailable} from './basketballBaselineAvailability.ts';
const wire={...capturedWire,records:capturedWire.records.map(r=>withoutBaseline({...r,value:r.value as number|null,at:r.at as string|null},nbaMountedBaselineUnavailable))};
export {wire as marginExpectation};
const fields=['source','_market_id','contributor_outcome_ids','market_type','market_name','outcome_name','period','threshold','category','source_file'];
const identity=(row:unknown)=>row&&typeof row==='object'?JSON.stringify(fields.map(f=>(row as Record<string,unknown>)[f])):null;
const bindings=wire.records.map(record=>({record,identity:identity(JSON.parse(record.originalJSON))}));
export function marginRecord(row:unknown){const id=identity(row),matches=bindings.filter(b=>b.identity===id);return matches.length===1?matches[0].record:null;}
export function marginEligible(rows:unknown[],status:string){const records=rows.map(marginRecord);return status==='completed'&&records.length===25&&records.every(Boolean)&&new Set(records.map(r=>r?.key)).size===25;}
export function marginNote(row:unknown){const r=marginRecord(row);return r?.at?`Recorded before tip-off · ${eventReaderTime.full(r.at,true)}.`:r&&nbaMountedBaselineUnavailable?'Pregame chance is unavailable in this page response.':undefined;}
