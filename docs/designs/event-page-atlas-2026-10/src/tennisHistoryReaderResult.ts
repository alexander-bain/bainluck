type Event={unit:string;detail:{id:number;status:string;home_team:string;away_team:string;home_score:number|null;away_score:number|null}};
/** Actual set result from this captured event, never a history/projection value. */
export function tennisHistoryReaderResult(event:Event){
 const d=event.detail,h=d.home_score,a=d.away_score;
 if(event.unit!=='sets'||d.id!==15310688||d.status!=='completed'||d.home_team!=='Alexander Zverev'||d.away_team!=='Ben Shelton'||h===null||a===null||!Number.isInteger(h)||!Number.isInteger(a)||h<0||a<0||h>3||a>3||Math.max(h,a)!==3||h===a)return null;
 return {home:h,away:a,unit:'sets' as const,label:`Final · ${h}–${a} sets`};
}
