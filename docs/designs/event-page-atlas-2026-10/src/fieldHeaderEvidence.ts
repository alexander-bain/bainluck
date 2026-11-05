import {selectedPregame} from './pregameEvidence.ts';
import {catalogPresentation, type CatalogContext, type CatalogEvidenceRow} from './catalogPresentation.ts';

export interface FieldHeaderConfig {
 id:string; title:string; role:string; predicate:string; source:string; marketID:string;
 rowKeys:string[]; missingNote:string; historyNote:string; contextNote:string;
}

// Explicit fixture bindings: a podium, matchup or fastest-lap quote cannot become a win chance.
export function selectFieldHeader<T extends CatalogEvidenceRow>(config:FieldHeaderConfig, rows:T[], context:CatalogContext) {
 const keys=new Set(config.rowKeys);
 const bound=rows.filter(row=>keys.has(row.key)&&row.source===config.source&&String(row._market_id)===config.marketID);
 const named=[...bound].sort((a,b)=>a.outcome_name.localeCompare(b.outcome_name,'en'));
 const presented=bound.map(row=>({row,state:catalogPresentation(row,context)}));
 const quoted=presented.flatMap(({row,state})=>state.kind==='quote'?[{row,value:state.value,observedAt:state.observedAt}]:[])
  .sort((a,b)=>b.value-a.value||a.row.outcome_name.localeCompare(b.row.outcome_name,'en'));
 const resolved=presented.filter(({state})=>state.kind==='result'&&(state.label==='Won'||state.label==='Lost'));
 return {bound,named,quoted,resolved,reached:resolved.filter(x=>x.state.label==='Won').length,missed:resolved.filter(x=>x.state.label==='Lost').length,pending:bound.length-resolved.length};
}

export function fieldBaselineLabel(id:string,plural=true):string {
 return id==='economics'?'Earlier chance':id==='racing'?(plural?'Pre-race chances':'Pre-race chance'):(plural?'Pre-event chances':'Pre-event chance');
}
export function fieldBaselineSummary<T extends CatalogEvidenceRow>(config:FieldHeaderConfig,rows:T[],context:CatalogContext){
 const bound=selectFieldHeader(config,rows,context).bound;
 return {label:fieldBaselineLabel(config.id),known:bound.filter(r=>selectedPregame(r)!==null).length,total:bound.length};
}
