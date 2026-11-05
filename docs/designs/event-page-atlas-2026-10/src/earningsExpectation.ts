/** Latest dated observation strictly before the actual report, never an untimed opening or settlement. */
export function preReportObservation(points:readonly {t:number;value:number}[],publishedAt:number){
 if(!Number.isFinite(publishedAt))return null;
 return points.filter(p=>Number.isFinite(p.t)&&Number.isFinite(p.value)&&p.value>=0&&p.value<=1&&p.t<publishedAt).reduce<{t:number;value:number}|null>((latest,p)=>!latest||p.t>latest.t?p:latest,null);
}
