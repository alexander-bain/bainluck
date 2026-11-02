"""Signed review events dispatch only a PR number, never review text or credentials."""
import hashlib
import hmac
import importlib.util
import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

ROOT = Path(__file__).resolve().parents[2]
FILE = ROOT / 'backend/app/routes/tier_b_review_webhook.py'


def module():
    assert FILE.exists(), 'signed review webhook has not been built'
    spec = importlib.util.spec_from_file_location('tier_b_webhook', FILE)
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


def payload(action='dismissed'):
    return json.dumps({'action':action, 'repository':{'full_name':'alexander-bain/bainluck'},
                       'pull_request':{'number':17}, 'review':{'body':'private review text'}}).encode()


def client(monkeypatch):
    m=module()
    monkeypatch.setenv('TIER_B_REVIEW_WEBHOOK_SECRET','test-secret')
    monkeypatch.setenv('RELEASE_DISPATCH_TOKEN','test-token')
    app=FastAPI(); app.include_router(m.router)
    return m, TestClient(app)


def test_unsigned_or_tampered_event_never_dispatches(monkeypatch):
    m, http=client(monkeypatch)
    sent=[]
    async def dispatch(number): sent.append(number)
    monkeypatch.setattr(m,'dispatch_review',dispatch)
    response=http.post('/api/release-loop/tier-b-review',content=payload(),headers={'X-GitHub-Event':'pull_request_review'})
    assert response.status_code==401 and not sent


@pytest.mark.parametrize('action',['submitted','edited','dismissed'])
def test_review_updates_use_signed_default_branch_dispatch(monkeypatch,action):
    m,http=client(monkeypatch);sent=[]
    async def dispatch(number): sent.append(number)
    monkeypatch.setattr(m,'dispatch_review',dispatch)
    data=payload(action)
    signature='sha256='+hmac.new(b'test-secret',data,hashlib.sha256).hexdigest()
    response=http.post('/api/release-loop/tier-b-review',content=data,
                       headers={'X-GitHub-Event':'pull_request_review','X-Hub-Signature-256':signature})
    assert response.status_code==202 and sent==[17]
    assert 'private review' not in response.text and 'test-token' not in response.text


def test_wrong_repository_and_unavailable_dispatch_fail_closed(monkeypatch):
    m,http=client(monkeypatch)
    data=payload().replace(b'alexander-bain/bainluck',b'another/repo')
    sig='sha256='+hmac.new(b'test-secret',data,hashlib.sha256).hexdigest()
    response=http.post('/api/release-loop/tier-b-review',content=data,headers={'X-GitHub-Event':'pull_request_review','X-Hub-Signature-256':sig})
    assert response.status_code==403


def test_dispatch_does_not_forward_review_body_or_secret_in_payload(monkeypatch):
    m=module()
    monkeypatch.setenv('RELEASE_DISPATCH_TOKEN','test-token')
    assert m.dispatch_payload(17)=={'event_type':'tier-b-review','client_payload':{'pull_number':17}}


def test_transport_failure_is_loud_and_never_exposes_token(monkeypatch):
    m,http=client(monkeypatch)
    class Transport:
        def __init__(self,**kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self,*args): pass
        async def post(self,*args,**kwargs):
            raise m.httpx.ConnectError('Bearer test-token private review text')
    monkeypatch.setattr(m.httpx,'AsyncClient',Transport)
    data=payload()
    signature='sha256='+hmac.new(b'test-secret',data,hashlib.sha256).hexdigest()
    response=http.post('/api/release-loop/tier-b-review',content=data,
                       headers={'X-GitHub-Event':'pull_request_review','X-Hub-Signature-256':signature})
    assert response.status_code==502
    assert 'test-token' not in response.text and 'private review' not in response.text


def test_receiver_is_mounted_in_the_real_app():
    from app.main import app
    assert any(route.path=='/api/release-loop/tier-b-review' for route in app.routes)
