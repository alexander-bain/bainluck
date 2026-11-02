"""A queued release keeps its actual worker startup and latency input across dyno restarts."""
import importlib.util
import pathlib

import fakeredis
import pytest

PATH=pathlib.Path(__file__).resolve().parents[1]/'app/utils/release_log_store.py'

def module():
    assert PATH.exists(), 'durable release log store is missing'
    spec=importlib.util.spec_from_file_location('release_log_store',PATH)
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result);return result

def frame(text):
    data=text.encode();return str(len(data)).encode()+b' '+data

def line(message,proc='worker-ws.1',app='app',stamp='2026-11-02T00:01:00.100Z'):
    return '<190>1 '+stamp+' host '+app+' '+proc+' - - '+message

def test_octet_frames_preserve_startup_and_unicode_in_canonical_check_shape():
    m=module()
    rows=m.parse_logplex(frame(line('Starting process with command python worker',app='heroku'))+frame(line('gc thresholds café')))
    assert len(rows)==2
    assert rows[0]['line'].startswith('2026-11-02T00:01:00.100000+00:00 heroku[worker-ws.1]: Starting process')
    assert 'café' in rows[1]['line']

def test_router_and_regular_price_logs_are_not_stored():
    m=module()
    raw=frame(line('request worker-ws diagnostic',proc='router',app='heroku'))+frame(line('price update'))+frame(line('Kalshi WS: 20 msgs'))
    rows=m.parse_logplex(raw)
    stored=[row for row in rows if row.get('line')]
    assert len(stored)==1 and '20 msgs' in stored[0]['line']

def test_error_secrets_are_redacted_before_persistence():
    m=module()
    text='{"level": "ERROR", "message": "TypeError redis://user:password@host/?apiKey=private", "token": "raw-secret"}'
    result=m.parse_logplex(frame(line(text)))[0]['line']
    assert 'TypeError' in result
    for secret in ('password','private','raw-secret'):assert secret not in result

def test_bad_length_frames_are_rejected_without_partial_store():
    m=module()
    for body in (b'100 short',b'no-length',b'999999 huge'):
        with pytest.raises(ValueError):m.parse_logplex(body)

def test_replayed_batches_dedupe_and_survive_a_new_client():
    m=module();server=fakeredis.FakeServer();first=fakeredis.FakeRedis(server=server,decode_responses=True)
    rows=m.parse_logplex(frame(line('gc thresholds')))
    now=rows[0]['timestamp']+1
    m.store(rows,client=first,now=now);m.store(rows,client=first,now=now)
    second=fakeredis.FakeRedis(server=server,decode_responses=True)
    result=m.read_window(rows[0]['timestamp'],client=second,now=now+5)
    assert result['complete'] is True
    assert len(result['lines'])==1

def test_old_and_count_trimmed_history_is_loud():
    m=module();client=fakeredis.FakeRedis(decode_responses=True)
    rows=[{'timestamp':100+i,'line':str(i)} for i in range(m.MAX_RECORDS+20)]
    now=100+m.MAX_RECORDS+20;m.store(rows,client=client,now=now)
    result=m.read_window(100,client=client,now=now)
    assert result['complete'] is False
    assert len(result['lines'])==m.MAX_RECORDS
    assert client.ttl(m.LOG_KEY)>0

def test_silent_or_dropped_drain_is_unknown():
    m=module();client=fakeredis.FakeRedis(decode_responses=True)
    m.store([{'timestamp':100,'line':'startup'},{'timestamp':101,'loss':True}],client=client,now=102)
    assert m.read_window(100,client=client,now=103)['complete'] is False
    assert m.read_window(100,client=client,now=500)['live'] is False

def test_authenticated_routes_persist_frames_and_reject_anonymous_reads(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.routes import release_logs
    from app.utils import release_log_store
    client=fakeredis.FakeRedis(decode_responses=True)
    now=__import__('datetime').datetime.fromisoformat('2026-11-02T00:01:01.100+00:00').timestamp()
    monkeypatch.setenv('RELEASE_LOG_DRAIN_TOKEN','fixture-drain-token')
    monkeypatch.setenv('ADMIN_TOKEN','fixture-admin-token')
    monkeypatch.setattr(release_log_store,'_client',lambda:client)
    monkeypatch.setattr(release_log_store.time,'time',lambda:now)
    app=FastAPI();app.include_router(release_logs.router,prefix='/api')
    with TestClient(app) as http:
        body=frame(line('gc thresholds'))
        assert http.post('/api/release-logs/drain',content=body).status_code==403
        sent=http.post('/api/release-logs/drain',content=body,headers={'Authorization':'Bearer fixture-drain-token'})
        assert sent.status_code==202 and sent.json()['accepted']==1
        path='/api/admin/release-logs?since=2026-11-02T00%3A01%3A00.100Z'
        assert http.get(path).status_code==403
        received=http.get(path,headers={'Authorization':'Bearer fixture-admin-token'})
        assert received.status_code==200 and 'gc thresholds' in received.json()['lines'][0]
        assert received.headers['cache-control']=='no-store'

def test_old_replays_cannot_refresh_source_liveness():
    m=module();client=fakeredis.FakeRedis(decode_responses=True)
    m.store([{'timestamp':100,'line':'old startup'}],client=client,now=100)
    m.store([{'timestamp':100,'line':'old startup'}],client=client,now=1000)
    result=m.read_window(100,client=client,now=1001)
    assert result['live'] is False and result['complete'] is False

def test_truncated_error_diagnostics_make_coverage_incomplete():
    m=module();client=fakeredis.FakeRedis(decode_responses=True)
    raw=frame(line('{"level": "ERROR", "message": "'+('x'*4000)+' TypeError"}'))
    rows=m.parse_logplex(raw);now=rows[0]['timestamp']+1
    m.store(rows,client=client,now=now)
    assert m.read_window(rows[0]['timestamp'],client=client,now=now)['complete'] is False

def test_rejected_authenticated_batch_leaves_a_durable_loss_marker(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.routes import release_logs
    from app.utils import release_log_store as m
    client=fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setenv('RELEASE_LOG_DRAIN_TOKEN','fixture-drain-token')
    monkeypatch.setattr(m,'_client',lambda:client)
    monkeypatch.setattr(m.time,'time',lambda:102)
    m.store([{'timestamp':100,'line':'old startup'}],client=client,now=101)
    app=FastAPI();app.include_router(release_logs.router,prefix='/api')
    with TestClient(app) as http:
        result=http.post('/api/release-logs/drain',content=b'bad frame',headers={'Authorization':'Bearer fixture-drain-token'})
        assert result.status_code==400
    m.store([{'timestamp':103,'line':'fresh minute'}],client=client,now=103)
    assert m.read_window(100,client=client,now=104)['complete'] is False
