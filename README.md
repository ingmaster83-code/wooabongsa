# 우아봉사 (wooabongsa)

행안부 1365자원봉사포털 봉사참여정보(공공데이터포털 15157582, `apis.data.go.kr/1741000/volunteerPartcptnService`)로 만든 자원봉사 모집 사이트(Python 정적 생성기). https://wooabongsa.wooahouse.com

- `scripts/fetch_data.py` — `getVltrCategoryList`로 현재 모집 중인 프로그램 목록(약 9.6k) 전체를 받아 `data/list.json.gz`, 처음 보는 프로그램만 `getVltrPartcptnItem`으로 상세를 받아 `data/details/{id//2000}.json.gz`에 누적(목록에서 사라지면 제거).
  - **개발계정 일일 호출 한도 ≈ 1,000회**(초과 시 `LIMITED_NUMBER_OF_SERVICE_REQUESTS_EXCEEDS_ERROR`). 하루 예산 900건만 받고 멈춘다(`--budget`/`DAILY_BUDGET`). 초당 제한(코드 23)은 별개라 0.6초 간격 + 15초 대기 재시도. 운영계정으로 전환하면 예산을 늘린다.
  - 받는 순서: 상세가 없는 시군구 우선(시군구 이름은 상세의 `nanmmbyNm`에서만 얻을 수 있음) → 종료일이 먼 순.
  - 응답이 한 번 더 이스케이프돼 있어(`&amp;`) 빌드에서 `html.unescape`. XML 제어문자는 제거 후 파싱.
- `scripts/build_site.py` — `_site/` 생성: 프로그램 상세(상세 보유분만), 시도·시군구(이름 확인된 곳만) 허브, 모집기관 허브(3건 이상), 청소년, 마감 임박, 안내, 검색 인덱스.
- 담당자 이름·이메일은 게시하지 않는다(기관 대표 전화만).
- Actions: 매일 KST 00:30 fetch → 데이터 커밋 → 빌드 → 배포. 레포 시크릿 `API_KEY` 필요.
