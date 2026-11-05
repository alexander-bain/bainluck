import {SeriesPregameChance} from './SeriesPregameChance';
import {seriesPregame,seriesPregameNote} from './seriesPregame';
import {probabilityLabel} from './probabilityLabel';
import {useState} from 'react';
import {CheckIcon,Cross2Icon,QuestionMarkCircledIcon,ChevronRightIcon,ChevronDownIcon,ChevronUpIcon} from '@radix-ui/react-icons';
import {PregameContext} from './PregameContext';
import {catalogPresentation,type CatalogEvidenceRow} from './probabilityPresentation';
import {associatedSeriesRows,seriesRecord,seriesSubject,type SeriesRow} from './associatedSeries';
import './associatedSeries.css';
export function SeriesScoreGrid<T extends CatalogEvidenceRow>({rows,selected,choose,visibleRows=rows}:{rows:T[];selected:T;choose:(row:T)=>void;visibleRows?:T[]}){
 const allowed=new Set(visibleRows.map(row=>row.key));
 return <div className="series-score-grid" role="group" aria-label="Exact series score outcomes">{['Chicago White Sox','Houston Astros'].map(team=><div className="series-team" key={team}><h4>{team}</h4>{rows.filter(row=>seriesRecord(row)?.team===team).sort((a,b)=>seriesRecord(a)!.losses!-seriesRecord(b)!.losses!).map(row=>{
  const record=seriesRecord(row)!,state=catalogPresentation(row,{status:'completed',qualityHold:false,mode:'captured'});
  return <button key={row.key} className={`series-score-tile ${state.label==='Won'?'won':''}`} aria-label={`${record.team} ${record.wins}–${record.losses} series score · ${seriesPregame(row)?probabilityLabel(seriesPregame(row)!.value)+' pre-series':'Pre-series unavailable'} · ${state.label}`} aria-pressed={selected.key===row.key} disabled={!allowed.has(row.key)} onClick={()=>choose(row)}><strong>{record.wins}–{record.losses}</strong><SeriesPregameChance row={row}/><span>{state.label==='Won'?<CheckIcon/>:state.label==='Lost'?<Cross2Icon/>:<QuestionMarkCircledIcon/>}{state.label}</span></button>;
 })}</div>)}</div>;
}
export function AssociatedSeriesCard({onPick,selectedKey,onSelection,expanded:controlledExpanded,onExpanded}:{onPick:(row:SeriesRow)=>void;selectedKey?:string;onSelection?:(key:string)=>void;expanded?:boolean;onExpanded?:(value:boolean)=>void}){
 const rows=associatedSeriesRows;
 const [localSelectedID,setLocalSelectedID]=useState('mlb-series:62898789:237333168');
 const selectedID=selectedKey??localSelectedID;
 const [localExpanded,setLocalExpanded]=useState(false);
 const expanded=controlledExpanded??localExpanded;
 const setExpanded=(value:boolean)=>{setLocalExpanded(value);onExpanded?.(value)};
 const selected=rows.find(row=>row.key===selectedID)!;
 const choose=(row:SeriesRow)=>{setLocalSelectedID(row.key);onSelection?.(row.key)};
 const scores=rows.filter(row=>seriesRecord(row)?.team!=null);
 const pending=rows.find(row=>String(row._market_id)==='62898790')!;
 return <article className="atlas-card associated-series-card" aria-label="Associated series props">
  <div className="atlas-card-head"><div><span className="eyebrow">Associated series · separate from this game</span><h3>Exact series score</h3></div></div>
  <SeriesScoreGrid rows={scores} selected={selected} choose={choose}/>
  <button className="series-pending" aria-pressed={selectedID===pending.key} onClick={()=>choose(pending)}><QuestionMarkCircledIcon/><span><strong>Over 2.5 total games</strong><small>{probabilityLabel(seriesPregame(pending)?.value??null)} pre-series · Result pending</small></span><ChevronRightIcon/></button>
  <PregameContext value={seriesPregame(selected)?.value} label="Pre-series chance" subject={seriesSubject(selected)} note={seriesPregameNote(selected)}/>
  <button className="card-link" aria-expanded={expanded} onClick={()=>setExpanded(!expanded)}>{expanded?'Hide series winners':'Explore all 9 series outcomes'}{expanded?<ChevronUpIcon/>:<ChevronDownIcon/>}</button>
  <div hidden={!expanded} className="series-winner-groups">{['kalshi','polymarket'].map(source=><div key={source}><h4>{source==='kalshi'?'Kalshi':'Polymarket'} · series winner</h4><div className="series-winners">{rows.filter(row=>row.source===source&&['62898791','63348824'].includes(String(row._market_id))).map(row=><button key={row.key} aria-pressed={selectedID===row.key} onClick={()=>choose(row)}><strong>{row.outcome_name}</strong><small>{seriesPregame(row)?probabilityLabel(seriesPregame(row)!.value)+' pre-series':'Pre-series unavailable'}</small><span>{row.is_winner?<CheckIcon/>:<Cross2Icon/>}{row.is_winner?'Won':'Lost'}</span></button>)}</div></div>)}</div>
  <button className="card-link series-detail" onClick={()=>onPick(selected)}>Selected prop details<ChevronRightIcon/></button>
 </article>;
}
