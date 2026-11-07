import {readerTime} from './readerTime';
import {scoreGridWinner} from './scoreGridWinner';
import {selectedPregame} from './pregameEvidence';
import type {CSSProperties} from 'react';
import {catalogPresentation,type CatalogContext} from './probabilityPresentation';
import {catalogOutcomeIdentity} from './catalogSelection';
import {probabilityLabel} from './probabilityLabel';
import {scoreGridStrength,type ScoreGrid,type ScoreGridRow} from './exactScoreGrid';
import './exactScoreGrid.css';
export function ExactScoreGridCard<T extends ScoreGridRow>({data,selected,visibleRows,context,choose}:{data:ScoreGrid<T>;selected:T;visibleRows:T[];context:CatalogContext;choose:(row:T)=>void}){
 const visible=new Set(visibleRows.map(catalogOutcomeIdentity)),isVisible=(r:T)=>visible.has(catalogOutcomeIdentity(r)),active=(r:T)=>catalogOutcomeIdentity(r)===catalogOutcomeIdentity(selected);
 const state=catalogPresentation(selected,context),cell=data.cells.find(c=>active(c.row));
 const winner=scoreGridWinner(data,context);
 const historical=context.status==='completed';const quote=(r:T)=>{if(historical)return selectedPregame(r);const s=catalogPresentation(r,context);return s.kind==='quote'?s.value:null};
 const title=cell?`${data.home} ${cell.home} – ${data.away} ${cell.away}`:selected.outcome_name;
 const cellLabel=(r:T)=>{const s=catalogPresentation(r,context);return historical?`${selectedPregame(r)==null?'Earlier chance unavailable':probabilityLabel(selectedPregame(r))+' earlier pre-match'}; ${s.label}`:s.kind==='quote'?probabilityLabel(s.value):s.label};
 const strength=(r:T):CSSProperties=>({'--score-strength':quote(r)===null?0:scoreGridStrength(quote(r)!)} as CSSProperties);
 return <section className="exact-score-visual" aria-label={`${data.scope} exact-score grid`}>
  {winner&&<button className="score-winner-focus" onClick={()=>choose(winner.row)} aria-label={`View winning score ${winner.home}–${winner.away}, ${probabilityLabel(selectedPregame(winner.row))} earlier pre-match`}><span>Winning score · {winner.home}–{winner.away}</span><strong>{probabilityLabel(selectedPregame(winner.row))} pre-match <span aria-hidden="true">→</span></strong></button>}
  <p className="exact-score-scope">{data.scope} · goals</p>
  <div className="exact-score-readout"><strong>{title}</strong><b>{state.kind==='quote'?probabilityLabel(state.value):state.label}</b><span>{state.kind==='quote'?`Recorded chance · ${readerTime(state.observedAt)}`:'Last quote in details'}</span></div>
  <p className="exact-score-axis">{data.home} goals → · {data.away} goals ↓</p>
  <div className="exact-score-grid" style={{gridTemplateColumns:`18px repeat(${data.size},minmax(0,1fr))`}} role="group" aria-label={`${data.home} goals across, ${data.away} goals down`}>
   <span/>{Array.from({length:data.size},(_,n)=><b key={`h${n}`}>{n}</b>)}
   {Array.from({length:data.size},(_,away)=><div className="exact-score-grid-row" key={away}><b>{away}</b>{Array.from({length:data.size},(_,home)=>{const c=data.cells.find(c=>c.home===home&&c.away===away),r=c?.row;if(!r)return <span className="exact-score-unlisted" key={home} aria-label={`${data.home} ${home}, ${data.away} ${away}: not separately listed`}>Not listed</span>;const shown=isVisible(r),s=catalogPresentation(r,context);return <button key={home} style={strength(r)} disabled={!shown} aria-pressed={active(r)} aria-label={`${data.home} ${home}, ${data.away} ${away}: ${shown?cellLabel(r):'outside filter'}`} onClick={()=>choose(r)}>{shown?(historical&&selectedPregame(r)!=null?<><span>{probabilityLabel(selectedPregame(r)).replace('%','')}</span><small className="score-result-mark" aria-hidden="true">{s.label==='Won'?'✓':s.label==='Lost'?'×':'?'}</small></>:s.kind==='quote'?probabilityLabel(s.value).replace('%',''):s.kind==='result'?(s.label==='Won'?'✓':s.label==='Lost'?'×':'?'):'—'):'·'}</button>})}</div>)}
  </div>
  <button className="exact-score-other" style={strength(data.other)} disabled={!isVisible(data.other)} aria-pressed={active(data.other)} onClick={()=>choose(data.other)}><span>Any Other Score</span><strong>{isVisible(data.other)?cellLabel(data.other):'Outside filter'}</strong></button>
  <p className="exact-score-note">{historical?'Earlier pre-match chances (%) · darker means higher. ✓ / × show independently reported results.':'Recorded chances (%) · darker means higher.'} Each quote keeps its own time; no normalization.</p>
 </section>;
}
