import {completionPregame} from './nflCompletion.ts';
import {nflAdmitted,nflBaselineRow,nflActual} from './nflReconciliation.ts';
import type {CatalogEvidenceRow} from './catalogPresentation';
export type PlayerProfileRow=CatalogEvidenceRow&{player_entity_key?:unknown;category?:unknown;pregame_mark?:unknown;source_file?:unknown};
// Bound source families, not a general title parser. Production supplies equivalent typed semantics.
export const playerProfileBindings:Record<string,{title:string;unit:string}>={
 '65129757':{title:'Philadelphia vs Jacksonville: Passing Completions',unit:'completions'},
 '65129771':{title:'Philadelphia vs Jacksonville: Passing Interceptions',unit:'interceptions'},
 '64627553':{title:'Philadelphia vs Jacksonville: Passing Yards',unit:'passing yards'},
 '64654478':{title:'Philadelphia vs Jacksonville: Rushing Yards',unit:'rushing yards'},
 '64654471':{title:'Philadelphia vs Jacksonville: Receiving Yards',unit:'receiving yards'},
 '65080168':{title:'Philadelphia vs Jacksonville: Passing Touchdowns (Protected)',unit:'passing touchdowns'},
 '64627547':{title:'Philadelphia vs Jacksonville: Passing Touchdowns',unit:'passing touchdowns'},
 '65129743':{title:'Philadelphia vs Jacksonville: Passing Attempts',unit:'attempts'},
 '65080210':{title:'Philadelphia vs Jacksonville: Rushing Yards (Protected)',unit:'rushing yards'},
 '65080182':{title:'Philadelphia vs Jacksonville: Passing Yards (Protected)',unit:'passing yards'},
 '65080196':{title:'Philadelphia vs Jacksonville: Receiving Yards (Protected)',unit:'receiving yards'},
};
export type PlayerProfilePoint<T>={row:T;playerID:string;player:string;threshold:number;pregame:number|null};
export type PlayerProfile<T>={unit:string;points:PlayerProfilePoint<T>[];players:{id:string;name:string;count:number}[]};
export function playerCatalogProfile<T extends PlayerProfileRow>(rows:T[]):PlayerProfile<T>|null{
 const first=rows[0],binding=first&&playerProfileBindings[String(first._market_id)];
 if(!binding||rows.length<2)return null;
 const points:PlayerProfilePoint<T>[]=[],seen=new Set<string>();
 for(const row of rows){
  const n=row.threshold;
  if(row.source!=='kalshi'||(row.source_file!=='nfl-14639175-game-markets.json'&&!nflAdmitted(row))||row.category!=='player_props'||String(row._market_id)!==String(first._market_id)||row.market_name!==binding.title||row.period!=null||row._inverted===true||typeof row.player_entity_key!=='string'||!row.player_entity_key||typeof n!=='number'||!Number.isSafeInteger(n)||n<0||n>100000)return null;
  const suffix=`: ${n}+`;if(!row.outcome_name.endsWith(suffix))return null;
  const player=row.outcome_name.slice(0,-suffix.length);if(!player.trim())return null;
  const identity=JSON.stringify([row.player_entity_key,n]);if(seen.has(identity))return null;seen.add(identity);
  if(points.some(p=>p.playerID===row.player_entity_key&&p.player!==player))return null;
  const baseline=completionPregame(row)?.value??nflBaselineRow(row).pregame_mark;
  points.push({row,playerID:row.player_entity_key,player,threshold:n,pregame:typeof baseline==='number'&&Number.isFinite(baseline)&&baseline>=0&&baseline<=1?baseline:null});
 }
 const players=Array.from(new Set(points.map(p=>p.playerID))).map(id=>({id,name:points.find(p=>p.playerID===id)!.player,count:points.filter(p=>p.playerID===id).length}));
 return {unit:binding.unit,points,players};
}

export function playerFinalActual<T extends PlayerProfileRow>(profile:PlayerProfile<T>,playerID:string):number|null{
 const rows=profile.points.filter(p=>p.playerID===playerID).map(p=>p.row).filter(r=>nflAdmitted(r)&&['matched','new'].includes(String((r as any)._nfl_presence)));
 const values=rows.map(nflActual);return values.length&&values.every(v=>v!==null&&v===values[0])?values[0]:null;
}
