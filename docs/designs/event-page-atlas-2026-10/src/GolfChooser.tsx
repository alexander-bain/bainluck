import {golfReadout,beforeMovement} from './golfReadable';
import type {Dispatch,SetStateAction,CSSProperties} from 'react';
import {CheckIcon,ChevronDownIcon,ChevronUpIcon} from '@radix-ui/react-icons';
import {chance,journeyNames,journeyClock,journeyWire,type JourneyWindow} from './golfJourneyEvidence';
import {chanceMovement,choiceWindow,golfChoice,golfChoices,golferBands,golfersInBand,type GolfPickerState} from './golfChoiceEvidence';
import {golfChoiceFrame,golfChoicePreview} from './golfChoicePreview';
import './golfChooser.css';
type Choice=NonNullable<ReturnType<typeof golfChoice>>;
export function GolfChooser({selected,period,through,onChoose,state,setState,pinned=true}:{selected:string;period:JourneyWindow;through?:string;pinned?:boolean;onChoose:(name:string)=>void;state:GolfPickerState;setState:Dispatch<SetStateAction<GolfPickerState>>}){
 const {inChart,more,available}=golfChoices(selected,period,through),window=choiceWindow(period);
 const frame=golfChoiceFrame(period,through);
 const colorFor=(name:string)=>`var(--golf-series-${journeyWire.history.outcomes.findIndex(r=>r.name===name)+1}, var(--text-muted))`;
 const preview=(row:Choice)=>{
  const p=golfChoicePreview(row.name,period,frame,through),color=colorFor(row.name);
  if(!p.last)return <span className="gc-no-preview">No captured history</span>;
  const x=(v:number)=>8+v*126,y=(v:number)=>6+v*60;
  return <div className="gc-preview-wrap" aria-hidden="true" style={{color}}><svg className="gc-preview" viewBox="0 0 142 72">
   <line x1="8" x2="134" y1="66" y2="66" className="gc-zero"/>
   {period!=='Pre'&&p.baselineY!==null&&<line x1="8" x2="134" y1={y(p.baselineY)} y2={y(p.baselineY)} className="gc-baseline"/>}
   {period!=='Pre'&&p.gaps.map((g,i)=><g key={i} className="gc-gap"><line x1={x((g.from+g.to)/2)-3} x2={x((g.from+g.to)/2)} y1="69" y2="63"/><line x1={x((g.from+g.to)/2)} x2={x((g.from+g.to)/2)+3} y1="69" y2="63"/></g>)}
   {p.segments.map((segment,i)=>segment.length===1?<circle key={i} cx={x(segment[0].x)} cy={y(segment[0].y)} r="2" fill="currentColor"/>:<polyline key={i} points={segment.map(point=>`${x(point.x)},${y(point.y)}`).join(' ')} fill="none" stroke="currentColor" strokeWidth="2" strokeLinejoin="round"/>)}
   <circle cx={x(p.last.x)} cy={y(p.last.y)} r="3.2" fill="currentColor"/>
  </svg><span>0–{chance(frame.ceiling)} chance</span></div>;
 };
 const pick=(row:Choice,chart=false)=><button key={row.id} className={`gc-choice ${chart?'gc-in-chart':''} ${row.last?'':'gc-missing'}`} style={{'--gc-series':colorFor(row.name)} as CSSProperties} aria-pressed={row.name===selected} aria-label={`Keep ${row.name} in chart. ${period==='Pre'?'':`Before tournament ${chance(row.baseline?.probability)}.`} ${row.last?`Last in ${window} ${chance(row.last.probability)}, recorded ${journeyClock(row.last.timestamp)}`:'No history in this view'}. ${period==='Pre'?beforeMovement(golfReadout(row.name,period,through).change):chanceMovement(row.change)}.`} onClick={()=>onChoose(row.name)}>
  <div className="gc-name"><strong>{row.name}</strong>{row.name===selected&&<span><CheckIcon/>{pinned?'Kept in view':'In focus'}</span>}</div><div className="gc-visual"><div className="gc-chances">{period!=='Pre'&&<div><span>Before tournament</span><b>{chance(row.baseline?.probability)}</b></div>}<div><span>{period==='Pre'?'Last recorded':`Last in ${window}`}</span><b>{row.last?chance(row.last.probability):'Unavailable'}</b></div></div>{preview(row)}</div>
  <div className="gc-movement">{row.last?<><span>{(period==='Pre'?beforeMovement(golfReadout(row.name,period,through).change):chanceMovement(row.change)).replace('percentage points','pts')}</span><time>{journeyClock(row.last.timestamp)}</time></>:<span>No captured history in this view</span>}</div>
 </button>;
 return <section className="golf-chooser" aria-label="Choose chart golfers"><p className="gc-intro">Pick one to keep. We suggest the other two.</p>
  <h3>In your chart <span>3 maximum</span></h3><p className="gc-chart-key">{window} history · same time &amp; scale{period!=='Pre'&&<><br/><span>Dashed line: before tournament</span></>}</p><div className="gc-choices">{inChart.map(r=>pick(r,true))}</div>
  <p className="gc-context">{window} · {available} of {journeyNames.length} golfers have history in this view. Values are separately timed estimates.</p>
  {more.length>0&&<><button className="gc-disclosure" aria-expanded={state.more} onClick={()=>setState(s=>({...s,more:!s.more}))}>More with recorded history · {more.length}{state.more?<ChevronUpIcon/>:<ChevronDownIcon/>}</button>{state.more&&<div className="gc-choices" aria-label="More recorded golfers">{more.map(r=>pick(r))}</div>}</>}
  <button className="gc-disclosure" aria-expanded={state.all} onClick={()=>setState(s=>({...s,all:!s.all}))}>Browse all {journeyNames.length} golfers{state.all?<ChevronUpIcon/>:<ChevronDownIcon/>}</button>
  {state.all&&<div className="gc-field"><p>By last name · a golfer stays selectable when history is missing.</p><div className="gc-bands" aria-label="Last-name groups">{golferBands.map(b=><button key={b} aria-pressed={state.band===b} onClick={()=>setState(s=>({...s,band:b}))}>{b}<span>{golfersInBand(b).length}</span></button>)}</div><div className="gc-field-list" aria-label={`Golfers ${state.band}`}>{golfersInBand(state.band).map(name=>{const row=golfChoice(name,period,through)!;return <button key={row.id} aria-pressed={name===selected} onClick={()=>onChoose(name)}><strong>{name}</strong><span>{name===selected?<><CheckIcon/>{pinned?'Kept in view':'In focus'}</>:row.last?'Recorded history available':'History unavailable in this view'}</span></button>})}</div></div>}
 </section>;
}
