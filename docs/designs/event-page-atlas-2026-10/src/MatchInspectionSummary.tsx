import {matchInspectionSummary,type MatchInspectionRow} from './matchInspectionReadings.ts';
import {probabilityLabel as pct} from './probabilityLabel';
import {archiveMatchClock as clock} from './archiveMatchClock';
import './matchInspectionSummary.css';
export function MatchInspectionSummary({rows,baselineRows,at}:{rows:MatchInspectionRow[];baselineRows?:MatchInspectionRow[];at:number|null}){
 const readings=matchInspectionSummary(rows,at,baselineRows),dates=[...new Set(readings.flatMap(r=>r.point?[clock.date(r.point.at)]:[]))];
 return <section className="match-inspection-summary" aria-label="Recorded chance and pre-match comparison"><p>{at===null?`Last recorded trades${dates.length===1?' · '+dates[0]:''}`:`Recorded trades · ${clock.full(at)}`}</p><div style={{gridTemplateColumns:`repeat(${Math.max(1,readings.length)},minmax(0,1fr))`}}>{readings.map((r,i)=><div key={r.ticker} className={`rg-color-${i}`}><span className={`rg-label rg-label-${i}`}>{r.name}</span><b className={`match-inspection-value ${r.point?'':'match-inspection-missing'}`}>{r.point?pct(r.point.p):'No trade'}</b>{at===null&&r.point&&<small>{dates.length===1?clock.short(r.point.at):clock.full(r.point.at)}</small>}<small>Pre-match {r.baseline?pct(r.baseline.p):'unavailable'}</small></div>)}</div></section>;
}
