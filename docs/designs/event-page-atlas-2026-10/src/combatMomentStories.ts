import atlas from './atlas.json' with {type:'json'};
import originalFinal from './combatOfficialFinal.json' with {type:'json'};
import originalPrices from './combatPregameEvidence.json' with {type:'json'};
import {combatPregame,combatResultConflict,type CombatPregameWire} from './combatPregame.ts';
import {qualifyCombatFinal,type CombatFinalWire} from './combatOfficialFinal.ts';
import {combatQuestions,type CombatRow} from './combatOutcome.ts';
import {durationQuestions} from './combatDuration.ts';
export const combatStoryFamilies=[{id:'methods',name:'Finish method'},{id:'rounds',name:'Fighter rounds'},{id:'fighterKO',name:'Knockout chances'},{id:'duration',name:'Fight length'}] as const;
export type CombatFamily=typeof combatStoryFamilies[number]['id'];
export type CombatMomentOrder={ids:CombatFamily[];reasons:Partial<Record<CombatFamily,string>>;selectedKeys:Partial<Record<CombatFamily,string>>};
const captured=atlas.events.find(event=>event.key==='mma')!;
const same=(a:unknown,b:unknown):boolean=>{
 if(a===b)return true;
 if(!a||!b||typeof a!=='object'||typeof b!=='object')return false;
 if(Array.isArray(a)||Array.isArray(b))return Array.isArray(a)&&Array.isArray(b)&&a.length===b.length&&a.every((value,i)=>same(value,b[i]));
 const x=a as Record<string,unknown>,y=b as Record<string,unknown>;
 return Object.keys(x).length===Object.keys(y).length&&Object.keys(x).every(key=>Object.hasOwn(y,key)&&same(x[key],y[key]));
};
/** Captured final ranking only. No terminal quotes, joint chances or inferred contract grades. */
export function combatMomentOrder(rows:CombatRow[],eventID:number,final:CombatFinalWire=originalFinal,prices:CombatPregameWire=originalPrices):CombatMomentOrder {
 const admitted=combatStoryFamilies.filter(f=>f.id==='duration'?durationQuestions(rows,eventID).length:combatQuestions(rows,f.id,eventID).length);
 const fallback:CombatMomentOrder={ids:admitted.map(f=>f.id),reasons:{},selectedKeys:{}};
 if(typeof captured.detail.away_team!=='string'||typeof captured.detail.commence_time!=='string')return fallback;
 const bout={event_id:eventID,home_team:captured.detail.home_team,away_team:captured.detail.away_team,commence_time:captured.detail.commence_time};
 if(eventID!==15318681||!qualifyCombatFinal(final,bout)||!same(final,originalFinal)||!same(prices,originalPrices)||rows.length!==captured.rows.length||!captured.rows.every(original=>rows.filter(row=>row.key===original.key&&same(row,original)).length===1))return fallback;
 const picks={fighterKO:[63900810,'Yes',.125],rounds:[63900818,'Yes',.11],duration:[63786880,'Yes',.325],methods:[63786874,'Yes',.55]} as const;
 const selectedKeys:Partial<Record<CombatFamily,string>>={};
 for(const family of Object.keys(picks) as CombatFamily[]){
  const [market,side,chance]=picks[family],matches=rows.filter(row=>String(row._market_id)===String(market)&&row.outcome_name===side);
  if(matches.length!==1||combatPregame(matches[0],prices)?.value!==chance||combatResultConflict(matches[0],prices))return fallback;
  selectedKeys[family]=matches[0].key;
 }
 return {ids:['fighterKO','rounds','duration','methods'],selectedKeys,reasons:{
  fighterKO:'Kopylov’s KO/TKO win had a 12.5% pre-match chance.',
  rounds:'Kopylov winning in Round 1 had an 11% pre-match chance.',
  duration:'Ending before Round 2 had a 32.5% pre-match chance.',
  methods:'A KO/TKO finish for either fighter had a 55% pre-match chance.'
 }};
}
