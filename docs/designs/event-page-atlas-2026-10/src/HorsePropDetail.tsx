import {rangeGestureProps} from './rangeGesture';
import {useState} from 'react';
import {EnterFullScreenIcon} from '@radix-ui/react-icons';
import {ScatterChart,Scatter,XAxis,YAxis,CartesianGrid,ReferenceLine,ReferenceDot} from 'recharts';
import {ResponsiveContainer} from './ChartVisibility';
import {horseOutcomeHistory,horseOutcomeDomain,horseOutcomeScale,horseOutcomeMove} from './horseOutcomeHistory';
import {type RacePhase} from './horseRacingPhase';
import timing from './horseRacingTiming.json';
import {readerTime,readerClock} from './readerTime';
import {probabilityLabel as pct} from './probabilityLabel';
import './skatingPropDetail.css';
import './horseOriginalOutcome.css';
const stamp=(t:number)=>readerTime(t,{seconds:true});
export function HorsePropDetail({id,side,phase,onSide,large=false}:{id:string;side:string;phase:RacePhase;onSide:(s:string)=>void;large?:boolean}){
 const [expanded,setExpanded]=useState(false),[index,setIndex]=useState<number|null>(null),[full,setFull]=useState(false);
 const d=horseOutcomeHistory(id,side,phase,index);if(!d)return null;
 const ceiling=horseOutcomeScale(d.points,expanded?full:true),domain=horseOutcomeDomain(d.points,phase);
 const change=(s:string)=>{onSide(s);setIndex(null)};
 const plot=(big:boolean)=><ResponsiveContainer width="100%" height="100%"><ScatterChart margin={{top:14,right:14,left:-17,bottom:4}}><CartesianGrid vertical={false} stroke="var(--surface-border)" strokeDasharray="3 4"/><XAxis dataKey="t" type="number" domain={domain} ticks={big?[domain[0],(domain[0]+domain[1])/2,domain[1]]:[domain[0],domain[1]]} height={big?38:26} axisLine={false} tickLine={false} tick={{fontSize:large?13:10}} tickFormatter={t=>readerClock(t)}/><YAxis dataKey="p" type="number" domain={[0,ceiling]} ticks={big?[0,ceiling/2,ceiling]:[0,ceiling]} tickFormatter={pct} axisLine={false} tickLine={false} tick={{fontSize:large?13:10}}/>{big&&<ReferenceLine x={timing.scheduledStart} stroke="var(--text-secondary)" strokeDasharray="3 4" label={{value:'Scheduled start',position:'insideTopRight',fontSize:10,fill:'var(--text-secondary)'}}/>}<Scatter data={d.points} fill="var(--series-home)" fillOpacity={.65} isAnimationActive={false} onClick={big?(p:any)=>setIndex(d.points.findIndex(q=>q.tx===p.tx&&q.t===p.t&&q.p===p.p)):undefined}/>{big&&d.point&&<ReferenceDot x={d.point.t} y={d.point.p} r={6} fill="var(--surface-card)" stroke="var(--series-home)" strokeWidth={2}/>}</ScatterChart></ResponsiveContainer>;
 return <section className={`pk-details sk-prop-detail hr-prop-detail ${large?'pk-large':''}`} aria-label="Original horse outcome probability and result">
  {expanded&&<button className="hr-prop-back" onClick={()=>setExpanded(false)}>Back to prop</button>}
  <div className="sk-prop-heading"><div><h3>{d.market.name}</h3><p>{d.meaning}</p></div><div role="group" aria-label="Selected original horse outcome">{['Yes','No'].map(s=><button key={s} aria-pressed={side===s} onClick={()=>change(s)}>{s}</button>)}</div></div>
  <p className="sk-prop-warning" role="status">Current probability unavailable · recorded history below</p>
  {expanded?<>
   <div className="hr-prop-selected" aria-live="polite"><span>Selected {side} trade</span><strong>{d.point?pct(d.point.p):'Unavailable'}</strong><small>{d.point?stamp(d.point.t):'No retained trade'}</small></div>
   <p className="hr-prop-baseline">Pre-race · before scheduled start <b>{d.baseline?pct(d.baseline.p):'Unavailable'}</b>{d.baseline&&<small>{stamp(d.baseline.t)}</small>}</p>
   {d.points.length>0?<><div className="hr-prop-full-chart" role="img" aria-label={`Original ${side} recorded probabilities for ${d.market.name}, zero to ${pct(ceiling)}. Separate trade dots; no inferred continuous forecast.`}>{plot(true)}</div><div className="hr-prop-chart-actions"><span>0–{pct(ceiling)} · Your local time</span><button aria-pressed={full} onClick={()=>setFull(!full)}>{full?'Closer scale':'0–100%'}</button></div>{d.points.length>1&&<input {...rangeGestureProps} type="range" aria-label="Inspect original horse outcome trade" aria-valuetext={`${d.market.name}, ${d.meaning}, ${pct(d.point!.p)}, ${stamp(d.point!.t)}`} min={0} max={d.points.length-1} value={d.index} onChange={e=>setIndex(+e.target.value)}/>}<div className="hr-prop-inspect"><button disabled={d.index===0} onClick={()=>setIndex(d.index-1)}>Earlier</button><button disabled={d.baselineIndex<0} onClick={()=>setIndex(d.baselineIndex)}>Pre-race trade</button><button disabled={d.index===d.points.length-1} onClick={()=>setIndex(d.index+1)}>Later</button></div><p className="sk-prop-warning">Trade {d.index+1} of {d.points.length} · {readerTime(domain[0],{dateOnly:true})}{readerTime(domain[0],{dateOnly:true})!==readerTime(domain[1],{dateOnly:true})?' – '+readerTime(domain[1],{dateOnly:true}):''}</p></>:<p className="sk-prop-empty"><b>No retained trades</b><span>This original {side} outcome has no recorded probabilities in this view.</span></p>}
  </>:<>
   {(d.start||d.end)&&<div className={`sk-prop-metrics ${d.single?'sk-prop-single':''}`} aria-label="Historical horse probability comparison">{!d.single&&<div><span>{d.startLabel}</span><strong>{d.start?pct(d.start.p):'Unavailable'}</strong><small>{d.start?stamp(d.start.t):'No retained pre-race trade'}</small></div>}<div><span>{d.endLabel}</span><strong>{d.end?pct(d.end.p):'Unavailable'}</strong><small>{d.end?stamp(d.end.t):'No retained trade'}</small></div></div>}
   {d.end?<><div className="sk-prop-chart-head"><span>Recorded chance · 0–100%</span><button aria-label="Expand horse outcome history" onClick={()=>setExpanded(true)}><EnterFullScreenIcon/></button></div><button className="sk-prop-chart" aria-label="Open full original horse outcome history" onClick={()=>setExpanded(true)}>{plot(false)}</button><p className="sk-prop-move">{d.single?(phase==='before'?'One captured trade':'No later recorded trade'):horseOutcomeMove(d.move)}</p></>:<p className="sk-prop-empty"><b>No retained trades</b><span>Pre-race chance: Unavailable</span><small>This original {side} outcome has no captured probabilities in this view.</small></p>}
   {phase==='final'&&<div className="sk-prop-result"><div><span>Selected outcome</span><b>{d.grade??'Unconfirmed'}</b></div><div><span>Reported horse finish</span><b>{d.place?`#${d.place}`:d.market.name==='Other'?'Special outcome':'Not captured'}</b></div></div>}
   <button className="hr-prop-link sk-prop-history" onClick={()=>setExpanded(true)}>Explore probability history</button>
  </>}
  <details className="sk-prop-rules"><summary>Market wording & rules</summary><p>{d.market.predicate}</p><p>{d.market.rules}</p><p>Pre-race means strictly before the published 3 p.m. Melbourne schedule, not a verified actual start or closing probability. First captured trade is not opening. These independently recorded {side} trades are not a live probability or the Bain Luck blend. No opposite-side complement, field normalization or settlement endpoint is added.</p><p>Polymarket · market {d.market.id}</p></details>
  <details className="sk-prop-identity"><summary>Exact original identity</summary><p>{d.condition}</p><p>{d.token}</p></details>
  <a className="hr-prop-link" href={`https://polymarket.com/event/horse-racing-2025-lexus-melbourne-cup-winner`} target="_blank" rel="noreferrer">Provider event</a>
 </section>;
}
