# data.go.kr 아파트매매 실거래가 직접 교차검증 패턴

## 언제 쓰나

사용자가 리포트의 가격 미조회 문구가 `MOLIT 기준`인지, 사용자가 제공한 data.go.kr 키로 `국토교통부_아파트 매매 실거래가 자료` API를 직접 호출한 결과인지 구분해 달라고 할 때 사용한다.

## 핵심 원칙

- `MOLIT`는 내부/영문 축약어로는 맞지만 사용자-facing 리포트 문구에는 모호할 수 있다.
- 교차검증을 요구받으면 같은 조건(`lawd_cd`, `deal_ymd`)으로 공식 endpoint를 직접 호출한다.
- 직접 호출 결과가 정상인데도 특정 Kakao POI-only 단지에 가격이 없으면 “API가 죽었다”가 아니라 “해당 단지가 그 조건의 공식 아파트매매 실거래가 결과와 매칭되지 않았다”로 본다.
- 리포트 문구는 `국토교통부 아파트매매 실거래가 API로 조회되지 않음`을 사용한다.

## 직접 호출 endpoint

```bash
uv run python3 scripts/fetch_molit.py fetch \
  --lawd-cd 41173 \
  --deal-ymd 202605 \
  --kind trade \
  --source direct \
  --out trade_41173_202605_direct.json
```

내부적으로 호출하는 공식 endpoint:

```text
https://apis.data.go.kr/1613000/RTMSDataSvcAptTrade/getRTMSDataSvcAptTrade
```

필수 파라미터:

- `serviceKey`: 사용자 또는 환경의 data.go.kr 인증키
- `LAWD_CD`: 5자리 법정동/시군구 코드
- `DEAL_YMD`: YYYYMM
- `pageNo`, `numOfRows`
- `_type=json` 또는 `type=json` 계열 JSON 요청

## 검증 보고 형식

최종 답변에는 다음을 짧게 포함한다.

- 직접 호출 여부: 사용자 키로 data.go.kr 공식 아파트매매 API 직접 호출
- endpoint 이름: `RTMSDataSvcAptTrade`
- 조건: 법정동 코드, 거래년월
- 결과: 지역별 `items`/`raw_total_count`, 총 건수
- 문구 변경 여부: `MOLIT 기준...` → `국토교통부 아파트매매 실거래가 API로 조회되지 않음`

## 주의

- 예전 WSL 세션에서 `apis.data.go.kr` outbound가 막힌 적이 있지만, 환경 상태는 변할 수 있다. 먼저 직접 호출을 실제로 시도하고 결과를 기준으로 판단한다.
- API 키 값은 절대 출력하지 않는다.
- 직접 API 전체가 정상이어도 단지명 매칭은 별도 문제다. Kakao POI 이름과 국토교통부 실거래 단지명이 다를 수 있어 이름 정규화/주소/좌표 기반 매칭 보완이 필요할 수 있다.
