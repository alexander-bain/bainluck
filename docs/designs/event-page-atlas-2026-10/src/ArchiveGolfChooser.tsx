import {useLayoutEffect,useMemo,useRef,useState} from 'react';
import {CheckIcon,ChevronDownIcon,ChevronLeftIcon,ChevronRightIcon,CrossCircledIcon} from '@radix-ui/react-icons';
import {archiveGolfBands,archiveGolfBand,archiveGolfChoices,archiveGolfSuggestions,archiveGolfPage,archiveGolfGroup,archiveGolfFrame,archiveGolfPreview,type ArchiveGolfRole} from './archiveGolfChoices';
import {readerTime} from './readerTime';
import {probabilityLabel as pct} from './probabilityLabel';
import './archiveGolfChooser.css';
export function ArchiveGolfChooser({role,selected,label,onChoose}:{role:ArchiveGolfRole;selected:string;label:string;onChoose:(id:string)=>void}){
 const [open,setOpen]=useState(false),[all,setAll]=useState(false),[band,setBand]=useState(archiveGolfBand('A')),[page,setPage]=useState(0),trigger=useRef<HTMLButtonElement>(null),returning=useRef(false);
 const rows=useMemo(()=>archiveGolfChoices(role),[role]),suggestions=useMemo(()=>archiveGolfSuggestions(rows,role),[rows,role]),frame=useMemo(()=>archiveGolfFrame(rows),[rows]);
 const current=rows.find(r=>r.id===selected),slice=archiveGolfPage(rows,band,page),shown=all?slice.rows:suggestions;
 useLayoutEffect(()=>{if(returning.current&&!open){returning.current=false;trigger.current?.focus({preventScroll:true});trigger.current?.scrollIntoView({block:'start',behavior:'instant'});}},[open,selected]);
 if(!current)return null;
 const choose=(id:string)=>{returning.current=true;onChoose(id);setOpen(false);};
 return <section className="archive-golf-chooser" aria-label={label}>
  <button ref={trigger} className="agc-trigger" aria-expanded={open} aria-label={`${label}: ${current.name}. Compare golfers`} onClick={()=>setOpen(v=>!v)}><span><small>Golfer in view</small><strong>{current.name}</strong></span><span>Change<ChevronDownIcon/></span></button>
  {open&&<div className="agc-panel"><div className="agc-tabs" role="group" aria-label="Golfer choices"><button aria-pressed={!all} onClick={()=>{setAll(false);setPage(0)}}>Suggested</button><button aria-pressed={all} onClick={()=>{setAll(true);setBand(archiveGolfBand(current.name));setPage(0)}}>All {rows.length}</button></div>
   <p className="agc-intro">{all?'A–Z by first name':'Starting chances, final results'}</p>
   {all&&<div className="agc-bands" role="group" aria-label="First-name groups">{archiveGolfBands.map(b=><button key={b} aria-pressed={b===band} onClick={()=>{setBand(b);setPage(0)}}>{b}<small>{archiveGolfGroup(rows,b).length}</small></button>)}</div>}
   <div className="agc-grid">{shown.map(row=>{const preview=archiveGolfPreview(row,frame);return <button key={row.id} className="agc-choice" aria-pressed={row.id===selected} aria-label={`Show ${row.name}, ${row.source}. Pre-event ${role==='win'?'win':'top-10'} chance ${row.before?pct(row.before.value):'unavailable'}. ${row.resultLabel}.`} onClick={()=>choose(row.id)}>
    <span className="agc-name"><strong>{row.name}</strong>{row.id===selected&&<CheckIcon aria-label="Selected"/>}</span><span className="agc-source">{row.source==='kalshi'?'Kalshi':row.source==='polymarket'?'Polymarket':row.source}</span>
    <span className="agc-before"><small>Before play · {role==='win'?'win':'top 10'}</small><b>{row.before?pct(row.before.value):'Unavailable'}</b></span>
    <span className="agc-track" aria-hidden="true">{row.before&&<i style={{width:`${row.before.value*100}%`}}/>}</span>
    <span className="agc-result">{row.result?<CheckIcon/>:<CrossCircledIcon/>}<span>Final · {row.resultLabel}</span></span>
    {preview.last?<><svg viewBox="0 0 142 56" aria-hidden="true"><line x1="6" x2="136" y1="50" y2="50" className="agc-zero"/>{preview.segments.map((segment,i)=><g key={i}>{segment.length>1&&<polyline points={segment.map(p=>`${6+p.x*130},${5+p.y*45}`).join(' ')} fill="none" stroke="currentColor" strokeWidth="1.5"/>}{segment.map((p,j)=><circle key={j} cx={6+p.x*130} cy={5+p.y*45} r="2" fill={p.before?'var(--surface-card)':'currentColor'} stroke="currentColor" strokeWidth="1"/>)}</g>)}</svg><span className="agc-history">Captured history · 0–100%</span><time>Last recorded · {readerTime(preview.last.at)}</time></>:<span className="agc-no-history">No recorded history</span>}
   </button>})}</div>
   {all&&<div className="agc-pages"><button aria-label="Previous golfers" disabled={!slice.page} onClick={()=>setPage(p=>p-1)}><ChevronLeftIcon/></button><span>{slice.first}–{slice.last} of {slice.count} · {band}</span><button aria-label="Next golfers" disabled={slice.page===slice.pages-1} onClick={()=>setPage(p=>p+1)}><ChevronRightIcon/></button></div>}
   <p className="agc-note">{frame?`History previews share ${readerTime(frame.from*1000,{dateOnly:true})}–${readerTime(frame.through*1000,{dateOnly:true})} and a 0–100% scale. `:''}Pre-event quotes keep separate dates. Hollow dots: before play. Hourly trade closes; gaps stay blank. All {rows.length} original props remain available, including entries with unavailable probabilities.</p>
  </div>}
 </section>;
}
