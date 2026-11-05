import capture from './racingLifecycleCapture.json' with {type:'json'};
import original from './racingEvidence.json' with {type:'json'};
import {racingLiveWire as wire,raceTrades,raceSegments,raceBaseline,raceStage as liveStage} from './racingLiveEvidence.ts';
export {racingLiveWire,raceBaseline,raceClock,raceOriginals} from './racingLiveEvidence.ts';
export const BEFORE=-1,FINAL=3;
export function raceStage(stage:number){
 if(stage===BEFORE)return {lap:0,reportedAt:new Date(Date.parse(wire.start)-1).toISOString(),gapSeconds:0};
 if(stage===FINAL)return {lap:62,reportedAt:capture.lastLapReport.publishedAt,gapSeconds:0};
 return liveStage(stage);
}
export function raceDomain(stage:number):[number,number]{const f=raceStage(stage);return f?[stage===BEFORE?Date.parse(wire.start)-7200000:Date.parse(wire.start),Date.parse(f.reportedAt)]:[0,0];}
export function raceHistory(key:string,stage:number){
 const f=raceStage(stage),d=wire.drivers.find(d=>d.key===key);if(!f||!d)return [];
 if(stage===BEFORE){const [lo,hi]=raceDomain(stage);return (original.rows.find(r=>r.key===key)?.history??[]).filter(p=>Number.isFinite(p.value)&&p.value>=0&&p.value<=1&&p.t*1000>=lo&&p.t*1000<=hi).map(p=>({t:p.t*1000,value:p.value}));}
 return raceTrades(d.trades,d.tokenID,d.conditionID,Date.parse(wire.start),Date.parse(f.reportedAt));
}
export function raceQuote(key:string,stage:number,mode='captured'){
 if(stage===FINAL||mode!=='captured')return null;
 const f=raceStage(stage);if(!f)return null;const q=raceHistory(key,stage).at(-1);return q&&Date.parse(f.reportedAt)-q.t<=300000?q:null;
}
export function racePlot(key:string,stage:number){return raceSegments(raceHistory(key,stage)).flatMap((g,i)=>i?[{t:g[0].t-1,value:null},...g]:g);}
export function raceTimes(stage:number){return [...new Set(wire.drivers.flatMap(d=>raceHistory(d.key,stage).map(p=>p.t)))].sort((a,b)=>a-b);}
export function raceDelta(key:string,stage:number,mode='captured'){const q=raceQuote(key,stage,mode),b=raceBaseline(key);return q&&b?q.value-b.value:null;}
export function raceFinish(key:string,stage:number){if(stage!==FINAL)return null;const r=original.rows.find(r=>r.key===key);return r?{position:r.position,result:r.result,capturedAt:original.actualCapturedAt}:null;}
export const raceFinalSource={capturedAt:original.actualCapturedAt,providerEventID:original.providerEventID,lastLapReport:capture.lastLapReport.publishedAt};
