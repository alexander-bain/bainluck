/** Comparisons between observations, never a reconstructed probability history.
 * No interpolated values are exposed; chart inspection keeps its separate gap policy.
 */
export type RecordedEstimate={timestamp:string;probability:number};
export type EstimateLink={from:RecordedEstimate;to:RecordedEstimate};
export function beforeEstimateLinks(points:readonly RecordedEstimate[],start:string,through?:string):EstimateLink[]{
 const boundary=Date.parse(start),cutoff=through===undefined?Infinity:Date.parse(through);
 if(!Number.isFinite(boundary)||Number.isNaN(cutoff)||points.length<2)return [];
 const seen=new Set<number>();
 for(const point of points){
  const at=Date.parse(point.timestamp);
  if(!Number.isFinite(at)||at>=boundary||at>cutoff||seen.has(at)||!Number.isFinite(point.probability)||point.probability<0||point.probability>1)return [];
  seen.add(at);
 }
 const sorted=[...points].sort((a,b)=>Date.parse(a.timestamp)-Date.parse(b.timestamp));
 return sorted.slice(1).map((to,i)=>({from:sorted[i],to}));
}
