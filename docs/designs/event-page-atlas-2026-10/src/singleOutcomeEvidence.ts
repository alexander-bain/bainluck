import type {CatalogEvidenceRow,CatalogPresentation} from './catalogPresentation';
import {selectedPregame,pregameLabel} from './pregameEvidence.ts';
/** Present the already-admitted state. A settled/held quote cannot become a current chance. */
export function singleOutcomeEvidence(row:CatalogEvidenceRow & {source_file?:unknown},state:CatalogPresentation){
 const baseline=selectedPregame(row),recorded=state.kind==='quote'?state.value:null;
 const qualifiedLabel=pregameLabel(row);
 const baselineLabel=qualifiedLabel==='Pregame chance'&&typeof row.source_file==='string'&&row.source_file.startsWith('field-')?'Earlier chance':qualifiedLabel;
 return {baseline,baselineLabel,recorded,stateKind:state.kind,stateLabel:state.label,deltaPoints:baseline!==null&&recorded!==null?(recorded-baseline)*100:null};
}
