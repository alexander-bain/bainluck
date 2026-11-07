import {readerTime} from './readerTime';
import {BarChartIcon,ChevronRightIcon,CheckCircledIcon,CrossCircledIcon,QuestionMarkCircledIcon} from '@radix-ui/react-icons';
import {selectFieldHeader,fieldBaselineSummary,type FieldHeaderConfig} from './fieldHeaderEvidence';
import {type CatalogContext,type CatalogEvidenceRow} from './probabilityPresentation';
import {probabilityLabel} from './probabilityLabel';
import './fieldEventHeader.css';

const time=(raw:string)=>readerTime(raw,{seconds:true});
export function FieldEventHeader<T extends CatalogEvidenceRow>({config,rows,context,onPick,onBrowse}:{config:FieldHeaderConfig;rows:T[];context:CatalogContext;onPick:(row:T)=>void;onBrowse:()=>void}) {
 const evidence=selectFieldHeader(config,rows,context),baseline=fieldBaselineSummary(config,rows,context);
 const label=config.role==='winner'?'Recorded win chances':config.role==='placement'?'Recorded placement chances':config.role==='qualification'?'Recorded qualification chances':'Recorded chance';
 return <section className="atlas-hero panel field-event-header" aria-label={config.predicate}>
  <div className="hero-head"><span>{config.source} · archived markets</span></div>
  <h1>{config.title}</h1><h2 className="field-predicate">{config.predicate}</h2>
  <div className="field-header-layout"><div className="field-header-summary">
   {evidence.resolved.length>0?<>
    <p className="field-caption">Recorded results</p>
    <div className="field-result-summary">
     <div><CheckCircledIcon/><strong>{evidence.reached}</strong><span>{config.role==='placement'?'Reached top 10':'Won'}</span></div>
     <div><CrossCircledIcon/><strong>{evidence.missed}</strong><span>{config.role==='placement'?'Missed top 10':'Lost'}</span></div>
     {evidence.pending>0&&<div><QuestionMarkCircledIcon/><strong>{evidence.pending}</strong><span>Unconfirmed</span></div>}
    </div>
    <p className="field-caption">{evidence.resolved.length} captured results · {evidence.bound.length} supplied props</p>
    {evidence.resolved.slice(0,3).map(({row,state})=><button className="field-name" key={row.key} onClick={()=>onPick(row)}><span>{row.outcome_name}</span><span>{state.label==='Won'?<CheckCircledIcon/>:<CrossCircledIcon/>}<span className="sr-only">{state.label}</span></span></button>)}
   </>:evidence.quoted.length>0?<>
    <p className="field-caption">{label}</p>
    {evidence.quoted.slice(0,3).map(({row,value,observedAt},index)=><button className={`field-chance ${index===0?'field-leader':''}`} key={row.key} onClick={()=>onPick(row)} aria-label={`${row.outcome_name}, ${probabilityLabel(value)} recorded ${time(observedAt)}. Open original prop.`}>
     <span className="field-chance-label"><span>{row.outcome_name}</span><strong>{probabilityLabel(value)}</strong></span>
     <span className="field-bar" aria-hidden="true"><span style={{width:`${value*100}%`}}/></span>
     {index===0&&<span className="field-caption">Recorded {time(observedAt)}</span>}
    </button>)}
    {evidence.bound.length>3&&<p className="field-caption">Leading quoted contenders · {evidence.bound.length} supplied outcomes</p>}
   </>:<>
    <h3 className="field-missing">{context.mode==='loading'?'Loading…':'Current probability unavailable'}</h3>
    <p className="field-caption">{config.missingNote.replaceAll('questions','markets')}</p>
    {evidence.named.slice(0,3).map(row=><button className="field-name" key={row.key} onClick={()=>onPick(row)}><span>{row.outcome_name}</span><ChevronRightIcon/></button>)}
    <p className="field-caption">{evidence.bound.length} named props · no ranking inferred</p>
   </>}
  </div><div className="field-history-note"><div className="field-baseline-summary" aria-label={`${baseline.label}: ${baseline.known===0?'Unavailable':'See details'}`}><span>{baseline.label}</span><strong>{baseline.known===0?'Unavailable':'See details'}</strong></div><strong><BarChartIcon/>Probability history</strong><p>{config.historyNote.replaceAll('questions','markets')}</p><p>{config.contextNote.replaceAll('questions','markets')}</p>{config.role==='qualification'&&<p>Each country has its own qualification prop. These are not shares of one winner field.</p>}</div></div>
  <button className="card-link field-browse" onClick={onBrowse}>Explore all markets<ChevronRightIcon/></button>
 </section>;
}
