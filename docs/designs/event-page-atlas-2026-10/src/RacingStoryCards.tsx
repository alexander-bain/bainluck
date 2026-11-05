import {readerTime} from './readerTime';
import {PregameContext} from './PregameContext';
import {useEffect,useState} from 'react';
import {PieChart,Pie,Cell} from 'recharts';
import {ChevronLeftIcon,ChevronRightIcon} from '@radix-ui/react-icons';
import {type CatalogContext,type CatalogEvidenceRow,catalogPresentation} from './probabilityPresentation';
import {probabilityLabel} from './probabilityLabel';
import {racingStoryRows,racingStableStory,racingMatchupLabel} from './racingStoryEvidence';
import {catalogAnchor,type CatalogAnchor} from './catalogSelection';
import config from './racingStories.json';
import './racingStoryCards.css';

const time=(raw:string)=>readerTime(raw,{seconds:true});
function Track({value,selected,midpoint=false}:{value:number;selected:boolean;midpoint?:boolean}) {
 return <span className={`racing-track ${selected?'selected':''}`} aria-hidden="true"><span className="racing-track-line"/><span className="racing-track-stem" style={{width:`calc((100% - 12px) * ${value})`}}/>{midpoint&&<span className="racing-midpoint"/>}<span className="racing-dot" style={{left:`calc(6px + (100% - 12px) * ${value})`}}/></span>;
}
function useStorySelection<T extends CatalogEvidenceRow>(rows:T[],size:number,context:CatalogContext){
 const [anchor,setAnchor]=useState<CatalogAnchor<T>|null>(()=>rows[0]?catalogAnchor(rows[0]):null);
 const selection=racingStableStory(rows,anchor,size,context);
 useEffect(()=>{if(selection.present&&selection.selected&&anchor?.row!==selection.selected)setAnchor(catalogAnchor(selection.selected))},[selection.present,selection.selected,anchor]);
 return {selection,choose:(row:T)=>setAnchor(catalogAnchor(row))};
}
function StoryControls<T extends CatalogEvidenceRow>({rows,selection,choose,onPick}:{rows:T[];selection:ReturnType<typeof racingStableStory<T>>;choose:(row:T)=>void;onPick:(row:T)=>void}) {
 const {selected:row,selectedState:state,index,present,ambiguous}=selection;
 if(!row||!state)return <p className="atlas-note">No outcomes in this update.</p>;
 return <div className="racing-story-controls"><div aria-live="polite" aria-atomic="true"><strong>{row.outcome_name}</strong><p>{state.kind==='quote'?`${probabilityLabel(state.value)} · ${time(state.observedAt)}`:state.label}</p>
  {!present&&<p>{ambiguous?'This update has conflicting records for your selection.':'Your selection is not in this update.'} Original evidence remains available.</p>}</div>
  {index!==null&&rows.length>1&&<div className="racing-stepper"><button aria-label="Previous prop" disabled={index===0} onClick={()=>choose(rows[index-1])}><ChevronLeftIcon/></button><span>{index+1} of {rows.length}</span><button aria-label="Next prop" disabled={index===rows.length-1} onClick={()=>choose(rows[index+1])}><ChevronRightIcon/></button></div>}
  <button className="card-link" onClick={()=>onPick(row)}>Details &amp; timing<ChevronRightIcon/></button>
 </div>;
}
export function RacingStoryCards<T extends CatalogEvidenceRow>({rows,context,onPick}:{rows:T[];context:CatalogContext;onPick:(row:T)=>void}) {
 const podium=racingStoryRows(rows,config.source,config.podiumMarketID);
 const matchups=racingStoryRows(rows,config.source,config.matchupMarketID);
 const fastest=racingStoryRows(rows,config.source,config.fastestLapMarketID);
 return <><RacingPodium rows={podium} context={context} onPick={onPick}/><MatchupCard rows={matchups} context={context} onPick={onPick}/><FastestLapCard rows={fastest} context={context} onPick={onPick}/></>;
}
function RacingPodium<T extends CatalogEvidenceRow>({rows,context,onPick}:{rows:T[];context:CatalogContext;onPick:(row:T)=>void}) {
 const [expanded,setExpanded]=useState(false);const visible=expanded?rows:rows.slice(0,6);
 return <article className="atlas-card racing-story-card racing-podium"><h3>Finish on the podium</h3><PregameContext label="Pre-race chances"/><p className="racing-subtitle">Top 3 · independent recorded chances</p>
  <div className="racing-podium-grid">{visible.map(row=>{const state=catalogPresentation(row,context);return <button key={row.key} onClick={()=>onPick(row)} aria-label={`${row.outcome_name}, podium: ${state.kind==='quote'?probabilityLabel(state.value)+' recorded '+time(state.observedAt):state.label}`}>
   <strong>{row.outcome_name}</strong>{state.kind==='quote'?<div className="racing-ring" aria-hidden="true"><PieChart width={84} height={84}><Pie data={[{value:state.value},{value:1-state.value}]} dataKey="value" startAngle={90} endAngle={-270} innerRadius={31} outerRadius={39} stroke="none" isAnimationActive={false}><Cell fill="var(--series-home)"/><Cell fill="var(--surface-border)"/></Pie></PieChart><span>{probabilityLabel(state.value)}</span></div>:<span className="racing-unavailable">{state.label}</span>}
  </button>})}</div>
  {rows.length>6&&<button className="card-link" onClick={()=>setExpanded(!expanded)}>{expanded?'Show fewer':`Show all ${rows.length} contenders`}<ChevronRightIcon/></button>}
  <p className="atlas-note">{context.mode==='captured'?'Each chance stands alone. Quotes have different times; they are not shares of one pie.':'Every contender remains available. Last quotes are in details.'}</p>
 </article>;
}
function MatchupCard<T extends CatalogEvidenceRow>({rows,context,onPick}:{rows:T[];context:CatalogContext;onPick:(row:T)=>void}) {
 const {selection:window,choose}=useStorySelection(rows,3,context);
 return <article className="atlas-card racing-story-card racing-matchups"><h3>Race matchups</h3><PregameContext label="Pre-race chances"/><p className="racing-subtitle">Recorded chance for the named driver</p>
  <div className="racing-matchup-tiles">{window.shown.map(({row,state})=>{const pair=racingMatchupLabel(row,config.bindings),selected=window.present&&row.key===window.selected?.key;return <button key={row.key} className={selected?'selected':''} aria-pressed={selected} onClick={()=>choose(row)} aria-label={`${row.outcome_name}: ${state.kind==='quote'?probabilityLabel(state.value)+' recorded '+time(state.observedAt):state.label}`}>
   <strong>{pair?`${pair.subject} vs ${pair.opponent}`:row.outcome_name}</strong><span className="racing-matchup-readout"><span>{pair?.subject}</span><b className={state.kind==='quote'?'':'racing-missing'}>{state.kind==='quote'?probabilityLabel(state.value):state.label}</b></span>{state.kind==='quote'&&<Track value={state.value} selected={selected} midpoint/>}
  </button>})}</div>
  {window.shown.some(x=>x.state.kind==='quote')&&<p className="atlas-note">0–100% chance · center tick is 50%</p>}<StoryControls rows={rows} selection={window} choose={choose} onPick={onPick}/><p className="atlas-note">Each matchup is a separate prop. Only the supplied side is shown.</p>
 </article>;
}
function FastestLapCard<T extends CatalogEvidenceRow>({rows,context,onPick}:{rows:T[];context:CatalogContext;onPick:(row:T)=>void}) {
 const {selection:window,choose}=useStorySelection(rows,6,context);
 return <article className="atlas-card racing-story-card racing-fastest"><h3>Fastest lap</h3><PregameContext label="Pre-race chances"/><p className="racing-subtitle">A different prop from winning the race</p>
  <div className="racing-fastest-rows">{window.shown.map(({row,state})=><button key={row.key} aria-pressed={window.present&&row.key===window.selected?.key} onClick={()=>choose(row)} aria-label={`${row.outcome_name}, fastest lap: ${state.kind==='quote'?probabilityLabel(state.value)+' recorded '+time(state.observedAt):state.label}`}>
   <span className="racing-fastest-readout"><span>{row.outcome_name}</span><strong className={state.kind==='quote'?'':'racing-missing'}>{state.kind==='quote'?probabilityLabel(state.value):state.label}</strong></span>{state.kind==='quote'&&<Track value={state.value} selected={window.present&&row.key===window.selected?.key}/>}
  </button>)}</div>{window.shown.some(x=>x.state.kind==='quote')&&<div className="racing-axis" aria-hidden="true"><span>0%</span><span>50%</span><span>100%</span></div>}
  <StoryControls rows={rows} selection={window} choose={choose} onPick={onPick}/><p className="atlas-note">Recorded quotes keep their own timestamps. No missing driver or probability is estimated.</p>
 </article>;
}
