import type {CSSProperties} from 'react';
import {ArrowRightIcon,ArrowTopRightIcon} from '@radix-ui/react-icons';
import {chessContenders} from './chessHistory';
import {chessMovement,chessMovementLabel} from './chessMovement';
import {chessIdentityColor} from './contenderColors';
import {eventReaderTime as clock} from './eventReaderTime';
import {probabilityLabel as pct} from './probabilityLabel';
import './golfBeforeMovement.css';
import './chessMovement.css';
export function ChessMovementCard({through,selected,onChoose,onExpand,expanded=false}:{through:string;selected:number;onChoose:(id:number,at:string)=>void;onExpand?:()=>void;expanded?:boolean}){
 const comparison=chessMovement(chessContenders,through);
 const rows=comparison?(expanded?comparison.rows:comparison.rows.slice(0,3)):[];
 return <article className={`gbm-card chess-movement ${expanded?'chess-movement-expanded':''}`} aria-label="Historical chess probability movement">
  <div className="gbm-heading"><div><span className="eyebrow">Historical win chances</span><h2>What changed?</h2></div>{onExpand&&<button onClick={onExpand} aria-label="Expand chess probability movement"><ArrowTopRightIcon/></button>}</div>
  {!expanded&&<p className="gbm-intro">Current probability unavailable · comparing recorded chances</p>}
  {comparison?<><div className="gbm-times"><span>Earlier<b>{clock.full(comparison.earlier)}</b></span><ArrowRightIcon/><span>Later<b>{clock.full(comparison.later)}</b></span></div>
   <div className="gbm-axis"><span>−{Number((comparison.scale*100).toFixed(2))} pts</span><span>0 · no change</span><span>+{Number((comparison.scale*100).toFixed(2))} pts</span></div>
   <div className="gbm-plots">{rows.map(row=><button key={row.id} style={{'--movement-ink':chessIdentityColor(row.id)} as CSSProperties} aria-pressed={selected===row.id} aria-label={`${row.name}, earlier ${pct(row.first.probability)}, later ${pct(row.last.probability)}, ${chessMovementLabel(row.change)}. Show in history.`} onClick={()=>onChoose(row.id,comparison.later)}>
    <div className="gbm-name"><strong>{row.name}</strong><span>{chessMovementLabel(row.change)}</span></div>
    <svg viewBox="0 0 300 38" preserveAspectRatio="none" aria-hidden="true"><line vectorEffect="non-scaling-stroke" x1="10" y1="18" x2="290" y2="18" className="gbm-track"/>{[10,80,220,290].map(x=><line vectorEffect="non-scaling-stroke" key={x} x1={x} x2={x} y1="11" y2="25" className="gbm-tick"/>)}<line vectorEffect="non-scaling-stroke" x1="150" x2="150" y1="4" y2="32" className="gbm-zero"/><line vectorEffect="non-scaling-stroke" x1="150" x2={150+row.change/comparison.scale*140} y1="18" y2="18" className="gbm-change"/><line vectorEffect="non-scaling-stroke" x1={150+row.change/comparison.scale*140} x2={150+row.change/comparison.scale*140+.001} y1="18" y2="18" className="chess-movement-end"/></svg>
    <div className="gbm-values"><span>Earlier <b>{pct(row.first.probability)}</b></span><span>Later <b>{pct(row.last.probability)}</b></span></div>
   </button>)}</div>
   <p className="gbm-note">{expanded?'All':'Biggest changes among'} {comparison.rows.length} contenders with recorded probabilities at both moments. Tap a name to explore their history.</p>
   {!expanded&&onExpand&&<button className="chess-movement-all" onClick={onExpand}>Explore all {comparison.rows.length} changes</button>}
  </>:<p className="gbm-empty">A shared comparison isn’t available at this moment. Choose a later recorded point in the history chart.</p>}
  <details><summary>How this comparison works</summary><p>The two adjacent captured moments at or before the chart selection are compared. A contender needs one recorded probability at each moment; missing or ambiguous probabilities stay out. No gaps are filled. Bars show percentage-point changes, not chances of winning. These are independent Kalshi probabilities; they are not normalized. Pre-tournament chances and actual standings are unavailable.</p>{comparison&&<p>Recorded instants: <time>{comparison.earlier}</time> → <time>{comparison.later}</time>.</p>}</details>
 </article>;
}
