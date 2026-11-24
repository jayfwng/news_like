// 앱 화면은 저장해 두고(오프라인 실행), 뉴스는 항상 새로 받되 안 되면 저장본을 보여줘요.
const VERSION = "v1";
const SHELL = [
  "./", "index.html", "css/app.css", "js/app.js", "js/glossary.js",
  "manifest.webmanifest", "icons/icon.svg", "icons/icon-192.png",
];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(`shell-${VERSION}`).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== `shell-${VERSION}` && k !== "news").map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.origin !== location.origin) return;
  if (url.pathname.endsWith("/data/news.json")) {
    e.respondWith(
      fetch(e.request)
        .then((res) => {
          if (res.ok) { const copy = res.clone(); caches.open("news").then((c) => c.put("news.json", copy)); }
          return res;
        })
        .catch(() => caches.open("news").then((c) => c.match("news.json")).then((r) => r || Response.error()))
    );
    return;
  }
  // 앱 화면: 네트워크 먼저(업데이트 반영), 실패하면 저장본
  e.respondWith(
    fetch(e.request)
      .then((res) => {
        if (res.ok) { const copy = res.clone(); caches.open(`shell-${VERSION}`).then((c) => c.put(e.request, copy)); }
        return res;
      })
      .catch(() => caches.match(e.request).then((r) => r || caches.match("index.html")))
  );
});
