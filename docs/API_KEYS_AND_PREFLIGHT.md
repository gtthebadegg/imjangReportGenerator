# API 키와 사전 점검

## 필요한 API

| API | 환경변수 | 필수성 | 설명 |
|---|---|---:|---|
| Kakao Local REST API | `KAKAO_REST_API_KEY` | 전체 파이프라인 권장/사실상 필수 | 동선 주변 아파트 POI 수집, 단지 좌표 검색 |
| data.go.kr MOLIT RTMS 아파트 매매 실거래가 | `MOLIT_SERVICE_KEY` 또는 `DATA_GO_KR_SERVICE_KEY` | 전체 파이프라인 권장/필수 | 거래월/법정동 코드 기준 매매 실거래 수집 |
| VWorld Search | `VWORLD_KEY` | 선택 | 좌표 fallback |
| k-skill proxy | `KSKILL_PROXY_BASE_URL` | 선택 | region/rent/proxy fallback |

## 키 발급

### Kakao Local

1. https://developers.kakao.com/console/app 접속
2. 애플리케이션 생성
3. `앱 키`에서 `REST API 키` 복사
4. `.env`에 저장

```bash
KAKAO_REST_API_KEY=...
```

### data.go.kr MOLIT RTMS

1. https://www.data.go.kr/data/15126469/openapi.do 접속
2. “국토교통부_아파트 매매 실거래가 자료” 활용 신청
3. 마이페이지에서 Encoding 인증키 복사
4. `.env`에 저장

```bash
MOLIT_SERVICE_KEY=...
# 또는
DATA_GO_KR_SERVICE_KEY=...
```

### VWorld 선택

1. https://www.data.go.kr/data/15000273/openapi.do 활용 신청
2. VWorld 검색 API 키 복사

```bash
VWORLD_KEY=...
```

## 점검 명령

```bash
python -m imjang_report.scripts.check_setup
python -m imjang_report.scripts.check_setup --check-network
python -m imjang_report.scripts.check_setup --json
```

`check_setup`은 키 값을 출력하지 않고 `abc…xyz` 형태로 redacted 표시만 합니다.

## 키가 없는 경우 가능한 실행

키가 없어도 다음은 가능합니다.

```bash
python -m imjang_report.scripts.run_pipeline \
  --photos /absolute/path/to/photos \
  --workdir ./out/no-api \
  --region-hint 테스트 \
  --lawd-cd 00000 \
  --deal-ymd 202605 \
  --skip-geocode-clusters \
  --skip-market-data
```

이 모드는 사진 GPS/클러스터링/HTML 생성만 검증합니다. 주변 아파트/실거래 데이터는 비어 있습니다.
