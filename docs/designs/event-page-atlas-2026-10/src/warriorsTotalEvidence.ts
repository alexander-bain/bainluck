import wire from './warriorsTotalEvidence.json' with {type:'json'};
import {eventReaderTime} from './eventReaderTime.ts';
export const warriorsTotals=wire;
export type WarriorsTotal=typeof wire.rows[number];
const canonical=(x:unknown):string=>JSON.stringify(x,(_k,v)=>v&&typeof v==='object'&&!Array.isArray(v)?Object.fromEntries(Object.entries(v).sort(([a],[b])=>a.localeCompare(b))):v);
const originals=new Map(wire.rows.map(r=>[canonical(r.original),r]));
export const warriorsTotalFor=(row:unknown)=>originals.get(canonical(row));
export const warriorsTotalDefault=wire.rows.find(r=>r.minimumTotal===223)!;
export function warriorsTotalLabel(row:WarriorsTotal){return row.state==='stale'?'No recent price':row.baseline?`${Math.round(row.baseline.value*100)}%`:'Unavailable'}
export function warriorsTotalNote(row:unknown){const r=warriorsTotalFor(row);return !r?undefined:r.baseline?`Pregame hour-ending trade · ${eventReaderTime.full(r.baseline.at,true)} · by scheduled tipoff`:r.state==='stale'?'No recent probability update at the pregame cutoff; the older observation is in Details.':'No qualifying pregame trade captured.'}
export function warriorsTotalsEligible(eventID:unknown,status:string,rows:unknown[],visible:unknown[],held=false){
 if(eventID!==wire.eventID||status!=='completed'||held||rows.length!==wire.rows.length||visible.length!==rows.length)return false;
 const match=(xs:unknown[])=>{const bound=xs.map(warriorsTotalFor);return bound.every(Boolean)&&new Set(bound.map(r=>r!.key)).size===wire.rows.length};
 return match(rows)&&match(visible);
}
