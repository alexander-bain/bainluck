import wire from './ceremonyCapture.json' with {type:'json'};
export const ceremonyCapture=wire;
export type AwardPhase='before'|'final';
export type AwardWindow='recent'|'earlier'|'all';
export type AwardRace=(typeof wire.races)[number];
export type AwardMarket=AwardRace['markets'][number];
export type AwardPoint=AwardMarket['sides'][number]['points'][number];
export type AwardCapture=typeof wire;
export function awardRace(id:string,capture:AwardCapture=wire){return capture.races.find(r=>r.id===id)??null}
export function awardReading(raceID:string,id:string,side:string,phase:AwardPhase,capture:AwardCapture=wire){
 const race=awardRace(raceID,capture),market=race?.markets.find(m=>m.id===id),original=market?.sides.find(s=>s.side===side);if(!race||!market||!original||!['Yes','No'].includes(side))return null;
 const points=original.points.filter(p=>p.asset===original.token&&Number.isSafeInteger(p.t)&&p.t>0&&Number.isFinite(p.p)&&p.p>0&&p.p<1&&Number.isFinite(p.size)&&p.size>0&&p.tx&&(phase==='final'||p.t<capture.baselineCutoff));
 const baseline=points.filter(p=>p.t<capture.baselineCutoff).at(-1)??null;
 return {race,market,original,points,baseline,first:points[0]??null,last:points.at(-1)??null,grade:phase==='final'&&market.sourceResolved?(original.settled?'Happened':'Didn’t happen'):null,reportedWinner:phase==='final'?race.reportedWinner:null,wonAward:phase==='final'?market.reportedWinner:null,meaning:side==='Yes'?`Wins ${race.title}`:`Doesn’t win ${race.title}`};
}
export function awardSeries(id:string,phase:AwardPhase,window:AwardWindow,capture:AwardCapture=wire){
 const race=awardRace(id,capture);if(!race)return [];
 return race.markets.filter(m=>m.sides.some(s=>s.historyCaptured)).map(m=>{const d=awardReading(id,m.id,'Yes',phase,capture)!;return {...d,plotted:d.points.filter(p=>phase==='before'||window==='all'||(window==='earlier'?p.t<capture.baselineCutoff:p.t>=capture.baselineCutoff))}});
}
export function awardDomain(rows:ReadonlyArray<{plotted:ReadonlyArray<AwardPoint>}>,phase:AwardPhase):[number,number]{const times=rows.flatMap(r=>r.plotted.map(p=>p.t));const lo=times.length?Math.min(...times):wire.baselineCutoff-86400,hi=times.length?Math.max(...times):wire.baselineCutoff;return [lo,hi>lo?hi:lo+3600]}
export function awardOriginals(raceID:string,phase:AwardPhase,capture:AwardCapture=wire){const race=awardRace(raceID,capture);if(!race)return [];return race.markets.flatMap(m=>m.sides.map(s=>awardReading(raceID,m.id,s.side,phase,capture)!));}

export function awardPointAt(points:ReadonlyArray<AwardPoint>,at:number|null,picked:AwardPoint|null=null):AwardPoint|null{
 if(at===null)return points.at(-1)??null;
 if(picked&&picked.t===at){const exact=points.find(p=>p.t===picked.t&&p.p===picked.p&&p.tx===picked.tx&&p.asset===picked.asset&&p.size===picked.size&&p.action===picked.action);if(exact)return exact;}
 const same=points.filter(p=>p.t===at);return same.length&&new Set(same.map(p=>p.p)).size===1?same.at(-1)!:null;
}

/** A pre-day print cannot masquerade as a later quote in a comparative card. */
export function awardComparison(d:NonNullable<ReturnType<typeof awardReading>>,phase:AwardPhase,cutoff=wire.baselineCutoff){
 const earlier=phase==='before'?d.first:d.baseline;
 const later=phase==='before'?d.last:d.last&&d.last.t>=cutoff?d.last:null;
 return {earlier,later,earlierLabel:phase==='before'?'First retained':'Before day',laterLabel:phase==='before'?'Before day':d.last&&d.last.t<cutoff?'No later trade':'Last recorded'};
}
