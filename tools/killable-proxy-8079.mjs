// killable-proxy-8079.mjs — live/515. A forward proxy whose connections can actually be SEVERED.
//
// WHY THIS EXISTS. `context.setOffline(true)` was measured (sse-cut-instrument-check-8079.mjs, this
// directory) to block only NEW requests: across a 50 s "offline" window the page's established SSE
// stream kept receiving heartbeats at readyState 1, dead on the 20 s cadence, while sibling fetches
// failed with ERR_INTERNET_DISCONNECTED. A reconnect test built on that would have reported "push
// survived the outage" — the instrument's failure mode wearing the healthy result's face.
//
// So the cut has to happen at the socket. The browser is pointed at this proxy; this proxy chains
// to the sandbox's real egress proxy; and on command it destroys every live socket and refuses new
// ones, which is what a phone losing signal does to an open stream.
//
// CONTROL PLANE. Plain HTTP on the same port (CONNECT and GET coexist on one node server):
//   GET /__cut      destroy all live sockets, refuse new CONNECTs
//   GET /__restore  allow new CONNECTs again
//   GET /__stat     {cut, live, opened, killed, refused}
// Called from the rig over 127.0.0.1, which never goes through the proxy itself.
//
// WHAT IT IS NOT: a TLS interceptor. It only tunnels CONNECT, so it never sees or alters payload
// bytes — the page talks real TLS to real production. That also means it cannot fake a response;
// it can only carry bytes or stop carrying them.
import net from 'net';
import http from 'http';
import { URL } from 'url';

const PORT = Number(process.env.PROXY_PORT || 10555);
const UPSTREAM = process.env.UPSTREAM_PROXY || process.env.HTTPS_PROXY || process.env.HTTP_PROXY || '';

let cut = false;
const live = new Set();
const stats = { opened: 0, killed: 0, refused: 0 };

const track = (sock) => {
  live.add(sock);
  sock.once('close', () => live.delete(sock));
  sock.on('error', () => { try { sock.destroy(); } catch { /* already gone */ } });
};

const killAll = () => {
  let n = 0;
  for (const s of [...live]) { try { s.destroy(); n += 1; } catch { /* already gone */ } }
  live.clear();
  stats.killed += n;
  return n;
};

const server = http.createServer((req, res) => {
  // Control plane only. This proxy is not a general HTTP forward proxy; the page uses CONNECT for
  // everything because production is https.
  const path = (req.url || '').split('?')[0];
  if (path === '/__cut') {
    cut = true;
    const n = killAll();
    res.writeHead(200, { 'content-type': 'application/json' });
    return res.end(JSON.stringify({ ok: true, cut, killed: n }));
  }
  if (path === '/__restore') {
    cut = false;
    res.writeHead(200, { 'content-type': 'application/json' });
    return res.end(JSON.stringify({ ok: true, cut }));
  }
  if (path === '/__stat') {
    res.writeHead(200, { 'content-type': 'application/json' });
    return res.end(JSON.stringify({ cut, live: live.size, ...stats }));
  }
  res.writeHead(404); res.end('no');
});

server.on('connect', (req, clientSock, head) => {
  if (cut) {
    stats.refused += 1;
    try { clientSock.destroy(); } catch { /* client already gone */ }
    return;
  }
  stats.opened += 1;
  const [host, portStr] = (req.url || '').split(':');
  const port = Number(portStr || 443);

  const wire = (upSock) => {
    if (cut) { try { upSock.destroy(); clientSock.destroy(); } catch { /* raced with a cut */ } return; }
    track(clientSock); track(upSock);
    clientSock.write('HTTP/1.1 200 Connection Established\r\n\r\n');
    if (head && head.length) upSock.write(head);
    upSock.pipe(clientSock);
    clientSock.pipe(upSock);
  };

  if (UPSTREAM) {
    // Chain: issue our own CONNECT to the sandbox's egress proxy and splice the tunnels.
    const u = new URL(UPSTREAM);
    const upSock = net.connect(Number(u.port || 80), u.hostname, () => {
      upSock.write(`CONNECT ${host}:${port} HTTP/1.1\r\nHost: ${host}:${port}\r\n\r\n`);
    });
    let banner = '';
    const onData = (chunk) => {
      banner += chunk.toString('latin1');
      const end = banner.indexOf('\r\n\r\n');
      if (end === -1) return;
      upSock.removeListener('data', onData);
      if (!/^HTTP\/1\.[01] 200/.test(banner)) { try { clientSock.destroy(); upSock.destroy(); } catch { /* gone */ } return; }
      const rest = Buffer.from(banner.slice(end + 4), 'latin1');
      wire(upSock);
      if (rest.length) clientSock.write(rest);
    };
    upSock.on('data', onData);
    upSock.on('error', () => { try { clientSock.destroy(); } catch { /* gone */ } });
  } else {
    const upSock = net.connect(port, host, () => wire(upSock));
    upSock.on('error', () => { try { clientSock.destroy(); } catch { /* gone */ } });
  }
});

server.listen(PORT, '127.0.0.1', () => {
  process.stdout.write(`killable_proxy listening 127.0.0.1:${PORT} upstream=${UPSTREAM || 'direct'}\n`);
});
