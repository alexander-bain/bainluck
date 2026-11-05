import {useState} from 'react';
import {CheckIcon,Cross2Icon,QuestionMarkIcon,ChevronRightIcon} from '@radix-ui/react-icons';
import {catalogPresentation,type CatalogContext} from './probabilityPresentation';
import {PregameContext} from './PregameContext';
import {selectedPregame,pregameNote} from './pregameEvidence';
import type {PlayerTargetFamily,PlayerTargetRow} from './soccerPlayerTargets';
import './soccerPlayerTargets.css';
export function SoccerPlayerTargets<T extends PlayerTargetRow>({family,context,onPick}:{family:PlayerTargetFamily<T>;context:CatalogContext;onPick:(row:T)=>void}){
 const [key,setKey]=useState<string|null>(null);
 const all=family.targets.flatMap(t=>t.rows),selected=all.find(r=>r.key===key)??all[0],target=family.targets.find(t=>t.rows.includes(selected))!,state=catalogPresentation(selected,context);
 const yes=(t:typeof target)=>t.rows.find(r=>r.outcome_name==='Yes')!;
 return <article className="atlas-card soccer-player-targets" aria-label={family.title}>
  <span className="eyebrow">Player props · reported results</span><h3>{family.title}</h3>
  <PregameContext value={selectedPregame(selected)} label="Pre-match chance" subject={`${selected.market_name} · ${selected.outcome_name}`} note={pregameNote(selected)}/>
  <p className="soccer-target-note">Targets below show the prop, not a measured player total.</p>
  <div className="soccer-target-field">{family.targets.map(t=>{const row=yes(t),s=catalogPresentation(row,context),active=t===target;return <button key={t.id} aria-pressed={active} aria-label={`${t.player}: ${t.count}+ ${t.unit}. Yes ${s.label}`} onClick={()=>setKey(row.key??null)}>
   <strong>{t.player}</strong><span className="soccer-target-unit">{t.count}+ {t.unit}</span>
   <span className="soccer-target-symbols" aria-hidden="true"><span className="soccer-target-bars">{Array.from({length:t.count},(_,i)=><i key={i}/>)}</span><span className={s.label==='Won'?'target-won':'target-unknown'}>{s.label==='Won'?<CheckIcon/>:s.label==='Lost'?<Cross2Icon/>:<QuestionMarkIcon/>}</span></span>
   <span className="soccer-target-result">Yes · {s.label}</span>
  </button>})}</div>
  <div className="soccer-target-selected"><strong>{selected.market_name}</strong><div className="combat-sides">{target.rows.map(row=><button key={row.key} aria-pressed={row.key===selected.key} onClick={()=>setKey(row.key??null)}>{row.outcome_name}<span>{catalogPresentation(row,context).label}</span></button>)}</div><p>{selected.outcome_name} · {state.label}</p><p className="soccer-target-note">Actual count unavailable · pre-match comparison unavailable</p><button className="card-link" onClick={()=>onPick(selected)}>Original {selected.outcome_name} prop & evidence <ChevronRightIcon/></button></div>
 </article>;
}
