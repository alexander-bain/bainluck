import type {CatalogEvidenceRow} from './catalogPresentation';
export type TennisScoreRow=CatalogEvidenceRow&{category?:unknown;source_file?:unknown};
export type TennisScore<T>={players:[string,string];target:number;cells:{player:number;won:number;lost:number;row:T}[]};
const families:Record<string,{players:[string,string];target:number;file:string}>={
 '60804333':{players:['Alexander Zverev','Ben Shelton'],target:3,file:'tennis-15310688-game-markets.json'},
 '65129363':{players:['Alejandro Davidovich Fokina','Frances Tiafoe'],target:2,file:'raw/tennis-15327291-game-markets.json'}
};
// These bindings describe retained provider contracts, not a general title parser.
export function tennisScoreOutcome<T extends TennisScoreRow>(rows:T[],status:string):TennisScore<T>|null{
 const first=rows[0],f=first&&families[String(first._market_id)];if(!f||status!=='completed'||!rows.length)return null;
 const cells:TennisScore<T>['cells']=[],seen=new Set<string>();
 for(const row of rows){
  if(row.source!=='kalshi'||row.source_file!==f.file||row._market_id!==first._market_id||row.category!=='other'||row.market_name!==`${f.players[0]} vs ${f.players[1]}: Exact Match Score`||row.period!=null||row._inverted!=null)return null;
  let match:{player:number;won:number;lost:number;row:T}|undefined;
  for(let player=0;player<2;player++)for(let lost=0;lost<f.target;lost++)if(row.outcome_name===`${f.players[player]} wins ${f.target}-${lost}`)match={player,won:f.target,lost,row};
  if(!match||seen.has(`${match.player}:${match.lost}`))return null;
  seen.add(`${match.player}:${match.lost}`);cells.push(match);
 }
 return {players:f.players,target:f.target,cells};
}
