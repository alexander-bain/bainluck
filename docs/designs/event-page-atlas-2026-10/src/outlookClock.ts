import {readerTime} from './readerTime.ts';
/** A single session timezone serves every outlook date; null must never become the Unix epoch. */
export function outlookTime(source:string|number|null|undefined,timeZone:string,dateOnly=false){
 if(source===null||source===undefined||source==='')return 'Time unavailable';
 return readerTime(source,{timeZone,dateOnly});
}
export function outlookCaptureLabel(source:string|null|undefined,timeZone:string){
 const label=outlookTime(source,timeZone,true);
 return label==='Time unavailable'?'Capture time unavailable':`Captured ${label}`;
}
