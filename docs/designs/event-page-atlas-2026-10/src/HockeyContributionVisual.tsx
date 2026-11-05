import {BarChart,Bar,Cell,XAxis,YAxis,CartesianGrid,LabelList} from 'recharts';
import {ResponsiveContainer} from './ChartVisibility';
import {ChevronRightIcon,CheckCircledIcon,CrossCircledIcon} from '@radix-ui/react-icons';
import type {ContributionKind} from './hockeyContributions';
import {probabilityLabel as pct} from './probabilityLabel';
import {eventReaderTime as clock} from './eventReaderTime';
import './hockeyContributions.css';
export const contributionTitles={points:'Points in context',assists:'Who set them up?'};
export type ContributionSelection={player:string;threshold:number};
export type ContributionVisualProfile<T>={name:string;team?:string|null;records:{key:string;threshold:number;baseline:{value:number;at:string}|null;actual:{team:string;goals:number;assists:number;points:number}|null;result:string|null;row:T}[]};
export function HockeyContributionVisual<T,>({profiles,kind,phase,selection,onSelection,onPick,playersOpen,onPlayersOpen,large=false}:{profiles:ContributionVisualProfile<T>[];kind:ContributionKind;phase:'before'|'final';selection:ContributionSelection;onSelection:(s:ContributionSelection)=>void;onPick:(r:T)=>void;playersOpen:boolean;onPlayersOpen:(open:boolean)=>void;large?:boolean}){
 const profile=profiles.find(p=>p.name===selection.player)??profiles[0];
 if(!profile)return <article className="atlas-card"><h3>{contributionTitles[kind]}</h3><p>Probability evidence unavailable. Every original remains in All props.</p></article>;
 const selected=profile.records.find(r=>r.threshold===selection.threshold)??profile.records[0],actual=phase==='final'?selected.actual:null,count=actual?.[kind]??null,result=phase==='final'?selected.result:null;
 const data=profile.records.map(r=>({threshold:r.threshold,chance:r.baseline?.value??null}));
 const unit=count===1?(kind==='points'?'point':'assist'):kind;
 const horizontal=kind==='assists',select=(threshold:number)=>onSelection({player:profile.name,threshold});
 const label=(p:any)=>{if(typeof p.value!=='number')return <g/>;return <text x={horizontal?p.x+p.width+7:p.x+p.width/2} y={horizontal?p.y+p.height/2+5:p.y-9} textAnchor={horizontal?'start':'middle'} fill="var(--text-primary)" fontSize={large?17:14} fontWeight={700}>{pct(p.value)}</text>};
 const missing=profile.records.filter(r=>r.baseline===null).map(r=>r.threshold+'+');
 return <article className={`atlas-card hc-card hc-${kind}`} aria-label={`Hockey player ${kind} against pre-game expectations`}>
  <div className="atlas-card-head"><div><span className="eyebrow">PLAYER {kind.toUpperCase()}</span><h3>{phase==='before'?(kind==='points'?'Points to watch':'Who could set them up?'):contributionTitles[kind]}</h3></div>{phase==='final'&&<div className="hc-actual"><strong>{count??'—'}</strong><span>FINAL {kind.toUpperCase()}</span></div>}</div>
  <div className="hc-player"><strong>{profile.name}</strong>{(profile.team||phase==='final')&&<span>{profile.team??actual?.team??'Team unavailable'}</span>}</div>
  <p className="hc-definition">{kind==='points'?'One point for each goal or assist.':'An assist credits a player who helped create a goal.'}</p>
  <p className="hc-chart-key">Pre-game chances · at least this many {kind}</p>
  <div className="hc-chart" role="img" aria-label={`${profile.name}. Pre-game chances of at least each ${kind} milestone on a zero to 100% scale: ${profile.records.map(r=>r.threshold+' or more, '+(r.baseline?pct(r.baseline.value):'unavailable')).join('; ')}. ${phase==='final'?`Final actual: ${count??'unavailable'} ${unit}. Actual count is separate from probabilities.`:'Before game. Later results and counts are hidden.'}`}>
   <ResponsiveContainer width="100%" height="100%"><BarChart data={data} layout={horizontal?'vertical':'horizontal'} margin={horizontal?{top:9,right:52,left:0,bottom:0}:{top:26,right:12,left:-16,bottom:0}} barCategoryGap="35%">
    <CartesianGrid vertical={horizontal} horizontal={!horizontal} stroke="var(--surface-border)" strokeDasharray="3 4"/>
    {horizontal?<><XAxis type="number" domain={[0,1]} ticks={[0,.5,1]} tickFormatter={pct} tick={{fontSize:large?14:11}} axisLine={false} tickLine={false}/><YAxis type="category" dataKey="threshold" width={92} tickFormatter={n=>n+'+'+(data.find(r=>r.threshold===n)?.chance===null?' · unavailable':'')} tick={{fontSize:large?14:11}} axisLine={false} tickLine={false}/></>:<><XAxis type="category" dataKey="threshold" height={48} tick={(p:any)=><text x={p.x} y={p.y+16} textAnchor="middle" fill="var(--text-secondary)" fontSize={large?16:13}><tspan>{p.payload.value}+</tspan>{data.find(r=>r.threshold===p.payload.value)?.chance===null&&<tspan x={p.x} dy={17} fontSize={large?12:10}>Unavailable</tspan>}</text>} axisLine={false} tickLine={false}/><YAxis type="number" domain={[0,1]} ticks={[0,.5,1]} tickFormatter={pct} tick={{fontSize:large?14:11}} axisLine={false} tickLine={false}/></>}
    <Bar dataKey="chance" name="Pre-game chance" fill="var(--surface-card)" stroke={horizontal?'var(--series-away)':'var(--series-home)'} radius={horizontal?[0,5,5,0]:[5,5,0,0]} isAnimationActive={false} onClick={(_r,index)=>select(data[index].threshold)}>{data.map(r=><Cell key={r.threshold} strokeWidth={r.threshold===selected.threshold?3:1.5} strokeDasharray={horizontal?'5 3':undefined}/>)}<LabelList dataKey="chance" content={label}/></Bar>
   </BarChart></ResponsiveContainer>
  </div>
  {missing.length>0&&<p className="hc-gap">{missing.join(', ')} · pre-game chance unavailable</p>}
  <div className="hc-thresholds" role="group" aria-label={`${profile.name} ${kind} milestone`}>{profile.records.map(r=><button key={r.key} aria-pressed={r.key===selected.key} onClick={()=>select(r.threshold)}>{r.threshold}+ {kind}</button>)}</div>
  <div className="hc-selected"><div><span>Pre-game chance · {selected.threshold}+ {kind}</span><strong>{selected.baseline?pct(selected.baseline.value):'Unavailable'}</strong></div>{phase==='final'&&<div className="hc-grade">{result==='Reached'?<CheckCircledIcon/>:result==='Missed'?<CrossCircledIcon/>:null}<b>{result??'Result unconfirmed'}</b><span>{count===null?'Exact final count unavailable':`${count} final ${unit}`}</span></div>}</div>
  {actual&&<p className="hc-actual-note">{kind==='points'?`${actual.goals} ${actual.goals===1?'goal':'goals'} + ${actual.assists} ${actual.assists===1?'assist':'assists'} = ${actual.points} points`:`${actual.assists} ${actual.assists===1?'assist':'assists'} in the final box score`}</p>}
  <p className="hc-time">{selected.baseline?'Recorded '+clock.full(selected.baseline.at):'No captured pre-game trade for this milestone'}</p>
  <details className="hc-players" open={playersOpen} onToggle={e=>onPlayersOpen(e.currentTarget.open)}><summary>Choose player · {profiles.length}</summary><div>{profiles.map(p=><button key={p.name} aria-pressed={p.name===profile.name} onClick={()=>onSelection({player:p.name,threshold:p.records.some(r=>r.threshold===selected.threshold)?selected.threshold:p.records[0].threshold})}>{p.name}</button>)}</div></details>
  <button className="card-link" onClick={()=>onPick(selected.row)}>Details & recorded time <ChevronRightIcon/></button>
 </article>;
}
