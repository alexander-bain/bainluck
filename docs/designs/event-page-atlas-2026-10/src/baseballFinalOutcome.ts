import bindings from './baseball-final-bindings.json' with {type:'json'};
import type {CatalogEvidenceRow} from './catalogPresentation';
export type BaseballRow=CatalogEvidenceRow&{category?:unknown;source_file?:unknown;actual?:unknown;pregame_mark?:unknown};
export type BaseballOutcome<T>={player:string;unit:string;threshold:number;over:T;under:T;actual:number|null};
export function baseballFinalOutcome<T extends BaseballRow>(rows:T[],status:string):BaseballOutcome<T>|null{
 const first=rows[0],b=first&&(bindings as Record<string,{title:string;player:string;unit:string;threshold:number}>)[String(first._market_id)];
 if(status!=='completed'||!b||rows.length!==2)return null;
 let over:T|undefined,under:T|undefined;
 for(const r of rows){if(r.source!=='polymarket'||r.source_file!=='mlb-15321836-game-markets.json'||r.category!=='player_props'||r._market_id!==first._market_id||r.market_name!==b.title||r.threshold!==b.threshold||r.period!=null)return null;
  if(r.outcome_name==='Over'&&r._inverted===false&&!over)over=r;else if(r.outcome_name==='Under'&&r._inverted===true&&!under)under=r;else return null;
 }
 if(!over||!under)return null;
 const a=over.actual,actual=typeof a==='number'&&Number.isSafeInteger(a)&&a>=0&&a<=100&&a===under.actual?a:null;
 return {player:b.player,unit:b.unit,threshold:b.threshold,over,under,actual};
}
export function baseballBaseline(row:BaseballRow):number|null{const p=row.pregame_mark;return typeof p==='number'&&Number.isFinite(p)&&p>=0&&p<=1?(row._inverted===true?1-p:p):null}
export function baseballPredicate(row:BaseballRow,threshold:number):string{return row.outcome_name==='Over'?`At least ${Math.ceil(threshold)}`:`At most ${Math.floor(threshold)}`}
