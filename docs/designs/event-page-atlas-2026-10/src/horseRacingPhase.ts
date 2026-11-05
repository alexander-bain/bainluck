export type RacePhase='before'|'final';
type Trade={t:number;p:number};
type Market={id:string;trades:Trade[];place:number|null;resolved:boolean;settledYes:boolean};
export function racePhase<T extends Market>(markets:T[],phase:RacePhase,scheduled:number){
 if(!Number.isFinite(scheduled)||scheduled<=0)throw new Error('A verified scheduled-start instant is required');
 const eligible=markets.map(m=>({...m,trades:m.trades.filter(t=>Number.isFinite(t.t)&&Number.isFinite(t.p)&&t.p>0&&t.p<1&&(phase==='final'||t.t<scheduled)),place:phase==='final'?m.place:null,resolved:phase==='final'&&m.resolved,settledYes:phase==='final'?m.settledYes:null}));
 const points=eligible.flatMap(m=>m.trades),times=points.map(t=>t.t);
 const start=times.length?Math.min(...times):scheduled-3600000;
 const end=phase==='before'?scheduled:Math.max(scheduled,...times);
 const upper=phase==='before'?Math.min(1,Math.max(.1,Math.ceil(Math.max(0,...points.map(p=>p.p))*10)/10)):1;
 return {markets:eligible,domain:[start,end] as [number,number],upper};
}
export function lastBefore<T extends Trade>(trades:T[],scheduled:number):T|undefined{
 return trades.filter(t=>Number.isFinite(t.t)&&Number.isFinite(t.p)&&t.p>0&&t.p<1&&t.t<scheduled).sort((a,b)=>a.t-b.t).at(-1);
}
export function raceIdentity(id:string){
 return id==='662204'?{color:'var(--series-home)',shape:'circle' as const,mark:'●'}:id==='662191'?{color:'var(--series-away)',shape:'triangle' as const,mark:'▲'}:id==='662196'?{color:'var(--text-secondary)',shape:'diamond' as const,mark:'◆'}:{color:'var(--accent-brand)',shape:'square' as const,mark:'■'};
}
