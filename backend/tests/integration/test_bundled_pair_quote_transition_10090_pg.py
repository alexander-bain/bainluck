"""#10090 — Healthy book changes select ordinary-policy prices through committed and held paths without another ticker (attempt190).

Ported from the reviewed attempt190 packet onto the 8129 per-test schema rig.
"""
import tempfile
import json
from pathlib import Path
from contextlib import asynccontextmanager
from datetime import timedelta
from types import SimpleNamespace as NS
import pytest
from sqlalchemy import select,update,func
from app.models.models import Sport,Event,FuturesMarket,FuturesOutcome
from app.tasks.live_blend_refresh import LiveBlendRefresher,HeldRowQuotes
from app.services.kalshi_ws import KalshiWebSocket
from app.utils.kalshi_orderbook import KalshiOrderBook
from tests import test_bundled_pair_quote_transition_10090 as fixture
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



@pytest.mark.asyncio
@pytest.mark.parametrize('landing',['commit','held'])
async def test_real_book_transition_delivers_without_another_ticker(rig,monkeypatch,landing):
 maker=rig.maker
 suffix='27' if landing=='commit' else '28';p='KXATPCHALLENGERMATCH-26OCT'+suffix+'BROKRU';h=p+'-BRO';a=p+'-KRU'
 receipt={'arm':ARM,'landing':landing,'original_tickers':0,'selected':[],'steps':[],'claim':'correctness gate; no visible interval measured'}
 try:
  async with maker() as db:
   now=await db.scalar(select(func.clock_timestamp()));sport=Sport(key='local190'+suffix,name='Local190'+suffix);db.add(sport);await db.flush()
   ev=Event(sport_id=sport.id,home_team_name='Jenson Brooksby',away_team_name='Mitchell Krueger',status='live',commence_time=now-timedelta(hours=1),win_probability_sources={});db.add(ev);await db.flush()
   market=FuturesMarket(sport_id=sport.id,event_id=ev.id,source='kalshi',external_id=p,name='Brooksby vs Krueger',category='game',status='open',market_metadata={});db.add(market);await db.flush()
   home=FuturesOutcome(market_id=market.id,external_id=h,name=ev.home_team_name,current_probability=.825,rank=1,last_updated=now)
   away=FuturesOutcome(market_id=market.id,external_id=a,name=ev.away_team_name,current_probability=.175,rank=2,last_updated=now-timedelta(hours=2))
   db.add_all([home,away]);await db.flush();eid,hid,aid,mid=ev.id,home.id,away.id,market.id
   await db.execute(update(FuturesOutcome).where(FuturesOutcome.id.in_([hid,aid])).values(is_winner=None));await db.commit()
  @asynccontextmanager
  async def sessions():
   async with maker() as session:
    try:yield session;await session.commit()
    except BaseException:await session.rollback();raise
  s=KalshiWebSocket();s._connected=True;s._socket=NS();s._subscribed={'ticker','market_lifecycle_v2'};s._book_sid=3;s._book_requested=s.book_tickers=frozenset([h,a]);s._book=KalshiOrderBook()
  s._book.apply(fixture.old.snapshot(h,'.82','.83',1));s._book.apply(fixture.old.snapshot(a,'.17','.18',2))
  r=LiveBlendRefresher('kalshi',session_factory=sessions,min_refresh_interval_s=.25);r._normal_closed=True
  s,c,r,handle,proof,ns=fixture.consumer(s,ticker_ids={h:(mid,hid),a:(mid,aid)},event_ids={hid:eid,aid:eid},refresher=r)
  if landing=='held':r.held_quotes=HeldRowQuotes()
  async def skip_history(*args,**kwargs):return None,False
  monkeypatch.setattr('app.tasks.snapshots._create_or_update_win_prob_snapshot',skip_history)
  frames=[]
  async def publish(accepted):frames.extend(accepted)
  async def step(label,clock):
   await r._refresh_batch([eid],clock,publish_committed=publish)
   async with maker() as db:
    event=await db.get(Event,eid);row=await db.get(FuturesOutcome,hid);other=await db.get(FuturesOutcome,aid);source=event.win_probability_sources.get('kalshi')
    item={'label':label,'stored':float(row.current_probability),'stamped':None if source is None else source['value'],'frames':len(frames),'errors':r.stats['errors'],'pending':eid in r.pending_event_ids(),'away_unchanged':other.last_updated==now-timedelta(hours=2),'cached_original_trade':s._last_trade.get(h)}
   receipt['steps'].append(item);assert item['errors']==0 and item['away_unchanged'];return item
  # The sole original ticker: normal tight policy selects .825, not its .83 trade.
  await handle(s._overlay_ticker({'market_ticker':h,'price_dollars':'.83'}));receipt['original_tickers']+=1
  assert ns['price_buffer'][hid][0]==.825
  captured=c.snapshot([hid])
  async with maker() as db:
   returned=await db.scalar(update(FuturesOutcome).where(FuturesOutcome.id==hid).values(current_probability=.825,last_updated=func.clock_timestamp()).returning(FuturesOutcome.last_updated));await db.commit()
  c.committed(captured,{hid:returned})
  first=await step('initial_tight',100);assert first['stamped']==pytest.approx(.825)
  for idx,(bid,ask,expected) in enumerate([('.20','.90',.83),('.82','.83',.825),('.20','.90',.83)]):
   emitted=await fixture.book(s,fixture.old.snapshot(h,bid,ask,3+idx),handle)
   assert len(emitted)==1
   selected=ns['price_buffer'][hid][0];assert selected==pytest.approx(expected)
   receipt['selected'].append({'value':selected,'origin':'healthy book change; original trade unchanged','identity_attached':'_primary_quote_identity' in emitted[0]})
   captured=c.snapshot([hid])
   if landing=='commit':
    async with maker() as db:
     returned=await db.scalar(update(FuturesOutcome).where(FuturesOutcome.id==hid).values(current_probability=selected,last_updated=func.clock_timestamp()).returning(FuturesOutcome.last_updated));await db.commit()
    c.committed(captured,{hid:returned})
   else:
    async with maker() as db:bound=(await db.scalar(select(func.clock_timestamp()))).timestamp()
    r.held_quotes.hold({hid:(selected,bound)});c.admitted(captured,{hid:(selected,bound)})
   await step('book_transition_'+str(idx+1),101+idx)
  # Venue is silent: two retries must not wait for an unrelated new original ticker.
  await step('silent_retry_1',104);await step('silent_retry_2',105)
  stamped=[x['stamped'] for x in receipt['steps'] if x['label'].startswith('book_transition_')]
  receipt['safety']='Only one genuine ticker; later inputs are actual book callbacks through real handle_ticker. Stale away unchanged.'
  (ROOT/(ARM+'-transition-'+landing+'.json')).write_text(json.dumps(receipt,indent=2,default=str)+'\n')
  assert stamped==pytest.approx([.83,.825,.83]),'healthy book transition selected a legitimate cached trade but headline refused it'
  before=receipt['steps'][-1]['frames'];s._reset_subscription();blocked=await step('reset_refuses',106)
  assert blocked['frames']==before and blocked['pending']
 finally:
  (ROOT/(ARM+'-transition-'+landing+'.json')).write_text(json.dumps(receipt,indent=2,default=str)+'\n')
