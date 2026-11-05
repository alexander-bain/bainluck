import atlas from './atlas.json' with {type:'json'};
import headers from './finalHeaders.json' with {type:'json'};
import {baseballStoryFamilies} from './baseballCardContext.ts';

export type BaseballFamily=typeof baseballStoryFamilies[number]['id'];
type Original={key:string;[key:string]:unknown};
type Order={ids:BaseballFamily[];reasons:Partial<Record<BaseballFamily,string>>;selectedStrikeoutKey:string|null};
const captured=atlas.events.find(event=>event.key==='mlb')!;
const expectedHeader=headers.find(header=>header.id==='mlb')!;
export const baseballHomeRunKeys=['mlb-15321836-game-markets.json:player_props:32','mlb-15321836-game-markets.json:player_props:38'] as const;
const same=(a:unknown,b:unknown):boolean=>{
 if(a===b)return true;
 if(!a||!b||typeof a!=='object'||typeof b!=='object')return false;
 if(Array.isArray(a)||Array.isArray(b))return Array.isArray(a)&&Array.isArray(b)&&a.length===b.length&&a.every((value,i)=>same(value,b[i]));
 const left=a as Record<string,unknown>,right=b as Record<string,unknown>;
 return Object.keys(left).length===Object.keys(right).length&&Object.keys(left).every(key=>Object.hasOwn(right,key)&&same(left[key],right[key]));
};
/** This retained-game order never turns terminal quotes into current chances or joint probabilities. */
export function baseballMomentOrder(rows:Original[],eventID:unknown,header=expectedHeader,comparison=atlas.player_comparison):Order {
 const fallback:Order={ids:baseballStoryFamilies.map(card=>card.id),reasons:{},selectedStrikeoutKey:null};
 if(eventID!==15321836||header.id!=='mlb'||header.home!=='Houston Astros'||header.away!=='Chicago White Sox'||header.homeScore!==3||header.awayScore!==7||header.winner!=='away'||header.scoreAt!==expectedHeader.scoreAt)return fallback;
 for(const key of baseballHomeRunKeys){
  const original=captured.rows.find(row=>row.key===key),matches=rows.filter(row=>row.key===key);
  if(!original||matches.length!==1||!same(matches[0],original))return fallback;
 }
 const baseline=comparison.baselines.find(row=>row.threshold===5.5);
 if(typeof captured.detail.commence_time!=='string'||!same(comparison,atlas.player_comparison)||comparison.final_actual!==2||comparison.name!=='Hunter Brown'||!baseline||baseline.pregame_mark!==.57||!Number.isFinite(Date.parse(baseline.observed_at))||Date.parse(baseline.observed_at)>=Date.parse(captured.detail.commence_time))return fallback;
 return {ids:['home-runs','strikeouts','totals','extra','series'],selectedStrikeoutKey:baseline.key,reasons:{
  'home-runs':'Peña and Altuve each homered after pregame chances of 14.5% and 10%.',
  strikeouts:'Brown finished with two strikeouts. Six or more had a 57% pregame chance.',
  totals:'Ten runs in the final. Explore which total lines won.',
  extra:'An earlier outlook on extra innings; the inning result is unavailable.',
  series:'A separate series outcome, with its own pre-series chances.'
 }};
}
