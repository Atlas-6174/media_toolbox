const CACHE_NAME = "mediabox-v1";

self.addEventListener("install", (e) => {
  e.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(["/", "/static/manifest.json", "/static/icon.svg"]);
    })
  );
});

self.addEventListener("fetch", (e) => {
  // Network first con fallback a cache
  e.respondWith(
    fetch(e.request).catch(() => caches.match(e.request))
  );
});
