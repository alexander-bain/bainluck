import {deviceTimeZone,readerTime} from './readerTime.ts';
/** One reader timezone for racing headline, history, props and source explanations. */
export const racingTimeZone=deviceTimeZone();
export function racingReaderTime(at:string|number|null|undefined,timeZone=racingTimeZone){
 if(at===null||at===undefined||at==='')return 'Time unavailable';
 return readerTime(at,{timeZone});
}
/** Include dates: the captured pre-race history spans a full day. */
export const racingAxisClock=(at:number,timeZone=racingTimeZone)=>racingReaderTime(at,timeZone);
