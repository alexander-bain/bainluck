import './totalExpectation.css';
export type ExpectationPoint={key:string;threshold:number;value:number|null};
export function TotalExpectationPlot({records,actual,forecast,selectedKey,low,high,ticks,showUnits=true}:{records:ExpectationPoint[];actual:number;forecast:number|null;selectedKey?:string;low:number;high:number;ticks:number[];showUnits?:boolean}){
 const known=records.filter(r=>r.value!=null&&Number.isFinite(r.value)&&r.value>=0&&r.value<=1);
 const x=(n:number)=>40+(n-low)/(high-low)*288,y=(n:number)=>165-n*120;
 const closeLabels=forecast!==null&&Math.abs(x(actual)-x(forecast))<80;
 return (
  <svg viewBox="0 0 360 202" role="img" aria-label={`${known.length} recorded pregame chances on a zero to 100 percent scale. Solid line: ${actual} actual points. ${forecast===null?'No qualified forecast.':`Dashed line: ${forecast} projected points.`} Missing chances are not zero.`}>
   {[0,.5,1].map(p=><g key={p}><line x1="40" x2="328" y1={y(p)} y2={y(p)} className="expectation-grid"/><text x="32" y={y(p)+4} textAnchor="end">{p*100}%</text></g>)}
   <line x1={x(actual)} x2={x(actual)} y1="28" y2="172" className="expectation-actual"/><text x={x(actual)-(closeLabels?4:0)} y="17" textAnchor={closeLabels?"end":"middle"} className="expectation-label">{actual} actual</text>
   {forecast!==null&&<><line x1={x(forecast)} x2={x(forecast)} y1="28" y2="172" className="expectation-projection"/><text x={x(forecast)+(closeLabels?4:0)} y="17" textAnchor={closeLabels?"start":"middle"} className="expectation-label">{forecast} forecast</text></>}
   {known.map(r=><g key={r.key}><line x1={x(r.threshold)} x2={x(r.threshold)} y1={y(r.value!)} y2="165" className="expectation-stem"/><circle cx={x(r.threshold)} cy={y(r.value!)} r={r.key===selectedKey?6:4} className={`expectation-dot ${r.key===selectedKey?'selected':''}`}/></g>)}
   {ticks.map(n=><text x={x(n)} y="189" textAnchor="middle" key={n}>{n}</text>)}{showUnits&&<text x="328" y="189" textAnchor="end">points</text>}
  </svg>
);
}
