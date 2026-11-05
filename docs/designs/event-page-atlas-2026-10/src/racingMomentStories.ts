import {BEFORE,FINAL,raceStage,raceDelta,racingLiveWire as wire} from './racingLifecycle.ts';
export type RaceStoryID='podium-paths'|'shifts'|'chase'|'finish';
export interface RaceStoryOrder {ids:RaceStoryID[];reasons:Partial<Record<RaceStoryID,string>>}
/** A transparent recorded-context rule, not an AI or connected production ranking claim. */
export function raceStoryOrder(stage:number,mode='captured'):RaceStoryOrder {
 if(stage===BEFORE)return {ids:['podium-paths'],reasons:{}};
 if(stage===FINAL)return {ids:['podium-paths','finish'],reasons:{}};
 const frame=raceStage(stage);if(!frame)return {ids:[],reasons:{}};
 const earlier=stage>0?raceStage(stage-1):null;
 const closed=earlier?earlier.gapSeconds-frame.gapSeconds:null;
 const biggest=wire.drivers.flatMap(d=>{const delta=raceDelta(d.key,stage,mode);return delta===null?[]:[{d,delta}]}).sort((a,b)=>Math.abs(b.delta)-Math.abs(a.delta))[0];
 const reasons:RaceStoryOrder['reasons']={};
 if(biggest)reasons.shifts=`${biggest.d.name.split(' ').at(-1)}’s win chance ${biggest.delta>=0?'rose':'fell'} ${(Math.abs(biggest.delta)*100).toFixed(1)} points from pre-race.`;
 if(earlier&&closed!==null)reasons.chase=closed>=1?`Leclerc closed ${closed.toFixed(1)} seconds since the lap ${earlier.lap} report.`:`Leclerc trails by ${frame.gapSeconds.toFixed(1)} seconds at the lap ${frame.lap} report.`;
 else reasons.chase=`Leclerc trails by ${frame.gapSeconds.toFixed(1)} seconds at the lap ${frame.lap} report.`;
 // A material change in the actual race can lead; tiny gap changes do not outrank a supported probability move.
 if(closed!==null&&closed>=1)return {ids:['chase',...(biggest?['shifts','podium-paths'] as const:['podium-paths','shifts'] as const)],reasons};
 return {ids:biggest?['shifts','podium-paths','chase']:['podium-paths','chase','shifts'],reasons};
}
export function raceStreamScope(stage:number){return `race-live-moment:${stage}`}
