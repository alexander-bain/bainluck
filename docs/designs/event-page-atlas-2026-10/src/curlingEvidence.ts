import capture from './curling-capture.json' with {type:'json'};
export const curlingCapture=capture;
export type CurlingPhase='before'|'final';
export type CurlingWindow='before'|'match';
export type CurlingPoint={t:number;p:number;volume:number};
export const curlingTeams=capture.teams;
export function curlingPoints(team:number,window:CurlingWindow):CurlingPoint[]{return curlingTeams[team].history.filter(p=>window==='before'?p.t<capture.listedStart:p.t>=capture.listedStart&&p.t<=capture.resultReportAt);}
export function curlingBaseline(team:number):CurlingPoint|null{const p=curlingPoints(team,'before').at(-1);return p&&capture.listedStart-p.t<=15*60?p:null;}
export function curlingTimes(window:CurlingWindow):number[]{return [...new Set(curlingTeams.flatMap((_,i)=>curlingPoints(i,window).map(p=>p.t)))].sort((a,b)=>a-b);}
export function curlingDefaultTime(window:CurlingWindow):number{if(window==='before')return curlingTimes(window).at(-1)!;const a=curlingPoints(0,window),b=new Set(curlingPoints(1,window).map(p=>p.t));return a.slice().reverse().find(p=>b.has(p.t))?.t??curlingTimes(window).at(-1)!;}
export function curlingExact(team:number,t:number,window:CurlingWindow){return curlingPoints(team,window).find(p=>p.t===t)??null;}
/** Plot each independent contract on its own observations. Breaks are display policy, never freshness. */
export function curlingPlot(team:number,window:CurlingWindow){const points=curlingPoints(team,window),gap=window==='before'?15*60:5*60;return points.flatMap((p,i)=>i&&p.t-points[i-1].t>gap?[{t:points[i-1].t+1,p:null},p]:[p]);}
export function curlingFacts(phase:CurlingPhase){return {scores:phase==='final'?curlingTeams.map(t=>t.scores.reduce((a,b)=>a+b,0)):null,ends:phase==='final'?10:null,winner:phase==='final'?'Sweden':null,firstEndLastStone:capture.firstEndLastStone};}
export const curlingScorePath=Array.from({length:11},(_,i)=>({end:i,sweden:curlingTeams[0].scores.slice(0,i).reduce((a,b)=>a+b,0),switzerland:curlingTeams[1].scores.slice(0,i).reduce((a,b)=>a+b,0)}));

export function curlingDomain(window:CurlingWindow,zoom:boolean):[number,number]{if(!zoom)return [0,1];const values=curlingTeams.flatMap((_,i)=>curlingPoints(i,window).map(p=>p.p));return [Math.max(0,Math.floor((Math.min(...values)-.05)*20)/20),Math.min(1,Math.ceil((Math.max(...values)+.05)*20)/20)];}

export function curlingDisplay(team:number,at:number,window:CurlingWindow,inspecting:boolean){return window==='before'&&!inspecting?curlingBaseline(team):curlingExact(team,at,window);}
