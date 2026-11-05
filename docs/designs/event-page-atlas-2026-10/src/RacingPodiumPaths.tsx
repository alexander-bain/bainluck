import * as Dialog from '@radix-ui/react-dialog';
import {BottomSheet} from './mobile';
import {ComposedChart,Scatter,XAxis,YAxis,CartesianGrid,ReferenceLine,LabelList} from 'recharts';
import {CircleIcon,SquareIcon,ChevronLeftIcon,ChevronRightIcon,ChevronRightIcon as OpenIcon} from '@radix-ui/react-icons';
import {ResponsiveContainer} from './ChartVisibility';
import {probabilityLabel as pct} from './probabilityLabel';
import {eventReaderTime} from './eventReaderTime';
import {podiumPathDrivers,defaultPathDriver,pathSnapshot,pathWindow,pathBaseline,pathPlace,pathShortName} from './racingPodiumEvidence';
import {useStoryState} from './StorySession';
import './racingPodiumPaths.css';
export function RacingPodiumPaths({stage,onPick}:{stage:number;onPick:(key:string)=>void}){
 const [selected,setSelected]=useStoryState('race-live','podiumPathDriver',defaultPathDriver);
 const driver=podiumPathDrivers.find(d=>d.id===selected);const state=driver&&pathSnapshot(driver,stage);
 if(!driver||!state)return null;
 const shown=pathWindow(selected),index=podiumPathDrivers.indexOf(driver);
 const points=(kind:'win'|'podium')=>shown.flatMap((d,y)=>{const b=pathBaseline(d[kind]);return b?[{x:b.value,y,id:d.id,name:d.name,label:d.id===selected?pct(b.value):''}]:[]});
 const pick=(point:unknown)=>{if(point&&typeof point==='object'&&'id'in point&&typeof point.id==='string'&&podiumPathDrivers.some(d=>d.id===point.id))setSelected(point.id)};
 return <article className="atlas-card race-paths"><h3>Win and podium chances</h3><p className="race-caption">A podium means finishing in the top three.</p><div className="path-key"><strong>Pre-race chances</strong><span><CircleIcon/>Win</span><span><SquareIcon/>Podium</span></div>
 <div className="path-plot" role="img" aria-label={`Pre-race win and podium chances for ${shown.map(d=>d.name).join(', ')}. Zero to one hundred percent. Selected ${driver.name}: win ${pct(state.win.baseline?.value)}, podium ${pct(state.podium.baseline?.value)}.`}>
 <ResponsiveContainer width="100%" height="100%"><ComposedChart margin={{left:0,right:12,top:22,bottom:0}}>
 <CartesianGrid horizontal={false} stroke="var(--surface-border)"/>
 <XAxis type="number" dataKey="x" domain={[0,1]} ticks={[0,.5,1]} tickFormatter={pct} tick={{fontSize:11}} axisLine={false} tickLine={false}/>
 <YAxis type="number" dataKey="y" domain={[-.5,shown.length-.5]} ticks={shown.map((_,i)=>i)} reversed tickFormatter={i=>shown[i]?pathShortName(shown[i].name):''} width={80} tick={{fontSize:12}} axisLine={false} tickLine={false}/>
 {shown.map((d,i)=>{const a=pathBaseline(d.win),b=pathBaseline(d.podium);return a&&b?<ReferenceLine key={d.id} segment={[{x:a.value,y:i},{x:b.value,y:i}]} stroke={selected===d.id?'var(--text-secondary)':'var(--surface-border)'} strokeWidth={selected===d.id?2:1}/>:null})}
 <Scatter name="Win" data={points('win')} shape="circle" fill="var(--surface-card)" stroke="var(--series-home)" strokeWidth={2.5} isAnimationActive={false} onClick={pick}><LabelList dataKey="label" position="top" offset={10} fill="var(--series-home)" fontSize={12}/></Scatter>
 <Scatter name="Podium" data={points('podium')} shape="square" fill="var(--surface-card)" stroke="var(--series-away)" strokeWidth={2.5} isAnimationActive={false} onClick={pick}><LabelList dataKey="label" position="top" offset={10} fill="var(--series-away)" fontSize={12}/></Scatter>
 </ComposedChart></ResponsiveContainer></div>
 <div className="path-select"><button aria-label="Previous podium driver" disabled={index===0} onClick={()=>setSelected(podiumPathDrivers[index-1].id)}><ChevronLeftIcon/></button><div aria-live="polite"><strong>{driver.name}</strong><span>{state.phase==='final'?`Actual finish · ${state.position===null?'Unavailable':pathPlace(state.position)}`:state.phase==='before'?'Before the race':'No recent probability update'}</span></div><button aria-label="Next podium driver" disabled={index===podiumPathDrivers.length-1} onClick={()=>setSelected(podiumPathDrivers[index+1].id)}><ChevronRightIcon/></button></div>
 <div className="path-chances">{(['win','podium'] as const).map(kind=><button key={kind} onClick={()=>onPick(state[kind].key)} aria-label={`${driver.name}, ${kind==='win'?'win':'finish top three'}: ${pct(state[kind].baseline?.value)} pre-race. Open original prop.`}><span>{kind==='win'?<CircleIcon/>:<SquareIcon/>}{kind==='win'?'Win':'Finish top 3'}<OpenIcon/></span><strong>{pct(state[kind].baseline?.value)}</strong><small>Pre-race{state.phase==='final'?` · ${state[kind].result===true?'Won':state[kind].result===false?'Lost':'Unconfirmed'}`:''}</small></button>)}</div>
 <details className="path-disclosure"><summary>How to read this comparison</summary><p>{index+1} of {podiumPathDrivers.length} identity-matched drivers. Arrows visit every paired driver; all 75 originals remain in the catalog.</p><p>Hollow marks are pre-race trades for two separate markets. They are independently timed; the connecting line is a visual comparison, not a combined probability. Missing probabilities stay blank.</p>{(['win','podium']as const).map(k=><p key={k}>{k==='win'?'Win':'Podium'}: {state[k].baseline?eventReaderTime.full(state[k].baseline!.at,true):'No qualifying pre-race trade'}.</p>)}</details>
 </article>;
}

export function RacingPathDetails({originalKey,stage,wide,large,onClose}:{originalKey:string|null;stage:number;wide:boolean;large:boolean;onClose:()=>void}){
 const driver=podiumPathDrivers.find(d=>d.win.key===originalKey||d.podium.key===originalKey),snapshot=driver&&pathSnapshot(driver,stage),kind=driver?.win.key===originalKey?'win':'podium',row=driver?.[kind],fact=snapshot?.[kind];
 const content=row&&fact?<div className="path-detail"><h3>{row.name} · {kind==='win'?'Win the race':'Finish on the podium'}</h3><strong>{pct(fact.baseline?.value)} pre-race</strong><p>{fact.baseline?`Trade recorded ${eventReaderTime.full(fact.baseline.at,true)}.`:'No qualifying pre-race trade was captured.'}</p><p>{snapshot?.phase==='final'?`Market result: ${fact.result===true?'Won':fact.result===false?'Lost':'Unconfirmed'}.`:'No result shown in this earlier view.'}</p><p>Current probability unavailable. Historical chances stay separate from current probabilities.</p><p>{row.rules}</p><details><summary>Original contract identity</summary><p>Polymarket market {row.sourceMarketID} · selected {row.selected}</p><p>{row.conditionID}</p></details></div>:null;
 return wide?<Dialog.Root open={!!originalKey} onOpenChange={open=>{if(!open)onClose()}}><Dialog.Portal><Dialog.Overlay className="cf-overlay"/><Dialog.Content className={`path-modal ${large?'large-text':''}`} aria-describedby={undefined}><Dialog.Title>Prop details</Dialog.Title><button onClick={onClose}>Done</button>{content}</Dialog.Content></Dialog.Portal></Dialog.Root>:<BottomSheet open={!!originalKey} onOpenChange={open=>{if(!open)onClose()}} title="Prop details"><div className={large?'large-text':''}><button className="race-more" onClick={onClose}>Done</button>{content}</div></BottomSheet>;
}
