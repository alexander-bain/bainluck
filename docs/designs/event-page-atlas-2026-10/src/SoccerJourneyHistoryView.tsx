import {rangeGestureProps} from './rangeGesture';
import {ComposedChart,Line,Area,XAxis,YAxis,CartesianGrid,ReferenceDot,ReferenceLine} from 'recharts';
import {ResponsiveContainer} from './ChartVisibility';
import {SoccerBeforeHistory} from './SoccerBeforeJourney';
import {eventReaderTime as clock} from './eventReaderTime';
import {probabilityLabel as pct} from './probabilityLabel';
import type {useSoccerReadingSession} from './SoccerReadingSession';
import {journeyHistoryPoints,journeyHistoryPlot,journeyHistorySelection} from './soccerJourneyHistory';
import f from './liveSoccer.json';
import './soccerJourneyHistory.css';
export function SoccerJourneyHistory({session:s}:{session:ReturnType<typeof useSoccerReadingSession>}){
 const context=s.state.displayed.payload,before=context.phase==='before'||s.historyWindow==='before';
 const points=journeyHistoryPoints(context),selection=journeyHistorySelection(context,s.matchHistoryAt),point=selection.point;
 const first=Date.parse(points[0].at),last=Date.parse(points.at(-1)!.at),domain=first===last?[first-60000,last+60000]:[first,last];
 return <section className={`sjh ${s.large?'sjh-large':''}`} aria-label="Match probability journey">
 {context.phase!=='before'&&<div className="sjh-tabs" aria-label="Probability history window"><button aria-pressed={!before} onClick={()=>s.setHistoryWindow('match')}>During match</button><button aria-pressed={before} onClick={()=>s.setHistoryWindow('before')}>Before match</button></div>}
 {before?<SoccerBeforeHistory index={s.historyIndex} setIndex={s.setHistoryIndex} fullScale={s.historyFullScale} setFullScale={s.setHistoryFullScale} large={s.large}/>:<>
 <h2>Win probability</h2>
 <div className="sjh-readout"><span>Valladolid win</span><strong>{pct(point.value)}</strong><span>{selection.inspecting?'Recorded':'Last recorded'} {clock.full(point.at)}</span><div className="sjh-score"><span>Score recorded by then</span><strong>{selection.score?`Valladolid ${selection.score.home_score}–${selection.score.away_score} Albacete`:'Not yet recorded'}</strong>{selection.score&&<small>First observed {clock.short(selection.score.timestamp)}</small>}</div></div>
 <label className="sjh-slider">Explore recorded chances<input {...rangeGestureProps} aria-label="Inspect match probability" type="range" min={0} max={points.length-1} value={selection.index} aria-valuetext={`${pct(point.value)} at ${clock.full(point.at)}`} onChange={e=>s.setMatchHistoryAt(points[Number(e.target.value)].at)}/></label>
 <div className="sjh-chart" role="img" aria-label={`Valladolid match history: ${points.length} recorded observations. Selected ${pct(point.value)} at ${clock.full(point.at)}. Pre-match ${pct(f.baseline.value)}. 0 to 100 percent scale.`}><ResponsiveContainer width="100%" height="100%"><ComposedChart data={journeyHistoryPlot(context)} margin={{left:-18,right:18,top:12,bottom:4}}><XAxis dataKey="time" type="number" domain={domain} ticks={first===last?[first]:[first,(first+last)/2,last]} tickFormatter={clock.short} tick={{fontSize:11}} axisLine={false} tickLine={false}/><YAxis domain={[0,100]} ticks={[0,50,100]} tickFormatter={n=>n+'%'} tick={{fontSize:11}} axisLine={false} tickLine={false}/><CartesianGrid vertical={false} stroke="var(--surface-border)" strokeDasharray="3 5"/><Area dataKey="chance" fill="var(--series-home)" fillOpacity={.08} stroke="none" connectNulls={false} isAnimationActive={false}/><Line dataKey="chance" stroke="var(--series-home)" strokeWidth={2.5} dot={false} connectNulls={false} isAnimationActive={false}/><ReferenceLine y={f.baseline.value*100} stroke="var(--series-home)" strokeDasharray="4 4" strokeOpacity={.5}/><ReferenceLine x={Date.parse(point.at)} stroke="var(--text-secondary)" strokeDasharray="2 4"/><ReferenceDot x={Date.parse(point.at)} y={point.value*100} r={5} fill="var(--series-home)"/></ComposedChart></ResponsiveContainer></div>


 <div className="sjh-key"><span>Dashed · pre-match {pct(f.baseline.value)}</span>{selection.inspecting&&<button onClick={()=>s.setMatchHistoryAt(null)}>Latest recorded</button>}</div>
 <details><summary>About this history</summary><p>Only observations in the displayed match are shown. New arrivals wait while you read. A score is the last checkpoint recorded at or before the selected probability, not an exact goal time. Gaps over five minutes stay blank. Exact half markers and other competitors’ blended histories are unavailable. Final results never become probability samples.</p></details>
 </>}
 </section>;
}
