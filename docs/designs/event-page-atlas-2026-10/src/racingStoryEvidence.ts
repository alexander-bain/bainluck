import {catalogPresentation,type CatalogEvidenceRow,type CatalogContext} from './catalogPresentation.ts';

export function racingStoryRows<T extends CatalogEvidenceRow>(rows:T[],source:string,marketID:string) {
 return rows.filter(row=>row.source===source&&String(row._market_id)===marketID);
}
export function racingStoryWindow<T extends CatalogEvidenceRow>(rows:T[],selection:number,size:number,context:CatalogContext) {
 const index=Math.min(Math.max(0,selection),Math.max(0,rows.length-1));
 const offset=Math.floor(index/size)*size;
 return {index,offset,selected:rows[index],shown:rows.slice(offset,offset+size).map(row=>({row,state:catalogPresentation(row,context)}))};
}
export function racingMatchupLabel(row:CatalogEvidenceRow,bindings:{id:string;subject:string;opponent:string}[]) {
 return bindings.find(pair=>pair.id===row.key&&row.outcome_name===`${pair.subject} — ${pair.subject} vs ${pair.opponent}`);
}

/** A story uses the same source identity as the complete catalog. */
export {catalogAnchor as racingStoryAnchor} from './catalogSelection.ts';
import {resolveCatalogSelection,type CatalogAnchor} from './catalogSelection.ts';
export function racingStableStory<T extends CatalogEvidenceRow>(rows:T[],anchor:CatalogAnchor<T>|null,size:number,context:CatalogContext){
 const selection=resolveCatalogSelection(rows,anchor,size);
 return {...selection,selected:selection.row,
  selectedState:selection.row?catalogPresentation(selection.row,selection.present?context:{...context,mode:'stale'}):null,
  shown:selection.shown.map(row=>({row,state:catalogPresentation(row,context)}))};
}

export function racingStorySimulation<T extends CatalogEvidenceRow>(rows:T[],mode:string){
 const ids=['63989363','63989365'];
 if(mode==='empty')return rows.filter(row=>!ids.includes(String(row._market_id)));
 if(mode==='omit')return rows.filter(row=>!(String(row._market_id)==='63989365'&&row.outcome_name==='Lewis Hamilton')&&!(String(row._market_id)==='63989363'&&row.outcome_name==='Leclerc — Leclerc vs Russell'));
 if(mode!=='reverse')return rows;
 const groups=ids.map(id=>rows.filter(row=>String(row._market_id)===id));
 return rows.map(row=>{const group=groups.find(g=>g.includes(row));return group?group[group.length-1-group.indexOf(row)]:row});
}
