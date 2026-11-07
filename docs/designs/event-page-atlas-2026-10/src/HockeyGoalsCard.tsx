import {rangeGestureProps} from './rangeGesture';
import {useState} from 'react';
import {ResponsiveContainer} from './ChartVisibility';
import {ScatterChart, Scatter, XAxis, YAxis, CartesianGrid, ReferenceLine} from 'recharts';
import {CircleIcon,CheckIcon,Cross2Icon,ChevronLeftIcon,ChevronRightIcon} from '@radix-ui/react-icons';
import {hockeyEvidence as wire,hockeyPregame,hockeyClock} from './hockeyEvidence';
import {probabilityLabel} from './probabilityLabel';
import {catalogPresentation} from './probabilityPresentation';
export function HockeyGoalsCard({onPick,selectedKey,onSelection}:{onPick:(row:any)=>void;selectedKey?:string;onSelection?:(key:string)=>void}){
 const [localKey,setLocalKey]=useState(()=>wire.points.find(p=>p.count===6)!.key);const key=selectedKey??localKey,setKey=onSelection??setLocalKey,selected=wire.points.find(p=>p.key===key)!,index=wire.points.indexOf(selected),baseline=hockeyPregame(selected.original),result=catalogPresentation(selected.original,{status:'completed',qualityHold:false,mode:'stale'}).label;
 const dots=wire.points.map(p=>({x:p.count,y:hockeyPregame(p.original)?.value??null}));
 return <article className="atlas-card hockey-goals" aria-label="Hockey goals against pregame expectations">
  <div className="atlas-card-head"><div><span className="eyebrow">Kalshi · total goals</span><h3>How many goals felt likely?</h3></div><div className="player-final"><strong>{wire.actual}</strong><span>FINAL GOALS</span></div></div>
  <p className="axis-caption">Pregame chance of reaching each total</p>
  <div className="live-profile-plot" role="img" aria-label={`Nine original goal milestones. Hollow circles show pregame probabilities. A black rule marks five final goals. Selected ${selected.count} or more: ${probabilityLabel(baseline?.value)} pregame. Current probability unavailable.`}>
   <ResponsiveContainer width="100%" height="100%"><ScatterChart margin={{top:26,bottom:3,left:-16,right:17}}>
    <CartesianGrid vertical={false} stroke="var(--surface-border)" strokeDasharray="3 4"/>
    <XAxis dataKey="x" type="number" domain={[1,11]} ticks={[2,4,6,8,10]} axisLine={false} tickLine={false} tick={{fontSize:11}}/>
    <YAxis dataKey="y" type="number" domain={[0,1]} ticks={[0,.5,1]} tickFormatter={probabilityLabel} axisLine={false} tickLine={false} tick={{fontSize:11}}/>
    <ReferenceLine x={wire.actual} stroke="var(--text-primary)" strokeWidth={3} label={{value:'5 final',position:'top',fontSize:11,fill:'var(--text-primary)'}}/>
    <Scatter data={dots.filter(p=>p.y!==null)} isAnimationActive={false} shape={(p:any)=><circle cx={p.cx} cy={p.cy} r={p.payload.x===selected.count?7:4.5} fill="white" stroke="var(--series-home)" strokeWidth={p.payload.x===selected.count?3:2}/>}/>
   </ScatterChart></ResponsiveContainer>
  </div>
  <div className="hockey-key"><span><CircleIcon/> Pregame chance</span><span>┃ Final goals</span></div>
  <div className="hockey-selected"><strong>{selected.count}+ goals</strong><span>{wire.actual>=selected.count?'Reached in final score':`Finished ${selected.count-wire.actual} short`}</span></div>
  <div className="hockey-chance"><strong>{probabilityLabel(baseline?.value)}</strong><div>Pregame chance<br/><small>{baseline?hockeyClock(baseline.at):'Baseline unavailable'}</small></div></div>
  <label className="hockey-slider">Goal milestone<input {...rangeGestureProps} type="range" min={0} max={wire.points.length-1} value={index} onChange={e=>setKey(wire.points[+e.target.value].key)} aria-label="Hockey goal milestone" aria-valuetext={`${selected.count} or more goals, pregame chance ${probabilityLabel(baseline?.value)}${baseline?'; '+hockeyClock(baseline.at):''}; final ${wire.actual} goals; ${result}`}/></label>
  <div className="hockey-step"><button disabled={index===0} onClick={()=>setKey(wire.points[index-1].key)} aria-label="Previous goal milestone"><ChevronLeftIcon/></button><span>{selected.count}+ goals · {index+1} of {wire.points.length}</span><button disabled={index===wire.points.length-1} onClick={()=>setKey(wire.points[index+1].key)} aria-label="Next goal milestone"><ChevronRightIcon/></button></div>
  <p className="hockey-result">{result==='Won'?<CheckIcon/>:result==='Lost'?<Cross2Icon/>:null} Contract result: <strong>{result}</strong></p>
  <p className="atlas-note">Minnesota 4–1 Boston. Final score observed {hockeyClock(wire.actualAt)}. Each circle is an offered milestone, not an exact-goal prediction.</p>
  <button className="card-link" onClick={()=>onPick(selected.original)}>Details & timing <ChevronRightIcon/></button>
 </article>
}
