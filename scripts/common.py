# -*- coding: utf-8 -*-
"""우아봉사 공용: 상수, 서식 도우미, 레이아웃(헤더/푸터/광고/FAQ/JSON-LD), 파일 쓰기·사이트맵. (wooamarket/common.py 기반)"""
import html, json, re, pathlib, urllib.parse

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "_site"
BASE = "https://wooabongsa.wooahouse.com"
SITE = "우아봉사"
ICON = "🤝"
NAVER_TOKEN = "9f2692c3829c5bec02dea7bc5c7bcaa8578fb971"  # 네이버 서치어드바이저 소유확인 메타 태그 값(받으면 채움)
esc = html.escape

NAV = [("봉사 찾기", "/"), ("지역별", "/region/"), ("청소년 봉사", "/youth/"), ("마감 임박", "/closing/"), ("이용 안내", "/guide/")]

_JOSA = re.compile(r'(\S)((?:</[a-z]+>)*)(이\(가\)|은\(는\)|을\(를\)|과\(와\)|으로\(로\))')
_DIG = {"0": True, "1": True, "2": False, "3": True, "4": False, "5": False, "6": True, "7": True, "8": True, "9": False}


def _has_batchim(s, end):
    c = s[end]
    if c == ")":
        k = s.rfind("(", 0, end)
        return _has_batchim(s, k - 1) if k > 0 else False
    if c in _DIG:
        return _DIG[c]
    if "가" <= c <= "힣":
        return (ord(c) - 0xAC00) % 28 != 0
    if c.isascii() and c.isalpha():
        return c in "lmnrLMNR"
    return False


def josa(t):
    def f(m):
        has = _has_batchim(m.string, m.start(1))
        pair = m.group(3)
        if pair == "으로(로)":
            ro = has and (ord(m.group(1)) - 0xAC00) % 28 != 8 if "가" <= m.group(1) <= "힣" else has
            return m.group(1) + m.group(2) + ("으로" if ro else "로")
        return m.group(1) + m.group(2) + (pair[0] if has else pair[2])
    return _JOSA.sub(f, t)


def q(path):
    return urllib.parse.quote(path, safe="/-_.~()")


def ad():
    return ('<div class="ad-slot"><ins class="adsbygoogle" style="display:block" data-ad-client="ca-pub-6464921081676309" '
            'data-ad-slot="7080296704" data-ad-format="auto" data-full-width-responsive="true"></ins>'
            '<script>(adsbygoogle = window.adsbygoogle || []).push({});</script></div>')


COUPANG = ('<div class="coupang-partners" style="margin:36px auto 0;max-width:720px;padding:0 16px 8px;text-align:center;overflow-x:auto;">'
           '<script src="https://ads-partners.coupang.com/g.js"></script>'
           '<script>new PartnersCoupang.G({"id":980427,"trackingCode":"AF5600192","subId":"bongsa","template":"carousel","width":"680","height":"140"});</script>'
           '</div>')
COUPANG_NOTE = '<p style="margin:6px 0 0;font-size:.7rem;opacity:.55;">이 페이지는 쿠팡 파트너스 활동의 일환으로, 이에 따른 일정액의 수수료를 제공받습니다.</p>'


def layout(path, title, desc, body, faq=None, crumbs=None, kind="website", extra_ld=None, coupang=False, noindex=False):
    canon = BASE + q(path)
    title, desc, body = josa(title), josa(desc), josa(body)
    if faq:
        faq = [(josa(a), josa(b)) for a, b in faq]
    full_title = title if (title.endswith(SITE) or path == "/") else title + " | " + SITE
    ld = []
    if crumbs:
        ld.append({"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": i + 1, "name": n, "item": BASE + q(u)} for i, (n, u) in enumerate(crumbs)]})
    if faq:
        ld.append({"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
            {"@type": "Question", "name": a, "acceptedAnswer": {"@type": "Answer", "text": b}} for a, b in faq]})
    if extra_ld:
        ld += extra_ld
    ld_html = "".join('<script type="application/ld+json">%s</script>' % json.dumps(x, ensure_ascii=False).replace("</", "<\\/") for x in ld)
    nav = "".join('<a href="%s">%s</a>' % (u, n) for n, u in NAV)
    crumb_html = ""
    if crumbs:
        crumb_html = '<nav class="breadcrumb" aria-label="위치">' + ' <span>›</span> '.join(
            ('<a href="%s">%s</a>' % (u, esc(n))) if i < len(crumbs) - 1 else '<span>%s</span>' % esc(n) for i, (n, u) in enumerate(crumbs)) + '</nav>'
    faq_html = ""
    if faq:
        faq_html = '<div class="faq-block"><h2>자주 묻는 질문</h2>' + "".join(
            '<details><summary>%s</summary><p>%s</p></details>' % (esc(a), esc(b)) for a, b in faq) + '</div>'
    naver = '<meta name="naver-site-verification" content="%s" />' % NAVER_TOKEN if NAVER_TOKEN else ""
    robots = '<meta name="robots" content="noindex,follow">' if noindex else ""
    return """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>%(title)s</title>
<meta name="description" content="%(desc)s">
%(naver)s%(robots)s
<link rel="canonical" href="%(canon)s">
<meta property="og:type" content="%(kind)s">
<meta property="og:title" content="%(title)s">
<meta property="og:description" content="%(desc)s">
<meta property="og:url" content="%(canon)s">
<meta property="og:site_name" content="우아봉사">
<meta property="og:image" content="%(base)s/assets/og-image.png">
<meta name="twitter:card" content="summary_large_image">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Pretendard:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<link rel="stylesheet" href="/assets/css/main.css?v=1">
<script async src="https://www.googletagmanager.com/gtag/js?id=G-9ZGENFSXWC"></script>
<script>window.dataLayer=window.dataLayer||[];function gtag(){dataLayer.push(arguments);}gtag('js',new Date());gtag('config','G-9ZGENFSXWC');</script>
<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-6464921081676309" crossorigin="anonymous"></script>
%(ld)s
</head>
<body>
<header class="site-header"><div class="header-inner">
<a href="/" class="site-logo"><span class="logo-icon">%(icon)s</span><span class="logo-text">우아봉사</span></a>
<nav class="header-nav">%(nav)s</nav></div></header>
<script src="/assets/js/wooa-sites-bar.js"></script>
<script src="/assets/js/ad-dev-placeholder.js"></script>
<main class="site-main">
<div class="page-with-sidebar">
<div class="cal-page">
%(crumb)s
%(body)s
%(faq)s
</div>
<aside class="tool-sidebar"></aside>
</div>
</main>
<script src="/assets/js/wooa-sidebar.js"></script>
%(coupang)s
<footer class="site-footer"><div class="footer-inner">
<p class="footer-disclaimer">이 사이트는 행정안전부 1365자원봉사포털이 공공데이터포털에 공개한 봉사 모집 정보를 정리한 <b>참고용 정보</b>입니다. 모집 마감·변경과 신청은 1365자원봉사포털(www.1365.go.kr)과 모집 기관에서 반드시 확인하세요.</p>
<p class="footer-links"><a href="https://wooahouse.com">WooaHouse</a> · <a href="https://wooasenior.wooahouse.com">우아시니어</a> · <a href="https://wooawelfare.wooahouse.com">우아복지</a> · <a href="https://wooabyung.wooahouse.com">우아병역</a> · <a href="/about/">데이터 설명</a> · <a href="/privacy/">개인정보처리방침</a></p>
<p class="copyright">&copy; 2026 우아봉사 · WooaHouse. All rights reserved.</p>
%(cnote)s
</div></footer>
</body>
</html>
""" % dict(title=esc(full_title), desc=esc(desc), naver=naver, robots=robots, canon=canon, kind=kind, base=BASE, ld=ld_html, nav=nav,
           crumb=crumb_html, body=body, faq=faq_html, coupang=COUPANG if coupang else "", cnote=COUPANG_NOTE if coupang else "", icon=ICON)


WRITTEN = []


def write(path, html_text, prio="0.6", sitemap=True):
    out = OUT / path.strip("/") / "index.html" if path != "/" else OUT / "index.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html_text, encoding="utf-8")
    if sitemap:
        WRITTEN.append((path, prio))
