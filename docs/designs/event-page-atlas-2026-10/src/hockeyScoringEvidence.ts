import capture from './hockeyScoring.json' with {type:'json'};
import {catalogOutcomeIdentity} from './catalogSelection.ts';
import {catalogPresentation,type CatalogEvidenceRow} from './catalogPresentation.ts';
export type HockeyScoringKind='first'|'goals';
export type HockeyScoringRow=CatalogEvidenceRow & {actual?:unknown;player_team?:unknown};
const bindings=capture.map(family=>({...family,originals:family.group.rows.map(row=>({key:row.id,identity:catalogOutcomeIdentity(JSON.parse(row.original))}))}));
/** Bind the supplied player and predicate identities; player_props/1+ alone is not a stat type. */
export function hockeyScoringRows<T extends HockeyScoringRow>(rows:T[],eventID:unknown,kind:HockeyScoringKind):T[]{
 const family=bindings.find(f=>f.id===kind&&f.eventID===eventID);if(!family)return [];
 const admitted=rows.filter(row=>(kind!=='goals'||row._inverted===false)&&family.originals.some(original=>row.key===original.key&&catalogOutcomeIdentity(row)===original.identity));
 return admitted.filter(row=>admitted.filter(other=>catalogOutcomeIdentity(other)===catalogOutcomeIdentity(row)).length===1);
}
export function hockeyScoringRecord<T extends HockeyScoringRow>(row:T,kind:HockeyScoringKind){
 const family=bindings.find(f=>f.id===kind)!;
 if(!hockeyScoringRows([row],family.eventID,kind).length)return null;
 const original=family.records.find(record=>record.id===row.key)!;
 const actual=kind==='goals'&&typeof row.actual==='number'&&Number.isFinite(row.actual)&&Number.isInteger(row.actual)&&row.actual>=0?row.actual:null;
 const result=catalogPresentation(row,{status:'completed',qualityHold:false,mode:'captured'}).label;
 return {id:row.key,player:original.player,contributor:original.contributor,actual,team:row.player_team==='home'?'Minnesota':row.player_team==='away'?'Boston':null,result,row};
}
export function hockeyGoalLabel(actual:number|null){return actual===null?'Goals unavailable':`${actual} ${actual===1?'goal':'goals'}`;}
