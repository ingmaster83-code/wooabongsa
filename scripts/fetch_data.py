# -*- coding: utf-8 -*-
"""
우아봉사 수집기 — 행안부 봉사참여정보서비스(1365자원봉사포털, data.go.kr 15157582)

1) getVltrCategoryList 로 현재 모집 중인 프로그램 목록 전체(약 1만 건)를 받아 data/list.json.gz 에 저장한다.
2) 처음 보는 프로그램만 getVltrPartcptnItem 으로 상세를 받아 data/details/{등록번호//2000}.json.gz 에 누적한다.
   · 개발계정은 **일일 호출 한도가 약 1,000회**라(초과 시 LIMITED_NUMBER_OF_SERVICE_REQUESTS_EXCEEDS_ERROR) 하루 예산(기본 900건)만큼만 받고 멈춘다.
     내일 다시 돌리면 이어서 받는다. 운영계정으로 전환되면 DAILY_BUDGET 을 늘리면 된다.
   · 받는 순서: ① 시군구 코드별로 상세가 하나도 없는 곳(시군구 이름을 알아내려고) → ② 종료일이 먼 프로그램 순.
   · 상세는 거의 바뀌지 않으므로 캐시를 재사용한다. 목록에서 사라진(마감·삭제된) 프로그램은 캐시에서도 제거한다.
3) 초당 호출 제한(코드 23, "PER_SECOND")은 일일 한도와 다르다. 호출 간격 0.6초 + 코드 23이면 15초 쉬고 재시도.
키: 환경변수 API_KEY → DATA_GO_KR_API_KEY → 로컬 ../hosppass/.env 의 API_KEY (코드에 넣지 않는다).
사용: python scripts/fetch_data.py [--budget N]
"""
import gzip, json, os, re, sys, time
import xml.etree.ElementTree as ET
from pathlib import Path

import requests

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
DET = DATA / "details"
DET.mkdir(parents=True, exist_ok=True)
BASE = "https://apis.data.go.kr/1741000/volunteerPartcptnService/"
BAD = {c for c in range(0, 32) if c not in (9, 10, 13)} | {0xFFFE, 0xFFFF}
GAP = 0.6
BUCKET = 2000


class DailyLimit(Exception):
    pass


CALLS = 0  # 이번 실행의 API 호출 수(일일 한도 예산 계산용)


def api_key():
    for name in ("API_KEY", "DATA_GO_KR_API_KEY"):
        if os.environ.get(name):
            return os.environ[name].strip()
    for p in (ROOT / ".env", ROOT.parent / "hosppass" / ".env"):
        if p.exists():
            m = re.search(r"^API_KEY\s*=\s*(\S+)", p.read_text(encoding="utf-8"), re.M)
            if m:
                return m.group(1).strip("\"'")
    sys.exit("환경변수 API_KEY 가 필요합니다.")


KEY = api_key()
S = requests.Session()
S.headers["User-Agent"] = "Mozilla/5.0"


def clean(t):
    return "".join(ch for ch in t if ord(ch) not in BAD)


def call(op, **params):
    global CALLS
    last = ""
    for attempt in range(8):
        try:
            CALLS += 1
            r = S.get(BASE + op, params=dict(serviceKey=KEY, **params), timeout=90)
            txt = clean(r.content.decode("utf-8", "replace"))
            if "LIMITED_NUMBER_OF_SERVICE_REQUESTS_PER_SECOND" in txt or "<returnReasonCode>23<" in txt:
                last = "rate"
                time.sleep(15 + 5 * attempt)
                continue
            if "LIMITED_NUMBER_OF_SERVICE_REQUESTS_EXCEEDS" in txt or "<returnReasonCode>22<" in txt:
                raise DailyLimit(txt[:200])
            root = ET.fromstring(txt.encode("utf-8"))
            if root.tag == "OpenAPI_ServiceResponse":
                raise RuntimeError(txt[:300])
            if root.findtext("./header/resultCode") != "00":
                raise RuntimeError(root.findtext("./header/resultMsg"))
            return root.find("./body")
        except (requests.RequestException, ET.ParseError) as e:
            last = str(e)
            time.sleep(3 + 3 * attempt)
    raise RuntimeError("API 실패: %s %s" % (op, last))


def rows(body):
    return [{c.tag: (c.text or "").strip() for c in it} for it in body.findall("./items/item")]


def fetch_list(quiet=False, **flt):
    out, page, n = [], 1, 1000
    while True:
        body = call("getVltrCategoryList", numOfRows=n, pageNo=page, **flt)
        out += rows(body)
        total = int(body.findtext("totalCount"))
        if not quiet:
            print("  목록 %d/%d" % (len(out), total), flush=True)
        if page * n >= total:
            return out
        page += 1
        time.sleep(GAP)


def fetch_tags(det, total):
    """목록 필터로 상세 없이도 청소년 가능·분야를 알아낸다(필터 호출 ~15회).
    분야 코드(upperClCode)는 처음 한 번 후보 코드를 찔러 알아내 data/catcodes.json 에 저장한다.
    코드→분야 이름은 상세(srvcClCode)가 있는 프로그램의 다수결로 정한다."""
    cp = DATA / "catcodes.json"
    codes = json.loads(cp.read_text(encoding="utf-8")) if cp.exists() else None
    if codes is None:
        codes = []
        cands = ["%02d00" % i for i in range(1, 21)] + ["%02d" % i for i in range(1, 21)]
        for c in cands:
            body = call("getVltrCategoryList", numOfRows=1, pageNo=1, upperClCode=c)
            n = int(body.findtext("totalCount"))
            print("   후보 코드", c, n)
            if 0 < n < total * 0.95:
                codes.append(c)
            time.sleep(GAP)
        cp.write_text(json.dumps(codes), encoding="utf-8")
    cats = {}
    for c in codes:
        cats[c] = [x["progrmRegistNo"] for x in fetch_list(quiet=True, upperClCode=c)]
        time.sleep(GAP)
    label = {}
    for c, ids in cats.items():
        votes = {}
        for i in ids:
            d = det.get(i)
            if d and d.get("srvcClCode"):
                votes[d["srvcClCode"]] = votes.get(d["srvcClCode"], 0) + 1
        label[c] = max(votes, key=votes.get) if votes else c
    out = {"cat": {}}
    for c, ids in cats.items():
        out["cat"].setdefault(label[c], []).extend(ids)
    print("  분야", {k: len(v) for k, v in out["cat"].items()})
    return out


def bucket_of(no):
    return int(no) // BUCKET


def load_details():
    det = {}
    for p in DET.glob("*.json.gz"):
        det.update(json.loads(gzip.open(p, "rt", encoding="utf-8").read()))
    return det


def save_details(det, only=None):
    """버킷별로 저장(바뀐 버킷만). 비어 있는 버킷 파일은 삭제."""
    byb = {}
    for no, d in det.items():
        byb.setdefault(bucket_of(no), {})[no] = d
    keep = set()
    for b, items in byb.items():
        if only is not None and b not in only:
            keep.add("%d.json.gz" % b)
            continue
        p = DET / ("%d.json.gz" % b)
        keep.add(p.name)
        blob = json.dumps(items, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
        if p.exists() and gzip.decompress(p.read_bytes()) == blob:
            continue
        with gzip.GzipFile(p, "wb", compresslevel=9, mtime=0) as f:
            f.write(blob)
    for p in DET.glob("*.json.gz"):
        if p.name not in keep:
            p.unlink()


def main():
    budget = int(sys.argv[sys.argv.index("--budget") + 1]) if "--budget" in sys.argv else int(os.environ.get("DAILY_BUDGET", "900"))
    lst = fetch_list()
    with gzip.open(DATA / "list.json.gz", "wt", encoding="utf-8", compresslevel=9) as f:
        json.dump(lst, f, ensure_ascii=False, separators=(",", ":"))
    ids = {x["progrmRegistNo"]: x for x in lst}
    print("현재 목록", len(lst), "건")
    det = load_details()
    n0 = len(det)
    det = {k: v for k, v in det.items() if k in ids}  # 목록에서 사라진 프로그램 제거
    print("캐시 상세", n0, "→ 유지", len(det))
    # 받을 순서: 상세가 없는 시군구 우선 → 종료일이 먼 순
    have_gugun = {ids[k]["gugunCd"] for k in det if k in ids}
    todo = [i for i in ids if i not in det]
    todo.sort(key=lambda i: (ids[i]["gugunCd"] in have_gugun, -int(ids[i].get("progrmEndde") or 0)))
    try:
        tags = fetch_tags(det, len(lst))
        with gzip.open(DATA / "tags.json.gz", "wt", encoding="utf-8", compresslevel=9) as f:
            json.dump(tags, f, ensure_ascii=False, separators=(",", ":"))
    except DailyLimit as e:
        print("태그 수집 중 일일 한도 도달:", str(e)[:60].replace(chr(10), " "))
        todo = []
    todo = todo[:max(0, budget - CALLS)]
    print("이번에 받을 상세 %d건 (약 %.0f분, 예산 %d, 지금까지 호출 %d)" % (len(todo), len(todo) * GAP / 60, budget, CALLS), flush=True)
    t0, fail, done = time.time(), 0, 0
    touched = set()
    try:
        for n, no in enumerate(todo, 1):
            try:
                r = rows(call("getVltrPartcptnItem", progrmRegistNo=no))
                if r:
                    det[no] = r[0]
                    touched.add(bucket_of(no))
                    done += 1
            except DailyLimit:
                raise
            except Exception as e:
                fail += 1
                print("  실패", no, str(e)[:80])
                if fail > 40:
                    print("실패 과다, 중단")
                    break
            if n % 200 == 0:
                save_details(det)
                print("  상세 %d/%d (%.0f초) 실패 %d" % (n, len(todo), time.time() - t0, fail), flush=True)
            have_gugun.add(ids[no]["gugunCd"])
            time.sleep(GAP)
    except DailyLimit as e:
        print("일일 호출 한도 도달 — 여기까지 저장하고 종료:", str(e)[:80].replace("\n", " "))
    save_details(det)
    print("완료: 목록 %d, 상세 보유 %d, 이번 신규 %d (실패 %d)" % (len(lst), len(det), done, fail))


if __name__ == "__main__":
    main()
