import capture from './soccerFinal.json' with {type:'json'};
export type FinalSoccerRow=typeof capture.rows[number];
export type SoccerWindow='match'|'before';
export const soccerFinal=capture;
export const soccerFinalChance=(value:number|null|undefined)=>value==null?'Unavailable':`${(value*100).toLocaleString('en-US',{maximumFractionDigits:2})}%`;
export const soccerResultLabel=(state:string)=>state==='won'?'Won':state==='lost'?'Lost':'Result unconfirmed';
export function finalSoccerPoints(window:SoccerWindow){const start=Date.parse(capture.start);return capture.points.filter(p=>window==='before'?Date.parse(p.at)<start:Date.parse(p.at)>=Date.parse(capture.baseline.at))}
export function finalSoccerPlot(window:SoccerWindow){const points=finalSoccerPoints(window),gap=window==='before'?2*60*60*1000:5*60*1000;return points.flatMap((p,i)=>{const value={time:Date.parse(p.at),chance:p.value*100};return i&&Date.parse(p.at)-Date.parse(points[i-1].at)>gap?[{time:(Date.parse(p.at)+Date.parse(points[i-1].at))/2,chance:null},value]:[value]})}
export function finalSoccerRow(mid:number,label?:string){const rows=capture.rows.filter(r=>r.marketID===mid&&(!label||r.label===label));if(rows.length!==1)throw new Error('Exact original soccer outcome required');return rows[0]}
export const finalSoccerGoals=[3,5,6].map((n,i)=>({goals:n,row:finalSoccerRow(capture.bindings.totals[i],'Over')}));
export function finalSoccerInspect(window:SoccerWindow,index:number){const points=finalSoccerPoints(window);if(!Number.isInteger(index)||index<0||index>=points.length)throw new Error('Unknown historical observation');return points[index]}
