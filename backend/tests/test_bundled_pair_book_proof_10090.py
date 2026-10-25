import ast, asyncio, inspect, os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace as NS
import pytest
from app.services.kalshi_ws import KalshiWebSocket
from app.utils.kalshi_orderbook import KalshiOrderBook
from app.utils.live_blend import MarketOutcomes, compute_source_home_probability
from app.utils.aggregation import oldest_observation_time
from app.tasks.live_blend_refresh import LiveBlendRefresher
import app.tasks.kalshi_ws as consumer
P="KXATPCHALLENGERMATCH-26OCT19BROKRU";H=P+"-BRO";A=P+"-KRU"
NOW=datetime.now(timezone.utc);OLD=NOW-timedelta(minutes=30)
def snapshot(ticker,bid,ask,seq=1):
 return {'type':'orderbook_snapshot','sid':3,'seq':seq,'msg':{'market_ticker':ticker,'yes_dollars_fp':[[str(bid),'10']],'no_dollars_fp':[[str(Decimal(1)-Decimal(str(ask))),'10']]}}
def socket():
 s=KalshiWebSocket();s._connected=True;s._socket=NS();s._subscribed={'ticker','market_lifecycle_v2'};s._book_sid=3;s._book_requested=s.book_tickers=frozenset([H,A]);s._book=KalshiOrderBook()
 s._book.apply(snapshot(H,'.82','.83',1));s._book.apply(snapshot(A,'.18','.19',2));return s

def group(stale_home=False):
 m=NS(id=1,source='kalshi',external_id=P,name='Brooksby vs Krueger',status='open',market_metadata={})
 h=NS(id=11,name='Jenson Brooksby',external_id=H,current_probability=Decimal('.825000'),rank=1,last_updated=OLD if stale_home else NOW,is_winner=None,resolution_source=None)
 a=NS(id=12,name='Mitchell Krueger',external_id=A,current_probability=Decimal('.185000'),rank=2,last_updated=NOW if stale_home else OLD,is_winner=None,resolution_source=None)
 return [MarketOutcomes(m,[h,a],event_commence_time=NOW-timedelta(hours=1),event_has_result=False)]

def read(g,lookup=None):
 kwargs={}
 if 'require_current_book_midpoint' in inspect.signature(compute_source_home_probability).parameters:
  kwargs={'require_current_book_midpoint':True,'current_book_midpoint':lookup}
 return compute_source_home_probability(g,'Brooksby','Krueger',**kwargs)

def lookup(s):
 method=getattr(s,'current_book_midpoint',None)
 return method if method is not None else lambda ticker:None

@pytest.mark.parametrize('stale_home',[False,True])
def test_stale_leg_without_proof_never_enters_fresh_stamped_reading(stale_home):
 g=group(stale_home);proof={A:Decimal('.185')} if stale_home else {H:Decimal('.825')}
 r=read(g,proof.get)
 assert r is None if stale_home else (not r.devigged and r.home_probability==pytest.approx(.825))
 if r:assert oldest_observation_time(r.contributing_outcomes)==NOW

@pytest.mark.parametrize('stale_home',[False,True])
def test_live_book_confirms_unchanged_old_row_without_forging_its_clock(stale_home):
 g=group(stale_home);s=socket();r=read(g,lookup(s))
 assert r.devigged and r.home_probability==pytest.approx(.82)
 assert oldest_observation_time(r.contributing_outcomes)==OLD
 assert [o.last_updated for o in g[0].outcomes]==([OLD,NOW] if stale_home else [NOW,OLD])
 # One leg changes; the other book is still healthy and its DB clock stays old.
 s._book.apply(snapshot(A,'.17','.18',3));g[0].outcomes[1].current_probability=Decimal('.175000')
 moved=read(g,lookup(s));assert moved.home_probability==pytest.approx(.825) and moved.devigged
 assert oldest_observation_time(moved.contributing_outcomes)==OLD

@pytest.mark.parametrize('damage',['reset','retiring','disconnected','no_socket','unacknowledged','rejected','book_pending','departed','not_requested','wrong_sid','gap','crossed','wide','mismatch'])
def test_missing_or_invalid_current_book_cannot_authorize(damage):
 s=socket();g=group()
 if damage=='reset':s._reset_subscription()
 elif damage=='retiring':s._retiring=True
 elif damage=='disconnected':s._connected=False
 elif damage=='no_socket':s._socket=None
 elif damage=='unacknowledged':s._subscribe_pending={1:'ticker'}
 elif damage=='rejected':s._subscribe_rejected={'error':True}
 elif damage=='book_pending':s._book_pending=9
 elif damage=='departed':s.book_tickers=frozenset([A])
 elif damage=='not_requested':s._book_requested=frozenset([A])
 elif damage=='wrong_sid':s._book_sid=4
 elif damage=='gap':s._book.apply({'type':'orderbook_delta','sid':3,'seq':9,'msg':{'market_ticker':H,'side':'yes','price_dollars':'.80','delta_fp':'1'}})
 elif damage=='crossed':s._book.apply(snapshot(H,'.90','.80',3))
 elif damage=='wide':s._book.apply(snapshot(H,'.50','1.00',3))
 elif damage=='mismatch':s._book.apply(snapshot(H,'.80','.81',3))
 assert read(g,lookup(s)) is None

@pytest.mark.parametrize('damage',['home_winner','away_winner','home_resolution','away_resolution','event_result'])
def test_settled_pair_never_authorized_even_with_current_book(damage):
 s=socket();g=group()
 if damage=='event_result':
  from dataclasses import replace
  g[0]=replace(g[0],event_has_result=True)
 else:
  row=g[0].outcomes[0 if damage.startswith('home') else 1]
  if damage.endswith('winner'):row.is_winner=False
  else:row.resolution_source='kalshi'
 assert read(g,lookup(s)) is None

def nested(name,namespace):
 tree=ast.parse(Path(consumer.__file__).read_text());node=next(n for n in ast.walk(tree) if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name==name)
 code=compile(ast.fix_missing_locations(ast.Module(body=[node],type_ignores=[])),consumer.__file__,'exec');exec(code,namespace);return namespace[name]

def test_consumer_uses_only_current_game_clients_and_refuses_handover_conflict():
 s=socket();client=NS(sock=s,tickers={H,A},task=NS(done=lambda:False));clients=[client];prices=NS(settled_market_ids=set())
 try:f=nested('steady_book_midpoint',{'game_clients':clients,'ticker_to_ids':{H:(1,11),A:(1,12)},'prices':prices})
 except StopIteration:pytest.fail('consumer has no current-book proof owner')
 assert f(H)==Decimal('.825')
 other=socket();other._book.apply(snapshot(H,'.80','.81',3));clients.append(NS(sock=other,tickers={H},task=NS(done=lambda:False)))
 assert f(H) is None
 clients.pop();prices.settled_market_ids.add(1);assert f(H) is None
 prices.settled_market_ids.clear();client.task=NS(done=lambda:True);assert f(H) is None
 client.task=NS(done=lambda:False);clients.clear();assert f(H) is None

@pytest.mark.asyncio
async def test_terminal_prepare_revokes_proof_before_its_first_await():
 class Barrier:
  async def __aenter__(self):
   assert 1 in prices.settled_market_ids, 'terminal accepted but proof survived until deferred handler'
  async def __aexit__(self,*args):return False
 prices=NS(settled_market_ids=set())
 ns={'ticker_owner':{},'_UNCAPTURED':object(),'open_contract_ids':{},'ticker_to_ids':{H:(1,11)},'market_id_by_ext':{P:1},'prices':prices,'buffer_lock':Barrier(),'price_buffer':{},'is_terminal':lambda x:x=='settled','handle_lifecycle':lambda *args,**kwargs:None}
 f=nested('prepare_lifecycle',ns);await f({'market_ticker':H,'status':'settled'})

@pytest.mark.asyncio
@pytest.mark.parametrize('expire',[False,True])
async def test_real_refresh_batch_uses_proof_and_rechecks_after_budget_await(monkeypatch,expire):
 from sqlalchemy.sql.dml import Update
 from app.tasks.live_blend_refresh import atomic_stamp_expression
 g=group();s=socket();r=LiveBlendRefresher('kalshi',min_refresh_interval_s=.25);r.require_current_book_proof=True;r.current_book_midpoint=lookup(s)
 event=NS(id=1,home_team_name='Brooksby',away_team_name='Krueger',status='live',completed_at=None,espn_win_prob_home=None,opening_home_probability=None,win_probability_sources={'kalshi':{'value':.815,'updated_at':(NOW-timedelta(seconds=5)).isoformat()}})
 updates=[]
 class Session:
  async def execute(self,stmt,*args,**kwargs):
   if isinstance(stmt,Update):
    updates.append(stmt);return NS(first=lambda:({'kalshi':{'value':.82,'updated_at':NOW.isoformat()}},1))
   if expire:s._reset_subscription()
   return NS()
  def add(self,*args):pass
  async def flush(self):pass
 @asynccontextmanager
 async def session():yield Session()
 async def groups(_session,ids):return {1:(event,g)}
 async def snapshot(*args,**kwargs):return None,False
 r._session_factory=session;monkeypatch.setattr(r,'_read_groups',groups)
 monkeypatch.setattr('app.tasks.snapshots._create_or_update_win_prob_snapshot',snapshot)
 await r._refresh_batch([1],0)
 assert len(updates)==(0 if expire else 1)
 assert r.stats['errors']==0
 if expire:assert 1 in r.pending_event_ids()
 if updates:
  from sqlalchemy.dialects import postgresql
  assert 'clock_timestamp()' in str(updates[0].compile(dialect=postgresql.dialect()))


def test_nba_and_other_sources_keep_existing_rules():
 from tests.test_devig_observation_oldest_contributor_5661 import _kalshi_pair, FRESH, STALE
 g=_kalshi_pair(FRESH,STALE)
 parent=compute_source_home_probability(g,'Boston Celtics','Golden State Warriors')
 kwargs={} if 'require_current_book_midpoint' not in inspect.signature(compute_source_home_probability).parameters else {'require_current_book_midpoint':True,'current_book_midpoint':lambda ticker:None}
 candidate=compute_source_home_probability(g,'Boston Celtics','Golden State Warriors',**kwargs)
 assert parent.home_probability==candidate.home_probability
 assert parent.contributing_outcomes==candidate.contributing_outcomes

@pytest.mark.asyncio
async def test_real_refresh_keeps_quote_owed_through_absent_book_then_recovers_without_new_input(monkeypatch):
 from sqlalchemy.sql.dml import Update
 g=group();s=socket();r=LiveBlendRefresher('kalshi',min_refresh_interval_s=.25);r.require_current_book_proof=True;r.current_book_midpoint=lambda t:None
 event=NS(id=1,home_team_name='Brooksby',away_team_name='Krueger',status='live',completed_at=None,espn_win_prob_home=None,opening_home_probability=None,win_probability_sources={'kalshi':{'value':.815,'updated_at':(NOW-timedelta(seconds=5)).isoformat()}})
 updates=[]
 class Session:
  async def execute(self,stmt,*args,**kwargs):
   if isinstance(stmt,Update):updates.append(stmt);return NS(first=lambda:({'kalshi':{'value':.82,'updated_at':NOW.isoformat()}},1))
   return NS()
  def add(self,*args):pass
  async def flush(self):pass
 @asynccontextmanager
 async def session():yield Session()
 async def groups(_session,ids):return {1:(event,g)}
 async def snapshot(*args,**kwargs):return None,False
 async def publish(frames):return r._normal_revisions(frames)
 r._session_factory=session;monkeypatch.setattr(r,'_read_groups',groups)
 monkeypatch.setattr('app.tasks.snapshots._create_or_update_win_prob_snapshot',snapshot)
 monkeypatch.setattr(r,'_publish',publish)
 r._normal_closed=True
 await r.refresh([1],flush_started=100)
 assert updates==[] and 1 in r.pending_event_ids()
 r.current_book_midpoint=lookup(s)
 await r.refresh([],flush_started=100.25)
 assert len(updates)==1 and 1 not in r.pending_event_ids()


@pytest.mark.asyncio
async def test_actual_service_ack_gap_resnapshot_departure_and_retire_remove_proof(monkeypatch):
 from contextlib import suppress
 import tests.test_kalshi_direct_book_10090 as rig
 monkeypatch.setattr(rig,'ZVE',H)
 s,run,wire,seen=await rig._service(monkeypatch,{H,A})
 try:
  if not hasattr(s,'current_book_midpoint'):pytest.fail('service has no current book proof')
  assert s.current_book_midpoint(H) is None
  cmd=wire.book_subscribe();await wire.respond(cmd,'subscribed');sid=cmd['id']
  frame=snapshot(H,'.82','.83',1);frame['sid']=sid;await wire.frame(frame)
  assert s.current_book_midpoint(H)==Decimal('.825')
  await wire.frame(rig._delta(9,'.80','1',sid=sid,ticker=H))
  assert s.current_book_midpoint(H) is None
  frame=snapshot(H,'.82','.83',10);frame['sid']=sid;await wire.frame(frame)
  assert s.current_book_midpoint(H)==Decimal('.825')
  await s.set_book_tickers({A});assert s.current_book_midpoint(H) is None
  await s.retire();assert s.current_book_midpoint(A) is None
 finally:
  run.cancel()
  with suppress(asyncio.CancelledError):await run
