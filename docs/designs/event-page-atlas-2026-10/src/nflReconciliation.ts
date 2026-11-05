import wire from './nflCaptures.json' with {type:'json'};
import type {CatalogEvidenceRow} from './catalogPresentation';
export type NFLRow=CatalogEvidenceRow&{category?:unknown;source_file?:unknown;player_entity_key?:unknown;player_team_entity_key?:unknown;actual?:unknown;pregame_mark?:unknown;_nfl_previous?:NFLRow;_nfl_presence?:string;[key:string]:unknown};
const stable=(v:unknown):string=>JSON.stringify(v,(_,value)=>value&&typeof value==='object'&&!Array.isArray(value)?Object.fromEntries(Object.keys(value).sort().map(k=>[k,value[k]])):value);
export function nflIdentity(r:NFLRow){return stable(['source','_market_id','contributor_outcome_ids','market_name','outcome_name','threshold','period','market_type','_inverted','category','player_entity_key','player_team_entity_key'].map(k=>r[k]??null))}
export function reconcileNFL(earlier:NFLRow[],latest:NFLRow[]):NFLRow[]{
 const index=new Map<string,NFLRow[]>();for(const r of latest){const k=nflIdentity(r);index.set(k,[...(index.get(k)??[]),r])}
 const seen=new Set(earlier.map(nflIdentity));
 return [...earlier.map(old=>{const matches=index.get(nflIdentity(old))??[];return matches.length===1?{...matches[0],key:old.key,_nfl_previous:old,_nfl_presence:'matched'}:{...old,_nfl_previous:old,_nfl_presence:matches.length?'ambiguous':'absent',result_unconfirmed:true}}),...latest.filter(r=>!seen.has(nflIdentity(r))).map(r=>({...r,_nfl_presence:'new',...((index.get(nflIdentity(r))?.length??0)>1?{result_unconfirmed:true}:{})}))];
}
export const nflFinalRows=reconcileNFL(wire.earlier as NFLRow[],wire.latest as NFLRow[]);
const admitted=new Map(nflFinalRows.map(r=>[r.key,stable(r)]));
export function nflAdmitted(row:CatalogEvidenceRow){return admitted.get(row.key)===stable(row)}
export function nflBaselineRow<T extends CatalogEvidenceRow>(row:T):T{
 if(!nflAdmitted(row))return row;
 return ((row as unknown as NFLRow)._nfl_previous??row) as T;
}
export function nflActual(row:CatalogEvidenceRow):number|null{
 const r=row as unknown as NFLRow;
 return wire.detail.status==='completed'&&nflAdmitted(r)&&['matched','new'].includes(r._nfl_presence??'')&&typeof r.actual==='number'&&Number.isSafeInteger(r.actual)&&r.actual>=0?r.actual:null;
}
export function nflPregameNote(row:CatalogEvidenceRow){
 if(!nflAdmitted(row))return undefined;
 const baseline=nflBaselineRow(row) as NFLRow,p=baseline.pregame_mark;
 if(typeof p!=='number'||!Number.isFinite(p)||p<0||p>1||typeof baseline._inverted!=='boolean')return 'Pregame baseline unavailable';
 return (row as unknown as NFLRow)._nfl_previous?'Pregame baseline retained from the earlier capture · exact time unavailable':'Supplied pregame baseline in final capture · exact time unavailable';
}
export function nflCaptureNote(row:CatalogEvidenceRow){
 const r=row as unknown as NFLRow;if(!nflAdmitted(row))return undefined;
 return r._nfl_presence==='absent'?'Absent from the final update. Earlier evidence stays available; final actual and result are unconfirmed.':r._nfl_presence==='ambiguous'?'Conflicting final records. Final actual and result are unconfirmed.':'Final capture matched by exact prop, side, player and source IDs. Baseline and final actual are separate observations.';
}
export {wire as nflCaptures};
