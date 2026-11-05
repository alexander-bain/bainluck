import {catalogOutcomeIdentity} from './catalogSelection.ts';
import bindings from './combatOutcomeBindings.json' with {type:'json'};
import type {CatalogEvidenceRow} from './catalogPresentation';
export type CombatRow=CatalogEvidenceRow;
export type CombatQuestion<T>={id:number;label:string;question:string;subject?:string;round?:number;yes:T;no:T};
export function combatQuestions<T extends CombatRow>(rows:T[],family:'methods'|'rounds'|'fighterKO',eventID:number):CombatQuestion<T>[] {
 if(eventID!==bindings.eventID)return [];
 return bindings[family].flatMap(b=>{
  const matches=rows.filter(r=>r.source===bindings.source&&String(r._market_id)===String(b.id));
  if(matches.length!==2||matches.some(r=>r.market_name!==b.question||r.period!=null))return [];
  const yes=matches.filter(r=>r.outcome_name==='Yes'),no=matches.filter(r=>r.outcome_name==='No');
  return yes.length===1&&no.length===1?[{...b,yes:yes[0],no:no[0]}]:[];
 });
}
export function combatResult(row:CombatRow,other:CombatRow):'Won'|'Lost'|'Result unconfirmed'{
 const known=(r:CombatRow)=>r.resolution_source==='api_settlement'&&typeof r.is_winner==='boolean';
 if(!known(row)||(known(other)&&row.is_winner===other.is_winner))return 'Result unconfirmed';
 return row.is_winner?'Won':'Lost';
}

export function combatRoundKnown(subject:string,round:number){return bindings.rounds.some(b=>b.subject===subject&&b.round===round);}

/** A selected No keeps its own evidence; never leave a Yes ring highlighted. */
export function combatTileRow<T extends CombatRow>(question:CombatQuestion<T>,selected:T|null,visible:T[]):T {
 const sides=[question.yes,question.no];
 const exact=selected&&sides.find(r=>catalogOutcomeIdentity(r)===catalogOutcomeIdentity(selected));
 return exact||sides.find(r=>visible.some(v=>catalogOutcomeIdentity(v)===catalogOutcomeIdentity(r)))||question.yes;
}
