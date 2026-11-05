import {combatFinalFor} from './combatOfficialFinal';
import {CombatBaselineMark} from './CombatBaselineMark';
import {combatCheckedResult,combatPregame,combatPregameNote,combatQuoteTime} from './combatPregame';
import {PregameContext} from './PregameContext';
import {useState} from 'react';
import {combatQuestions,combatResult,combatRoundKnown,combatTileRow,type CombatRow,type CombatQuestion} from './combatOutcome';
import {catalogAnchor,catalogOutcomeIdentity,resolveCatalogSelection,type CatalogAnchor} from './catalogSelection';
import './combatOutcomeCards.css';
const mark=(grade:string)=>grade==='Won'?'✓':grade==='Lost'?'×':'?';
export function CombatOutcomeCards<T extends CombatRow>({rows,eventID,onPick}:{rows:T[];eventID:number;onPick:(r:T)=>void}){
 return <>{(['methods','rounds','fighterKO'] as const).map(family=><CombatOutcomeCard key={family} rows={rows} eventID={eventID} family={family} onPick={onPick}/>)}</>;
}
export function CombatOutcomeCard<T extends CombatRow>({rows,eventID,family,onPick,visibleRows=rows,savedAnchor,onSelection,onReveal,finalStory=false}:{rows:T[];visibleRows?:T[];savedAnchor?:CatalogAnchor<T>|null;onSelection?:(a:CatalogAnchor<T>)=>void;onReveal?:()=>void;finalStory?:boolean;eventID:number;family:'methods'|'rounds'|'fighterKO';onPick:(r:T)=>void}){
 const questions=combatQuestions(rows,family,eventID),all=questions.flatMap(q=>[q.yes,q.no]);
 const [anchor,setAnchor]=useState(()=>all[0]?catalogAnchor(all[0]):null);
 const selection=resolveCatalogSelection(all,savedAnchor??anchor,6,visibleRows),selected=selection.row;
 const visible=new Set(visibleRows.map(catalogOutcomeIdentity));
 if(!questions.length||!selected)return null;
 const q=questions.find(q=>[q.yes,q.no].some(r=>catalogOutcomeIdentity(r)===catalogOutcomeIdentity(selected)));
 const choose=(row:T)=>{const a=catalogAnchor(row);setAnchor(a);onSelection?.(a)};
 const cell=(q:CombatQuestion<T>)=>{
  const active=!!selection.present&&[q.yes,q.no].some(r=>catalogOutcomeIdentity(r)===catalogOutcomeIdentity(selected)),row=combatTileRow(q,selection.present?selected:null,visibleRows),other=row.outcome_name==='Yes'?q.no:q.yes,grade=combatCheckedResult(row,combatResult(row,other)),shown=visible.has(catalogOutcomeIdentity(row));
  return <button key={q.id} className={`combat-cell ${grade==='Won'?'combat-won':''}`} aria-pressed={active} disabled={!shown} aria-label={`${q.question} ${row.outcome_name}: ${grade}`} aria-description={`Pre-match ${combatPregame(row)?.value==null?'unavailable':Math.round(combatPregame(row)!.value*10000)/100+'% · '+combatQuoteTime(combatPregame(row)!.at)}`} onClick={()=>choose(row)}><span className="combat-cell-title">{family!=='rounds'?q.label:`Round ${q.round}`}</span><CombatBaselineMark row={row} sideLabel={row.outcome_name} showClock={false} style={family==='rounds'?'rail':'ring'}/><span className="combat-compact-result"><span aria-hidden="true">{mark(grade)} </span>{!shown?'Outside filter':grade==='Result unconfirmed'?'Unconfirmed':`${row.outcome_name} ${grade.toLowerCase()}`}</span></button>
 };
 return <article className={`atlas-card combat-outcome-card combat-dense combat-family-${family}`} aria-label={family==='methods'?'Combat finish-method results':family==='fighterKO'?'Combat fighter-knockout results':'Combat fighter-round results'}>
 <span className="eyebrow">Polymarket · contract results</span><h3>{finalStory?(family==='methods'?'How the bout ended':family==='fighterKO'?'The knockout few expected':'The first-round surprise'):(family==='methods'?'How could the fight end?':family==='fighterKO'?'Who wins by knockout?':'Which round for each fighter?')}</h3>{!finalStory&&<PregameContext label="Pre-match chance" value={combatPregame(selected)?.value} subject={`${selected.market_name} · ${selected.outcome_name}`} note={combatPregameNote(selected)}/>}<p className="combat-caption">{family==='rounds'?'Pre-match chance · tracks run from 0 to 100%':'Pre-match chances · select a tile for its quote time'}</p>
 {family!=='rounds'?<div className={family==='fighterKO'?'combat-methods combat-fighter-ko':'combat-methods'}>{questions.map(cell)}</div>:<div className="combat-round-map">{['Roman Kopylov','Ateba Gautier'].map(name=><section key={name}><h4>{name}</h4><div className="combat-rounds">{[1,2,3].map(round=>{const q=questions.find(q=>q.subject===name&&q.round===round);return q?cell(q):<div key={round} className="combat-cell combat-absent"><span className="combat-cell-title">Round {round}</span><b aria-hidden="true">—</b><span>{combatRoundKnown(name,round)?'Unavailable in update':'No captured prop'}</span></div>})}</div></section>)}</div>}
 {finalStory&&<PregameContext label="Pre-match chance" value={combatPregame(selected)?.value} subject={`${selected.market_name} · ${selected.outcome_name}`} note={combatPregameNote(selected)}/>}
 <div className="combat-selected" aria-live="polite">{selection.filteredOut&&<p className="combat-filter-note">Your selected side is outside this filter. {onReveal&&<button onClick={onReveal}>Show selection</button>}</p>}{q&&selection.present?<div className="combat-sides">{[q.yes,q.no].map((r,i)=>{const grade=combatCheckedResult(r,combatResult(r,i?q.yes:q.no));return <button key={r.key} aria-pressed={catalogOutcomeIdentity(r)===catalogOutcomeIdentity(selected)} disabled={!visible.has(catalogOutcomeIdentity(r))} onClick={()=>choose(r)}>{r.outcome_name} <span>{mark(grade)} {grade}</span></button>})}</div>:<p>Selection unavailable in this update. Original evidence remains accessible.</p>}<button className="card-link" onClick={()=>onPick(selected)}>Original {selected.outcome_name} prop &amp; evidence <span aria-hidden="true">›</span></button></div>
 <p className="combat-caption">{combatFinalFor(eventID)?'Official bout result: Kopylov won by TKO, R1 at 3:12. Contract results shown separately.':'Contract results shown separately · fight status unresolved.'}</p>
 </article>;
}
