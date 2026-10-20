"""#10090 — K1: an unheld bundled sibling committed after a held leg's frozen bound refuses the mixed overlay (attempt177, real PostgreSQL row lock).

Ported from the reviewed attempt190 packet onto the 8129 per-test schema rig.
"""
import tempfile
from pathlib import Path
from datetime import timedelta
from types import SimpleNamespace as NS
import pytest
from sqlalchemy import select, update, func, text
from app.models.models import Sport, Event, FuturesMarket, FuturesOutcome
from app.tasks.live_blend_refresh import HeldRowQuotes, LiveBlendRefresher
from app.utils.live_blend import MarketOutcomes, compute_source_home_probability
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


P='KXATPCHALLENGERMATCH-26OCT19BROKRU'

@pytest.mark.asyncio
async def test_K1_open_away_lock_and_separate_committed_home_refuse_held_quote(rig):
    maker=rig.maker
    try:
        async with maker() as db:
            now=await db.scalar(select(func.clock_timestamp()))
            sport=Sport(key='local177',name='Local177');db.add(sport);await db.flush()
            ev=Event(sport_id=sport.id,home_team_name='Jenson Brooksby',away_team_name='Mitchell Krueger',status='live',commence_time=now-timedelta(hours=1),win_probability_sources={})
            db.add(ev);await db.flush()
            m=FuturesMarket(sport_id=sport.id,event_id=ev.id,source='kalshi',external_id=P,name='Brooksby vs Krueger',category='game',status='open',market_metadata={})
            db.add(m);await db.flush()
            h=FuturesOutcome(market_id=m.id,external_id=P+'-BRO',name=ev.home_team_name,current_probability=.60,rank=1,last_updated=now-timedelta(seconds=2))
            a=FuturesOutcome(market_id=m.id,external_id=P+'-KRU',name=ev.away_team_name,current_probability=.40,rank=2,last_updated=now-timedelta(seconds=2))
            db.add_all([h,a]);await db.flush();eid,hid,aid=ev.id,h.id,a.id
            await db.execute(update(FuturesOutcome).where(FuturesOutcome.id.in_([hid,aid])).values(is_winner=None))
            await db.commit()
        async with maker() as holder:
            await holder.execute(select(FuturesOutcome.id).where(FuturesOutcome.id==aid).with_for_update())
            holder_pid=await holder.scalar(select(func.pg_backend_pid()))
            bound=(await holder.scalar(select(func.clock_timestamp()))).timestamp()
            held=HeldRowQuotes();held._quotes[aid]=(.42,bound)
            async with maker() as writer:
                writer_pid=await writer.scalar(select(func.pg_backend_pid()))
                assert writer_pid != holder_pid
                await writer.execute(update(FuturesOutcome).where(FuturesOutcome.id==hid).values(current_probability=.58,last_updated=func.clock_timestamp()))
                await writer.commit()
            # Prove the away transaction still owns its lock after home commit.
            async with maker() as probe:
                await probe.execute(text("SET LOCAL lock_timeout = '1ms'"))
                with pytest.raises(Exception) as caught:
                    await probe.execute(select(FuturesOutcome.id).where(FuturesOutcome.id==aid).with_for_update())
                assert getattr(caught.value.orig,'sqlstate',None)=='55P03'
                await probe.rollback()
            refresher=LiveBlendRefresher('kalshi');refresher.held_quotes=held
            async with maker() as reader:
                event,groups=(await refresher._read_groups(reader,[eid]))[eid]
            prices={o.id:float(o.current_probability) for g in groups for o in g.outcomes}
            assert prices[hid]==pytest.approx(.58)
            assert prices[aid]==pytest.approx(.40), 'older held away overrode a snapshot with a newer committed home'
            assert compute_source_home_probability(groups,event.home_team_name,event.away_team_name).home_probability==pytest.approx(.59)
            assert holder.in_transaction()
            await holder.rollback()
    finally:
        pass


def entries(ticker=P,home_stamp=98,away_stamp=98):
    from datetime import datetime,timezone
    def row(i,name,p,t):return NS(id=i,name=name,current_probability=p,last_updated=datetime.fromtimestamp(t,timezone.utc))
    m=NS(id=1,source='kalshi',external_id=ticker)
    return [MarketOutcomes(m,[row(11,'Jenson Brooksby',.60,home_stamp),row(12,'Mitchell Krueger',.40,away_stamp)])]

@pytest.mark.parametrize('home_stamp,expected',[(98,.42),(100,.40),(101,.40)])
def test_bundled_sibling_bound(home_stamp,expected):
    g=entries(home_stamp=home_stamp);h=HeldRowQuotes();h._quotes[12]=(.42,100)
    h.overlay_event(g)
    assert g[0].outcomes[1].current_probability==expected

def test_whole_held_pair_still_admitted():
    g=entries();h=HeldRowQuotes();h._quotes={11:(.58,100),12:(.42,100)}
    h.overlay_event(g)
    assert [o.current_probability for o in g[0].outcomes]==[.58,.42]

def test_separate_NBA_markets_preserve_existing_behavior():
    g=entries(ticker='KXNBAGAME-26OCT19BOSNYK-BOS',home_stamp=101)
    away=g[0].outcomes.pop()
    g.append(MarketOutcomes(NS(id=2,source='kalshi',external_id='KXNBAGAME-26OCT19BOSNYK-NYK'),[away]))
    h=HeldRowQuotes();h._quotes[12]=(.42,100);h.overlay_event(g)
    assert g[1].outcomes[0].current_probability==.42

def test_nonspeaking_prop_newer_than_bound_does_not_refuse():
    g=entries();extra=entries(ticker='KXATPSETWINNER-26OCT19BROKRU-S1',home_stamp=101,away_stamp=101)[0]
    for o in extra.outcomes:o.id+=10
    g.append(extra);h=HeldRowQuotes();h._quotes[12]=(.42,100);h.overlay_event(g)
    assert g[0].outcomes[1].current_probability==.42
