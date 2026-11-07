import {catalogOutcomeIdentity} from './catalogSelection.ts';
import type {CombatRow} from './combatOutcome';
export const durationBindings=[
 {id:63786877,question:'O/U 0.5 Rounds',label:'Over ½ round',sides:['Over'],threshold:0.5,start:0.5,end:3},
 {id:63254895,question:'O/U 1.5 Rounds',label:'Under 1½ rounds',sides:['Under'],threshold:1.5,start:0,end:1.5},
 {id:63455521,question:'O/U 2.5 Rounds',label:'Under 2½ rounds',sides:['Under'],threshold:2.5,start:0,end:2.5},
 {id:63786880,question:'Will the fight end before Round 2?',label:'Before Round 2',sides:['Yes','No'],start:0,end:1},
 {id:63786881,question:'Will the fight end before Round 3?',label:'Before Round 3',sides:['Yes','No'],start:0,end:2},
 {id:63254894,question:'Fight to Go the Distance?',label:'Go the distance',sides:['Yes','No'],start:0,end:3},
] as const;
export type DurationQuestion<T>={id:number;question:string;label:string;start:number;end:number;rows:T[]};
export function durationQuestions<T extends CombatRow>(rows:T[],eventID:number,leadKey?:string):DurationQuestion<T>[] {
 if(eventID!==15318681)return [];
 const questions=durationBindings.flatMap(b=>{
  const matches=rows.filter(r=>r.source==='polymarket'&&String(r._market_id)===String(b.id));
  if(matches.length!==b.sides.length||matches.some(r=>r.market_name!==b.question||r.period!=null||('threshold' in b?r.threshold!==b.threshold:r.threshold!=null)))return [];
  const ordered=b.sides.map(side=>matches.filter(r=>r.outcome_name===side));
  return ordered.every(side=>side.length===1)?[{...b,rows:ordered.map(side=>side[0])}]:[];
 });
 const lead=questions.find(q=>q.rows.some(row=>row.key===leadKey));
 return lead?[lead,...questions.filter(q=>q!==lead)]:questions;
}
export function durationResult<T extends CombatRow>(row:T,rows:T[]):string {
 const known=(r:T)=>r.resolution_source==='api_settlement'&&typeof r.is_winner==='boolean'&&r.result_unconfirmed!==true&&r.settlement_kind!=='fair_value';
 if(!known(row)||rows.some(r=>r!==row&&known(r)&&r.is_winner===row.is_winner))return 'Result unconfirmed';
 return row.is_winner?'Won':'Lost';
}

/** Keep the exact selected duration side in its tile, including when filtered out. */
export function durationTileRow<T extends CombatRow>(q:DurationQuestion<T>,selected:T|null,visible:T[]):T {
 const exact=selected&&q.rows.find(r=>catalogOutcomeIdentity(r)===catalogOutcomeIdentity(selected));
 return exact||q.rows.find(r=>visible.some(v=>catalogOutcomeIdentity(v)===catalogOutcomeIdentity(r)))||q.rows[0];
}
