import type {CatalogEvidenceRow} from './catalogPresentation';
export type ScoreGridRow=CatalogEvidenceRow&{category?:unknown;source_file?:unknown};
export type ScoreGrid<T>={scope:string;home:string;away:string;size:number;cells:{home:number;away:number;row:T}[];other:T};
const families:Record<string,{title:string;scope:string;size:number}>={62939468:{title:'Hull City AFC vs. Everton FC - Exact Score',scope:'Full match',size:6},64002155:{title:'Hull City AFC vs. Everton FC - 1st Half Exact Score',scope:'First half',size:3}};
export function exactScoreGrid<T extends ScoreGridRow>(rows:T[]):ScoreGrid<T>|null{
 const first=rows[0],family=first&&families[String(first._market_id)];if(!family||rows.length<2)return null;
 const cells:ScoreGrid<T>['cells']=[],seen=new Set<string>();let other:T|undefined;
 for(const row of rows){
  if(row.source!=='polymarket'||!['soccer-15311089-game-markets.json','soccer-final-15311089-game-markets.json'].includes(String(row.source_file))||row.category!=='other'||row._market_id!==first._market_id||row.market_name!==family.title||row.period!=null||row._inverted!=null)return null;
  if(row.outcome_name==='Any Other Score'){if(other)return null;other=row;continue;}
  const m=/^Hull City AFC ([0-5]) - ([0-5]) Everton FC$/.exec(row.outcome_name);if(!m)return null;
  const home=Number(m[1]),away=Number(m[2]),key=`${home}:${away}`;
  if(home>=family.size||away>=family.size||seen.has(key))return null;seen.add(key);cells.push({home,away,row});
 }
 if(!other||!cells.length)return null;
 return {scope:family.scope,home:'Hull',away:'Everton',size:family.size,cells,other};
}
// One fixed probability scale for both scopes; no field normalization or remainder estimate.
export function scoreGridStrength(value:number):number{return Math.sqrt(Math.max(0,Math.min(1,value)))*.85}
