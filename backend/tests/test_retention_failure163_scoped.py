"""Real Redis: failed cache retention still delivers, but keeps normal-price debt."""
import asyncio,json
import pytest
from redis.asyncio import Redis
from app.utils import live_push
from tests.test_event_frame_batching_10659 import private_redis_socket, frames, refresher
pytestmark=pytest.mark.asyncio

@pytest.mark.parametrize('with_listener',[False,True])
async def test_unretained_normal_owed_but_healthy_sibling_acknowledged(private_redis_socket,monkeypatch,with_listener):
    client=Redis(unix_socket_path=str(private_redis_socket));ps=client.pubsub()
    original=live_push.frame_publish_command
    def command(frame, **kwargs):
        cmd=original(frame, **kwargs)
        return (*cmd[:8],'0',*cmd[9:]) if frame['event_id']==1 else cmd
    monkeypatch.setattr(live_push,'frame_publish_command',command)
    batch=frames(2)
    try:
        if with_listener:
            await ps.psubscribe('live:event:*');await ps.get_message(timeout=1)
        r=refresher(client);ack=await r._publish(batch)
        if with_listener:
            received=[]
            async with asyncio.timeout(1):
                while len(received)<2:
                    msg=await ps.get_message(ignore_subscribe_messages=True,timeout=.1)
                    if msg:received.append(json.loads(msg['data']))
            assert received==batch,'Cache refusal must not suppress delivery'
        assert await client.get(live_push.latest_frame_key(1)) is None
        assert json.loads(await client.get(live_push.latest_frame_key(2)))==batch[1]
        assert ack=={(2,3)},'Unretained normal frame must keep recovery custody'
        assert r.stats['publish_errors']==1 and r.stats['published']==1
    finally:await ps.aclose();await client.aclose()

async def test_control_ack_remains_payable_even_if_retention_keeps_failing(private_redis_socket,monkeypatch):
    client=Redis(unix_socket_path=str(private_redis_socket));original=live_push.frame_publish_command
    def command(frame, **kwargs):
        cmd=original(frame, **kwargs);return (*cmd[:8],'0',*cmd[9:])
    monkeypatch.setattr(live_push,'frame_publish_command',command)
    control={'event_id':1,'p':None,'rev':{'1':2},'updated_at':'2026-10-19T00:00:00+00:00','reconcile_only':True,'reconcile':{'event_id':1,'custody_id':'normal-price:1:2','removal_rev':{'1':2}}}
    try:
        r=refresher(client)
        assert await r._publish([control])=={(1,2)}
        assert r.stats['publish_errors']==0 and r.stats['published']==1
        assert await client.get(live_push.latest_frame_key(1)) is None
    finally:await client.aclose()

async def test_generic_publisher_ack_contract_is_unchanged(private_redis_socket,monkeypatch):
    client=Redis(unix_socket_path=str(private_redis_socket));original=live_push.frame_publish_command
    def command(frame, **kwargs):
        cmd=original(frame, **kwargs);return (*cmd[:8],'0',*cmd[9:])
    monkeypatch.setattr(live_push,'frame_publish_command',command)
    try:
        assert await live_push.publish_frame(client,frames(1)[0]) is True
        assert await client.get(live_push.latest_frame_key(1)) is None
    finally:await client.aclose()
