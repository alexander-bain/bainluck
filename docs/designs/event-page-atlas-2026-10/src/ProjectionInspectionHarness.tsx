import {useState} from 'react';
import {createRoot} from 'react-dom/client';
import {ProjectionJourneyCard,projectionFor} from './ProjectionJourneyCard';
import {projectionObservations} from './projectionInspection';
import './prototype.css';
function Harness(){
 const [key,setKey]=useState('nfl'),[snapshot,setSnapshot]=useState('tail'),[mode,setMode]=useState('captured'),[large,setLarge]=useState(false);
 const original=projectionFor(key)!,rows=projectionObservations(original),target=rows[Math.floor(rows.length*.65)],floor=Date.parse(rows[Math.floor(rows.length*.5)].point.at);
 const bundle={...original,segments:snapshot==='empty'?[]:original.segments.map(s=>s.filter(p=>snapshot==='tail'?Date.parse(p.at)>=floor:snapshot==='omit'?p.at!==target.point.at:true)).filter(s=>s.length)};
 return <main style={{maxWidth:1050,margin:'auto',padding:12,fontFamily:'system-ui'}}>
  <header><h1>Projection refresh check</h1><p>UI simulation using unchanged captured readings. These controls are a verification harness, not product controls or new provider captures.</p>
   <p>Target reading: <b>{target.point.at} · {target.point.home}–{target.point.away}</b></p>
   <label>Real event <select aria-label="Harness event" value={key} onChange={e=>setKey(e.target.value)}><option value="nfl">Bears–Eagles final</option><option value="nfl-live">Jaguars–Eagles recorded live</option></select></label>
   <div style={{display:'flex',flexWrap:'wrap',gap:8}}>{[['tail','Later readings only'],['full','Restore full capture'],['omit','Omit target timestamp'],['empty','Empty history']].map(([value,label])=><button key={value} style={{minHeight:44}} onClick={()=>setSnapshot(value)}>{label}</button>)}</div>
   <label><input type="checkbox" checked={large} onChange={e=>setLarge(e.target.checked)}/>Enlarged text</label>
   <label> Probability mode <select aria-label="Harness probability mode" value={mode} onChange={e=>setMode(e.target.value)}><option value="captured">Captured</option><option value="stale">Current probability unavailable</option></select></label>
  </header>
  <section className={`event-content ${large?'large-text':''}`} style={{padding:'18px 0',position:'static'}}><ProjectionJourneyCard bundle={bundle} mode={mode}/></section>
 </main>
}
createRoot(document.getElementById('root')!).render(<Harness/>);
