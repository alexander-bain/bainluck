import {CardFocus} from './CardFocus';
import {useStoryState,useStoryReaderMemory} from './StorySession';
import {ArrowTopRightIcon} from '@radix-ui/react-icons';
import {HistoryReaderContext} from './HistoryReaderContext';
import {rangeGestureProps} from './rangeGesture';
import {readerTime,readerClock,readerCrossesDay} from './readerTime';
import {HeadlineInfo} from './HeadlineInfo';
import {SoccerFinalFacts} from './SpecializedHeadlines';
import {useCapturedHistory} from './useCapturedHistory';
import {HistorySelectionStatus} from './HistorySelectionStatus';
import {ResponsiveContainer} from './ChartVisibility';
import {LineChart, Line, XAxis, YAxis, CartesianGrid, ReferenceLine} from 'recharts';
import {retainedSoccerHistory,soccerScope} from './soccerFinalHistory';
import {probabilityLabel} from './probabilityLabel';
import './tennisProbabilityJourney.css';import './soccerFinalJourney.css';
const clock=readerTime;
const sides=['home','draw','away'] as const,labels={home:'Hull',draw:'Draw',away:'Everton'},colors={home:'var(--series-home)',draw:'var(--text-primary)',away:'var(--series-away)'};
export function SoccerFinalJourney({wide=false,large=false,inReader=false}:{wide?:boolean;large?:boolean;inReader?:boolean}){
 const [open,setOpen]=useStoryState('soccer-final:hull-everton','full-probability-history',false);
 const memory=useStoryReaderMemory('soccer-final:hull-everton:full-history');
 const {selection,scope,points,selected,index,unavailable,choose,change,pin}=useCapturedHistory('soccer-final:hull-everton',retainedSoccerHistory,soccerScope);
 const baseline=retainedSoccerHistory.filter(p=>p.pregame).at(-1);
 if(!baseline)return <p>Three-way probability history unavailable.</p>;
 const showDates=scope!=='game'||readerCrossesDay(points);
 const plotted=points.flatMap((p,i)=>i&&p.segment!==points[i-1].segment?[{t:p.t-1,home:null,away:null,draw:null},p]:[p]);
 return <section className={`soccer-final-journey tennis-journey ${inReader?'history-reader-plot soccer-history-reader':''}`} aria-label="Hull and Everton final draw against pre-match expectations">
 {!inReader&&<div className="soccer-headline-summary"><div className="hero-head"><span>SOCCER · FINAL</span><HeadlineInfo scopeKey="soccer:hull-everton:final" wide={wide} large={large}><SoccerFinalFacts/></HeadlineInfo></div><h1 className="sr-only">Hull City · Everton</h1>
 
 <div className="soccer-three-baseline"><span>○ Last pre-match · Kalshi only</span><div>{sides.map(side=><div key={side}><span>{labels[side]}</span><strong style={{color:colors[side]}}>{probabilityLabel(baseline[side])}</strong></div>)}</div></div>
 <div className="soccer-final-score"><span>Hull</span><strong>2–2</strong><span>Everton</span><b>Final · Draw</b></div>
 <p className="sr-only">Kalshi only · blended history unavailable</p>
 </div>}<div className="soccer-headline-history">{!inReader&&<div className="tennis-journey-heading"><h3>Win probability history</h3></div>}<div className="tennis-history-scopes" role="group" aria-label="Soccer history window">{(['game','pregame','all'] as const).map(s=><button key={s} aria-pressed={scope===s} onClick={()=>change(s)}>{s==='game'?'Around match':s==='pregame'?'Pre-match':'All'}</button>)}{!inReader&&<button className="match-history-expand" aria-label="Expand soccer win probability history" onClick={()=>{pin();setOpen(true)}}><ArrowTopRightIcon/></button>}</div>
 {points.length>0&&<div className="tennis-journey-plot" role="img" aria-label="Hull, draw and Everton quoted chances on a zero to 100% scale. Draw uses a dashed dark line; gaps are blank."><ResponsiveContainer width="100%" height="100%"><LineChart data={plotted} margin={{left:-12,right:34,top:16,bottom:12}}><CartesianGrid vertical={false} stroke="var(--surface-border)" strokeDasharray="3 4"/><XAxis dataKey="t" type="number" domain={['dataMin','dataMax']} tickFormatter={t=>readerClock(t)} tick={!showDates?{fontSize:11}:(d:any)=><text x={d.x} y={d.y+12} textAnchor="middle" fill="var(--text-secondary)" fontSize={11}><tspan x={d.x}>{readerTime(d.payload.value,{dateOnly:true})}</tspan><tspan x={d.x} dy={13}>{readerClock(d.payload.value)}</tspan></text>} minTickGap={50} tickCount={3} axisLine={false} tickLine={false}/><YAxis domain={[0,1]} ticks={[0,.5,1]} tickFormatter={probabilityLabel} tick={{fontSize:11}} axisLine={false} tickLine={false}/>{sides.map(side=><Line key={side} dataKey={side} stroke={colors[side]} strokeWidth={side==='draw'?3:2} strokeDasharray={side==='draw'?'6 4':undefined} connectNulls={false} dot={false} isAnimationActive={false}/>)}{selected&&<ReferenceLine x={selected.t} stroke="var(--text-secondary)" strokeDasharray="3 3"/>}</LineChart></ResponsiveContainer></div>}
 {selected&&<>{!inReader&&<div className="soccer-three-readout" aria-live="polite"><span>{selected.pregame?'○ Pre-match chances':'● Recorded after kickoff'} · {clock(selected.t)}</span><div>{sides.map(side=><strong key={side} style={{color:colors[side]}}>{labels[side]} {probabilityLabel(selected[side])}</strong>)}</div></div>}
 <div className="tennis-history-inspect"><button aria-label="Previous soccer observation" disabled={index===0} onClick={()=>choose(index-1)}>‹</button><input {...rangeGestureProps} type="range" aria-label="Soccer recorded observation" min={0} max={points.length-1} value={index} onChange={e=>choose(+e.target.value)} aria-valuetext={`${clock(selected.t)}; Hull ${probabilityLabel(selected.home)}, draw ${probabilityLabel(selected.draw)}, Everton ${probabilityLabel(selected.away)}`}/><button aria-label="Next soccer observation" disabled={index===points.length-1} onClick={()=>choose(index+1)}>›</button></div></>}
 <HistorySelectionStatus selection={selection} unavailable={unavailable} count={points.length} home="Hull" away="Everton" afterLabel="Recorded after kickoff" onLatest={()=>choose(points.length-1)}/>
 {inReader&&<details><summary>History source &amp; gaps</summary><SoccerFinalFacts/>{selected&&<p>Selected original timestamp: <code>{selected.at}</code>.</p>}</details>}
 </div>
 {!inReader&&<CardFocus memory={memory} start={open?'history':null} onClose={()=>setOpen(false)} wide={wide} large={large} readerTitle="Soccer win probability history" returnLabel="Back to match" cards={[{id:'history',name:'Win probability history',visual:<div className={large?'large-text':''}><SoccerFinalJourney inReader wide={wide} large={large}/></div>}]} anchor={<HistoryReaderContext title="Hull · Everton" result="Final · 2–2 · Draw" selected={selected?{at:selected.at,label:selected.pregame?(selected.at===baseline.at?'Last pre-match chances':'Pre-match observation'):'Recorded after kickoff',outcomes:sides.map(side=>({name:labels[side],value:selected[side],tone:side}))}:null} baseline={{at:baseline.at,label:'Last pre-match',outcomes:sides.map(side=>({name:labels[side],value:baseline[side],tone:side}))}}/>}/>}
 </section>
}
