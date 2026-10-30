'use strict';
// #10090 / #11674: the recorder's byte boundary.
//
// Chrome is launched with this loopback proxy as its only route out
// (`--proxy-server`, loopback NOT bypassed). Every byte the browser receives
// crosses `deliver()` below, which counts it BEFORE writing it and refuses the
// chunk that would cross the ceiling. So:
//   - forwarded overshoot is 0 bytes: the browser never receives a byte past the cap;
//   - received overshoot is at most one socket read (libuv: 64 KiB) held in
//     this process and discarded — the grant must authorize that bound;
//   - counted bytes are ENCODED wire bytes. HTTP bodies pass through with their
//     Content-Encoding untouched; an https CONNECT tunnel counts TLS records,
//     which is never less than the response bytes inside them.
// Streams without Content-Length (SSE) are counted chunk by chunk, the same as
// any other body; nothing waits for a response to finish.
// Request attempts are counted at the browser (route) layer, not here: one
// CONNECT tunnel can carry many requests.
const http = require('http');
const net = require('net');

function createTransport({allowOrigin, limits, onTrip, onEvent, fault = null}) {
  const counters = {response_bytes: 0, request_bytes: 0, http_requests: 0, tunnels: 0, refused_origins: 0,
    refused_chunks: 0, received_discarded_bytes: 0, max_received_chunk: 0, open_sockets: 0};
  const sockets = new Set();
  let tripped = null;
  let closed = false;

  function trip(kind, detail) {
    if (tripped) return;
    tripped = {kind, detail, at_response_bytes: counters.response_bytes, at_request_bytes: counters.request_bytes};
    for (const s of sockets) s.destroy();
    onTrip(tripped);
  }

  // Count-then-write. Returns false (and writes nothing) if the chunk would cross the cap.
  function deliver(sock, chunk) {
    counters.max_received_chunk = Math.max(counters.max_received_chunk, chunk.length);
    if (tripped || closed) { counters.received_discarded_bytes += chunk.length; return false; }
    if (counters.response_bytes + chunk.length > limits.max_response_bytes) {
      counters.refused_chunks++;
      counters.received_discarded_bytes += chunk.length;
      trip('max_response_bytes', {chunk: chunk.length, cap: limits.max_response_bytes});
      return false;
    }
    counters.response_bytes += chunk.length;
    sock.write(chunk);
    return true;
  }
  function sendUp(sock, chunk) {
    if (tripped || closed) return false;
    if (counters.request_bytes + chunk.length > limits.max_request_bytes) {
      trip('max_request_bytes', {chunk: chunk.length, cap: limits.max_request_bytes});
      return false;
    }
    counters.request_bytes += chunk.length;
    sock.write(chunk);
    return true;
  }
  function track(sock) {
    sockets.add(sock);
    counters.open_sockets = sockets.size;
    sock.on('close', () => { sockets.delete(sock); counters.open_sockets = sockets.size; });
    sock.on('error', () => {});
  }

  const server = http.createServer();
  server.keepAliveTimeout = 0;

  // Absolute-form http:// requests (the local scope's loopback origins).
  server.on('request', (req, res) => {
    let target;
    try { target = new URL(req.url); } catch { res.destroy(); return; }
    const origin = target.origin;
    if (target.protocol !== 'http:' || !allowOrigin(origin)) {
      counters.refused_origins++;
      onEvent({kind: 'transport-refused-origin', origin, method: req.method});
      res.destroy();
      return;
    }
    counters.http_requests++;
    const head = `${req.method} ${target.pathname}${target.search} HTTP/1.1\r\n` +
      Object.entries(req.headers).map(([k, v]) => `${k}: ${v}`).join('\r\n') + '\r\n\r\n';
    if (counters.request_bytes + Buffer.byteLength(head) > limits.max_request_bytes) {
      trip('max_request_bytes', {head: Buffer.byteLength(head)});
      res.destroy();
      return;
    }
    counters.request_bytes += Buffer.byteLength(head);
    const headers = {...req.headers};
    delete headers['proxy-connection'];
    headers.connection = 'close';
    const up = http.request({host: target.hostname, port: target.port || 80, method: req.method,
      path: target.pathname + target.search, headers, agent: false});
    up.on('socket', s => track(s));
    req.on('data', chunk => {
      if (counters.request_bytes + chunk.length > limits.max_request_bytes) { trip('max_request_bytes', {chunk: chunk.length}); return; }
      counters.request_bytes += chunk.length;
      up.write(chunk);
    });
    req.on('end', () => up.end());
    up.on('error', () => res.destroy());
    up.on('response', upRes => {
      // Serialize the head ourselves so the counted bytes are the written bytes.
      const lines = [`HTTP/1.1 ${upRes.statusCode} ${upRes.statusMessage || ''}`];
      for (let i = 0; i < upRes.rawHeaders.length; i += 2) {
        const k = upRes.rawHeaders[i];
        if (['connection', 'keep-alive', 'proxy-connection'].includes(k.toLowerCase())) continue;
        lines.push(`${k}: ${upRes.rawHeaders[i + 1]}`);
      }
      lines.push('Connection: close', '', '');
      const sock = res.socket;
      track(sock);
      res.detachSocket?.(sock);
      if (!deliver(sock, Buffer.from(lines.join('\r\n')))) { upRes.destroy(); return; }
      if (fault && fault.onResponse) fault.onResponse(target, sock);
      // The upstream body arrives already framed (chunked or length-delimited)
      // only at the socket level; Node has de-chunked it here. Re-frame chunked
      // bodies exactly as received so the browser's parser sees the same body.
      const chunked = /chunked/i.test(upRes.headers['transfer-encoding'] || '');
      upRes.on('data', chunk => {
        const framed = chunked ? Buffer.concat([Buffer.from(chunk.length.toString(16) + '\r\n'), chunk, Buffer.from('\r\n')]) : chunk;
        if (!deliver(sock, framed)) upRes.destroy();
      });
      upRes.on('end', () => {
        if (chunked) deliver(sock, Buffer.from('0\r\n\r\n'));
        sock.end();
      });
      upRes.on('error', () => sock.destroy());
      sock.on('close', () => upRes.destroy());
    });
  });

  // https:// via CONNECT (the production scope). TLS is end-to-end; bytes are counted raw.
  server.on('connect', (req, clientSock, headBuf) => {
    track(clientSock);
    const [host, portStr] = req.url.split(':');
    const port = Number(portStr);
    const origin = port === 443 ? `https://${host}` : `https://${host}:${port}`;
    if (!allowOrigin(origin)) {
      counters.refused_origins++;
      onEvent({kind: 'transport-refused-origin', origin, method: 'CONNECT'});
      clientSock.destroy();
      return;
    }
    counters.tunnels++;
    const up = net.connect(port, host);
    track(up);
    up.on('connect', () => {
      if (!deliver(clientSock, Buffer.from('HTTP/1.1 200 Connection Established\r\n\r\n'))) { up.destroy(); return; }
      if (headBuf && headBuf.length) sendUp(up, headBuf);
      up.on('data', chunk => { if (!deliver(clientSock, chunk)) up.destroy(); });
      clientSock.on('data', chunk => { if (!sendUp(up, chunk)) clientSock.destroy(); });
      up.on('end', () => clientSock.end());
      clientSock.on('end', () => up.end());
    });
    up.on('error', () => clientSock.destroy());
    clientSock.on('close', () => up.destroy());
    up.on('close', () => clientSock.destroy());
  });
  server.on('connection', s => track(s));

  return {
    counters,
    get tripped() { return tripped; },
    trip,
    listen() {
      return new Promise((resolve, reject) => {
        server.once('error', reject);
        server.listen(0, '127.0.0.1', () => resolve(server.address().port));
      });
    },
    // Destroys every socket; no request outlives the recorder's teardown.
    close() {
      closed = true;
      for (const s of sockets) s.destroy();
      return new Promise(resolve => server.close(() => resolve()));
    },
  };
}

module.exports = {createTransport};
