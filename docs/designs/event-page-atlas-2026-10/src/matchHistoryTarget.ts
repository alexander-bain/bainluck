type Point={at:number;p:number;volume:number};
type Series={ticker:string;points:Point[]};
/** Navigate only to an exact admitted point in this phase's full history. */
export function matchHistoryTarget(series:Series[],ticker:string,at:number|null|undefined){
 if(at==null||!Number.isFinite(at))return null;
 const rows=series.filter(s=>s.ticker===ticker);
 if(rows.length!==1)return null;
 const points=rows[0].points.filter(p=>p.at===at);
 const p=points[0];
 return points.length===1&&Number.isFinite(p.p)&&p.p>=0&&p.p<=1&&Number.isFinite(p.volume)&&p.volume>0?at:null;
}

export function matchHistoryFrame(all:Series[],nearMatch:Series[],ticker:string,at:number|null|undefined){
 const target=matchHistoryTarget(all,ticker,at);
 if(target===null)return null;
 return {at:target,window:matchHistoryTarget(nearMatch,ticker,target)!==null?'match' as const:'all' as const};
}
