import {soccerCaptures,soccerIdentity,type SoccerRow} from './soccerReconciliation.ts';
import type {CatalogEvidenceRow} from './catalogPresentation.ts';
export type PlayerTargetRow=CatalogEvidenceRow&{category?:unknown;source_file?:unknown;actual?:unknown};
export type PlayerTarget<T>={id:number;player:string;count:number;unit:string;rows:T[]};
export type PlayerTargetFamily<T>={id:string;title:string;unit:string;targets:PlayerTarget<T>[]};
const bindings:[number,string,number,string][]=[
 [65362198,'Sorba Thomas',1,'assists'],[65362199,'Kiernan Dewsbury Hall',1,'assists'],[65362200,'Ainsley Maitland-Niles',1,'assists'],
 [65362201,'Sorba Thomas',1,'goals + assists'],[65355442,'Kiernan Dewsbury Hall',1,'goals + assists'],[65362206,'Ainsley Maitland-Niles',1,'goals + assists'],[65362202,'Joe Gelhardt',1,'goals + assists'],[65362203,'Thierno Barry',1,'goals + assists'],[65362205,'Kiernan Dewsbury Hall',2,'goals + assists'],
 [65355461,'Kostas Tzolakis',3,'saves'],[65355462,'Jordan Pickford',1,'saves'],[65355460,'Kostas Tzolakis',2,'saves'],[65355459,'Kostas Tzolakis',1,'saves'],
];
/** A fixed, source-bound same-stat view. Every target and both original sides stay independent. */
export function soccerPlayerTargets<T extends PlayerTargetRow>(rows:T[],status:string):PlayerTargetFamily<T>[] {
 if(status!=='completed')return [];
 return ['assists','goals + assists','saves'].flatMap(unit=>{
  const expected=bindings.filter(b=>b[3]===unit),targets:PlayerTarget<T>[]=[];
  for(const [id,player,count] of expected){
   const pair=rows.filter(r=>r._market_id===id);
   if(!pair.every(r=>soccerCaptures.latest.filter(x=>soccerIdentity(x as SoccerRow)===soccerIdentity(r as unknown as SoccerRow)).length===1)||pair.length!==2||new Set(pair.map(r=>r.outcome_name)).size!==2||!pair.every(r=>r.source==='polymarket'&&r.source_file==='soccer-final-15311089-game-markets.json'&&r.category==='player_props'&&r.market_name===`${player}: ${count}+ ${unit}`&&r.threshold===count&&r.period==null&&['Yes','No'].includes(r.outcome_name)&&r._inverted===(r.outcome_name==='No')&&Array.isArray(r.contributor_outcome_ids)&&r.contributor_outcome_ids.length===1))return [];
   targets.push({id,player,count,unit,rows:pair});
  }
  return [{id:unit,title:unit==='assists'?'Who set up a goal?':unit==='saves'?'The save targets':'Goals and assists together',unit,targets}];
 });
}
