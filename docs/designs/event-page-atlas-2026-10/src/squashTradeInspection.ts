import {squashClock, squashTickers, type SquashPoint} from './squashMatchEvidence.ts';
export const squashAnchorPlot={left:44,width:280,bottom:243,height:225};
export function squashPlotForSize(width:number,height:number){return {left:44,width:Math.max(1,width-56),bottom:height-57,height:Math.max(1,height-75)}}
type Plot={left:number;width:number;bottom:number;height:number};
type Series={ticker:string;points:SquashPoint[]};
// Use plot coordinates, not elapsed-time interpolation: compressed gaps are not observations.
export function squashTradeHit(series:Series[], point:{x:number;y:number}, radius:number, plot:Plot={left:44,width:280,bottom:228,height:196}, scale={x:1,y:1}):number|null {
 if(!Number.isFinite(scale.x)||!Number.isFinite(scale.y)||scale.x<=0||scale.y<=0)return null;
 if(Object.values(plot).some(v=>!Number.isFinite(v))||plot.width<=0||plot.height<=0)return null;
 if(!Number.isFinite(point.x)||!Number.isFinite(point.y)||!Number.isFinite(radius)||radius<=0)return null;
 if(series.length!==2||squashTickers.some(t=>series.filter(s=>s.ticker===t).length!==1))return null;
 const points=series.flatMap(s=>s.points);
 if(points.some(p=>!Number.isSafeInteger(p.at)||p.at%60!==0||!Number.isFinite(p.p)||p.p<0||p.p>1||!Number.isFinite(p.volume)||p.volume<=0))return null;
 if(series.some(s=>new Set(s.points.map(p=>p.at)).size!==s.points.length))return null;
 const axis=squashClock([...new Set(points.map(p=>p.at))].sort((a,b)=>a-b));
 const candidates=points.map(p=>({at:p.at,distance:Math.hypot((plot.left+axis.fraction(p.at)*plot.width-point.x)*scale.x,(plot.bottom-plot.height*p.p-point.y)*scale.y)})).filter(p=>p.distance<=radius).sort((a,b)=>a.distance-b.distance||a.at-b.at);
 return candidates[0]?.at??null;
}
