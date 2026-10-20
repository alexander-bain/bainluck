from decimal import Decimal
import pytest

from tests import test_bundled_pair_book_proof_10090 as old


def thin(s, value='.12', bid=None, seq=3):
    frame = old.snapshot(old.H, '0', value, seq)
    if bid is None:
        frame['msg']['yes_dollars_fp'] = []
    s._book.apply(frame)
    return s._overlay_ticker({'market_ticker':old.H, 'price_dollars':value})


def read(g,s):
    return old.compute_source_home_probability(
        g,'Brooksby','Krueger',require_current_book_midpoint=True,
        current_book_midpoint=s.current_book_midpoint,
        current_book_primary_price=s.current_book_primary_price)


@pytest.mark.parametrize('damage',['reset','retiring','disconnected','no_socket','unacknowledged','rejected','book_pending','departed','not_requested','wrong_sid','gap','crossed'])
def test_primary_proof_requires_same_live_session_and_healthy_book(damage):
    s=old.socket();thin(s);assert s.current_book_primary_price(old.H)==Decimal('.12')
    if damage=='reset':s._reset_subscription()
    elif damage=='retiring':s._retiring=True
    elif damage=='disconnected':s._connected=False
    elif damage=='no_socket':s._socket=None
    elif damage=='unacknowledged':s._subscribe_pending={1:'ticker'}
    elif damage=='rejected':s._subscribe_rejected={'error':True}
    elif damage=='book_pending':s._book_pending=9
    elif damage=='departed':s.book_tickers=frozenset([old.A])
    elif damage=='not_requested':s._book_requested=frozenset([old.A])
    elif damage=='wrong_sid':s._book_sid=4
    elif damage=='gap':s._book.apply({'type':'orderbook_delta','sid':3,'seq':9,'msg':{'market_ticker':old.H,'side':'yes','price_dollars':'.01','delta_fp':'1'}})
    elif damage=='crossed':s._book.apply(old.snapshot(old.H,'.90','.80',4))
    assert s.current_book_primary_price(old.H) is None


@pytest.mark.parametrize('bid,trade,ask,expected',[
    (None,None,'.12',None),('0',None,'.12','.12'),
    (None,'.12','.12','.12'),(None,'.08','.12',None),
    (None,'.12','.13',None),(None,'.60','.60',None),
    ('0','.12','.12','.12'),('0','.08','.12',None),
])
def test_existing_policy_and_current_ask_both_required(bid,trade,ask,expected):
    s=old.socket();thin(s,ask,bid);s._last_trade.clear()
    if trade is not None:s._overlay_ticker({'market_ticker':old.H,'price_dollars':trade})
    assert s.current_book_midpoint(old.H) is None
    assert s.current_book_primary_price(old.H)==(None if expected is None else Decimal(expected))


@pytest.mark.parametrize('which',['home','away'])
def test_primary_only_proof_never_authorizes_two_contract_average(which):
    s=old.socket();g=old.group();h,a=g[0].outcomes
    if which=='home':
        thin(s,'.12');h.current_probability=Decimal('.12')
        s._book.apply(old.snapshot(old.A,'.86','.88',4));a.current_probability=Decimal('.87')
    else:
        frame=old.snapshot(old.A,'0','.18',3);frame['msg']['yes_dollars_fp']=[];s._book.apply(frame)
        s._overlay_ticker({'market_ticker':old.A,'price_dollars':'.18'});a.current_probability=Decimal('.18')
    r=read(g,s)
    assert not r.devigged and r.home_probability==pytest.approx(float(h.current_probability))
    assert r.contributing_outcomes==(h,)


def test_primary_mismatched_stored_value_refused():
    s=old.socket();thin(s);g=old.group();g[0].outcomes[0].current_probability=Decimal('.10')
    assert read(g,s) is None


@pytest.mark.parametrize('damage',['home_winner','away_winner','home_resolution','away_resolution','event_result'])
def test_terminal_guard_also_applies_to_primary_only_price(damage):
    from dataclasses import replace
    s=old.socket();thin(s);g=old.group();g[0].outcomes[0].current_probability=Decimal('.12')
    if damage=='event_result':g[0]=replace(g[0],event_has_result=True)
    else:
        row=g[0].outcomes[0 if damage.startswith('home') else 1]
        if damage.endswith('winner'):row.is_winner=False
        else:row.resolution_source='kalshi'
    assert read(g,s) is None


@pytest.mark.asyncio
async def test_primary_proof_rechecked_after_budget_await(monkeypatch):
    from sqlalchemy.sql.dml import Update
    from contextlib import asynccontextmanager
    s=old.socket();thin(s);g=old.group();g[0].outcomes[0].current_probability=Decimal('.12')
    r=old.LiveBlendRefresher('kalshi',min_refresh_interval_s=.25)
    r.require_current_book_proof=True;r.current_book_midpoint=s.current_book_midpoint;r.current_book_primary_price=s.current_book_primary_price
    event=old.NS(id=1,home_team_name='Brooksby',away_team_name='Krueger',status='live',completed_at=None,espn_win_prob_home=None,opening_home_probability=None,win_probability_sources={})
    updates=[]
    class Session:
        async def execute(self,stmt,*args,**kwargs):
            if isinstance(stmt,Update):updates.append(stmt)
            s._reset_subscription();return old.NS()
        def add(self,*args):pass
        async def flush(self):pass
    @asynccontextmanager
    async def sessions():yield Session()
    async def groups(*args):return {1:(event,g)}
    r._session_factory=sessions;monkeypatch.setattr(r,'_read_groups',groups)
    await r._refresh_batch([1],0)
    assert not updates and r.stats['errors']==0 and 1 in r.pending_event_ids()


def test_primary_consumer_owner_refuses_conflict_settlement_and_finished_client():
    s=old.socket();thin(s);client=old.NS(sock=s,tickers={old.H},task=old.NS(done=lambda:False));clients=[client];prices=old.NS(settled_market_ids=set())
    f=old.nested('steady_book_primary_price',{'game_clients':clients,'ticker_to_ids':{old.H:(1,11)},'prices':prices})
    assert f(old.H)==Decimal('.12')
    other=old.socket();thin(other,'.13');clients.append(old.NS(sock=other,tickers={old.H},task=old.NS(done=lambda:False)))
    assert f(old.H) is None
    clients.pop();prices.settled_market_ids.add(1);assert f(old.H) is None
    prices.settled_market_ids.clear();client.task=old.NS(done=lambda:True);assert f(old.H) is None
