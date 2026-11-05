import type {Dispatch,SetStateAction} from 'react';
import {CheckIcon} from '@radix-ui/react-icons';
import {outlookBands,outlookChoices,outlooksInBand,outlookPercent,suggestedOutlooks,type OutlookChoice,type OutlookPickerState} from './golfOutlookChoices';
import './golfOutlookChooser.css';
const metrics=[{index:0,label:'Win'},{index:2,label:'Top 10'},{index:4,label:'Make cut'}];
export function GolfOutlookChooser({selected,onChoose,state,setState}:{selected:string;onChoose:(name:string)=>void;state:OutlookPickerState;setState:Dispatch<SetStateAction<OutlookPickerState>>}){
 const rows=outlookChoices(),shown=state.view==='suggested'?suggestedOutlooks(selected,rows):outlooksInBand(state.band,rows);
 const card=(row:OutlookChoice)=><button className="go-choice" key={row.id} aria-pressed={selected===row.name} aria-label={`Follow ${row.name}. Recorded pre-tournament estimates: ${metrics.map(m=>`${m.label} ${outlookPercent(row.values[m.index])}`).join(', ')}.`} onClick={()=>onChoose(row.name)}>
  <span className="go-name"><strong>{row.name}</strong>{row.name===selected&&<span><CheckIcon/>Following</span>}</span>
  {row.values.every(v=>v===null)?<span className="go-unavailable">Forecast unavailable</span>:<span className="go-metrics">{metrics.map(m=><span className="go-metric" key={m.index}><span>{m.label}</span><b data-missing={row.values[m.index]===null}>{outlookPercent(row.values[m.index])}</b><span className="go-track" aria-hidden="true">{row.values[m.index]!==null&&<i style={{width:`${row.values[m.index]!*100}%`}}/>}</span></span>)}</span>}
 </button>;
 return <section className="golf-outlook-chooser" aria-label="India Championship golfers"><p className="go-intro">Choose a golfer to explore their chances.</p><div className="go-tabs" role="group" aria-label="Golfer selection view"><button aria-pressed={state.view==='suggested'} onClick={()=>setState(s=>({...s,view:'suggested'}))}>Suggested</button><button aria-pressed={state.view==='all'} onClick={()=>setState(s=>({...s,view:'all'}))}>All {rows.length}</button></div>
 {state.view==='all'?<><p className="go-subtitle">A–Z by first name</p><div className="go-bands" role="group" aria-label="First-name groups">{outlookBands.map(b=><button key={b} aria-pressed={state.band===b} onClick={()=>setState(s=>({...s,band:b}))}>{b}<span>{outlooksInBand(b,rows).length}</span></button>)}</div></>:<p className="go-subtitle">Your golfer & leading win estimates</p>}
 <p className="go-caption">Recorded before tee-off · DataGolf model</p><div className="go-list" aria-label={state.view==='all'?`Golfers ${state.band}`:'Suggested golfers'}>{shown.map(card)}</div><p className="go-note">Finishes overlap. Each bar runs from 0 to 100%. {rows.filter(r=>r.values[0]===null).length} golfers have no recorded forecast; they remain selectable.</p></section>;
}
