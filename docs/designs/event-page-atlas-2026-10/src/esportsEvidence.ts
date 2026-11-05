import {readerTime} from './readerTime.ts';
import wire from './esportsEvidence.json' with {type:'json'};
import type {CatalogEvidenceRow} from './catalogPresentation';
export type EsportsRow=CatalogEvidenceRow;
export const handicapQuestion='Map 1 Rounds Handicap: Nice Try (-6.5) vs Flame Hard (+6.5)';
export const matchQuestion='Counter-Strike: Flame Hard vs Nice Try (BO1) - FOX Legacy Cup Group B';
export function esportsIdentity(row:EsportsRow,w=wire){
 const matches=w.rows.filter(({row:r})=>r.key===row.key&&r.source===row.source&&r._market_id===row._market_id&&r.market_name===row.market_name&&r.outcome_name===row.outcome_name&&JSON.stringify(r.contributor_outcome_ids)===JSON.stringify(row.contributor_outcome_ids));
 return matches.length===1&&row.period==null&&row.threshold==null?matches[0]:null;
}
export function esportsBaseline(row:EsportsRow,w=wire):{value:number;at:string}|null {
 if(w.eventID!==15322123||!w.verifiedStart||!Number.isFinite(Date.parse(w.start)))return null;
 const binding=esportsIdentity(row,w);if(!binding)return null;
 const pre=binding.observations.filter(o=>Number.isFinite(Date.parse(o.timestamp))&&Date.parse(o.timestamp)<Date.parse(w.start)).sort((a,b)=>Date.parse(a.timestamp)-Date.parse(b.timestamp));
 const last=pre.at(-1);if(!last||pre.filter(o=>o.timestamp===last.timestamp).length!==1||last.bookmaker!=='consensus'||typeof last.probability!=='number'||!Number.isFinite(last.probability)||last.probability<=0||last.probability>=1)return null;
 return {value:last.probability,at:last.timestamp};
}
export function esportsPregameNote(row:EsportsRow){const b=esportsBaseline(row);return b?'Last recorded before start · '+readerTime(b.at):undefined;}
export type EsportsQuestion<T>={kind:'roundMargin'|'matchWinner';rows:T[]};
export function esportsQuestion<T extends EsportsRow>(rows:T[]):EsportsQuestion<T>|null {
 if(!rows.length||rows.some(r=>!esportsIdentity(r))||new Set(rows.map(r=>r.key)).size!==rows.length)return null;
 if(rows.length===1&&rows[0]._market_id===63664403&&rows[0].market_name===handicapQuestion&&rows[0].outcome_name==='Nice Try')return {kind:'roundMargin',rows};
 if(rows.length===3&&rows.every(r=>r._market_id===63403921&&r.market_name===matchQuestion)&&['Nice Try','Flame Hard',handicapQuestion].every(n=>rows.filter(r=>r.outcome_name===n).length===1))return {kind:'matchWinner',rows};
 return null;
}
