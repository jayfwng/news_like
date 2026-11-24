"""뉴스를 가져올 곳 목록.

- topic: 이 피드에서 온 기사의 기본 분야. None이면 제목·요약의 낱말로 분야를 정해요.
- weight: 화제성 점수에 더하는 값(많이 본 뉴스 목록은 크게).
- 주소가 바뀌거나 막혀도 그 피드만 건너뛰고 나머지는 계속 모아요.
"""

# (언론사 이름, 피드 주소, 기본 분야)
RSS_FEEDS = [
    # 연합뉴스
    ("연합뉴스", "https://www.yna.co.kr/rss/news.xml", None),
    ("연합뉴스", "https://www.yna.co.kr/rss/economy.xml", "economy"),
    ("연합뉴스", "https://www.yna.co.kr/rss/market.xml", "stock"),
    ("연합뉴스", "https://www.yna.co.kr/rss/industry.xml", "industry"),
    # 조선일보
    ("조선일보", "https://www.chosun.com/arc/outboundfeeds/rss/?outputType=xml", None),
    ("조선일보", "https://www.chosun.com/arc/outboundfeeds/rss/category/economy/?outputType=xml", "economy"),
    # 동아일보
    ("동아일보", "https://rss.donga.com/total.xml", None),
    ("동아일보", "https://rss.donga.com/economy.xml", "economy"),
    # 한겨레
    ("한겨레", "https://www.hani.co.kr/rss/", None),
    ("한겨레", "https://www.hani.co.kr/rss/economy/", "economy"),
    # 경향신문
    ("경향신문", "https://www.khan.co.kr/rss/rssdata/total_news.xml", None),
    ("경향신문", "https://www.khan.co.kr/rss/rssdata/economy_news.xml", "economy"),
    # 매일경제
    ("매일경제", "https://www.mk.co.kr/rss/30000001/", None),
    ("매일경제", "https://www.mk.co.kr/rss/30100041/", "economy"),
    ("매일경제", "https://www.mk.co.kr/rss/50200011/", "stock"),
    ("매일경제", "https://www.mk.co.kr/rss/50300009/", "realestate"),
    # 한국경제
    ("한국경제", "https://www.hankyung.com/feed/all-news", None),
    ("한국경제", "https://www.hankyung.com/feed/economy", "economy"),
    ("한국경제", "https://www.hankyung.com/feed/finance", "stock"),
    ("한국경제", "https://www.hankyung.com/feed/realestate", "realestate"),
    ("한국경제", "https://www.hankyung.com/feed/industry", "industry"),
    # 방송사
    ("SBS", "https://news.sbs.co.kr/news/SectionRssFeed.do?sectionId=01", "politics"),
    ("SBS", "https://news.sbs.co.kr/news/SectionRssFeed.do?sectionId=02", "economy"),
    ("SBS", "https://news.sbs.co.kr/news/SectionRssFeed.do?sectionId=03", "society"),
    ("SBS", "https://news.sbs.co.kr/news/SectionRssFeed.do?sectionId=07", "world"),
    ("MBC", "https://imnews.imbc.com/rss/google_news/narrativeNews.rss", None),
    ("JTBC", "https://fs.jtbc.co.kr/RSS/newsflash.xml", None),
    ("JTBC", "https://fs.jtbc.co.kr/RSS/economy.xml", "economy"),
    # 경제지
    ("머니투데이", "https://rss.mt.co.kr/mt_news.xml", "economy"),
    ("서울경제", "https://www.sedaily.com/RSS/S1N1.xml", "economy"),
]

# RSS가 없거나 자주 바뀌는 언론사는 구글 뉴스의 "사이트 검색" 피드로 대신 가져와요.
# (언론사 이름, 사이트 주소, 기본 분야)
GOOGLE_SITE_FEEDS = [
    ("YTN", "ytn.co.kr", None),
    ("중앙일보", "joongang.co.kr", None),
    ("KBS", "news.kbs.co.kr", None),
    ("한국일보", "hankookilbo.com", None),
]

GOOGLE_NEWS = "https://news.google.com/rss{path}?hl=ko&gl=KR&ceid=KR:ko"

# 사람들이 많이 보는 뉴스: 여기 실린 기사는 화제성 점수를 크게 받아요.
# (이름, 주소, 기본 분야)
POPULAR_FEEDS = [
    ("구글 뉴스 주요 기사", GOOGLE_NEWS.format(path=""), None),
    ("구글 뉴스 비즈니스", GOOGLE_NEWS.format(path="/headlines/section/topic/BUSINESS"), "economy"),
    ("구글 뉴스 대한민국", GOOGLE_NEWS.format(path="/headlines/section/topic/NATION"), None),
    ("구글 뉴스 세계", GOOGLE_NEWS.format(path="/headlines/section/topic/WORLD"), "world"),
    ("구글 뉴스 과학/기술", GOOGLE_NEWS.format(path="/headlines/section/topic/TECHNOLOGY"), "tech"),
]

# 네이버 "언론사별 많이 본 뉴스" (HTML). 막히면 건너뛰어요.
NAVER_RANKING_URL = "https://news.naver.com/main/ranking/popularDay.naver"

# 경제 지표 (야후 파이낸스 차트 API). (표시 이름, 심볼, 단위, 소수점)
MARKET_SYMBOLS = [
    ("코스피", "^KS11", "", 2),
    ("코스닥", "^KQ11", "", 2),
    ("원/달러", "KRW=X", "원", 1),
    ("S&P500", "^GSPC", "", 2),
    ("나스닥", "^IXIC", "", 2),
    ("WTI 유가", "CL=F", "$", 2),
    ("금", "GC=F", "$", 1),
    ("비트코인", "BTC-USD", "$", 0),
]
