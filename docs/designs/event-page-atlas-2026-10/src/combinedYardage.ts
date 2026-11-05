import wire from './markets.json' with {type:'json'};
import flags from './finalCatalogFlags.json' with {type:'json'};
export type CombinedRow=(typeof wire)[number];
export const combinedNames=["D'Andre Swift",'Saquon Barkley','Kyle Monangai'];
export const combinedMarketID=62481365;
const titles={combined:'Philadelphia vs Chicago: Rushing + Receiving Yards',rush:'Philadelphia vs Chicago: Rushing Yards',receive:'Philadelphia vs Chicago: Receiving Yards'};
const ids={combined:62481365,rush:62146484,receive:62146482};
const finite=(v:unknown):v is number=>typeof v==='number'&&Number.isFinite(v);
export function combinedRows(rows:readonly CombinedRow[]=wire){return rows.filter(r=>r.source==='kalshi'&&r._market_id===ids.combined&&r.market_name===titles.combined&&r.period==null&&r.category==='player_props'&&r._inverted===false)}
export function combinedProfile(name:string,phase:string,rows:readonly CombinedRow[]=wire){
 if(!combinedNames.includes(name))return null;
 const matches=combinedRows(rows).filter(r=>r.outcome_name.startsWith(name+': '));
 if(!matches.length||matches.some(r=>r.player_team!==matches[0].player_team||r.observed_at!==matches[0].observed_at))return null;
 if(matches.some(r=>!finite(r.threshold)||!Number.isSafeInteger(r.threshold)||r.threshold<0||r.outcome_name!==name+': '+r.threshold+'+')||new Set(matches.map(r=>r.threshold)).size!==matches.length)return null;
 const actuals=matches.map(r=>r.actual),total=phase==='Final'&&actuals.every(v=>finite(v)&&v===actuals[0])?actuals[0] as number:null;
 function component(kind:'rush'|'receive'){
  const parts=rows.filter(r=>r.source==='kalshi'&&r._market_id===ids[kind]&&r.market_name===titles[kind]&&r.category==='player_props'&&r.period==null&&r._inverted===false&&r.outcome_name.startsWith(name+': '));
  if(!parts.length||parts.some(r=>r.player_team!==matches[0].player_team||r.observed_at!==matches[0].observed_at||!finite(r.actual)||r.actual!==parts[0].actual))return null;
  return parts[0].actual as number;
 }
 const rush=phase==='Final'?component('rush'):null,receive=phase==='Final'?component('receive'):null;
 const decomposition=total!==null&&rush!==null&&receive!==null&&Math.abs(rush+receive-total)<1e-9?{rush,receive}:null;
 const points=matches.sort((a,b)=>a.threshold!-b.threshold!).map(row=>({row,threshold:row.threshold!,baseline:finite(row.pregame_mark)&&row.pregame_mark>=0&&row.pregame_mark<=1?row.pregame_mark:null}));
 const defaultPoint=total===null?points[0]:points.find(p=>p.threshold>total)??points.at(-1)!;
 return {name,team:matches[0].player_team==='home'?'Bears':'Eagles',points,total,decomposition,defaultKey:defaultPoint.row.row_key,clock:matches[0].observed_at};
}
export function combinedResult(row:CombinedRow,phase:string){
 if(phase!=='Final')return null;
 const conflict=flags[row.row_key as keyof typeof flags]===true;
 return !conflict&&row.resolution_source==='api_settlement'&&typeof row.is_winner==='boolean'?(row.is_winner?'Happened':'Didn’t happen'):'Result unconfirmed';
}
export function combinedRank(phase:string){return combinedNames.map(name=>{
 const profile=combinedProfile(name,phase)!;
 const scores=profile.points.filter(p=>p.baseline!==null).map(p=>phase==='Final'?(profile.total===null?-1:profile.total>=p.threshold?1-p.baseline!:p.baseline!):p.baseline!);
 return {id:name,score:Math.max(-1,...scores)};
}).sort((a,b)=>b.score-a.score||a.id.localeCompare(b.id)).map(x=>x.id)}
