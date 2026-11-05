import {duelSeries,duelWire,duelStart,duelCents,type DuelPhase} from './playerDuelEvidence.ts';

/** Endpoint distance is price movement, never elapsed time or outright-win probability. */
export function playerDuelMovement(phase:DuelPhase='final',wire=duelWire){
 return duelSeries('duel',phase,'all',wire).map(row=>{
  const from=phase==='before'?row.points[0]:row.baseline;
  const to=row.points.at(-1);
  const admitted=from&&to&&to.at>from.at&&(phase==='before'?to.at<duelStart:to.at>=duelStart);
  return {key:row.key,ticker:row.ticker,name:row.name,fromLabel:phase==='before'?'First captured':'Pre-game',toLabel:phase==='before'?'Last before game':'Last trade',from:from??null,to:admitted?to:null,change:admitted?to.p-from.p:null};
 });
}
export const duelPriceChange=(change:number|null)=>change===null?'No later trade':change===0?'Unchanged':`${change>0?'+':'−'}${duelCents(Math.abs(change))}`;
