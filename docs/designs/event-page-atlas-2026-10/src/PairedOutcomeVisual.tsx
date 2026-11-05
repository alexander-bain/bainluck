import type {CatalogEvidenceRow,CatalogPresentation} from './probabilityPresentation';
import {catalogOutcomeIdentity} from './catalogSelection';
import {singleOutcomeEvidence} from './singleOutcomeEvidence';
import {probabilityLabel} from './probabilityLabel';
import {SingleOutcomeVisual} from './SingleOutcomeVisual';
import './pairedOutcome.css';
/** Each side retains its own evidence; neither quote is derived from the other. */
export function PairedOutcomeVisual<T extends CatalogEvidenceRow>({rows,visibleRows,selected,stateFor,choose}:{rows:T[];visibleRows:T[];selected:T;stateFor:(r:T)=>CatalogPresentation;choose:(r:T)=>void}){
 const visible=new Set(visibleRows.map(catalogOutcomeIdentity));
 return <div className="paired-outcome-grid" role="group" aria-label="Compare both outcomes">
 {rows.map(row=>{const state=stateFor(row),e=singleOutcomeEvidence(row,state);return <button aria-label={`${row.outcome_name}. ${state.kind==='quote'?probabilityLabel(e.recorded)+' recorded chance':state.label}. ${e.baselineLabel}: ${probabilityLabel(e.baseline)}.`} key={row.key} className="paired-outcome-choice" aria-pressed={catalogOutcomeIdentity(row)===catalogOutcomeIdentity(selected)} disabled={!visible.has(catalogOutcomeIdentity(row))} onClick={()=>choose(row)}><SingleOutcomeVisual row={row} state={state}/></button>})}
 </div>;
}
