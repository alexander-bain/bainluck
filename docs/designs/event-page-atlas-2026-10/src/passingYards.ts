import wire from './markets.json' with {type:'json'};
import flags from './finalCatalogFlags.json' with {type:'json'};
import {nflOriginalBaseline} from './nflOriginalBaseline.ts';
export type PassingRow=(typeof wire)[number];
export const passingID='passing:quarterbacks' as const;
export const passingNames=['Case Keenum','Jalen Hurts'] as const;
export const passingThresholds=[150,175,200,225,250,275,300,325,350];
export const passingMarketID=62146479;
const keys=[['player_props:342','player_props:344','player_props:346','player_props:348','player_props:350','player_props:352','player_props:354','player_props:356','player_props:357'],['player_props:360','player_props:362','player_props:364','player_props:366','player_props:368','player_props:370','player_props:372','player_props:374','player_props:375']];
const finite=(v:unknown):v is number=>typeof v==='number'&&Number.isFinite(v);
/** One known full-game Kalshi family, inside the retained event envelope.
 * Unrelated rows never fill a missing baseline, actual or result. */
export function passingProfiles(phase:string,rows:readonly PassingRow[]=wire,eventID=14780549){
 if(eventID!==14780549||!['Before','During','Final'].includes(phase))return null;
 const profiles=passingNames.map((name,i)=>{
  const originals=keys[i].map((key,j)=>{
   const matches=rows.filter(r=>r.row_key===key);
   if(matches.length!==1)return null;
   const row=matches[0],threshold=passingThresholds[j];
   return row.source==='kalshi'&&row._market_id===passingMarketID&&row.market_name==='Philadelphia vs Chicago: Passing Yards'&&row.outcome_name===name+': '+threshold+'+'&&row.category==='player_props'&&row.period==null&&row._inverted===false&&row.threshold===threshold&&row.player_team===(i===0?'home':'away')?row:null;
  });
  if(originals.some(r=>r===null))return null;
  const admitted=originals as PassingRow[];
  if(admitted.some(r=>r.observed_at!==admitted[0].observed_at))return null;
  const actuals=admitted.map(r=>r.actual),actual=phase==='Final'&&actuals.every(v=>finite(v)&&v===actuals[0])?actuals[0] as number:null;
  return {name,short:i===0?'Keenum':'Hurts',team:i===0?'Bears':'Eagles',actual,
   points:admitted.map(row=>({row,threshold:row.threshold!,baseline:nflOriginalBaseline(row).value})),
   observedAt:phase==='Final'?admitted[0].observed_at:null};
 });
 if(profiles.some(p=>p===null))return null;
 return profiles as NonNullable<typeof profiles[number]>[];
}
export function passingOwns(row:PassingRow){return passingProfiles('Before')?.some(p=>p.points.some(q=>
 q.row.row_key===row.row_key&&q.row._market_id===row._market_id&&q.row.outcome_name===row.outcome_name&&
 q.row.source===row.source&&q.row.market_name===row.market_name&&q.row.threshold===row.threshold&&
 q.row.category===row.category&&row.period==null&&row._inverted===false&&q.row.player_team===row.player_team))??false}
export function passingResult(row:PassingRow,phase:string){
 if(phase!=='Final')return null;
 return flags[row.row_key as keyof typeof flags]!==true&&row.resolution_source==='api_settlement'&&typeof row.is_winner==='boolean'?(row.is_winner?'Hit':'Missed'):'Result unconfirmed';
}
export function passingComparison(actual:number|null,threshold:number){return actual===null?'Actual unavailable':actual>=threshold?`${actual-threshold} yards beyond ${threshold}+`:`${threshold-actual} yards short of ${threshold}+`}
export function passingStory(phase:string){
 const profiles=passingProfiles(phase);if(!profiles)return null;
 const comparisons=profiles.flatMap(p=>p.points.flatMap(q=>q.baseline===null?[]:phase!=='Final'?[q.baseline]:p.actual===null?[]:[p.actual>=q.threshold?1-q.baseline:q.baseline]));
 return {id:passingID,family:'passing' as const,name:'Quarterbacks · passing yards',score:comparisons.length?Math.max(...comparisons):null,originals:profiles.flatMap(p=>p.points.map(q=>q.row.row_key))};
}
