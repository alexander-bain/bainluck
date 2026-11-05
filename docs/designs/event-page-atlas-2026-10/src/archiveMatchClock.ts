import {createEventReaderTime,eventReaderTime} from './eventReaderTime.ts';
/** Candle timestamps are seconds. Keep this conversion separate from millisecond chart clocks. */
export function createArchiveMatchClock(timeZone=eventReaderTime.timeZone){
 const reader=createEventReaderTime(timeZone);
 const instant=(seconds:unknown)=>typeof seconds==='number'&&Number.isFinite(seconds)?seconds*1000:null;
 return {timeZone,short:(seconds:unknown)=>reader.short(instant(seconds)),full:(seconds:unknown)=>reader.full(instant(seconds)),date:(seconds:unknown)=>reader.date(instant(seconds)),range:(first:unknown,last:unknown)=>reader.range(instant(first),instant(last))};
}
export const archiveMatchClock=createArchiveMatchClock();
