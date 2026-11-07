import {useDenseCardLayout} from './useDenseCardLayout';
import {ProjectionJourneyCard,projectionFor} from './ProjectionJourneyCard';
import { useState } from 'react';
import {selectedProfilePoint} from './profileSelection';
import {ResponsiveContainer} from './ChartVisibility';
import {LineChart, Line, XAxis, YAxis, ReferenceLine, ReferenceArea} from 'recharts';
import { ChevronLeftIcon, ChevronRightIcon } from '@radix-ui/react-icons';
import profiles from './profiles.json';
import { TemporalKey, ForecastCard, TouchdownCard } from './VarietyCards';
type Profile = typeof profiles[number];
export function ExpectationProfiles({phase,onDetail}:{phase:string;onDetail:(key:string)=>void}){
 const denseRef=useDenseCardLayout();
 const [view,setView]=useState('Stories');
 return <section className="expectation-section"><div className="expectation-heading"><div><span className="eyebrow">THE GAME AGAINST EXPECTATIONS</span><h2>{phase==='Final'?'The game the market didn’t see':'What would an exceptional game look like?'}</h2></div><div className="segment card-view">{['Stories','All profiles'].map(v=><button key={v} className={v===view?'active':''} onClick={()=>setView(v)}>{v}</button>)}</div></div><TemporalKey/><p className="time-caveat">{phase==='Final'?'Final actuals against archived pregame expectations. No live probabilities are shown.':'Archived pregame reference. In-game player probabilities and progress are unavailable in this capture.'}</p><div ref={denseRef} className={view==='Stories'?'variety-grid':'profile-grid'}>{phase==='Final'&&<ProjectionJourneyCard bundle={projectionFor('nfl')!}/>} {view==='Stories'?<><ProfileChart profile={profiles[0]} final={phase==='Final'} onDetail={onDetail}/>{phase!=='Final'&&<ForecastCard final={false}/>}<TouchdownCard final={phase==='Final'} onDetail={onDetail}/></>:profiles.map(p=><ProfileChart key={p.name} profile={p} final={phase==='Final'} onDetail={onDetail}/>)}</div><div className="baseline-note">Player probabilities: Kalshi · archived pregame baselines; some may be opening quotes. Each dot is a quoted milestone, not an estimated distribution.</div></section>
}
export function ProfileChart({profile:p,final,onDetail,selection}:{profile:Profile;final:boolean;onDetail:(key:string)=>void;selection?:{rowKey:string;onSelect:(key:string)=>void}}){
 const [localKey,setLocalKey]=useState(p.points.find(d=>d.x===p.focus)!.row_key);
 const selected=selectedProfilePoint(p.points,selection?.rowKey??localKey);
 const choose=(key:string)=>selection?selection.onSelect(key):setLocalKey(key);
 if(!selected)return <article className="expectation-profile"><h3>{p.name}</h3><p>Selected milestone unavailable</p><p>The selected prop is no longer in this card.</p></article>;
 const index=p.points.findIndex(point=>point.row_key===selected.row_key);
 const setIndex=(next:number)=>{const point=p.points[next];if(point)choose(point.row_key)};
 const color=p.team==='Bears'?'var(--series-home)':'var(--series-away)';
 const max=p.stat==='Receiving Yards'?160:p.points.at(-1)!.x;
 const min=p.stat==='Passing Yards'?100:0;
 const ticks=p.stat==='Passing Yards'?[100,150,200,250,300,350]:[0,40,80,120,160].filter(x=>x<=max);
 const percent=(n:number)=>Number((n*100).toFixed(1))+'%';
 return <article className="expectation-profile" style={{'--profile-color':color} as React.CSSProperties}>
  <div className="profile-top"><div><span className="profile-stat">{p.team} · {p.stat}</span><h3>{p.name}</h3></div>{final&&<div className="actual-number"><strong>{p.actual}</strong><span>yards · final</span></div>}</div>
  <p className="card-caption">Pregame chance to reach each milestone</p><div className="expectation-plot" role="img" aria-label={`${p.name}, ${p.stat}. ${final?'Final '+p.actual+' yards. ':''}Recorded pregame chances at ${p.points.length} offered milestones. Select a milestone below for its exact probability.`}>
  <ResponsiveContainer width="100%" height="100%"><LineChart data={p.points} margin={{left:0,right:20,top:25,bottom:0}}>
   <XAxis type="number" dataKey="x" domain={[min,max]} ticks={ticks} tick={{fontSize:11,fill:'var(--text-secondary)'}} axisLine={false} tickLine={false} height={25}/>
   <YAxis type="number" domain={[0,1]} ticks={[0,.5,1]} tickFormatter={n=>`${n*100}%`} tick={{fontSize:10,fill:'var(--text-secondary)'}} width={34} axisLine={false} tickLine={false}/>
   {final&&<ReferenceArea x1={min} x2={p.actual} fill={color} fillOpacity={.055}/>}
   <ReferenceLine y={.5} stroke="var(--text-muted)" strokeDasharray="3 4" strokeOpacity={.45}/>
   <ReferenceLine y={0} stroke="var(--surface-border)"/>
   {final&&<ReferenceLine x={p.actual} stroke={color} strokeWidth={2} label={{value:`${p.actual} YD · FINAL`,position:'top',fill:color,fontSize:11,fontWeight:700}}/>}
   {p.points.map(point=><ReferenceLine key={point.row_key} segment={[{x:point.x,y:0},{x:point.x,y:point.p}]} stroke={point.row_key===selected.row_key?color:'var(--text-muted)'} strokeWidth={point.row_key===selected.row_key?2:1.5} strokeOpacity={point.row_key===selected.row_key?.6:.3}/>)}
   <Line dataKey="p" stroke="none" isAnimationActive={false} activeDot={false} dot={(props:any)=>{
    const {cx,cy,payload}=props; const active=payload.x===selected.x;const labelLeft=(final&&payload.x<=p.actual)||payload.x>max*.8;
    return <g key={payload.row_key} style={{cursor:'pointer'}} onClick={()=>setIndex(p.points.findIndex(d=>d.x===payload.x))}><circle cx={cx} cy={cy} r={active?6:4} fill='var(--surface-card)' stroke={active?color:'var(--text-muted)'} strokeWidth={1.5}/>{active&&<text x={cx+(labelLeft?-9:9)} y={cy-13} textAnchor={labelLeft?'end':'start'} fill={color} fontSize={12} fontWeight={750}>{percent(payload.p)}</text>}</g>
   }}/>
  </LineChart></ResponsiveContainer></div>
  <div className="milestone-readout"><button aria-label={`Previous milestone for ${p.name}`} disabled={index===0} onClick={()=>setIndex(index-1)}><ChevronLeftIcon/></button><button className="milestone-detail" onClick={()=>onDetail(selected.row_key)}><strong>{selected.x}+ yards <span>{percent(selected.p)} pregame</span></strong><span>{final?(selected.hit?'Reached':'Not reached'):'Archived expectation'} · View quote</span></button><button aria-label={`Next milestone for ${p.name}`} disabled={index===p.points.length-1} onClick={()=>setIndex(index+1)}><ChevronRightIcon/></button></div>
 </article>
}
