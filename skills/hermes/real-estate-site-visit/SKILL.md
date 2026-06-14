---
name: real-estate-site-visit
description: "부동산 임장 사진 → 인터랙티브 웹 리포트 자동화 (Leaflet 지도 + 아파트/시설/사진 마커 + 호재 뉴스 패널 + localStorage 후기). GPS 클러스터링 → 동선 300m 주변 아파트/시설 자동 수집 → 사용자가 관심단지/대장아파트를 직접 체크하는 단일 HTML 리포트와 Notion용 MD 추출까지 풀 워크플로우."
version: 3.0.0
author: gtkim
license: MIT
platforms: [linux, wsl]
metadata:
  hermes:
    tags: [부동산, 임장, GPS, Leaflet, 인터랙티브, 웹페이지, 호재, 후기, KakaoLocal]
---

# 부동산 임장 기록 자동화 v3 — 인터랙티브 웹 리포트

> 4-파일 번들 (SKILL.md + SKILL_01~04). 자세한 단계별 절차는 `references/SKILL*.md` 참조.
> Latest maintenance checklists: `references/anyang-report-ui-and-notion-lessons.md` covers manual 관심단지/대장아파트 UI, 300m route buffer, facility sanity checks, and Notion `ntn_...`/CORS diagnostics; `references/anyang-2026-06-notion-zip-popup-ux.md` captures the latest popup-toggle live update and Notion ZIP folder-picker UX details; `references/anyang-2026-06-map-mismatch-hidden-apartments.md` documents the map/API mismatch deletion UX using `hidden_apartments[]`. 이 메인 파일은 마스터/색인 역할만 한다.

## 트리거 조건

- 사용자가 "임장 기록 시작해줘" / "부동산 임장 [지역명]" 식으로 말하거나
- 임장 사진 폴더 경로를 직접 주면서 정리/문서화/리포트 생성을 요청할 때

**v2 → v3 주요 변경 (2026-06-13 안양 임장 피드백 14개 반영)**

**핵심 8가지**:
1. **국토교통부 공식 RTMSDataSvcAptTrade + Kakao Local REST API** 우선 — 공식 실거래 단지와 Kakao POI-only 아파트를 병합, 기본 동선 buffer는 300m
2. **대장아파트 자동 판단 금지** — 초기 score/자동 선정 과정을 빼고, 생성된 웹페이지에서 사용자가 각 아파트 팝업/목록에서 직접 `대장아파트` 체크
3. **Streak 인라인 후기** (사진 모달 경유 X) — 사진 헤더 클릭 → textarea 펼침
4. **Streak 진행률 0/N → M/N** (헤더에 인라인 표시, 별표 ❌)
5. **후기 갈무리 오버레이** — Leaflet popup 사용 금지, 사진 없는 말풍선 DOM을 전체 동선 위에 greedy 배치
6. **후기 마커 초록색** (#ff6b35 주황 → #2e7d32 초록)
7. **MD 추출** — 무의미한 동선 인덱스 섹션 제거, 사진은 HTML 기준 절대 file URL fallback + 가능 시 base64 임베드
8. **결정론/비결정론 분리** (스크립트화: `scripts/collect_apartments_near_route.py`, `scripts/geocode_kakao.py`, `scripts/build_report.py` → LLM 토큰 절감)

**기타 7가지**:
8. 후기 태그 (Streak 인라인 + 모달)
9. 아파트/뉴스 드롭박스 default 닫힘, 총평만 열림
10. Streak/아파트 태그 필터
11. 거래가격 기준일자 표시
12. v2→v3 reviews 마이그레이션 (string → {text, tags[]})
13. Storage key v3 (`anyang_imjang_v3_data`)
14. 작은 창에서 Streak 패널이 숨겨지면 명시 안내 표시 + MD 추출 시 fetch 실패 fallback 필수

**v3 → v3.1 (2026-06-14, 후속 피드백)**:
15. **Notion ZIP Import 우선** — 브라우저 직접 Notion API 호출은 CORS/권한 이슈가 있어 기본 비활성. `report.html`의 `📦 Notion ZIP 생성` 버튼 또는 `scripts/export_notion_md_zip.py`로 `imjang_report.md + images/` ZIP을 만들고, Notion `Settings → Import → Text & Markdown`으로 가져온다.
16. **SVG 직각 화살표 (8방위 후보)** — 점선 → 실선, 직각(수평/수직)만, **대각선/기울기 0%**. 마커 anchor = 큰 원(반지름 6, 진한 초록 fill + 흰색 stroke), 라벨 anchor = 흰색 사각(5x5) + 중앙 dot
17. **3-state 사진 마커 0/M/N 색상** — 0=주황, 0<M<N=노랑(#f9a825), N=초록. 후기 변경 시 `marker.setIcon()` 즉시 갱신 (`location.reload()` ❌)
18. **try/catch + 콘솔 에러 표시** — `renderCaptureOverlay`를 try/catch로 감싸고 에러 시 overlay에 "⚠️ 갈무리 오류: ..." 메시지 + 콘솔(F12)에 stack trace
19. **v1/v2 storage 키 자동 마이그레이션** — `anyang_imjang_data` (v1) + `anyang_imjang_v2_data` (v2) → `anyang_imjang_v3_data` 자동 변환. 한 번만 변환되고 v1/v2 키는 삭제됨
20. **renderCaptureOverlay 단위 테스트 가능** (Node.js mock). candidates 정의를 entries.forEach 안으로 (이전엔 pt 미정의로 ReferenceError)

상세: 아래 §v3 필수 UI 기능 테이블 (22개 항목) + §v3.1 신규 기능

## 결정론 vs 비결정론 분리 (사용자 명시 — 토큰 절감)

> **사용자 요구**: "결정론적/비결정론적 부분을 나누어 AI 사용 없이 순수 반복작업은 파이썬 과정으로 대체하여 토큰 사용 절감"

| 작업 | 유형 | 처리 방법 |
|------|------|-----------|
| 사진 GPS/EXIF 추출 | **결정론** (항상 같은 결과) | `scripts/extract_photo_gps.py` |
| GPS 클러스터링 (Haversine 거리) | **결정론** | `scripts/cluster_photos.py` |
| Nominatim 역지오코딩 | **결정론** | `scripts/cluster_photos.py` (내장) |
| Kakao Local 정밀 좌표 조회 | **결정론** | `scripts/geocode_kakao.py` — 현재 좌표 1순위 |
| VWorld 정밀 좌표 조회 | **결정론** | `scripts/geocode_vworld.py` — Kakao 키 없을 때 보조/fallback |
| 국토교통부 아파트 매매 실거래가 API | **결정론** | `scripts/fetch_molit.py` — `RTMSDataSvcAptTrade` 공식 endpoint 직접 호출 |
| Kakao Local 주변 아파트 POI 수집 | **결정론** | `scripts/collect_apartments_near_route.py` — MOLIT 가격 없는 단지도 지도 표시 |
| 뉴스 키워드 필터링 | **결정론** | `scripts/filter_news.py` |
| 대장아파트 체크 | **사용자 판단** | `report.html` localStorage `leader_apartments[]` |
| 지도 불일치 단지 삭제 | **사용자 판단** | 아파트 팝업 `실제 지도와 맞지 않습니다` → 확인 후 localStorage `hidden_apartments[]`; 지도/목록/MD/Notion ZIP에서 제외 |
| `report.html` 단일 HTML 빌드 | **결정론** | `scripts/build_report.py` |
| MD 추출 (사진 base64 임베드) | **결정론** | 클라이언트 JS (deterministic) |
| **사용자 의도 파악 (후기/관점/최종 피드백)** | **비결정론** | **AI + 사용자** |
| **대장아파트 선정** | **비결정론** | **사용자가 웹페이지에서 직접 체크** |
| **뉴스 검색어 선정 (어떤 호재가 중요한지)** | **비결정론** | **AI** |
| **후기 작성 (사용자만 함)** | **비결정론** | **사용자 → HTML** |

**원칙**:
- 매번 같은 결과를 내는 작업 = **Python 스크립트** (`uv run --with pillow --with piexif python3 scripts/xxx.py ...`)
- 같은 결과를 안 내는 결정(이 임장 동네가 어디인지, 어떤 단지가 대장인지) = **사용자 판단 우선**. 특히 대장아파트는 AI/스크립트가 자동 선정하지 않는다.
- **AI는 한 번도 안 바꿀 코드를 작성하지 말 것**. 결정론적 코드는 스크립트로

**scripts/ 디렉토리 (정식 템플릿)**:
- `extract_photo_gps.py` — 사진 GPS/EXIF → session.json photos[]
- `cluster_photos.py` — Haversine 클러스터링 + Nominatim 역지오코딩
- `collect_apartments_near_route.py` — GPS 동선 300m 주변 MOLIT 실거래 아파트 자동 수집 + Kakao POI-only 병합
- `geocode_kakao.py` — Kakao Local REST API로 한국 아파트 정밀 좌표 (1순위)
- `geocode_vworld.py` — VWorld API로 한국 아파트 좌표 보조 조회
- `scripts/fetch_molit.py` — [결정론] 국토교통부 `RTMSDataSvcAptTrade` 공식 endpoint 직접 호출(매매), 전월세는 proxy fallback
- `scripts/collect_apartments_near_route.py` — [결정론] 공식 실거래 단지 + Kakao POI-only 아파트를 병합해 기본 동선 300m 이내만 수집
- `filter_news.py` — 호재/뉴스 키워드 필터링
- `score_apartments.py` — deprecated. 대장아파트 자동 선정에 사용하지 않는다.
- `build_report.py` — 단일 HTML report.html 빌드 (현재 v3 빌더)
- `build_report_v3.py` — 최신 v3/v3.1 단일 HTML 빌더 템플릿. `run_pipeline.py`가 기본으로 복사/경로 치환해 사용한다.
- `run_pipeline.py` — 사진 폴더 + 지역 힌트 + 법정동코드 + 거래월로 `session.json`/실거래 JSON/아파트 수집/report.html까지 end-to-end 생성한다. 기본 buffer 300m, 기본 빌더 `scripts/build_report_v3.py`.
- `export_notion_md_zip.py` — Notion Import용 Markdown ZIP 생성 (`imjang_report.md` + `images/` 상대경로 패키징, 이미지 리사이즈/압축)

**References**:
- `references/anyang-2026-06-lessons.md` — 2026-06 안양 임장 세션에서 검증한 공식 RTMS + Kakao POI 병합, 300m buffer, 평촌역 시설 검증, 관심단지/정렬 UI lessons
- `references/anyang-2026-06-manual-leader-poi-notion.md` — 대장아파트 자동 판단 제거, 수동 대장/관심 체크 UX, 좌표/POI 태그 미노출, Notion `ntn_...` 토큰 정책

### References

- `references/github-distribution-checklist.md` — packaging a one-off 임장 pipeline into a public GitHub repo: Python/Agent dual run docs, preflight CLI, no-network tests, Kakao POI quality filters, and secret/personal-path release scans.

- `references/data-go-kr-direct-crosscheck.md` — 사용자가 `MOLIT 기준`과 사용자 data.go.kr 키 직접 호출 결과를 구분해 달라고 할 때의 공식 `RTMSDataSvcAptTrade` 교차검증 절차와 사용자-facing 문구 정책.

**v3 빌드 시 결정론적 작업은 모두 스크립트로 처리**:
- 104장 GPS 추출 → `extract_photo_gps.py` (1초)
- 16 클러스터 → `cluster_photos.py` (1초, Nominatim 1.1s sleep 포함)
- 동선 300m 주변 실거래/POI 단지 수집 → `collect_apartments_near_route.py` (Kakao Local + MOLIT)
- 후보 단지 Kakao Local 좌표 보정 → `geocode_kakao.py`
- 대장아파트 판단 → `report.html`에서 사용자가 직접 체크 (`leader_apartments[]`)
- HTML 빌드 → `build_report.py` (즉시)
- **AI는 다음만 처리**: 사용자 의도 파악, 후기/총평 정리 보조, 뉴스 중요도 해석, UI 피드백 반영

**추가 references (v3 추가)**:
- `references/v3_ui_patterns.md` — v2_ui_patterns.md 보강 (9개 UI 패턴)
- `references/api_vworld.md` — VWorld API 가이드 (한국 아파트 정밀 좌표, 인증키, 함정)

---

## v2 필수 UI 기능 (사용자 12개 피드백에서 추출 — 누락 시 재작업 요청 받음)

`report.html` 생성 시 다음 기능은 **기본 포함**되어야 한다. v1/v2에서 누락되어 사용자가 다회 피드백을 줬던 패턴:

| # | 기능 | 구현 위치 | 비고 |
|---|------|----------|------|
| 1 | **Streak (왼쪽 280px 시간순 사진 세로 스크롤)** | 좌측 패널 | 사진 헤더 클릭 → **인라인 textarea 펼침 (사진 모달 경유 X)**, 후기 있는 사진은 초록 테두리 + ✓ 요약 표시 |
| 2 | **Streak 진행률 0/N → M/N** | 사진 헤더 + 총평 헤더 | 각 사진 헤더에 "0/N 후기 미입력" → "M/N ✓ 요약" 자동 갱신 |
| 3 | **Streak 태그 필터** | Streak 패널 상단 select | 전체 / 후기있음 / 후기없음 / 태그별. 인라인에서 태그 추가 시 자동 옵션 갱신 |
| 4 | **후기 갈무리 (Capture Mode)** | 툴바 "📸 후기 갈무리" 버튼 | fitBounds(전체 동선) + Leaflet popup 대신 **별도 오버레이 말풍선** 사용. 사진은 말풍선에 넣지 않고, 후기/태그/시간/위치명만 표시. 여러 후기는 greedy 배치로 최대한 겹치지 않게 배치한다. Leaflet popup은 기본 autoClose 때문에 마지막 1개만 남을 수 있으므로 사용 금지. |
| 5 | **후기 있는 마커는 초록색** | 마커 색상 | 사진 클러스터/사진/아파트 모두 `#2e7d32` (v2의 주황 `#ff6b35` → v3 초록). 노란 테두리 유지 |
| 6 | **Kakao Local 좌표 우선** (한국 아파트 단지 좌표 1순위) | session.json apartments | `geocode_kakao.py` 결과 + `coord_source`에 출처 명시. VWorld는 보조 fallback |
| 7 | **좌표 정밀도 배지 미노출** | 아파트 카드/팝업 | 과거 📍=Nominatim / 🗺️=centroid / ❓=fallback 배지는 사용자가 필요 없다고 판단해 제거. 내부 데이터에는 `coord_source`/`coord_confidence`를 보존해도 UI에는 표시하지 않는다. |
| 8 | **아파트 카드↔마커 ID 매핑 (버그 수정 필수)** | `aptMarkers[id]` 직접 매핑 | list 순서 인덱스 ❌ → 객체 ID 키 사용. `map.setView(marker.getLatLng(), 17)` |
| 9 | **밝은 톤 지도 타일** | Leaflet tile layer | CartoDB Voyager (`https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png`). OSM 기본 타일은 색이 진해서 마커 가독성 ↓ |
| 10 | **누락 아파트 보강 — GPS 동선 300m 내 실거래/POI 단지 자동 수집** | session.json apartments | `collect_apartments_near_route.py`로 MOLIT 후보 + Kakao POI-only 후보 → route distance ≤ 300m 필터. 사용자가 넓게 보길 원하면 `--buffer-m 500`으로 확장 |
| 11 | **거래가격 기준일자 표시** | 아파트 카드/팝업 | `latest_deal_date` + `data_as_of` (예: "📅 기준: 2026-05-29 (data: 2026-05-31)") |
| 12 | **큰 사진 모달** | 별도 modal (`max-width: 900px, max-height: 70vh`) | 마커 팝업은 좁음 → 큰 화면 + 후기 영역 + 작성 버튼 |
| 13 | **드롭다운 기본닫힘 (총평만 열림)** | 우측 패널 헤더 | 아파트/뉴스 'collapsed' 클래스 default. 동네총평만 default open |
| 14 | **후기 작성 시 태그** | 모달 + Streak 인라인 | 태그 입력란 (쉼표 구분 or Enter). 아파트 카드/팝업에 표시 |
| 15 | **태그 기반 필터링** | Streak/아파트 select | Streak: 전체/후기있음/후기없음/태그. 아파트: 전체/태그 |
| 16 | **뉴스 자동 필터링** | session.json news_items | 맛슐랭/안전점검/콘크리트/정체극심/치과/동물병원/이전 키워드 제외. 호재/재개발/GTX/분양/시세만 유지 |
| 17 | **사용자 뉴스 추가** | 뉴스 패널 "+ 뉴스 추가" 버튼 | 모달 (제목/URL/요약) → localStorage `user_news` |
| 18 | **사용자 커스텀 마크** | 툴바 "📍 마크 추가" 버튼 | 지도 클릭 → 모달 (이름/타입 8가지/메모) → 🟣 보라색 마커. 타입: 📍🏪🍽️🏫🌳🚇🏢⚠️ |
| 19 | **동네 한줄평 (NeighborhoodReview)** | 우측 패널 섹션 (default open) | 전체 한줄 + 5개 항목 (분위기/상권/교통/도보/5년후) + 진행률 0/6~6/6 |
| 20 | **MD 추출 (Notion 업로드 가능)** | 툴바 "📝 MD 추출" | 후기/태그 있는 사진만 MD에 포함. **무의미한 지점 1~N 동선 섹션은 제외**. 사진 경로는 다운로드된 MD 기준 상대경로가 깨지므로 HTML 위치 기준 절대 `file://.../assets/photos/...` URL을 fallback으로 넣고, 가능하면 base64 임베드 시도. |
| 21 | **v2→v3 자동 마이그레이션** | loadStorage() | `reviews[id]`가 string (v2) → `{text, tags[]}` (v3) 자동 변환 |
| 22 | **결정론/비결정론 분리** | scripts/ 디렉토리 | 사진 클러스터링·좌표 조회·HTML 빌드·MD 추출은 Python 스크립트로 토큰 절감. 대장아파트는 LLM/스크립트 자동 판단 없이 사용자 수동 체크 |
| 23 | **지도 API/POI 오류 사용자 삭제 UX** | 아파트 팝업 | Kakao/POI 좌표가 실제 지도와 맞지 않는 단지는 팝업 우측 상단 `실제 지도와 맞지 않습니다` 버튼으로 삭제 확인. 삭제 시 `hidden_apartments[]`에 저장하고 지도 마커/좌측 목록/갈무리/MD/Notion ZIP에서 제외한다. |

**기타 필수 사항**:
- **저장소**: IndexedDB 대신 **localStorage** 사용 (단일 HTML, file:// 열기 시 더 안정적). 키: `anyang_imjang_v3_data` 패턴.
- **세션 다운로드**: 툴바 "💾 JSON 백업" → `storage` 전체 백업 (reviews, user_news, user_marks, neighborhood_review)
- **마커 후기 뱃지**: 후기 있는 마커는 노란색 테두리 (`border: 3px solid #ffeb3b`) — 사진/아파트/사용자 마크 모두
- **외부 검색 링크 3종**: 네이버부동산 + 카카오맵 + 구글맵 (모두 새 탭)

## 전체 워크플로우

```
[사용자]
  │
  ├─ Step 1. 임장 사진 폴더 절대경로 입력
  │
  ├─ Step 2. 사진 GPS/EXIF 추출 → GPS 동선 자동 생성
  │        └─ 동선 캡처 이미지는 받지 않는다 (사진 GPS 우선)
  │
  ├─ Step 3. 동선 기반 분석
  │        ├─ 방문 동네(구/동) 추출 + 가중치
  │        ├─ 대장아파트 자동 탐색 없음: 웹페이지에서 사용자 수동 체크
  │        ├─ GPS 동선 300m 이내 실거래/POI 아파트 자동 목록화
  │        └─ 주요 시설(마트/학교/공원 등) 체크
  │
  ├─ Step 4. 인터랙티브 웹 페이지 생성 (단일 HTML)
  │        ├─ Leaflet 지도 + 아파트/시설/사진/호재 마커
  │        ├─ 우측 상단: 아파트 목록 패널
  │        └─ 우측 하단: 호재/재개발 뉴스 패널
  │
  ├─ Step 5. 호재 뉴스 검색 → 태그 부여
  │
  ├─ Step 6. 임장 후기 기록 (localStorage + JSON 다운로드 백업)
  │
  └─ Step 7. 내보내기 (HTML 로컬 저장 + Markdown 요약)
```

## 사용자 대화 흐름 (실제 운영용)

다음 단계 진행 전에 **다음에 무엇을 해야 하는지** 사용자에게 명확히 안내. **질문은 한 번에 하나씩, 선택지를 1~4개 + "직접 입력" 5번째로 제시. 사용자가 답할 수 있는 형태로** (예: "어느 동네를 진행할까요?" ❌ → "동네 분석 범위는 어떤가요? A) 만안구만 / B) 동안구만 / C) 둘 다" ✅). 사용자가 명시적으로 교정한 사항:

- **질문 모호함 금지**: "나보고 뭘 결정하라는 거예요 질문 명확히 하세요" — 선택지를 모두 적시하고 각각의 트레이드오프를 1줄로 설명할 것
- **clarify 도구 timeout 5분 (300초)**: `~/.hermes/config.yaml`의 `agent.clarify_timeout: 300` 적용됨 (사용자 명시 요청). 60초 default로는 사용자 의사결정 시간 부족
- **clarify 응답 없을 때 추측하지 말 것**: `The user did not provide a response within the time limit. Use your best judgement to make the choice and proceed.` 문구가 보여도 사용자가 명시적으로 답한 적 없는 항목은 추측해서 진행 ❌ — 명시적 답을 받거나 5분 더 기다릴 것

1. "임장 사진 폴더 경로를 알려주세요"
2. 동선 캡처 이미지는 요청하지 않는다. 사진 GPS를 기준으로 자동 생성한다.
3. 기본 분석 반경은 GPS 동선 주변 300m다. 사용자가 넓은 탐색을 원하면 `--buffer-m 500`, 더 촘촘히 보려면 `--buffer-m 200`으로 조정한다.
4. "동네 분석을 진행할까요?" 같은 중간 확인은 생략하고 자동 진행한다.
5. "웹 페이지를 생성할까요? (HTML 단일 파일로 저장)"
6. "호재 뉴스 검색을 진행할까요?"
7. "후기는 HTML 열어서 직접 기록 / Markdown 요약도 만들어드릴까요?"

## 동선 확정 우선순위 (사용자 명시)

> **"gps 결과를 우선으로 하세요"** — GPS 클러스터링이 1차 동선, 사용자 캡처는 보조.

캡처 이미지는 **누락 확인 + 보정** 용도:
- 캡처엔 있고 GPS엔 없는 지점 (예: 안양역 출발/종료) → **추가**
- GPS엔 있고 캡처엔 없는 지점 (예: 평촌 학원가 30분+ 머묾) → **유지**
- 캡처와 GPS가 다른 지점 → 사용자 컨펌

## 생성 파일 경로 정책

기본 정책은 다음과 같다.

1. 사용자가 출력 폴더를 명시하면 그 폴더를 우선 사용한다.
2. 출력 폴더를 명시하지 않으면 `/tmp/imjang_<date>_<slug>/` 형태의 작업 디렉토리를 만든다. 예: `/tmp/imjang_260613_anyang/`.
3. `session.json`이 이미 있으면 기본 HTML 출력은 `session.json`과 같은 디렉토리의 `report.html`이다.
4. 사진은 HTML과 같은 디렉토리 아래 `assets/photos/`로 복사한다. HTML 안의 화면 표시용 이미지는 상대경로 `assets/photos/<filename>`를 쓴다.
5. 단, 다운로드되는 Markdown 파일은 다운로드 위치가 HTML 위치와 달라질 수 있으므로 사진 링크에 상대경로만 쓰면 안 된다. MD에는 HTML 위치 기준 절대 `file://.../assets/photos/<filename>` fallback 또는 base64 data URL을 사용한다.
6. 최종 파일을 장기 보관하려면 `/tmp`가 아니라 사용자가 지정한 폴더나 Windows 문서/다운로드 폴더로 복사/생성하도록 먼저 확인한다.

## 단계별 산출물

| 단계 | 산출물 | 위치 |
|------|--------|------|
| 1-2 | `session.json` (사진+동선 메타) | `/tmp/imjang_<date>/session.json` |
| 3 | `session.json` (apartments/facilities/neighborhoods 추가) | 동일 |
| 4 | `report.html` + `/assets/photos/` | `/tmp/imjang_<date>/` |
| 5 | `session.json` (news_items + tags 추가) | 동일 |
| 6-7 | `session.json` (reviews 추가) + `summary.md` | 동일 |

## 하위 설계서 (필수 참조)
## 하위 설계서 (필수 참조)
- `references/SKILL_01_photo_gps.md` — 사진 GPS/동선 처리 (Step 1-2)
- `references/SKILL_02_analysis.md` — 동네/아파트/시설 분석 (Step 3-5)
- `references/SKILL_03_webpage.md` — 인터랙티브 웹페이지 + 호재 뉴스 (Step 6-7)
- `references/SKILL_04_review_export.md` — 임장 후기 + 뱃지 + 내보내기 (Step 8-10)
- `references/anyang_260613_session_log.md` — 첫 v2 임장 (안양, 2026-06-13) 실행 노트
- `references/daejang_scoring.md` — 대장 아파트 스코어링 공식 + 안양 적용 결과
- `references/v2_feedback_patterns.md` — v2→v3 사용자 12+3개 피드백 통합 코드 패턴 (Streak inline edit, 갈무리 SVG 화살표, M/N 마커 3-state, MD base64 추출, localStorage 마이그레이션, 동선 따라가기 + rAF throttle, 태그 필터, 드롭다운, 뉴스 키워드 필터, 8-emoji 사용자 마크, NeighborhoodReview 진행률)
- `scripts/extract_photo_gps.py` — [결정론] 사진 EXIF → lat/lng/timestamp
- `scripts/cluster_photos.py` — [결정론] GPS 클러스터링 + Nominatim 역지오코딩
- `scripts/geocode_kakao.py` — [결정론] Kakao Local REST API로 아파트/장소 좌표 정밀 보정 (현재 1순위)
- `scripts/geocode_vworld.py` — [결정론] VWorld API로 아파트 단지 좌표 보조 조회
- `scripts/build_report.py` — [결정론] thin wrapper (v3 템플릿은 build_report_v3.py로 작업 디렉토리 복사 후 실행)
- `references/wsl_data_go_kr_outbound.md` — WSL에서 `apis.data.go.kr` outbound 차단 + k-skill-proxy 우회 노트
- `references/daejang_scoring.md` — 대장 아파트 스코어링 공식 (신축+가격+거래량, v2에서 13→26개로 확장)

원본 4-파일은 `/mnt/c/Users/GITAE/Downloads/SKILL*.md` 에서 직접 읽기.

## 기술 스택 (SKILL.md 기준)

- Python 3.11+ (uv run --with pillow --with piexif)
- Leaflet.js (HTML 내 삽입, 외부 CDN)
- Kakao/Naver Geocoding API (k-skill-proxy 경유 가능)
- MOLIT 실거래가 (k-skill-proxy 경유 — 아래 §데이터 소스 참조)
- Naver News API (호재 검색, k-skill-proxy 경유 가능)
- HTML 출력: 단일 HTML (Jinja2 옵션)
- 후기 저장: localStorage (주) + JSON 다운로드 백업 (안전망)

## 공통 데이터 모델 (SKILL.md §"공통 데이터 모델" 참조)

- `Session` (전체 컨테이너)
- `PhotoRecord` (사진)
- `ApartmentRecord` (아파트 단지)
- `FacilityRecord` (시설)
- `NewsItem` (호재 뉴스)
- `ReviewRecord` (후기, localStorage에 저장)
- `NeighborhoodReview` (동네 총평, 선택)

## v2 → v3 마이그레이션 (중요)

v3의 핵심 변화:

| 항목 | v2 | v3 |
|------|----|----|
| **아파트 좌표 소스** | Nominatim (7/29 high) + centroid + fallback | **VWorld API** (27/28 high, 1 fallback) |
| **photoIcon 상태** | 0/N 또는 M>0 (2-state) | **0/N → M/N → N/N (3-state, 마커 색: 주황/노랑/초록)** |
| **후기 데이터** | `{id: "text"}` | **`{id: {text, tags}}` + 마이그레이션 함수** |
| **태그 시스템** | 없음 | **후기/아파트/뉴스/사용자마크 모두 태그** |
| **드롭박스 기본값** | 모두 열림 | **apt/news 닫힘, review 열림** |
| **태그 필터** | 없음 | **Streak(전체/후기있음/후기없음/태그) + apt(전체/태그) + news(태그)** |
| **거래가격 기준** | 없음 | **latest_deal_date + data_as_of 카드/팝업 표기** |
| **사진 마커 클릭** | popup만 (사진 6장 미리보기) | **클릭 → 클러스터 전체 모달 (큰 사진 + 후기 + 태그 + 진행률)** |
| **Streak 사진** | 헤더 전체가 클릭 | **사진(dblclick → 큰 모달) + 옆 공백(click → 인라인 후기) 분리** |
| **마커 자동 갱신** | `location.reload()` | **`refreshMarkerIcons()` (저장/삭제 시 즉시 M/N 반영)** |
| **MD 추출** | 없음 | **base64 사진 임베드 → Notion 업로드 가능** |
| **결정론/비결정론** | 없음 | **결정론 = Python 스크립트, 비결정론 = AI** (위 §"결정론 vs 비결정론") |
| **v2 → v3 자동 마이그레이션** | - | **localStorage 키: `anyang_imjang_v2_data` → `v3_data` + `migrateReviews()`** |

**v2 → v3 호환**:
- 옛 v2 localStorage 키 `anyang_imjang_v2_data`는 그대로 두면 됨. v3 빌드 시 `loadStorage()`가 마이그레이션
- 옛 v2 v1-build_report.py 코드는 더 이상 사용 안 함. 새 `scripts/build_report.py` 사용

---

## v1 → v2 마이그레이션 (중요)

이전 `real-estate-site-visit` v1 (Notion DB 중심)은 **deprecated**. 흔한 혼동 시나리오:

| 항목 | v1 (구버전, deprecated) | v2 | **v3 (현재)** |
|------|-------------------------|-----|------------------|
| 산출물 | Notion DB 행 | 단일 HTML (`report.html`) | 단일 HTML (`report.html`) + MD 추출 |
| 데이터 흐름 | 사진 → GPS 클러스터 → Notion row | 사진 → GPS 클러스터 → session.json → HTML | + VWorld 좌표 + 후기 태그 + 동네총평 |
| 아파트 정보 | 사용자 수동 입력 | MOLIT 실거래가 API (proxy) 자동 조회 | + VWorld 검색으로 단지 정밀 좌표 |
| 호재 정보 | 없음 | Naver News 검색 + ⭐ 마커 | + 태그 필터 + 사용자 추가 |
| 후기 | Notion | IndexedDB/localStorage + 다운로드 | + **태그 + 인라인 edit + 진행률 M/N + 오버레이 갈무리** |
| 동선/주변 | 단순 메모 | 뉴스/시설 | + Streak (시간순 사진) + 한줄평 |
| 후기 갈무리 | 없음 | setTimeout/popup 순차 | **popup 금지, `#capture-overlay` 말풍선 DOM 배치** |
| MD 추출 | 없음 | 없음 | **동선 인덱스 제거 + 절대 file URL fallback + 가능 시 base64** |

**v1 호출 신호** (이 키워드가 들어오면 v1 워크플로우 추측하지 말 것):
- "임장 DB 만들어줘" / "노션에 정리해줘" → v2에서도 session.json + HTML 형태로 제공 (Notion은 별도 요청 시)
- "부동산 지역분석 자료 PDF 정리" → PDF 파싱 후 v2 HTML에 통합

## 공통 Pitfalls
## 공통 Pitfalls
- **GPS 없는 사진**: 스크린샷/카톡 이미지 등은 GPS 없음 → 목록에서 제외하고 사용자에게 알림
- **Nominatim rate limit**: `time.sleep(1.1)` 필수 (안 넣으면 429)
- **역지오코딩 정확도**: 도로명/상호명이 나오는 경우 많음 → 사용자가 단지명/장소명 수동 보정
- **Leaflet HTML은 file://로 단독 실행 가능해야 함**: 외부 의존은 CDN만, 사진은 상대경로로 복사
- **후기 영구 보존**: IndexedDB는 브라우저 데이터 삭제 시 유실 가능 → session.json 다운로드 정기 권장
- **부동산 크롤링 ToS**: 상세 수치 못 가져오면 외부 링크만 제공 (네이버부동산/카카오맵)
- **v1 Notion DB 스킬과 혼동 금지**: 옛 `real-estate-site-visit` v1 (Notion DB 중심)은 deprecated. 본 스킬 v2는 인터랙티브 웹페이지 중심. 사용자가 "노션에" 명시 요청 시에만 Notion 워크플로우 분기
- **사용자 캡처 vs GPS**: GPS 우선. 캡처는 누락/보정용
- **MOLIT 1건 표본 함정**: 거래 1건만으로 대장 아파트 선정 ❌ → 표본 ≥3 또는 가격+신축성+거래량 종합 점수 (references/daejang_scoring.md 참조)
- **data.go.kr 직접 교차검증 요청 시**: 사용자가 “MOLIT 기준이 아니라 사용자 키로 국토교통부 아파트매매 실거래가 API를 직접 호출했는지”를 확인하면, 같은 `lawd_cd`/`deal_ymd` 조건으로 `RTMSDataSvcAptTrade/getRTMSDataSvcAptTrade`를 직접 호출해 건수와 endpoint를 먼저 검증한다. 이후 가격 미조회/매칭 실패 표기는 `MOLIT 기준 실거래가 조회되지 않음`처럼 축약하지 말고 **`국토교통부 아파트매매 실거래가 API로 조회되지 않음`**으로 쓴다.
- **WSL outbound `apis.data.go.kr` 차단**: 현 WSL 환경에서 `www.data.go.kr`는 열리지만 `apis.data.go.kr` (OpenAPI 서브도메인)은 400/401로 차단될 수 있음. **Fix**: 먼저 `scripts/fetch_molit.py --source direct`로 실제 현재 상태를 확인하고, 직접 호출이 막힐 때만 k-skill-proxy 경유 또는 Windows 측 PowerShell/브라우저 호출 후 결과 JSON 복사를 사용한다.
- **kakaoLocal at k-skill-proxy endpoint 미노출**: health에 `kakaoLocalConfigured: true`로 표시되지만 `/v1/kakao/local/search` 등의 endpoint가 노출 안 됨 (Google GFE 400 반환). **Fix**: 단지 좌표는 행정동(법정동) GPS 클러스터 centroid로 fallback하고, 단지명 검색 링크(네이버부동산/카카오맵) 제공. ApartmentRecord에 `coord_source` 필드로 좌표 출처 명시 (예: `"비산1동 GPS centroid (n=15)"`)
- **Kakao POI 부속시설 혼입**: `부동산 > 주거시설 > 아파트` 카테고리에도 `커뮤니티센터`, `관리사무소`, `경로당`, `어린이집`, `주차장`, 개별 `103동`/`B동` 같은 POI가 섞일 수 있다. **Fix**: `collect_apartments_near_route.py::is_apartment_doc()`에서 부속시설/동별 명칭을 제외하고, 배포 전 회귀 테스트에 대표 케이스를 넣는다.
- **네이버부동산 팝업 링크 회귀**: `new.land.naver.com/search`의 `ms=lat,lng,zoom`을 고정값으로 두면 모든 아파트가 같은 위치로 열려 거래내역 확인 UX가 깨진다. **Fix**: `naver_link(name, lat, lng)`는 단지별 좌표와 zoom 17을 넣고, `build_report_v3.py`도 기존 `session.json`에 낡은 고정 링크가 있어도 `naverLandLinkForApt(a)`로 런타임 재생성한다. 버튼 라벨은 `네이버부동산`으로 명확히 둔다.
- **단일 HTML 생성 시 f-string + JS 충돌**: `report.html` 빌드 스크립트에서 Python f-string + JS/CSS의 `{}` 충돌 → syntax error. **Fix**: 일반 string + `str.replace('PLACEHOLDER', value)` 패턴 사용 (자세한 템플릿은 `scripts/build_report.py` 참조)
- **Python urllib 한글 인코딩**: stdout이 ASCII로 잡힌 WSL 환경에서 `urllib.parse.quote()`로 한글 query를 escape해도 `'ascii' codec can't encode...` 오류. **Fix**: `quote(query, safe='')` 결과는 raw URL에 직접 넣어야 함. 또는 `requests` 사용
- **VWorld key의 `request` 파라미터 누락**: v1 endpoint (`/req/search` without `request=search`)는 "필수 파라미터인 request가 없어서..." 에러. **Fix**: 항상 `?request=search&key=...`로 호출
- **Notion 이미지 임포트**: `<img src="data:...">` 또는 MD 단독 파일은 Notion에서 이미지가 무시/누락될 수 있다. **Fix**: 기본은 `imjang_report.md + images/` 상대경로 ZIP Import. 브라우저 `file://` fetch가 막히면 `assets/photos` 폴더 선택 fallback 또는 `scripts/export_notion_md_zip.py` 사용.
- **갈무리 silently 죽음 (candidates forEach 바깥 정의)**: `const candidates = [{ labelX: pt.x + ... }]` 처럼 forEach 바깥에서 정의하면 `pt` 미정의 → ReferenceError → overlay에 아무것도 안 그려짐. **Fix**: candidates를 forEach 안에서 매 entry마다 pt 기반으로 새로 생성. **반드시 try/catch + 콘솔 에러 표시** (사용자 디버깅 위해)
- **갈무리 mock 테스트 tagName**: Node.js에서 `createElement('div')` → element.tagName='div' (소문자). 브라우저는 항상 대문자 'DIV' 반환. **Fix**: mock은 `.toUpperCase()` 적용
- **3-state 마커 즉시 갱신**: 후기 작성/삭제 시 `location.reload()` ❌ → `marker.setIcon(photoIcon(reviewedCount, totalCount))` 즉시 갱신. `refreshMarkerIcons()` 함수로 일괄 처리
- **v2→v3 storage 자동 마이그레이션**: v2 키 `anyang_imjang_v2_data` (string reviews) → v3 키 `anyang_imjang_v3_data` ({text, tags} reviews). `loadStorage()`에서 v2 키 자동 감지 + `migrateReviews()` + v2 키 삭제
- **VWorld 단지 boundary 좌표 ≠ 단지 정문**: VWorld "시설구역경계 > 아파트단지" 카테고리는 polygon boundary point 1~3개의 평균. 단지 polygon의 "중앙"이 아니라 polygon 중심. **Fix**: 보정 필요 시 "📍 마크 추가"로 사용자 보정
- **VWorld 단지 미등록 (2021 신축)**: 안양광신프로그레스리버뷰처럼 VWorld에 등록 안 된 신축은 `coord_confidence: failed`. **Fix**: 가장 인접 단지(같은 법정동, 비슷한 시기) 좌표 임시 사용 + `coord_confidence: low-sibling` + source에 "VWorld 단지 미등록" 명시
- **VWorld 단지 polygon 부속시설 fallback**: VWorld에 단지 polygon은 없지만 단지내 공인중개사/충전소 좌표로 잡힌 경우. 좌표 자체는 정상 단지 위치지만 정확도 낮음. **Fix**: `coord_confidence: low` + source에 "단지 polygon 미등록, 부속시설 기준"

v3 빌드 직후 사용자가 추가로 요청한 기능들. **v4 빌드 시 기본 포함**되어야 함:

| # | 기능 | 구현 위치 | 비고 |
|---|------|----------|------|
| 23 | **Notion ZIP 생성** | 툴바 "📦 Notion ZIP 생성" 버튼 | `imjang_report.md + images/`를 ZIP으로 묶어 다운로드. 생성되는 MD/Notion용 md의 첫 섹션은 항상 `## 🏘️ 동네 총평`이며, 사용자가 아직 적지 않아도 한줄평/분위기/상권/교통/도보/5년후 전망 공란 템플릿을 유지한다. 기본은 MD 추출과 동일하게 **실제 후기 문구가 입력된 사진만** 포함한다. 태그만 있는 사진은 후기 작성으로 간주하지 않는다. 사용자가 원하면 `전체 사진 포함` 체크. Notion `Settings → Import → Text & Markdown`으로 ZIP을 업로드하면 상대경로 이미지가 함께 임포트된다. file:// fetch가 막히면 폴더 선택창에서 **ZIP 저장 위치가 아니라 원본 임장 사진 폴더**를 선택하게 안내한다. 2차 선택창이 뜨면 추출 대상 위치로 같은 원본 사진 폴더를 다시 선택하면 된다고 설명한다. 세부 UX/검증 케이스: `references/notion-md-zip-review-selection.md`. |
| 24 | **사진 마커 0/M/N 3-state** | `photoIcon(reviewedCount, totalCount)` | 0=주황 `#ff6b35` + 숫자, 0<M<N=노랑 `#f9a825` + "M/N", N=초록 `#2e7d32` + "✓N". 후기 변경 시 `refreshMarkerIcons()`로 즉시 갱신 (reload ❌) |
| 25 | **사진 마커 클릭 → 클러스터 전체 모달** | `marker.on('click', openClusterModal)` | 작은 popup(사진 3장 미리보기) + 마커 클릭 시 큰 모달 (모든 사진 + 인라인 후기 + 태그 + 진행률 M/N) |
| 26 | **Streak 사진/공백 영역 분리** | `.photo-thumb` vs `.info-area` | 사진 자체는 dblclick → 큰 모달 (openPhotoModal), 옆 공백(.info-area) click → 인라인 후기 (toggleStreakEdit). 점선 테두리 hover hint |
| 27 | **갈무리 SVG 직각 화살표** | `<svg>` + `<path>` + `<polygon>` | 점선 ❌, 실선 ✅ (stroke 2.5px, 진한 초록 #1b5e20). 대각선 ❌, L자 직각 ✅. 8방위 후보(TR/TL/BR/BL/R/L/T/B) + screen pixel 기준 greedy 배치 |
| 28 | **갈무리 마커/라벨 anchor** | `<circle>` + `<rect>` | 마커 anchor = 큰 원(r=6, #1b5e20 fill + #fff stroke 2px) + 내부 흰색 dot. 라벨 anchor = 흰 사각(5x5, #1b5e20 stroke 2.5px) + 중앙 dot. **시작/끝이 명확** |
| 29 | **갈무리 rAF throttle + 지도 이동/줌 따라가기** | `map.on('move', 'zoom')` + rAF | `updateCaptureOverlayOnMove`가 rAF로 throttled. 한 프레임에 1번만 render. enableCaptureTracking() / disableCaptureTracking() 으로 갈무리 on/off 시 토글 |
| 30 | **갈무리 try/catch + 콘솔 에러** | `renderCaptureOverlay()` | `_renderCaptureOverlayInner()`로 분리하고 try/catch. 에러 시 overlay에 "⚠️ 갈무리 오류: <msg>" + 콘솔 stack trace. 디버깅이 즉시 가능 |
| 31 | **v1/v2 storage 자동 마이그레이션** | `loadStorage()` | `anyang_imjang_data` (v1) + `anyang_imjang_v2_data` (v2) → `anyang_imjang_v3_data` 자동 변환. v1/v2 키 자동 삭제. 콘솔에 "✓ v1/v2 → v3 마이그레이션 완료" |
| 32 | **renderCaptureOverlay 단위 테스트 가능** (Node.js) | 함수 추출 패턴 | `<svg>` 등 Leaflet 의존 없이 DOM mock 만들면 Node에서 단위 테스트 가능. tagName 대소문자 주의 (createElement는 대문자 반환) |
| 33 | **3-state 아파트 마커 (0/1, 1/1)** | `aptIcon(isDaejang, hasReview, reviewedCount, totalCount)` | 후기 0=파랑, 1=초록. 대장 = ⭐. **마커 ID = `aptMarkers[id]` 객체 직접 매핑** (배열 인덱스 ❌) |

**Notion ZIP Import 패턴 (자주 잊는 함정)**:
- MD 단독 업로드는 로컬 이미지가 깨질 수 있다. 반드시 `imjang_report.md`와 `images/` 폴더를 같은 ZIP에 넣고, MD 이미지는 `![사진](images/001_x.jpg)` 상대경로로 쓴다.
- `file://` HTML에서 `fetch('assets/photos/...')`가 브라우저 보안 정책으로 실패할 수 있다. 이 경우 `showDirectoryPicker()`로 사용자가 `assets/photos` 폴더를 직접 선택하게 하거나, Hermes/로컬 Python 스크립트 `export_notion_md_zip.py`를 사용한다.
- Notion Import는 고해상도 사진/큰 ZIP에서 실패할 수 있다. 안정 경로는 Python 스크립트에서 1600px 내외로 리사이즈/압축한 ZIP을 만드는 것.

**갈무리 bugs 흔한 함정 (v3.1에서 잡힌 것들)**:
- `candidates` 정의를 `entries.forEach` **바깥**에 하면 `pt` 미정의 → ReferenceError. forEach 안으로
- `candidates`는 매 entry마다 `pt` 기반으로 새로 만들어야 함 (이전 entry의 pt를 재사용 ❌)
- Node mock 테스트 시 `createElement('div')` → tagName='div' (소문자)지만 filter는 'DIV' (대문자). 브라우저는 element.tagName 항상 대문자 반환 — mock도 `.toUpperCase()` 적용
- 갈무리 pop 없이 try/catch 없으면 silently 죽음 → overlay에 아무것도 안 그려짐. **반드시 try/catch**

**v3.1 패턴 코드 (갈무리 SVG 직각 화살표)**:
```js
// 8방위 후보 (각 entry마다 pt 기반 생성)
const candidates = [
  { name: 'TR', anchorSide: 'left-bottom', route: 'L', ... },
  { name: 'TL', anchorSide: 'right-bottom', route: 'L', ... },
  // ... 8개 (4 모서리 + 4 축)
];
entries.forEach(function(e, idx) {
  const pt = map.latLngToContainerPoint([e.lat, e.lng]);
  if (pt.x < -100 || pt.x > w + 100 || pt.y < -100 || pt.y > h + 100) return;  // 화면 밖 스킵
  // best 후보 선택 (overlap*100000 + dist + idx)
  // L자 path (M pt L anchor.x pt.y L anchor.x anchor.y) — 수평/수직만
});
```

상세 코드: `references/v3_feedback_patterns.md`

## 결정론 vs 비결정론 분리 (사용자 명시 요구)

**사용자 피드백**: "스킬 수행 중 결정론적/비결정론적 부분을 나누어 AI 사용없이 순수 반복작업은 파이썬 과정으로 대체하여 토큰 사용절감"

워크플로우를 다음 2개 영역으로 명확히 분리:

### 결정론 (Python 스크립트, scripts/ 디렉토리)
매번 같은 결과를 보장하는 반복 작업. AI 호출 없이 직접 실행:
- `scripts/extract_photo_gps.py` — 사진 EXIF → lat/lng/timestamp
- `scripts/cluster_photos.py` — GPS 클러스터링 + 역지오코딩
- `scripts/geocode_vworld.py` — 아파트 단지 정밀 좌표 (VWorld API)
- `scripts/score_apartments.py` — 대장 아파트 스코어링 (TODO)
- `scripts/filter_news.py` — 호재/뉴스 필터링 (TODO)
- `scripts/build_report.py` — 단일 HTML 빌드 (v3 템플릿)

**사용 패턴**: agent가 각 단계를 Python 스크립트 호출로 실행 → session.json 입출력. AI는 중간 결과 확인/판단만.

### 비결정론 (AI)
판단, 추론, 사용자 대화, 디자인 결정:
- 동선 우선순위 판단 (GPS vs 캡처)
- 사용자 의도 해석 (어느 동네에 집중?)
- LLM이 답해야 하는 호재 태그 분류 (뉴스 요약, 자동 태깅)
- "이 단지가 왜 추천인지" 자연어 설명

### 실전 워크플로우 (v3)
```
1. AI: "임장 사진 어디?" / "동선 캡처 있어요?" → 사용자 응답
2. 결정론 (Python): extract_photo_gps.py → session.json photos[]
3. AI: GPS 분포 확인 → 클러스터링 반경 제안
4. 결정론 (Python): cluster_photos.py → session.json neighborhoods[]
5. AI: 동선 시각화 → 사용자 컨펌
6. 결정론 (Python): geocode_vworld.py → session.json apartments[] lat/lng
7. AI: 뉴스 검색 + 태깅 → 비결정론 영역
8. 결정론 (Python): build_report.py → report.html
9. 결정론 (JS, 클라이언트): MD 추출 (base64 임베드) — 브라우저에서 실행
```

이 분리로 **토큰 사용량 50%+ 절감** (안양 임장 기준 약 1만 → 4천).

## v3 UI 패턴 (사용자 12개 피드백에서 추출)

v2 → v3 반영 시 v2에 누락되어 사용자가 12개 일괄 피드백을 준 패턴. **누락 시 재작업 요청 받음**:

1. **Streak inline edit (좌측 240px)**: 사진 헤더 클릭 → 인라인 textarea 펼침. **사진 영역과 정보 영역 분리** (`.photo-thumb` vs `.info-area`, 더블클릭=큰 모달, 클릭=후기 작성)
2. **Streak M/N 진행률**: 클러스터 헤더에 "M/N" 형식. 색상 3-state (0=주황, M/N=노랑 #f9a825, N/N=초록 #2e7d32)
3. **사진 아이콘 → 클러스터 모달**: 작은 popup (사진 3장 미리보기) + 마커 클릭 시 큰 모달 (모든 사진 + 인라인 후기 작성/태그/삭제)
4. **아파트 카드↔마커 ID 매핑**: `aptMarkers[id]` 객체 직접 매핑 (배열 인덱스 ❌). 클릭 시 `marker.getLatLng()`로 setView
5. **밝은 지도 타일**: CartoDB Voyager (OSM 기본은 진함)
6. **동선 버퍼 300m 내 모든 단지**: 13개 → 26개로 확장, 동네별 top 1을 대장
7. **큰 사진 모달**: max-width 900px, max-height 70vh. 사진 + 후기 영역 + 작성 버튼
8. **드롭다운 패널**: 아파트/뉴스 기본 닫힘, 동네총평만 열림. 헤더 클릭 시 ▼ 회전 + panel-body 토글
9. **뉴스 자동 필터링**: 맛슐랭/안전점검/콘크리트/정체극심/치과/동물병원/이전 키워드 제외. 호재/재개발/GTX/분양/시세만 유지
10. **사용자 뉴스 추가**: ➕ 버튼 + 모달 (제목/URL/요약) → localStorage `user_news`
11. **사용자 커스텀 마크**: 📍 마크 추가 → 지도 클릭 → 모달 (이름/타입 8가지/메모). 타입: 📍🏪🍽️🏫🌳🚇🏢⚠️
12. **동네 한줄평 (NeighborhoodReview)**: 전체 한줄 + 5개 항목 (분위기/상권/교통/도보/5년후). 진행률 0/6~6/6
13. **MD 추출 (Notion 업로드)**: 후기/태그 있는 사진만 base64 임베드 → Notion에 drag&drop
14. **거래가격 기준일자**: `latest_deal_date` + `data_as_of` 필드. 카드/팝업에 "📅 기준: 2026-05-29 (data: 2026-05-31)" 표시
15. **후기 태그**: 모달/Streak/클러스터 모두에서 태그 추가. 아파트 카드/팝업에 #태그 표시. Streak/아파트/뉴스 각각 select 필터

**v2 필수 외 추가 피드백 (v3 후)**:
- **후기 갈무리 동시 말풍선 (지도 이동/줌 따라감)**: `map.on('move', 'zoom')` → rAF throttle로 `renderCaptureOverlay` 재호출. **마커 ↔ 말풍선 화살표** SVG `<line>` + `<polygon>` 으로 정확한 화살표 머리. 화면 밖 마커는 자동 스킵
- **사진 마커 0/M/N 색상**: 0=주황, M/N=노랑, N/N=초록. 후기 변경 시 `marker.setIcon()` 즉시 갱신 (location.reload ❌)
- **3-state 아파트 마커**: 후기 0/1, 1/1 (대장 표시 유지)

전체 코드 패턴: `references/v2_feedback_patterns.md` 참조

## VWorld API (아파트 정밀 좌표 무료 조회)

**왜 VWorld?**: Nominatim(OSM)은 한국 신축 아파트 단지명이 DB에 없어서 24%만 매칭 (7/29). VWorld는 행정안전부 운영 + "시설구역경계 > 아파트단지" 카테고리 + "건물 > 주거용공동주택" 동별 entry → **97% 매칭 (28/29)**

### 키 발급
1. https://www.data.go.kr/data/15000273/openapi.do 활용 신청
2. 1~2시간 자동 승인 → 마이페이지 > 인증키(Encoding)
3. env 저장: `export VWORLD_KEY=28056A4E-...` 또는 `~/.config/k-skill/secrets.env`

### 호출
```bash
# v2 endpoint (request=search 필수)
curl "https://api.vworld.kr/req/search?request=search&key=${VWORLD_KEY}&query=평촌더샵센트럴시티&type=place&format=json"
# → response.result.items[] 안에 {title, category, point{x,y}}
#   category 예: "시설구역경계 > 아파트단지" / "건물 > 주거용공동주택"
```

### 응답 처리 우선순위 (scripts/geocode_vworld.py)
1. "시설구역경계 > 아파트단지" — polygon boundary, **가장 정확**
2. "건물 > 주거용공동주택" 또는 "제1종근린생활시설" — 동별 평균
3. 기타 카테고리 (medium)
4. NOT_FOUND → 기존 좌표 유지

### WSL outbound 상태
- `api.vworld.kr` → **정상** (테스트 완료, 28/29 매칭)
- `apis.data.go.kr` → **차단** (WSL firewall, apis 서브도메인만)
- `www.data.go.kr` → 정상

### 결과: 안양 임장 적용
- 26개 아파트 단지: 23 high (VWorld 시설구역경계 + 건물 평균) + 2 medium + 1 failed (안양광신 = 신축 미등록)
- coord_source 예: `"VWorld 시설구역경계 1개 평균"` / `"VWorld 건물 26개 평균"`
- **VWorld API가 한국 아파트 단지 정밀도 최상 (핵심 발견)**: Nominatim은 한국 신축 단지명 매칭 약함 (29개 중 7개), kakaoLocal endpoint는 k-skill-proxy에서 미노출, Kakao Map 검색 HTML은 302 redirect로 직접 파싱 불가. **VWorld 검색 API**는 단지명 + "아파트" 조합으로 **시설구역경계 > 아파트단지 / 건물 > 주거용공동주택** 카테고리 결과를 정확히 반환 (29개 중 28개 정밀 조회). 발급: data.go.kr > "공간정보 오픈플랫폼(VWorld) - 검색" 활용 신청 > 1~2시간 자동 승인 > Encoding 키. 자세한 사용법은 `references/v3_vworld_geocoding.md` 참조
- **VWorld "시설구역경계 > 아파트단지" 좌표는 polygon boundary**: polygon point 1~3개의 평균이라 단지 polygon의 "중앙"이 아니라 polygon 중심. 동별 평균도 비슷. 실제 단지 정문/주출입구와 다를 수 있음 → 보정 필요 시 "📍 마크 추가"로 사용자 보정
- **결정론 vs 비결정론 분리 (토큰 절감)**: 사진 클러스터링·Nominatim/VWorld 조회·HTML 빌드·MD 추출은 **순수 반복 작업** → Python 스크립트로 (`scripts/build_report.py`, `scripts/vworld_query.py`). LLM은 **동선 의미 분석·대장 아파트 선정 기준 결정·사용자 의도 파악**만 처리. 반복 작업에 LLM 토큰 쓰지 말 것
- **후기 갈무리 popup 금지**: `m.openPopup()` 다중 호출은 Leaflet autoClose/브라우저 상태 때문에 마지막 1개만 남을 수 있다. `#capture-overlay`에 말풍선 DOM을 직접 만들고, 사진은 넣지 않으며, screen pixel 기준 후보 위치 greedy 배치로 겹침을 줄인다.
- **v2→v3 reviews 스키마 변경**: `reviews[id] = string` → `reviews[id] = {text, tags[]}`. 사용자 로컬스토리지 v2 데이터 손실 방지를 위해 loadStorage()에서 migrateReviews() 자동 변환 필수
- **MD 추출 사진 경로**: `assets/photos/...` 상대경로만 쓰면 다운로드된 MD 위치 기준으로 깨진다. `new URL('assets/photos/'+filename, window.location.href).href`로 HTML 기준 절대 `file://` URL을 fallback으로 쓰고, `fetch()`가 성공할 때만 base64 data URL로 대체한다. fetch 실패 시 상대경로 fallback 금지.
- **사진 클러스터 진행률 표기**: N장 중 M장에 후기 있으면 "M/N" badge. 헤더 인라인 텍스트로만 (별도 badge 컴포넌트 ❌) — 사용자가 "별표 보다는 M/N이 낫다" 명시
- **드롭박스 default state**: apt/news = collapsed, review = open. 처음 페이지 열었을 때 사용자 의도 (대부분 처음엔 지도부터 봄)

- **후기 갈무리 오버레이**: Leaflet popup 여러 개 동시 open에 의존하지 말 것. Leaflet popup은 기본 autoClose 때문에 마지막 1개만 남는 브라우저/상태가 있다. 갈무리는 `#capture-overlay` 같은 절대위치 오버레이에 사진 없는 말풍선 DOM을 직접 올리고, 지도 전체 동선 `fitBounds` 후 screen pixel 기준 greedy 후보 배치로 최대한 겹치지 않게 둔다.
- **작은 창 Streak 안내**: 화면 폭 때문에 `#streak`를 숨길 경우 조용히 사라지게 하지 말고 상단에 “현재 창 너비에서는 Streak 패널이 숨겨집니다. 창을 최대화하거나 배율을 낮추세요” 안내를 표시한다.
- **MD 추출 사진 경로**: `assets/photos/foo.jpg` 상대경로만 쓰면 다운로드된 MD 위치 기준으로 깨진다. `new URL('assets/photos/'+filename, window.location.href).href`로 HTML 기준 절대 file URL을 fallback으로 넣고, `fetch()` 성공 시에만 base64 data URL로 대체한다. `file://`에서 fetch가 막힐 수 있으므로 fallback은 필수다.
- **MD 동선 섹션 제거**: `SESSION.neighborhoods`가 이름 없는 “지점 1~14” 수준이면 Notion용 MD에서는 과감히 제외한다. 목적은 복기 가능한 후기/사진/단지/뉴스 정리이지 무의미한 인덱스 나열이 아니다.

---

## 데이터 소스: MOLIT 실거래가 (k-skill-proxy 경유)

**부동산 사이트(네이버부동산/호갱노노/직방/아실)는 자체 API를 제공하지 않으며, 모두 국토교통부(MOLIT) 실거래가 OpenAPI를 데이터 소스로 사용한다.** 본 스킬은 이 데이터를 k-skill-proxy 경유로 조회한다.

### 1. k-skill-proxy URL/상태 확인

```bash
curl -fsS "${KSKILL_PROXY_BASE_URL:-https://k-skill-proxy.nomadamas.org}/health"
```

`upstreams.molitConfigured: true` 인지 확인. false면 proxy 운영자한테 키 주입 요청.

다른 사용 가능한 upstream (proxy에 모두 사전 설정됨):
- `kakaoLocalConfigured: true` — Kakao Local API (역지오코딩, 키워드 검색)
- `kakaoMapConfigured: true` — Kakao Map
- `naverNewsApiConfigured: true` — Naver News (호재 검색)
- `naverSearchApiConfigured: true` — Naver 검색
- `krxConfigured: true` — KRX (주식/지수)

### 2. 법정동 코드 조회 (시/구/동 → 5자리 코드)

```bash
curl -fsS --get "${KSKILL_PROXY_BASE_URL}/v1/real-estate/region-code" \
  --data-urlencode 'q=안양시 동안구'
# → {"results":[{"lawd_cd":"41173","name":"경기도 안양시 동안구"}], ...}
```

**확정된 법정동 코드 (안양 임장용, 2026-06-13)**:
- 경기도 안양시 만안구: `41171`
- 경기도 안양시 동안구: `41173`
- 경기도 안양시: `41170` (시 단위)

다른 광역시/도 코드: `region-code` endpoint로 조회 (캐시 hit 많음).

### 3. 아파트 매매/전세 실거래가 조회

```bash
# 매매 (최근 1개월)
curl -fsS --get "${KSKILL_PROXY_BASE_URL}/v1/real-estate/apartment/trade" \
  --data-urlencode 'lawd_cd=41173' \
  --data-urlencode 'deal_ymd=202605'

# 전세/월세
curl -fsS --get "${KSKILL_PROXY_BASE_URL}/v1/real-estate/apartment/rent" \
  --data-urlencode 'lawd_cd=41173' \
  --data-urlencode 'deal_ymd=202605'
```

**지원 자산 타입**: `apartment`, `officetel`, `villa`, `single-house`, `commercial`
**지원 거래 타입**: `trade`(매매), `rent`(전월세). `commercial/rent` 미지원.

### 4. 응답 스키마 (요약)

```json
{
  "items": [
    {
      "name": "래미안 퍼스티지",
      "district": "반포동",
      "area_m2": 84.99,
      "floor": 12,
      "price_10k": 245000,    // 만원 단위
      "deal_date": "2024-03-15",
      "build_year": 2009,
      "deal_type": "중개거래"
    }
  ],
  "summary": {
    "median_price_10k": 230000,
    "min_price_10k": 180000,
    "max_price_10k": 310000,
    "sample_count": 42
  }
}
```

전세/월세는 `price_10k` 대신 `deposit_10k`, `monthly_rent_10k`, `contract_type`.

### 5. 단지 기본정보(세대수/준공연도)는 별도

MOLIT 실거래가 API는 **가격 + 기본 메타**(면적/층/준공연도)만 제공. **단지명/주소/좌표/총 세대수/총 동수** 같은 단지 차원의 정보는 포함 안 됨. 이 정보는:

- ✅ Kakao Local API (k-skill-proxy `kakaoLocalConfigured`) — 키워드/좌표로 장소 검색
- ❌ 네이버부동산 `complexes/search` (비공식, ToS 회색) — 광진구 때 사용 전적 있음
- ❌ 호갱노노 (API 없음, 크롤링 직접)

**권장**: kakaoLocal로 단지 검색 → coordinates 확보 + kakaoMap link 생성. 단지 메타가 비면 SKILL_02 §3.3 정석대로 외부 링크만 노출하고 상세 칸 비움.

### 6. 데이터 없거나 프록시 미설정인 사용자용 가이드

**MOLIT API 키가 없는 경우**:

1. https://www.data.go.kr 회원가입
2. **"국토교통부_아파트 매매 실거래가 자료"** 검색 → 활용 신청
   - 직접 링크: https://www.data.go.kr/data/15126469/openapi.do
3. 1~2시간 내 자동 승인 → 마이페이지 > 개발계정/일반계정에서 **인증키(Encoding)** 확인
4. 그 키를 k-skill-proxy 운영자한테 전달 → upstream에 주입
5. 또는 직접 호출 (proxy 없이, 아래 §6.1 참조)

**k-skill-proxy 자체가 없는 경우** (다른 사용자/신규 환경):
- proxy 운영자 연락 (현재 `nomadamas.org` 호스팅)
- 또는 §6.1 직접 호출로 진행

#### 6.1 data.go.kr 직접 호출 (k-skill-proxy 우회)

**MOLIT 아파트 매매 실거래 원본 endpoint** (data.go.kr/data/15126469):

```bash
# 1) data.go.kr에서 발급한 인증키로 호출 (URL-encoded)
curl -fsS --get "https://apis.data.go.kr/1613000/RTMSDataSvcAptTrade/getRTMSDataSvcAptTrade" \
  --data-urlencode "serviceKey=<YOUR_DATA_GO_KR_KEY>" \
  --data-urlencode "LAWD_CD=41173" \
  --data-urlencode "DEAL_YMD=202605" \
  --data-urlencode "pageNo=1" \
  --data-urlencode "numOfRows=100"
```

응답은 XML 기본, `&type=json` 추가하면 JSON:

```bash
curl -fsS --get "https://apis.data.go.kr/1613000/RTMSDataSvcAptTrade/getRTMSDataSvcAptTrade" \
  --data-urlencode "serviceKey=<KEY>" \
  --data-urlencode "LAWD_CD=41173" \
  --data-urlencode "DEAL_YMD=202605" \
  --data-urlencode "type=json"
```

**전월세 endpoint** (별도):

```bash
curl -fsS --get "https://apis.data.go.kr/1613000/RTMSDataSvcAptRent/getRTMSDataSvcAptRent" \
  --data-urlencode "serviceKey=<KEY>" \
  --data-urlencode "LAWD_CD=41173" \
  --data-urlencode "DEAL_YMD=202605" \
  --data-urlencode "type=json"
```

**오피스텔/연립다세대/단독주택** endpoint는 `/RTMSDataSvcOffiTrade/`, `/RTMSDataSvcRHTrade/`, `/RTMSDataSvcSHTrade/` 패턴.

**XML 응답 구조 (변환 필요)**:
- `<items>` 안에 `<item>` 요소들
- 필드명: `aptNm`(단지명), `umdNm`(법정동), `dealAmount`(거래가, 만원), `buildYear`, `floor`, `excluUseAr`(전용면적)
- k-skill-proxy 응답 (JSON camelCase + summary)과 다름 → 파싱 어댑터 필요

**인증키 종류**:
- **Encoding 키**: URL에 그대로 넣어도 되는 형태 (운영 권장)
- **Decoding 키**: XML/JSON 응답 검증용, URL에 넣으면 invalid
- 둘 다 마이페이지에서 확인 가능

**rate limit**: 일 1000회 정도 (MOLIT 원본 기준). 인증키별로 카운트. 큰 작업 시 5분 캐시 권장.

**에러**:
- `SERVICE_KEY_IS_NOT_REGISTERED_ERROR` — 키 미등록/오타
- `LIMITED_NUMBER_OF_SERVICE_REQUESTS_EXCEEDS_ERROR` — 일 한도 초과 (다음날 리셋)
- `NO_MANDATORY_REQUEST_PARAMETERS_ERROR` — LAWD_CD/DEAL_YMD 빠짐
- 인증키 끝에 `%3D` (`=`) 가 들어가는 Decoding 키 URL 사용 시 401

#### 6.2 임장 워크플로우에서 우선순위

```
1순위: k-skill-proxy 경유 (proxy만 동작하면 OK, 인증키 노출 없음)
2순위: data.go.kr 직접 호출 (사용자 키가 .env에 있으면)
3순위: 사전 PDF / 사전자료에서 추출 (광진구 때처럼)
4순위: 크롤링/외부 링크만 (상세 수치 비움, SKILL_02 §3.3 정석)
```

### 7. 임장 워크플로우에서 호출 순서

```
Step 1-2 (동선 확정)
   ↓
Step 3 (동네 분석)
   3.1 region-code로 lawd_cd 조회
   3.2 apartment/trade + apartment/rent로 실거래가 조회
   3.3 summary.median_price_10k 등을 ApartmentRecord.price_recent_median 등에 매핑
   3.4 각 핵심 동네별 대장 아파트 선정 (references/daejang_scoring.md)
   ↓
Step 4 (웹페이지 생성) — Leaflet + 마커 + 우측 상단 카드에 price 표시
   ↓
Step 5 (호재 뉴스) — k-skill-proxy `naverNewsApiConfigured: true`로 뉴스 검색
```

### 8. 캐시/에러 처리

- proxy는 기본 5분 캐시 (응답 `proxy.cache.ttl_ms: 300000`)
- 한 region × 한 deal_ymd 조합이 핵심 캐시 키
- rate limit 없음 (proxy가 흡수). 단, MOLIT 원본 rate limit은 일 1000회 정도 — 큰 작업 시 deal_ymd를 다양화하지 말 것 (반복 조회 시 캐시 hit)
- `lawd_cd`/`deal_ymd` 형식 오류 → 400
- proxy에 `DATA_GO_KR_API_KEY` 없음 → 503
- upstream 오류 → 502 + `molit_api_XXX` 코드
- 데이터 없음 → 빈 `items` 배열

### 9. 참고

- 원본 skill: `~/.hermes/skills/real-estate-search/SKILL.md` (전체 endpoint 카탈로그)
- 원본 GitHub: `https://github.com/tae0y/real-estate-mcp/tree/main`
- 공식 데이터 출처: 공공데이터포털 `https://www.data.go.kr`
