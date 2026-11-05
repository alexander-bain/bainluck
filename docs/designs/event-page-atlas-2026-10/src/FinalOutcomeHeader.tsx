import {nbaProjectionUnavailable,withoutNBAProjection} from './basketballProjectionAvailability';
import {eventReaderTime} from './eventReaderTime';
import {retainedTennisGames} from './tennisGamesEvidence';
import { CheckIcon, Cross2Icon, CircleIcon, SquareIcon } from '@radix-ui/react-icons';
import records from './finalHeaders.json';
import { probabilityLabel } from './probabilityLabel';
import './finalOutcomeHeader.css';

export type FinalHeaderSpecimen = (typeof records)[number];
export const finalHeaderFor = (id: string) => records.map(record=>withoutNBAProjection(record,nbaProjectionUnavailable)).find(record => record.id === id);
const time = (value: string | null) => eventReaderTime.full(value);

/** All fields are retained evidence. A result never supplies a probability or a projection. */
export function FinalOutcomeHeader({specimen:s, observation, compact=false}: {
  specimen:FinalHeaderSpecimen;
  compact?:boolean;
  observation?:{home:number;away:number;at:string};
}) {
  const games=s.id==='tennis'?retainedTennisGames:null;
  const projection = s.projectedHome != null && s.projectedAway != null;
  const hasProjection = Boolean(games?.projection || projection);
  return <div className="final-outcome-header">
    <div className="final-contenders">
      {(['home','away'] as const).map(side => {
        const decided = s.winner === 'home' || s.winner === 'away';
        const won = s.winner === side;
        return <div className={`final-contender ${side}`} key={side}>
          <strong className="final-name">{s[side]}</strong>
          <span className="final-verdict">{decided&&(won?<CheckIcon/>:<Cross2Icon/>)}{decided?(won?'Won':'Lost'):s.winner==='draw'?'Draw':'Result unconfirmed'}</span>
          <strong className="final-baseline">{probabilityLabel(side==='home'?s.homeBaseline:s.awayBaseline)}</strong>
          <span className="final-baseline-caption"><CircleIcon/>{s.baselineLabel.startsWith("Opening")?"Pregame · opening":s.baselineLabel}</span>
        </div>;
      })}
    </div>
    <div className={`final-score-projection${hasProjection ? "" : " final-score-only"}`}>
      <div><strong className="final-score">{s.homeScore}–{s.awayScore}</strong><span>Final · {s.unit}</span>{games&&<span>{games.home}–{games.away} games</span>}</div>
      {hasProjection&&<div><span><SquareIcon/> Projected before game</span><strong className="final-projection">{games?.projection?`${games.projection.home}–${games.projection.away}`:`${s.projectedHome}–${s.projectedAway}`}</strong>{games?.projection?<span>games · not sets</span>:<span>{s.unit}</span>}</div>}
    </div>
    {!compact&&<>
    <p className="final-clock">{s.baselineAt?`Pregame win chances · ${time(s.baselineAt)}`:'Opening quote time unavailable'}</p>
    {(projection||games?.projection)&&<p className="final-clock">Pregame projection · {time(games?.projection?.at??s.projectionAt)}</p>}
    </>}
    {observation&&<div className="final-observation" aria-live="polite">
      <span>Selected history · {time(observation.at)}</span>
      <div><strong className="home">{s.home} {probabilityLabel(observation.home)}</strong><strong className="away">{s.away} {probabilityLabel(observation.away)}</strong></div>
      <span>Recorded chances; final score above stays fixed.</span>
    </div>}
    {!compact&&<details className="final-evidence"><summary>Result, baseline & projection evidence</summary><FinalHeaderFacts specimen={s}/></details>}
  </div>;
}

export function FinalHeaderFacts({specimen:s}:{specimen:FinalHeaderSpecimen}){
 const games=s.id==='tennis'?retainedTennisGames:null;
 const projection=s.projectedHome!=null&&s.projectedAway!=null;
 return <div className="final-header-facts"><h3>Result, baseline & projection</h3>
      <p>Final score: {s.homeScore}–{s.awayScore} {s.unit}. Score record: {time(s.scoreAt)}. Completed: {time(s.completedAt)}.</p>
      <p>{s.baselineLabel}: {s.home} {probabilityLabel(s.homeBaseline)}, {s.away} {probabilityLabel(s.awayBaseline)}. {s.baselineAt?time(s.baselineAt):'Exact opening time unavailable.'}</p>
      <p>{games?.projection?`Final games: ${games.home}–${games.away}. Pregame projected games: ${games.projection.home}–${games.projection.away} · ${time(games.projection.at)}. Actual observation time unavailable; ESPN detail retrieved ${time(games.capturedAt)}.`:projection?`Pregame projection: ${s.projectedHome}–${s.projectedAway} ${s.unit}, ${time(s.projectionAt)}.`:'No comparable paired pregame projection is supplied.'} {!games&&s.projectionNote}</p>
      <p>Current probability unavailable. These are archived observations, not current chances. Archived history, where available, preserves recorded probabilities. A final result does not supply a probability.</p>
<p>Source record: {s.source}</p></div>;
}
