import {skatingCapture, skatingMarket, skatingTrades, skatingBaseline, type SkatePhase} from './skatingEvidence.ts';

export function skatingOutcomeHistory(id:string, side:string, phase:SkatePhase, selected:number|null=null) {
  const market=skatingMarket(id);
  if(!market || (side!=='Yes' && side!=='No')) return null;
  const original=market.sides.find(s=>s.side===side);
  if(!original) return null;
  const points=skatingTrades(market,phase,side);
  const index=points.length ? Math.min(points.length-1,Math.max(0,selected??points.length-1)) : 0;
  const baseline=skatingBaseline(market,side);
  return {market,side,token:original.token,condition:market.condition,points,index,point:points[index]??null,baseline,
    baselineIndex:baseline ? points.indexOf(baseline) : -1,
    meaning:side==='Yes'?'Wins gold':'Doesn’t win gold'};
}

export function skatingOutcomeScale(values:ReadonlyArray<{p:number}>,full=false) {
  if(full) return 1;
  const maximum=Math.max(0,...values.map(p=>p.p));
  return [.01,.02,.05,.1,.2,.25,.5,.75,1].find(n=>n>=maximum)??1;
}

export function skatingOutcomeDomain(phase:SkatePhase):[number,number] {
  const all=skatingCapture.markets.flatMap(m=>m.sides.flatMap(s=>skatingTrades(m,phase,s.side)));
  return [Math.min(skatingCapture.beforeDay,...all.map(p=>p.t)),phase==='before'?skatingCapture.beforeDay:skatingCapture.reportAt];
}
