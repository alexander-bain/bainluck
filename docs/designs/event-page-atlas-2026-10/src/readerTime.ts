/** Display in the device timezone; exact source timestamps remain in details. */
export function readerTime(value:string|number,options:{dateOnly?:boolean;timeZone?:string;seconds?:boolean}={}){
 const date=new Date(value);
 if(!Number.isFinite(date.getTime()))return 'Time unavailable';
 return new Intl.DateTimeFormat('en-US',{month:'short',day:'numeric',...(options.dateOnly?{}:{hour:'numeric',minute:'2-digit',hour12:true,...(options.seconds?{second:'2-digit'}:{})}),...(options.timeZone?{timeZone:options.timeZone}:{})}).format(date);
}

export const deviceTimeZone=()=>Intl.DateTimeFormat().resolvedOptions().timeZone;
const dayFormatters=new Map<string,Intl.DateTimeFormat>();
/** A calendar key is not an instant; use parts so locale ordering cannot alter identity. */
export function readerDay(value:string|number,timeZone:string){
 const date=new Date(value);if(!Number.isFinite(date.getTime()))return null;
 let formatter=dayFormatters.get(timeZone);
 if(!formatter){formatter=new Intl.DateTimeFormat('en-US',{timeZone,year:'numeric',month:'2-digit',day:'2-digit'});if(dayFormatters.size>=32)dayFormatters.clear();dayFormatters.set(timeZone,formatter);}
 const parts=formatter.formatToParts(date);
 const part=(type:string)=>parts.find(p=>p.type===type)!.value;
 return `${part('year')}-${part('month')}-${part('day')}`;
}
export function readerDateLabel(day:string){
 if(!/^\d{4}-\d{2}-\d{2}$/.test(day))return 'Date unavailable';
 const instant=new Date(day+'T12:00:00Z');
 if(!Number.isFinite(instant.getTime())||instant.toISOString().slice(0,10)!==day)return 'Date unavailable';
 // Format the date identity without applying a second timezone conversion.
 return readerTime(day+'T12:00:00Z',{timeZone:'UTC',dateOnly:true});
}

/** Compact chart clock in the same device zone as readerTime. Date labels are separate. */
export function readerClock(value:string|number,options:{timeZone?:string;seconds?:boolean}={}){
 const date=new Date(value);if(!Number.isFinite(date.getTime()))return 'Time unavailable';
 return new Intl.DateTimeFormat('en-US',{hour:'numeric',minute:'2-digit',hour12:true,...(options.seconds?{second:'2-digit'}:{}),...(options.timeZone?{timeZone:options.timeZone}:{})}).format(date);
}
/** A short match can still straddle midnight in the reader's timezone. */
export function readerCrossesDay(points:readonly {t:number}[],timeZone=deviceTimeZone()){
 const days=points.map(p=>readerDay(p.t,timeZone)).filter(d=>d!==null);
 return new Set(days).size>1;
}
