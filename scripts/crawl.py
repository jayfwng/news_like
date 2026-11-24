#!/usr/bin/env python3
"""뉴스 수집기.

여러 언론사 RSS, 구글 뉴스, 네이버 많이 본 뉴스를 모아서
같은 사건을 다룬 기사끼리 묶고, 화제성 순으로 정렬해 JSON 한 파일로 저장해요.

    python scripts/crawl.py --out web/data/news.json

표준 라이브러리만 써서 따로 설치할 것이 없어요.
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import email.utils
import gzip
import hashlib
import html
import json
import math
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sources  # noqa: E402

KST = timezone(timedelta(hours=9))
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
)
MAX_AGE_HOURS = 36
MAX_STORIES = 300
OG_IMAGE_LOOKUPS = 80

# 분야: (아이디, 이름, 이모지)
TOPICS = [
    ("top", "오늘 TOP", "🔥"),
    ("economy", "경제", "💰"),
    ("stock", "증시", "📈"),
    ("rate", "금리·환율", "💱"),
    ("realestate", "부동산", "🏠"),
    ("industry", "기업·산업", "🏭"),
    ("politics", "정치", "🏛️"),
    ("society", "사회", "👥"),
    ("world", "국제", "🌏"),
    ("tech", "IT·과학", "🤖"),
]
ECONOMY_SUBTOPICS = {"stock", "rate", "realestate", "industry"}

# 제목·요약에 이 낱말이 있으면 그 분야로 분류해요(여러 분야 가능).
TOPIC_KEYWORDS = {
    "stock": [
        "코스피", "코스닥", "증시", "주가", "상장", "공모주", "IPO", "외국인 순매수", "순매도",
        "시가총액", "나스닥", "다우", "S&P", "ETF", "배당", "공매도", "증권", "주식", "개미",
        "밸류업", "서학개미", "동학개미", "급등", "급락", "상한가", "하한가",
    ],
    "rate": [
        "금리", "기준금리", "환율", "원·달러", "원/달러", "달러", "엔화", "위안화", "한국은행",
        "한은", "연준", "Fed", "FOMC", "통화정책", "채권", "국채", "물가", "인플레이션",
        "소비자물가", "CPI", "금통위", "디플레이션", "외환",
    ],
    "realestate": [
        "부동산", "아파트", "집값", "전세", "월세", "청약", "분양", "재건축", "재개발",
        "주택", "토지", "전셋값", "매매가", "LTV", "DSR", "DTI", "주담대", "주택담보대출",
        "공시가격", "종부세", "임대차", "미분양", "PF",
    ],
    "industry": [
        "삼성전자", "SK하이닉스", "현대차", "LG", "반도체", "배터리", "2차전지", "이차전지",
        "자동차", "조선", "철강", "석유화학", "수출", "수입", "무역", "관세", "실적",
        "영업이익", "매출", "기업", "재계", "인수", "합병", "M&A", "공장", "투자",
        "HBM", "파운드리", "카카오", "네이버", "쿠팡",
    ],
    "economy": [
        "경제", "성장률", "GDP", "경기침체", "경기 둔화", "고용", "실업", "일자리", "세금", "세수", "예산",
        "추경", "재정", "기재부", "기획재정부", "금융위", "금감원", "은행", "대출", "가계부채",
        "소비", "내수", "자영업", "소상공인", "최저임금", "연금", "보험", "카드", "가상자산",
        "비트코인", "코인", "유가", "원자재",
    ],
    "politics": [
        "대통령", "국회", "여당", "야당", "의원", "정당", "선거", "총선", "대선", "국무총리",
        "장관", "청와대", "대통령실", "민주당", "국민의힘", "탄핵", "법안", "개헌", "외교부",
        "통일", "북한", "국방",
    ],
    "society": [
        "경찰", "검찰", "법원", "재판", "판결", "구속", "기소", "사고", "화재", "사망", "부상",
        "날씨", "폭염", "한파", "폭우", "태풍", "교육", "학교", "수능", "의대", "병원", "의료",
        "복지", "저출산", "고령화", "노동", "파업",
    ],
    "world": [
        "미국", "중국", "일본", "러시아", "우크라이나", "이스라엘", "가자지구", "중동", "유럽",
        "EU", "트럼프", "시진핑", "백악관", "유엔", "UN", "NATO", "나토", "이란", "영국",
        "프랑스", "독일", "인도네시아",
    ],
    "tech": [
        "AI", "인공지능", "챗GPT", "ChatGPT", "오픈AI", "OpenAI", "구글", "애플", "아이폰",
        "갤럭시", "메타", "엔비디아", "테슬라", "로봇", "우주", "누리호", "과학", "연구진",
        "플랫폼", "스타트업", "양자", "클라우드", "데이터센터",
    ],
}

# ---------------------------------------------------------------- 내려받기


def fetch(url: str, timeout: float = 15, limit: int | None = None) -> bytes:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": UA,
            "Accept": "application/rss+xml, application/xml, text/xml, text/html, */*",
            "Accept-Language": "ko-KR,ko;q=0.9",
            "Accept-Encoding": "gzip",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as res:
        data = res.read(limit) if limit else res.read()
        if res.headers.get("Content-Encoding") == "gzip":
            try:
                data = gzip.decompress(data)
            except (OSError, EOFError):
                pass
        return data


def decode(data: bytes) -> str:
    head = data[:300].decode("ascii", "ignore").lower()
    m = re.search(r'encoding=["\']([\w-]+)', head) or re.search(r"charset=([\w-]+)", head)
    enc = m.group(1) if m else "utf-8"
    if enc in ("euc-kr", "ks_c_5601-1987"):
        enc = "cp949"
    try:
        return data.decode(enc)
    except (LookupError, UnicodeDecodeError):
        return data.decode("utf-8", "replace")


# ---------------------------------------------------------------- 글자 정리

TAG_RE = re.compile(r"<[^>]+>")
SPACE_RE = re.compile(r"\s+")
IMG_RE = re.compile(r"<img[^>]+src=[\"']([^\"']+)[\"']", re.I)


def clean_text(s: str | None) -> str:
    if not s:
        return ""
    s = html.unescape(s)
    s = TAG_RE.sub(" ", s)
    s = html.unescape(s)
    return SPACE_RE.sub(" ", s).strip()


def shorten(s: str, n: int = 180) -> str:
    if len(s) <= n:
        return s
    cut = s[:n]
    # 문장 끝에서 자르기
    for mark in (". ", "다. ", "다.", "요. "):
        i = cut.rfind(mark)
        if i > n * 0.5:
            return cut[: i + len(mark)].strip()
    return cut.rstrip() + "…"


def parse_date(s: str | None) -> datetime | None:
    if not s:
        return None
    s = s.strip()
    try:
        d = email.utils.parsedate_to_datetime(s)
    except (TypeError, ValueError):
        d = None
    if d is None:
        try:
            d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y.%m.%d %H:%M"):
                try:
                    d = datetime.strptime(s, fmt)
                    break
                except ValueError:
                    continue
    if d is None:
        return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=KST)
    return d.astimezone(timezone.utc)


def local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def child_text(el: ET.Element, *names: str) -> str | None:
    for c in el:
        if local(c.tag) in names and (c.text or "").strip():
            return c.text
    return None


def find_image(el: ET.Element, raw_html: str) -> str | None:
    for c in el.iter():
        name = local(c.tag)
        if name in ("content", "thumbnail") and c.get("url"):
            if c.get("medium", "image") == "image" or "image" in (c.get("type") or "image"):
                return c.get("url")
        if name == "enclosure" and c.get("url") and "image" in (c.get("type") or "image"):
            return c.get("url")
    m = IMG_RE.search(raw_html or "")
    return m.group(1) if m else None


def parse_feed(xml_text: str) -> list[dict]:
    xml_text = re.sub(r"^[^<]+", "", xml_text)
    root = ET.fromstring(xml_text.encode("utf-8"))
    items = []
    for el in root.iter():
        name = local(el.tag)
        if name not in ("item", "entry"):
            continue
        title = clean_text(child_text(el, "title"))
        link = None
        for c in el:
            if local(c.tag) == "link":
                link = (c.text or "").strip() or c.get("href")
                if link:
                    break
        if not title or not link:
            continue
        raw_desc = ""
        for c in el:
            if local(c.tag) in ("description", "summary", "encoded", "content") and c.text:
                raw_desc = c.text
                break
        source = None
        for c in el:
            if local(c.tag) == "source" and (c.text or "").strip():
                source = c.text.strip()
        items.append(
            {
                "title": title,
                "url": link.strip(),
                "summary": clean_text(raw_desc),
                "published": parse_date(child_text(el, "pubdate", "published", "updated", "date")),
                "image": find_image(el, raw_desc),
                "source": source,
            }
        )
    return items


# ---------------------------------------------------------------- 수집


def collect_rss(name: str, url: str, topic: str | None, popular: bool = False) -> list[dict]:
    items = parse_feed(decode(fetch(url)))
    out = []
    for i, it in enumerate(items):
        outlet = name
        title = it["title"]
        summary = it["summary"]
        if "news.google.com" in url or "news.google.com" in it["url"]:
            # 구글 뉴스: "제목 - 언론사" 형태, 요약은 제목 반복이라 버려요.
            outlet = it["source"] or outlet
            if " - " in title:
                title, tail = title.rsplit(" - ", 1)
                if not it["source"]:
                    outlet = tail.strip()
            summary = ""
        if summary and title in summary[: len(title) + 5]:
            summary = summary[len(title):].strip()
        out.append(
            {
                "title": title.strip(),
                "url": it["url"],
                "summary": shorten(summary),
                "published": it["published"],
                "image": it["image"],
                "outlet": outlet,
                "topic": topic,
                "popular": (1.0 / (1 + i * 0.15)) if popular else 0.0,
                "via": name,
            }
        )
    return out


NAVER_ITEM_RE = re.compile(
    r'<a href="(https://n\.news\.naver\.com/[^"]+)"[^>]*class="list_title[^"]*"[^>]*>(.*?)</a>', re.S
)
NAVER_BOX_RE = re.compile(r'<strong class="rankingnews_name">(.*?)</strong>(.*?)</ul>', re.S)


def collect_naver() -> list[dict]:
    text = decode(fetch(sources.NAVER_RANKING_URL))
    out = []
    for press, block in NAVER_BOX_RE.findall(text):
        press = clean_text(press)
        for rank, (link, title) in enumerate(NAVER_ITEM_RE.findall(block)):
            out.append(
                {
                    "title": clean_text(title),
                    "url": html.unescape(link),
                    "summary": "",
                    "published": None,
                    "image": None,
                    "outlet": press,
                    "topic": None,
                    "popular": 1.0 / (1 + rank * 0.3),
                    "via": "네이버 많이 본 뉴스",
                }
            )
    return out


def collect_market() -> list[dict]:
    out = []
    for label, sym, unit, digits in sources.MARKET_SYMBOLS:
        url = (
            "https://query1.finance.yahoo.com/v8/finance/chart/"
            + urllib.parse.quote(sym)
            + "?range=5d&interval=1d"
        )
        try:
            data = json.loads(fetch(url, timeout=10))
            meta = data["chart"]["result"][0]["meta"]
            price = meta["regularMarketPrice"]
            prev = meta.get("chartPreviousClose") or meta.get("previousClose")
            closes = data["chart"]["result"][0]["indicators"]["quote"][0].get("close") or []
            closes = [c for c in closes if c is not None]
            if len(closes) >= 2:
                prev = closes[-2]
            change = (price - prev) / prev * 100 if prev else None
            out.append(
                {
                    "name": label,
                    "price": round(price, digits),
                    "unit": unit,
                    "digits": digits,
                    "change": round(change, 2) if change is not None else None,
                    "spark": [round(c, digits) for c in closes[-5:]],
                }
            )
        except Exception as e:  # noqa: BLE001
            log(f"  지표 실패 {label}: {e}")
    return out


OG_RE = re.compile(
    r'<meta[^>]+(?:property|name)=["\'](?:og:image|twitter:image)["\'][^>]*content=["\']([^"\']+)', re.I
)
OG_RE2 = re.compile(
    r'<meta[^>]+content=["\']([^"\']+)["\'][^>]*(?:property|name)=["\'](?:og:image|twitter:image)', re.I
)
OG_DESC_RE = re.compile(
    r'<meta[^>]+(?:property|name)=["\'](?:og:description|description)["\'][^>]*content=["\']([^"\']+)', re.I
)


def og_lookup(url: str) -> tuple[str | None, str | None]:
    text = decode(fetch(url, timeout=8, limit=400_000))
    m = OG_RE.search(text) or OG_RE2.search(text)
    d = OG_DESC_RE.search(text)
    img = html.unescape(m.group(1)) if m else None
    if img and img.startswith("//"):
        img = "https:" + img
    elif img and img.startswith("/"):
        img = urllib.parse.urljoin(url, img)
    return img, (clean_text(d.group(1)) if d else None)


# ---------------------------------------------------------------- 분류·묶기

BRACKET_RE = re.compile(r"[\[\(【<〈「『][^\]\)】>〉」』]{0,12}[\]\)】>〉」』]")
NON_WORD_RE = re.compile(r"[^0-9A-Za-z가-힣]+")


def norm_title(t: str) -> str:
    t = BRACKET_RE.sub(" ", t)
    t = re.sub(r"(속보|단독|종합|포토|영상|사진|오늘의|그래픽)\s*", " ", t)
    return NON_WORD_RE.sub("", t).lower()


def bigrams(t: str) -> frozenset[str]:
    return frozenset(t[i : i + 2] for i in range(len(t) - 1))


def classify(text: str, base: str | None) -> list[str]:
    found = set()
    if base:
        found.add(base)
    for topic, words in TOPIC_KEYWORDS.items():
        if any(w in text for w in words):
            found.add(topic)
    if found & ECONOMY_SUBTOPICS:
        found.add("economy")
    return [t for t, _, _ in TOPICS if t in found]


def similarity(a: frozenset, b: frozenset) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    return inter / min(len(a), len(b)) * 0.5 + inter / len(a | b) * 0.5


def cluster(items: list[dict]) -> list[list[dict]]:
    groups: list[dict] = []
    for it in items:
        key = norm_title(it["title"])
        if len(key) < 6:
            continue
        bg = bigrams(key)
        best, best_s = None, 0.0
        for g in groups:
            s = similarity(bg, g["bg"])
            if s > best_s:
                best, best_s = g, s
        if best is not None and best_s >= 0.55:
            best["items"].append(it)
            best["bg"] = best["bg"] | bg if len(best["bg"]) < 80 else best["bg"]
        else:
            groups.append({"bg": bg, "items": [it]})
    return [g["items"] for g in groups]


def score_group(items: list[dict], now: datetime) -> float:
    outlets = {i["outlet"] for i in items}
    popular = sum(i["popular"] for i in items)
    times = [i["published"] for i in items if i["published"]]
    newest = max(times) if times else now - timedelta(hours=6)
    hours = max(0.0, (now - newest).total_seconds() / 3600)
    freshness = 1 / (1 + hours / 10)
    return (len(outlets) * 2.0 + popular * 4.0 + min(len(items), 10) * 0.3) * (0.4 + freshness)


def story_id(url: str) -> str:
    return hashlib.sha1(url.encode()).hexdigest()[:12]


def build_story(items: list[dict], now: datetime) -> dict:
    # 대표 기사: 요약과 사진이 있고, 구글 경유가 아닌 것 우선
    def rank(i: dict) -> tuple:
        return (
            bool(i["summary"]),
            bool(i["image"]),
            "news.google.com" not in i["url"],
            i["published"] or datetime.min.replace(tzinfo=timezone.utc),
        )

    items = sorted(items, key=rank, reverse=True)
    main = items[0]
    text = " ".join(i["title"] + " " + i["summary"] for i in items[:6])
    base = next((i["topic"] for i in items if i["topic"]), None)
    times = [i["published"] for i in items if i["published"]]
    published = min(times) if times else None
    seen, outlets = set(), []
    for i in items:
        if i["outlet"] in seen:
            continue
        seen.add(i["outlet"])
        outlets.append({"name": i["outlet"], "title": i["title"], "url": i["url"]})
    image = main["image"] or next((i["image"] for i in items if i["image"]), None)
    summary = main["summary"] or next((i["summary"] for i in items if i["summary"]), "")
    return {
        "id": story_id(main["url"]),
        "title": main["title"],
        "summary": summary,
        "url": main["url"],
        "outlet": main["outlet"],
        "image": image,
        "published": published.isoformat() if published else None,
        "topics": classify(text, base),
        "outlets": outlets[:12],
        "popular": round(sum(i["popular"] for i in items), 2),
        "score": round(score_group(items, now), 3),
    }


# ---------------------------------------------------------------- 실행


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def run(out_path: Path) -> dict:
    now = datetime.now(timezone.utc)
    jobs = []
    for name, url, topic in sources.RSS_FEEDS:
        jobs.append((f"{name} {url}", collect_rss, (name, url, topic)))
    for name, site, topic in sources.GOOGLE_SITE_FEEDS:
        url = sources.GOOGLE_NEWS.format(path="/search") + "&q=" + urllib.parse.quote(
            f"site:{site} when:1d"
        )
        jobs.append((f"{name} (구글)", collect_rss, (name, url, topic)))
    for name, url, topic in sources.POPULAR_FEEDS:
        jobs.append((name, collect_rss, (name, url, topic, True)))
    jobs.append(("네이버 많이 본 뉴스", collect_naver, ()))

    items: list[dict] = []
    report = {}
    with cf.ThreadPoolExecutor(max_workers=12) as pool:
        futs = {pool.submit(fn, *args): label for label, fn, args in jobs}
        for f in cf.as_completed(futs):
            label = futs[f]
            try:
                got = f.result()
                items.extend(got)
                report[label] = len(got)
                log(f"  ✓ {label}: {len(got)}")
            except Exception as e:  # noqa: BLE001
                report[label] = f"실패: {type(e).__name__}"
                log(f"  ✗ {label}: {e}")

    cutoff = now - timedelta(hours=MAX_AGE_HOURS)
    items = [i for i in items if i["published"] is None or i["published"] >= cutoff]
    items = [i for i in items if i["published"] is None or i["published"] <= now + timedelta(hours=1)]

    # 같은 주소 중복 제거
    by_url: dict[str, dict] = {}
    for it in items:
        prev = by_url.get(it["url"])
        if prev is None:
            by_url[it["url"]] = it
        else:
            prev["popular"] = max(prev["popular"], it["popular"])
            prev["image"] = prev["image"] or it["image"]
            prev["summary"] = prev["summary"] or it["summary"]
    items = list(by_url.values())
    log(f"기사 {len(items)}개 → 묶는 중")

    groups = cluster(items)
    stories = [build_story(g, now) for g in groups]
    stories.sort(key=lambda s: s["score"], reverse=True)
    stories = stories[:MAX_STORIES]

    # 사진·요약이 없는 상위 기사는 원문 페이지의 og:image / og:description을 읽어요.
    need = [s for s in stories[:OG_IMAGE_LOOKUPS] if not s["image"] or not s["summary"]]
    with cf.ThreadPoolExecutor(max_workers=10) as pool:
        futs = {}
        for s in need:
            link = next((o["url"] for o in s["outlets"] if "news.google.com" not in o["url"]), s["url"])
            futs[pool.submit(og_lookup, link)] = s
        for f in cf.as_completed(futs):
            s = futs[f]
            try:
                img, desc = f.result()
                s["image"] = s["image"] or img
                if not s["summary"] and desc and norm_title(desc)[:20] != norm_title(s["title"])[:20]:
                    s["summary"] = shorten(desc)
            except Exception:  # noqa: BLE001
                pass

    # 화면에 보여줄 이미지 주소는 https만
    for s in stories:
        if s["image"] and s["image"].startswith("http://"):
            s["image"] = "https://" + s["image"][7:]

    # "오늘 TOP": 여러 곳에서 다뤘거나 많이 본 기사 상위
    for s in stories[:30]:
        if len(s["outlets"]) >= 2 or s["popular"] > 0:
            s["topics"] = ["top"] + s["topics"]

    market = collect_market()

    data = {
        "generated_at": now.isoformat(),
        "topics": [{"id": t, "name": n, "emoji": e} for t, n, e in TOPICS],
        "market": market,
        "stories": stories,
        "sources": report,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    ok = sum(1 for v in report.values() if isinstance(v, int) and v > 0)
    log(f"완료: 이야기 {len(stories)}개, 피드 {ok}/{len(report)}개 성공, 지표 {len(market)}개 → {out_path}")
    return data


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="web/data/news.json")
    args = ap.parse_args()
    t = time.time()
    data = run(Path(args.out))
    log(f"{time.time() - t:.1f}초")
    if not data["stories"]:
        log("기사를 하나도 못 가져왔어요. 네트워크나 피드 주소를 확인하세요.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
