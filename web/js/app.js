import { GLOSSARY, buildIndex } from "./glossary.js";

const $ = (s, el = document) => el.querySelector(s);
const DICT = buildIndex();
const STORY_MS = 8000;

// ───────────────────────────────── 저장소 (이 기기에만)
const store = {
  get(key, fallback) {
    try { const v = localStorage.getItem(key); return v ? JSON.parse(v) : fallback; } catch { return fallback; }
  },
  set(key, val) {
    try { localStorage.setItem(key, JSON.stringify(val)); } catch { /* 저장 불가 */ }
  },
};
const state = {
  data: null,
  filter: store.get("filter", "all"),
  saved: store.get("saved", {}),        // id → story
  words: store.get("words", {}),        // term → {def, cat, at}
  read: new Set(store.get("read", [])), // 읽은 기사 id
  seenTopics: store.get("seenTopics", {}), // topic → generated_at
};
function saveRead() { store.set("read", [...state.read].slice(-800)); }

// ───────────────────────────────── 글자 처리
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

// 긴 용어부터 찾도록 정렬한 정규식
const TERM_KEYS = [...DICT.keys()].sort((a, b) => b.length - a.length);
const TERM_RE = new RegExp(TERM_KEYS.map((k) => k.replace(/[.*+?^${}()|[\]\\/]/g, "\\$&")).join("|"), "g");
// 다른 낱말의 일부일 때는 밑줄 긋지 않기 (예: '전세계'의 '전세')
const NOT_FOLLOWED = { "전세": /^[계기]/ };
const ASCII_WORD = /[A-Za-z0-9]/;

function withTerms(text, used = new Set()) {
  const src = String(text ?? "");
  let out = "", last = 0;
  for (const m of src.matchAll(TERM_RE)) {
    const k = m[0], i = m.index, after = src.slice(i + k.length);
    if (NOT_FOLLOWED[k] && NOT_FOLLOWED[k].test(after)) continue;
    // 영문 약어는 단어 경계에서만 (예: 'PF'가 'PFAS'에 걸리지 않게)
    if (ASCII_WORD.test(k[0]) && (ASCII_WORD.test(src[i - 1] || "") || ASCII_WORD.test(after[0] || ""))) continue;
    const entry = DICT.get(k);
    if (used.has(entry.term)) continue; // 한 기사에 같은 용어는 한 번만
    used.add(entry.term);
    out += esc(src.slice(last, i)) + `<button class="term" data-term="${esc(entry.term)}">${esc(k)}</button>`;
    last = i + k.length;
  }
  return out + esc(src.slice(last));
}

function termsIn(text) {
  const found = new Set();
  for (const m of String(text).matchAll(TERM_RE)) {
    const k = m[0], after = text.slice(m.index + k.length);
    if (NOT_FOLLOWED[k] && NOT_FOLLOWED[k].test(after)) continue;
    if (ASCII_WORD.test(k[0]) && (ASCII_WORD.test(text[m.index - 1] || "") || ASCII_WORD.test(after[0] || ""))) continue;
    found.add(DICT.get(k).term);
  }
  return found;
}

function timeAgo(iso) {
  if (!iso) return "";
  const m = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
  if (m < 1) return "방금";
  if (m < 60) return `${m}분 전`;
  const h = Math.round(m / 60);
  if (h < 24) return `${h}시간 전`;
  return `${Math.round(h / 24)}일 전`;
}

const PALETTE = ["#e1306c", "#f77737", "#833ab4", "#405de6", "#0a9396", "#2a9d8f", "#e76f51", "#6d597a", "#1d3557", "#bc4749"];
function colorFor(s) {
  let h = 0;
  for (const c of String(s)) h = (h * 31 + c.codePointAt(0)) >>> 0;
  return PALETTE[h % PALETTE.length];
}
const TOPIC_GRADIENT = {
  economy: "linear-gradient(135deg,#0f9b8e,#1d4ed8)", stock: "linear-gradient(135deg,#ef4444,#7c3aed)",
  rate: "linear-gradient(135deg,#0ea5e9,#4338ca)", realestate: "linear-gradient(135deg,#f59e0b,#b45309)",
  industry: "linear-gradient(135deg,#64748b,#0f172a)", politics: "linear-gradient(135deg,#6366f1,#1e3a8a)",
  society: "linear-gradient(135deg,#14b8a6,#166534)", world: "linear-gradient(135deg,#06b6d4,#1e40af)",
  tech: "linear-gradient(135deg,#a855f7,#db2777)", top: "linear-gradient(135deg,#f97316,#e11d48)",
};
const topicInfo = (id) => state.data?.topics.find((t) => t.id === id) || { id, name: id, emoji: "📰" };
const mainTopic = (s) => s.topics.find((t) => t !== "top") || "top";

// ───────────────────────────────── 데이터 불러오기
async function load(force = false) {
  const btn = $("#refresh");
  btn.classList.add("spin");
  try {
    const res = await fetch("data/news.json", { cache: force ? "reload" : "no-cache" });
    if (!res.ok) throw new Error(res.status);
    state.data = await res.json();
    render();
    if (force) toast("새 소식을 불러왔어요");
  } catch (e) {
    if (!state.data) {
      $("#feed").innerHTML = `<p class="empty">뉴스를 불러오지 못했어요.<br>인터넷 연결을 확인하거나, 아직 첫 수집이 끝나지 않았다면 잠시 뒤 다시 열어 주세요.</p>`;
    } else toast("새로고침에 실패했어요");
  } finally {
    btn.classList.remove("spin");
  }
}

function render() {
  const d = state.data;
  $("#updated").textContent = d.generated_at ? `${timeAgo(d.generated_at)} 업데이트` : "";
  renderMarket(d.market || []);
  renderStoriesRow();
  renderTodayTerms();
  renderFilters();
  renderFeed();
}

function renderMarket(list) {
  const el = $("#market");
  el.hidden = !list.length;
  el.innerHTML = list.map((m) => {
    const dir = m.change > 0 ? "up" : m.change < 0 ? "down" : "";
    const arrow = m.change > 0 ? "▲" : m.change < 0 ? "▼" : "";
    const price = Number(m.price).toLocaleString("ko-KR", { minimumFractionDigits: m.digits, maximumFractionDigits: m.digits });
    const unit = m.unit === "$" ? "$" : "";
    const tail = m.unit && m.unit !== "$" ? m.unit : "";
    return `<button class="tick ${dir}" data-term="${esc(m.name)}">
      <span class="name">${esc(m.name)}</span>
      <span class="price">${unit}${price}${tail}</span>
      <span class="chg">${m.change == null ? "" : `${arrow}${Math.abs(m.change).toFixed(2)}%`}</span>
    </button>`;
  }).join("");
}

function storiesFor(topic) {
  const list = state.data.stories.filter((s) => topic === "all" || s.topics.includes(topic));
  return list;
}

function renderStoriesRow() {
  const d = state.data;
  $("#stories").innerHTML = d.topics.map((t) => {
    const n = storiesFor(t.id).length;
    if (!n) return "";
    const seen = state.seenTopics[t.id] === d.generated_at;
    return `<button class="story-btn ${seen ? "seen" : ""}" data-story="${t.id}">
      <span class="story-ring"><span>${t.emoji}</span></span>
      <span class="label">${esc(t.name)}</span>
    </button>`;
  }).join("");
}

function renderTodayTerms() {
  const counts = new Map();
  for (const s of state.data.stories.slice(0, 150)) {
    for (const t of termsIn(s.title + " " + s.summary)) counts.set(t, (counts.get(t) || 0) + 1);
  }
  const top = [...counts.entries()].filter(([, n]) => n >= 2).sort((a, b) => b[1] - a[1]).slice(0, 12);
  $("#today-terms").hidden = !top.length;
  $("#term-chips").innerHTML = top.map(([t, n]) => `<button class="chip" data-term="${esc(t)}">${esc(t)}<span class="n">${n}</span></button>`).join("");
}

function renderFilters() {
  const tabs = [{ id: "all", name: "전체" }, ...state.data.topics.filter((t) => t.id !== "top")];
  $("#filters").innerHTML = tabs.map((t) =>
    `<button class="chip ${state.filter === t.id ? "active" : ""}" data-filter="${t.id}">${esc(t.name)}</button>`
  ).join("");
}

function postHTML(s) {
  const t = mainTopic(s);
  const info = topicInfo(t);
  const used = new Set();
  const others = s.outlets.filter((o) => o.name !== s.outlet);
  const n = s.outlets.length;
  const hot = n >= 4 || s.popular >= 1.5;
  const tags = s.topics.filter((x) => x !== "top").slice(0, 2).map((x) => `<span class="tag">${esc(topicInfo(x).name)}</span>`).join("");
  const placeholder = `<div class="placeholder" style="background:${TOPIC_GRADIENT[t] || TOPIC_GRADIENT.top}"><div><span class="emoji">${info.emoji}</span>${esc(s.title)}</div></div>`;
  const media = s.image
    ? `<img src="${esc(s.image)}" alt="" loading="lazy" referrerpolicy="no-referrer" data-fallback="1">`
    : placeholder;
  const saved = !!state.saved[s.id];
  return `<article class="post ${state.read.has(s.id) ? "read" : ""}" data-id="${s.id}">
    <div class="post-head">
      <span class="avatar" style="background:${colorFor(s.outlet)}">${esc(s.outlet.slice(0, 1))}</span>
      <div class="post-meta"><div class="outlet">${esc(s.outlet)}</div><div class="time">${timeAgo(s.published)}</div></div>
      ${n >= 2 || s.popular ? `<span class="badge ${hot ? "hot" : ""}">${hot ? "🔥 " : ""}${n >= 2 ? `${n}곳 보도` : "많이 본 뉴스"}</span>` : ""}
    </div>
    <a class="post-media" href="${esc(s.url)}" target="_blank" rel="noopener" data-open="${s.id}">
      ${media}<template>${placeholder}</template>
      <div class="tags">${tags}</div>
    </a>
    <div class="post-actions">
      <button class="icon-btn ${saved ? "on" : ""}" data-save="${s.id}" aria-label="저장"><svg viewBox="0 0 24 24"><path d="M6 3h12v18l-6-4-6 4z"/></svg></button>
      <button class="icon-btn" data-share="${s.id}" aria-label="공유"><svg viewBox="0 0 24 24"><path d="M22 2 11 13M22 2l-7 20-4-9-9-4z"/></svg></button>
      <span class="grow"></span>
      <a class="read-link" href="${esc(s.url)}" target="_blank" rel="noopener" data-open="${s.id}">원문 보기 ↗</a>
    </div>
    <div class="post-body">
      <h3 class="post-title">${withTerms(s.title, used)}</h3>
      <p class="post-summary ${s.summary ? "" : "empty"}">${withTerms(s.summary, used)}</p>
      ${others.length ? `<button class="more-outlets" data-more="${s.id}">다른 언론사 ${others.length}곳 기사 보기</button>
      <ul class="outlet-list" hidden>${others.map((o) => `<li><a href="${esc(o.url)}" target="_blank" rel="noopener" data-open="${s.id}"><b>${esc(o.name)}</b>${esc(o.title)}</a></li>`).join("")}</ul>` : ""}
    </div>
  </article>`;
}

function renderFeed() {
  const list = storiesFor(state.filter);
  $("#feed").innerHTML = list.length ? list.map(postHTML).join("") : `<p class="empty">이 분야에는 아직 뉴스가 없어요.</p>`;
  $("#feed-end").hidden = !list.length;
  wireImages($("#feed"));
}

function wireImages(root) {
  root.querySelectorAll("img[data-fallback]").forEach((img) => {
    const swap = () => { const tpl = img.nextElementSibling; if (tpl?.tagName === "TEMPLATE") img.replaceWith(tpl.content.cloneNode(true)); };
    img.addEventListener("error", swap, { once: true });
    if (img.complete && img.naturalWidth === 0 && img.src) swap();
  });
}

function renderSaved() {
  const list = Object.values(state.saved).sort((a, b) => (b.savedAt || 0) - (a.savedAt || 0));
  $("#saved-feed").innerHTML = list.map(postHTML).join("");
  $("#saved-empty").hidden = list.length > 0;
  wireImages($("#saved-feed"));
}

function renderWords() {
  const mine = Object.entries(state.words).sort((a, b) => b[1].at - a[1].at);
  $("#word-list").innerHTML = mine.map(([t, w]) => `<button class="word" data-term="${esc(t)}"><b>${esc(t)}</b><small>${esc(w.cat || "")}</small><p>${esc(w.def)}</p></button>`).join("");
  $("#words-empty").hidden = mine.length > 0;
  renderDict($("#dict-search").value);
}

function renderDict(q = "") {
  q = q.trim().toLowerCase();
  const list = GLOSSARY.filter(([t, a, d]) => !q || t.toLowerCase().includes(q) || a.some((x) => x.toLowerCase().includes(q)) || d.includes(q));
  $("#dict-list").innerHTML = list.map(([t, , d, c]) => `<button class="word" data-term="${esc(t)}"><b>${esc(t)}</b><small>${esc(c)}</small><p>${esc(d)}</p></button>`).join("")
    || `<p class="empty">사전에 없는 말이에요. <button class="term" data-lookup="${esc(q)}">'${esc(q)}' 위키백과에서 찾기</button></p>`;
}

// ───────────────────────────────── 화면 전환
function showView(name) {
  for (const v of ["home", "saved", "words"]) $(`#view-${v}`).hidden = v !== name;
  document.querySelectorAll(".tabbar button").forEach((b) => b.classList.toggle("active", b.dataset.view === name));
  if (name === "saved") renderSaved();
  if (name === "words") renderWords();
  window.scrollTo({ top: 0 });
}

// ───────────────────────────────── 스토리 보기
const story = { list: [], i: 0, timer: 0, start: 0, left: STORY_MS, paused: false, topic: null };

function openStory(topic) {
  const list = storiesFor(topic).slice(0, 10);
  if (!list.length) return;
  Object.assign(story, { list, i: 0, topic });
  $("#story-topic").textContent = `${topicInfo(topic).emoji} ${topicInfo(topic).name}`;
  $("#story-bars").innerHTML = list.map(() => "<i><b></b></i>").join("");
  $("#story-viewer").hidden = false;
  document.body.style.overflow = "hidden";
  state.seenTopics[topic] = state.data.generated_at;
  store.set("seenTopics", state.seenTopics);
  showStory(0);
}

function showStory(i) {
  if (i < 0) i = 0;
  if (i >= story.list.length) return closeStory();
  story.i = i;
  const s = story.list[i];
  state.read.add(s.id); saveRead();
  const bars = $("#story-bars").children;
  [...bars].forEach((b, k) => { b.classList.toggle("done", k < i); b.firstElementChild.style.cssText = ""; });
  const t = mainTopic(s);
  const bg = s.image ? `background-image:url('${encodeURI(s.image).replace(/'/g, "%27")}')` : `background:${TOPIC_GRADIENT[t] || TOPIC_GRADIENT.top}`;
  const used = new Set();
  $("#story-body").innerHTML = `<div class="story-bg" style="${bg}"></div>
    <div class="story-content">
      <div class="src">${esc(s.outlet)} · ${timeAgo(s.published)}${s.outlets.length >= 2 ? ` · ${s.outlets.length}곳 보도` : ""}</div>
      <h2>${withTerms(s.title, used)}</h2>
      ${s.summary ? `<p>${withTerms(s.summary, used)}</p>` : ""}
      <a class="go" href="${esc(s.url)}" target="_blank" rel="noopener">원문 보기 ↗</a>
    </div>`;
  story.left = STORY_MS;
  story.paused = false;
  runStoryTimer();
}

function runStoryTimer() {
  clearTimeout(story.timer);
  const bar = $("#story-bars").children[story.i]?.firstElementChild;
  if (!bar) return;
  const done = 1 - story.left / STORY_MS;
  bar.style.transition = "none";
  bar.style.width = `${done * 100}%`;
  bar.offsetWidth; // 다시 그리기
  bar.style.transition = `width ${story.left}ms linear`;
  bar.style.width = "100%";
  story.start = performance.now();
  story.timer = setTimeout(() => showStory(story.i + 1), story.left);
}

function pauseStory() {
  if (story.paused || $("#story-viewer").hidden) return;
  story.paused = true;
  clearTimeout(story.timer);
  story.left = Math.max(0, story.left - (performance.now() - story.start));
  const bar = $("#story-bars").children[story.i]?.firstElementChild;
  if (bar) { bar.style.transition = "none"; bar.style.width = `${(1 - story.left / STORY_MS) * 100}%`; }
}
function resumeStory() {
  if (!story.paused || $("#story-viewer").hidden || !$("#sheet").hidden) return;
  story.paused = false;
  runStoryTimer();
}
function closeStory() {
  clearTimeout(story.timer);
  $("#story-viewer").hidden = true;
  document.body.style.overflow = "";
  renderStoriesRow();
  markReadInFeed();
}
function markReadInFeed() {
  document.querySelectorAll(".post").forEach((p) => p.classList.toggle("read", state.read.has(p.dataset.id)));
}

// ───────────────────────────────── 단어 뜻 시트
let sheetTerm = null;

function openSheet(term) {
  pauseStory();
  hideFab();
  const entry = DICT.get(term) || marketEntry(term);
  sheetTerm = entry ? entry.term : term;
  $("#sheet-term").textContent = sheetTerm;
  $("#sheet-cat").textContent = entry?.cat || "검색";
  $("#sheet-cat").hidden = false;
  const body = $("#sheet-body");
  if (entry) {
    body.innerHTML = `<p style="margin:0">${esc(entry.def)}</p>${entry.aliases?.length ? `<p style="margin:8px 0 0;color:var(--text-2);font-size:13px">다른 표기: ${esc(entry.aliases.join(", "))}</p>` : ""}<div class="wiki" id="wiki-more"></div>`;
  } else {
    body.innerHTML = `<p class="loading">위키백과에서 찾는 중…</p>`;
    wikiLookup(term).then((w) => {
      if (sheetTerm !== term) return;
      body.innerHTML = w
        ? `<p style="margin:0"><b>${esc(w.title)}</b> — ${esc(w.extract)}</p><p style="margin:8px 0 0;font-size:12px;color:var(--text-2)">출처: 위키백과</p>`
        : `<p style="margin:0">'${esc(term)}'에 대한 풀이를 찾지 못했어요. 아래 사전에서 찾아보세요.</p>`;
      if (w) state._lastWiki = { term, def: w.extract };
    });
  }
  updateStar();
  const q = encodeURIComponent(sheetTerm);
  $("#sheet-links").innerHTML = `
    ${entry ? `<button data-wiki="${esc(sheetTerm)}">위키백과 설명 더 보기</button>` : ""}
    <a href="https://terms.naver.com/search.naver?query=${q}" target="_blank" rel="noopener">지식백과</a>
    <a href="https://stdict.korean.go.kr/search/searchResult.do?searchKeyword=${q}" target="_blank" rel="noopener">표준국어대사전</a>
    <a href="https://search.naver.com/search.naver?query=${q}+%EB%9C%BB" target="_blank" rel="noopener">네이버 검색</a>`;
  $("#sheet").hidden = false;
  $("#sheet-backdrop").hidden = false;
}

function marketEntry(name) {
  const map = { "코스피": "코스피", "코스닥": "코스닥", "원/달러": "원/달러 환율", "S&P500": "S&P500", "나스닥": "나스닥", "WTI 유가": "WTI" };
  if (map[name]) return DICT.get(map[name]);
  if (name === "금") return { term: "금", def: "대표적인 안전자산. 경제가 불안하거나 달러 가치가 떨어질 때 값이 오르는 경향이 있어요. 단위는 1트로이온스(약 31.1g)당 달러예요.", cat: "에너지·원자재", aliases: [] };
  if (name === "비트코인") return DICT.get("가상자산");
  return null;
}

function closeSheet() {
  $("#sheet").hidden = true;
  $("#sheet-backdrop").hidden = true;
  sheetTerm = null;
  resumeStory();
}

function updateStar() {
  const on = !!state.words[sheetTerm];
  $("#sheet-star").textContent = on ? "★" : "☆";
  $("#sheet-star").setAttribute("aria-label", on ? "단어장에서 빼기" : "단어장에 저장");
}

function toggleWord() {
  if (!sheetTerm) return;
  if (state.words[sheetTerm]) {
    delete state.words[sheetTerm];
    toast("단어장에서 뺐어요");
  } else {
    const e = DICT.get(sheetTerm) || marketEntry(sheetTerm);
    const def = e?.def || (state._lastWiki?.term === sheetTerm ? state._lastWiki.def : "") || $("#sheet-body").innerText.trim();
    state.words[sheetTerm] = { def, cat: e?.cat || "검색", at: Date.now() };
    toast("단어장에 저장했어요");
  }
  store.set("words", state.words);
  updateStar();
  if (!$("#view-words").hidden) renderWords();
}

const wikiCache = new Map();
async function wikiLookup(term) {
  if (wikiCache.has(term)) return wikiCache.get(term);
  const api = "https://ko.wikipedia.org";
  let result = null;
  try {
    let r = await fetch(`${api}/api/rest_v1/page/summary/${encodeURIComponent(term)}`);
    let j = r.ok ? await r.json() : null;
    if (!j || j.type === "disambiguation" || !j.extract) {
      const sr = await fetch(`${api}/w/api.php?action=query&list=search&srsearch=${encodeURIComponent(term)}&srlimit=1&format=json&origin=*`);
      const title = (await sr.json())?.query?.search?.[0]?.title;
      if (title) {
        r = await fetch(`${api}/api/rest_v1/page/summary/${encodeURIComponent(title)}`);
        j = r.ok ? await r.json() : null;
      }
    }
    if (j?.extract) {
      const extract = j.extract.length > 400 ? j.extract.slice(0, 400).replace(/[^.。]*$/, "") || j.extract.slice(0, 400) + "…" : j.extract;
      result = { title: j.title, extract };
    }
  } catch { /* 오프라인 등 */ }
  wikiCache.set(term, result);
  return result;
}

// ───────────────────────────────── 글자 길게 눌러 찾기
let fabText = "";
function onSelection() {
  const sel = window.getSelection();
  const text = sel ? sel.toString().trim().replace(/\s+/g, " ") : "";
  if (!text || text.length > 30 || !$("#sheet").hidden) return hideFab();
  const node = sel.anchorNode?.parentElement;
  if (!node?.closest(".post-body, .story-content, .word")) return hideFab();
  fabText = text;
  const fab = $("#lookup-fab");
  fab.textContent = `🔍 '${text}' 뜻 찾기`;
  fab.hidden = false;
  pauseStory();
}
function hideFab() { $("#lookup-fab").hidden = true; }

// ───────────────────────────────── 기타 동작
function toggleSave(id) {
  const s = state.data?.stories.find((x) => x.id === id) || state.saved[id];
  if (!s) return;
  if (state.saved[id]) { delete state.saved[id]; toast("저장을 취소했어요"); }
  else { state.saved[id] = { ...s, savedAt: Date.now() }; toast("저장했어요"); }
  store.set("saved", state.saved);
  document.querySelectorAll(`[data-save="${id}"]`).forEach((b) => b.classList.toggle("on", !!state.saved[id]));
  if (!$("#view-saved").hidden) renderSaved();
}

async function share(id) {
  const s = state.data?.stories.find((x) => x.id === id) || state.saved[id];
  if (!s) return;
  try {
    if (navigator.share) await navigator.share({ title: s.title, url: s.url });
    else { await navigator.clipboard.writeText(`${s.title}\n${s.url}`); toast("링크를 복사했어요"); }
  } catch { /* 취소 */ }
}

let toastTimer = 0;
function toast(msg) {
  const t = $("#toast");
  t.textContent = msg;
  t.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (t.hidden = true), 1800);
}

document.addEventListener("click", (e) => {
  const el = e.target.closest("button, a");
  if (!el) return;
  const d = el.dataset;
  if (d.term) { e.preventDefault(); e.stopPropagation(); return openSheet(d.term); }
  if (d.lookup) return openSheet(d.lookup);
  if (d.wiki) {
    el.remove();
    const box = $("#wiki-more");
    if (!box) return;
    box.innerHTML = `<span class="loading">불러오는 중…</span>`;
    wikiLookup(d.wiki).then((w) => { box.innerHTML = w ? `<b>위키백과</b> · ${esc(w.extract)}` : "위키백과에 문서가 없어요."; });
    return;
  }
  if (d.story) return openStory(d.story);
  if (d.filter) {
    state.filter = d.filter; store.set("filter", d.filter);
    renderFilters(); renderFeed();
    const top = $("#filters").offsetTop - 57;
    if (window.scrollY > top) window.scrollTo({ top });
    return;
  }
  if (d.save) return toggleSave(d.save);
  if (d.share) return share(d.share);
  if (d.more) { el.nextElementSibling.hidden = !el.nextElementSibling.hidden; el.hidden = true; return; }
  if (d.open) { state.read.add(d.open); saveRead(); el.closest(".post")?.classList.add("read"); return; }
  if (d.view) return showView(d.view);
});

$("#refresh").addEventListener("click", () => load(true));
$("#story-close").addEventListener("click", closeStory);
$("#story-prev").addEventListener("click", () => showStory(story.i - 1));
$("#story-next").addEventListener("click", () => showStory(story.i + 1));
$("#sheet-backdrop").addEventListener("click", closeSheet);
$("#sheet-star").addEventListener("click", toggleWord);
$("#lookup-fab").addEventListener("click", () => { const t = fabText; window.getSelection()?.removeAllRanges(); openSheet(t); });
$("#dict-search").addEventListener("input", (e) => renderDict(e.target.value));
document.addEventListener("selectionchange", () => { clearTimeout(onSelection.t); onSelection.t = setTimeout(onSelection, 250); });

// 스토리: 길게 누르면 멈춤, 아래로 쓸면 닫기
const viewer = $("#story-viewer");
let touchY = 0, holdTimer = 0, held = false;
viewer.addEventListener("pointerdown", (e) => {
  touchY = e.clientY; held = false;
  holdTimer = setTimeout(() => { held = true; pauseStory(); }, 250);
});
viewer.addEventListener("pointerup", (e) => {
  clearTimeout(holdTimer);
  if (e.clientY - touchY > 90) return closeStory();
  if (held) { held = false; resumeStory(); }
});
viewer.addEventListener("click", (e) => { if (held) { e.stopPropagation(); e.preventDefault(); } }, true);

document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") { if (!$("#sheet").hidden) closeSheet(); else if (!viewer.hidden) closeStory(); }
  if (!viewer.hidden && $("#sheet").hidden) {
    if (e.key === "ArrowRight") showStory(story.i + 1);
    if (e.key === "ArrowLeft") showStory(story.i - 1);
  }
});
document.addEventListener("visibilitychange", () => {
  if (document.hidden) pauseStory();
  else {
    resumeStory();
    // 30분 넘게 지난 데이터면 새로 받기
    if (state.data && Date.now() - new Date(state.data.generated_at).getTime() > 30 * 60000) load();
  }
});

// 시작
$("#feed").innerHTML = '<div class="skeleton"></div><div class="skeleton"></div>';
load();
if ("serviceWorker" in navigator && location.protocol === "https:") {
  navigator.serviceWorker.register("sw.js").catch(() => {});
}
