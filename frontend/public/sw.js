// Built by frontend/scripts/build-pwa.mjs. This source is copied to dist/ by Vite.
// The build script injects hashed JS/CSS assets before publishing the service worker.
const CACHE_NAME = "__CACHE_NAME__";
const BUILD_ASSETS = __BUILD_ASSETS__;
const STATIC_ASSETS = [
  "/",
  "/index.html",
  "/manifest.webmanifest",
  "/icons/icon-192.png",
  "/icons/icon-512.png",
  "/icons/apple-touch-icon.png",
  "/icons/favicon-32.png",
  "/icons/icon.svg",
  "/samples/topdown_sample.jpg",
  "/samples/oblique_sample.jpg",
];

self.addEventListener("install", (event) => {
  // Installation only succeeds when the app shell *and* hashed bundles are cached.
  // This enables offline startup after the first online visit (no extra reload).
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) => cache.addAll([...STATIC_ASSETS, ...BUILD_ASSETS]))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then(async (names) => {
      await Promise.all(
        names.filter((name) => name.startsWith("optipack-pwa-") && name !== CACHE_NAME)
          .map((name) => caches.delete(name))
      );
      await self.clients.claim();
    })
  );
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  const url = new URL(request.url);
  // Never cache analysis/solver API calls or cross-origin traffic.
  if (request.method !== "GET" || url.origin !== self.location.origin || url.pathname.startsWith("/api/")) {
    return;
  }
  event.respondWith((async () => {
    // Precached asset responses can carry Vary: Origin, while module requests
    // include different headers. Both reference identical public static assets.
    const cached = await caches.match(request, { ignoreVary: true });
    if (cached) return cached;
    try {
      const response = await fetch(request);
      if (response.ok) {
        // Await persistence so an offline navigation cannot race the cache write.
        const cache = await caches.open(CACHE_NAME);
        await cache.put(request, response.clone());
      }
      return response;
    } catch (error) {
      if (request.mode === "navigate") {
        const index = await caches.match("/index.html");
        if (index) return index;
      }
      throw error;
    }
  })());
});
