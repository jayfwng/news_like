"""크롤러 테스트. 인터넷 없이 예시 피드로 확인해요."""

import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import crawl  # noqa: E402
import sources  # noqa: E402

NOW = datetime.now(timezone.utc)


def rfc(hours_ago: float) -> str:
    return format_datetime(NOW - timedelta(hours=hours_ago))


def rss(items: list[tuple[str, str, str, float, str | None]]) -> bytes:
    body = "".join(
        f"""<item><title><![CDATA[{t}]]></title><link>{link}</link>
        <description><![CDATA[{d}]]></description><pubDate>{rfc(h)}</pubDate>
        {f'<media:content url="{img}" medium="image"/>' if img else ''}</item>"""
        for t, link, d, h, img in items
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?><rss version="2.0" '
        'xmlns:media="http://search.yahoo.com/mrss/"><channel>' + body + "</channel></rss>"
    ).encode()


def google(items: list[tuple[str, str, str, float]]) -> bytes:
    body = "".join(
        f"""<item><title>{t} - {src}</title><link>{link}</link>
        <description>&lt;a href="{link}"&gt;{t}&lt;/a&gt;</description>
        <pubDate>{rfc(h)}</pubDate><source url="https://x">{src}</source></item>"""
        for t, link, src, h in items
    )
    return f'<?xml version="1.0"?><rss version="2.0"><channel>{body}</channel></rss>'.encode()


ATOM = f"""<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
 <entry><title>예시 아톰 기사: 반도체 수출 증가</title><link href="https://ex.com/atom1"/>
 <updated>{(NOW - timedelta(hours=2)).isoformat()}</updated>
 <summary type="html">&lt;p&gt;예시 요약입니다. &lt;img src="https://img.ex/a.jpg"&gt;&lt;/p&gt;</summary></entry>
</feed>""".encode()

NAVER = """<div class="rankingnews_box"><strong class="rankingnews_name">예시일보</strong>
<ul><li><a href="https://n.news.naver.com/article/001/1" class="list_title nclicks('x')">한은 기준금리 동결…연내 인하 신호 (예시)</a></li>
<li><a href="https://n.news.naver.com/article/001/2" class="list_title">예시 연예 기사</a></li></ul></div>""".encode()

FEEDS = {
    "https://a.example/rss": rss([
        ("[속보] 한은, 기준금리 연 3.0% 동결…연내 인하 신호 (예시)", "https://a.example/1",
         "예시 요약: 한국은행이 기준금리를 동결했다. 원/달러 환율과 가계부채가 변수다.", 1, "http://img.a/1.jpg"),
        ("예시 아파트 청약 경쟁률 역대 최고", "https://a.example/2", "예시 요약: 서울 아파트 청약.", 3, None),
        ("아주 오래된 예시 기사", "https://a.example/old", "오래됨", 80, None),
    ]),
    "https://b.example/rss": rss([
        ("한은 기준금리 3.0% 동결, 연내 인하 신호 나왔다 (예시)", "https://b.example/1",
         "예시 요약 두 번째.", 2, None),
        ("예시 코스피 2% 급등…외국인 순매수", "https://b.example/2", "예시 증시 요약.", 1, None),
    ]),
    "https://c.example/atom": ATOM,
    "https://g.example/rss": google([
        ("한은 기준금리 연 3.0% 동결…연내 인하 신호 (예시)", "https://news.google.com/rss/articles/xyz", "예시방송", 1.5),
    ]),
    sources.NAVER_RANKING_URL: NAVER,
}


def fake_fetch(url, timeout=15, limit=None):
    if url in FEEDS:
        return FEEDS[url]
    raise OSError(f"offline: {url}")


class CrawlTest(unittest.TestCase):
    def setUp(self):
        patches = [
            mock.patch.object(crawl, "fetch", fake_fetch),
            mock.patch.object(sources, "RSS_FEEDS", [
                ("가일보", "https://a.example/rss", None),
                ("나경제", "https://b.example/rss", "economy"),
                ("다뉴스", "https://c.example/atom", None),
                ("라일보", "https://broken.example/rss", None),
            ]),
            mock.patch.object(sources, "GOOGLE_SITE_FEEDS", []),
            mock.patch.object(sources, "POPULAR_FEEDS", [("구글", "https://g.example/rss", None)]),
            mock.patch.object(sources, "MARKET_SYMBOLS", []),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.tmp = Path(tempfile.mkdtemp()) / "news.json"
        self.data = crawl.run(self.tmp)

    def story(self, word):
        return next(s for s in self.data["stories"] if word in s["title"])

    def test_writes_json(self):
        saved = json.loads(self.tmp.read_text(encoding="utf-8"))
        self.assertEqual(saved["stories"], self.data["stories"])
        self.assertTrue(saved["generated_at"])

    def test_same_event_grouped(self):
        s = self.story("기준금리")
        names = {o["name"] for o in s["outlets"]}
        self.assertTrue({"가일보", "나경제", "예시방송", "예시일보"} <= names, names)
        self.assertEqual(self.data["stories"][0]["id"], s["id"], "가장 많이 다룬 기사가 맨 위")

    def test_representative_has_summary_and_https_image(self):
        s = self.story("기준금리")
        self.assertTrue(s["summary"].startswith("예시 요약"))
        self.assertEqual(s["image"], "https://img.a/1.jpg")
        self.assertNotIn("news.google.com", s["url"])

    def test_topics(self):
        self.assertIn("rate", self.story("기준금리")["topics"])
        self.assertIn("economy", self.story("기준금리")["topics"])
        self.assertIn("top", self.story("기준금리")["topics"])
        self.assertIn("realestate", self.story("청약")["topics"])
        self.assertIn("stock", self.story("코스피")["topics"])
        self.assertIn("industry", self.story("반도체")["topics"])

    def test_old_items_dropped(self):
        self.assertFalse(any("오래된" in s["title"] for s in self.data["stories"]))

    def test_atom_and_inline_image(self):
        s = self.story("아톰")
        self.assertEqual(s["image"], "https://img.ex/a.jpg")
        self.assertEqual(s["summary"], "예시 요약입니다.")

    def test_broken_feed_reported(self):
        self.assertTrue(str(self.data["sources"]["라일보 https://broken.example/rss"]).startswith("실패"))

    def test_naver_parsed(self):
        self.assertTrue(any(s["outlet"] == "예시일보" or any(o["name"] == "예시일보" for o in s["outlets"])
                            for s in self.data["stories"]))


class HelperTest(unittest.TestCase):
    def test_norm_title_removes_tags(self):
        self.assertEqual(crawl.norm_title("[속보] 코스피, 2%↑ (종합)"), "코스피2")

    def test_shorten(self):
        s = "첫 문장입니다. " * 30
        self.assertLessEqual(len(crawl.shorten(s, 100)), 101)

    def test_decode_euckr(self):
        data = '<?xml version="1.0" encoding="euc-kr"?><a>한글</a>'.encode("cp949")
        self.assertIn("한글", crawl.decode(data))


if __name__ == "__main__":
    unittest.main()
