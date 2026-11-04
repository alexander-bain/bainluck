import {raceHistory,raceStage,racingLiveWire as wire} from './racingLifecycle.ts';
import type {RacePoint} from './racingLiveEvidence.ts';
export type RaceHistories=Record<string,RacePoint[]>;
export type RaceInspection={event:'singapore:2026-10-11';stage:number;at:number;values:Record<string,number|null>};
export const raceInspectionHistories=(stage:number):RaceHistories=>Object.fromEntries(wire.drivers.map(d=>[d.key,raceHistory(d.key,stage)]));
const valid=(p:RacePoint)=>Number.isFinite(p.t)&&Number.isFinite(p.value)&&p.value>=0&&p.value<=1;
const exact=(points:RacePoint[],at:number)=>{const matches=points.filter(p=>p.t===at);return matches.length===1&&valid(matches[0])?matches[0]:null};
/** Retain original supplied values at one second; absent opponents stay absent. */
export function captureRaceInspection(stage:number,at:number,histories=raceInspectionHistories(stage)):RaceInspection|null{
 if(!raceStage(stage)||!Number.isFinite(at)||!wire.drivers.some(d=>exact(histories[d.key]??[],at)))return null;
 return {event:'singapore:2026-10-11',stage,at,values:Object.fromEntries(wire.drivers.map(d=>[d.key,exact(histories[d.key]??[],at)?.value??null]))};
}
export function resolveRaceInspection(stage:number,driver:string,inspection:RaceInspection|null,histories=raceInspectionHistories(stage)){
 if(!raceStage(stage))return {point:null,unavailable:inspection!==null};
 const known=wire.drivers.some(d=>d.key===driver),points=known?(histories[driver]??[]):[];
 if(!inspection){const last=points.at(-1);return {point:last?exact(points,last.t):null,unavailable:false};}
 if(inspection.event!=='singapore:2026-10-11'||inspection.stage!==stage||!known)return {point:null,unavailable:true};
 const point=exact(points,inspection.at),value=inspection.values[driver];
 return point&&value!==null&&value!==undefined&&point.value===value?{point,unavailable:false}:{point:null,unavailable:true};
}
export function pinRaceInspection(stage:number,driver:string,inspection:RaceInspection|null,histories=raceInspectionHistories(stage)){
 if(inspection)return inspection;
 const point=resolveRaceInspection(stage,driver,null,histories).point;
 return point?captureRaceInspection(stage,point.t,histories):null;
}
