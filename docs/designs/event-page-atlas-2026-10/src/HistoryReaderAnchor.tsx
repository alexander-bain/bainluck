import {InfoCircledIcon} from '@radix-ui/react-icons';
import {probabilityLabel} from './probabilityLabel';
import './historyReaderAnchor.css';

type Outcome={name:string;value:number|null;tone?:'home'|'away'};
/** Fixed historical basis, never the currently inspected observation or a live quote. */
export function HistoryReaderAnchor({title,state,outcomes,onInfo}:{title:string;state:string;outcomes:readonly Outcome[];onInfo:()=>void}){
 return <div className="history-reader-anchor">
  <div className="history-anchor-top"><div><b>{title}</b><span>{state}</span></div><button aria-label="About this probability history" onClick={onInfo}><InfoCircledIcon/></button></div>
  <div className={`history-anchor-baselines history-anchor-count-${outcomes.length}`} aria-label="Pre-match win chances">
   <span className="history-anchor-basis">Pre-match win chance</span>
   {outcomes.map(row=><div key={row.name} className={`history-anchor-outcome ${row.tone??'unknown'}`} aria-label={`${row.name}: pre-match win chance ${row.value===null?'unavailable':probabilityLabel(row.value)}`}><span>{row.name}</span><strong data-unavailable={row.value===null}>{row.value===null?'Unavailable':probabilityLabel(row.value)}</strong></div>)}
  </div>
 </div>;
}
