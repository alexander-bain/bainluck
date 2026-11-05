import {eventReaderTime} from './eventReaderTime.ts';
import wire from './halfEvidence.json' with {type:'json'};
export const halfWire=wire;
export type HalfRow=typeof wire.rows[number];
const canonical=(x:unknown):string=>JSON.stringify(x,(_k,v)=>v&&typeof v==='object'&&!Array.isArray(v)?Object.fromEntries(Object.entries(v).sort(([a],[b])=>a.localeCompare(b))):v);
export function halfFor(row:unknown):HalfRow|undefined{const s=canonical(row);return halfWire.rows.find(r=>canonical(r.original)===s||canonical(r.display)===s)}
export const halfClock=(at:string)=>eventReaderTime.full(at);
export function halfNote(row:unknown){const r=halfFor(row);return r?(r.baseline?'Kalshi hour-ending trade · '+halfClock(r.baseline.at)+' · by scheduled tipoff':'No qualifying pregame trade captured'):undefined}
export const halfDefault=wire.rows.find(r=>r.side==='home'&&r.minimumLead===12)!;

/** Only the complete, unchanged captured family may use the halftime comparison. */
export function halfCatalogEligible(eventID:unknown,status:string,rows:unknown[],visibleRows:unknown[],held=false):boolean{
 if(eventID!==wire.eventID||status!=='completed'||held||rows.length!==wire.rows.length||visibleRows.length!==rows.length)return false;
 const retained=rows.map(halfFor),visible=visibleRows.map(halfFor);
 return retained.every(Boolean)&&visible.every(Boolean)&&new Set(retained.map(r=>r!.key)).size===wire.rows.length&&new Set(visible.map(r=>r!.key)).size===wire.rows.length;
}
