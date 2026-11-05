import {groupCatalogRows} from './catalogGroups.ts';
import type {CatalogEvidenceRow} from './catalogPresentation';
export function catalogBrowseGroups<T extends CatalogEvidenceRow & {category?:string}>(rows:T[],query:string,category:string,update:(rows:T[])=>T[]=rows=>rows){
 const term=query.trim().toLocaleLowerCase();
 return groupCatalogRows(rows).map(group=>{
  const incoming=update(group.rows);
  const visibleRows=incoming.filter(r=>(category==='All'||(r.category||'other')===category)&&`${r.market_name} ${r.outcome_name}`.toLocaleLowerCase().includes(term));
  return {...group,rows:incoming,visibleRows};
 }).filter(group=>group.visibleRows.length>0||(!term&&category==='All'&&group.rows.length===0));
}
