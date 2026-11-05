import {catalogPresentation,type CatalogEvidenceRow} from './catalogPresentation.ts';
// Exact identities from this retained fixture; not a production adapter.
export const aflwSides=[{name:'Sydney Swans',id:242153909},{name:'Carlton Blues',id:242153908}] as const;
export function aflwHeadlineSides(rows:CatalogEvidenceRow[],status:string,mode:string){
 return aflwSides.map(side=>{
  const matches=rows.filter(row=>row._market_id===64356945&&row.source==='polymarket'&&row.contributor_outcome_ids?.includes(side.id));
  const row=matches.length===1?matches[0]:undefined;
  const state=row?catalogPresentation(row,{status,qualityHold:false,mode}):null;
  return {...side,baseline:null,baselineLabel:'Pregame unavailable',quote:state?.kind==='quote'?state:null};
 });
}
