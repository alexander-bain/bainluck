"""A successful PUBLISH plus failed retention must not rotate a healthy pool."""
import json
from unittest.mock import AsyncMock, Mock
import pytest
from redis.asyncio import Redis
from redis.exceptions import ResponseError, ConnectionError
from app.utils import live_push
from tests.test_event_frame_batching_10659 import private_redis_socket, frames, refresher, ProtocolRedis

pytestmark=pytest.mark.asyncio
RETENTION_ERROR='normal price replay retention failed after PUBLISH'


async def test_real_retention_failure_keeps_client_and_owes_final_revision(private_redis_socket,monkeypatch):
    client=Redis(unix_socket_path=str(private_redis_socket))
    ps=client.pubsub()
    original=live_push.frame_publish_command
    def command(frame, **kwargs):
        cmd=original(frame, **kwargs)
        return (*cmd[:8], '0', *cmd[9:])  # real Redis SET refusal, PUBLISH still executes
    monkeypatch.setattr(live_push,'frame_publish_command',command)
    r=refresher(client)
    r._normal_has_debt=False
    monkeypatch.setattr(r,'_start_normal_recovery',Mock())
    # Warm and instrument the exact connection the packed publisher will borrow.
    await client.ping()
    connection=await client.connection_pool.get_connection()
    await client.connection_pool.release(connection)
    disconnect=AsyncMock(wraps=connection.disconnect)
    monkeypatch.setattr(connection,'disconnect',disconnect)
    batch=frames(1)
    try:
        await ps.subscribe('live:event:1')
        await ps.get_message(timeout=1)
        assert await r._publish_prices(batch)==set()
        assert r._normal_has_debt and r._normal_epoch==1
        assert r._normal_acked=={}
        assert r._redis is client,'retention refusal discarded a healthy pool'
        disconnect.assert_not_awaited()
        msg=await ps.get_message(ignore_subscribe_messages=True,timeout=1)
        assert msg and json.loads(msg['data'])==batch[0]
        assert await client.get(live_push.latest_frame_key(1)) is None
        r._start_normal_recovery.assert_called_once()
    finally:
        await ps.aclose()
        await client.aclose()


@pytest.mark.parametrize('replies,keeps_client,disconnects',[
    ([ResponseError(RETENTION_ERROR)],True,False),
    ([ResponseError('denied')],False,False),
    ([ResponseError(RETENTION_ERROR),ResponseError('denied')],True,False),
    ([ResponseError(RETENTION_ERROR),ConnectionError('lost after first reply')],False,True),
])
async def test_only_proven_retention_reply_preserves_connection(replies,keeps_client,disconnects):
    client=ProtocolRedis(replies)
    r=refresher(client)
    assert await r._publish(frames(len(replies)))==set()
    assert (r._redis is client)==keeps_client
    assert client.connection.disconnect.await_count==int(disconnects)
    client.connection_pool.release.assert_awaited_once()


async def test_repeated_price_refusals_and_control_use_same_pool(monkeypatch):
    client=ProtocolRedis([ResponseError(RETENTION_ERROR)]*8+[0])
    r=refresher(client)
    monkeypatch.setattr(r,'_start_normal_recovery',Mock())
    r._normal_has_debt=False
    for revision in range(2,10):
        batch=frames(1)
        batch[0]['rev']={'1':revision}
        assert await r._publish_prices(batch)==set()
        assert r._redis is client
    assert r._normal_has_debt and r._normal_acked=={}
    assert r._normal_epoch==8
    control=frames(1)[0]
    control.update(p=None,rev={'1':9},reconcile_only=True,
                   reconcile={'event_id':1,'custody_id':'normal-price:1:9','removal_rev':{'1':9}})
    assert await r._publish([control])=={(1,9)}
    assert r._redis is client
    assert client.connection_pool.get_connection.await_count==9
    client.connection.disconnect.assert_not_awaited()
    assert len(client.commands)==9
