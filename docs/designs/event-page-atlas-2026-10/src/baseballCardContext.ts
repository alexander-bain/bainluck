import {createEventReaderTime,eventReaderTime} from './eventReaderTime.ts';
/** Presentation of retained observations only; this does not establish live freshness. */
export function baseballQuoteReading(input:{baseline:unknown;recorded:unknown;at:unknown;mode:string},clock:ReturnType<typeof createEventReaderTime>=eventReaderTime){
 const chance=(v:unknown):v is number=>typeof v==='number'&&Number.isFinite(v)&&v>=0&&v<=1;
 const validClock=typeof input.at==='string'&&input.at.trim()!==''&&Number.isFinite(Date.parse(input.at));
 const baseline=chance(input.baseline)?input.baseline:null;
 const archived=chance(input.recorded)&&validClock?input.recorded:null;
 const recorded=input.mode==='captured'?archived:null;
 return {baseline,recorded,archived,at:validClock?input.at as string:null,clock:validClock?clock.full(input.at):'Time unavailable',missing:input.mode==='loading'?'Loading…':input.mode==='captured'?'Not captured':'No recent price',change:baseline!==null&&recorded!==null?Math.round((recorded-baseline)*10000)/100:null};
}
export function baseballMilestoneResult(actual:unknown,milestone:number){
 if(typeof actual!=='number'||!Number.isInteger(actual)||actual<0||!Number.isInteger(milestone)||milestone<0)return 'Final result unavailable';
 const difference=actual-milestone;
 return difference===0?'Reached the milestone':difference>0?`Finished ${difference} above`:`Finished ${-difference} short`;
}

export const baseballStoryFamilies=[{id:'strikeouts',name:'Strikeout expectations'},{id:'extra',name:'Extra innings'},{id:'home-runs',name:'Home-run surprises'},{id:'totals',name:'Run totals'},{id:'series',name:'Associated series'}] as const;

/** Zero-based shared scale for a low-probability two-time comparison. */
export function baseballChanceCeiling(values:unknown[]){
 const valid=values.filter((v):v is number=>typeof v==='number'&&Number.isFinite(v)&&v>=0&&v<=1);
 return Math.max(.25,Math.ceil(Math.max(0,...valid)*4)/4);
}
