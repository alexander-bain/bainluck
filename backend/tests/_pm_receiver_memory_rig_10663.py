"""#10663 rig: the Polymarket open-contract receiver child at production size.

Run by ``test_pm_receiver_resident_glibc_10663`` in fresh interpreters:

    python3 _pm_receiver_memory_rig_10663.py arm BACKEND SECONDS N_IDS
    python3 _pm_receiver_memory_rig_10663.py child BACKEND URL CAFILE   (spawned)
    python3 _pm_receiver_memory_rig_10663.py server PORT CERT KEY      (spawned)

``arm`` starts a fake venue (``server``: a TLS websocket that answers each
subscribe with ONE list of a full book per id, ~1.5 MB on the wire for 500 ids
as in production, then streams ``price_change`` frames) and drives the
production ``PolymarketOpenReceiverProcess`` loaded from BACKEND, with
production's open-client settings (4 handshakes, max_queue 4, book snapshots
priced). Its child (``child``) runs BACKEND's unchanged ``serve_receiver`` and
``PolymarketWebSocket``, the real heap trim on its 60 s timer, and the
production TLS path (one shared ``create_default_context``, trusting only this
rig's certificate). The child's own ``heap trim: arm=polymarket_open_receiver
... rss=a->b`` lines are the reading, the same line production logs.

It prints one JSON line: the child's trims, its RSS samples, and what the
proxy delivered (prices, served ids, shards connected) so an arm that serves
less cannot pass for one that holds less.
"""

import asyncio
import importlib.util
import json
import os
import random
import signal
import ssl
import subprocess
import sys
import time

RATE_PER_SOCKET = 11.0  # ~1,500 frames/s over 136 sockets (production 1-2k)


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


# ------------------------------------------------------------------ venue ----

def _hex(rng, n):
    return "%0*x" % (n, rng.getrandbits(4 * n))


def _book(rng, asset_id):
    mid = rng.uniform(0.05, 0.95)
    nb, na = rng.randint(25, 50), rng.randint(25, 50)
    level = lambda p: {"price": f"{p:.3f}", "size": f"{rng.uniform(1, 50000):.2f}"}
    return {
        "market": "0x" + _hex(rng, 64), "asset_id": asset_id,
        "timestamp": str(1761160000000 + rng.randrange(10**7)), "hash": _hex(rng, 40),
        "bids": [level(max(0.001, mid - 0.01 * (nb - i))) for i in range(nb)],
        "asks": [level(min(0.999, mid + 0.01 * (na - i))) for i in range(na)],
        "event_type": "book", "tick_size": "0.001", "last_trade_price": f"{mid:.3f}",
    }


def _change(rng, asset_id):
    p = rng.uniform(0.05, 0.95)
    return {
        "market": "0x" + _hex(rng, 64),
        "price_changes": [{
            "asset_id": asset_id, "price": f"{p:.3f}", "size": f"{rng.uniform(1, 9999):.2f}",
            "side": "BUY", "hash": _hex(rng, 40),
            "best_bid": f"{p - 0.005:.3f}", "best_ask": f"{p + 0.005:.3f}",
        }],
        "timestamp": str(1761160000000 + rng.randrange(10**7)),
        "event_type": "price_change",
    }


async def serve_venue(port, cert, key):
    import websockets
    from websockets.asyncio.server import serve

    async def handler(ws):
        sub = json.loads(await ws.recv())
        ids = sub.get("assets_ids") or []
        rng = random.Random(hash(ids[0]) if ids else 0)
        await ws.send(json.dumps([_book(rng, a) for a in ids], separators=(",", ":")))

        async def pongs():
            async for message in ws:
                if message == "PING":
                    await ws.send("PONG")

        reader = asyncio.create_task(pongs())
        try:
            while ids:
                await asyncio.sleep(rng.expovariate(RATE_PER_SOCKET))
                await ws.send(json.dumps(_change(rng, rng.choice(ids)), separators=(",", ":")))
        except websockets.ConnectionClosed:
            pass
        finally:
            reader.cancel()

    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert, key)
    async with serve(handler, "127.0.0.1", port, max_size=None, ssl=context):
        print("READY", flush=True)
        await asyncio.Future()


def make_cert(directory):
    import datetime

    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder().subject_name(name).issuer_name(name)
        .public_key(key.public_key()).serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=2))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName("localhost")]), False)
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), True)
        .sign(key, hashes.SHA256())
    )
    cert_path, key_path = os.path.join(directory, "cert.pem"), os.path.join(directory, "key.pem")
    with open(cert_path, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))
    with open(key_path, "wb") as f:
        f.write(key.private_bytes(serialization.Encoding.PEM,
                                  serialization.PrivateFormat.PKCS8,
                                  serialization.NoEncryption()))
    return cert_path, key_path


# ------------------------------------------------------------------ child ----

def run_child(backend, url, cafile):
    app = os.path.join(backend, "app")
    client = _load("app.services.polymarket_ws", os.path.join(app, "services", "polymarket_ws.py"))
    process = _load("app.services.polymarket_ws_process",
                    os.path.join(app, "services", "polymarket_ws_process.py"))
    heap = _load("app.utils.heap_trim", os.path.join(app, "utils", "heap_trim.py"))
    import logging

    logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")
    client.WS_URL = url
    # The production shared-context path (#11218), trusting only the rig cert.
    client._TLS_CONTEXT = ssl.create_default_context(cafile=cafile)
    return asyncio.run(process.serve_receiver(
        client.PolymarketWebSocket,
        release_free_heap=lambda: heap.release_free_heap("polymarket_open_receiver"),
    ))


# -------------------------------------------------------------------- arm ----

def _proc_status(pid):
    out = {}
    try:
        with open(f"/proc/{pid}/status") as f:
            for line in f:
                key, _, value = line.partition(":")
                if key in ("VmRSS", "RssAnon", "RssFile", "VmSwap", "VmHWM"):
                    out[key] = int(value.split()[0]) / 1024
    except OSError:
        pass
    return out


async def run_arm(backend, seconds, n):
    import tempfile

    pwp = _load("rig_pwp", os.path.join(backend, "app", "services", "polymarket_ws_process.py"))
    here = os.path.abspath(__file__)
    tmp = tempfile.mkdtemp(prefix="rig10663-")
    cert, key = make_cert(tmp)
    probe = __import__("socket").socket()
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()
    server = subprocess.Popen([sys.executable, here, "server", str(port), cert, key],
                              stdout=subprocess.PIPE, text=True)
    try:
        assert server.stdout.readline().strip() == "READY"
        rng = random.Random(10663)
        ids = list(dict.fromkeys(str(rng.randrange(10**76, 10**77)) for _ in range(n)))
        proxy = pwp.PolymarketOpenReceiverProcess(
            max_concurrent_handshakes=4, max_queue=4, price_book_snapshots=True,
            command=[sys.executable, here, "child", backend,
                     f"wss://localhost:{port}/ws/market", cert],
        )
        prices = [0]

        async def on_price(_quote):
            prices[0] += 1

        proxy.on_price, proxy.on_trade = on_price, (lambda _m: None)
        run = asyncio.create_task(proxy.run_refreshable(ids, price_book_snapshots=True))
        started, samples, child = time.monotonic(), [], None
        while time.monotonic() - started < seconds:
            await asyncio.sleep(5)
            if run.done():
                run.result()
            if child is None and os.path.isdir("/proc"):  # Linux: the lab
                child = next((int(p) for p in os.listdir("/proc") if p.isdigit()
                              and _is_child(int(p))), None)
            if child is not None:
                samples.append(round(_proc_status(child).get("VmRSS", 0), 1))
        stats = proxy.stats
        end = _proc_status(child) if child else {}
        run.cancel()
        await asyncio.gather(run, return_exceptions=True)
        return {
            "rss_samples": samples, "end": end, "prices": prices[0],
            "served": stats.get("assets_served"), "subscribed": stats.get("assets_subscribed"),
            "shards": stats.get("shards"), "shards_connected": stats.get("shards_connected"),
            "messages": stats.get("messages"), "n": len(ids),
        }
    finally:
        server.send_signal(signal.SIGTERM)
        server.wait(10)


def _is_child(pid):
    try:
        with open(f"/proc/{pid}/stat") as f:
            ppid = int(f.read().rsplit(")", 1)[1].split()[1])
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            cmd = f.read().split(b"\0")
    except (OSError, ValueError, IndexError):
        return False
    return ppid == os.getpid() and b"child" in cmd


if __name__ == "__main__":
    mode = sys.argv[1]
    if mode == "server":
        asyncio.run(serve_venue(int(sys.argv[2]), sys.argv[3], sys.argv[4]))
    elif mode == "child":
        sys.exit(run_child(sys.argv[2], sys.argv[3], sys.argv[4]))
    else:
        result = asyncio.run(run_arm(sys.argv[2], float(sys.argv[3]), int(sys.argv[4])))
        print(json.dumps(result), flush=True)
