import type {CatalogEvidenceRow} from './catalogPresentation';
export type FinalPlayerRow=CatalogEvidenceRow&{actual?:unknown;category?:unknown;source_file?:unknown};
const families:Record<string,{title:string;unit:string}>={64870965:{title:'Boston vs Minnesota: Goals',unit:'goals'},64870807:{title:'Boston vs Minnesota: Assists',unit:'assists'},64871068:{title:'Boston vs Minnesota: Points',unit:'points'}};
export type FinalPlayerProfile<T>={unit:string;points:{row:T;player:string;threshold:number}[];players:string[]};
export function finalPlayerMilestones<T extends FinalPlayerRow>(rows:T[],status:string):FinalPlayerProfile<T>|null{
 const first=rows[0],family=first&&families[String(first._market_id)];if(status!=='completed'||!family||rows.length<2)return null;
 const points:FinalPlayerProfile<T>['points']=[],seen=new Set<string>();
 for(const row of rows){const threshold=row.threshold;
  if(row.source!=='kalshi'||row.source_file!=='nhl-15169793-game-markets.json'||row.category!=='player_props'||row.market_name!==family.title||row._market_id!==first._market_id||row.period!=null||row._inverted!==false||typeof threshold!=='number'||!Number.isSafeInteger(threshold)||threshold<1||threshold>100)return null;
  const suffix=`: ${threshold}+`;if(!row.outcome_name.endsWith(suffix))return null;
  const player=row.outcome_name.slice(0,-suffix.length);if(!player.trim())return null;
  const key=JSON.stringify([player,threshold]);if(seen.has(key))return null;seen.add(key);points.push({row,player,threshold});
 }
 // Player labels are scoped to this bound source question; no cross-market person matching.
 return {unit:family.unit,points,players:[...new Set(points.map(p=>p.player))]};
}
export function finalPlayerActual<T extends FinalPlayerRow>(profile:FinalPlayerProfile<T>,player:string):number|null{
 const values=profile.points.filter(p=>p.player===player).map(p=>p.row.actual);
 if(!values.length||values.some(v=>typeof v!=='number'||!Number.isSafeInteger(v)||v<0||v>100))return null;
 return values.every(v=>v===values[0])?values[0] as number:null;
}

export function finalPlayerIsField<T>(profile:FinalPlayerProfile<T>):boolean{return profile.points.length>0&&profile.players.length===profile.points.length&&profile.points.every(p=>p.threshold===profile.points[0].threshold)}

export function finalPlayerFieldWindow<T>(profile:FinalPlayerProfile<T>,visibleRows:T[],selected:T|null,count=6):FinalPlayerProfile<T>['points']{
 const matching=profile.points.filter(p=>visibleRows.includes(p.row));
 const index=matching.findIndex(p=>p.row===selected),size=Math.max(1,count),offset=Math.floor(Math.max(0,index)/size)*size;
 return matching.slice(offset,offset+size);
}
