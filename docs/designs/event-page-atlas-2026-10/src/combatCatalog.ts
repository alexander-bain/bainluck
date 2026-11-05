import {durationQuestions} from './combatDuration.ts';
import {combatQuestions,type CombatRow} from './combatOutcome.ts';
import type {CatalogEntry} from './catalogPageSession';
export type CombatCatalogEntry<T> = CatalogEntry<T> & {combatFamily?:'methods'|'rounds'|'fighterKO'|'duration'};
/** Presentation grouping only: never drops rows, merges original identities, or synthesizes prices. */
export function combatCatalogEntries<T extends CombatRow>(entries:CatalogEntry<T>[],eventID:number):CombatCatalogEntry<T>[] {
 if(eventID!==15318681)return entries;
 const membership=new Map<string,'methods'|'rounds'|'fighterKO'|'duration'>();
 for(const family of ['methods','rounds','fighterKO','duration'] as const){
  for(const e of entries){const q=family==='duration'?durationQuestions(e.rows,eventID):combatQuestions(e.rows,family,eventID);if(q.length===1&&(family==='duration'||e.rows.length===2))membership.set(e.key,family);}
 }
 const emitted=new Set<string>();const result:CombatCatalogEntry<T>[]=[];
 for(const e of entries){const family=membership.get(e.key);if(!family){result.push(e);continue;}if(emitted.has(family))continue;emitted.add(family);
  const members=entries.filter(g=>membership.get(g.key)===family),all=members.flatMap(g=>g.rows),questions=family==='duration'?durationQuestions(all,eventID):combatQuestions(all,family,eventID);
  // Duplicate predicates across source groups are ambiguous: preserve original groups.
  if(questions.length!==members.length){result.push(...members);continue;}
  result.push({key:'combat:'+family,rows:questions.flatMap(q=>'rows' in q?q.rows:[q.yes,q.no]),absentFromUpdate:members.some(g=>g.absentFromUpdate),combatFamily:family});
 }
 return result;
}
