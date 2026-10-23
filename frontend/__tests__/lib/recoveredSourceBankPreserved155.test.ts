import { admitRecoveredSourceObservations, admitCurrentSourceObservations, admitChartFrames, appendAdmittedSourceObservations } from "../../lib/liveChartHistory";
const t=(n:number)=>new Date(Date.UTC(2026,9,19,12,0,n)).toISOString();
const detail=(rev:number,k:number)=>({id:1,status:"live",blend_fold_revision:{1:rev},win_probability_sources:{polymarket:{value:.66,updated_at:t(11)},kalshi:{value:k,updated_at:t(rev)}}});
const currentHistory={event_id:1,history_fold_revision:{1:13},win_prob_history:{polymarket:[{timestamp:t(0),away_probability:null,home_probability:.5}],kalshi:[{timestamp:t(0),away_probability:null,home_probability:.5}]}};
const oldHistory={event_id:1,history_fold_revision:{1:11},win_prob_history:{polymarket:[{timestamp:t(0),away_probability:null,home_probability:.5}]}};
it("review155 preserves banked newer-source excursion when older pair history is not adopted",()=>{
  const priorHistory={...currentHistory,history_fold_revision:{1:12}};
  let bank=admitCurrentSourceObservations(admitChartFrames(1,[],detail(12,.55)),null,priorHistory,detail(12,.55));
  bank=admitCurrentSourceObservations(admitChartFrames(1,[],detail(13,.6)),bank,currentHistory,detail(13,.6));
  expect(bank.sourcePoints?.some(p=>p.source==='kalshi' && p.source_probability===.55)).toBe(true);
  const recovered={id:1,status:'live',blend_fold_revision:{1:11},win_probability_sources:{polymarket:{value:.78,updated_at:t(11)}}};
  const after=admitRecoveredSourceObservations(bank,oldHistory,recovered,detail(13,.6));
  const rerendered=admitCurrentSourceObservations(admitChartFrames(1,[],detail(13,.6)),after,currentHistory,detail(13,.6));
  const rendered=appendAdmittedSourceObservations(currentHistory,rerendered,detail(13,.6));
  expect(rendered?.win_prob_history?.kalshi.some(p=>p.timestamp===t(12)&&p.home_probability===.55)).toBe(true);
});
