import {ScatterChart,Scatter,XAxis,YAxis,CartesianGrid} from 'recharts';
import {EnterFullScreenIcon} from '@radix-ui/react-icons';
import {ResponsiveContainer} from './ChartVisibility';
import {probabilityLabel as pct} from './probabilityLabel';
import {eventReaderTime as clock} from './eventReaderTime';
import {skatingMedal,type SkatePhase} from './skatingEvidence';
import {skatingOutcomeDomain,skatingOutcomeScale} from './skatingOutcomeHistory';
import {skatingPropDetail,skatingMoveLabel} from './skatingPropPresentation';
import './skatingPropDetail.css';

export function SkatingPropDetail({id,side,phase,onSide,onHistory,large=false}:{id:string;side:string;phase:SkatePhase;onSide:(s:string)=>void;onHistory:()=>void;large?:boolean}) {
  const d=skatingPropDetail(id,side,phase);
  if(!d)return null;
  const ceiling=skatingOutcomeScale(d.points),domain=skatingOutcomeDomain(phase);
  return <section className={`pk-details sk-prop-detail ${large?'pk-large':''}`} aria-label="Gold prop probability and result">
    <div className="sk-prop-heading"><div><h3>{d.market.name}</h3><p>{d.meaning}</p></div><div role="group" aria-label="Selected original gold outcome">{['Yes','No'].map(s=><button key={s} aria-pressed={s===side} onClick={()=>onSide(s)}>{s}</button>)}</div></div>
    <p className="sk-prop-warning" role="status">Current probability unavailable · recorded history below</p>
    {(d.start||d.end)&&<div className={`sk-prop-metrics ${d.single?'sk-prop-single':''}`} aria-label="Historical probability comparison">
      {!d.single&&<div><span>{d.startLabel}</span><strong>{d.start?pct(d.start.p):'Unavailable'}</strong><small>{d.start?clock.full(d.start.t*1000):'No retained baseline trade'}</small></div>}
      <div><span>{d.endLabel}</span><strong>{d.end?pct(d.end.p):'Unavailable'}</strong><small>{d.end?clock.full(d.end.t*1000):'No retained trade'}</small></div>
    </div>}
    {d.end?<><div className="sk-prop-chart-head"><span>Recorded chance · 0–{pct(ceiling)}</span><button aria-label="Expand recorded chance" onClick={onHistory}><EnterFullScreenIcon/></button></div><button className="sk-prop-chart" aria-label="Open full original outcome history" onClick={onHistory}><span className="sr-only">{d.market.name}, {d.meaning}. Dots are original {side} trades.</span><ResponsiveContainer width="100%" height="100%"><ScatterChart margin={{top:8,right:10,left:-17,bottom:0}}><CartesianGrid vertical={false} stroke="var(--surface-border)" strokeDasharray="3 4"/><XAxis dataKey="t" type="number" domain={domain} ticks={[domain[0],domain[1]]} height={23} axisLine={false} tickLine={false} tick={{fontSize:10}} tickFormatter={t=>clock.date(t*1000)}/><YAxis dataKey="p" type="number" domain={[0,ceiling]} ticks={[0,ceiling]} tickFormatter={pct} axisLine={false} tickLine={false} tick={{fontSize:10}}/><Scatter data={d.points} fill="var(--series-home)" fillOpacity={.62} isAnimationActive={false}/></ScatterChart></ResponsiveContainer></button><p className="sk-prop-move">{d.single?(phase==='before'?'One captured trade':'No later recorded trade'):skatingMoveLabel(d.move)}</p></>:<p className="sk-prop-empty"><b>No retained trades</b><span>Before race day: Unavailable</span><small>This original {side} outcome has no captured probability history.</small></p>}
    {phase==='final'&&<div className="sk-prop-result"><div><span>Selected outcome</span><b>{d.grade}</b></div><div><span>Reported finish</span><b>{d.result?`${skatingMedal(d.result.rank)} · ${d.result.time}s`:'Not linked'}</b></div></div>}
    <button className="pk-link sk-prop-history" onClick={onHistory}>Explore probability history</button>
    <details className="sk-prop-rules"><summary>Market wording & rules</summary><p>{d.market.predicate}</p><p>{d.market.rules}</p><p>Gold chance concerns first place, not any medal. Before race day means before midnight February 15 in Milan; actual start is unverified. First captured trade is not the opening probability.</p><p>Polymarket · market {d.market.id}</p></details>
    <details className="sk-prop-identity"><summary>Exact original identity</summary><p>{d.condition}</p><p>{d.token}</p></details>
    <a href={d.market.providerURL} target="_blank" rel="noreferrer">Provider market</a>
  </section>;
}
