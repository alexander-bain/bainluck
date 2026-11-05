import {chessGapMs,type ChessContender,type ChessPoint} from './chessHistory.ts';
/** Full archived window, explicitly independent of the inspected chart moment. */
export function chessChoiceFrame(all:ChessContender[]){
 const points=all.flatMap(c=>c.history).filter(p=>Number.isFinite(Date.parse(p.timestamp))&&Number.isFinite(p.probability)&&p.probability>=0&&p.probability<=1);
 if(!points.length)return null;
 const from=Math.min(...points.map(p=>Date.parse(p.timestamp))),through=Math.max(...points.map(p=>Date.parse(p.timestamp)));
 return {from,through,ceiling:Math.max(.1,Math.ceil((Math.max(...points.map(p=>p.probability))-1e-12)*10)/10)};
}
export function chessChoicePreview(contender:ChessContender,frame:NonNullable<ReturnType<typeof chessChoiceFrame>>){
 const times=new Map<number,ChessPoint[]>();
 for(const p of contender.history){const time=Date.parse(p.timestamp);if(!Number.isFinite(time))continue;times.set(time,[...(times.get(time)??[]),p])}
 const segments:Array<Array<ChessPoint&{x:number;y:number}>>=[];
 let interrupted=true;
 for(const [time,rows] of [...times].sort((a,b)=>a[0]-b[0])){
  const p=rows[0];
  if(time<frame.from||time>frame.through||rows.length!==1||!Number.isFinite(p.probability)||p.probability<0||p.probability>frame.ceiling){interrupted=true;continue}
  const point={...p,x:frame.through===frame.from?0.5:(time-frame.from)/(frame.through-frame.from),y:1-p.probability/frame.ceiling};
  const previous=segments.at(-1)?.at(-1);
  if(!interrupted&&previous&&time-Date.parse(previous.timestamp)<=chessGapMs)segments.at(-1)!.push(point);else segments.push([point]);
  interrupted=false;
 }
 return {segments,last:segments.at(-1)?.at(-1)??null,count:segments.reduce((n,s)=>n+s.length,0)};
}
