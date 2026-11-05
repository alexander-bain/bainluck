import capture from './liveTennis.json' with {type:'json'};
import {tennisFocusCards,type TennisFocusKind} from './tennisFocus.ts';
/** A single captured match state, not live AI ranking or invented score progression. */
export function tennisMomentOrder(wire=capture):{ids:TennisFocusKind[];reasons:Partial<Record<TennisFocusKind,string>>}{
 const fallback={ids:tennisFocusCards.map(c=>c.id),reasons:{}};
 const winner=wire.rows.find(r=>r.outcomeID===245152776),ruledOut=wire.rows.find(r=>r.outcomeID===245059338);
 if(wire.eventID!==15327807||wire.homeSets!==0||wire.awaySets!==1||wire.sets[0]?.[0]!==5||wire.sets[0]?.[1]!==7||wire.sets[1]?.[0]!==3||wire.sets[1]?.[1]!==3||wire.scoreTotal!==18||wire.homeGames!==8||wire.awayGames!==10||!winner?.baseline||winner.baseline.value!==.285||!ruledOut?.impossible||ruledOut.baseline?.value!==.56)return fallback;
 return {ids:['set','exact','totals','handicaps'],reasons:{
  set:'Zandschulp won set 1 after a 28.5% pre-match chance.',
  exact:'Fils 2–0 had a 56% pre-match chance. That finish is now ruled out.',
  totals:'18 games played; the original total-game markets remain unresolved.',
  handicaps:'Zandschulp has won a set and leads by 2 games.'
 }};
}
