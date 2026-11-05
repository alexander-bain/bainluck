export interface CatalogEvidenceRow {
 _display_scope?:unknown;_market_status?:unknown;settled?:unknown;
 id?:number|string; contributor_outcome_ids?:Array<number|string>; threshold?:number|null; period?:unknown;
 key:string; source:string; market_name:string; outcome_name:string; _market_id?:number|string;
 probability?:number|null; over_probability?:number|null; observed_at?:string|null;
 _inverted?:unknown; settlement_kind?:unknown; resolution_source?:string|null;
 is_winner?:boolean|null; window_closed?:unknown; result_unconfirmed?:boolean;
}
export interface CatalogContext {status:string;qualityHold:boolean;mode:string}
export type CatalogPresentation = {kind:'quote';label:'Recorded chance';value:number;observedAt:string}|{kind:'result'|'unavailable';label:string;value:null;observedAt:null};
export function catalogQuote(row:CatalogEvidenceRow):number|null {
 const raw=typeof row.probability==='number'?row.probability:typeof row.over_probability==='number'?row.over_probability:null;
 if(raw===null||!Number.isFinite(raw)||raw<0||raw>1)return null;
 return typeof row.probability==='number'?raw:row._inverted===true||/^(Under\b|No$)/i.test(row.outcome_name)?1-raw:raw;
}
export function catalogPresentation(row:CatalogEvidenceRow,context:CatalogContext):CatalogPresentation {
 const hold=(kind:'result'|'unavailable',label:string):CatalogPresentation=>({kind,label,value:null,observedAt:null});
 if(row.settlement_kind==='fair_value')return hold('result','Closed · no winner');
 if(row.result_unconfirmed===true||row.resolution_source==='ungradeable_result')return hold('result','Result unconfirmed');
 if(row.resolution_source&&typeof row.is_winner==='boolean')return hold('result',row.is_winner?'Won':'Lost');
 if(row._display_scope==='series'&&row._market_status==='open'&&row.settled===false&&row.is_winner==null&&catalogQuote(row)===null)return hold('result','Result pending');
 if(row.window_closed===true)return hold('result','Period ended · result pending');
 if(context.status==='completed')return hold('result','Result pending');
 const quote=catalogQuote(row);
 const clock=row.observed_at;
 if(context.mode!=='captured'||context.qualityHold||!['live','scheduled','field'].includes(context.status)||quote===null||!clock||!Number.isFinite(Date.parse(clock)))return hold('unavailable',context.mode==='loading'?'Loading…':'No recent price');
 return {kind:'quote',label:'Recorded chance',value:quote,observedAt:clock};
}
