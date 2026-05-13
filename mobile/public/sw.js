/**
 * sw.js — Brevio PWA service worker.
 *
 * Two cache strategies are wired here, both intentionally simple — Workbox
 * would be overkill for a 5-route static-shell + read-only API.
 *
 *   1. App shell (HTML, JS, CSS, fonts, images): cache-first.
 *      Stale resources get evicted when CACHE_VERSION bumps.
 *
 *   2. /api/v1/* GETs: stale-while-revalidate. The user sees yesterday's
 *      digest instantly, while we silently refresh the cache in the
 *      background — perfect for a once-a-day product where data
 *      *eventually* matters but instant render matters always.
 *
 * Bump CACHE_VERSION whenever you ship a build that would otherwise serve
 * a mix of new HTML and stale JS chunks. Stale JS + new HTML is the most
 * common PWA footgun.
 */

const CACHE_VERSION = "brevio-v1";
const SHELL_CACHE   = `${CACHE_VERSION}-shell`;
const API_CACHE     = `${CACHE_VERSION}-api`;

// Minimal precache: just the entry point. Everything else gets cached
// lazily on first navigation. A heavy precache list would need to be
// regenerated on every build — not worth the build-script complexity
// for the marginal first-load gain.
const PRECACHE_URLS = ["/"];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(SHELL_CACHE).then((cache) => cache.addAll(PRECACHE_URLS)),
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((k) => !k.startsWith(CACHE_VERSION))
          .map((k) => caches.delete(k)),
      ),
    ),
  );
  self.clients.claim();
});

const isApiRequest = (url) =>
  url.pathname.startsWith("/api/v1/") ||
  url.hostname.endsWith(".modal.run");

const isShellAsset = (request) => {
  if (request.method !== "GET") return false;
  if (request.mode === "navigate") return true;
  const dest = request.destination;
  return (
    dest === "script" ||
    dest === "style" ||
    dest === "font" ||
    dest === "image" ||
    dest === "document"
  );
};

async function staleWhileRevalidate(request) {
  const cache  = await caches.open(API_CACHE);
  const cached = await cache.match(request);

  const network = fetch(request)
    .then((response) => {
      if (response && response.ok) {
        cache.put(request, response.clone()).catch(() => undefined);
      }
      return response;
    })
    .catch(() => cached);  // offline → fall back to whatever we had

  return cached ?? network;
}

async function cacheFirst(request) {
  const cache  = await caches.open(SHELL_CACHE);
  const cached = await cache.match(request);
  if (cached) return cached;

  try {
    const response = await fetch(request);
    if (response && response.ok && response.type === "basic") {
      cache.put(request, response.clone()).catch(() => undefined);
    }
    return response;
  } catch (err) {
    // Navigation fallback: serve the cached index for SPA routes when offline.
    if (request.mode === "navigate") {
      const fallback = await cache.match("/");
      if (fallback) return fallback;
    }
    throw err;
  }
}

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;

  let url;
  try {
    url = new URL(request.url);
  } catch {
    return;
  }

  if (isApiRequest(url)) {
    event.respondWith(staleWhileRevalidate(request));
    return;
  }

  if (isShellAsset(request)) {
    event.respondWith(cacheFirst(request));
  }
});
