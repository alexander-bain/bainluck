import c from './skatingCapture.json' with {type:'json'};
export const skatingCapture=c;
export type SkatePhase='before'|'final';
export type SkateMarket=(typeof c.markets)[number];
export type SkateResult=(typeof c.results)[number];
export const skatingFeatured=['1347941','1347948','1347949'];
export function skatingMarket(id:string){return c.markets.find(m=>m.id===id)??null;}
export function skatingTrades(m:SkateMarket|null,phase:SkatePhase,side='Yes'){return (m?.sides.find(s=>s.side===side)?.points??[]).filter(p=>p.size>0&&Number.isFinite(p.t)&&Number.isFinite(p.p)&&p.p>0&&p.p<1&&(phase==='before'?p.t<c.beforeDay:p.t<=c.reportAt));}
export function skatingBaseline(m:SkateMarket|null,side='Yes'){return skatingTrades(m,'before',side).at(-1)??null;}
export function skatingResult(id:string,phase:SkatePhase){return phase==='final'?c.results.find(r=>r.id===id)??null:null;}
export function skatingGrade(m:SkateMarket|null,phase:SkatePhase,side='Yes'){if(phase==='before'||!m)return null;const won=m.sides.find(s=>s.side===side)?.won;return won===true?'Won':won===false?'Lost':'Result pending';}
export function skatingSelection(m:SkateMarket|null,phase:SkatePhase,index:number|null){const points=skatingTrades(m,phase);const i=index===null?points.length-1:Math.max(0,Math.min(points.length-1,index));return {points,index:Math.max(0,i),point:points[i]??null};}
export function skatingComparisons(id:string){return [...new Set([id,...skatingFeatured])].slice(0,3).map(skatingMarket).filter((m):m is SkateMarket=>m!==null);}
export function skatingDomain(phase:SkatePhase):[number,number]{const points=c.markets.flatMap(m=>skatingTrades(m,phase));return [Math.min(c.beforeDay,...points.map(p=>p.t)),phase==='before'?c.beforeDay:c.reportAt];}
export function skatingScale(phase:SkatePhase,full:boolean){return full?1:Math.min(1,Math.max(.1,Math.ceil(Math.max(0,...c.markets.flatMap(m=>skatingTrades(m,phase)).map(p=>p.p))*10)/10));}
export function skatingIdentity(id:string){return id==='1347941'?{color:'var(--series-home)',shape:'circle' as const}:id==='1347948'?{color:'var(--series-away)',shape:'triangle' as const}:{color:'var(--text-secondary)',shape:'diamond' as const};}
export function skatingFinishGroup(id:string,phase:SkatePhase){if(phase==='before')return [];const selected=skatingResult(id,phase);return [...c.results.slice(0,5),...(selected&&!c.results.slice(0,5).includes(selected)?[selected]:[])].map(r=>({...r,gap:(r.ms-c.results[0].ms)/1000,short:'#'+r.rank+' '+r.name.split(' ').at(-1)}));}
export function skatingMovement(){return skatingFeatured.map(skatingMarket).filter((m):m is SkateMarket=>m!==null).flatMap(m=>{const first=skatingTrades(m,'before')[0],last=skatingBaseline(m);return first&&last?[{market:m,first,last,short:m.name.replace(/ \([A-Z]+\)$/,'').split(' ').at(-1)!}]:[];});}
export function skatingMedal(rank:number){return rank===1?'Gold':rank===2?'Silver':rank===3?'Bronze':'#'+rank;}
