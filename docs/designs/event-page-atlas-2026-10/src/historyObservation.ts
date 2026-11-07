/** Exact captured observation identity. Production adapters should supply provider/aggregate revision IDs. */
export type HistoryObservation={t:number;at:string;home:number;away:number;pregame:boolean;draw?:number;books?:number};
export type RetainedHistorySelection={eventKey:string;point:HistoryObservation};
export function sameHistoryObservation(a:HistoryObservation,b:HistoryObservation){
 return a.t===b.t&&a.at===b.at&&a.home===b.home&&a.away===b.away&&a.pregame===b.pregame&&a.draw===b.draw&&a.books===b.books;
}
export function retainHistoryObservation(eventKey:string,point:HistoryObservation):RetainedHistorySelection{
 return {eventKey,point:{t:point.t,at:point.at,home:point.home,away:point.away,pregame:point.pregame,...(point.draw!==undefined?{draw:point.draw}:{}),...(point.books!==undefined?{books:point.books}:{})}};
}
/** Opening a reader preserves the displayed default as deliberately read history.
 * An unavailable prior observation remains unavailable; entry never replaces it. */
export function pinHistorySelection<T extends HistoryObservation>(eventKey:string,points:T[],selection:RetainedHistorySelection|null):RetainedHistorySelection|null{
 if(selection)return selection;
 const point=points.at(-1);
 return point?retainHistoryObservation(eventKey,point):null;
}
export function resolveHistorySelection<T extends HistoryObservation>(eventKey:string,points:T[],selection:RetainedHistorySelection|null):{point:T|undefined;index:number;unavailable:boolean}{
 if(!selection)return {point:points.at(-1),index:points.length-1,unavailable:false};
 if(selection.eventKey!==eventKey)return {point:undefined,index:-1,unavailable:true};
 const matches=points.map((p,index)=>({p,index})).filter(({p})=>p.t===selection.point.t);
 if(matches.length===1&&!sameHistoryObservation(matches[0].p,selection.point))return {point:undefined,index:-1,unavailable:true};
 if(matches.length!==1)return {point:undefined,index:-1,unavailable:true};
 return {point:matches[0].p,index:matches[0].index,unavailable:false};
}
