import {receivingLeaders,type LeaderRow} from './receivingLeaders';
import {leaderProbabilityStatus,usesLeaderProbabilityUnavailable} from './leaderProbabilityEligibility';
import type {FinalCatalogRow} from './finalCatalogEvidence';
export function isReceivingLeaderCatalog(rows:FinalCatalogRow[],eventID:string){return rows.some(row=>usesLeaderProbabilityUnavailable(row,eventID))}
export function ReceivingLeaderCatalog({rows,visibleRows,selected,phase,choose,eventID,supportRows}:{rows:FinalCatalogRow[];visibleRows:FinalCatalogRow[];selected:FinalCatalogRow;phase:string;choose:(row:FinalCatalogRow)=>void;pick:(row:FinalCatalogRow)=>void;eventID:string;supportRows:FinalCatalogRow[]}){
 const sourceRows=[...supportRows.filter(row=>row._market_id===62146482),...rows] as unknown as LeaderRow[];
 const all=eventID==='14780549'?receivingLeaders(phase,sourceRows):null;
 const athlete=all?.find(p=>p.key===selected.row_key),shown=visibleRows.slice().sort((a,b)=>a.outcome_name.localeCompare(b.outcome_name));
 return <div className="rl-probability-unavailable"><h4>{leaderProbabilityStatus.label}</h4><p>{leaderProbabilityStatus.reason}</p><p className="rl-selected-name">{selected.outcome_name}</p>{phase==='Final'&&athlete&&<p>{athlete.result}{athlete.actual!==null?' · '+athlete.actual+' final receiving yards':''}</p>}<div className="catalog-evidence-tiles" role="group" aria-label="Receiving-yard leader outcomes">{shown.map(row=>{const outcome=all?.find(p=>p.key===row.row_key);return <button key={row.key} onClick={()=>choose(row)} aria-pressed={row.row_key===selected.row_key}><strong>{row.outcome_name}</strong>{phase==='Final'&&<span>{outcome?.result??'Result unconfirmed'}</span>}</button>})}</div><p>Current probability unavailable · {visibleRows.length} of {rows.length} original outcomes</p></div>;
}
