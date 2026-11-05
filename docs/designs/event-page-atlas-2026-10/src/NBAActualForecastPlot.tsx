import './nbaUnavailableBaseline.css';
/** Quantities only: no chance axis when no chances are supplied. */
export function NBAActualForecastPlot({actual,forecast,low,high,ticks,actualLabel,forecastLabel,signed=false,leftLabel,rightLabel}:{actual:number;forecast:number;low:number;high:number;ticks:number[];actualLabel:string;forecastLabel:string;signed?:boolean;leftLabel?:string;rightLabel?:string}){
 const x=(value:number)=>24+(value-low)/(high-low)*312;
 return <div className="nba-quantity-comparison"><svg viewBox="0 0 360 150" role="img" aria-label={`${actualLabel}, actual final. ${forecastLabel}, pregame projection. Points axis ${low} to ${high}. Pregame prop chances unavailable; no probability is plotted.`}>
 <line x1="24" x2="336" y1="52" y2="52" className="nba-quantity-track"/>
 <line x1={x(actual)} x2={x(forecast)} y1="52" y2="52" className="nba-quantity-distance"/>
 <line x1={x(actual)} x2={x(actual)} y1="38" y2="66" className="nba-quantity-actual"/>
 <rect x={x(forecast)-5} y="47" width="10" height="10" className="nba-quantity-forecast"/>
 {ticks.map(t=><g key={t}><line x1={x(t)} x2={x(t)} y1="78" y2="84" className="nba-quantity-track"/><text x={x(t)} y="103" textAnchor="middle">{signed?(t===0?'Tie':Math.abs(t)):t}</text></g>)}
 {signed?<><text x="24" y="133">{leftLabel}</text><text x="336" y="133" textAnchor="end">{rightLabel}</text></>:<text x="336" y="133" textAnchor="end">combined points</text>}
 </svg><p className="nba-quantity-legend"><span>┃ Actual final</span><span>□ Pregame projection</span></p></div>;
}
