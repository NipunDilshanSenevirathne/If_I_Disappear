/* If I Disappear: offline support.
   Pages and app files: network first, saved copy when offline.
   The family's saved handover (board, recordings, clips): network first, then the copy
   saved with "Save for offline". Video is answered in ranges so it can play offline.
   Every lookup ignores Vary: a host can add "Vary: Origin" to every response (a Hugging Face
   Space does), and the app's script and styles are asked for with an Origin header while the
   saved copies were stored without one, so offline they didn't match and the page stayed blank
   (found on the hosted copy, 1 November). */
const CACHE = 'iid-offline-v1';
const ANY = { ignoreVary: true };

self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', (event) => event.waitUntil(self.clients.claim()));

async function rangeFrom(cached, request) {
  const range = request.headers.get('range');
  if (!range) return cached;
  const blob = await cached.blob();
  const match = /bytes=(\d*)-(\d*)/.exec(range);
  const start = match && match[1] ? Number(match[1]) : 0;
  const end = match && match[2] ? Math.min(Number(match[2]), blob.size - 1) : blob.size - 1;
  return new Response(blob.slice(start, end + 1), {
    status: 206,
    headers: {
      'Content-Type': cached.headers.get('Content-Type') || 'application/octet-stream',
      'Content-Range': `bytes ${start}-${end}/${blob.size}`,
      'Content-Length': String(end - start + 1),
      'Accept-Ranges': 'bytes',
    },
  });
}

self.addEventListener('fetch', (event) => {
  const request = event.request;
  if (request.method !== 'GET') return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;

  if (request.mode === 'navigate') {
    event.respondWith(
      fetch(request).catch(async () => (await caches.match(url.pathname, ANY)) || (await caches.match('/index.html', ANY)) || (await caches.match('/', ANY)) || Response.error()),
    );
    return;
  }

  if (url.pathname.startsWith('/assets/') || url.pathname.startsWith('/icons/') || url.pathname.startsWith('/images/')) {
    event.respondWith(
      caches.match(request, ANY).then(
        (hit) =>
          hit ||
          fetch(request).then((response) => {
            if (response.ok && url.pathname.startsWith('/assets/')) {
              const copy = response.clone();
              caches.open(CACHE).then((cache) => cache.put(request, copy));
            }
            return response;
          }),
      ),
    );
    return;
  }

  if (url.pathname.startsWith('/api/h/') || url.pathname.startsWith('/api/s/')) {
    event.respondWith(
      fetch(request).catch(async () => {
        const media = url.pathname.includes('/media/');
        // A saved photo or clip is found by its path alone, because a sticker asks for it
        // with its own link rather than the one it was saved with.
        const cached =
          (await caches.match(url.pathname + url.search, ANY)) || (await caches.match(request, ANY)) || (media ? await caches.match(url.pathname, { ignoreSearch: true, ignoreVary: true }) : undefined);
        if (!cached) return Response.error();
        return media ? rangeFrom(cached, request) : cached;
      }),
    );
  }
});
