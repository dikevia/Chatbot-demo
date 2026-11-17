// Dikevia demo: network-only service worker.
// No application pages, questions, answers, or credentials are cached.
self.addEventListener("install", (event) => {
  event.waitUntil(self.skipWaiting());
});
self.addEventListener("activate", (event) => {
  event.waitUntil(self.clients.claim());
});
