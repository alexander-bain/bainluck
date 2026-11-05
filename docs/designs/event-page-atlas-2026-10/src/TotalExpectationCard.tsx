import {rangeGestureProps} from './rangeGesture';
import {nbaProjectionUnavailable} from './basketballProjectionAvailability';
import {NBAFinalThresholdPlot} from './NBAFinalThresholdPlot';
import {NBAActualForecastPlot} from './NBAActualForecastPlot';
import {eventReaderTime} from './eventReaderTime';
import {TotalExpectationPlot} from './TotalExpectationPlot';
import {useState} from 'react';
import {totalExpectation as evidence,totalPregame,totalPregameNote,totalPregameRecord} from './totalPregame';
import {probabilityLabel} from './probabilityLabel';
import type {CatalogEvidenceRow} from './probabilityPresentation';
import './totalExpectation.css';
type Props<T>={rows:T[];onPick:(row:T)=>void;selectedKey?:string;onSelection?:(key:string)=>void;timingOpen?:boolean;onTimingOpen?:(value:boolean)=>void};
export function TotalExpectationCard<T extends CatalogEvidenceRow&{threshold?:number|null;key:string}>({rows,onPick,selectedKey,onSelection,timingOpen,onTimingOpen}:Props<T>){
 const [localIndex,setLocalIndex]=useState(4);const index=selectedKey===undefined?localIndex:Math.max(0,rows.findIndex(row=>row.key===selectedKey));const setIndex=(next:number)=>{const row=rows[next];if(row){if(onSelection)onSelection(row.key);else setLocalIndex(next)}};const selected=rows[index];if(!selected)return null;
 const records=evidence.records.filter(r=>r.value!=null),record=totalPregameRecord(selected)!,chance=totalPregame(selected);
 return <article className="atlas-card total-expectation-card" aria-label="Scoring versus pregame expectations">
  <span className="eyebrow">Combined points · final</span><h3>{nbaProjectionUnavailable?"205 points at the final buzzer":"17.3 below the forecast"}</h3>
  <div className="expectation-score"><div><span>Actual final</span><strong>205</strong></div>{!nbaProjectionUnavailable&&<div><span>Pregame projection</span><strong>222.3</strong></div>}</div>
  <p className="expectation-axis-title">{records.length?"Pregame chance of finishing above each line":nbaProjectionUnavailable?"Final points versus the selected total":"Final points versus pregame projection"}</p>
  {records.length?<TotalExpectationPlot records={records} actual={205} forecast={nbaProjectionUnavailable?null:222.3} selectedKey={selected.key} low={200} high={248} ticks={[200,220,240]}/>:nbaProjectionUnavailable?<NBAFinalThresholdPlot actual={205} threshold={selected.threshold!} low={190} high={250} ticks={[200,220,240]} actualLabel="Final 205" thresholdLabel={`Over ${selected.threshold} points`}/>:<NBAActualForecastPlot actual={205} forecast={222.3} low={190} high={250} ticks={[200,220,240]} actualLabel="Final 205" forecastLabel="Projected 222.3"/>}
  <p className="expectation-coverage">{records.length?`○ Pregame chance · ${records.length} of ${rows.length} lines have recorded history`:nbaProjectionUnavailable?"Pregame chances and score projection unavailable.":"Pregame prop chances unavailable. Final score and projection are separate, known observations."}</p>
  {nbaProjectionUnavailable&&records.length>0&&<p className="expectation-coverage">Pregame score projection unavailable.</p>}
  <div className="expectation-selected" aria-live="polite"><div><strong>Over {selected.threshold} points</strong><span>{record.result}</span></div><div><strong className={!chance?"baseline-unavailable":undefined}>{chance?probabilityLabel(chance.value):"Unavailable"}</strong><span>Pregame chance</span></div></div>
  <label className="threshold-scrub">Explore all {rows.length} total lines<input {...rangeGestureProps} type="range" min="0" max={rows.length-1} value={index} aria-label="Explore scoring expectations" aria-valuetext={`Over ${selected.threshold} points: ${chance?probabilityLabel(chance.value)+' pregame':'Pregame unavailable'}; ${record.result}`} onChange={e=>setIndex(+e.target.value)}/></label>
  <div className="total-selection"><button aria-label="Previous scoring threshold" disabled={index===0} onClick={()=>setIndex(index-1)}>‹</button><span>{index+1} of {rows.length}</span><button aria-label="Next scoring threshold" disabled={index===rows.length-1} onClick={()=>setIndex(index+1)}>›</button></div>
  <details className="expectation-disclosure" open={timingOpen} onToggle={e=>onTimingOpen?.(e.currentTarget.open)}><summary>Timing &amp; missing history</summary><p>{totalPregameNote(selected)} {nbaProjectionUnavailable?"Pregame score projection unavailable.":`Projection recorded ${eventReaderTime.full(evidence.forecastAt)}.`} Final score observed {eventReaderTime.full(evidence.actualAt)}. Result is separately confirmed by the source.</p><p>{records.length?`The probability chart shows only ${records.length} lines with pregame history.`:"No probability axis or probability marks are shown without baseline evidence."} Every offered line is selectable; missing history is never a zero chance.</p></details>
  <button className="card-link" onClick={()=>onPick(selected)}>Selected total details <span aria-hidden="true">›</span></button>
 </article>;
}
