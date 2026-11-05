import raw from './volleyball-capture.json' with {type:'json'};
export type VolleyballPoint={at:number;probability:number;volume:number};
export type VolleyballTeam={id:string;name:string;predicate:string;rules:string;history:VolleyballPoint[];sourceRecord:Record<string,unknown>};
export const volleyballCapture=raw;
export const volleyballTeams=raw.teams as VolleyballTeam[];
export const volleyballFeatured=raw.featured.map(id=>volleyballTeams.find(t=>t.id===id)!);
export const volleyballHours=Array.from({length:(raw.through-raw.from)/3600000+1},(_,i)=>raw.from+i*3600000);
export const volleyballCeiling=Math.max(.1,Math.ceil((Math.max(...volleyballFeatured.flatMap(t=>t.history.map(p=>p.probability)))-1e-12)*10)/10);
export function volleyballAt(team:VolleyballTeam,at:number){const rows=team.history.filter(p=>p.at===at);return rows.length===1&&Number.isFinite(rows[0].probability)&&rows[0].probability>=0&&rows[0].probability<=1&&rows[0].volume>0?rows[0]:null}
export function volleyballLatest(team:VolleyballTeam){return [...team.history].sort((a,b)=>b.at-a.at).find(p=>volleyballAt(team,p.at))??null}
export function volleyballPlot(team:VolleyballTeam){return volleyballHours.map(at=>({at,chance:volleyballAt(team,at)?.probability??null}))}
export function qualifyVolleyballCandles(rows:Array<{end_period_ts:number;volume_fp?:string;price?:{close_dollars?:string|null;previous_dollars?:string|null}}>){
 return rows.flatMap(c=>{const probability=c.price?.close_dollars==null?NaN:Number(c.price.close_dollars),volume=Number(c.volume_fp);return Number.isFinite(c.end_period_ts)&&Number.isFinite(probability)&&probability>=0&&probability<=1&&Number.isFinite(volume)&&volume>0?[{at:c.end_period_ts*1000,probability,volume}]:[]});
}

// Navigate actual traded hours without carrying one team's quote into another hour.
export function volleyballTradeHour(direction:'earlier'|'later',at:number|null,source:VolleyballTeam[]=volleyballFeatured):number|null {
 const times=[...new Set(source.flatMap(t=>t.history.filter(p=>volleyballAt(t,p.at)!==null).map(p=>p.at)))].sort((a,b)=>a-b);
 if(at===null)return direction==='earlier'?times.at(-1)??null:null;
 return direction==='earlier'?[...times].reverse().find(time=>time<at)??null:times.find(time=>time>at)??null;
}
