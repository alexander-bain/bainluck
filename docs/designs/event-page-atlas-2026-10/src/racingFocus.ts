import {racingRows} from './racingEvidence.ts';
import type {CatalogEvidenceRow} from './catalogPresentation';
import {catalogAnchor,resolveCatalogSelection,type CatalogAnchor} from './catalogSelection.ts';
import {groupCatalogRows} from './catalogGroups.ts';
export const racingFamilies=[
 {id:'podium',name:'Podium chances',title:'Who made the podium?',subtitle:'Antonelli finished third from a 48% pre-race chance.'},
 {id:'fastest',name:'Fastest lap',title:'A different kind of win',subtitle:'Leclerc took fastest lap from a 15.9% pre-race trade.'},
 {id:'matchup',name:'Driver matchups',title:'Who finished ahead?',subtitle:'Finishing order and market result stay separate.'}
] as const;
/** Shared original outcome identity makes story, expanded reader and catalog agree. */
export function racingFamilySelection(family:string,anchors:Record<string,CatalogAnchor<CatalogEvidenceRow>>){
 const all=racingRows.filter(r=>r.family===family),originals=all.map(r=>r.final);
 const groupKey=groupCatalogRows(originals)[0]?.key??'';
 const initial=(family==='podium'?all.find(r=>r.name==='Kimi Antonelli'):family==='fastest'?all.find(r=>r.result===true):all.find(r=>r.baseline))??all[0];
 const anchor=anchors[groupKey]??(initial?catalogAnchor(initial.final):null);
 const state=resolveCatalogSelection<CatalogEvidenceRow>(originals,anchor);
 // A wrong-family or ambiguous selection must not silently borrow another driver's chance.
 const selected=state.present?all.find(r=>r.key===state.row?.key):undefined;
 return {all,groupKey,selected,shown:all.slice(state.offset,state.offset+6)};
}
