import {golfRows,golfFeatured} from './golfEvidence.ts';
import {placementRows,placementDefault,placementFor} from './placementEvidence.ts';
import type {CatalogEvidenceRow} from './catalogPresentation';
import {catalogAnchor,resolveCatalogSelection,type CatalogAnchor} from './catalogSelection.ts';
import {groupCatalogRows} from './catalogGroups.ts';
export const placementSelectionKey='golf:placement:selected-original';
export const golfGroupKey=groupCatalogRows(golfRows.map(r=>r.final))[0].key;
export function golfStorySelection(anchors:Record<string,CatalogAnchor<CatalogEvidenceRow>>){
 const state=resolveCatalogSelection<CatalogEvidenceRow>(golfRows.map(r=>r.final),anchors[golfGroupKey]??catalogAnchor(golfFeatured[0].final));
 return state.present?golfRows.find(r=>r.key===state.row?.key):undefined;
}
export function placementStorySelection(anchors:Record<string,CatalogAnchor<CatalogEvidenceRow>>){
 const anchor=anchors[placementSelectionKey]??catalogAnchor(placementDefault.final);
 const state=resolveCatalogSelection<CatalogEvidenceRow>(placementRows.map(r=>r.final),anchor);
 return state.present?placementRows.find(r=>r.key===state.row?.key):undefined;
}
/** Keep each provider group independent while remembering the last top-ten selection. */
export function rememberGolfCatalogSelection<T extends CatalogEvidenceRow>(anchors:Record<string,CatalogAnchor<T>>,groupKey:string,anchor:CatalogAnchor<T>){
 return {...anchors,[groupKey]:anchor,...(placementFor(anchor.row)?{[placementSelectionKey]:anchor}:{})};
}
