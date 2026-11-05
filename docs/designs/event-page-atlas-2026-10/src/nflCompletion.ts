import {eventReaderTime} from './eventReaderTime.ts';
import bindings from './nflCompletionBindings.json' with {type:'json'};
import {nflBaselineRow,nflFinalRows,nflActual,nflAdmitted,nflCaptures,type NFLRow} from './nflReconciliation.ts';
import {catalogPresentation,type CatalogEvidenceRow} from './catalogPresentation.ts';
import type {LiveMilestone,LivePlayerProfile} from './livePlayerEvidence';
const stable=(v:unknown):string=>JSON.stringify(v,(_,x)=>x&&typeof x==='object'&&!Array.isArray(x)?Object.fromEntries(Object.keys(x).sort().map(k=>[k,x[k]])):x);
export function completionPregame(row:CatalogEvidenceRow){
 const original=nflBaselineRow(row),match=bindings.filter(b=>b.original.key===original.key&&stable(b.original)===stable(original));
 return match.length===1?{value:match[0].point.baseline,at:match[0].point.baselineAt}:null;
}
export function completionPregameNote(row:CatalogEvidenceRow){const b=completionPregame(row);return b?`Pinned before play · ${eventReaderTime.full(b.at)}`:undefined}
function pointIdentity(p:LiveMilestone){return stable([p.key,p.source,p.marketID,p.marketName,p.outcomeName,p.count])}
export function completionFinal(profile:LivePlayerProfile,point:LiveMilestone,rows:NFLRow[]=nflFinalRows){
 const match=bindings.filter(b=>b.profile.name===profile.name&&b.profile.statKey===profile.statKey&&b.profile.unit===profile.unit&&b.profile.period===profile.period&&pointIdentity(b.point)===pointIdentity(point));
 if(match.length!==1)return {actual:null,result:'Result unconfirmed',capturedAt:null,row:null};
 const all=bindings.filter(b=>b.profile.name===profile.name).map(b=>rows.filter(r=>r.key===b.original.key&&nflAdmitted(r)));
 const values=all.map(rs=>rs.length===1?nflActual(rs[0]):null),actual=values.length&&values.every(v=>v!==null&&v===values[0])?values[0]:null;
 const selected=rows.filter(r=>r.key===match[0].original.key&&nflAdmitted(r));
 const row=selected.length===1?selected[0]:null;
 return {actual,result:row?catalogPresentation(row,{status:'completed',qualityHold:false,mode:'stale'}).label:'Result unconfirmed',capturedAt:actual!==null?nflCaptures.actualCapturedAt:null,row};
}
