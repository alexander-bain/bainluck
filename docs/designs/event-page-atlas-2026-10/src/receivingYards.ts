import wire from './markets.json' with {type:'json'};
import flags from './finalCatalogFlags.json' with {type:'json'};
import {nflOriginalBaseline} from './nflOriginalBaseline.ts';
export type ReceivingRow=(typeof wire)[number];
export const receivingID='receiving:comparison' as const;
export const receivingThresholds=[15,25,40,50,60,70,80,90,100,110,120,130,140,150,160];
export const receivingMarketID=62146482;
const definitions=[{name:'Kalif Raymond',short:'Raymond',team:'Bears',side:'home',keys:['player_props:443','player_props:446','player_props:450','player_props:452','player_props:453','player_props:454','player_props:455'],thresholds:[15,25,40,50,60,70,80]},{name:'DeVonta Smith',short:'Smith',team:'Eagles',side:'away',keys:['player_props:14','player_props:16','player_props:18','player_props:20','player_props:22','player_props:24','player_props:26','player_props:28','player_props:29','player_props:30','player_props:31','player_props:32','player_props:33'],thresholds:[40,50,60,70,80,90,100,110,120,130,140,150,160]}];
const finite=(v:unknown):v is number=>typeof v==='number'&&Number.isFinite(v);
export function receivingProfiles(phase:string,rows:readonly ReceivingRow[]=wire,eventID=14780549){
 if(eventID!==14780549||!['Before','During','Final'].includes(phase))return null;
 const family=rows.filter(r=>r._market_id===receivingMarketID);
 if(definitions.some(d=>family.filter(r=>r.outcome_name.startsWith(d.name+': ')).length!==d.keys.length))return null;
 const profiles=definitions.map(d=>{
  const points=d.keys.map((key,index)=>{
   const matches=rows.filter(r=>r.row_key===key);if(matches.length!==1)return null;
   const row=matches[0],needed=d.thresholds[index];
   if(row.source!=='kalshi'||row._market_id!==receivingMarketID||row.market_name!=='Philadelphia vs Chicago: Receiving Yards'||row.outcome_name!==d.name+': '+needed+'+'||row.category!=='player_props'||row.period!=null||row._inverted!==false||row.threshold!==needed||row.player_team!==d.side)return null;
   return {row,needed,baseline:nflOriginalBaseline(row).value};
  });
  if(points.some(q=>q===null))return null;
  const admitted=points.filter(q=>q!==null);if(admitted.some(q=>q.row.observed_at!==admitted[0].row.observed_at))return null;
  const a=admitted[0].row.actual;
  const actual=phase==='Final'&&finite(a)&&Number.isSafeInteger(a)&&admitted.every(q=>q.row.actual===a)?a:null;
  return {...d,points:admitted,actual,observedAt:phase==='Final'?admitted[0].row.observed_at:null};
 });
 if(profiles.some(p=>p===null))return null;
 return profiles.filter(p=>p!==null);
}
export function receivingOwns(row:ReceivingRow){return receivingProfiles('Before')?.some(p=>p.points.some(q=>q.row.row_key===row.row_key&&q.row._market_id===row._market_id&&q.row.source===row.source&&q.row.market_name===row.market_name&&q.row.outcome_name===row.outcome_name&&q.row.threshold===row.threshold&&q.row.player_team===row.player_team&&q.row.category===row.category&&row.period==null&&row._inverted===false))??false}
export function receivingResult(row:ReceivingRow,phase:string){if(phase!=='Final')return null;return flags[row.row_key as keyof typeof flags]!==true&&row.resolution_source==='api_settlement'&&typeof row.is_winner==='boolean'?(row.is_winner?'Hit':'Missed'):'Result unconfirmed'}
export function receivingComparison(actual:number|null,needed:number){return actual===null?'Actual unavailable':actual===needed?'Reached this milestone':actual>needed?`${actual-needed} yards beyond ${needed}+`:`${needed-actual} yards short of ${needed}+`}

export function receivingStory(phase:string){const profiles=receivingProfiles(phase);if(!profiles)return null;const scores=profiles.flatMap(p=>p.points.flatMap(q=>q.baseline===null?[]:phase!=='Final'?[q.baseline]:p.actual===null?[]:[p.actual>=q.needed?1-q.baseline:q.baseline]));return {id:receivingID,family:'receiving' as const,name:'Receivers · yards',score:scores.length?Math.max(...scores):null,originals:profiles.flatMap(p=>p.points.map(q=>q.row.row_key))}}
