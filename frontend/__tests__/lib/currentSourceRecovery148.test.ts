import * as chart from '@/lib/liveChartHistory';
import { createReconnectCatchup } from '@/lib/reconnectCatchup';
const append = (chart as any).appendCurrentSourceObservations ?? ((history: any) => history);
const earlier='2026-10-19T12:00:00Z', later='2026-10-19T12:00:01Z';
const history=()=>({event_id:1,history_fold_revision:{'1':3},win_prob_history:{polymarket:[{timestamp:earlier,home_probability:.66,away_probability:.34}]}});
const detail=()=>({id:1,status:'live',blend_fold_revision:{'1':3},win_probability_sources:{polymarket:{value:.78,updated_at:later}}});

test('current actual source price reaches the existing series at its own time',()=>{
 const h=history();const out=append(h,detail());
 expect(out.win_prob_history.polymarket.at(-1)).toEqual({timestamp:later,home_probability:.78,away_probability:null});
 expect(h.win_prob_history.polymarket).toHaveLength(1);
 expect(out.aggregate_line).toBeUndefined();
});
test.each(['terminal','completed','wrong_event','folded','older_revision','missing_clock','bad_price','no_price'])('refuses %s detail without inventing chart evidence',(kind)=>{
 const d:any=detail(),h=history();
 if(kind==='terminal')d.status='completed';
 if(kind==='completed')d.completed_at=later;
 if(kind==='wrong_event')d.id=2;
 if(kind==='folded')d.blend_fold_revision={'1':3,'2':1};
 if(kind==='older_revision')d.blend_fold_revision={'1':2};
 if(kind==='missing_clock')delete d.win_probability_sources.polymarket.updated_at;
 if(kind==='bad_price')d.win_probability_sources.polymarket.value=1.5;
 if(kind==='no_price')delete d.win_probability_sources.polymarket;
 expect(append(h,d)).toBe(h);
});
test('never creates an unserved source series',()=>{
 const h={event_id:1,history_fold_revision:{'1':3},win_prob_history:{}};
 expect(append(h,detail())).toBe(h);
});
test.each(['later_real','covered','withdrawn'])('does not overwrite %s source evidence',(kind)=>{
 const h:any=history();
 if(kind==='later_real')h.win_prob_history.polymarket=[{timestamp:'2026-10-19T12:00:02Z',home_probability:.81}];
 if(kind==='covered')h.win_prob_history.polymarket[0].evidence={kind:'observed',covered_through:'2026-10-19T12:00:02Z'};
 if(kind==='withdrawn'){h.history_fold_revision={'1':4};h.win_prob_history.polymarket.push({timestamp:later,home_probability:null,game_state:{live_source_withdrawal:true}});}
 expect(append(h,detail())).toBe(h);
});

describe('bounded prompt recovery without removing the ordinary spread',()=>{
 beforeEach(()=>jest.useFakeTimers());afterEach(()=>jest.useRealTimers());
 test('prompt control advances pending slow timer once, retains latest generation',()=>{
  const calls:number[]=[];const c=createReconnectCatchup(g=>calls.push(g),()=>4999);
  c.recover(1);jest.advanceTimersByTime(50);c.recover(2,250);c.recover(3,250);
  jest.advanceTimersByTime(249);expect(calls).toEqual([]);
  jest.advanceTimersByTime(1);expect(calls).toEqual([3]);
  jest.advanceTimersByTime(5000);expect(calls).toEqual([3]);c.cancel();
 });
 test('ordinary control keeps its original delay and duplicate does not add timer',()=>{
  const calls:number[]=[];const c=createReconnectCatchup(g=>calls.push(g),()=>4000);
  c.recover(1);c.recover(2);jest.advanceTimersByTime(3999);expect(calls).toEqual([]);
  jest.advanceTimersByTime(1);expect(calls).toEqual([2]);c.cancel();
 });
 test('prompt control never postpones a timer already due sooner and teardown cancels',()=>{
  const calls:number[]=[];const c=createReconnectCatchup(g=>calls.push(g),()=>100);
  c.recover(1);jest.advanceTimersByTime(50);c.recover(2,250);
  jest.advanceTimersByTime(50);expect(calls).toEqual([2]);c.recover(3,250);c.cancel();
  jest.advanceTimersByTime(5000);expect(calls).toEqual([2]);
 });
});
