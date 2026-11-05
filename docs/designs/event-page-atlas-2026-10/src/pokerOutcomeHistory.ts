import {pokerCapture as c,pokerPoints,pokerBaseline,pokerResult,pokerActual,type PokerPhase,type PokerMarket} from './pokerEvidence.ts';
import {probabilityLabel} from './probabilityLabel.ts';

export function pokerOutcomeMeaning(m:PokerMarket,side:string) {
  return m.kind==='nationality'?(side==='Yes'?'American winner':'Winner from outside the USA'):(side==='Yes'?'Wins the tournament':'Doesn’t win the tournament');
}
/** Refuse absent original identities; never use pokerMarket's primary-chart fallback here. */
export function pokerOutcomeHistory(id:string,side:string,phase:PokerPhase,selected:number|null=null) {
  const market=c.markets.find(m=>m.id===id),original=market?.sides.find(s=>s.side===side);
  if(!market||!original||(side!=='Yes'&&side!=='No'))return null;
  const points=pokerPoints(market,phase,side),baseline=pokerBaseline(market,side);
  const index=points.length?Math.min(points.length-1,Math.max(0,selected??points.length-1)):0;
  const start=phase==='before'?(points[0]??null):baseline,end=points.at(-1)??null,single=start!==null&&start===end;
  const raw=pokerResult(market,phase,side);
  return {market,side,token:original.token,condition:market.condition,meaning:pokerOutcomeMeaning(market,side),points,index,point:points[index]??null,baseline,baselineIndex:baseline?points.indexOf(baseline):-1,
    start,end,single,move:start&&end&&!single?end.p-start.p:null,
    startLabel:phase==='before'?'First captured trade':'Before final table',
    endLabel:phase==='before'?(single?'Before final table · only captured trade':'Before final table'):(single?'Before final table · last recorded':'Last recorded trade'),
    grade:raw==='Won'?'Happened':raw==='Lost'?'Didn’t happen':raw,actual:pokerActual(market,phase),tournamentBaseline:null};
}
export function pokerOutcomeScale(points:ReadonlyArray<{p:number}>,full=false) {
  if(full)return 1;const max=Math.max(0,...points.map(p=>p.p));
  return [.01,.02,.05,.1,.2,.25,.5,.75,1].find(n=>n>=max)??1;
}
export function pokerOutcomeDomain(phase:PokerPhase,selectedPoints?:ReadonlyArray<{t:number}>):[number,number] {
  const points=selectedPoints??c.markets.flatMap(m=>m.sides.flatMap(s=>pokerPoints(m,phase,s.side)));
  return [Math.min(c.scheduledFinalTable,...points.map(p=>p.t)),phase==='before'?c.scheduledFinalTable:c.resultReportAt];
}
export function pokerOutcomeMove(move:number|null) {
  if(move===null)return 'Comparison unavailable';if(move===0)return 'Same recorded chance at both times';
  return probabilityLabel(Math.abs(move)).replace('%','')+' points '+(move>0?'higher':'lower');
}
