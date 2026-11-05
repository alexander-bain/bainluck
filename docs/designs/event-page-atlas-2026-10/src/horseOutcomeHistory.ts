import capture from './horseOutcomeCapture.json' with {type:'json'};
import timing from './horseRacingTiming.json' with {type:'json'};
import {type RacePhase} from './horseRacingPhase.ts';
import {probabilityLabel} from './probabilityLabel.ts';
export const horseOutcomes=capture;
export type HorseOutcomeTrade=(typeof capture.markets)[number]['sides'][number]['trades'][number];
export function horseOutcomeHistory(id:string,side:string,phase:RacePhase,selected:number|null=null){
 const market=capture.markets.find(m=>m.id===id),original=market?.sides.find(s=>s.side===side);
 if(!market||!original||(side!=='Yes'&&side!=='No'))return null;
 const points=original.trades.filter(t=>phase==='final'||t.t<timing.scheduledStart);
 const baseline=original.trades.filter(t=>t.t<timing.scheduledStart).at(-1)??null;
 const index=points.length?Math.max(0,Math.min(points.length-1,selected??points.length-1)):0;
 const start=phase==='before'?(points[0]??null):baseline,end=points.at(-1)??null,single=start!==null&&start===end;
 const meaning=market.name==='Other'?(side==='Yes'?'Another horse wins · special rules apply':'Another horse does not win · special rules apply'):(side==='Yes'?'Wins the race':'Doesn’t win the race');
 return {market,side,token:original.token,condition:market.condition,meaning,points,index,point:points[index]??null,baseline,baselineIndex:baseline?points.indexOf(baseline):-1,start,end,single,
  move:start&&end&&!single?end.p-start.p:null,startLabel:phase==='before'?'First captured trade':'Before scheduled start',endLabel:phase==='before'?(single?'Before scheduled start · only trade':'Before scheduled start'):(single?'Before scheduled start · last trade':'Last recorded trade'),
  grade:phase==='final'&&market.resolved?(original.settled?'Happened':'Didn’t happen'):null,place:phase==='final'?market.place:null};
}
export function horseOutcomeDomain(points:ReadonlyArray<{t:number}>,phase:RacePhase):[number,number]{
 const first=Math.min(timing.scheduledStart,...points.map(p=>p.t));
 return [first===timing.scheduledStart?first-3600000:first,phase==='before'?timing.scheduledStart:Math.max(timing.scheduledStart,...points.map(p=>p.t))];
}
export function horseOutcomeScale(points:ReadonlyArray<{p:number}>,full=false){
 if(full)return 1;const max=Math.max(0,...points.map(p=>p.p));return [.01,.02,.05,.1,.2,.25,.5,.75,1].find(n=>n>=max)??1;
}
export function horseOutcomeMove(move:number|null){
 if(move===null)return 'Comparison unavailable';if(move===0)return 'Same recorded chance at both times';
 return probabilityLabel(Math.abs(move)).replace('%','')+' points '+(move>0?'higher':'lower');
}
