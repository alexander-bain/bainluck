import sourceRows from './markets.json' with {type:'json'};
import flags from './finalCatalogFlags.json' with {type:'json'};
export type TeamMilestoneRow=(typeof sourceRows)[number];
export const teamMilestoneKinds=['sacks','field-goals'] as const;
export type TeamMilestoneKind=(typeof teamMilestoneKinds)[number];
export const teamMilestoneDefinitions={
 sacks:{market:62481362,title:'Philadelphia vs Chicago: Team Sacks',name:'Quarterback pressure',unit:'sacks',thresholds:[2,3,4,5,6]},
 'field-goals':{market:62436325,title:'Philadelphia vs Chicago: Team Field Goals',name:'The kicking game',unit:'field goals',thresholds:[1,2,3,4]},
} as const;
const teams=['Chicago','Philadelphia'] as const;
const finite=(v:unknown):v is number=>typeof v==='number'&&Number.isFinite(v);
export function teamMilestoneResult(row:TeamMilestoneRow,phase:string){
 if(phase!=='Final')return null;
 if(flags[row.row_key as keyof typeof flags]===true||row.resolution_source!=='api_settlement'||typeof row.is_winner!=='boolean')return 'Unconfirmed';
 return row.is_winner?'Hit':'Missed';
}
export function teamMilestones(kind:TeamMilestoneKind,phase:string,rows:readonly TeamMilestoneRow[]=sourceRows){
 const definition=teamMilestoneDefinitions[kind];
 const own=rows.filter(r=>r._market_id===definition.market&&r.source==='kalshi'&&r.market_name===definition.title&&r.category==='player_props'&&r.period==null&&r._inverted===false);
 if(own.length!==definition.thresholds.length*2||new Set(own.map(r=>r.row_key)).size!==own.length||own.some(r=>r.observed_at!==own[0].observed_at))return null;
 const profiles=teams.map(team=>{
  const points=definition.thresholds.map(threshold=>{
   const matching=own.filter(r=>r.outcome_name===team+': '+threshold+'+'&&r.threshold===threshold);
   if(matching.length!==1)return null;
   const row=matching[0],baseline=finite(row.pregame_mark)&&row.pregame_mark>=0&&row.pregame_mark<=1?row.pregame_mark:null;
   return {threshold,row,baseline,result:teamMilestoneResult(row,phase)};
  });
  if(points.some(p=>p===null))return null;
  const complete=points.filter(p=>p!==null),a=complete[0].row.actual;
  const actual=phase==='Final'&&finite(a)&&a>=0&&Number.isSafeInteger(a)&&complete.every(p=>p.row.actual===a)?a:null;
  return {team,name:team==='Chicago'?'Bears':'Eagles',points:complete,actual};
 });
 if(profiles.some(p=>p===null))return null;
 return {kind,definition,profiles:profiles.filter(p=>p!==null),clock:phase==='Final'?own[0].observed_at:null};
}
export function teamMilestoneRank(phase:string){
 return teamMilestoneKinds.map(kind=>{
  const profile=teamMilestones(kind,phase);
  const scores=profile?.profiles.flatMap(p=>p.points.flatMap(q=>q.baseline===null?[]:phase!=='Final'?[q.baseline]:q.result==='Hit'?[1-q.baseline]:q.result==='Missed'?[q.baseline]:[]))??[];
  return {id:kind,score:Math.max(-1,...scores)};
 }).sort((a,b)=>b.score-a.score||a.id.localeCompare(b.id)).map(x=>x.id);
}
export function teamMilestoneKindFor(row:TeamMilestoneRow){return teamMilestoneKinds.find(k=>teamMilestoneDefinitions[k].market===row._market_id&&teamMilestones(k,'Final')?.profiles.some(p=>p.points.some(q=>q.row.row_key===row.row_key)))??null}
