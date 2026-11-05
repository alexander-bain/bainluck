import {readerTime} from './readerTime';
import {probabilityLabel} from './probabilityLabel';
import './matchHistoryReader.css';

type Outcome={name:string;value:number;tone:'home'|'away'|'draw'};
type Reading={at:string;label:string;outcomes:Outcome[];seconds?:boolean};
/** Presentation only: each chance retains the exact supplied outcome and clock. */
export function HistoryReaderContext({title,result,selected,baseline}:{title:string;result:string;selected:Reading|null;baseline:Reading|null}){
 return <div className="mhr-context"><b>{title}</b><span>{result}</span>
  {selected?<div className="mhr-selected"><span>{selected.label} · {readerTime(Date.parse(selected.at),{seconds:selected.seconds})}</span><div className="mhr-outcomes" style={{gridTemplateColumns:`repeat(${selected.outcomes.length},minmax(0,1fr))`}}>{selected.outcomes.map(o=><strong key={o.tone} className={o.tone}><span>{o.name}</span><b>{probabilityLabel(o.value)}</b></strong>)}</div></div>:<span>Selected recorded observation unavailable</span>}
  {baseline&&selected?.at!==baseline.at&&<div className="mhr-baseline"><span>{baseline.label} · {readerTime(Date.parse(baseline.at),{seconds:baseline.seconds})}</span><div className="mhr-outcomes" style={{gridTemplateColumns:`repeat(${baseline.outcomes.length},minmax(0,1fr))`}}>{baseline.outcomes.map(o=><strong key={o.tone} className={o.tone}><span>{o.name}</span><b>{probabilityLabel(o.value)}</b></strong>)}</div></div>}
 </div>;
}
