import {ceremonyCapture,awardSeries,awardComparison,type AwardPhase,type AwardCapture} from './ceremonyEvidence.ts';
import {probabilityLabel as pct} from './probabilityLabel.ts';
export type CeremonyStoryID='picture'|'actor';
export function ceremonyStoryRank(phase:AwardPhase,capture:AwardCapture=ceremonyCapture){
 return ([{id:'picture' as const,race:'50251'},{id:'actor' as const,race:'50282'}]).map(({id,race})=>{
  const rows=awardSeries(race,phase,'all',capture);
  const candidates=rows.flatMap(row=>{
   const before=row.baseline,last=phase==='before'?row.last:awardComparison(row,phase,capture.baselineCutoff).later;if(!before||!last)return [];
   return [{name:row.market.name,before,last,score:phase==='before'?before.p:Math.abs(last.p-before.p)}];
  }).sort((a,b)=>b.score-a.score||a.name.localeCompare(b.name));
  const lead=candidates[0];
  return {id,score:lead?.score??null,support:lead?{name:lead.name,before:lead.before,last:lead.last}:null,
   reason:lead?(phase==='before'?`${lead.name} · ${pct(lead.before.p)} before awards day`:`${lead.name} · ${pct(lead.before.p)} before day → ${pct(lead.last.p)} last recorded`):'Dated context · comparison unavailable'};
 }).sort((a,b)=>(b.score??-1)-(a.score??-1)||a.id.localeCompare(b.id));
}
