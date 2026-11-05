import {dartsSeries,dartsTickers,type TradePoint} from './dartsMatchEvidence.ts';
export type DartsMovementSeries={ticker:string;name:string;points:TradePoint[]};
export function dartsMovement(through:number|null,series:DartsMovementSeries[]=dartsSeries()) {
 if(series.length!==2||dartsTickers.some(id=>series.filter(s=>s.ticker===id).length!==1))return null;
 const ordered=dartsTickers.map(id=>series.find(s=>s.ticker===id)!);
 const point=(s:DartsMovementSeries,t:number)=>{const a=s.points.filter(p=>p.at===t),p=a[0];return a.length===1&&Number.isFinite(t)&&Number.isFinite(p.p)&&p.p>=0&&p.p<=1&&Number.isFinite(p.volume)&&p.volume>0?p:null};
 const shared=[...new Set(ordered[0].points.map(p=>p.at))].filter(t=>ordered.every(s=>point(s,t))).sort((a,b)=>a-b);
 const later=through===null?shared.at(-1):through;if(later===undefined||!shared.includes(later))return null;
 const earlier=shared[0];if(earlier>=later)return null;
 return {earlier,later,rows:ordered.map(s=>{const first=point(s,earlier)!.p,last=point(s,later)!.p;return {ticker:s.ticker,name:s.name,first,last,change:last-first}})};
}
export const dartsMovementChange=(n:number)=>`${n>0?'+':n<0?'−':''}${Number((Math.abs(n)*100).toFixed(2))} pts`;
