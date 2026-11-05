import {readerTime} from './readerTime';
import type {RetainedHistorySelection} from './historyObservation';
import {probabilityLabel} from './probabilityLabel';
export function HistorySelectionStatus({selection,unavailable,count,home,away,preLabel='Pre-match',afterLabel='Recorded after start',onLatest}:{selection:RetainedHistorySelection|null;unavailable:boolean;count:number;home:string;away:string;preLabel?:string;afterLabel?:string;onLatest:()=>void}){
 const p=selection?.point;
 const clock=p?readerTime(p.t):'';
 return <>{unavailable&&p&&<div className="history-selection-unavailable" role="status"><p>Selected observation is not available in this update.</p><details><summary>Retained observation · {clock}</summary><p>{p.pregame?preLabel:afterLabel} · {home} {probabilityLabel(p.home)}{p.draw!==undefined&&<> · Draw {probabilityLabel(p.draw)}</>} · {away} {probabilityLabel(p.away)}.{p.books!==undefined&&<> {p.books} {p.books===1?'bookmaker':'bookmakers'}.</>} Earlier captured values; not a replacement quote. Original timestamp: <code>{p.at}</code>.</p></details>{count>0&&<button onClick={onLatest}>Inspect latest available</button>}</div>}{!count&&<p>No recorded observations in this update.</p>}</>;
}
