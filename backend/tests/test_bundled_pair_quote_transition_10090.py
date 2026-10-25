import asyncio
from types import SimpleNamespace as NS
from contextlib import asynccontextmanager
from decimal import Decimal
import pytest
import app.tasks.kalshi_ws as K
from app.tasks.kalshi import _kalshi_yes_probability
from app.tasks.live_blend_refresh import LiveBlendRefresher
from app.utils.kalshi_primary_quote import PrimaryQuoteCustody
from tests import test_bundled_pair_primary_quote_10090 as prior
old=prior.old


def consumer(s=None,*,ticker_ids=None,event_ids=None,refresher=None):
    s=s or old.socket();c=PrimaryQuoteCustody();r=refresher or LiveBlendRefresher('kalshi',min_refresh_interval_s=.25)
    ticker_ids=ticker_ids or {old.H:(1,11),old.A:(1,12)}
    event_ids=event_ids or {11:1,12:1}
    clients=[NS(sock=s,tickers=set(ticker_ids),task=NS(done=lambda:False))]
    ns=dict(vars(K));ns['_kalshi_yes_probability']=_kalshi_yes_probability
    ns.update(game_clients=clients,ticker_to_ids=ticker_ids,prices=NS(settled_market_ids=set()),primary_quote_custody=c,tail_receipts=NS(note_raw=lambda *a:None,note_input=lambda *a:None),ticker_owner={},open_contract_ids={},event_id_by_outcome=event_ids,buffer_lock=asyncio.Lock(),price_buffer={},input_marks={},blend_refresher=r,non_blend_outcome_ids=set(),flush_wake=asyncio.Event(),winner_quoted_at={},live_event_ids=set(event_ids.values()),admission_wake=asyncio.Event())
    old.nested('_parse_dollar',ns)
    # Extract the real observation helpers with their shared closure state;
    # default DNPL exercises these on every accepted/refused ticker.
    ns['observation_continuity']={}
    for name in ('steady_book_signature','observation_signature','note_observation_continuity'):
        old.nested(name,ns)
    handle=old.nested('handle_ticker',ns);proof=old.nested('steady_primary_input',ns)
    r.require_current_book_proof=True;r.current_book_midpoint=s.current_book_midpoint;r.current_book_primary_price=s.current_book_primary_price;r.current_primary_input=proof
    return s,c,r,handle,proof,ns


async def book(s,frame,handle):
    delivered=[]
    async def callback(q):delivered.append(q);await handle(q)
    class Dispatch:
        async def submit(self,cb,q,*args):await cb(q)
    class WS:
        async def send(self,*args):pass
    s.on_ticker=callback
    await s._handle_book_frame(WS(),frame,Dispatch())
    return delivered


@pytest.mark.asyncio
async def test_real_book_transition_reaches_actual_consumer_selector_and_refresher(monkeypatch):
    from sqlalchemy.sql.dml import Update
    s,c,r,handle,proof,ns=consumer()
    await handle(s._overlay_ticker({'market_ticker':old.H,'price_dollars':'.83'}))
    assert ns['price_buffer'][11][0]==.825
    c.committed(c.snapshot([11]),{11:old.NOW})
    delivered=await book(s,old.snapshot(old.H,'.20','.90',3),handle)
    assert len(delivered)==1 and ns['price_buffer'][11][0]==.83
    g=old.group();h=g[0].outcomes[0];h.current_probability=Decimal('.83');h.last_updated=old.NOW
    assert proof(h) is None # equality before the new quote lands is insufficient
    c.committed(c.snapshot([11]),{11:old.NOW})
    reading=old.compute_source_home_probability(g,'Brooksby','Krueger',require_current_book_midpoint=True,current_book_midpoint=s.current_book_midpoint,current_book_primary_price=s.current_book_primary_price,current_primary_input=proof)
    assert reading is not None and reading.home_probability==.83 and not reading.devigged
    event=NS(id=1,home_team_name='Brooksby',away_team_name='Krueger',status='live',completed_at=None,espn_win_prob_home=None,opening_home_probability=None,win_probability_sources={})
    updates=[];frames=[]
    class Session:
        async def execute(self,stmt,*args,**kwargs):
            if isinstance(stmt,Update):
                updates.append(stmt);return NS(first=lambda:({'kalshi':{'value':.83,'updated_at':old.NOW.isoformat()}},1))
            return NS(scalar_one_or_none=lambda:None)
        def add(self,*args):pass
        async def flush(self):pass
    @asynccontextmanager
    async def sessions():yield Session()
    async def groups(*args):return {1:(event,g)}
    async def snapshot(*args,**kwargs):return None,False
    async def publish(accepted):frames.extend(accepted)
    r._session_factory=sessions;monkeypatch.setattr(r,'_read_groups',groups)
    monkeypatch.setattr('app.tasks.snapshots._create_or_update_win_prob_snapshot',snapshot)
    await r._refresh_batch([1],0,publish_committed=publish)
    assert len(updates)==1 and len(frames)==1 and r.stats['errors']==0 and r.stats['no_reading']==0


@pytest.mark.asyncio
@pytest.mark.parametrize("bid,ask",[(".82",".83"),(".81",".83")])
async def test_unchanged_tight_book_tickers_do_not_force_observations(bid,ask):
    r,c,s,q=prior.adapted_rig();selected=(float(bid)+float(ask))/2;r.batch[1]=(selected,float(bid),float(ask));r.ns['prices'].committed_outcome_ids.add(1)
    s=old.socket();s._book.apply(old.snapshot(old.H,bid,ask,3));oldphase=r.ns['prices'].phase;forced=[]
    async def phase(db,values,**kw):
        forced.append(set(kw['forced_ids']))
        async for result in oldphase(db,values,**kw):yield result
    r.ns['prices'].phase=phase
    for _ in range(3):
        c.receive(1,s._overlay_ticker({'market_ticker':old.H,'price_dollars':'.83'}))
        r.batch[1]=(selected,float(bid),float(ask))
        await r.flush()
    assert forced==[set(),set(),set()]


@pytest.mark.asyncio
async def test_repeated_book_callbacks_keep_same_fallback_evidence_after_landing():
    s,c,r,handle,proof,ns=consumer()
    await handle(s._overlay_ticker({'market_ticker':old.H,'price_dollars':'.83'}))
    first=await book(s,old.snapshot(old.H,'.20','.90',3),handle)
    captured=c.snapshot([11]);assert captured[11] is not None
    c.committed(captured,{11:old.NOW})
    second=await book(s,old.snapshot(old.H,'.10','.95',4),handle)
    assert first[0]['_primary_quote_identity']==second[0]['_primary_quote_identity']
    assert not c.pending(c.snapshot([11]))


@pytest.mark.asyncio
async def test_post_gap_current_snapshot_requires_new_accepted_observation():
    s,c,r,handle,proof,ns=consumer()
    await handle(s._overlay_ticker({'market_ticker':old.H,'price_dollars':'.83'}))
    await book(s,old.snapshot(old.H,'.20','.90',3),handle)
    c.committed(c.snapshot([11]),{11:old.NOW})
    row=NS(id=11,external_id=old.H,current_probability=Decimal('.83'),last_updated=old.NOW,is_winner=None,resolution_source=None)
    assert proof(row)==.83
    before=c.snapshot([11])
    await book(s,old.snapshot(old.H,'.10','.95',9),handle)
    assert c.snapshot([11])!=before and proof(row) is None
    c.committed(c.snapshot([11]),{11:old.NOW});assert proof(row)==.83


@pytest.mark.asyncio
async def test_policy_transition_after_reset_cannot_reuse_prior_trade():
    s,c,r,handle,proof,ns=consumer()
    await handle(s._overlay_ticker({'market_ticker':old.H,'price_dollars':'.83'}))
    s._reset_subscription()
    replacement=old.socket();ns['game_clients'][0].sock=replacement
    delivered=await book(replacement,old.snapshot(old.H,'.20','.90',3),handle)
    assert replacement._last_trade=={}
    assert not c.pending(c.snapshot([11]))
    assert '_primary_quote_identity' not in delivered[0]


def test_unrelated_wide_book_market_does_not_acquire_forced_quote_custody():
    from app.utils.kalshi_orderbook import KalshiOrderBook
    s=old.socket();ticker='KXNBAGAME-26OCT20BOSGSW-BOS'
    s.book_tickers=s._book_requested=frozenset([ticker]);s._book=KalshiOrderBook()
    s._book.apply(old.snapshot(ticker,'.20','.90',1))
    q=s._overlay_ticker({'market_ticker':ticker,'price_dollars':'.83'})
    assert s._primary_policy_price(q)==.83
    assert '_primary_quote_identity' not in q and not s._primary_inputs
