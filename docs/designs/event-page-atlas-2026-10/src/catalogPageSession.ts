import {groupCatalogRows} from './catalogGroups.ts';
import type {CatalogEvidenceRow} from './catalogPresentation';
export type SessionRow=CatalogEvidenceRow & {category?:string};
export type CatalogEntry<T>={key:string;rows:T[];absentFromUpdate:boolean};
export type CatalogSnapshot<T>={eventID:string;status:string;qualityHold:boolean;rows:T[]};
export type CatalogSession<T>={snapshot:CatalogSnapshot<T>;entries:CatalogEntry<T>[]};
/** Receive complete, unfiltered snapshots. Prior rows belong to this exact page event only. */
export function receiveCatalogSnapshot<T extends SessionRow>(previous:CatalogSession<T>|null,snapshot:CatalogSnapshot<T>):CatalogSession<T>{
 if(previous?.snapshot===snapshot)return previous;
 const incoming=groupCatalogRows(snapshot.rows).map(group=>({...group,absentFromUpdate:false}));
 const present=new Set(incoming.map(group=>group.key));
 const held=previous?.snapshot.eventID===snapshot.eventID?previous.entries.filter(group=>!present.has(group.key)).map(group=>({...group,absentFromUpdate:true})):[];
 return {snapshot,entries:[...incoming,...held]};
}
export function catalogEntryContext<T>(session:CatalogSession<T>,entry:CatalogEntry<T>,mode:string){
 return {status:session.snapshot.status,qualityHold:session.snapshot.qualityHold||entry.absentFromUpdate,mode:entry.absentFromUpdate?'stale':mode};
}
export function browseCatalogEntries<T extends SessionRow>(entries:CatalogEntry<T>[],query:string,category:string,update:(rows:T[])=>T[]=rows=>rows){
 const term=query.trim().toLocaleLowerCase();
 return entries.map(group=>{
  const rows=update(group.rows);
  const visibleRows=rows.filter(row=>(category==='All'||(row.category||'other')===category)&&`${row.market_name} ${row.outcome_name}`.toLocaleLowerCase().includes(term));
  return {...group,rows,visibleRows};
 }).filter(group=>group.visibleRows.length>0||(!term&&category==='All'&&group.rows.length===0));
}
