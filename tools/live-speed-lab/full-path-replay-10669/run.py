"""PILLAR TRUTH/FORMATTING; SHIP: a venue quote reaches one coherent live hero/chart.
Private, synthetic protocol replay; one invocation owns and removes all servers.
"""
from __future__ import annotations
import argparse, asyncio, contextlib, fcntl, hashlib, json, os, shutil, signal, socket, subprocess, sys, tarfile, tempfile, time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from fastapi import Request
OUT=Path(__file__).resolve().parent
REPO=OUT.parents[2]
PIN='c5923961027e9cff8140a57f6adf3f24cb420450'
QUIET_PAIR=('416d7bd94d185cc9fb704f00b960d40b47e83e47','e020191be2970e1de4718b029a46b721138feccd')

class Inconclusive(RuntimeError):
 pass

def resolve_application_ref(ref):
 return subprocess.check_output(['git','-C',str(REPO),'rev-parse','--verify','--end-of-options',ref+'^{commit}'],text=True,timeout=10).strip()

def matches_target(frame,event_id,revision,probability):
 return frame.get('event_id')==event_id and frame.get('rev')=={str(event_id):revision} and frame.get('p')==probability

def affected_batch_error(batch,event_map,pending,live,expected,quiet,target):
 if set(batch)!=set(expected):return 'accepted burst did not remain one complete causal batch'
 if set(pending)!={quiet}:return 'quiet debt missing or mixed with buffered-event debt'
 if quiet in {event_map.get(oid) for oid in batch}:return 'quiet debt overlaps batch'
 if target not in live:return 'target not admitted as Live'
 if any(event_map.get(oid) is None for oid in batch):return 'unknown event membership'
 return None

def parity_signature(state):
 # Database-assigned IDs are deterministic in the fresh identical fixture.
 return {'all_prices':state['all_prices'],'snapshots':state['snapshots'],'all_events':[{'id':e['id'],'p':e['p'],'rev':e['rev'],'source_values':{k:v.get('value') if isinstance(v,dict) else v for k,v in e['sources'].items()}} for e in state['all_events']]}

def fixture_parity_error(state,expected_prices,expected_events):
 if len(state['all_prices'])!=36 or len(state['all_events'])!=18:return 'finite fixture rows missing'
 for row in state['all_prices']:
  if row[0] not in expected_prices or abs(float(row[1])-expected_prices[row[0]])>1e-5:return 'final fixture price parity failed'
  if row[3] is not None or row[4] is not None:return 'unsettled fixture became resolved'
 for event in state['all_events']:
  if event['id'] not in expected_events or abs(event['p']-expected_events[event['id']])>1e-5:return 'final event blend parity failed'
  if event['rev']<1 or set(event['sources'])!={'kalshi'}:return 'missing event revision/source'
 return None

PG=Path('/opt/homebrew/opt/postgresql@17/bin')
CONTRACT=Path('/Users/bain/bainluck/artifacts/discovery-containers-release-plan/live-speed-progress/15326313-delivery-diagnosis/kalshi-event.json')

def dump(p,x): p.write_text(json.dumps(x,indent=2,default=str)+'\n')
def utc(): return datetime.now(timezone.utc).isoformat()
def stamp(): return {'at':utc(),'monotonic_s':time.monotonic()}
def port():
 with socket.socket() as s:
  s.bind(('127.0.0.1',0)); return s.getsockname()[1]

def group_exists(pgid):
 try:os.killpg(pgid,0);return True
 except ProcessLookupError:return False

def stop_owned_group(process,grace=5):
 """The leader may exit before its browser descendants: prove group absence."""
 for sig in (signal.SIGTERM,signal.SIGKILL):
  if group_exists(process.pid):
   with contextlib.suppress(ProcessLookupError):os.killpg(process.pid,sig)
  try:process.wait(timeout=grace)
  except subprocess.TimeoutExpired:pass
  deadline=time.monotonic()+grace
  while group_exists(process.pid) and time.monotonic()<deadline:time.sleep(.025)
  if not group_exists(process.pid):
   process.wait(timeout=grace)
   return
 raise RuntimeError(f'owned process group {process.pid} still present after SIGKILL')

def cleanup_owned(temp,worker,redis_process,lock):
 # A work-deadline alarm or repeated termination must not skip later resources.
 signal.alarm(0)
 previous_term=signal.signal(signal.SIGTERM,signal.SIG_IGN)
 errors=[];checks={}
 def attempt(name,operation):
  try:return operation()
  except BaseException as error:errors.append({'resource':name,'error':repr(error)})
 try:
  if worker:attempt('worker_group',lambda:stop_owned_group(worker))
  if redis_process:attempt('redis_group',lambda:stop_owned_group(redis_process))
  pidfile=temp/'pg/postmaster.pid'
  if pidfile.exists():
   attempt('postgres',lambda:subprocess.run([str(PG/'pg_ctl'),'-D',str(temp/'pg'),'-m','immediate','-w','stop'],stdout=subprocess.DEVNULL,check=True,timeout=30))
  def private_processes():
   rows=subprocess.check_output(['ps','-axww','-o','pid=,command='],text=True,timeout=5).splitlines()
   return [row for row in rows if str(temp) in row]
  # Preserve a failed database's directory for a bounded owner cleanup; do not
  # erase the data files of an owned process that could still be running.
  def remove_temp():
   if (worker is not None and group_exists(worker.pid)) or (redis_process is not None and group_exists(redis_process.pid)):
    raise RuntimeError('owned process group remains; preserving temporary root')
   remaining=private_processes()
   if remaining:raise RuntimeError('private processes remain: '+repr(remaining))
   shutil.rmtree(temp)
  attempt('temporary_root',remove_temp)
  if lock:
   attempt('benchmark_unlock',lambda:fcntl.flock(lock,fcntl.LOCK_UN))
   attempt('benchmark_close',lock.close)
  def verify():
   checks.update(worker_group_absent=worker is None or not group_exists(worker.pid),redis_group_absent=redis_process is None or not group_exists(redis_process.pid),private_processes=private_processes(),temporary_root_absent=not temp.exists(),lock_closed=lock is None or lock.closed)
  attempt('absence_verification',verify)
 finally:signal.signal(signal.SIGTERM,previous_term)
 stopped=not errors and checks.get('worker_group_absent') and checks.get('redis_group_absent') and not checks.get('private_processes') and checks.get('temporary_root_absent') and checks.get('lock_closed')
 return {'stopped':bool(stopped),'cleanup_errors':errors,'cleanup_checks':checks}

async def replay(tree,output,url,redis_url,http_port,application_ref=PIN,quiet_debt=False,history_hold=False):
 import aiohttp, uvicorn, websockets
 from fastapi import FastAPI, Request
 from fastapi.responses import FileResponse
 from sqlalchemy import select,event as sql_event,text
 from sqlalchemy.ext.asyncio import async_sessionmaker
 from app.models.models import Base,Event,FuturesMarket,FuturesOutcome,Sport,WinProbSnapshot
 from app.services import database
 from app.tasks.base import get_task_session
 from app.tasks import base as task_base
 from app.tasks import kalshi_ws as consumer
 from app.tasks import live_blend_refresh as blend
 from app.services import kalshi_ws as service
 from app.routes import events,event_stream,market_stream,feed
 from app.utils import aggregation,live_fanout
 engine=task_base._get_task_engine()
 maker=async_sessionmaker(engine,expire_on_commit=False)
 receipt={'source_pin':application_ref,'quiet_debt_comparison':quiet_debt,'started_at':utc(),'started_monotonic_s':time.monotonic(),'synthetic_protocol':True,'inputs':[],'accepted':[],'price_commits':[],'publish_calls':[],'api':[],'errors':[]}
 dump(output/'receipt.json',receipt)
 async with engine.begin() as conn: await conn.run_sync(Base.metadata.create_all)
 if quiet_debt:
  # Same finite relational shape as the paid #10728 control, no delay hooks.
  now=datetime.now(timezone.utc); fixture_events=[];fixture_markets=[];fixture_legs=[]
  async with maker() as db:
   sport=Sport(key='tennis_atp',name='ATP Tennis');db.add(sport);await db.flush()
   for i in range(18):
    ev=Event(sport_id=sport.id,home_team_name=f'Home{i}',away_team_name=f'Away{i}',status='live' if i==16 else 'scheduled',commence_time=now-timedelta(minutes=5) if i==16 else now+timedelta(minutes=30),commence_time_source='schedule',win_probability_sources={},opening_home_probability=.5)
    db.add(ev);fixture_events.append(ev)
   await db.flush()
   for i,ev in enumerate(fixture_events):
    market=FuturesMarket(sport_id=sport.id,event_id=ev.id,external_id=f'KXATPCHALLENGERDOUBLES-26OCT07LAB{i}',source='kalshi',name=f'Home{i} vs Away{i}',category='game',status='open',mutually_exclusive=True)
    db.add(market);fixture_markets.append(market)
   await db.flush()
   for i,market in enumerate(fixture_markets):
    pair=[]
    for j,p0 in enumerate((.54,.46) if i==17 else (.5,.5)):
     leg=FuturesOutcome(market_id=market.id,external_id=market.external_id+('-HOME' if j==0 else '-AWAY'),name=f'Home{i}' if j==0 else f'Away{i}',current_probability=p0,rank=j+1,last_updated=now)
     db.add(leg);pair.append(leg)
    fixture_legs.append(pair)
   await db.commit()
  E=fixture_events[16].id;M=fixture_markets[16].id;H=fixture_legs[16][0].id;A=fixture_legs[16][1].id;Q=fixture_events[17].id
 else:
  # Preserve the original single-contract fixture and controls.
  import importlib.util
  spec=importlib.util.spec_from_file_location('mixed_seed',REPO/'tools/live-speed-lab/mixed-writer-10669/kalshi-fixture.py')
  fixture=importlib.util.module_from_spec(spec); spec.loader.exec_module(fixture)
  ids=await fixture._seed(maker)
  E=ids['events']['a']; M=ids['markets']['a']; H=ids['legs']['a1']; A=ids['legs']['a2']
 ticker='KXATPCHALLENGERDOUBLES-26OCT07BARVOCMARWAL'
 async with maker() as db:
  ev=await db.get(Event,E); ev.home_team_name='Barrientos / Vocel';ev.away_team_name='Martos Gornes / Walkow';ev.commence_time=datetime.now(timezone.utc)-timedelta(minutes=5);ev.commence_time_source='schedule';ev.opening_home_probability=.68
  sport=await db.get(Sport,ev.sport_id);sport.key='tennis_atp';sport.name='ATP Tennis'
  market=await db.get(FuturesMarket,M);market.external_id=ticker;market.name='Barrientos / Vocel vs Martos Gornes / Walkow';market.category='game';market.status='open';market.mutually_exclusive=True
  for oid,name,suffix,p in [(H,'Nicolas Barrientos / Matej Vocel','BARVOC',.68),(A,'Sergio Martos Gornes / Szymon Walkow','MARWAL',.315)]:
   leg=await db.get(FuturesOutcome,oid);leg.name=name;leg.external_id=ticker+'-'+suffix;leg.current_probability=p;leg.last_updated=datetime.now(timezone.utc)
  # Keep unrelated fixture companions out of the consumer's slate for this one contract.
  for name in ([] if quiet_debt else ['b']):
   evb=await db.get(Event,ids['events'][name]);evb.status='scheduled';evb.commence_time=datetime.now(timezone.utc)+timedelta(days=2)
  for minutes,p in [(4,.65),(2,.68)]:
   db.add(WinProbSnapshot(event_id=E,source='kalshi',captured_at=datetime.now(timezone.utc)-timedelta(minutes=minutes),home_win_probability=p,away_win_probability=1-p,valid_until=datetime.now(timezone.utc)))
  await db.commit()
 if quiet_debt:
  burst=[(leg.external_id,leg.id,.62 if j==0 else .38) for pair in fixture_legs[:16] for j,leg in enumerate(pair)]
  burst.extend([(ticker+'-MARWAL',A,.26),(ticker+'-BARVOC',H,.74)])
  expected_oids={oid for _,oid,_ in burst}
  fixture_event_ids={ev.id for ev in fixture_events};fixture_market_ids={m.id for m in fixture_markets}
  receipt['fixture']={'events':18,'active_games':17,'quiet_event':Q,'target_event':E,'quoted_rows':34,'stored_rows':36,'quiet_stored_prices':[.54,.46],'input_order':burst}
 database.async_session_maker=maker;market_stream.async_session_maker=maker;event_stream.async_session_maker=maker
 @contextlib.asynccontextmanager
 async def sessions():
  async with get_task_session(engine=engine) as s: yield s
 # No alternate price/blend math; only private session/Redis factories and transport endpoint.
 refresher=blend.LiveBlendRefresher('kalshi',session_factory=sessions,min_refresh_interval_s=0,snapshot_interval_s=0)
 await refresher.refresh([E])
 if hasattr(refresher,'drain_history'): await refresher.drain_history()
 if refresher._redis: await refresher._redis.aclose()
 async def get_db():
  async with maker() as db: yield db
 app=FastAPI()
 app.include_router(event_stream.router,prefix='/api/events')
 app.include_router(events.router,prefix='/api/events')
 app.include_router(market_stream.router,prefix='/api/markets')
 app.include_router(feed.router,prefix='/api')
 app.dependency_overrides[database.get_db]=get_db
 mode={'drop':False,'control':False,'label':'setup'}
 # One deliberately blocked real history helper; all SQL still runs on release.
 # This isolates ownership, not production lock duration or throughput.
 from app.tasks import snapshots
 original_snapshot=snapshots._create_or_update_win_prob_snapshot
 history_entered=asyncio.Event()
 async def held_snapshot(*args,**kwargs):
  if history_hold and kwargs.get('event_id')==E and abs(kwargs.get('home_win_probability',0)-.71)<1e-6 and not history_entered.is_set():
   receipt['history_hold']={'entered':stamp(),'seconds':4,'kind':'synthetic async wait before forwarding real snapshot helper'}
   history_entered.set()
   try: await asyncio.sleep(4)
   finally: receipt['history_hold']['released']=stamp()
  return await original_snapshot(*args,**kwargs)
 if history_hold: snapshots._create_or_update_win_prob_snapshot=held_snapshot
 captured={};accepted_burst=set();affected=[]
 receipt['qualification_errors']=[];receipt['plans']=[];receipt['flushes']=[];receipt['committed_publication_checks']=[]
 original_cadence=blend.run_flush_cadence
 original_planner=consumer.linked_first_phases
 if quiet_debt:
  async def observe_cadence(flush,*args,**kwargs):
   closure=dict(zip(flush.__code__.co_freevars,[c.cell_contents for c in flush.__closure__ or ()]))
   inner=closure.get('flush_prices',flush)
   closure=dict(zip(inner.__code__.co_freevars,[c.cell_contents for c in inner.__closure__ or ()]))
   if not {'price_buffer','blend_refresher','stats'}<=closure.keys():raise Inconclusive('unsupported existing flush observer closure')
   captured.update(closure)
   async def observed(started):
    record={**stamp(),'cadence_started':started,'batch_before':list(closure['price_buffer']),'pending_before':sorted(closure['blend_refresher'].pending_event_ids())};receipt['flushes'].append(record)
    try:return await flush(started)
    finally:record.update(finished=stamp(),buffer_after=list(closure['price_buffer']),pending_after=sorted(closure['blend_refresher'].pending_event_ids()))
   return await original_cadence(observed,*args,**kwargs)
  def observe_plan(batch,market_map,event_map,pending_events=(),live_events=None):
   phases=original_planner(batch,market_map,event_map,pending_events,live_events=live_events)
   record={**stamp(),'batch':list(batch),'pending':sorted(pending_events),'live':sorted(live_events or ()),'phases':[list(p) for p in phases]};receipt['plans'].append(record)
   if mode['label']=='normal' and Q in pending_events and not affected:
    error=affected_batch_error(batch,event_map,pending_events,live_events or (),expected_oids,Q,E)
    if any(market_map.get(oid) is None for oid in batch):error='unknown market membership'
    if application_ref==QUIET_PAIR[0] and [set(p) for p in phases]!=[expected_oids]:error='parent did not retain the complete joined game phase'
    if application_ref==QUIET_PAIR[1] and (not phases or set(phases[0])!={H,A}):error='candidate did not put the complete Live game first'
    if error:receipt['qualification_errors'].append(error)
    affected.append(record)
   return phases
  blend.run_flush_cadence=observe_cadence;consumer.linked_first_phases=observe_plan
 original_publish=blend.LiveBlendRefresher._publish
 original_market=blend.LiveBlendRefresher.publish_market_changes
 async def observe_publish(self,frames):
  publication={**stamp(),'frames':frames,'intentionally_dropped':mode['drop'],'buffer':list(captured.get('price_buffer',{}))};receipt['publish_calls'].append(publication)
  if not mode['drop']: await original_publish(self,frames)
  publication['publication_return']=stamp()
  # Verify before crediting, AFTER forwarding publication: do not add observer
  # queries ahead of the target Redis delivery. This is not exact commit time.
  if quiet_debt and frames:
   async with maker() as db:
    committed_rows={ev.id:ev for ev in (await db.execute(select(Event).where(Event.id.in_([f['event_id'] for f in frames])))).scalars()}
    for frame in frames:
     ev=committed_rows[frame['event_id']]
     ok=frame['rev']=={str(ev.id):ev.win_probability_sources_rev} and abs(aggregation.compute_aggregate_probability(ev,ev.status)-frame['p'])<1e-5
     receipt['committed_publication_checks'].append({'event_id':ev.id,'rev':frame['rev'],'p':frame['p'],'passed':ok})
     if not ok:receipt['qualification_errors'].append('publication does not match independent committed row')
 async def observe_market(self,db):
  if mode['drop']:
   receipt.setdefault('dropped_market_signals',0);receipt['dropped_market_signals']+=1
   return 0
  return await original_market(self,db)
 blend.LiveBlendRefresher._publish=observe_publish;blend.LiveBlendRefresher.publish_market_changes=observe_market
 original_note=blend.TailReceipts.note_input
 def note(self,*args,**kw):
  mark=original_note(self,*args,**kw);receipt['accepted'].append({**stamp(),'args':args,'mark':str(mark),'recv_mono':getattr(mark,'recv_mono',None),'label':mode['label']})
  if quiet_debt and mode['label']=='normal':
   if mark is None:
    receipt['qualification_errors'].append('accepted quote had no linked input mark');return mark
   accepted_burst.add(mark.outcome_id)
   if accepted_burst==expected_oids and 'debt_adopted' not in receipt:
    if 'blend_refresher' not in captured:receipt['qualification_errors'].append('consumer refresher was not captured')
    else:
     captured['blend_refresher'].adopt_pending([Q])
     receipt['debt_adopted']={**stamp(),'event_id':Q,'pending':sorted(captured['blend_refresher'].pending_event_ids()),'buffer':list(captured['price_buffer'])}
  return mark
 blend.TailReceipts.note_input=note
 def committed(db):
  receipt['price_commits'].append({'at':utc(),'drop':mode['drop']})
 sql_event.listen(__import__('sqlalchemy').orm.Session,'after_commit',committed)
 @app.middleware('http')
 async def log(request,call_next):
  response=await call_next(request);receipt['api'].append({'at':utc(),'path':request.url.path,'query':str(request.url.query),'status':response.status_code});return response
 @app.get('/')
 async def page(): return FileResponse(output/'index.html')
 @app.post('/lab/visible')
 async def visible(request:Request):
  receipt['render_ack']={**stamp(),'view':await request.json()}
  return {'received':True}
 @app.get('/env.js')
 async def env():
  from fastapi.responses import Response
  return Response('window.process={env:{}};',media_type='application/javascript')
 @app.get('/bundle.js')
 async def bundle(): return FileResponse(output/'bundle.js')
 @app.get('/style.css')
 async def css(): return FileResponse(output/'style.css')
 @app.get('/{name}.js')
 async def chunk(name:str): return FileResponse(output/(name+'.js'))
 frames=asyncio.Queue()
 ws_ready=asyncio.Event()
 async def provider(ws):
  # Actual service sends normal subscription commands to this private protocol peer.
  for _ in range(2):
   cmd=json.loads(await ws.recv());receipt.setdefault('subscriptions',[]).append(cmd)
   await ws.send(json.dumps({'type':'subscribed','msg':{'channel':cmd['params']['channels'][0]}}))
  ws_ready.set()
  while True:
   incoming=asyncio.create_task(frames.get());closed=asyncio.create_task(ws.wait_closed())
   try:
    done,_=await asyncio.wait([incoming,closed],return_when=asyncio.FIRST_COMPLETED)
    if closed in done:return
    frame=incoming.result();receipt['inputs'].append({**stamp(),'frame':frame,'label':mode['label']});await ws.send(json.dumps(frame))
   finally:
    incoming.cancel();closed.cancel();await asyncio.gather(incoming,closed,return_exceptions=True)
 provider_port=port()
 service.WS_URL=f'ws://127.0.0.1:{provider_port}'
 service.KalshiWebSocket._ensure_key=lambda self:None
 service._sign_ws_request=lambda *a:{}
 # Synthetic sentinels satisfy only consumer's presence check; no signing/secret access.
 os.environ['KALSHI_API_KEY_ID']='LOCAL_SYNTHETIC_NO_KEY';os.environ['KALSHI_RSA_PRIVATE_KEY']='LOCAL_SYNTHETIC_NO_KEY'
 consumer._report_liveness=lambda *a,**kw:None
 # Consumer imports its reporter inside the function.
 import app.tasks.ws_liveness as liveness
 liveness.report=lambda *a,**kw:None
 config=uvicorn.Config(app,host='127.0.0.1',port=http_port,log_level='warning',access_log=False)
 server=uvicorn.Server(config)
 api_task=asyncio.create_task(server.serve())
 writer=None;browser=None
 async def state(full=True):
  async with maker() as db:
   ev=await db.get(Event,E)
   prices=(await db.execute(select(FuturesOutcome.id,FuturesOutcome.current_probability,FuturesOutcome.rank).where(FuturesOutcome.market_id==M))).all()
   extra={}
   if quiet_debt and full:
    all_prices=(await db.execute(select(FuturesOutcome.id,FuturesOutcome.current_probability,FuturesOutcome.rank,FuturesOutcome.is_winner,FuturesOutcome.resolution_source).where(FuturesOutcome.market_id.in_(fixture_market_ids)).order_by(FuturesOutcome.id))).all()
    all_events=(await db.execute(select(Event).where(Event.id.in_(fixture_event_ids)).order_by(Event.id))).scalars().all()
    snapshots=(await db.execute(select(WinProbSnapshot.event_id,WinProbSnapshot.source,WinProbSnapshot.home_win_probability,WinProbSnapshot.away_win_probability).where(WinProbSnapshot.event_id.in_(fixture_event_ids)).order_by(WinProbSnapshot.event_id,WinProbSnapshot.id))).all()
    extra={'all_prices':[list(row) for row in all_prices],'all_events':[{'id':e.id,'p':aggregation.compute_aggregate_probability(e,e.status),'rev':e.win_probability_sources_rev,'sources':e.win_probability_sources} for e in all_events],'snapshots':[list(row) for row in snapshots]}
   return {**extra,**stamp(),'p':aggregation.compute_aggregate_probability(ev,ev.status),'rev':{str(E):ev.win_probability_sources_rev},'sources':ev.win_probability_sources,'prices':[list(x) for x in prices]}
 try:
  async with websockets.serve(provider,'127.0.0.1',provider_port):
   writer=asyncio.create_task(consumer._run_kalshi_ws_consumer())
   async with asyncio.timeout(20):
    while not server.started: await asyncio.sleep(.02)
    while not ws_ready.is_set():
     if writer.done(): await writer;raise RuntimeError('consumer ended before socket ready')
     await asyncio.sleep(.02)
   dump(output/'initial-state.json',await state())
   initial=json.loads((output/'initial-state.json').read_text())
   receipt['initial_contract']={key:initial[key] for key in ['p','rev','prices']}
   if quiet_debt:receipt['initial_contract']['fixture']=parity_signature(initial)
   (output/'index.html').write_text((OUT/'index.html').read_text().replace('@@EVENT@@',str(E)))
   browser=await asyncio.create_subprocess_exec('node',str(OUT/'browser.cjs'),str(http_port),str(output),str(E),stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.STDOUT)
   # Browser announces mounted hero+chart+native SSE before input.
   async with asyncio.timeout(70):
    while not (output/'browser-ready.json').exists():
     if (output/'browser-receipt.json').exists(): raise RuntimeError('browser failed before ready')
     await asyncio.sleep(.05)
   async def inject(p,label):
    mode['label']=label
    before=(await state(full=False))['rev'][str(E)]
    quotes=burst if quiet_debt and label=='normal' else [(ticker+'-BARVOC',H,p)]
    for external_id,oid,value in quotes:
     frame={'type':'ticker','sid':1,'seq':len(receipt['inputs'])+frames.qsize()+1,'msg':{'market_ticker':external_id,'yes_bid_dollars':f'{value-.02:.4f}','yes_ask_dollars':f'{value+.02:.4f}','price_dollars':f'{value:.4f}'}}
     frames.put_nowait(frame)
    async with asyncio.timeout(15):
     while (await state(full=False))['rev'][str(E)]<=before:
      if receipt['qualification_errors']:raise Inconclusive('; '.join(receipt['qualification_errors']))
      await asyncio.sleep(.025)
    actual=await state();dump(output/(label+'-state.json'),actual)
    receipt[label]=actual
    if quiet_debt and label=='normal':
     if not affected or receipt['qualification_errors']:raise Inconclusive('missing complete affected batch: '+repr(receipt['qualification_errors']))
     receipt['affected_batch']=affected[0]
    dump(output/'receipt.json',receipt)
    return actual
   if history_hold:
    await inject(.71,'prelude')
    await asyncio.wait_for(history_entered.wait(),5)
   normal=await inject(.74,'normal')
   async with asyncio.timeout(15):
    while not (output/'normal-render.json').exists(): await asyncio.sleep(.05)
   if quiet_debt:
    async with asyncio.timeout(30):
     while captured['price_buffer'] or captured['blend_refresher'].pending_event_ids():await asyncio.sleep(.025)
    # Empty buffer precedes the final stamp completion: wait for observed flush exit too.
    async with asyncio.timeout(30):
     while any('finished' not in f for f in receipt['flushes']):await asyncio.sleep(.025)
    normal_final=await state();dump(output/'normal-final-state.json',normal_final)
    receipt['normal_final_parity']=parity_signature(normal_final)
    expected_prices={oid:p for _,oid,p in burst}
    expected_prices.update({leg.id:p for leg,p in zip(fixture_legs[17],(.54,.46))})
    expected_events={e.id:.62 for e in fixture_events[:16]};expected_events.update({E:.74,Q:.54})
    error=fixture_parity_error(normal_final,expected_prices,expected_events)
    if error:raise RuntimeError(error)
    expected_ranks={leg.id:j+1 for pair in fixture_legs for j,leg in enumerate(pair)}
    if any(row[2]!=expected_ranks[row[0]] for row in normal_final['all_prices']):raise RuntimeError('final rank parity failed')
   mode['drop']=True
   missing=await inject(.59,'missing-publication')
   dump(output/'missing-ready.json',missing)
   output_text=await browser.communicate()
   (output/'browser.log').write_bytes(output_text[0])
   if browser.returncode: raise RuntimeError('browser exit '+str(browser.returncode))
   receipt['output_parity']={'normal_stored_p':normal['p'],'normal_expected':.74,'missing_stored_p':missing['p'],'missing_expected':.59}
   rendered=json.loads((output/'normal-render.json').read_text())
   matching=[x for x in rendered['events'] if x.get('kind')=='probability' and matches_target(x['frame'],E,normal['rev'][str(E)],.74)]
   if not matching: raise RuntimeError('normal native frame does not match committed identity/revision')
   receipt['timing_limits']={'storage':'follow-up DB read after revision-advance poll; 25ms poll interval plus query/scheduler delay, not exact commit time','publication':'call entry, not Redis acknowledgement','browser':'separate process wall clock; offset unmeasured; visible sampled by requestAnimationFrame','commit_hooks':'savepoint-related after_commit callbacks are retained, not promoted to outer commits'}
   receipt['timings']={}
   for label in ['normal','missing-publication']:
    index=0 if label=='normal' else 1
    sent=next(x['monotonic_s'] for x in receipt['inputs'] if x['label']==label and x['frame']['msg']['market_ticker']==ticker+'-BARVOC');stored=receipt[label]
    pubs=[x for x in receipt['publish_calls'] if any(matches_target(f,E,stored['rev'][str(E)],.74 if label=='normal' else .59) for f in x['frames'])]
    receipt['timings'][label]={'input_to_observed_storage_ms':(stored['monotonic_s']-sent)*1000,'input_to_publication_call_ms':(pubs[0]['monotonic_s']-sent)*1000 if pubs else None,'publication_intentionally_dropped':index==1}
   if quiet_debt:
    affected_flush=next(f for f in receipt['flushes'] if set(f['batch_before'])==expected_oids and f['pending_before']==[Q])
    receipt['affected_flush']=affected_flush
    sent=next(x['monotonic_s'] for x in receipt['inputs'] if x['label']=='normal' and x['frame']['msg']['market_ticker']==ticker+'-BARVOC')
    target_publication=next(x for x in receipt['publish_calls'] if any(matches_target(f,E,normal['rev'][str(E)],.74) for f in x['frames']))
    receipt['timings']['normal'].update(send_to_affected_flush_ms=(affected_flush['monotonic_s']-sent)*1000,affected_flush_to_publication_entry_ms=(target_publication['monotonic_s']-affected_flush['monotonic_s'])*1000)
   receipt['timings']['normal']['native_frame_to_visible_ms']=rendered['visibleTiming']['performance_ms']-matching[0]['performance_ms']
   ack=receipt.get('render_ack')
   if not ack or float(ack['view']['hero'])!=.74 or not any(matches_target(x['frame'],E,normal['rev'][str(E)],.74) for x in ack['view']['events'] if x['kind']=='probability'):
    raise RuntimeError('render acknowledgement lacks matching committed identity/revision/value')
   sent=next(x['monotonic_s'] for x in receipt['inputs'] if x['label']=='normal' and x['frame']['msg']['market_ticker']==ticker+'-BARVOC')
   receipt['timings']['normal']['input_to_render_ack_upper_bound_ms']=(ack['monotonic_s']-sent)*1000
   if history_hold:
    hold=receipt['history_hold'];released=hold.get('released')
    receipt['visible_before_history_release']=released is None or ack['monotonic_s']<released['monotonic_s']
    receipt['hold_still_active_at_second_input']=released is None or sent<released['monotonic_s']
    if not receipt['hold_still_active_at_second_input']:raise Inconclusive('second input missed history hold')
   receipt['timings']['normal']['input_to_frame_wall_ms']=(matching[0]['at']/1000-datetime.fromisoformat(next(x['at'] for x in receipt['inputs'] if x['label']=='normal' and x['frame']['msg']['market_ticker']==ticker+'-BARVOC')).timestamp())*1000
   receipt['timings']['normal']['input_to_visible_wall_ms']=(rendered['visibleTiming']['at']/1000-datetime.fromisoformat(next(x['at'] for x in receipt['inputs'] if x['label']=='normal' and x['frame']['msg']['market_ticker']==ticker+'-BARVOC')).timestamp())*1000
   receipt['result']='PASS' if abs(normal['p']-.74)<.00001 and abs(missing['p']-.59)<.00001 else 'FAIL_PARITY'
   if quiet_debt:
    final=await state();dump(output/'final-state.json',final)
    receipt['final_parity']=parity_signature(final)
    expected_prices[H]=.59;expected_events[E]=.59
    error=fixture_parity_error(final,expected_prices,expected_events)
    if error:raise RuntimeError(error)
    if receipt['qualification_errors']:raise Inconclusive('; '.join(receipt['qualification_errors']))
   return receipt
 except Inconclusive as error:
  receipt['result']='INCONCLUSIVE';receipt['failure']=str(error);raise
 finally:
  cleanup_errors=[]
  async def clean(name,operation):
   try:await operation()
   except Exception as error:cleanup_errors.append({'resource':name,'error':repr(error)})
  async def stop_browser():
   if browser and browser.returncode is None:
    with contextlib.suppress(ProcessLookupError):browser.terminate()
    await browser.wait()
  async def stop_writer():
   if writer:
    writer.cancel()
    with contextlib.suppress(asyncio.CancelledError):await writer
  async def stop_api():
   server.should_exit=True
   try:await asyncio.wait_for(api_task,7)
   finally:
    if not api_task.done():api_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):await api_task
  await clean('browser',stop_browser)
  await clean('consumer_drain_join_dispose',stop_writer)
  await clean('api',stop_api)
  if quiet_debt and captured:
   async def read_final():
    receipt['post_drain_parity']=parity_signature(await state())
    owner=getattr(captured.get('get_task_session'),'__self__',None)
    if owner is None or owner._engine is engine:
     receipt['result']='FAIL_ENGINE_OWNERSHIP'
    else:
     receipt['consumer_engine']={'separate_from_observer':owner._engine is not engine,'pool_size':owner._engine.pool.size(),'owner_disposed':owner._disposed,'owner_closing':owner._closing,'owner_open_sessions':owner._open}
     if not owner._disposed or not owner._closing or owner._open:receipt['result']='FAIL_ENGINE_CLEANUP'
    receipt['consumer_final']={'buffer':list(captured['price_buffer']),'pending':sorted(captured['blend_refresher'].pending_event_ids()),'stats':dict(captured['stats'])}
    if receipt['consumer_final']['buffer'] or receipt['consumer_final']['pending'] or any(receipt['consumer_final']['stats'].get(k,0) for k in ('errors','final_flush_dropped','settled_declined')):receipt['result']='FAIL_FINAL_DRAIN'
   await clean('post_drain_readback',read_final)
   receipt['observer_limits']='Independent committed publication read runs after real publisher returns; it can add work before later phases. The target publication entry precedes that observer work. Shared API/observer queries use a separate source-configured engine; host contention is retained. No exact Redis ACK or painted-pixel clock.'
  blend.run_flush_cadence=original_cadence;consumer.linked_first_phases=original_planner
  blend.LiveBlendRefresher._publish=original_publish;blend.LiveBlendRefresher.publish_market_changes=original_market;blend.TailReceipts.note_input=original_note
  snapshots._create_or_update_win_prob_snapshot=original_snapshot
  try:sql_event.remove(__import__('sqlalchemy').orm.Session,'after_commit',committed)
  except Exception as error:cleanup_errors.append({'resource':'commit_listener','error':repr(error)})
  await clean('observer_engine',engine.dispose)
  receipt['worker_cleanup_errors']=cleanup_errors
  if cleanup_errors:receipt['result']='FAIL_WORKER_CLEANUP'
  receipt['finished_at']=utc();receipt['backend_wall_s']=time.monotonic()-receipt['started_monotonic_s']
  dump(output/'receipt.json',receipt)

def main():
 parser=argparse.ArgumentParser()
 parser.add_argument('--output',required=True)
 parser.add_argument('--application-ref',default=PIN)
 parser.add_argument('--quiet-debt-comparison',action='store_true')
 parser.add_argument('--history-hold',action='store_true')
 parser.add_argument('--trials',type=int,choices=[1,2,3],default=1)
 parser.add_argument('--worker',action='store_true',help=argparse.SUPPRESS)
 parser.add_argument('--tree',help=argparse.SUPPRESS)
 parser.add_argument('--database-url',help=argparse.SUPPRESS)
 parser.add_argument('--redis-url',help=argparse.SUPPRESS)
 parser.add_argument('--http-port',type=int,help=argparse.SUPPRESS)
 args=parser.parse_args();output=Path(args.output).resolve()
 application_ref=args.application_ref if args.worker else resolve_application_ref(args.application_ref)
 if args.history_hold and args.quiet_debt_comparison:parser.error('history hold and quiet debt are separate experiments')
 if args.quiet_debt_comparison and application_ref not in QUIET_PAIR:parser.error('quiet-debt comparison requires the exact #10728 parent or candidate')
 if args.quiet_debt_comparison and not args.worker:
  frontend_trees=[subprocess.check_output(['git','-C',str(REPO),'rev-parse',ref+':frontend'],text=True,timeout=10).strip() for ref in QUIET_PAIR]
  if len(set(frontend_trees))!=1:parser.error('quiet-debt pair frontend trees differ')
 if args.worker:
  os.environ.update(DATABASE_URL=args.database_url,REDIS_URL=args.redis_url,SSE_HEARTBEAT_INTERVAL_S='2')
  if args.history_hold:os.environ['KALSHI_WS_PRICE_FLUSH_SECONDS']='0.25'
  original_connect=socket.socket.connect
  def local_connect(self,address):
   if isinstance(address,tuple) and address[0] not in ('127.0.0.1','::1','localhost'):raise RuntimeError('external socket refused by local replay')
   return original_connect(self,address)
  socket.socket.connect=local_connect
  sys.path.insert(0,str(Path(args.tree)/'backend'))
  result=asyncio.run(asyncio.wait_for(replay(Path(args.tree),output,args.database_url,args.redis_url,args.http_port,application_ref,args.quiet_debt_comparison,args.history_hold),150))
  dump(output/'result.json',result)
  if result['result']!='PASS':raise RuntimeError(result['result'])
  return
 output.mkdir(parents=True,exist_ok=False)
 started=time.monotonic();deadline=started+900
 temp=Path(tempfile.mkdtemp(prefix='full-path-10669-',dir='/tmp'))
 life={'started_at':utc(),'temporary_root':str(temp),'stopped':False,'source_pin':application_ref,'quiet_debt_comparison':args.quiet_debt_comparison,'requested_trials':args.trials,'phases':[],'trials':[],'result':'RUNNING'}
 dump(output/'lifecycle.json',life)
 redis_process=None;worker=None;lock=None
 def alarm_expired(*_):raise TimeoutError('whole invocation exceeded 900 seconds')
 previous_alarm=signal.signal(signal.SIGALRM,alarm_expired);signal.alarm(900)
 def terminated(signum,*_):raise SystemExit(128+signum)
 previous_term=signal.signal(signal.SIGTERM,terminated)
 def remaining(cap):
  left=deadline-time.monotonic()
  if left<=0:raise TimeoutError('whole invocation exceeded 900 seconds')
  return min(cap,left)
 def run(command,cap=120,**kwargs):
  return subprocess.run(command,check=True,timeout=remaining(cap),**kwargs)
 def phase(name,operation):
  entry={'name':name,**stamp()};life['phases'].append(entry);dump(output/'lifecycle.json',life)
  print('START '+name,flush=True)
  try:return operation()
  finally:
   entry.update(finished_at=utc(),wall_s=time.monotonic()-entry['monotonic_s']);dump(output/'lifecycle.json',life)
   print('END '+name+' '+str(round(entry['wall_s'],3))+'s',flush=True)
 try:
  def claim_benchmark():
   nonlocal lock
   lock=open('/tmp/bainluck-live-lab-10669-benchmark.lock','a+')
   fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  phase('exclusive_lab_lock',claim_benchmark)
  tree=temp/'source';tree.mkdir()
  def archive_source():
   archive=subprocess.check_output(['git','-C',str(REPO),'archive',application_ref,'backend','frontend'],timeout=remaining(180))
   import io
   with tarfile.open(fileobj=io.BytesIO(archive)) as t:t.extractall(tree,filter='data')
   hashes={str(p.relative_to(tree)):hashlib.sha256(p.read_bytes()).hexdigest() for p in tree.rglob('*') if p.is_file()}
   dump(output/'source-manifest.json',{'pin':application_ref,'files':hashes,'frontend_tree':subprocess.check_output(['git','-C',str(REPO),'rev-parse',application_ref+':frontend'],text=True,timeout=remaining(10)).strip(),'runner_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()})
   shutil.copy(CONTRACT,output/'retained-contract.json')
  phase('source_archive_extract_hash',archive_source)
  prepared=output/'prepared';prepared.mkdir()
  phase('frontend_build_once',lambda:run(['node',str(OUT/'build.cjs'),str(tree/'frontend'),str(prepared)],100,stdout=(output/'build.log').open('w'),stderr=subprocess.STDOUT))
  data=temp/'pg';sock=temp/'sock';sock.mkdir();pgport=55570
  phase('initdb_once',lambda:run([str(PG/'initdb'),'-D',str(data),'-A','trust','--no-locale'],180,stdout=(output/'initdb.log').open('w'),stderr=subprocess.STDOUT))
  phase('postgres_start_once',lambda:run([str(PG/'pg_ctl'),'-D',str(data),'-l',str(output/'postgres.log'),'-o',f"-k {sock} -p {pgport} -c listen_addresses=''",'-w','start'],60,stdout=subprocess.DEVNULL))
  def start_redis():
   nonlocal redis_process
   import redislite,redis
   redisbin=Path(redislite.__file__).parent/'bin/redis-server'
   redis_process=subprocess.Popen([str(redisbin),'--bind','127.0.0.1','--port',str(redisport),'--save','','--appendonly','no','--dir',str(temp)],start_new_session=True,stdout=(output/'redis.log').open('w'),stderr=subprocess.STDOUT)
   client=redis.Redis(host='127.0.0.1',port=redisport,socket_connect_timeout=1,socket_timeout=1)
   try:
    for _ in range(100):
     try:client.ping();return
     except redis.ConnectionError:time.sleep(.02)
    raise RuntimeError('private Redis did not start')
   finally:client.close()
  redisport=port();phase('redis_start_once',start_redis)
  life['preparation_wall_s']=time.monotonic()-started
  for number in range(1,args.trials+1):
   trial=output/f'trial-{number}';trial.mkdir();record={'number':number,**stamp(),'result':'RUNNING','reset':'new empty PostgreSQL database; empty private Redis DB; fresh Python consumer and browser processes'};life['trials'].append(record)
   def reset():
    run([str(PG/'createdb'),'-h',str(sock),'-p',str(pgport),f'trial{number}'],30)
    import redis
    client=redis.Redis(host='127.0.0.1',port=redisport,db=number,socket_connect_timeout=1,socket_timeout=1)
    try:client.flushdb();assert client.dbsize()==0
    finally:client.close()
    for asset in prepared.iterdir():
     if asset.suffix in ('.js','.css'):os.link(asset,trial/asset.name)
   phase(f'trial_{number}_reset',reset)
   record['reset_wall_s']=time.monotonic()-record['monotonic_s']
   url=f'postgresql+asyncpg://bain@/trial{number}?host={sock}&port={pgport}'
   command=[sys.executable,str(OUT/'run.py'),'--application-ref',application_ref,*(['--quiet-debt-comparison'] if args.quiet_debt_comparison else []),*(['--history-hold'] if args.history_hold else []),'--worker','--output',str(trial),'--tree',str(tree),'--database-url',url,'--redis-url',f'redis://127.0.0.1:{redisport}/{number}','--http-port',str(port())]
   def execute():
    nonlocal worker
    worker=subprocess.Popen(command,start_new_session=True,stdout=(trial/'worker.log').open('w'),stderr=subprocess.STDOUT)
    try:
     code=worker.wait(timeout=remaining(160))
     if code:raise subprocess.CalledProcessError(code,command)
    except BaseException as error:
     record['worker_failure']=repr(error);raise
    finally:
     stop_owned_group(worker)
    worker=None
   phase(f'trial_{number}_worker_browser',execute)
   result=json.loads((trial/'result.json').read_text())
   if number==1:life['initial_contract']=result['initial_contract']
   elif result['initial_contract']!=life['initial_contract']:raise RuntimeError('trial initial DB/consumer contract differs')
   record.update(result=result['result'],wall_s=time.monotonic()-record['monotonic_s'],backend_wall_s=result['backend_wall_s'],timings=result['timings'])
   dump(output/'lifecycle.json',life)
   print('TRIAL '+str(number)+' '+record['result']+' '+str(round(record['wall_s'],3))+'s',flush=True)
  life['result']='PASS'
 except BaseException as error:
  life['result']='FAIL';life['failure']=repr(error);raise
 finally:
  cleanup_started=time.monotonic()
  cleanup=cleanup_owned(temp,worker,redis_process,lock)
  signal.signal(signal.SIGALRM,previous_alarm);signal.signal(signal.SIGTERM,previous_term)
  life.update(cleanup,cleanup_wall_s=time.monotonic()-cleanup_started,wall_s=time.monotonic()-started,finished_at=utc())
  if not cleanup['stopped']:
   life['result']='FAIL_CLEANUP'
  dump(output/'lifecycle.json',life)
  if not cleanup['stopped']:raise RuntimeError('owned cleanup incomplete: '+repr(cleanup))
if __name__=='__main__':main()
