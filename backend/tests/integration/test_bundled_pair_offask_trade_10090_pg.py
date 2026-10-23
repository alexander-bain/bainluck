"""#10090 — An off-ask trade the ordinary policy selects reaches the headline only through its own landed or held observation (attempt189).

Ported from the reviewed attempt190 packet onto the 8129 per-test schema rig.
"""
import tempfile
import json
from pathlib import Path
from contextlib import asynccontextmanager
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace as NS
import pytest
from sqlalchemy import select,update,func
from app.models.models import Sport,Event,FuturesMarket,FuturesOutcome
from app.tasks.live_blend_refresh import LiveBlendRefresher,HeldRowQuotes
from app.tasks.kalshi import _kalshi_yes_probability
from app.services.kalshi_ws import KalshiWebSocket
from app.utils.kalshi_orderbook import KalshiOrderBook
from tests.integration.test_live_blend_grouped_commit_8129_pg import (  # noqa: F401 — the fixture
    DB_URL, rig,
)

pytestmark = pytest.mark.skipif(
    not DB_URL, reason="requires disposable SEARCH_TEST_DATABASE_URL"
)
# Receipts are diagnostics only; they never land in the tree.
ROOT = Path(tempfile.gettempdir()) / "bundled_pair_10090"
ROOT.mkdir(exist_ok=True)
ARM = "current"



def number(x):return None if x is None else float(x)

def price(q):return _kalshi_yes_probability(number(q.get('yes_bid_dollars')),number(q.get('yes_ask_dollars')),number(q.get('price_dollars')))

def snapshot(s,ticker,bid,ask,seq):
 return s._book.apply({'type':'orderbook_snapshot','sid':3,'seq':seq,'msg':{'market_ticker':ticker,'yes_dollars_fp':[] if bid is None else [[str(bid),'10']],'no_dollars_fp':[[str(Decimal(1)-Decimal(str(ask))),'10']]}})

@pytest.mark.asyncio
@pytest.mark.parametrize('landing',['commit','held'])
@pytest.mark.parametrize('kind',['zero_bid_offask_trade','empty_bid_offask_trade'])
async def test_offask_policy_change_must_reach_headline(rig,monkeypatch,kind,landing):
 maker=rig.maker
 suffix=str((23 if kind=='zero_bid_offask_trade' else 24)+(2 if landing=='held' else 0));p='KXATPCHALLENGERMATCH-26OCT'+suffix+'BROKRU';h=p+'-BRO';a=p+'-KRU'
 receipt={'arm':ARM,'case':kind,'landing':landing,'inputs':[],'stages':[],'claim':'backend regression gate; no measured visible delay'}
 try:
  async with maker() as db:
   now=await db.scalar(select(func.clock_timestamp()));sport=Sport(key='local189'+suffix,name='Local189'+suffix);db.add(sport);await db.flush()
   ev=Event(sport_id=sport.id,home_team_name='Jenson Brooksby',away_team_name='Mitchell Krueger',status='live',commence_time=now-timedelta(hours=1),win_probability_sources={});db.add(ev);await db.flush()
   market=FuturesMarket(sport_id=sport.id,event_id=ev.id,source='kalshi',external_id=p,name='Brooksby vs Krueger',category='game',status='open',market_metadata={});db.add(market);await db.flush()
   # Old away row predates kickoff, so neither arm may average it into a fresh home-only change.
   home=FuturesOutcome(market_id=market.id,external_id=h,name=ev.home_team_name,current_probability=.04,rank=1,last_updated=now)
   away=FuturesOutcome(market_id=market.id,external_id=a,name=ev.away_team_name,current_probability=.96,rank=2,last_updated=now-timedelta(hours=2))
   db.add_all([home,away]);await db.flush();eid,hid,aid=ev.id,home.id,away.id
   await db.execute(update(FuturesOutcome).where(FuturesOutcome.id.in_([hid,aid])).values(is_winner=None));await db.commit()
  @asynccontextmanager
  async def sessions():
   async with maker() as session:
    try:yield session;await session.commit()
    except BaseException:await session.rollback();raise
  s=KalshiWebSocket();s._connected=True;s._socket=NS();s._subscribed={'ticker','market_lifecycle_v2'};s._book_sid=3;s._book_requested=s.book_tickers=frozenset([h,a]);s._book=KalshiOrderBook()
  snapshot(s,h,'.03','.05',1);snapshot(s,a,'.95','.97',2)
  assert s.is_subscribed
  r=LiveBlendRefresher('kalshi',session_factory=sessions,min_refresh_interval_s=.25);r.require_current_book_proof=True;r.current_book_midpoint=getattr(s,'current_book_midpoint',lambda t:None);r.current_book_primary_price=getattr(s,'current_book_primary_price',None);r._normal_closed=True
  if landing=='held':r.held_quotes=HeldRowQuotes()
  custody=None
  if hasattr(s,'current_primary_input'):
   import ast
   from app.tasks import kalshi_ws as K
   from app.utils.kalshi_primary_quote import PrimaryQuoteCustody
   custody=PrimaryQuoteCustody()
   node=next(n for n in ast.walk(ast.parse(Path(K.__file__).read_text())) if isinstance(n,ast.FunctionDef) and n.name=='steady_primary_input')
   ns={'game_clients':[NS(sock=s,tickers={h,a},task=NS(done=lambda:False))],'ticker_to_ids':{h:(market.id,hid),a:(market.id,aid)},'prices':NS(settled_market_ids=set()),'primary_quote_custody':custody}
   exec(compile(ast.Module(body=[node],type_ignores=[]),K.__file__,'exec'),ns)
   r.current_primary_input=ns['steady_primary_input']
  async def skip_history(*args,**kwargs):return None,False
  monkeypatch.setattr('app.tasks.snapshots._create_or_update_win_prob_snapshot',skip_history)
  frames=[]
  async def publish(accepted):frames.extend(accepted)
  async def step(label,clock):
   await r._refresh_batch([eid],clock,publish_committed=publish)
   async with maker() as db:
    event=await db.get(Event,eid);row=await db.get(FuturesOutcome,hid);other=await db.get(FuturesOutcome,aid)
    source=event.win_probability_sources.get('kalshi')
    item={'label':label,'stored_home':float(row.current_probability),'stored_home_time':row.last_updated.isoformat(),'stored_away':float(other.current_probability),'away_time_unchanged':other.last_updated==now-timedelta(hours=2),'stamped':None if source is None else source['value'],'observed_basis':None if source is None else source.get('observed_basis'),'frames':len(frames),'pending':eid in r.pending_event_ids(),'errors':r.stats['errors'],'no_reading':r.stats['no_reading']}
   receipt['stages'].append(item);assert item['errors']==0 and item['away_time_unchanged'];return item
  first=await step('initial_tight_book',100);assert first['stamped']==pytest.approx(.04)
  assert str(aid) not in first['observed_basis']
  seq=3
  for index,trade in enumerate(['.08','.11','.10']):
   ask='.12'
   quote=snapshot(s,h,'0' if kind=='zero_bid_offask_trade' else None,ask,seq);seq+=1
   # This is the actual service ticker overlay; it preserves a genuine fresh trade.
   raw={'market_ticker':h,'yes_bid_dollars':'0','yes_ask_dollars':ask}
   raw['price_dollars']=trade
   delivered=s._overlay_ticker(raw)
   selected=price(delivered)
   no_trade=dict(delivered);no_trade.pop('price_dollars',None)
   receipt['inputs'].append({'raw_ticker':raw,'healthy_book_quote':quote,'delivered':delivered,'selected':selected,'selected_without_trade':price(no_trade),'midpoint_proof':None if not hasattr(s,'current_book_midpoint') else s.current_book_midpoint(h),'book_owner':s._book._owners[h],'book_sid':s._book_sid,'book_awaiting':h in s._book._awaiting,'subscription_healthy':s.is_subscribed})
   assert selected==pytest.approx(float(trade))
   if custody is not None: custody.receive(hid,delivered)
   captured=None if custody is None else custody.snapshot([hid])
   if landing=='commit':
    async with maker() as db:
     returned=await db.scalar(update(FuturesOutcome).where(FuturesOutcome.id==hid).values(current_probability=selected,last_updated=func.clock_timestamp()).returning(FuturesOutcome.last_updated));await db.commit()
    if custody is not None: custody.committed(captured,{hid:returned})
   else:
    async with maker() as db: bound=(await db.scalar(select(func.clock_timestamp()))).timestamp()
    r.held_quotes.hold({hid:(selected,bound)})
    if custody is not None:custody.admitted(captured,{hid:(selected,bound)})
   await step('thin_input_'+str(index+1),101+index)
  # Same persisted evidence retried without a new input: no new book capability appears.
  await step('same_input_retry_1',104);await step('same_input_retry_2',105)
  if hasattr(s,'current_book_midpoint'):
   protected_value=receipt['stages'][-1]['stamped'];protected_frames=len(frames)
   # Existing fail-closed protections must not be weakened to manufacture progress.
   s._reset_subscription();reset=await step('reset_refuses',106)
   assert reset['stamped']==pytest.approx(protected_value) and reset['pending'] and reset['frames']==protected_frames
   s._connected=True;s._socket=NS();s._subscribed={'ticker','market_lifecycle_v2'};s._book_sid=4;s._book_requested=s.book_tickers=frozenset([h,a]);s._book=KalshiOrderBook();s._book_sid=3
   snapshot(s,h,'.14','.16',1);snapshot(s,a,'.95','.97',2)
   mismatch=await step('stale_stored_home_mismatch_refuses',107)
   assert mismatch['stamped']==pytest.approx(protected_value) and mismatch['pending'] and mismatch['frames']==protected_frames
   snapshot(s,h,'.09','.11',3)
   assert s.current_book_midpoint(h)==Decimal('.10')
   async with maker() as db:
    await db.execute(update(FuturesOutcome).where(FuturesOutcome.id==hid).values(is_winner=False,resolution_source='kalshi'));await db.commit()
   settled=await step('settled_row_refuses_even_matching_book',108)
   assert settled['stamped']==pytest.approx(protected_value) and settled['frames']==protected_frames
   receipt['safety_assertions']='reset, mismatched stored home, settled home all refuse; stale away never contributes'
  # Preserve all observations before the regression assertion fails in candidate.
  (ROOT/(ARM+'-'+kind+'-'+landing+'.json')).write_text(json.dumps(receipt,indent=2,default=str)+'\n')
  observed=[x['stamped'] for x in receipt['stages'] if x['label'].startswith('thin_input_')]
  assert observed==pytest.approx([.08,.11,.10]), 'fresh normal-policy changes stored but refused by midpoint-only headline gate'
 finally:
  (ROOT/(ARM+'-'+kind+'-'+landing+'.json')).write_text(json.dumps(receipt,indent=2,default=str)+'\n')
