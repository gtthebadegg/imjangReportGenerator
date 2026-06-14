# 순수 Python 실행 가이드

이 문서는 agent 없이 Python만으로 임장 리포트를 생성하는 절차입니다.

## 1. 설치

```bash
git clone https://github.com/<OWNER>/imjang-report.git
cd imjang-report
uv venv
uv pip install -e '.[test]'
```

uv가 없다면:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[test]'
```

## 2. 환경 점검

```bash
python -m imjang_report.scripts.check_setup
python -m imjang_report.scripts.check_setup --check-network
```

`--check-network`는 Kakao/data.go.kr/proxy endpoint를 실제로 찔러 봅니다. API 키가 없으면 인증 실패가 나올 수 있지만, 기본 샘플 테스트는 키 없이도 가능합니다.

## 3. API 키 설정

```bash
cp .env.example .env
# .env에 실제 키 입력
```

권장 키:

| 변수 | 필수성 | 용도 |
|---|---:|---|
| `KAKAO_REST_API_KEY` | 전체 파이프라인 권장/사실상 필수 | 동선 주변 아파트 POI 검색, 단지 좌표 확인 |
| `MOLIT_SERVICE_KEY` 또는 `DATA_GO_KR_SERVICE_KEY` | 전체 파이프라인 권장/필수 | 국토교통부 아파트 매매 실거래가 API |
| `VWORLD_KEY` | 선택 | VWorld 좌표 fallback |
| `KSKILL_PROXY_BASE_URL` | 선택 | rent/proxy fallback |

키는 `.env`, `~/.config/imjang-report/secrets.env`, `~/.config/k-skill/secrets.env`, `~/.hermes/.env` 순으로 읽습니다.

## 4. 전체 실행

```bash
python -m imjang_report.scripts.run_pipeline \
  --photos /absolute/path/to/photos \
  --workdir ./out/anyang-2026-06-13 \
  --region-hint "안양" \
  --lawd-cd 41171 \
  --lawd-cd 41173 \
  --deal-ymd 202605
```

옵션 설명:

- `--photos`: GPS EXIF가 있는 원본 사진 폴더
- `--workdir`: 결과 저장 폴더
- `--region-hint`: Kakao 검색 disambiguation용 지역명
- `--lawd-cd`: 시군구 법정동 코드 5자리. 여러 개 반복 가능
- `--deal-ymd`: 실거래 조회월, `YYYYMM`
- `--buffer-m`: GPS 동선 주변 반경. 기본 300m
- `--skip-geocode-clusters`: Nominatim 역지오코딩 생략
- `--skip-market-data`: Kakao/MOLIT API 없이 사진/GPS/HTML만 생성

## 5. 결과 확인

```bash
open ./out/anyang-2026-06-13/report.html      # macOS
xdg-open ./out/anyang-2026-06-13/report.html  # Linux
```

WSL에서는 Windows 경로로 열어도 됩니다.

## 6. Notion Import ZIP 생성

웹 리포트에서 `📦 Notion ZIP 생성`을 누르거나 Python으로 생성합니다.

```bash
python -m imjang_report.scripts.export_notion_md_zip \
  --session ./out/anyang-2026-06-13/session.json \
  --out ./out/anyang-2026-06-13/imjang_notion_import.zip
```

Notion에서는 `Settings → Import → Text & Markdown`에서 ZIP을 import합니다. ZIP 안에는 `imjang_report.md`와 `images/` 폴더가 상대경로로 들어갑니다.
