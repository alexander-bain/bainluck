import capture from './associatedSeries.json' with {type:'json'};
import type {CatalogEvidenceRow} from './catalogPresentation';
export type SeriesRow=CatalogEvidenceRow & {source_file:string;_display_scope:'series';_market_status:string;settled:boolean;category:string;_market_id:number|string;outcome_id:number;series_original:Record<string,unknown>;[key:string]:unknown};
/** Explicit related-event response bindings; no title-based association or game-result inference. */
export const associatedSeriesRows:SeriesRow[]=capture.groups.flatMap(group=>group.rows.map(row=>{
 const original=JSON.parse(row.original);
 return {...original,key:row.id,category:'series',resolution_source:row.resolution,series_original:original};
}));
export const associatedSeriesRecords=capture.records;
export function seriesRowsForEvent(id:unknown):SeriesRow[]{return id===capture.eventID?associatedSeriesRows:[];}
export function seriesRecord(row:CatalogEvidenceRow){return associatedSeriesRecords.find(record=>record.id===row.key&&String(record.marketID)===String(row._market_id)&&record.source===row.source);}
export function seriesSubject(row:CatalogEvidenceRow):string{
 const record=seriesRecord(row);if(!record)return row.outcome_name;
 if(record.team!=null)return `${record.team} · ${record.wins}–${record.losses} series score`;
 return ['62898791','63348824'].includes(record.marketID)?`Series winner · ${record.label}`:record.label;
}
export function seriesScoreRows(rows:CatalogEvidenceRow[]):boolean{return rows.length>0&&rows.every(row=>seriesRecord(row)?.team!=null);}
