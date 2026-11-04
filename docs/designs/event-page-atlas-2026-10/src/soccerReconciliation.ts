import wire from './soccerCaptures.json' with {type:'json'};
import type {CatalogEvidenceRow} from './catalogPresentation';
import type {SessionRow} from './catalogPageSession';
export type SoccerRow=SessionRow&{source_file?:string;_soccer_previous?:SoccerRow;_soccer_presence?:string;[key:string]:unknown};
const stable=(v:unknown):string=>JSON.stringify(v,(_,value)=>value&&typeof value==='object'&&!Array.isArray(value)?Object.fromEntries(Object.keys(value).sort().map(k=>[k,value[k]])):value);
export function soccerIdentity(r:SoccerRow){return stable([r.source,r._market_id,r.contributor_outcome_ids,r.market_name,r.outcome_name,r.threshold??null,r.period??null,r.market_type??null,r._inverted??null])}
export function reconcileSoccer(earlier:SoccerRow[],latest:SoccerRow[]):SoccerRow[]{
 const seen=new Set(earlier.map(soccerIdentity));
 const original=earlier.map(old=>{const matches=latest.filter(r=>soccerIdentity(r)===soccerIdentity(old));return matches.length===1?{...matches[0],key:old.key,_soccer_previous:old,_soccer_presence:'matched'}:{...old,_soccer_previous:old,_soccer_presence:matches.length?'ambiguous':'absent',result_unconfirmed:true}});
 const added=latest.filter(r=>!seen.has(soccerIdentity(r))).map(r=>({...r,_soccer_presence:'new',...(latest.filter(x=>soccerIdentity(x)===soccerIdentity(r)).length>1?{result_unconfirmed:true}:{})}));
 return [...original,...added];
}
export const soccerFinalRows=reconcileSoccer(wire.earlier as SoccerRow[],wire.latest as SoccerRow[]);
export function soccerPrevious(row:CatalogEvidenceRow):SoccerRow|null{const matches=soccerFinalRows.filter(r=>r.key===row.key&&stable(r)===stable(row));return matches.length===1?matches[0]._soccer_previous??null:null}
export function soccerCaptureNote(row:CatalogEvidenceRow){const r=row as SoccerRow;return r._soccer_presence==='absent'?'Not in the final capture. Earlier evidence is retained; result unconfirmed.':r._soccer_presence==='ambiguous'?'Conflicting records in the final capture. Result unconfirmed.':r._soccer_presence==='matched'?'Matched to the final capture by original prop and outcome IDs.':r._soccer_presence==='new'?'First seen in the final capture; no earlier baseline supplied.':undefined}
export {wire as soccerCaptures};
