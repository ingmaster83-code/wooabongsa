# -*- coding: utf-8 -*-
"""우아봉사 정적 사이트 생성기.
입력: data/list.json.gz(모집 중 프로그램 목록) · data/details/*.json.gz(상세 캐시) · data/tags.json.gz(선택: 청소년 가능·분야별 id 집합)
출력: _site/  (프로그램 상세, 시도·시군구·모집기관 허브, 청소년·마감임박, 안내, 검색 인덱스, sitemap)
상세가 아직 없는 프로그램은 목록(제목·기관·기간)에만 나오고 상세 페이지는 만들지 않는다 — 상세는 매일 예산만큼 쌓인다.
"""
import collections, gzip, hashlib, html as ihtml, json, re, shutil, sys
from datetime import datetime, timedelta, timezone

from common import *  # noqa

sys.stdout.reconfigure(encoding="utf-8")
DATA = ROOT / "data"
TODAY = (datetime.now(timezone.utc) + timedelta(hours=9)).date()

SIDO = {"6110000": "서울특별시", "6260000": "부산광역시", "6270000": "대구광역시", "6280000": "인천광역시", "6290000": "광주광역시", "6300000": "대전광역시",
        "6310000": "울산광역시", "5690000": "세종특별자치시", "6410000": "경기도", "6420000": "강원특별자치도", "6430000": "충청북도", "6440000": "충청남도",
        "6450000": "전북특별자치도", "6460000": "전라남도", "6470000": "경상북도", "6480000": "경상남도", "6500000": "제주특별자치도"}
SHORT = {"서울특별시": "서울", "부산광역시": "부산", "대구광역시": "대구", "인천광역시": "인천", "광주광역시": "광주", "대전광역시": "대전", "울산광역시": "울산",
         "세종특별자치시": "세종", "경기도": "경기", "강원특별자치도": "강원", "충청북도": "충북", "충청남도": "충남", "전북특별자치도": "전북",
         "전라남도": "전남", "경상북도": "경북", "경상남도": "경남", "제주특별자치도": "제주"}
WK = "월화수목금토일"


def ymd(d):
    d = (d or "").strip()
    return "%s.%s.%s" % (d[:4], d[4:6], d[6:8]) if re.fullmatch(r"\d{8}", d) else ""


def todate(d):
    try:
        return datetime.strptime(d, "%Y%m%d").date()
    except Exception:
        return None


def dday(d):
    x = todate(d)
    return (x - TODAY).days if x else None


def period(a, b):
    a, b = ymd(a), ymd(b)
    return "%s ~ %s" % (a, b) if a and b else (a or b)


def short_sido(s):
    return SHORT.get(s, s)


def phone(p):
    p = re.sub(r"[^0-9]", "", p or "")
    if len(p) < 8:
        return ""
    if p.startswith("02"):
        return "02-%s-%s" % (p[2:-4], p[-4:])
    if len(p) == 8:
        return "%s-%s" % (p[:4], p[4:])
    return "%s-%s-%s" % (p[:3], p[3:-4], p[-4:])


def text_block(t, cap=1400):
    t = re.sub(r"[ \t]+", " ", (t or "").replace("\r", "")).strip()
    t = re.sub(r"\n\s*\n+", "\n", t)
    if len(t) > cap:
        t = t[:cap].rsplit("\n", 1)[0].rsplit(" ", 1)[0] + " …"
    return "<br>".join(esc(l.strip()) for l in t.split("\n") if l.strip())


def weekdays(w):
    w = (w or "").strip()
    if len(w) != 7 or set(w) - {"0", "1"}:
        return ""
    days = [WK[i] for i, c in enumerate(w) if c == "1"]
    if len(days) == 7:
        return "매일"
    if days == list("월화수목금"):
        return "평일(월~금)"
    return "·".join(days)


# ───────────────────────── 데이터 ─────────────────────────
def load():
    lst = json.loads(gzip.open(DATA / "list.json.gz", "rt", encoding="utf-8").read())
    det = {}
    for p in (DATA / "details").glob("*.json.gz"):
        det.update(json.loads(gzip.open(p, "rt", encoding="utf-8").read()))
    tags = json.loads(gzip.open(DATA / "tags.json.gz", "rt", encoding="utf-8").read()) if (DATA / "tags.json.gz").exists() else {}
    # API 응답이 한 번 더 이스케이프돼 있어(&amp; 등) 문자열 필드는 unescape 한다.
    lst = [{k: ihtml.unescape(v) if isinstance(v, str) else v for k, v in x.items()} for x in lst]
    det = {no: {k: ihtml.unescape(v) if isinstance(v, str) else v for k, v in d.items()} for no, d in det.items()}
    # 시군구 이름: 상세의 nanmmbyNm("대구광역시 동구")에서 시도 접두어를 떼어 얻는다.
    gname = {}
    for no, d in det.items():
        nm = d.get("nanmmbyNm", "")
        sido = SIDO.get(d.get("sidoCd", ""), "")
        if sido and nm.startswith(sido):
            g = nm[len(sido):].strip()
            if g:
                gname.setdefault(d["gugunCd"], g)
    ps = []
    for x in lst:
        no = x["progrmRegistNo"]
        end = todate(x.get("progrmEndde"))
        if end and end < TODAY:
            continue
        d = det.get(no)
        p = dict(id=no, title=x.get("progrmSj", "").strip() or "자원봉사 모집", org=x.get("nanmmbyNm", "").strip(), sido=SIDO.get(x.get("sidoCd", ""), ""), gcode=x.get("gugunCd", ""),
                 bgn=x.get("progrmBgnde", ""), end=x.get("progrmEndde", ""), status=x.get("progrmSttusSe", ""), d=d)
        p["gugun"] = gname.get(p["gcode"], "")
        ps.append(p)
    ps = [p for p in ps if p["sido"]]
    return ps, tags, gname


def plink(p):
    if p["d"]:
        return '<a href="/program/%s/">%s</a>' % (p["id"], esc(p["title"]))
    return esc(p["title"])


def status_txt(p):
    if p["status"] == "3":
        return '<span class="tag bad">모집완료</span>'
    dl = dday(p["end"])
    return '<span class="tag gil">모집중</span>'


def ptable(ps, cap=300, show_region=False):
    ps = ps[:cap]
    head = "<tr><th>봉사 프로그램</th><th>모집 기관</th>%s<th>봉사 기간</th><th>상태</th></tr>" % ("<th>지역</th>" if show_region else "")
    rows = []
    for p in ps:
        loc = "<td>%s</td>" % esc((short_sido(p["sido"]) + " " + p["gugun"]).strip()) if show_region else ""
        rows.append("<tr><td>%s</td><td>%s</td>%s<td>%s</td><td>%s</td></tr>" % (plink(p), esc(p["org"]), loc, esc(period(p["bgn"], p["end"])), status_txt(p)))
    return '<div class="tbl-wrap"><table class="tbl">%s%s</table></div>' % (head, "".join(rows))


def recency(p):
    return -int(p["id"])


def closing_key(p):
    return (p["end"], -int(p["id"]))


def stat_line(ps):
    n = len(ps)
    open_n = sum(1 for p in ps if p["status"] != "3")
    orgs = len({p["org"] for p in ps})
    soon = sum(1 for p in ps if (dday(p["end"]) is not None and 0 <= dday(p["end"]) <= 14))
    s = "현재 <b>%d건</b>의 봉사활동이 올라와 있고 그중 모집 중인 프로그램은 <b>%d건</b>, 모집 기관은 %d곳입니다." % (n, open_n, orgs)
    if soon:
        s += " 봉사 기간이 2주 안에 끝나는 프로그램이 %d건 있습니다." % soon
    return '<p class="lead">%s</p>' % s


# ───────────────────────── 페이지 ─────────────────────────
def page_program(p, by_gugun, by_org, hubs, dup):
    d = p["d"]
    region = (p["sido"] + " " + p["gugun"]).strip()
    addr = " ".join(x for x in (d.get("areaAddress1"), d.get("areaAddress2")) if x).strip()
    cat = d.get("srvcClCode", "")
    hours = ""
    if d.get("actBeginTm") and d.get("actEndTm"):
        hours = "%s시 ~ %s시" % (d["actBeginTm"], d["actEndTm"])
    wk = weekdays(d.get("actWkdy"))
    targets = [lab for k, lab in (("yngbgsPosblAt", "청소년"), ("adultPosblAt", "성인"), ("familyPosblAt", "가족"), ("grpPosblAt", "단체")) if d.get(k) == "Y"]
    dl = dday(p["end"])
    lead = ["<b>%s</b>은(는) %s에서 진행하는 자원봉사 프로그램입니다." % (esc(p["title"]), esc(region))]
    lead.append("모집 기관은 %s이고 봉사 기간은 %s입니다." % (esc(d.get("mnnstNm") or p["org"]), esc(period(p["bgn"], p["end"]))))
    if cat:
        lead.append("봉사 분야는 %s입니다." % esc(cat))
    if targets:
        lead.append("%s 참여가 가능합니다." % "·".join(targets))
    if d.get("rcritNmpr") and d["rcritNmpr"] != "0":
        lead.append("모집 인원은 %s명입니다." % esc(d["rcritNmpr"]))
    if dl is not None and 0 <= dl <= 30:
        lead.append("봉사 기간이 끝나기까지 %d일 남았습니다." % dl)
    rows = [("봉사 기간", period(p["bgn"], p["end"])), ("모집 기간", period(d.get("noticeBgnde"), d.get("noticeEndde"))), ("봉사 시간", hours), ("봉사 요일", wk),
            ("봉사 분야", cat), ("모집 인원", (d.get("rcritNmpr") + "명") if d.get("rcritNmpr") and d["rcritNmpr"] != "0" else ""), ("참여 대상", " · ".join(targets)),
            ("모집 기관", d.get("mnnstNm") or p["org"]), ("봉사 장소", d.get("actPlace")), ("주소", addr), ("기관 연락처", phone(d.get("telno"))),
            ("1365 프로그램 등록번호", p["id"])]
    tbl = '<div class="tbl-wrap"><table class="tbl">%s</table></div>' % "".join("<tr><th>%s</th><td>%s</td></tr>" % (a, esc(b)) for a, b in rows if b)
    body = ['<div class="page-head"><h1>%s</h1><p>%s · %s</p></div>' % (esc(p["title"]), esc(region), esc(d.get("mnnstNm") or p["org"])),
            '<p class="lead">%s</p>' % " ".join(lead), ad(), '<h2 class="group-title">봉사 정보</h2>', tbl]
    if d.get("progrmCn"):
        body.append('<h2 class="group-title">활동 내용</h2><div class="lead">%s</div>' % text_block(d["progrmCn"]))
    if addr:
        body.append('<p><a class="btn" href="https://map.kakao.com/?q=%s">🗺️ 지도에서 위치 보기</a></p>' % urllib.parse.quote(addr))
    body.append('<div class="note-box">이 정보는 1365자원봉사포털에 등록된 모집 내용입니다. 신청 방법과 마감 여부는 <a href="https://www.1365.go.kr" rel="nofollow noopener">1365자원봉사포털</a>에서 프로그램 등록번호(%s)로 검색해 확인하세요.</div>' % esc(p["id"]))
    sib = [o for o in by_gugun.get(p["gcode"], []) if o is not p][:8]
    if sib:
        body.append('<h2 class="group-title">같은 지역 다른 봉사활동 <small>%s</small></h2>' % esc(region))
        body.append(ptable(sib))
    osib = [o for o in by_org.get((p["org"], p["gcode"]), []) if o is not p and o not in sib][:6]
    if osib:
        body.append('<h2 class="group-title">같은 기관의 다른 봉사활동</h2>')
        body.append(ptable(osib))
    chips = ['<a class="chip" href="/region/%s/">%s 봉사활동</a>' % (q(p["sido"]), esc(p["sido"]))]
    gh = bool(p["gugun"]) and len(hubs.get((p["sido"], p["gugun"]), [])) >= 2
    if gh:
        chips.append('<a class="chip" href="/region/%s/%s/">%s 봉사활동</a>' % (q(p["sido"]), q(p["gugun"]), esc(region)))
    if "청소년" in targets:
        chips.append('<a class="chip" href="/youth/">청소년 봉사활동</a>')
    body.append('<div class="chips">%s</div>' % "".join(chips))
    faq = [("이 봉사활동은 누가 참여할 수 있나요?", ("%s 참여가 가능한 것으로 등록돼 있습니다. 세부 자격 조건은 활동 내용과 모집 기관 안내를 확인하세요." % "·".join(targets)) if targets else "참여 대상은 모집 기관이 정합니다. 활동 내용과 기관 안내를 확인하세요."),
           ("신청은 어디서 하나요?", "1365자원봉사포털(www.1365.go.kr)에서 프로그램 등록번호(%s)로 검색해 신청할 수 있습니다. 기관에 직접 문의가 필요한 경우 위의 기관 연락처를 이용하세요." % p["id"]),
           ("봉사 시간은 인정되나요?", "봉사 시간 인정 여부와 방식은 모집 기관과 1365 시스템의 실적 등록 절차에 따라 다릅니다. 참여 전에 모집 기관에 확인하세요.")]
    crumbs = [("홈", "/"), (p["sido"], "/region/%s/" % p["sido"])] + ([(p["gugun"], "/region/%s/%s/" % (p["sido"], p["gugun"]))] if gh else []) + [((p["title"][:28] + "…") if len(p["title"]) > 28 else p["title"], "/program/%s/" % p["id"])]
    ld = [{"@context": "https://schema.org", "@type": "VolunteerAction", "name": p["title"], "location": {"@type": "Place", "name": d.get("actPlace") or region, **({"address": addr} if addr else {})},
           **({"startDate": "%s-%s-%s" % (p["bgn"][:4], p["bgn"][4:6], p["bgn"][6:8])} if re.fullmatch(r"\d{8}", p["bgn"]) else {}),
           **({"endDate": "%s-%s-%s" % (p["end"][:4], p["end"][4:6], p["end"][6:8])} if re.fullmatch(r"\d{8}", p["end"]) else {})}]
    title = "%s - %s 자원봉사 모집" % (p["title"], region)
    if dup.get((p["title"], region), 0) > 1:  # 같은 제목·지역의 회차별 프로그램은 시작일(그래도 같으면 등록번호)로 구분
        title = "%s (%s 시작) - %s 자원봉사 모집" % (p["title"], ymd(p["bgn"]), region)
        if dup.get((p["title"], region, p["bgn"]), 0) > 1:
            title = "%s (등록번호 %s) - %s 자원봉사 모집" % (p["title"], p["id"], region)
    desc = "%s 자원봉사 모집: %s. 봉사 기간 %s%s, 모집 기관 %s." % (region, p["title"], period(p["bgn"], p["end"]), (", " + cat + " 분야") if cat else "", d.get("mnnstNm") or p["org"])
    write("/program/%s/" % p["id"], layout("/program/%s/" % p["id"], title, desc, "\n".join(body), faq, crumbs, "article", ld, coupang=True), "0.6")


def build():
    ps, tags, gname = load()
    print("프로그램", len(ps), "상세 보유", sum(1 for p in ps if p["d"]), "시군구 이름 확인", len({p["gcode"] for p in ps if p["gugun"]}), "/", len({p["gcode"] for p in ps}))
    youth_ids = set(tags.get("youth", [])) if tags else {p["id"] for p in ps if p["d"] and p["d"].get("yngbgsPosblAt") == "Y"}
    by_sido, by_gugun, by_org, by_gname = collections.defaultdict(list), collections.defaultdict(list), collections.defaultdict(list), collections.defaultdict(list)
    for p in ps:
        by_sido[p["sido"]].append(p)
        by_gugun[p["gcode"]].append(p)
        by_org[(p["org"], p["gcode"])].append(p)
        if p["gugun"]:
            by_gname[(p["sido"], p["gugun"])].append(p)
    for L in list(by_sido.values()) + list(by_gugun.values()) + list(by_org.values()) + list(by_gname.values()):
        L.sort(key=lambda p: (p["d"] is None, recency(p)))
    dup = collections.Counter()
    for p in ps:
        if p["d"]:
            rg = (p["sido"] + " " + p["gugun"]).strip()
            dup[(p["title"], rg)] += 1
            dup[(p["title"], rg, p["bgn"])] += 1
    # _site 폴더 자체는 두고 내용만 비운다(다른 프로세스가 폴더를 붙잡고 있어도 빌드가 실패하지 않도록)
    OUT.mkdir(parents=True, exist_ok=True)
    for ch in OUT.iterdir():
        shutil.rmtree(ch) if ch.is_dir() else ch.unlink()
    for p in ps:
        if p["d"]:
            page_program(p, by_gugun, by_org, by_gname, dup)
    # 시도 허브
    for sido, L in by_sido.items():
        gn = collections.Counter(p["gugun"] for p in L if p["gugun"])
        orgc = collections.Counter(p["org"] for p in L).most_common(8)
        cats = collections.Counter(p["d"].get("srvcClCode") for p in L if p["d"] and p["d"].get("srvcClCode")).most_common(6)
        body = ['<div class="page-head"><h1>%s 자원봉사 모집 %d건</h1><p>1365자원봉사포털 등록 프로그램</p></div>' % (esc(sido), len(L)), stat_line(L), ad()]
        if gn:
            body.append('<h2 class="group-title">시군구별</h2><div class="chips">%s</div>' % "".join(('<a class="chip" href="/region/%s/%s/">%s <small>%d</small></a>' % (q(sido), q(k), esc(k), v)) if v >= 2 else '<span class="chip">%s <small>%d</small></span>' % (esc(k), v) for k, v in gn.most_common(80)))
        body.append('<h2 class="group-title">봉사 프로그램 <small>최근 등록 순 · 상위 300건</small></h2>')
        body.append(ptable(L, 300, show_region=True))
        if len(L) > 300:
            body.append('<p class="note">프로그램이 많아 최근 등록된 300건만 표시했습니다. 시군구별 페이지에서 지역을 좁혀 보세요.</p>')
        body.append('<h2 class="group-title">모집이 많은 기관</h2><ul class="lead">%s</ul>' % "".join("<li>%s <small>(%d건)</small></li>" % (esc(a), b) for a, b in orgc))
        if cats:
            body.append('<p class="note">상세 정보가 확인된 프로그램 기준 분야: %s</p>' % ", ".join("%s %d건" % (esc(a), b) for a, b in cats))
        faq = [("%s에서 봉사활동은 어떻게 신청하나요?" % sido, "1365자원봉사포털에서 지역·분야로 검색해 신청하거나, 이 사이트의 시군구별 목록에서 프로그램을 찾은 뒤 1365 프로그램 등록번호로 신청할 수 있습니다."),
               ("%s 봉사활동은 몇 건 있나요?" % sido, "오늘 기준 %d건이 모집 정보로 등록돼 있으며 매일 갱신됩니다." % len(L))]
        write("/region/%s/" % sido, layout("/region/%s/" % sido, "%s 자원봉사 모집 %d건 (봉사활동 찾기)" % (short_sido(sido), len(L)), "%s의 1365 자원봉사 모집 %d건을 시군구별로 정리했습니다. 청소년·성인 참여 가능 여부와 봉사 기간을 확인하세요." % (sido, len(L)), "\n".join(body), faq, [("홈", "/"), ("지역별", "/region/"), (sido, "/region/%s/" % sido)], coupang=True), "0.8")
    # 시군구 허브
    for (sido, g), L in by_gname.items():
        if len(L) < 2:
            continue
        orgc = collections.Counter(p["org"] for p in L).most_common(6)
        body = ['<div class="page-head"><h1>%s %s 자원봉사 모집 %d건</h1></div>' % (esc(sido), esc(g), len(L)), stat_line(L), ad(),
                '<h2 class="group-title">봉사 프로그램 <small>최근 등록 순</small></h2>', ptable(L, 300),
                '<h2 class="group-title">모집 기관</h2><ul class="lead">%s</ul>' % "".join("<li>%s <small>(%d건)</small></li>" % (esc(a), b) for a, b in orgc),
                '<div class="chips"><a class="chip" href="/region/%s/">%s 전체</a></div>' % (q(sido), esc(sido))]
        faq = [("%s %s 봉사활동은 어떻게 찾나요?" % (short_sido(sido), g), "이 페이지의 프로그램 목록에서 마음에 드는 활동을 고른 뒤 1365자원봉사포털에서 프로그램 등록번호로 신청하세요.")]
        write("/region/%s/%s/" % (sido, g), layout("/region/%s/%s/" % (sido, g), "%s %s 자원봉사 모집 %d건" % (short_sido(sido), g, len(L)), "%s %s의 1365 자원봉사 모집 %d건과 모집 기관을 정리했습니다." % (sido, g, len(L)), "\n".join(body), faq, [("홈", "/"), (sido, "/region/%s/" % sido), (g, "/region/%s/%s/" % (sido, g))], coupang=True), "0.7")
    # 지역 목록
    cards = "".join('<a class="card" href="/region/%s/"><b>%s</b><span>%d건 · 기관 %d곳</span></a>' % (q(s), esc(s), len(L), len({p["org"] for p in L})) for s, L in sorted(by_sido.items(), key=lambda t: -len(t[1])))
    write("/region/", layout("/region/", "지역별 자원봉사 모집 현황", "시도별 1365 자원봉사 모집 건수와 모집 기관 수를 한눈에 확인하세요.", '<div class="page-head"><h1>지역별 자원봉사 모집</h1><p>시도를 선택하세요</p></div>' + ad() + '<div class="card-grid">%s</div>' % cards, None, [("홈", "/"), ("지역별", "/region/")]), "0.8")
    # 모집 기관 허브
    n_org = 0
    for (org, gc), L in by_org.items():
        if len(L) < 3:
            continue
        slug = "%s-%s" % (re.sub(r"[\\/?#%&\"<>|:*\s]+", "-", org).strip("-")[:40], gc)
        region = (L[0]["sido"] + " " + L[0]["gugun"]).strip()
        body = ['<div class="page-head"><h1>%s 자원봉사 모집 %d건</h1><p>%s</p></div>' % (esc(org), len(L), esc(region)), stat_line(L), ad(), ptable(L, 200)]
        faq = [("%s은(는) 어떤 봉사활동을 모집하나요?" % org, "현재 1365자원봉사포털에 %d건의 봉사 프로그램을 등록해 두었습니다. 위 목록에서 활동 내용과 기간을 확인하세요." % len(L))]
        write("/org/%s/" % slug, layout("/org/%s/" % slug, "%s(%s) 자원봉사 모집 %d건" % (org, short_sido(L[0]["sido"]) + (" " + L[0]["gugun"] if L[0]["gugun"] else ""), len(L)), "%s(%s)가 모집 중인 자원봉사 프로그램 %d건의 기간과 활동 내용을 정리했습니다." % (org, region, len(L)), "\n".join(body), faq, [("홈", "/"), (region or "지역", "/region/%s/" % L[0]["sido"]), (org, "/org/%s/" % slug)]), "0.5")
        n_org += 1
    # 청소년
    Y = [p for p in ps if p["id"] in youth_ids]
    Y.sort(key=lambda p: (p["d"] is None, recency(p)))
    ys = collections.Counter(p["sido"] for p in Y)
    body = ['<div class="page-head"><h1>청소년 자원봉사 모집 %d건</h1><p>청소년 참여가 가능한 것으로 등록된 봉사활동</p></div>' % len(Y),
            '<p class="lead">1365자원봉사포털에서 <b>청소년 참여 가능</b>으로 등록된 봉사활동 <b>%d건</b>입니다. 시도별로 나눠 볼 수 있고, 학교 봉사활동 시간이 필요한 경우 모집 기관에 시간 인정 여부를 미리 확인하세요.</p>' % len(Y), ad(),
            '<div class="chips">%s</div>' % "".join('<a class="chip" href="/youth/%s/">%s <small>%d</small></a>' % (q(s), esc(short_sido(s)), n) for s, n in ys.most_common()),
            '<h2 class="group-title">최근 등록된 청소년 봉사활동</h2>', ptable(Y, 150, show_region=True)]
    faq = [("청소년도 봉사활동을 신청할 수 있나요?", "프로그램마다 청소년 참여 가능 여부가 다릅니다. 이 목록은 청소년 참여 가능으로 등록된 프로그램입니다. 연령·보호자 동의 등 조건은 모집 기관에 확인하세요."),
           ("학교 봉사활동 시간으로 인정되나요?", "인정 여부는 학교와 모집 기관의 기준에 따라 다릅니다. 참여 전에 학교 담당 교사와 모집 기관에 확인하세요.")]
    write("/youth/", layout("/youth/", "청소년 자원봉사 모집 %d건 - 청소년 봉사활동 찾기" % len(Y), "청소년이 참여할 수 있는 1365 자원봉사 모집 %d건을 지역별로 정리했습니다." % len(Y), "\n".join(body), faq, [("홈", "/"), ("청소년 봉사", "/youth/")], coupang=True), "0.9")
    for s, n in ys.items():
        L = [p for p in Y if p["sido"] == s]
        body = ['<div class="page-head"><h1>%s 청소년 자원봉사 모집 %d건</h1></div>' % (esc(s), len(L)), '<p class="lead">%s에서 청소년 참여가 가능한 것으로 등록된 봉사활동 <b>%d건</b>입니다.</p>' % (esc(s), len(L)), ad(), ptable(L, 200, show_region=True)]
        write("/youth/%s/" % s, layout("/youth/%s/" % s, "%s 청소년 자원봉사 모집 %d건" % (short_sido(s), len(L)), "%s에서 청소년이 참여할 수 있는 1365 자원봉사 모집 %d건을 정리했습니다." % (s, len(L)), "\n".join(body), None, [("홈", "/"), ("청소년 봉사", "/youth/"), (s, "/youth/%s/" % s)]), "0.7")
    # 분야별 (tags.json 이 있을 때만: 분야 코드 필터로 얻은 분류)
    fields = {}
    pid = {p["id"]: p for p in ps}
    for lab, ids in (tags.get("cat") or {}).items():
        L = sorted((pid[i] for i in ids if i in pid), key=lambda p: (p["d"] is None, recency(p)))
        if len(L) >= 5:
            fields[lab] = L
    for lab, L in fields.items():
        ss = collections.Counter(p["sido"] for p in L)
        body = ['<div class="page-head"><h1>%s 분야 자원봉사 모집 %d건</h1><p>1365자원봉사포털 분야별 분류</p></div>' % (esc(lab), len(L)), stat_line(L), ad(),
                '<h2 class="group-title">지역별</h2><div class="chips">%s</div>' % "".join(('<a class="chip" href="/field/%s/%s/">%s <small>%d</small></a>' % (q(lab), q(sd), esc(short_sido(sd)), n)) if n >= 5 else '<span class="chip">%s <small>%d</small></span>' % (esc(short_sido(sd)), n) for sd, n in ss.most_common()),
                '<h2 class="group-title">봉사 프로그램 <small>최근 등록 순</small></h2>', ptable(L, 200, show_region=True)]
        faq = [("%s 분야 봉사활동은 어떤 활동인가요?" % lab, "1365자원봉사포털에서 '%s' 분야로 분류된 봉사활동입니다. 구체적인 활동 내용은 각 프로그램 상세에서 확인하세요." % lab)]
        write("/field/%s/" % lab, layout("/field/%s/" % lab, "%s 분야 자원봉사 모집 %d건" % (lab, len(L)), "1365자원봉사포털의 %s 분야 봉사활동 %d건을 지역별로 정리했습니다." % (lab, len(L)), "\n".join(body), faq, [("홈", "/"), ("분야별", "/field/"), (lab, "/field/%s/" % lab)], coupang=True), "0.7")
        for sd, n in ss.items():
            if n >= 5:
                L2 = [p for p in L if p["sido"] == sd]
                b2 = ['<div class="page-head"><h1>%s %s 분야 자원봉사 모집 %d건</h1></div>' % (esc(sd), esc(lab), len(L2)), stat_line(L2), ad(), ptable(L2, 200)]
                write("/field/%s/%s/" % (lab, sd), layout("/field/%s/%s/" % (lab, sd), "%s %s 분야 자원봉사 %d건" % (short_sido(sd), lab, len(L2)), "%s의 %s 분야 자원봉사 모집 %d건을 정리했습니다." % (sd, lab, len(L2)), "\n".join(b2), None, [("홈", "/"), (lab, "/field/%s/" % lab), (sd, "/field/%s/%s/" % (lab, sd))]), "0.6")
    if fields:
        cards = "".join('<a class="card" href="/field/%s/"><b>%s</b><span>%d건</span></a>' % (q(l), esc(l), len(L)) for l, L in sorted(fields.items(), key=lambda t: -len(t[1])))
        write("/field/", layout("/field/", "분야별 자원봉사 모집", "1365 자원봉사 분야별 모집 건수를 확인하고 관심 분야 봉사활동을 찾으세요.", '<div class="page-head"><h1>분야별 자원봉사 모집</h1></div>' + ad() + '<div class="card-grid">%s</div>' % cards, None, [("홈", "/"), ("분야별", "/field/")]), "0.7")
    # 마감 임박
    soon = sorted([p for p in ps if dday(p["end"]) is not None and 0 <= dday(p["end"]) <= 21], key=closing_key)
    body = ['<div class="page-head"><h1>마감 임박 자원봉사 %d건</h1><p>봉사 기간이 3주 안에 끝나는 프로그램</p></div>' % len(soon),
            '<p class="lead">봉사 기간이 <b>21일 이내</b>에 끝나는 프로그램을 종료일이 빠른 순으로 모았습니다. 이미 시작한 활동도 포함되니 신청 가능 여부는 1365자원봉사포털과 모집 기관에서 확인하세요.</p>', ad(), ptable(soon, 300, show_region=True)]
    write("/closing/", layout("/closing/", "마감 임박 자원봉사 %d건 (3주 이내 종료)" % len(soon), "봉사 기간이 3주 안에 끝나는 1365 자원봉사 %d건을 종료일 순으로 정리했습니다." % len(soon), "\n".join(body), None, [("홈", "/"), ("마감 임박", "/closing/")], coupang=True), "0.8")
    # 홈
    newest = sorted([p for p in ps if p["status"] != "3"], key=recency)[:12]
    cards = "".join('<a class="card" href="/region/%s/"><b>%s</b><span>%d건</span></a>' % (q(s), esc(short_sido(s)), len(L)) for s, L in sorted(by_sido.items(), key=lambda t: -len(t[1])))
    body = ['<div class="hero"><h1>자원봉사 모집 찾기</h1><p>1365자원봉사포털에 올라온 봉사활동 %s건을 지역·청소년 여부로 쉽게 찾으세요</p>'
            '<div class="today-box"><div><small>모집 프로그램</small><b>%s건</b></div><div><small>모집 기관</small><b>%s곳</b></div><div><small>청소년 가능</small><b>%s건</b></div></div></div>' % (
                "{:,}".format(len(ps)), "{:,}".format(len(ps)), "{:,}".format(len({p["org"] for p in ps})), "{:,}".format(len(Y))),
            '<div class="search-box"><input id="q" type="search" placeholder="봉사 검색 (예: 노인, 도서관, 은평구)" autocomplete="off"><div id="sr" class="sr-list"></div></div>',
            ad(), '<h2 class="group-title">지역별</h2><div class="card-grid">%s</div>' % cards,
            '<p><a class="btn" href="/youth/">청소년 봉사활동 %d건</a> <a class="btn" href="/closing/">마감 임박 %d건</a>%s</p>' % (len(Y), len(soon), ' <a class="btn" href="/field/">분야별 봉사활동</a>' if fields else ""),
            '<h2 class="group-title">최근 등록된 봉사활동</h2>', ptable(newest, 12, show_region=True),
            '<script src="/assets/js/search.js"></script>']
    faq = [("봉사활동은 어디서 신청하나요?", "행정안전부 1365자원봉사포털(www.1365.go.kr)에서 신청합니다. 이 사이트는 포털에 등록된 모집 정보를 지역·대상별로 정리한 것이며 신청은 1365에서 합니다."),
           ("정보는 얼마나 자주 갱신되나요?", "공공데이터포털의 1365 봉사참여정보를 매일 받아 갱신합니다. 마감과 변경은 1365와 모집 기관에서 최종 확인하세요."),
           ("청소년도 참여할 수 있는 봉사가 있나요?", "있습니다. 청소년 참여 가능으로 등록된 프로그램을 따로 모았습니다. 학교 봉사시간 인정 여부는 모집 기관과 학교에 확인하세요.")]
    ld = [{"@context": "https://schema.org", "@type": "WebSite", "name": "우아봉사", "url": BASE + "/", "potentialAction": {"@type": "SearchAction", "target": BASE + "/?q={q}", "query-input": "required name=q"}}]
    write("/", layout("/", "자원봉사 모집 찾기 - 지역별·청소년 봉사활동 %s건 | 우아봉사" % "{:,}".format(len(ps)), "1365자원봉사포털에 올라온 자원봉사 %s건을 지역별·청소년 참여 여부로 찾고 봉사 기간과 모집 기관을 확인하세요." % "{:,}".format(len(ps)), "\n".join(body), faq, None, "website", ld, coupang=True), "1.0")
    # 검색 인덱스: [제목, 링크, 기관, 지역, 종료일]
    idx = []
    for p in sorted(ps, key=recency):
        link = "/program/%s/" % p["id"] if p["d"] else (("/region/%s/%s/" % (p["sido"], p["gugun"])) if p["gugun"] and len(by_gname[(p["sido"], p["gugun"])]) >= 2 else "/region/%s/" % p["sido"])
        idx.append([p["title"], link, p["org"], (short_sido(p["sido"]) + " " + p["gugun"]).strip(), p["end"][2:]])
    (OUT / "search_index.json").write_text(json.dumps(idx, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    pages_static(len(ps))
    finish()
    print("모집기관 허브", n_org)


def pages_static(n):
    body = ['<div class="page-head"><h1>봉사활동 찾는 방법과 이용 안내</h1><p>1365자원봉사포털 정보를 쉽게 찾기</p></div>', ad(),
            '<h2 class="group-title">1. 이 사이트에서 봉사활동 찾기</h2><ol class="lead"><li><a href="/region/">지역별</a>에서 시도·시군구를 고르거나 홈의 검색창에 지역·주제를 입력합니다.</li><li>청소년이라면 <a href="/youth/">청소년 봉사</a> 목록을 이용합니다.</li><li>프로그램 상세에서 봉사 기간·시간·장소·모집 기관을 확인합니다.</li><li>1365자원봉사포털에서 <b>프로그램 등록번호</b>로 검색해 신청합니다.</li></ol>',
            '<h2 class="group-title">2. 신청 전 확인할 점</h2><ul class="lead"><li><b>모집 마감</b>: 이 사이트의 정보는 매일 갱신되지만 마감은 1365와 기관에서 최종 확인하세요.</li><li><b>참여 대상</b>: 청소년·성인·가족·단체 가능 여부가 프로그램마다 다릅니다.</li><li><b>봉사 시간 인정</b>: 학교·기관별 인정 기준이 다르니 참여 전에 확인하세요.</li><li><b>준비물과 복장</b>: 활동 내용에 적혀 있지 않으면 기관에 문의하세요.</li></ul>',
            '<div class="note-box">이 사이트는 공공데이터를 정리한 참고용이며 신청·실적 관리는 1365자원봉사포털에서 이루어집니다.</div>']
    faq = [("봉사활동 신청은 이 사이트에서 하나요?", "아닙니다. 신청은 1365자원봉사포털에서 합니다. 이 사이트는 모집 정보를 지역·대상별로 찾기 쉽게 정리합니다.")]
    write("/guide/", layout("/guide/", "봉사활동 찾는 방법과 이용 안내", "1365 자원봉사 정보를 지역·청소년 대상으로 찾고 신청 전 확인할 점을 정리했습니다.", "\n".join(body), faq, [("홈", "/"), ("이용 안내", "/guide/")]), "0.7")
    body = ['<div class="page-head"><h1>데이터 설명</h1></div>', '<p class="lead">우아봉사는 행정안전부 <b>봉사참여정보서비스</b>(공공데이터포털 15157582, 1365자원봉사포털 제공)를 매일 받아 정리합니다. 현재 %d건의 프로그램이 게시돼 있습니다. 프로그램 상세(장소·활동 내용·참여 대상)는 호출 한도 때문에 매일 일부씩 받아 쌓으므로, 목록에는 있지만 상세 페이지가 아직 없는 프로그램이 있을 수 있습니다. 모집 기관 담당자의 이름·이메일은 게시하지 않습니다.</p>' % n]
    write("/about/", layout("/about/", "데이터 설명", "우아봉사가 사용하는 1365 봉사참여정보와 정리 방법을 설명합니다.", "\n".join(body), None, [("홈", "/"), ("데이터 설명", "/about/")]), "0.3")
    body = ['<div class="page-head"><h1>개인정보처리방침</h1></div>', '<p class="lead">우아봉사는 회원가입·로그인 없이 이용하며 이용자의 개인정보를 수집하지 않습니다. 사이트 개선을 위해 Google Analytics가 익명 방문 통계를 수집하고, Google AdSense와 쿠팡 파트너스가 광고를 표시하면서 쿠키를 사용할 수 있습니다. 게시된 봉사 모집 정보는 공공데이터포털에 공개된 자료입니다.</p>']
    write("/privacy/", layout("/privacy/", "개인정보처리방침", "우아봉사 개인정보처리방침", "\n".join(body), None, [("홈", "/"), ("개인정보처리방침", "/privacy/")]), sitemap=False)


def finish():
    shutil.copytree(ROOT / "assets", OUT / "assets")
    for nf in ROOT.glob("naver*.html"):
        shutil.copy(nf, OUT / nf.name)
    today = TODAY.isoformat()
    urls = "".join("<url><loc>%s%s</loc><lastmod>%s</lastmod><priority>%s</priority></url>" % (BASE, q(p), today, pr) for p, pr in WRITTEN)
    (OUT / "sitemap.xml").write_text('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">%s</urlset>\n' % urls, encoding="utf-8")
    (OUT / "robots.txt").write_text("User-agent: *\nAllow: /\n\nSitemap: %s/sitemap.xml\n" % BASE, encoding="utf-8")
    (OUT / "CNAME").write_text("wooabongsa.wooahouse.com\n", encoding="utf-8")
    nf = layout("/404.html", "페이지를 찾을 수 없습니다", "요청한 페이지를 찾을 수 없습니다. 마감된 봉사 모집은 목록에서 사라집니다.", '<div class="page-head"><h1>페이지를 찾을 수 없습니다</h1><p>마감된 봉사 모집 페이지는 삭제될 수 있습니다.</p></div><div class="chips"><a class="chip" href="/">홈</a><a class="chip" href="/region/">지역별 봉사</a></div>', None, None, noindex=True)
    (OUT / "404.html").write_text(nf, encoding="utf-8")
    print("페이지", len(WRITTEN), "(sitemap)")


if __name__ == "__main__":
    build()
