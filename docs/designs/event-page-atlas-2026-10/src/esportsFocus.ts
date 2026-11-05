import {esportsQuestion,type EsportsRow} from './esportsEvidence.ts';
import {groupCatalogRows} from './catalogGroups.ts';
import {catalogOutcomeIdentity} from './catalogSelection.ts';
export const esportsFamilies=[{id:'winner',marketID:63403921,name:'Match winner',title:'Who wins the match?'},{id:'margin',marketID:63664403,name:'Map 1 winning margin',title:'Nice Try by 7+ rounds'}] as const;
export type EsportsFamily=typeof esportsFamilies[number]['id'];
/** Source-scoped groups, including the original nested handicap row. */
export function esportsFocusGroups<T extends EsportsRow>(rows:T[]){
 return esportsFamilies.flatMap(f=>{
  const group=rows.filter(r=>r._market_id===f.marketID),data=esportsQuestion(group);
  if(!data)return [];
  const groups=groupCatalogRows(group);
  if(groups.length!==1||new Set(group.map(catalogOutcomeIdentity)).size!==group.length)return [];
  return [{...f,rows:group,data,groupKey:groups[0].key}];
 });
}
