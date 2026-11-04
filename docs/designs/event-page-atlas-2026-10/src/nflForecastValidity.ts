import type {nflContext} from './nflReplay.ts';
import type {StoryReadingFrame} from './storyReadingFrame.ts';

type Context=ReturnType<typeof nflContext>;
export interface ForecastClock {scope:string;through:string}
export function advanceForecastClock(clock:ForecastClock,next:ForecastClock):ForecastClock {
 if(next.scope!==clock.scope||!Number.isFinite(Date.parse(next.through))||Date.parse(next.through)<=Date.parse(clock.through))return clock;
 return {...next};
}
/** Validity may remove a current forecast while the reader keeps its sporting snapshot.
 * No received payload values are copied into the displayed frame. This replay clock
 * is explicit; it is not a production wall clock or a provider freshness guarantee. */
export function nflForecastPresentation(state:StoryReadingFrame<Context>,clock:ForecastClock){
 const shown=state.displayed.payload;
 const horizon=Math.max(Date.parse(state.received.through),Date.parse(clock.through));
 const validClock=clock.scope===state.displayed.scope&&Number.isFinite(horizon)&&Number.isFinite(Date.parse(clock.through));
 const candidate=shown.projection;
 const expiry=shown.lastProjection?.valid_until??null;
 const expired=!shown.final&&expiry!==null&&validClock&&Date.parse(expiry)<=horizon;
 const admitted=candidate&&validClock&&Number.isFinite(Date.parse(candidate.valid_until))&&Date.parse(candidate.valid_until)>horizon;
 return {context:candidate&&!admitted?{...shown,projection:null}:shown,expired,
  horizon:validClock?new Date(horizon).toISOString():null,
  historical:!shown.final&&shown.lastProjection&&!admitted?shown.lastProjection:null};
}
