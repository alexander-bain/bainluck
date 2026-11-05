import './nbaUnavailableBaseline.css';
/** Actual quantity versus this exact contract's threshold, never a forecast. */
export function NBAFinalThresholdPlot({actual,threshold,low,high,ticks,actualLabel,thresholdLabel,signed=false,leftLabel,rightLabel}:{actual:number;threshold:number;low:number;high:number;ticks:number[];actualLabel:string;thresholdLabel:string;signed?:boolean;leftLabel?:string;rightLabel?:string}){
 const x=(value:number)=>24+(value-low)/(high-low)*312;
 return <div className="nba-quantity-comparison"><svg viewBox="0 0 360 150" role="img" aria-label={`${actualLabel}, actual final. ${thresholdLabel}, contract threshold, not a projection. Points axis ${low} to ${high}. Pregame projection and prop chances unavailable.`}>
 <line x1="24" x2="336" y1="52" y2="52" className="nba-quantity-track"/>
 <line x1={x(actual)} x2={x(threshold)} y1="52" y2="52" className="nba-quantity-distance"/>
 <line x1={x(actual)} x2={x(actual)} y1="38" y2="66" className="nba-quantity-actual"/>
 <line x1={x(threshold)} x2={x(threshold)} y1="32" y2="72" className="nba-quantity-threshold"/>
 {ticks.map(t=><g key={t}><line x1={x(t)} x2={x(t)} y1="78" y2="84" className="nba-quantity-track"/><text x={x(t)} y="103" textAnchor="middle">{signed?(t===0?'Tie':Math.abs(t)):t}</text></g>)}
 {signed?<><text x="24" y="133">{leftLabel}</text><text x="336" y="133" textAnchor="end">{rightLabel}</text></>:<text x="336" y="133" textAnchor="end">combined points</text>}
 </svg><p className="nba-quantity-legend"><span>Solid: actual final</span><span>Dashed: selected line</span></p></div>;
}
