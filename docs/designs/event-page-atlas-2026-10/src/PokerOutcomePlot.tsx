import {rangeGestureProps} from './rangeGesture';
import {ScatterChart,Scatter,XAxis,YAxis,CartesianGrid,ReferenceDot,ReferenceLine} from 'recharts';
import {ResponsiveContainer} from './ChartVisibility';
import {probabilityLabel as pct} from './probabilityLabel';
import {eventReaderTime as clock} from './eventReaderTime';
import {pokerCapture,type PokerPhase} from './pokerEvidence';
import {pokerOutcomeHistory,pokerOutcomeDomain,pokerOutcomeScale} from './pokerOutcomeHistory';
import './pokerOriginalOutcome.css';

export function PokerOutcomePlot({id,side,phase,index,onIndex,full,onScale,large=false}:{id:string;side:string;phase:PokerPhase;index:number|null;onIndex:(n:number)=>void;full:boolean;onScale:()=>void;large?:boolean}) {
  const data=pokerOutcomeHistory(id,side,phase,index);
  if(!data) return null;
  const ceiling=pokerOutcomeScale(data.points,full),domain=pokerOutcomeDomain(phase,data.points);
  return <section className={`pk-card pk-history pk-expanded pk-original-history ${large?'pk-large':''}`} aria-label="Selected original outcome history">
    <div className="pk-card-top"><h2>{data.meaning}</h2></div>
    <p className="pk-note">{data.market.name} · Original outcome · {side}</p>
    {data.point ? <>
      <div className="pk-plot" role="img" aria-label={`${data.market.name}, ${data.meaning}. Original ${side} token trades, zero to ${pct(ceiling)}. Dots are recorded trades, not a continuous forecast.`}>
        <ResponsiveContainer width="100%" height="100%"><ScatterChart margin={{top:14,right:18,left:-15,bottom:8}}>
          <CartesianGrid vertical={false} stroke="var(--surface-border)" strokeDasharray="3 4"/>
          <XAxis dataKey="t" type="number" domain={domain} ticks={[domain[0],(domain[0]+domain[1])/2,domain[1]]} height={35} axisLine={false} tickLine={false} tick={{fontSize:11}} tickFormatter={t=>clock.date(t*1000)}/>
          <YAxis dataKey="p" type="number" domain={[0,ceiling]} ticks={[0,ceiling/2,ceiling]} tickFormatter={pct} axisLine={false} tickLine={false} tick={{fontSize:12}}/>
          {phase==='final'&&<ReferenceLine x={pokerCapture.scheduledFinalTable} stroke="var(--text-secondary)" strokeDasharray="3 4" label={(d:any)=><text x={d.viewBox.x-5} y={d.viewBox.y+10} textAnchor="end" fill="var(--text-secondary)" fontSize={10}>Final table · scheduled</text>}/>}
          <Scatter data={data.points} fill="var(--series-home)" fillOpacity={.5} isAnimationActive={false} onClick={(p:any)=>onIndex(data.points.findIndex(q=>q.t===p.t&&q.p===p.p&&q.tx===p.tx))}/>
          <ReferenceDot x={data.point.t} y={data.point.p} r={6} fill="var(--surface-card)" stroke="var(--series-home)" strokeWidth={2}/>
        </ScatterChart></ResponsiveContainer>
      </div>
      <div className="pk-chart-actions"><span>Recorded {side} chances · 0–{pct(ceiling)}</span><button aria-pressed={full} onClick={onScale}>{full?'Closer scale':'0–100%'}</button></div>
      {data.points.length>1&&<input {...rangeGestureProps} className="pk-slider" type="range" min={0} max={data.points.length-1} value={data.index} aria-label="Inspect original outcome trade" aria-valuetext={`${data.meaning}, ${pct(data.point.p)}, ${clock.full(data.point.t*1000)}`} onChange={e=>onIndex(+e.target.value)}/>}
      <div className="pk-inspect-buttons"><button disabled={data.index===0} onClick={()=>onIndex(data.index-1)}>Earlier</button><button disabled={data.baselineIndex<0} onClick={()=>onIndex(data.baselineIndex)}>Before final table</button><button disabled={data.index===data.points.length-1} onClick={()=>onIndex(data.index+1)}>Later</button></div>
      <p className="pk-note">Trade {data.index+1} of {data.points.length} · Each dot keeps its own recorded time.</p>
    </> : <div className="pk-original-empty" role="status"><h3>No retained trades</h3><p>This original {side} outcome has no traded history in this capture.</p></div>}
    <p className="pk-note">Only this original {side} token supports this history. Pre-tournament baseline is not verified in this capture.</p>
  </section>;
}
