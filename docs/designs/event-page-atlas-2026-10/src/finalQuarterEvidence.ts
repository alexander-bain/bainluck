import {eventReaderTime} from './eventReaderTime.ts';
import raw from './finalQuarterEvidence.json' with {type:'json'};
import {nflAdmitted,nflIdentity,nflFinalRows,type NFLRow} from './nflReconciliation.ts';
import type {CatalogEvidenceRow} from './catalogPresentation';
export const finalQuarterWire=raw;
export type FinalQuarterRow=typeof raw.rows[number];
export const finalQuarterRows=raw.rows;
const stable=(v:unknown):string=>JSON.stringify(v,(_,x)=>x&&typeof x==='object'&&!Array.isArray(x)?Object.fromEntries(Object.keys(x).sort().map(k=>[k,x[k]])):x);
export function finalQuarterFor(row:CatalogEvidenceRow){
 if((row as NFLRow).market_type!=='quarter_winner'||![64559187,64559196,64559205,64559214].includes(Number(row._market_id))||raw.eventID!==14639175||raw.verifiedStart!==true)return undefined;
 const matches=raw.rows.filter(p=>stable(p.original)===stable(row)||(p.earlier&&stable(p.earlier)===stable(row))||(nflAdmitted(row)&&nflIdentity(row as NFLRow)===nflIdentity(p.original as NFLRow)));
 return matches.length===1?matches[0]:undefined;
}
export function finalQuarterBaseline(p:FinalQuarterRow){const b=p.baseline;const at=Date.parse(b.at);return [b.value,b.volume,at].every(Number.isFinite)&&b.value>0&&b.value<1&&b.volume>0&&[1,60].includes(b.intervalMinutes)&&at<Date.parse(raw.start)&&at<=Date.parse(p.bookAt)?b:null;}
export const finalQuarterClock=(b:FinalQuarterRow['baseline'])=>`${b.intervalMinutes===1?'Minute':'Hour'} ending ${eventReaderTime.full(b.at)}`;
export const finalQuarterCaption=(p:FinalQuarterRow)=>`Q${p.quarter} · ${p.side==='tie'?'Tied quarter':(p.side==='home'?'Jaguars':'Eagles')+' outscore opponent'}`;
export function finalQuarterPregame(row:CatalogEvidenceRow){const p=finalQuarterFor(row);return p?finalQuarterBaseline(p):null;}
export function finalQuarterNote(row:CatalogEvidenceRow){const b=finalQuarterPregame(row);return b?`Pregame trade baseline · ${finalQuarterClock(b)}`:undefined;}
export function finalQuarterOriginal(p:FinalQuarterRow){return nflFinalRows.find(r=>nflIdentity(r)===nflIdentity(p.original as NFLRow))!;}
