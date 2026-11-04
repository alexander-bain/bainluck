import {journeyWire,journeyNames,journeyWindows,featuredGolfers,chartCeiling,windowPoints,type JourneyWindow} from './golfJourneyEvidence.ts';
import type {GolfInspection} from './golfInspection.ts';
export const golfArrivalTimes=[...new Set(journeyWire.history.outcomes.flatMap(r=>r.history.filter(p=>Number.isFinite(p.probability)&&p.probability>=0&&p.probability<=1&&Date.parse(p.timestamp)>=Date.parse(journeyWire.start)&&Date.parse(p.timestamp)<=Date.parse(journeyWire.terminalObservation.timestamp)).map(p=>p.timestamp)))].sort((a,b)=>Date.parse(a)-Date.parse(b));
export function roundAt(at:string):JourneyWindow {return [...journeyWire.history.round_boundaries].reverse().find(b=>Date.parse(b.timestamp)<=Date.parse(at))?.label as JourneyWindow ?? 'R1'}
export type GolfReadingState={received:number;displayed:number;held:boolean;pinned:string|null;period:JourneyWindow;full:boolean;inspection:GolfInspection;autoScale:{period:JourneyWindow;cap:number}};
export function initialGolfReading():GolfReadingState {
 const start=Date.parse(golfArrivalTimes[0]),index=Math.max(0,golfArrivalTimes.reduce((index,t,i)=>Date.parse(t)<=start+2*60*60*1000?i:index,0));
 const period=roundAt(golfArrivalTimes[index]),names=featuredGolfers(period,null,golfArrivalTimes[index]);
 return {received:index,displayed:index,held:false,pinned:null,period,full:false,inspection:null,autoScale:{period,cap:chartCeiling(names,period,false,golfArrivalTimes[index])}};
}
// Preserve the meaning of vertical movement as the suggested cohort changes.
// Only the frame actually displayed contributes; queued observations never set scale.
function displayedScale(previous:GolfReadingState,next:GolfReadingState,refit=false):GolfReadingState {
 const through=golfArrivalTimes[next.displayed],names=featuredGolfers(next.period,next.pinned,through);
 const required=chartCeiling(names,next.period,false,through);
 const retained=!refit&&previous.autoScale.period===next.period?previous.autoScale.cap:0;
 return {...next,autoScale:{period:next.period,cap:Math.max(required,retained)}};
}
export type GolfReadingAction={type:'arrive';count?:number}|{type:'hold'}|{type:'resume'}|{type:'golfer';name:string}|{type:'period';period:JourneyWindow}|{type:'scale'}|{type:'inspect';inspection:GolfInspection};
export function golfReadingReducer(s:GolfReadingState,a:GolfReadingAction):GolfReadingState {
 if(a.type==='hold')return s.held?s:{...s,held:true};
 if(a.type==='arrive'){
  const count=a.count??1;if(!Number.isInteger(count)||count<1)return s;
  const received=Math.min(golfArrivalTimes.length-1,s.received+count);if(received===s.received)return s;
  return s.held?{...s,received}:displayedScale(s,{...s,received,displayed:received,period:s.period==='All'?'All':roundAt(golfArrivalTimes[received])});
 }
 if(a.type==='resume')return displayedScale(s,{...s,displayed:s.received,held:false,inspection:null,period:s.period==='All'?'All':roundAt(golfArrivalTimes[s.received])});
 if(a.type==='golfer')return journeyNames.includes(a.name)?displayedScale(s,{...s,pinned:a.name,held:true},true):s;
 if(a.type==='period')return availableGolfPeriods(s).includes(a.period)?displayedScale(s,{...s,period:a.period,held:true,inspection:null},true):s;
 if(a.type==='scale')return {...s,full:!s.full,held:true};
 if(a.type==='inspect'){
  const next=a.inspection;
  if(next?.kind==='point'&&!golfReadingFrame(s).series.some(series=>series.points.some(p=>p.timestamp===next.at)))return s;
  return {...s,inspection:a.inspection,held:true};
 }
 return s;
}
export function golfReadingFrame(s:GolfReadingState){
 const through=golfArrivalTimes[s.displayed],names=featuredGolfers(s.period,s.pinned,through),selected=s.pinned??names[0];
 return {through,names,selected,period:s.period,cap:s.full?1:Math.max(s.autoScale.period===s.period?s.autoScale.cap:0,chartCeiling(names,s.period,false,through)),series:names.map(name=>({name,points:windowPoints(name,s.period,through)})),inspection:s.inspection};
}

export function availableGolfPeriods(s:GolfReadingState){const round=roundAt(golfArrivalTimes[s.displayed]);return journeyWindows.filter(p=>p==='Pre'||p==='All'||Number(p.slice(1))<=Number(round.slice(1)))}

export function golfReadingStatus(s:GolfReadingState){return s.held?'Updates paused':s.displayed===golfArrivalTimes.length-1?'End of captured history':'Following recorded updates'}
