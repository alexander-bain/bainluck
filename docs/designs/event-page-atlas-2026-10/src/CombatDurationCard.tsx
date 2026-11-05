import {combatFinalFor} from './combatOfficialFinal';
import {CombatBaselineMark} from './CombatBaselineMark';
import {combatCheckedResult,combatPregameNote,combatResultConflict} from './combatPregame';
import {useState} from 'react';
import {durationQuestions,durationResult,durationTileRow} from './combatDuration';
import type {CombatRow} from './combatOutcome';
import {catalogAnchor,catalogOutcomeIdentity,resolveCatalogSelection,type CatalogAnchor} from './catalogSelection';
import {PregameContext} from './PregameContext';
import {selectedPregame} from './pregameEvidence';
import './combatDuration.css';
const mark=(result:string)=>result==='Won'?'✓':result==='Lost'?'×':'?';
export function CombatDurationCard<T extends CombatRow>({rows,eventID,onPick,visibleRows=rows,savedAnchor,onSelection,onReveal,finalStory=false,leadKey}:{rows:T[];eventID:number;onPick:(r:T)=>void;visibleRows?:T[];savedAnchor?:CatalogAnchor<T>|null;onSelection?:(a:CatalogAnchor<T>)=>void;onReveal?:()=>void;finalStory?:boolean;leadKey?:string}) {
 const final=combatFinalFor(eventID);
 const questions=durationQuestions(rows,eventID,leadKey),all=questions.flatMap(q=>q.rows);
 const [anchor,setAnchor]=useState(()=>all[0]?catalogAnchor(all[0]):null);
 const selection=resolveCatalogSelection(all,savedAnchor??anchor,9,visibleRows),selected=selection.row;
 if(!questions.length||!selected)return null;
 const chosen=questions.find(q=>q.rows.some(r=>catalogOutcomeIdentity(r)===catalogOutcomeIdentity(selected)));
 const visible=new Set(visibleRows.map(catalogOutcomeIdentity));
 const choose=(row:T)=>{const a=catalogAnchor(row);setAnchor(a);onSelection?.(a)};
 return <article className="atlas-card combat-duration-card" aria-label="Combat fight-length props">
  <span className="eyebrow">Polymarket · contract results</span><h3>{finalStory?"Finished in the first round":"How long could it last?"}</h3>
  {!finalStory&&<PregameContext label="Pre-match chance" note={combatPregameNote(selected)} value={selectedPregame(selected)} subject={`${selected.market_name} · ${selected.outcome_name}`}/>}
  <p className="combat-caption">Shaded rounds show each prop’s time window.</p>
  <div className="duration-tiles">{questions.map(q=>{const lead=durationTileRow(q,selection.present?selected:null,visibleRows),grade=combatCheckedResult(lead,durationResult(lead,q.rows)),shown=q.rows.filter(r=>visible.has(catalogOutcomeIdentity(r))),active=selection.present&&q===chosen;return <button key={q.id} className="duration-tile" aria-pressed={!!active} disabled={!shown.length} aria-label={`${q.question} ${lead.outcome_name}: ${grade}`} onClick={()=>choose(lead)}>
   <strong>{q.label}</strong><span className="duration-rail" aria-hidden="true">{[0,1,2].map(i=><span className="duration-round" key={i}><i style={{left:`${Math.max(0,Math.min(1,q.start-i))*100}%`,width:`${Math.max(0,Math.min(i+1,q.end)-Math.max(i,q.start))*100}%`}}/><small>{i+1}</small></span>)}</span>
   <CombatBaselineMark row={lead} compact sideLabel={lead.outcome_name}/><span className={grade==='Won'?'duration-grade duration-won':'duration-grade'}><b aria-hidden="true">{mark(grade)}</b>{!shown.length?'Outside filter':`${lead.outcome_name} ${grade.toLowerCase()}`}</span>
  </button>})}</div>
  {finalStory&&<PregameContext label="Pre-match chance" note={combatPregameNote(selected)} value={selectedPregame(selected)} subject={`${selected.market_name} · ${selected.outcome_name}`}/>}
  <p className="duration-disagreement">{final?<><strong>Official finish · {final.finishLabel}</strong><br/>Kopylov won. Contract results remain independently reported.</>:<>These results don’t establish one finish time. Fight status remains unresolved.</>}</p>
  <div className="combat-selected" aria-live="polite"><strong>{selected.market_name}</strong>{combatResultConflict(selected)&&<p className="duration-disagreement">Result unconfirmed: the game-prop capture and market detail disagree on this side.</p>}
   {selection.filteredOut&&<p className="combat-filter-note">Your selected side is outside this filter. {onReveal&&<button onClick={onReveal}>Show selection</button>}</p>}
   {chosen&&selection.present?<div className="combat-sides">{chosen.rows.map(r=><button key={r.key} aria-pressed={catalogOutcomeIdentity(r)===catalogOutcomeIdentity(selected)} disabled={!visible.has(catalogOutcomeIdentity(r))} onClick={()=>choose(r)}>{r.outcome_name}<span>{mark(combatCheckedResult(r,durationResult(r,chosen.rows)))} {combatCheckedResult(r,durationResult(r,chosen.rows))}</span></button>)}</div>:<p>Selection unavailable in this update. Original evidence remains accessible.</p>}
   {chosen?.rows.length===1&&<p className="combat-caption">Only this original side was captured. No opposite-side result is inferred.</p>}
   <button className="card-link" onClick={()=>onPick(selected)}>Original {selected.outcome_name} prop &amp; evidence <span aria-hidden="true">›</span></button>
  </div>
 </article>;
}
