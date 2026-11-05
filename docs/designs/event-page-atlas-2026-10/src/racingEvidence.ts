import {racingReaderTime} from './racingReaderClock.ts';
import wire from './racingEvidence.json' with {type:'json'};
import type {CatalogEvidenceRow} from './catalogPresentation';
export type RaceRow=typeof wire.rows[number];
export const racingWire=wire;export const racingRows=wire.rows;export const racingFinalRows=wire.rows.map(r=>r.final);
const stable=(v:unknown):string=>JSON.stringify(v,(_,x)=>x&&typeof x==='object'&&!Array.isArray(x)?Object.fromEntries(Object.keys(x).sort().map(k=>[k,x[k]])):x);
const originals=new Map(wire.rows.flatMap(p=>[[stable(p.original),p],[stable(p.final),p]] as [string,RaceRow][]));
export function racingFor(row:CatalogEvidenceRow){return [63989371,63989361,63989363,63989365].includes(Number(row._market_id))?originals.get(stable(row)):undefined;}
export function racingPregame(row:CatalogEvidenceRow){const p=racingFor(row),b=p?.baseline;if(!b||!Number.isFinite(b.value)||!Number.isFinite(b.size)||b.value<=0||b.value>=1||b.size<=0||Date.parse(b.at)>=Date.parse(wire.start)||Date.parse(b.at)<Date.parse(wire.start)-86400000)return null;return b;}
export const racingClock=racingReaderTime;
export function racingNote(row:CatalogEvidenceRow){const p=racingFor(row);if(!p)return undefined;const b=racingPregame(row);return b?'Pre-race trade baseline · '+racingClock(b.at):'No qualifying pre-race trade in the bounded capture';}
export const racingResult=(p:RaceRow)=>p.result===true?'Won':p.result===false?'Lost':'Result unconfirmed';
