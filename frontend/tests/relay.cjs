/* A TCP relay to the server that a test can switch off, to cut the connection for real.

   The browser's offline switch (context.setOffline) doesn't reach a service worker, so a page's
   saved copy could seem to work while its requests still reached the server. Through a relay,
   once it is closed, nothing on that origin can reach the server: the page and its service
   worker are offline together, as in a power cut. */
const http = require('http');
const net = require('net');

function startRelay(target, options = {}) {
  if (target.protocol === 'https:' || options.http) return startForwarder(target, options);
  const sockets = new Set();
  const server = net.createServer((client) => {
    const upstream = net.connect(Number(target.port || 80), target.hostname);
    for (const s of [client, upstream]) {
      sockets.add(s);
      s.on('error', () => {});
      s.on('close', () => {
        sockets.delete(s);
        client.destroy();
        upstream.destroy();
      });
    }
    client.pipe(upstream).pipe(client);
  });
  return new Promise((resolve) =>
    server.listen(0, '127.0.0.1', () =>
      resolve({
        base: `http://127.0.0.1:${server.address().port}`,
        close: () =>
          new Promise((done) => {
            for (const s of sockets) s.destroy();
            server.close(() => done());
          }),
      }),
    ),
  );
}

// For a hosted copy over HTTPS (a Hugging Face Space), or with { http: true }: the same switch, one
// level up. Each request to the local address is sent on to the server, so the page has a local
// origin that a test can cut off. { vary } adds that Vary header to every answer, as some hosts
// do (a Space adds "Vary: origin"). Behind a proxy, run node with NODE_USE_ENV_PROXY=1.
const HOP = new Set(['host', 'connection', 'keep-alive', 'transfer-encoding', 'upgrade', 'proxy-connection', 'accept-encoding', 'content-length']);

function startForwarder(target, options = {}) {
  const sockets = new Set();
  const origin = `${target.protocol}//${target.host}`;
  const server = http.createServer(async (req, res) => {
    try {
      const headers = {};
      for (const [k, v] of Object.entries(req.headers)) if (!HOP.has(k)) headers[k] = v;
      const body = req.method === 'GET' || req.method === 'HEAD' ? undefined : req;
      const up = await fetch(origin + req.url, { method: req.method, headers, body, duplex: body ? 'half' : undefined, redirect: 'manual' });
      const out = {};
      up.headers.forEach((v, k) => {
        if (!['content-encoding', 'content-length', 'transfer-encoding', 'connection', 'strict-transport-security', 'set-cookie'].includes(k)) out[k] = v;
      });
      const cookies = up.headers.getSetCookie ? up.headers.getSetCookie() : [];
      if (cookies.length) out['set-cookie'] = cookies;
      if (options.vary) out.vary = out.vary ? `${out.vary}, ${options.vary}` : options.vary;
      res.writeHead(up.status, out);
      if (up.body && req.method !== 'HEAD') for await (const chunk of up.body) res.write(chunk);
      res.end();
    } catch (e) {
      if (!res.headersSent) res.writeHead(502, { 'content-type': 'text/plain' });
      res.end(`relay: ${e}`);
    }
  });
  server.on('connection', (s) => {
    sockets.add(s);
    s.on('close', () => sockets.delete(s));
  });
  return new Promise((resolve) =>
    server.listen(0, '127.0.0.1', () =>
      resolve({
        base: `http://127.0.0.1:${server.address().port}`,
        close: () =>
          new Promise((done) => {
            for (const s of sockets) s.destroy();
            server.close(() => done());
          }),
      }),
    ),
  );
}

async function reachable(url) {
  try {
    await fetch(url, { signal: AbortSignal.timeout(3000) });
    return true;
  } catch {
    return false;
  }
}

module.exports = { startRelay, reachable };
