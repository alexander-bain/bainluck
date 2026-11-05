import type {ChessContender,ChessPoint} from './chessHistory.ts';
export type ChessMovementRow={id:number;name:string;first:ChessPoint;last:ChessPoint;change:number};
export type ChessMovement={earlier:string;later:string;rows:ChessMovementRow[];scale:number};
/** Compare adjacent captured instants, never skip a sparse instant to find a better story. */
export function chessMovement(all:ChessContender[],through:string):ChessMovement|null{
 const cutoff=Date.parse(through);if(!Number.isFinite(cutoff))return null;
 const clocks=new Map<number,string>();
 for(const c of all)for(const p of c.history){const t=Date.parse(p.timestamp);if(Number.isFinite(t)&&t<=cutoff)clocks.set(t,p.timestamp)}
 const times=[...clocks.keys()].sort((a,b)=>a-b);
 if(times.length<2||times.at(-1)!==cutoff)return null;
 const later=times.at(-1)!,earlier=times.at(-2)!;
 const ids=new Map<number,number>();for(const c of all)ids.set(c.outcome_id,(ids.get(c.outcome_id)??0)+1);
 const at=(c:ChessContender,t:number)=>{const matches=c.history.filter(p=>Date.parse(p.timestamp)===t);const p=matches[0];return matches.length===1&&Number.isFinite(p.probability)&&p.probability>=0&&p.probability<=1?p:null};
 const rows:ChessMovementRow[]=[];
 for(const c of all){if(ids.get(c.outcome_id)!==1)continue;const first=at(c,earlier),last=at(c,later);if(first&&last)rows.push({id:c.outcome_id,name:c.name,first,last,change:last.probability-first.probability})}
 if(rows.length<2)return null;
 rows.sort((a,b)=>Math.abs(b.change)-Math.abs(a.change)||a.id-b.id);
 const max=Math.max(...rows.map(r=>Math.abs(r.change)));
 return {earlier:clocks.get(earlier)!,later:clocks.get(later)!,rows,scale:Math.max(.01,Math.ceil((max-1e-12)*100)/100)};
}
export function chessMovementLabel(change:number){const pts=Math.abs(change)*100;return pts<.0000001?'No change':`${change>0?'+':'−'}${Number(pts.toFixed(2))} pts`}
