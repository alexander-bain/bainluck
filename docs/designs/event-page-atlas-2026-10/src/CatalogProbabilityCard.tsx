import {nbaMarginTitle} from './basketballProjectionAvailability';
import {readerTime} from './readerTime';
import {MarginExpectationVisual} from './MarginExpectationVisual';
import {marginEligible} from './marginPregame';
import {PairedOutcomeVisual} from './PairedOutcomeVisual';
import {SingleOutcomeVisual} from './SingleOutcomeVisual';
import {PregameContext} from './PregameContext';
import {selectedPregame,pregameLabel,pregameNote} from './pregameEvidence';
import {useEffect,useState,type ReactNode} from 'react';
import {ChevronLeftIcon,ChevronRightIcon,CheckIcon,Cross2Icon,MinusIcon,QuestionMarkCircledIcon} from '@radix-ui/react-icons';
import {catalogPresentation,type CatalogEvidenceRow,type CatalogContext,type CatalogPresentation} from './probabilityPresentation';
import {probabilityLabel} from './probabilityLabel';
import './catalogAccess.css';
import {catalogAnchor,catalogOutcomeIdentity,resolveCatalogSelection,type CatalogAnchor} from './catalogSelection';
const time=readerTime;
export function CatalogProbabilityCard<T extends CatalogEvidenceRow>({rows,visibleRows=rows,context,onPick,savedAnchor,onSelection,onReveal,presentationFor=catalogPresentation,visual,displayTitle,selectionControlsInVisual=false,baselineInVisual=false,selectedSummaryInVisual=false}:{rows:T[];visibleRows?:T[];context:CatalogContext;onPick:(row:T)=>void;savedAnchor?:CatalogAnchor<T>|null;onSelection?:(anchor:CatalogAnchor<T>)=>void;onReveal?:()=>void;presentationFor?:(row:T,context:CatalogContext)=>CatalogPresentation;visual?:(row:T,choose:(row:T)=>void)=>ReactNode;displayTitle?:string;selectionControlsInVisual?:boolean;baselineInVisual?:boolean;selectedSummaryInVisual?:boolean}){
 const [localAnchor,setLocalAnchor]=useState<CatalogAnchor<T>|null>(()=>rows[0]?catalogAnchor(rows[0]):null);
 const anchor=savedAnchor===undefined?localAnchor:savedAnchor;
 const setAnchor=(next:CatalogAnchor<T>)=>onSelection?onSelection(next):setLocalAnchor(next);
 const {index,windowIndex,row,offset,shown,present,filteredOut,ambiguous}=resolveCatalogSelection(rows,anchor,6,visibleRows);
 // Retain the last received record for evidence if a later update omits it.
 useEffect(()=>{if(present&&row&&anchor&&anchor.row!==row)setAnchor(catalogAnchor(row))},[present,row,anchor,onSelection]);
 if(!row)return <article className="atlas-card catalog-visual-card"><h3>No outcomes in this update</h3><p>The original props will appear when supplied.</p></article>;
 const state=presentationFor(row,present?context:{...context,mode:'stale'});
 const selectedIdentity=present?catalogOutcomeIdentity(row):null;
 const choose=(r:T)=>setAnchor(catalogAnchor(r));
 const presented=shown.map(r=>({row:r,state:presentationFor(r,context)}));
 const quoted=presented.filter(p=>p.state.kind==='quote').map(p=>({row:p.row,value:p.state.value,label:p.row.outcome_name}));
 const other=presented.filter(p=>p.state.kind!=='quote');
 const margin=!visual&&present&&!ambiguous&&marginEligible(rows,context.status);
 const simpleSingle=!visual&&rows.length===1;
 const simplePair=!visual&&rows.length===2&&present&&!ambiguous;
 const compact=simpleSingle||simplePair||margin;
 const quoteCount=rows.filter(r=>presentationFor(r,context).kind==='quote').length;
 return <article className={`atlas-card catalog-visual-card ${simpleSingle?'single-outcome-card':simplePair?'paired-outcome-card':''}`}>
  <div className="atlas-card-head"><div><span className="eyebrow">{row.source}{!compact&&<> · {rows.length} {rows.length===1?'outcome':'outcomes'}</>}{visibleRows.length!==rows.length&&` · ${visibleRows.length} matching`}</span><h3>{displayTitle??(margin?nbaMarginTitle:row.market_name)}</h3></div></div>
  {!baselineInVisual&&!compact&&<PregameContext note={pregameNote(row)} value={selectedPregame(row)} label={pregameLabel(row)} subject={row.outcome_name}/>}
  {margin?<MarginExpectationVisual rows={rows} visibleRows={visibleRows} selected={row} state={state} choose={choose}/>:simplePair?<PairedOutcomeVisual rows={rows} visibleRows={visibleRows} selected={row} stateFor={r=>presentationFor(r,context)} choose={choose}/>:simpleSingle?<SingleOutcomeVisual row={row} state={state}/>:visual?visual(row,choose):<>{quoted.length>0&&<><p className="catalog-plot-caption">Recorded chances · 0–100%</p><div className="catalog-quote-buttons" role="group" aria-label={`Recorded outcomes: ${row.market_name}`}>
   {quoted.map(q=><button key={q.row.key} aria-pressed={catalogOutcomeIdentity(q.row)===selectedIdentity} aria-label={`${q.row.outcome_name}: ${probabilityLabel(q.value)} recorded, ${time(q.row.observed_at!)}`} onClick={()=>choose(q.row)}>
    <span className="catalog-quote-label"><span>{q.row.outcome_name}</span><strong>{probabilityLabel(q.value)}</strong></span>
    <span className="catalog-quote-track" aria-hidden="true"><span style={{width:`${q.value!*100}%`}}/></span>
   </button>)}
   <div className="catalog-quote-axis" aria-hidden="true"><span>0%</span><span>50%</span><span>100%</span></div>
  </div></>}
  {quoteCount===0&&other.every(p=>p.state.kind==='unavailable')&&<p className="catalog-unavailable-title">{context.mode==='historical'?'Earlier probability unavailable':context.mode==='loading'?'Loading…':'Current probability unavailable'}</p>}
  {other.length>0&&<div className="catalog-evidence-tiles">{other.map(({row:r,state:s})=><button key={r.key} className={s.label==='Won'?'won':''} onClick={()=>choose(r)} aria-pressed={catalogOutcomeIdentity(r)===selectedIdentity}>
   {s.kind==='result'?(s.label==='Won'?<CheckIcon/>:s.label==='Lost'?<Cross2Icon/>:s.label==='Closed · no winner'?<MinusIcon/>:<QuestionMarkCircledIcon/>):null}
   <strong>{r.outcome_name}</strong><span>{s.label}</span>
  </button>)}</div>}
  </>}
  <div className={(selectedSummaryInVisual||compact)?"catalog-selection-notices":"catalog-selected"} aria-live="polite" aria-atomic="true">{!selectedSummaryInVisual&&!compact&&<><strong>{row.outcome_name}</strong><span>{state.kind==='quote'?`${probabilityLabel(state.value)} · ${time(state.observedAt)}`:state.label}</span></>}{index!==null?<span className="sr-only">Outcome {index+1} of {rows.length}</span>:<span>{ambiguous?'This update has conflicting records for your selection.':'Your selection is not in this update.'} {rows.length>0?'Choose another outcome above, or keep this selection.':'Your original evidence remains available.'}</span>}{filteredOut&&<><span>Your selection is outside this filter.</span><button className="card-link" onClick={onReveal}>Show selected outcome <ChevronRightIcon/></button></>}</div>
  {!selectionControlsInVisual&&!simplePair&&!margin&&visibleRows.length>1&&windowIndex!==null&&<div className="catalog-outcome-stepper"><button aria-label={`Previous outcome: ${row.market_name}`} disabled={windowIndex===0} onClick={()=>choose(visibleRows[Math.max(0,windowIndex-1)])}><ChevronLeftIcon/></button><span>{windowIndex+1} of {visibleRows.length} {visibleRows.length!==rows.length?'matches':'outcomes'}{!visual&&visibleRows.length>6&&<small>Showing {offset+1}–{Math.min(offset+6,visibleRows.length)}</small>}</span><button aria-label={`Next outcome: ${row.market_name}`} disabled={windowIndex===visibleRows.length-1} onClick={()=>choose(visibleRows[Math.min(visibleRows.length-1,windowIndex+1)])}><ChevronRightIcon/></button></div>}
  <button className="card-link" onClick={()=>onPick(row)}>Details <ChevronRightIcon/></button>
 </article>;
}
