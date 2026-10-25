"""Original normal-policy ticker custody: no estimator or trade subscription."""
import ast
import asyncio
from pathlib import Path
from types import SimpleNamespace as NS
from datetime import datetime,timezone,timedelta
from contextlib import asynccontextmanager
from decimal import Decimal
import pytest
import app.tasks.kalshi_ws as K
from app.utils.kalshi_primary_quote import PrimaryQuoteCustody
from app.tasks.live_blend_refresh import HeldRowQuotes
from tests.test_kalshi_game_isolation_10655 import rig
from tests import test_bundled_pair_primary_price_10090 as previous
old=previous.old
H,A=old.H,old.A
AT=datetime(2026,10,19,tzinfo=timezone.utc)

def receive(s,value='.08',seq=3):
    frame=old.snapshot(H,'0','.12',seq);frame['msg']['yes_dollars_fp']=[]
    s._book.apply(frame)
    return s._overlay_ticker({'market_ticker':H,'price_dollars':value})

def setup():
    s=old.socket();q=receive(s);c=PrimaryQuoteCustody();c.receive(11,q)
    row=NS(id=11,external_id=H,current_probability=Decimal('.08'),last_updated=AT,is_winner=None,resolution_source=None)
    clients=[NS(sock=s,tickers={H,A},task=NS(done=lambda:False))]
    ns={'game_clients':clients,'ticker_to_ids':{H:(1,11),A:(1,12)},'prices':NS(settled_market_ids=set()),'primary_quote_custody':c}
    f=old.nested('steady_primary_input',ns)
    return s,q,c,row,clients,ns,f


def test_offask_original_receive_is_not_landed_but_actual_returning_proves_it():
    s,q,c,row,clients,ns,f=setup()
    assert s.current_book_primary_price(H) is None and s.current_book_midpoint(H) is None
    assert f(row) is None
    c.committed(c.snapshot([11]),{11:AT+timedelta(seconds=1)})
    assert f(row) is None
    row.last_updated+=timedelta(seconds=1)
    assert f(row)==.08


def test_reset_during_delayed_same_price_commit_does_not_authorize_new_generation():
    s,q,c,row,clients,ns,f=setup();captured=c.snapshot([11])
    s._reset_subscription()
    assert s.current_primary_input(H) is None
    replacement=old.socket();q2=receive(replacement);clients[0].sock=replacement
    assert q2['_primary_quote_identity']!=q['_primary_quote_identity']
    c.receive(11,q2)
    c.committed(captured,{11:AT})
    assert f(row) is None
    c.committed(c.snapshot([11]),{11:AT+timedelta(seconds=1)})
    assert f(row) is None
    row.last_updated+=timedelta(seconds=1);assert f(row)==.08


@pytest.mark.asyncio
async def test_cached_book_callback_reuses_original_and_cannot_create_commit_proof():
    s,q,c,row,clients,ns,f=setup();delivered=[]
    async def callback(value):delivered.append(value)
    class Dispatch:
        async def submit(self,cb,value,*args):await cb(value)
    class WS:
        async def send(self,*args):pass
    s.on_ticker=callback
    frame=old.snapshot(H,'0','.13',4);frame['msg']['yes_dollars_fp']=[]
    await s._handle_book_frame(WS(),frame,Dispatch())
    assert len(delivered)==1
    assert delivered[0]['_primary_quote_identity']==q['_primary_quote_identity']
    c.receive(11,delivered[0]);assert f(row) is None
    c.committed(c.snapshot([11]),{11:AT});assert f(row)==.08
    assert not c.pending(c.snapshot([11]))


@pytest.mark.asyncio
async def test_gap_then_resnapshot_never_revives_old_ticker_identity():
    s,q,c,row,clients,ns,f=setup();c.committed(c.snapshot([11]),{11:AT});assert f(row)==.08
    class WS:
        async def send(self,*args):pass
    class Dispatch:
        async def submit(self,*args):pass
    await s._handle_book_frame(WS(),{'type':'orderbook_delta','sid':3,'seq':9,'msg':{'market_ticker':H,'side':'yes','price_dollars':'.01','delta_fp':'1'}},Dispatch())
    assert f(row) is None and H not in s._primary_inputs
    frame=old.snapshot(H,'0','.12',10);frame['msg']['yes_dollars_fp']=[]
    await s._handle_book_frame(WS(),frame,Dispatch())
    assert f(row) is None
    q2=s._overlay_ticker({'market_ticker':H,'price_dollars':'.08'});c.receive(11,q2)
    assert f(row) is None
    c.committed(c.snapshot([11]),{11:AT});assert f(row)==.08


@pytest.mark.parametrize('damage',['retiring','disconnected','no_socket','unacknowledged','rejected','book_pending','departed','not_requested','wrong_sid','settled_market','finished_client','conflicting_client'])
def test_original_landed_proof_requires_current_owner_and_session(damage):
    s,q,c,row,clients,ns,f=setup();c.committed(c.snapshot([11]),{11:AT});assert f(row)==.08
    if damage=='retiring':s._retiring=True
    elif damage=='disconnected':s._connected=False
    elif damage=='no_socket':s._socket=None
    elif damage=='unacknowledged':s._subscribe_pending={1:'ticker'}
    elif damage=='rejected':s._subscribe_rejected={'error':True}
    elif damage=='book_pending':s._book_pending=9
    elif damage=='departed':s.book_tickers=frozenset([A])
    elif damage=='not_requested':s._book_requested=frozenset([A])
    elif damage=='wrong_sid':s._book_sid=4
    elif damage=='settled_market':ns['prices'].settled_market_ids.add(1)
    elif damage=='finished_client':clients[0].task=NS(done=lambda:True)
    elif damage=='conflicting_client':
        other=old.socket();receive(other);clients.append(NS(sock=other,tickers={H},task=NS(done=lambda:False)))
    assert f(row) is None


@pytest.mark.parametrize('field,value',[('resolution_source','kalshi'),('is_winner',False),('current_probability',.09),('last_updated',AT+timedelta(seconds=1))])
def test_different_row_or_settlement_cannot_borrow_original_identity(field,value):
    s,q,c,row,clients,ns,f=setup();c.committed(c.snapshot([11]),{11:AT});setattr(row,field,value)
    assert f(row) is None


def test_held_membership_without_actual_overlay_or_matching_identity_is_not_proof():
    s,q,c,row,clients,ns,f=setup();held=HeldRowQuotes();bound=(AT+timedelta(seconds=1)).timestamp()
    held.hold({11:(.08,bound)})
    assert f(row,held,overlaid=True) is None
    c.admitted(c.snapshot([11]),{11:(.08,bound)})
    assert f(row,held) is None
    assert f(row,held,overlaid=True) is None # wrong stored observation
    row.last_updated=AT+timedelta(seconds=1)
    assert f(row,held,overlaid=True)==.08
    assert f(row,held) is None # equal stored time is not an overlay
    q2=s._overlay_ticker({'market_ticker':H,'price_dollars':'.08'});c.receive(11,q2)
    assert f(row,held,overlaid=True) is None


def test_original_primary_proof_never_authorizes_complement_average():
    s,q,c,row,clients,ns,f=setup();c.committed(c.snapshot([11]),{11:AT})
    g=old.group();home,away=g[0].outcomes;home.current_probability=Decimal('.08');home.last_updated=AT
    # The other leg has a valid midpoint. The primary has only original-input proof.
    s._book.apply(old.snapshot(A,'.90','.92',4));away.current_probability=Decimal('.91')
    result=old.compute_source_home_probability(g,'Brooksby','Krueger',require_current_book_midpoint=True,current_book_midpoint=s.current_book_midpoint,current_book_primary_price=s.current_book_primary_price,current_primary_input=f)
    assert result.home_probability==.08 and not result.devigged and result.contributing_outcomes==(home,)


def adapted_rig(**kwargs):
    r=rig(**kwargs);r.batch.clear();r.batch[1]=(.08,None,.12)
    for key,val in vars(K).items():r.ns.setdefault(key,val)
    c=PrimaryQuoteCustody();r.ns.update(primary_quote_custody=c,ticker_to_ids={H:(10,1)})
    s=old.socket();q=receive(s)
    return r,c,s,q


@pytest.mark.asyncio
async def test_new_same_price_during_sql_remains_buffered_until_its_own_commit():
    r,c,s,q=adapted_rig(declined=1);c.receive(1,q)
    oldphase=r.ns['prices'].phase;forced=[];injected=False
    async def phase(db,values,**kw):
        nonlocal injected
        forced.append(set(kw['forced_ids']))
        if not injected:
            injected=True;c.receive(1,s._overlay_ticker({'market_ticker':H,'price_dollars':'.08'}));r.batch[1]=(.08,None,.12)
        async for result in oldphase(db,values,**kw):yield result
    r.ns['prices'].phase=phase
    await r.flush();assert 1 in r.batch and not c.landed
    r.control['declined']=None
    await r.flush();assert not r.batch and c.landed[1][0]==c.received[1]
    assert forced==[{1},{1}]
    r.batch[1]=(.08,None,.12);await r.flush();assert forced[-1]==set()


@pytest.mark.asyncio
async def test_settled_decline_drains_without_fabricating_landed_identity():
    r,c,s,q=adapted_rig(declined=1);c.receive(1,q)
    await r.flush();assert not r.batch and not c.landed


@pytest.mark.asyncio
async def test_phase_refresh_captures_original_input_after_initial_snapshot():
    r,c,s,q=adapted_rig();factory=r.ns['get_task_session']
    @asynccontextmanager
    async def sessions():
        async with factory() as db:
            execute=db.execute
            async def wrapped(stmt,bind=None):
                if stmt is K.SET_LOCK_TIMEOUT_SQL:c.receive(1,q)
                return await execute(stmt,bind)
            db.execute=wrapped;yield db
    r.ns['get_task_session']=sessions
    oldphase=r.ns['prices'].phase;forced=[]
    async def phase(db,values,**kw):
        forced.append(set(kw['forced_ids']))
        async for result in oldphase(db,values,**kw):yield result
    r.ns['prices'].phase=phase
    await r.flush();assert forced==[{1}] and not r.batch and c.landed[1][0]==c.received[1]


def test_retention_drops_all_identity_state_outside_current_game_population():
    s,q,c,row,clients,ns,f=setup();c.committed(c.snapshot([11]),{11:AT});c.admitted(c.snapshot([11]),{11:(.08,AT.timestamp())})
    c.retain([]);assert not c.received and not c.landed and not c.held


@pytest.mark.asyncio
async def test_delayed_old_commit_cannot_drain_newer_same_price_identity():
    r,c,s,q=adapted_rig();c.receive(1,q);first=c.snapshot([1])[1]
    oldphase=r.ns['prices'].phase;injected=False
    async def phase(db,values,**kw):
        nonlocal injected
        if not injected:
            injected=True;c.receive(1,s._overlay_ticker({'market_ticker':H,'price_dollars':'.08'}));r.batch[1]=(.08,None,.12)
        async for result in oldphase(db,values,**kw):yield result
    r.ns['prices'].phase=phase
    await r.flush()
    assert 1 in r.batch and c.landed[1][0]==first and c.received[1]!=first
    assert c.pending(c.snapshot([1]))=={1}
    await r.flush()
    assert not r.batch and c.landed[1][0]==c.received[1] and not c.pending(c.snapshot([1]))


@pytest.mark.asyncio
async def test_primary_original_proof_rechecked_after_stamp_budget_await(monkeypatch):
    from sqlalchemy.sql.dml import Update
    s,q,c,row,clients,ns,f=setup();c.committed(c.snapshot([11]),{11:AT})
    g=old.group();g[0].outcomes[0].current_probability=Decimal('.08');g[0].outcomes[0].last_updated=AT
    r=old.LiveBlendRefresher('kalshi',min_refresh_interval_s=.25)
    r.require_current_book_proof=True;r.current_book_midpoint=s.current_book_midpoint;r.current_book_primary_price=s.current_book_primary_price;r.current_primary_input=f
    event=NS(id=1,home_team_name='Brooksby',away_team_name='Krueger',status='live',completed_at=None,espn_win_prob_home=None,opening_home_probability=None,win_probability_sources={})
    updates=[]
    class Session:
        async def execute(self,stmt,*args,**kwargs):
            if isinstance(stmt,Update):updates.append(stmt)
            s._reset_subscription();return NS()
        def add(self,*args):pass
        async def flush(self):pass
    @asynccontextmanager
    async def sessions():yield Session()
    async def groups(*args):return {1:(event,g)}
    r._session_factory=sessions;monkeypatch.setattr(r,'_read_groups',groups)
    await r._refresh_batch([1],0)
    assert not updates and r.stats['errors']==0 and 1 in r.pending_event_ids()


@pytest.mark.parametrize('bid,ask,trade,expected',[
    ('.10','.90','.30',.30), # wide book, interior trade
    (None,None,'.30',.30), # healthy empty book, original trade
    ('.70',None,'.80',.80), # bid-only book
    (None,'.70','.60',.60), # ask above longshot-cap range, actual trade
    (None,'.07','.08',None), # book refutes the trade; ordinary policy skips
    (None,'.70',None,None), # no trade: never invent the ask
])
def test_general_policy_shapes_use_original_provenance_without_policy_change(bid,ask,trade,expected):
    s=old.socket();c=PrimaryQuoteCustody()
    frame={'type':'orderbook_snapshot','sid':3,'seq':3,'msg':{'market_ticker':H,'yes_dollars_fp':[] if bid is None else [[bid,'10']],'no_dollars_fp':[] if ask is None else [[str(Decimal(1)-Decimal(ask)),'10']]}}
    s._book.apply(frame)
    q=s._overlay_ticker({'market_ticker':H,**({} if trade is None else {'price_dollars':trade})})
    c.receive(11,q)
    if expected is None:
        assert s.current_primary_input(H) is None and not c.received
    else:
        assert s.current_book_primary_price(H) is None
        entry=s.current_primary_input(H);assert entry[1]==expected
        row=NS(id=11,current_probability=expected,last_updated=AT,is_winner=None,resolution_source=None)
        assert not c.eligible(row,entry)
        c.committed(c.snapshot([11]),{11:AT});assert c.eligible(row,entry)


@pytest.mark.asyncio
async def test_book_provenance_keeps_exact_trace_on_dispatched_object():
    s,q,c,row,clients,ns,f=setup();traced=[];delivered=[]
    s.exact_trace=NS(derived=lambda original,quote,reason:traced.append(quote))
    async def callback(value):delivered.append(value)
    class Dispatch:
        async def submit(self,cb,value,*args):await cb(value)
    class WS:
        async def send(self,*args):pass
    s.on_ticker=callback
    frame=old.snapshot(H,'0','.13',4);frame['msg']['yes_dollars_fp']=[]
    await s._handle_book_frame(WS(),frame,Dispatch())
    assert len(traced)==len(delivered)==1 and traced[0] is delivered[0]


@pytest.mark.asyncio
async def test_normal_book_frame_does_not_scan_all_primary_tickers():
    s,q,c,row,clients,ns,f=setup()
    class NoIteration(dict):
        def __iter__(self):raise AssertionError('normal book frame scanned primary ticker population')
    s._primary_inputs=NoIteration({**{f'OTHER-{n}':(object(),.5) for n in range(12000)},**s._primary_inputs})
    class WS:
        async def send(self,*args):pass
    class Dispatch:
        async def submit(self,*args):pass
    frame=old.snapshot(H,'0','.13',4);frame['msg']['yes_dollars_fp']=[]
    await s._handle_book_frame(WS(),frame,Dispatch())
    assert len(s._primary_inputs)==12001 and s.current_primary_input(H) is not None


@pytest.mark.asyncio
async def test_gap_arriving_as_snapshot_revokes_even_immediately_rebuilt_ticker():
    s,q,c,row,clients,ns,f=setup();c.committed(c.snapshot([11]),{11:AT});assert f(row)==.08
    class WS:
        async def send(self,*args):pass
    class Dispatch:
        async def submit(self,*args):pass
    frame=old.snapshot(H,'0','.12',9);frame['msg']['yes_dollars_fp']=[]
    await s._handle_book_frame(WS(),frame,Dispatch())
    assert H not in s._book._awaiting and s._current_book_quote(H) is not None
    assert f(row) is None and H not in s._primary_inputs


def test_overlay_classification_keeps_original_rows_alive_until_identity_check():
    import gc,weakref
    import app.tasks.live_blend_refresh as R
    tree=ast.parse(Path(R.__file__).read_text())
    method=next(n for n in ast.walk(tree) if isinstance(n,ast.AsyncFunctionDef) and n.name=='_read_groups')
    start=next(i for i,n in enumerate(method.body) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='original_rows' for t in n.targets))
    # The tail awaits the terminal retirement (F3), so it compiles as a coroutine; no ticket skips that call.
    fn=ast.AsyncFunctionDef(name='attach',args=ast.arguments(posonlyargs=[],args=[ast.arg(arg='self'),ast.arg(arg='grouped'),ast.arg(arg='held'),ast.arg(arg='preview_ticket')],kwonlyargs=[],kw_defaults=[],defaults=[ast.Constant(None)]),body=method.body[start:],decorator_list=[])
    ns={};exec(compile(ast.fix_missing_locations(ast.Module(body=[fn],type_ignores=[])),R.__file__,'exec'),ns)
    class WeakRow(NS):pass
    row=WeakRow(id=11);reference=weakref.ref(row);entry=NS(outcomes=[row]);del row
    replacement=NS(id=11)
    def overlay(entries):
        entries[0].outcomes[:]=[replacement]
        gc.collect()
        assert reference() is not None, 'original row was freed before overlay classification; its object id could be reused'
    grouped={100:(NS(),[entry])}
    asyncio.run(ns['attach'](NS(current_primary_input=lambda *args:None),grouped,NS(overlay_event=overlay)))
    assert replacement._primary_quote_overlaid is True
    assert reference() is None # temporary strong reference ends after classification
