import c from './dartsSetsCapture.json' with {type:'json'};
export const dartsSetsCapture=c;
export type SetPhase='before'|'final';
export type SetPlayer=(typeof c.players)[number];
export function setTrades(index:number,phase:SetPhase){return (c.players[index]?.points??[]).filter(p=>p.size>0&&Number.isFinite(p.t)&&Number.isFinite(p.p)&&p.p>0&&p.p<1&&(phase==='before'?p.t<c.scheduledStart:p.t<=c.reportAt));}
export function setBaseline(index:number){return setTrades(index,'before').at(-1)??null;}
export function setTimes(phase:SetPhase){return [...new Set(c.players.flatMap((_,i)=>setTrades(i,phase).map(p=>p.t)))].sort((a,b)=>a-b);}
export function setReading(index:number,at:number|null,phase:SetPhase){const points=setTrades(index,phase);return at===null?points.at(-1)??null:points.find(p=>p.t===at)??null;}
export function actualSet(set:number,phase:SetPhase){return phase==='final'?c.sets.find(s=>s.set===set)??null:null;}
export function setScorePath(phase:SetPhase){return phase==='final'?[{set:0,price:0,humphries:0},...c.sets.map(s=>({set:s.set,price:s.scores[0],humphries:s.scores[1]}))]:[];}
export function setWindow(phase:SetPhase):[number,number]{const t=setTimes(phase);return [Math.min(...t,c.scheduledStart),phase==='before'?c.scheduledStart:c.reportAt];}
export function setVerdict(index:number,phase:SetPhase){return phase==='final'&&c.players[index]?(c.players[index].resolvedWinner?'Won':'Lost'):null;}
