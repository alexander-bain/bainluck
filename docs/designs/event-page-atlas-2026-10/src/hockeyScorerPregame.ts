import {eventReaderTime} from './eventReaderTime.ts';
import wire from './hockeyScorerPregame.json' with {type:'json'};
import type {CatalogEvidenceRow} from './catalogPresentation';
export type ScorerWire=typeof wire;
const stable=(v:unknown):string=>JSON.stringify(v,(_,x)=>x&&typeof x==='object'&&!Array.isArray(x)?Object.fromEntries(Object.keys(x).sort().map(k=>[k,x[k]])):x);
export function scorerPregame(row:CatalogEvidenceRow,w:ScorerWire=wire){
 if(w.eventID!==15169793||w.marketID!==64870965||w.eventTicker!=='KXNHLGOAL-26OCT03BOSMIN'||w.verifiedStart!==true||!Number.isFinite(Date.parse(w.start)))return null;
 const matches=w.points.filter(p=>p.key===row.key&&stable(p.original)===stable(row));if(matches.length!==1)return null;
 const before=matches[0].observations.filter(o=>Number.isFinite(Date.parse(o.at))&&Date.parse(o.at)<Date.parse(w.start));
 const last=before.reduce((a,o)=>!a||Date.parse(o.at)>Date.parse(a.at)?o:a,null as typeof before[number]|null);
 if(!last||!Number.isFinite(last.value)||last.value<=0||last.value>=1||!Number.isFinite(last.volume)||last.volume<=0||before.filter(o=>o.at===last.at).length!==1)return null;
 return {value:last.value,at:last.at,ticker:matches[0].ticker,volume:last.volume};
}
export function scorerPregameNote(row:CatalogEvidenceRow){const b=scorerPregame(row);return b?'Pregame trade · minute ending '+eventReaderTime.full(b.at):undefined}
export {wire as scorerPregameEvidence};
