import wire from './pokerCapture.json' with {type:'json'};
export const pokerCapture=wire;
export type PokerPhase='before'|'final';
export type PokerMarket=(typeof wire.markets)[number];
export type PokerPoint=PokerMarket['sides'][number]['points'][number];
export const pokerWinners=wire.markets.filter(m=>m.kind==='winner');
export const pokerNamed=pokerWinners.filter(m=>m.actual!==null);
export const pokerNational=wire.markets.find(m=>m.kind==='nationality')!;
export function pokerMarket(id:string){return wire.markets.find(m=>m.id===id)??pokerWinners[1];}
export function pokerPoints(m:PokerMarket,phase:PokerPhase,side='Yes'){
 return (m.sides.find(s=>s.side===side)?.points??[]).filter(p=>Number.isFinite(p.t)&&Number.isFinite(p.p)&&p.p>0&&p.p<1&&p.size>0&&(phase==='final'?p.t<=wire.resultReportAt:p.t<wire.scheduledFinalTable));
}
export function pokerBaseline(m:PokerMarket,side='Yes'){return pokerPoints(m,'before',side).at(-1)??null;}
export function pokerSelected(m:PokerMarket,phase:PokerPhase,index:number|null,side='Yes'){
 const points=pokerPoints(m,phase,side);const i=index===null?(phase==='final'?Math.max(0,points.length-1):Math.max(0,points.indexOf(pokerBaseline(m,side)!))):Math.max(0,Math.min(points.length-1,index));
 return {points,index:i,point:points[i]??null};
}
export function pokerResult(m:PokerMarket,phase:PokerPhase,side='Yes'){
 if(phase==='before')return null;
 const result=m.sides.find(s=>s.side===side)?.resolved;
 return result===true?'Won':result===false?'Lost':'Result pending';
}
export function pokerActual(m:PokerMarket,phase:PokerPhase){return phase==='final'?m.actual:null;}
export function pokerField(){const total=pokerNamed.reduce((s,m)=>s+m.actual!.chips,0);return pokerNamed.map(m=>({id:m.id,name:m.name.charAt(0)+'. '+m.name.split(' ').slice(1).join(' '),fullName:m.name,chips:m.actual!.chips/total,chance:pokerBaseline(m)?.p??null})).sort((a,b)=>b.chips-a.chips);}
/** Every dot is an original Yes trade, including multiple prices in the same second. */
export function pokerPlot(m:PokerMarket,phase:PokerPhase){return pokerPoints(m,phase).map(p=>({...p}));}
export function pokerDomain(phase:PokerPhase):[number,number]{const points=pokerNamed.flatMap(m=>pokerPoints(m,phase));return [Math.min(...points.map(p=>p.t)),phase==='before'?wire.scheduledFinalTable:wire.resultReportAt];}
export function pokerScale(phase:PokerPhase,full:boolean){return full?1:Math.min(1,Math.max(.1,Math.ceil(Math.max(0,...pokerNamed.flatMap(m=>pokerPoints(m,phase)).map(p=>p.p))*10)/10));}
export function pokerChoice(ids:string[],selected:string){return [selected,...ids.filter(id=>id!==selected)].slice(0,3);}
