import {readerTime} from './readerTime.ts';
import wire from './placementEvidence.json' with {type:'json'};
import type {CatalogEvidenceRow} from './catalogPresentation';
export const placementWire=wire;export const placementRows=wire.rows;export const placementFinalRows=wire.rows.map(r=>r.final);export type PlacementRow=typeof wire.rows[number];
const stable=(v:unknown):string=>JSON.stringify(v,(_,x)=>x&&typeof x==='object'&&!Array.isArray(x)?Object.fromEntries(Object.keys(x).sort().map(k=>[k,x[k]])):x);
const index=new Map(wire.rows.flatMap(r=>[[stable(r.final),r],...r.original?[[stable(r.original),r]]:[]] as [string,PlacementRow][]));
export const placementFor=(r:CatalogEvidenceRow)=>index.get(stable(r));
export function placementPregame(row:CatalogEvidenceRow){const b=placementFor(row)?.baseline;if(!b||!Number.isFinite(b.value)||!Number.isFinite(b.volume)||b.volume<=0||b.value<=0||b.value>=1||Date.parse(b.at)>Date.parse(wire.baselineCutoff)||Date.parse(b.at)<Date.parse(wire.baselineCutoff)-86400000)return null;return b;}
export const placementClock=(s:string)=>readerTime(s);
export const placementNote=(r:CatalogEvidenceRow)=>placementFor(r)?placementPregame(r)?'Kalshi hour-ending trade · '+placementClock(placementPregame(r)!.at)+' · before opening day':'No qualifying pre-event trade captured':undefined;
export const placementResult=(r:PlacementRow)=>r.result?'Made top 10':'Missed top 10';
export const placementDefault=wire.rows.find(r=>r.key===wire.defaultKey)!;
export const placementKnown=wire.rows.filter(r=>r.baseline).sort((a,b)=>b.baseline!.value-a.baseline!.value);
