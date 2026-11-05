import {rangeGestureProps} from './rangeGesture';
import {ComposedChart,Line,XAxis,YAxis,CartesianGrid,ReferenceDot,ReferenceLine} from 'recharts';
import {ResponsiveContainer} from './ChartVisibility';
import {ExpandCard} from './CardFocus';
import {eventReaderTime as clock} from './eventReaderTime';
import {soccerBeforeCapture as f,beforeSoccerHistory,beforeSoccerPlot,beforeSoccerInspection} from './soccerBeforeHistory';
const pct=(value:number)=>`${(value*100).toLocaleString('en-US',{maximumFractionDigits:2})}%`;
import './soccerBeforeHistory.css';
export function SoccerBeforeHistory({index,setIndex,fullScale,setFullScale,expand,large=false}:{index:number|null;setIndex:(n:number|null)=>void;fullScale:boolean;setFullScale:(v:boolean)=>void;expand?:()=>void;large?:boolean}){
 const points=beforeSoccerHistory(),point=beforeSoccerInspection(index??points.length-1),first=Date.parse(points[0].at),last=Date.parse(points.at(-1)!.at);
 return <section className={`sbh ${large?'sbh-large':''}`} aria-label="Pre-match probability history">
 <div className="sbh-title"><h3>Before the match</h3>{expand&&<ExpandCard label="pre-match win history" onClick={expand}/>}</div>
 <div className="sbh-readout"><span>Valladolid win <strong>{pct(point.value)}</strong></span><span>{index===null?'Last recorded':'Recorded'} {clock.full(point.at)}</span></div>
 <button className="sbh-scale" onClick={()=>setFullScale(!fullScale)}>{fullScale?'0–100% scale · Zoom to 40–55%':'40–55% scale · Show 0–100%'}</button>
 <div className="sbh-chart" role="img" aria-label={`Valladolid pre-match history, 361 recorded observations. ${fullScale?'0 to 100':'40 to 55'} percent scale. Selected ${pct(point.value)} at ${clock.full(point.at)}.`}>
 <ResponsiveContainer width="100%" height="100%"><ComposedChart data={beforeSoccerPlot()} margin={{left:-18,right:20,top:12,bottom:0}}>
 <XAxis type="number" dataKey="time" domain={[first,last]} ticks={[first,(first+last)/2,last]} tickFormatter={clock.date} tick={{fontSize:11}} axisLine={false} tickLine={false}/>
 <YAxis domain={fullScale?[0,100]:[40,55]} ticks={fullScale?[0,50,100]:[40,45,50,55]} tickFormatter={v=>`${v}%`} tick={{fontSize:11}} axisLine={false} tickLine={false}/>
 <CartesianGrid vertical={false} stroke="var(--surface-border)" strokeDasharray="3 5"/>
 <ReferenceLine y={f.baseline.value*100} stroke="var(--series-home)" strokeDasharray="4 4" strokeOpacity={.45}/>
 <Line dataKey="chance" stroke="var(--series-home)" strokeWidth={2.5} dot={false} connectNulls={false} isAnimationActive={false}/>
 <ReferenceDot x={Date.parse(point.at)} y={point.value*100} r={5} fill="var(--surface-card)" stroke="var(--series-home)" strokeWidth={2}/>
 </ComposedChart></ResponsiveContainer></div>
 <label className="sbh-slider">Explore recorded chances<input {...rangeGestureProps} type="range" aria-label="Inspect pre-match probability" min={0} max={points.length-1} value={index??points.length-1} aria-valuetext={`${pct(point.value)} at ${clock.full(point.at)}`} onChange={e=>setIndex(Number(e.target.value))}/></label>
 <div className="sbh-foot"><span>Dashed · pre-match {pct(f.baseline.value)}</span>{index!==null&&<button onClick={()=>setIndex(null)}>Latest recorded</button>}</div>
 {!expand&&<details><summary>About this history</summary><p>361 recorded home-blend observations, captured for this replay. No match scores or later probabilities appear here. Gaps longer than two hours stay blank; this is a display rule, not live freshness policy. Other blended outcomes are unavailable.</p></details>}
 </section>;
}
