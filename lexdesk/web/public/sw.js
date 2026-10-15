/*
  LexDesk service worker.

  Keeps the app shell (pages, scripts, fonts) available offline so the app
  opens instantly on a phone in a court corridor with one bar of signal.
  API responses are never cached here: they hold privileged client data and
  must always come fresh from the server.
*/
const SHELL = "lexdesk-shell-v2";

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(SHELL).then((c) => c.addAll(["/", "/login", "/offline", "/manifest.webmanifest", "/icon.svg"])).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== SHELL).map((k) => caches.delete(k)))).then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (event) => {
  const { request } = event;
  const url = new URL(request.url);
  if (request.method !== "GET" || url.pathname.startsWith("/api/")) return;

  const isStatic = url.pathname.startsWith("/_next/static/") || url.origin.includes("fonts.g");
  if (isStatic) {
    // Fingerprinted assets never change: cache first.
    event.respondWith(
      caches.match(request).then((hit) => hit || fetch(request).then((res) => {
        const copy = res.clone();
        caches.open(SHELL).then((c) => c.put(request, copy));
        return res;
      })),
    );
    return;
  }
  if (request.mode === "navigate") {
    // Pages: network first, the cached shell when offline.
    event.respondWith(
      fetch(request)
        .then((res) => {
          const copy = res.clone();
          caches.open(SHELL).then((c) => c.put(request, copy));
          return res;
        })
        .catch(() => caches.match(request).then((hit) => hit || caches.match("/offline"))),
    );
  }
});
