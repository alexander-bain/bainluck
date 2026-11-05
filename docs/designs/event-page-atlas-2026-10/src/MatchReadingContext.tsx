import {ArrowTopRightIcon} from '@radix-ui/react-icons';
import {probabilityLabel as pct} from './probabilityLabel';
import {matchHistoryTarget} from './matchHistoryTarget';
import './matchReadingContext.css';
type Row={ticker:string;name:string;baseline:{at:number;p:number}|null;points:{at:number;p:number;volume:number}[]};
export function MatchReadingContext({rows,result,onChart,onInspect}:{rows:Row[];result:string;onChart:()=>void;onInspect:(ticker:string,at:number)=>void}){
 return <aside className="match-reading-context" aria-label="Match probability context">
  <header><span>{result}</span><button aria-label="Open match win probability" onClick={onChart}>Chart <ArrowTopRightIcon/></button></header>
  <p>Before match · separate trades</p>
  <div className="match-reading-values" style={{gridTemplateColumns:`repeat(${Math.max(1,rows.length)},minmax(0,1fr))`}}>{rows.map((s,i)=>{
   const target=matchHistoryTarget(rows,s.ticker,s.baseline?.at);
   return <button className={`rg-color-${i}`} key={s.ticker} disabled={target===null} onClick={()=>{if(target!==null)onInspect(s.ticker,target)}} aria-label={`Inspect ${s.name} pre-match chance ${pct(s.baseline?.p)} in chart`}><span>{s.name}</span><b>{s.baseline?pct(s.baseline.p):'Unavailable'}</b></button>;
  })}</div>
 </aside>;
}
