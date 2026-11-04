import {pokerCapture,pokerBaseline,pokerActual,pokerSelected,type PokerPhase,type PokerMarket} from './pokerEvidence.ts';
const symbols=['Circle','Triangle','Diamond'] as const;
/** Fixed before-table references, never prices at an inspected trade's clock.
 * Use each original Yes token directly; do not borrow a No price or normalize. */
export function pokerFeaturedContext(ids:readonly string[],phase:PokerPhase){
 const seen=new Set<string>();
 return ids.flatMap(id=>{
  if(seen.has(id))return [];seen.add(id);
  const market=pokerCapture.markets.find(m=>m.id===id&&m.kind==='winner');if(!market)return [];
  return [market];
 }).slice(0,3).map((market,slot)=>{
  const baseline=pokerBaseline(market),actual=pokerActual(market,phase);
  return {id:market.id,name:market.name,short:market.name.startsWith('Player ')||market.name==='Other'?market.name:market.name.split(' ').at(-1)!,slot,shape:symbols[slot],baseline:baseline?.p??null,baselineAt:baseline?.t??null,finish:actual?.finish??null};
 });
}
export function pokerTradeContext(market:PokerMarket,phase:PokerPhase,index:number|null){
 const selection=pokerSelected(market,phase,index),baseline=pokerBaseline(market);
 // Original array position distinguishes distinct trades even at one second.
 const sameAsBaseline=selection.point!==null&&selection.index===selection.points.indexOf(baseline!);
 const latest=selection.index===selection.points.length-1;
 const label=!selection.point?'No retained trade':phase==='before'?(sameAsBaseline?'Before final table':'Recorded trade'):sameAsBaseline?(latest?'Before final table · last recorded':'Before final table trade'):latest?'Last recorded trade':'Recorded trade';
 return {...selection,baseline,sameAsBaseline,label,showReading:phase==='final'||!sameAsBaseline};
}
