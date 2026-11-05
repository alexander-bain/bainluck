import type {Dispatch,SetStateAction,CSSProperties} from 'react';
import {MobileScroll} from './mobile';
import type {BeforeFrame} from './dunhillBefore';
import {dunhillChance} from './dunhillReading';
import {dunhillChoices,dunhillMovementScale,type DunhillChoiceState,type DunhillChoiceMode} from './dunhillChoices';
import {eventReaderTime as clock} from './eventReaderTime';
import './dunhillChooser.css';
type Entry=BeforeFrame['entries'][number];
type Frame=BeforeFrame&{domain:readonly [number,number];cohort:Entry[];colorSlots:Record<string,number>};
function MiniHistory({entry,frame}:{entry:Entry;frame:Frame}){
 const x=(t:number)=>3+(t-frame.domain[0])/(frame.domain[1]-frame.domain[0])*154,y=(p:number)=>43-p/frame.ceiling*40;
 return <svg viewBox="0 0 160 48" aria-hidden="true"><line x1="3" x2="157" y1="43" y2="43" className="dh-grid"/>{entry.segments.map((segment,i)=><g key={i}>{segment.length>1&&<path d={segment.map((p,j)=>`${j?'L':'M'}${x(p.t)},${y(p.probability)}`).join(' ')} fill="none" stroke="currentColor" strokeWidth="1.6"/>}{segment.map(p=><circle key={p.t} cx={x(p.t)} cy={y(p.probability)} r="1.3" fill="currentColor"/>)}</g>)}</svg>;
}
function MovementMark({entry,ceiling}:{entry:Entry;ceiling:number}){
 const x=80+(entry.change??0)/ceiling*70;
 return <svg viewBox="0 0 160 48" aria-hidden="true"><line x1="10" x2="150" y1="24" y2="24" className="dh-grid"/><line x1="80" x2="80" y1="8" y2="40" className="dh-change-zero"/><line x1="80" x2={x} y1="24" y2="24" stroke="currentColor" strokeWidth="9" strokeLinecap="round"/><circle cx={x} cy="24" r="5" fill="currentColor"/></svg>;
}
const modes:[DunhillChoiceMode,string][]=[['chances','Top chances'],['movement','Big movers'],['all','All golfers']];
export function DunhillChooser({frame,state,setState,pinned,choose,close}:{frame:Frame;state:DunhillChoiceState;setState:Dispatch<SetStateAction<DunhillChoiceState>>;pinned:string|null;choose:(id:string)=>void;close:()=>void}){
 const view=dunhillChoices(frame,state),changeScale=dunhillMovementScale(view.rows),selected=frame.entries.find(r=>r.id===pinned);
 const setMode=(mode:DunhillChoiceMode)=>setState(s=>({...s,mode,page:0}));
 return <div className="dh-picker dh-contextual-picker">
  <div className="dh-picker-header"><button onClick={close}>Done</button></div>
  <div className="dh-choice-modes" role="group" aria-label="Explore golfers by">{modes.map(([mode,label])=><button key={mode} aria-pressed={state.mode===mode} onClick={()=>setMode(mode)}>{label}</button>)}</div>
  <p className="dh-choice-clock">{clock.full(frame.at)} · recorded hour</p>
  <MobileScroll key={`${state.mode}/${view.band}/${view.page}`} className="dh-picker-scroll">  <p className="dh-choose-intro">Pick one to keep. We suggest the other two.</p>
  {selected&&<p className="dh-kept">Keeping <b>{selected.name}</b></p>}
  {state.mode==='all'?<div className="dh-choice-bands" role="group" aria-label="Browse by last name">{view.bands.map(b=><button key={b.label} aria-pressed={view.band===b.label} onClick={()=>setState(s=>({...s,band:b.label,page:0}))}>{b.label}<span>{b.count}</span></button>)}</div>:<p className="dh-choice-context">{state.mode==='chances'?'Highest chances recorded at this hour':'Biggest changes with trades 24 hours apart'}</p>}
<p className="dh-choice-chart-key">{state.mode==='movement'?<>← Chance fell · Chance rose →<br/>Same ±{(changeScale*100).toFixed(1)} percentage-point scale</>:<>{clock.range(frame.domain[0],frame.domain[1])} · same 0–{dunhillChance(frame.ceiling)} scale</>}</p><div className="dh-picker-grid">{view.visible.map(r=>{const i=frame.cohort.findIndex(c=>c.id===r.id),color=i<0?'var(--text-primary)':['var(--series-home)','var(--series-away)','var(--atlas-purple)'][frame.colorSlots[r.id]];return <button key={r.id} aria-pressed={pinned===r.id} aria-label={`Keep ${r.name} in chart. ${r.point?`${dunhillChance(r.point.probability)} at the selected hour`:'No trade recorded at the selected hour'}.${r.dayEarlier&&r.point?` 24 hours earlier ${dunhillChance(r.dayEarlier.probability)}.`:''}`} onClick={()=>choose(r.id)} style={{color} as CSSProperties}>
   <span className="dh-choice-name"><b>{r.name}</b>{pinned===r.id&&<small>Kept in chart</small>}</span>
   <strong data-missing={!r.point}>{dunhillChance(r.point?.probability)}</strong>
   {state.mode==='movement'?<MovementMark entry={r} ceiling={changeScale}/>:<MiniHistory entry={r} frame={frame}/>}
   <span className="dh-choice-comparison">{r.dayEarlier&&r.point?<>24h ago <b>{dunhillChance(r.dayEarlier.probability)}</b></>:!r.point?(r.points.length?'Earlier history shown':'No captured history'):'No 24h comparison'}</span>
  </button>})}</div>{!view.rows.length&&<p className="dh-choice-empty">{state.mode==='movement'?'No comparable changes at this hour. Try Top chances, or inspect a later hour.':state.mode==='chances'?'No trades recorded at this hour. Every golfer is still available under All golfers.':'No golfers in this last-name group.'}</p>}</MobileScroll>
  <div className="dh-picker-footer"><button aria-label="Previous golfers" disabled={view.page===0} onClick={()=>setState(s=>({...s,page:view.page-1}))}>Previous</button><span aria-live="polite">{view.start}–{view.end} of {view.rows.length}</span><button aria-label="Next golfers" disabled={view.page+1>=view.pages} onClick={()=>setState(s=>({...s,page:view.page+1}))}>Next</button></div>
 </div>;
}
