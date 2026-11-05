import type {CatalogEvidenceRow,CatalogPresentation} from './probabilityPresentation';
import {singleOutcomeEvidence} from './singleOutcomeEvidence';
import {probabilityLabel} from './probabilityLabel';
import {CheckIcon,Cross2Icon,MinusIcon,QuestionMarkCircledIcon} from '@radix-ui/react-icons';
import './singleOutcome.css';
export function SingleOutcomeVisual({row,state}:{row:CatalogEvidenceRow;state:CatalogPresentation}){
 const e=singleOutcomeEvidence(row,state),main=e.recorded??e.baseline;
 const label=e.recorded!==null?'Recorded chance':e.baselineLabel;
 const symbol=state.label==='Won'?<CheckIcon/>:state.label==='Lost'?<Cross2Icon/>:state.label==='Closed · no winner'?<MinusIcon/>:<QuestionMarkCircledIcon/>;
 const reference=e.baselineLabel.replace(/ chance$/,'').toLowerCase();
 const movement=e.deltaPoints===null?null:Math.abs(e.deltaPoints)<.05?`Unchanged from ${reference}`:`${Math.abs(e.deltaPoints).toFixed(1)} percentage points ${e.deltaPoints>0?'above':'below'} ${reference}`;
 return <section className="single-outcome-visual" aria-label={`Selected prop: ${row.outcome_name}`}>
  <div className="single-outcome-head"><div className="single-outcome-subject"><strong>{row.outcome_name}</strong>{state.kind==='result'&&<span className={`single-result ${state.label==='Won'?'won':''}`}>{symbol}{state.label}</span>}{state.kind==='unavailable'&&<span className="single-unavailable">{state.label}</span>}</div>{main!==null&&<div className="single-chance"><strong>{probabilityLabel(main)}</strong><span>{label}</span></div>}</div>
  {(e.recorded!==null||e.baseline!==null)&&<div className="single-chance-plot" role="img" aria-label={`${e.baselineLabel}: ${probabilityLabel(e.baseline)}. ${e.recorded!==null?'Recorded chance: '+probabilityLabel(e.recorded):state.label}. Scale zero to one hundred percent; hollow marker is earlier, solid marker is recorded.`}><div className="single-chance-track"><div className={e.recorded!==null?'single-chance-fill':'single-chance-fill baseline-only'} style={{width:`${main!*100}%`}}/>{e.baseline!==null&&<i className="single-baseline-marker" style={{left:`${e.baseline*100}%`}}/>}{e.recorded!==null&&<i className="single-recorded-marker" style={{left:`${e.recorded*100}%`}}/>}</div><div className="single-chance-axis"><span>0%</span><span>50%</span><span>100%</span></div></div>}
  {(e.recorded!==null||e.baseline===null)&&<p className="single-baseline"><span aria-hidden="true">○</span> {e.baselineLabel} {e.baseline===null?'unavailable':probabilityLabel(e.baseline)}</p>}
  {movement&&<p className="single-movement">{movement}</p>}
 </section>;
}
