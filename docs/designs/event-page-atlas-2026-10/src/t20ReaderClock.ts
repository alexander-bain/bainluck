import {readerTime} from './readerTime.ts';
import {t20Wire} from './t20Evidence.ts';

/** One captured timezone applies to the chart, inspection, and source sheet. */
export function t20ReaderClock(timeZone:string){
 const instant=(value:string|number|null|undefined)=>value==null?NaN:new Date(value).getTime();
 return {
  label(value:string|number|null|undefined){const at=instant(value);return Number.isFinite(at)?readerTime(at,{timeZone}):'Time unavailable'},
  tick(value:number){const at=instant(value);return Number.isFinite(at)?new Intl.DateTimeFormat('en-US',{timeZone,hour:'numeric',minute:'2-digit'}).format(at):'Time unavailable'},
 };
}
export type T20ReaderClock=ReturnType<typeof t20ReaderClock>;
/** Original report disclosure respects the same reconstruction cutoff as the page. */
export function t20ReportClocks(stage:number){
 const rows=[{label:'Pre-match report',timestamp:t20Wire.pregame.reportedAt}];
 if(stage>=0&&stage<=4){
  rows.push({label:'First innings report',timestamp:t20Wire.firstInnings.report.reportedAt});
  t20Wire.stages.slice(0,stage===4?4:stage+1).forEach(s=>rows.push({label:`${s.overs} overs report`,timestamp:s.report.reportedAt}));
 }
 if(stage===4)rows.push({label:'Final report',timestamp:t20Wire.final.report.reportedAt});
 return rows;
}
