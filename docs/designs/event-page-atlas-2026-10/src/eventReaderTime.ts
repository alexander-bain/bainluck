import {deviceTimeZone,readerClock,readerDay,readerTime} from './readerTime.ts';
/** One timezone per loaded reader; formatting never changes source clocks or cutoffs. */
export function createEventReaderTime(timeZone=deviceTimeZone()) {
 const valid=(value:unknown):value is string|number=>(typeof value==='string'&&value.trim()!==''||typeof value==='number'&&Number.isFinite(value))&&Number.isFinite(new Date(value as string|number).getTime());
 const full=(value:unknown,seconds=false)=>valid(value)?readerTime(value,{timeZone,seconds}):'Time unavailable';
 const short=(value:unknown)=>valid(value)?readerClock(value,{timeZone}):'Time unavailable';
 const date=(value:unknown)=>valid(value)?readerTime(value,{timeZone,dateOnly:true}):'Date unavailable';
 const range=(first:unknown,last:unknown)=>!valid(first)||!valid(last)?'Dates unavailable':readerDay(first,timeZone)===readerDay(last,timeZone)?date(first):`${date(first)} – ${date(last)}`;
 return {timeZone,full,short,date,range};
}
export const eventReaderTime=createEventReaderTime();
