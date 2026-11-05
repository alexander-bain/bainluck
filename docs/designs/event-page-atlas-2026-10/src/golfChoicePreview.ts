import {journeyNames,journeySegments,tournamentTimeline,windowPoints,type JourneyWindow} from './golfJourneyEvidence.ts';
import {golfChoice} from './golfChoiceEvidence.ts';

// A picker is a comparison surface: every preview uses one zero-based scale and clock.
// Include the baseline in the extent so the pre-event rule can never fall outside the plot.
export function golfChoiceFrame(period:JourneyWindow,through?:string){
 const values=journeyNames.flatMap(name=>{
  const row=golfChoice(name,period,through);
  return [...windowPoints(name,period,through).map(p=>p.probability),...(row?.baseline?[row.baseline.probability]:[])];
 });
 const peak=Math.max(0,...values),ceiling=[0.025,0.05,0.1,0.15,0.2,0.25,0.4,0.6,0.8,1].find(v=>v>=peak*1.04)??1;
 return {ceiling,timeline:tournamentTimeline(period,through)};
}
export function golfChoicePreview(name:string,period:JourneyWindow,frame:ReturnType<typeof golfChoiceFrame>,through?:string){
 const row=golfChoice(name,period,through),points=windowPoints(name,period,through);
 const x=(timestamp:string)=>frame.timeline.fraction(Date.parse(timestamp));
 const y=(probability:number)=>1-probability/frame.ceiling;
 return {
  segments:journeySegments(points).map(segment=>segment.map(p=>({...p,x:x(p.timestamp),y:y(p.probability)}))),
  baselineY:row?.baseline?y(row.baseline.probability):null,
  last:points.length?{...points.at(-1)!,x:x(points.at(-1)!.timestamp),y:y(points.at(-1)!.probability)}:null,
  gaps:frame.timeline.gaps.map(g=>({from:frame.timeline.fraction(g.start),to:frame.timeline.fraction(g.end)})),
 };
}
