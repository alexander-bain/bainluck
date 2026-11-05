import {eventReaderTime} from './eventReaderTime.ts';
import wire from './hockeyEvidence.json' with {type:'json'};
import type {CatalogEvidenceRow} from './catalogPresentation';
export type HockeyWire=typeof wire;
const stable=(v:unknown):string=>JSON.stringify(v,(_,x)=>x&&typeof x==='object'&&!Array.isArray(x)?Object.fromEntries(Object.keys(x).sort().map(k=>[k,x[k]])):x);
export function hockeyBinding(row:CatalogEvidenceRow,w:HockeyWire=wire){
 if(w.eventID!==15169793||w.marketID!==63539066||w.verifiedStart!==true||!Number.isFinite(Date.parse(w.start)))return null;
 const matches=w.points.filter(p=>p.key===row.key&&stable(p.original)===stable(row));return matches.length===1?matches[0]:null;
}
export function hockeyPregame(row:CatalogEvidenceRow,w:HockeyWire=wire){
 const binding=hockeyBinding(row,w);if(!binding)return null;
 const before=binding.observations.filter(p=>Number.isFinite(Date.parse(p.timestamp))&&Date.parse(p.timestamp)<Date.parse(w.start));
 const last=before.reduce((a,p)=>!a||Date.parse(p.timestamp)>Date.parse(a.timestamp)?p:a,null as typeof before[number]|null);
 if(!last||last.bookmaker!=='consensus'||typeof last.probability!=='number'||!Number.isFinite(last.probability)||last.probability<=0||last.probability>=1||before.filter(p=>Date.parse(p.timestamp)===Date.parse(last.timestamp)).length!==1)return null;
 return {value:last.probability,at:last.timestamp};
}
export const hockeyClock=(s:string)=>eventReaderTime.full(s);
export function hockeyPregameNote(row:CatalogEvidenceRow){const b=hockeyPregame(row);return b?'Last recorded before play · '+hockeyClock(b.at):undefined}
export {wire as hockeyEvidence};
