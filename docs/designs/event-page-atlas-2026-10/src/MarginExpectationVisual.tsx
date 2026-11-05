import {nbaProjectionUnavailable} from './basketballProjectionAvailability';
import {NBAFinalThresholdPlot} from './NBAFinalThresholdPlot';
import {NBAActualForecastPlot} from './NBAActualForecastPlot';
import {eventReaderTime} from './eventReaderTime';
import {marginExpectation as wire,marginRecord,marginNote} from './marginPregame';
import {probabilityLabel} from './probabilityLabel';
import type {CatalogEvidenceRow,CatalogPresentation} from './probabilityPresentation';
import {ChevronLeftIcon,ChevronRightIcon} from '@radix-ui/react-icons';
import './marginExpectation.css';
export function MarginExpectationVisual<T extends CatalogEvidenceRow>({rows,visibleRows,selected,state,choose,timingOpen,onTimingOpen}:{rows:T[];visibleRows:T[];selected:T;state:CatalogPresentation;choose:(r:T)=>void;timingOpen?:boolean;onTimingOpen?:(value:boolean)=>void}){
 const ordered=[...rows].sort((a,b)=>marginRecord(a)!.margin-marginRecord(b)!.margin),record=marginRecord(selected);if(!record)return null;
 const visible=new Set(visibleRows.map(r=>marginRecord(r)?.key)),index=ordered.findIndex(r=>marginRecord(r)?.key===record.key),filtered=!visible.has(record.key);
 const known=wire.records.filter(r=>r.value!==null);
 const x=(n:number)=>40+(n+24)/48*288,y=(n:number)=>172-n*120;
 return <section className="margin-expectation" aria-label="Winning margin versus pregame expectations">
  <div className="margin-finish"><div><span>Actual final</span><strong>Clippers by 3</strong></div>{!nbaProjectionUnavailable&&<div><span>Pregame forecast</span><strong>Warriors by 2.7</strong></div>}</div>
  <p className="margin-caption">{known.length?"Pregame chance to win by more than each margin":nbaProjectionUnavailable?"Final margin versus the selected line":"Final margin versus pregame forecast"}</p>
  {known.length?<svg viewBox="0 0 360 222" role="img" aria-label={`${known.length} original pregame probabilities. Warriors winning margins extend left, Clippers margins right. Solid rule: Clippers by 3 actual. ${nbaProjectionUnavailable?"No pregame projection supplied.":"Dashed rule: Warriors by 2.7 forecast."} Each dot retains its own quoted probability.`}>
   {[0,.5,1].map(p=><g key={p}><line x1="40" x2="328" y1={y(p)} y2={y(p)} className="expectation-grid"/><text x="32" y={y(p)+4} textAnchor="end">{p*100}%</text></g>)}
   <line x1={x(0)} x2={x(0)} y1="43" y2="177" className="margin-zero"/>
   <line x1={x(wire.actual)} x2={x(wire.actual)} y1="28" y2="180" className="expectation-actual"/><text x={x(wire.actual)+4} y="17" textAnchor="start">3 actual</text>
   {!nbaProjectionUnavailable&&<><line x1={x(wire.forecast)} x2={x(wire.forecast)} y1="28" y2="180" className="expectation-projection"/><text x={x(wire.forecast)-4} y="17" textAnchor="end">2.7 forecast</text></>}
   {wire.records.filter(r=>r.value!==null).map(r=><g key={r.key} className={r.team==='away'?'margin-away':'margin-home'}><line x1={x(r.margin)} x2={x(r.margin)} y1={y(r.value!)} y2="172" className="margin-stem"/><circle cx={x(r.margin)} cy={y(r.value!)} r={r.key===record.key?6:4} className={`margin-dot ${r.key===record.key?'selected':''}`}/></g>)}
   {[-20,-10,0,10,20].map(n=><text x={x(n)} y="195" textAnchor="middle" key={n}>{n===0?'Tie':Math.abs(n)}</text>)}<text x="100" y="216" textAnchor="middle">Warriors by</text><text x="267" y="216" textAnchor="middle">Clippers by</text>
  </svg>:nbaProjectionUnavailable?<NBAFinalThresholdPlot actual={wire.actual} threshold={record.margin} low={-24} high={24} ticks={[-20,0,20]} actualLabel="Clippers by 3" thresholdLabel={`${record.team==='home'?'Clippers':'Warriors'} by more than ${record.threshold} points`} signed leftLabel="Warriors by" rightLabel="Clippers by"/>:<NBAActualForecastPlot actual={wire.actual} forecast={wire.forecast} low={-24} high={24} ticks={[-20,0,20]} actualLabel="Clippers by 3" forecastLabel="Warriors by 2.7" signed leftLabel="Warriors by" rightLabel="Clippers by"/>}
  {!known.length&&<p className="expectation-coverage">{nbaProjectionUnavailable?"Pregame chances and score projection unavailable.":"Pregame prop chances unavailable. The signed points axis compares the known forecast with the final."}</p>}
  {nbaProjectionUnavailable&&known.length>0&&<p className="expectation-coverage">Pregame score projection unavailable.</p>}
  <div className="expectation-selected" aria-live="polite"><div><strong>{record.team==='home'?'Clippers':'Warriors'} by {Math.ceil(record.threshold)}+</strong><span>{state.label}</span></div><div><strong className={record.value===null?"baseline-unavailable":undefined}>{record.value===null?"Unavailable":probabilityLabel(record.value)}</strong><span>Pregame chance</span></div></div>
  <div className="margin-picker"><button aria-label="Previous margin" disabled={filtered||index<=0||!visible.has(marginRecord(ordered[index-1])?.key??'')} onClick={()=>choose(ordered[index-1])}><ChevronLeftIcon/></button><select aria-label="Inspect winning margin" value={record.key} onChange={e=>{const r=ordered.find(r=>marginRecord(r)?.key===e.target.value);if(r)choose(r)}}>{ordered.map(r=><option key={r.key} value={marginRecord(r)!.key} disabled={!visible.has(marginRecord(r)!.key)}>{marginRecord(r)!.team==='home'?'Clippers':'Warriors'} by {Math.ceil(marginRecord(r)!.threshold)}+</option>)}</select><button aria-label="Next margin" disabled={filtered||index>=ordered.length-1||!visible.has(marginRecord(ordered[index+1])?.key??'')} onClick={()=>choose(ordered[index+1])}><ChevronRightIcon/></button></div>
  <details className="expectation-disclosure" open={timingOpen} onToggle={e=>onTimingOpen?.(e.currentTarget.open)}><summary>Timing &amp; chart guide</summary><p>{marginNote(selected)} {nbaProjectionUnavailable?"Pregame score projection unavailable.":`Forecast recorded ${eventReaderTime.full(wire.forecastAt)}.`} Final score observed {eventReaderTime.full(wire.actualAt)}.</p><p>{known.length?"Each hollow dot is an offered margin and its own pregame chance, not a score distribution.":"No probability axis or probability marks are shown without baseline evidence."} Left means Warriors winning; right means Clippers winning. The score, contract threshold and any forecast use points; results come from separate source settlement.</p></details>
 </section>;
}
