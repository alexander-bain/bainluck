"""#9349: legitimate paired live reads fit a bounded shared caller budget."""
from collections import Counter

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from limits.storage import MemoryStorage
from limits.strategies import FixedWindowRateLimiter

from app.utils import rate_limit as rl


class LocalRedis:
    def __init__(self):
        self.counts = Counter()

    async def incr(self, key):
        self.counts[key] += 1
        return self.counts[key]

    async def expire(self, key, ttl):
        return True


@pytest.fixture(params=['redis', 'memory'])
def client(request, monkeypatch):
    monkeypatch.delenv('BYPASS_RATE_LIMITS', raising=False)
    monkeypatch.setenv('ADMIN_TOKEN', 'local-admin')
    monkeypatch.setattr(rl, '_trusted_ips', lambda: set())
    monkeypatch.setattr(rl, '_resolve_trusted_uid', lambda token: 'reader' if token == 'verified' else None)
    redis = LocalRedis()
    monkeypatch.setattr(rl, '_get_async_rl_redis', lambda: redis if request.param == 'redis' else None)
    monkeypatch.setattr(rl, '_rate_limiter', FixedWindowRateLimiter(MemoryStorage()))
    for name in ('_anon_limit', '_auth_limit', '_admin_limit', '_trusted_limit', '_fresh_event_limit'):
        monkeypatch.setattr(rl, name, None)
    monkeypatch.setattr(rl.time, 'time', lambda: 1800000000)
    app = FastAPI()
    app.add_middleware(rl.RateLimitMiddleware)

    @app.get('/api/events/{event_id}')
    async def detail(event_id: int, fresh: bool = False):
        return {'fresh': fresh}

    @app.get('/api/events/{event_id}/history')
    async def history(event_id: int, fresh: bool = False, hours: int = 24):
        return {'fresh': fresh}

    @app.api_route('/{path:path}', methods=['GET', 'POST', 'HEAD'])
    async def ordinary(path: str):
        return {'ok': True}

    with TestClient(app) as result:
        yield result


def test_paired_replay_with_setup_and_shared_multi_event_ceiling(client):
    for _ in range(7):
        assert client.get('/api/events/1').status_code == 200
    # One second worth of detail/history per iteration; all within one window.
    for _ in range(60):
        for suffix in ('', '/history'):
            assert client.get(f'/api/events/1{suffix}?fresh=true').status_code == 200
    # New event IDs and query variants must NOT buy new buckets.
    for i in range(60):
        assert client.get(f'/api/events/{i+2}/history?fresh=TRUE&hours=168').status_code == 200
    denied = client.get('/api/events/999?fresh=1')
    assert denied.status_code == 429
    assert int(denied.headers['retry-after']) > 0
    assert '180' in denied.json()['detail']
    # The seven initial ordinary reads still count against the ordinary bucket.
    for _ in range(53):
        assert client.get('/api/feed').status_code == 200
    assert client.get('/api/feed').status_code == 429


def test_verified_user_keeps_ordinary120_and_fresh180(client):
    headers = {'Authorization': 'Bearer verified'}
    for _ in range(120):
        assert client.get('/api/feed', headers=headers).status_code == 200
    assert client.get('/api/feed', headers=headers).status_code == 429
    for _ in range(180):
        assert client.get('/api/events/1?fresh=true', headers=headers).status_code == 200
    assert client.get('/api/events/2/history?fresh=true', headers=headers).status_code == 429


def test_forged_tokens_and_alternate_ids_do_not_buy_buckets(client):
    for i in range(180):
        assert client.get(f'/api/events/{i+1}?fresh=true', headers={'Authorization': f'Bearer forged-{i}'}).status_code == 200
    assert client.get('/api/events/999/history?fresh=true').status_code == 429
    # A different actual caller has its own finite budget.
    assert client.get('/api/events/1?fresh=true', headers={'X-Forwarded-For': '192.0.2.2'}).status_code == 200


@pytest.mark.parametrize('method,path', [
    ('POST', '/api/events/1?fresh=true'), ('HEAD', '/api/events/1?fresh=true'),
    ('GET', '/api/events/search?fresh=true'), ('GET', '/api/events/1/history/extra?fresh=true'),
    ('GET', '/api/events/0?fresh=true'), ('GET', '/api/events/-1?fresh=true'),
    ('GET', '/api/events/1?fresh=false'), ('GET', '/api/events/1?fresh=maybe'),
    ('GET', '/api/events/1?fresh=true&fresh=false'), ('GET', '/api/events/1'),
    ('GET', '/api/events/1/history?fresh=true&hours=bad'),
])
def test_nonqualifying_reads_spend_ordinary_budget(client, method, path):
    for _ in range(60):
        assert client.get('/api/feed').status_code == 200
    assert client.request(method, path).status_code == 429


@pytest.mark.parametrize('value', ['1', 'true', 'True', 'TRUE', 't', 'on', 'yes', 'y'])
def test_true_values_match_fastapi_route_consumption(client, value):
    for _ in range(60):
        assert client.get('/api/feed').status_code == 200
    response = client.get(f'/api/events/1?fresh=false&fresh={value}')
    assert response.status_code == 200
    assert response.json()['fresh'] is True


def test_admin_and_trusted_ceiling_preserved(client, monkeypatch):
    admin = {'Authorization': 'Bearer local-admin'}
    for _ in range(300):
        assert client.get('/api/admin/check?fresh=true', headers=admin).status_code == 200
    assert client.get('/api/admin/check?fresh=true', headers=admin).status_code == 429
    monkeypatch.setattr(rl, '_trusted_ips', lambda: {'192.0.2.3'})
    monkeypatch.setattr(rl, '_router_peer_ip', lambda request: '192.0.2.3')
    for i in range(600):
        path = '/api/feed' if i % 2 else '/api/events/1/history?fresh=true'
        assert client.get(path).status_code == 200
    assert client.get('/api/events/2?fresh=true').status_code == 429
