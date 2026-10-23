"""#10090 — K1 race, then the actual refresher's current-book gate on the bundled Challenger pair (attempt181).

Ported from the reviewed attempt190 packet onto the 8129 per-test schema rig.
"""
import tempfile
from pathlib import Path
from contextlib import asynccontextmanager
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace as NS
import pytest
from sqlalchemy import select,update,func,text
from app.models.models import Sport,Event,FuturesMarket,FuturesOutcome
from app.tasks.live_blend_refresh import HeldRowQuotes,LiveBlendRefresher
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


P='KXATPCHALLENGERMATCH-26OCT20BROKRU';H=P+'-BRO';A=P+'-KRU'
def healthy_socket():
 s=KalshiWebSocket();s._connected=True;s._socket=NS();s._subscribed={'ticker','market_lifecycle_v2'};s._book_sid=3;s._book_requested=s.book_tickers=frozenset([H,A]);s._book=KalshiOrderBook()
 for seq,(ticker,bid,ask) in enumerate([(H,'.57','.59'),(A,'.39','.41')],1):
  s._book.apply({'type':'orderbook_snapshot','sid':3,'seq':seq,'msg':{'market_ticker':ticker,'yes_dollars_fp':[[bid,'10']],'no_dollars_fp':[[str(Decimal(1)-Decimal(ask)),'10']]}})
 return s

@pytest.mark.asyncio
async def test_K1_real_PG_race_then_actual_refresher_current_book_gate(rig,monkeypatch):
 maker=rig.maker
 try:
  async with maker() as db:
   now=await db.scalar(select(func.clock_timestamp()));sport=Sport(key='local181',name='Local181');db.add(sport);await db.flush()
   ev=Event(sport_id=sport.id,home_team_name='Jenson Brooksby',away_team_name='Mitchell Krueger',status='live',commence_time=now-timedelta(hours=1),win_probability_sources={});db.add(ev);await db.flush()
   market=FuturesMarket(sport_id=sport.id,event_id=ev.id,source='kalshi',external_id=P,name='Brooksby vs Krueger',category='game',status='open',market_metadata={});db.add(market);await db.flush()
   home=FuturesOutcome(market_id=market.id,external_id=H,name=ev.home_team_name,current_probability=.60,rank=1,last_updated=now-timedelta(seconds=2));away=FuturesOutcome(market_id=market.id,external_id=A,name=ev.away_team_name,current_probability=.40,rank=2,last_updated=now-timedelta(minutes=30));db.add_all([home,away]);await db.flush();eid,hid,aid=ev.id,home.id,away.id
   await db.execute(update(FuturesOutcome).where(FuturesOutcome.id.in_([hid,aid])).values(is_winner=None));await db.commit()
  async with maker() as holder:
   await holder.execute(select(FuturesOutcome.id).where(FuturesOutcome.id==aid).with_for_update());holder_pid=await holder.scalar(select(func.pg_backend_pid()));bound=(await holder.scalar(select(func.clock_timestamp()))).timestamp()
   held=HeldRowQuotes();held._quotes[aid]=(.42,bound)
   async with maker() as writer:
    assert await writer.scalar(select(func.pg_backend_pid())) != holder_pid
    await writer.execute(update(FuturesOutcome).where(FuturesOutcome.id==hid).values(current_probability=.58,last_updated=func.clock_timestamp()));await writer.commit()
   async with maker() as probe:
    await probe.execute(text("SET LOCAL lock_timeout = '1ms'"))
    with pytest.raises(Exception) as caught:await probe.execute(select(FuturesOutcome.id).where(FuturesOutcome.id==aid).with_for_update())
    assert getattr(caught.value.orig,'sqlstate',None)=='55P03';await probe.rollback()
   @asynccontextmanager
   async def sessions():
    async with maker() as session:
     try:yield session;await session.commit()
     except BaseException:await session.rollback();raise
   s=healthy_socket();r=LiveBlendRefresher('kalshi',session_factory=sessions,min_refresh_interval_s=.25);r.held_quotes=held;r.require_current_book_proof=True;r.current_book_midpoint=s.current_book_midpoint;r._normal_closed=True
   async def skip_history(*args,**kwargs):return None,False
   monkeypatch.setattr('app.tasks.snapshots._create_or_update_win_prob_snapshot',skip_history)
   frames=[]
   async def publish(accepted):frames.extend(accepted)
   await r._refresh_batch([eid],100,publish_committed=publish)
   assert r.stats['errors']==0 and r.stats['stamped']==1
   async with maker() as reader:
    sources=(await reader.get(Event,eid)).win_probability_sources
    stored_away=await reader.get(FuturesOutcome,aid)
   assert sources['kalshi']['value']==pytest.approx(.59),'current-book proof was bypassed or K1 refused the wrong row'
   assert sources['kalshi']['observed_basis'][str(aid)]==pytest.approx((now-timedelta(minutes=30)).timestamp())
   assert float(stored_away.current_probability)==.40
   assert stored_away.last_updated==now-timedelta(minutes=30)
   assert len(frames)==1 and holder.in_transaction()
   # No stale stored or held fallback may stamp after the actual socket reset.
   s._reset_subscription()
   async with maker() as writer:
    await writer.execute(update(FuturesOutcome).where(FuturesOutcome.id==hid).values(current_probability=.57,last_updated=func.clock_timestamp()));await writer.commit()
   await r._refresh_batch([eid],101,publish_committed=publish)
   assert r.stats['errors']==0 and r.stats['stamped']==1 and len(frames)==1
   assert eid in r.pending_event_ids()
   async with maker() as reader:assert (await reader.get(Event,eid)).win_probability_sources['kalshi']['value']==pytest.approx(.59)
   assert holder.in_transaction();await holder.rollback()
 finally:pass
