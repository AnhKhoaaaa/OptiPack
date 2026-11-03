// OptiPack Progressive Web App Service Worker
const CACHE_NAME = "optipack-pwa-v1";
const STATIC_ASSETS = [
  "/",
  "/index.html",
  "/manifest.webmanifest",
  "/icons/icon-192.png",
  "/icons/icon-512.png",
  "/icons/apple-touch-icon.png",
  "/icons/favicon-32.png",
  "/icons/icon.svg"
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(STATIC_ASSETS).catch((err) => {
        console.warn("[SW] Cache prefetch warning:", err);
      });
    })
  );
  self.skipWaiting();
});

// P1 Fix: Only clean up older OptiPack caches, never wipe other apps on the same origin
self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys
          .filter((key) => key.startsWith("optipack-pwa-") && key !== CACHE_NAME)
          .map((key) => caches.delete(key))
      );
    })
  );
  self.clients.claim();
});

// P0 Fix: Dynamic runtime caching for JS/CSS bundles and fonts so PWA functions 100% offline
self.addEventListener("fetch", (event) => {
  // Pass through non-GET and API calls directly to the network
  if (event.request.method !== "GET" || event.request.url.includes("/api/")) {
    return;
  }

  event.respondWith(
    caches.match(event.request).then((cachedResponse) => {
      if (cachedResponse) {
        // Return cached immediately; update in background (stale-while-revalidate)
        fetch(event.request)
          .then((networkResponse) => {
            if (networkResponse && networkResponse.status === 200 && networkResponse.type === "basic") {
              const clone = networkResponse.clone();
              caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
            }
          })
          .catch(() => {});
        return cachedResponse;
      }

      // Cache miss (e.g. /assets/index-xxx.js, /assets/index-xxx.css, web fonts):
      // Fetch from network and dynamically store in cache for offline reloads!
      return fetch(event.request)
        .then((networkResponse) => {
          if (!networkResponse || networkResponse.status !== 200) {
            return networkResponse;
          }
          // Only cache same-origin assets or specific cross-origin font CDNs
          const url = new URL(event.request.url);
          const isSameOrigin = url.origin === self.location.origin;
          const isFontCDN = url.hostname.includes("fonts.googleapis.com") || url.hostname.includes("fonts.gstatic.com");

          if (isSameOrigin || isFontCDN) {
            const clone = networkResponse.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
          }
          return networkResponse;
        })
        .catch(() => {
          // If offline and requesting root document, return cached index.html
          if (event.request.mode === "navigate") {
            return caches.match("/index.html");
          }
        });
    })
  );
});
