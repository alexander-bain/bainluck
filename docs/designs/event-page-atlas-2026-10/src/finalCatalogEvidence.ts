import {catalogPresentation,type CatalogContext,type CatalogPresentation,type CatalogEvidenceRow} from './catalogPresentation.ts';
export type ArchivedFinalRow={row_key:string;category:string;market_name:string;outcome_name:string;source:string;_market_id:number;format:string;threshold?:number|null;actual?:number|null;hit?:boolean|null;is_winner?:boolean|null;resolution_source?:string|null;probability?:number|null;over_probability?:number|null;observed_at?:string|null;movement?:number|null;_inverted?:boolean;[key:string]:unknown};
export type FinalCatalogRow=ArchivedFinalRow & CatalogEvidenceRow & {result_unconfirmed:boolean};
/** Preserve every source field; the native reference supplies the captured conflict flag. */
export function adaptFinalRows(rows:ArchivedFinalRow[],flags:Record<string,boolean>):FinalCatalogRow[]{
 return rows.map(row=>({...row,key:row.row_key,result_unconfirmed:flags[row.row_key]===true}));
}
/** A final capture cannot supply earlier probabilities or earlier settlement states. */
export function finalCatalogPresentation(row:FinalCatalogRow,context:CatalogContext,phase:string):CatalogPresentation{
 if(phase!=='Final')return {kind:'unavailable',label:'Earlier probability unavailable',value:null,observedAt:null};
 return catalogPresentation(row,context);
}
export function finalCatalogSearchText(row:FinalCatalogRow){
 return `${row.market_name} ${row.outcome_name} ${row.source} ${row._market_id}`;
}
/** Exact source-bound full-game total specimen. Do not infer a period/team scope from prose. */
export function isFinalTotalTrack(rows:FinalCatalogRow[],eventID:string):boolean{
 return eventID==='14780549'&&rows.length>1&&rows.every(row=>row.source==='kalshi'&&row._market_id===61880781&&row.category==='totals'&&row.market_type==='game_total'&&row.period==null&&typeof row.threshold==='number'&&Number.isFinite(row.threshold)&&/^Over /.test(row.outcome_name));
}
