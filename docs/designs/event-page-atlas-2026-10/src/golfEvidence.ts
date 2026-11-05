import {readerTime} from './readerTime.ts';
import wire from './golfEvidence.json' with {type:'json'};
import type {CatalogEvidenceRow} from './catalogPresentation';
export const golfWire=wire;export const golfRows=wire.rows;export const golfFinalRows=wire.rows.map(r=>r.final);export type GolfRow=typeof wire.rows[number];
const stable=(v:unknown):string=>JSON.stringify(v,(_,x)=>x&&typeof x==='object'&&!Array.isArray(x)?Object.fromEntries(Object.keys(x).sort().map(k=>[k,x[k]])):x);
const index=new Map(wire.rows.flatMap(r=>[[stable(r.final),r],...r.original?[[stable(r.original),r]]:[]] as [string,GolfRow][]));
export function golfFor(row:CatalogEvidenceRow){return Number(row._market_id)===62455818?index.get(stable(row)):undefined;}
export function golfPregame(row:CatalogEvidenceRow){const p=golfFor(row),b=p?.baseline;if(!b||!Number.isFinite(b.value)||!Number.isFinite(b.volume)||b.volume<=0||b.value<=0||b.value>=1||Date.parse(b.at)>Date.parse(wire.baselineCutoff)||Date.parse(b.at)<Date.parse(wire.baselineCutoff)-86400000)return null;return b;}
export const golfClock=(s:string)=>readerTime(s);
export function golfNote(row:CatalogEvidenceRow){const p=golfFor(row);if(!p)return undefined;const b=golfPregame(row);return b?'Hour-ending trade · '+golfClock(b.at)+' · before opening day':'No qualifying pre-event trade in the captured day';}
export const golfResult=(p:GolfRow)=>p.result?'Won':'Lost';
export const golfScore=(p:GolfRow)=>p.score===null?'Unavailable':p.score==='E'?'Even':p.score.replace('-','−');
export const golfFeatured=[golfRows.find(r=>r.result)!,...golfRows.filter(r=>!r.result&&r.baseline).sort((a,b)=>b.baseline!.value-a.baseline!.value).slice(0,5)];
