import {readerTime} from './readerTime';
import {finalCatalogPresentation,type FinalCatalogRow} from './finalCatalogEvidence';
import {TotalExpectationPlot} from './TotalExpectationPlot';
import {nflTotalExpectation as evidence,nflTotalPregameRecord,nflTotalPregameNote} from './nflTotalPregame';
import {probabilityLabel} from './probabilityLabel';
import {ChevronLeftIcon,ChevronRightIcon} from '@radix-ui/react-icons';
import './compactTotal.css';
export function FinalTotalTrack({rows,visibleRows,selected,onChoose}:{rows:FinalCatalogRow[];visibleRows:FinalCatalogRow[];selected:FinalCatalogRow;onChoose:(row:FinalCatalogRow)=>void}){
 const label=(row:FinalCatalogRow)=>finalCatalogPresentation(row,{status:'completed',qualityHold:false,mode:'captured'},'Final').label;
 const records=visibleRows.flatMap(row=>{const r=nflTotalPregameRecord(row);return r?[{...r,key:row.key}]:[]});
 const record=nflTotalPregameRecord(selected),index=visibleRows.findIndex(row=>row.key===selected.key);
 return <div className="final-total-track total-expectation-card compact-total">
  <div className="compact-total-summary"><strong>{evidence.actual} points</strong><span>{evidence.forecast-evidence.actual} below the pregame forecast</span></div>
  <p className="expectation-axis-title">Pregame chance of finishing above each line</p>
  <TotalExpectationPlot records={records} actual={evidence.actual} forecast={evidence.forecast} selectedKey={selected.key} low={20} high={70} ticks={[20,40,60]}/>
  <div className="compact-total-selection" aria-live="polite" aria-atomic="true"><div><strong>{selected.outcome_name}</strong><span className="compact-total-result">{label(selected)}</span></div><div><strong>{probabilityLabel(record?.value??null)}</strong><span>Pregame chance</span></div></div>
  <div className="compact-total-picker"><button aria-label="Previous total line" disabled={index<=0} onClick={()=>onChoose(visibleRows[index-1])}><ChevronLeftIcon/></button><select aria-label="Inspect total points line" value={index>=0?selected.key:''} onChange={event=>{const row=visibleRows.find(row=>row.key===event.target.value);if(row)onChoose(row)}}><option value="" disabled>Choose an offered line</option>{visibleRows.map(row=><option key={row.key} value={row.key}>{row.outcome_name}</option>)}</select><button aria-label="Next total line" disabled={index<0||index>=visibleRows.length-1} onClick={()=>onChoose(visibleRows[index+1])}><ChevronRightIcon/></button></div>
  <details className="expectation-disclosure"><summary>Timing &amp; original results</summary><p>{nflTotalPregameNote(selected)} Projection {evidence.forecast} points, recorded {readerTime(evidence.forecastAt)}. Final score observed {readerTime(evidence.actualAt)}. Provider results remain separate from probabilities and actual points.</p><p>Hollow circles show {records.length} of {rows.length} offered lines. Missing history is never a zero chance. The solid line is the actual score; the dashed line is the pregame projection.</p></details>
 </div>;
}
