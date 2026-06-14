# WSL 환경에서 공공데이터포털(data.go.kr) 호출 노트

## 현상 (2026-06-13 안양 임장 시점)

WSL2 Ubuntu 22.04 환경에서 outbound 호출 결과:

| 도메인 | 상태 | 비고 |
|--------|------|------|
| `www.data.go.kr` | 200 OK | 마이페이지/목록 페이지 |
| `apis.data.go.kr` | 400 Request Blocked | OpenAPI 서브도메인 |
| `k-skill-proxy.nomadamas.org` | 200 OK | 프록시는 정상 |

→ **OpenAPI 서브도메인만 차단**, 홈페이지와 프록시는 열림.

## 진단

```bash
# 1. DNS 확인
nslookup apis.data.go.kr  # → 223.130.169.165 (정상 해석)

# 2. 응답 헤더 확인
curl -v "https://apis.data.go.kr/1613000/RTMSDataSvcAptTrade/getRTMSDataSvcAptTrade?..." 2>&1 | head -30
# → < HTTP/1.1 400 Bad Request  ← WSL 게이트웨이 또는 호스트 방화벽이 차단
```

원인: WSL의 NAT 인터페이스가 호스트 Windows 방화벽 정책에 따라 outbound 트래픽 일부를 차단. VPN/회사 네트워크 정책과 무관할 수 있음 (재현 가능).

## Fix 우선순위

### 1순위: k-skill-proxy 경유 (권장)

proxy가 자체 MOLIT API 키를 보유하고 있음. 인증키 노출 없이 호출 가능.

```bash
curl -fsS --get "https://k-skill-proxy.nomadamas.org/v1/real-estate/apartment/trade" \
  --data-urlencode 'lawd_cd=41173' \
  --data-urlencode 'deal_ymd=202605'
```

### 2순위: Windows PowerShell/브라우저에서 호출 후 JSON 복사

WSL에서 직접 호출이 안 되면, Windows 측에서 호출 후 결과 JSON을 WSL로 가져옴:

```powershell
# Windows PowerShell
$xml = Invoke-WebRequest -Uri "https://apis.data.go.kr/.../?serviceKey=...&LAWD_CD=41173&DEAL_YMD=202605&type=json" -UseBasicParsing
$xml.Content | Out-File "$env:USERPROFILE\Downloads\trade_41173.json"
```

```bash
# WSL
cp "/mnt/c/Users/<USER>/Downloads/trade_41173.json" /tmp/
```

### 3순위: WSL 네트워크 정책 변경 (비권장)

`/etc/wsl.conf` 또는 `netsh` 로 WSL 인터페이스 정책 변경 가능. 시스템 전체 영향 → 사용자에게 확인 필수.

## 검증 헬퍼

```bash
# proxy에 MOLIT 키가 살아있는지
curl -fsS "https://k-skill-proxy.nomadamas.org/health" | python3 -c "import json,sys; d=json.load(sys.stdin); print('molit:', d['upstreams']['molitConfigured'])"

# 다른 OpenAPI 사이트도 같은 패턴으로 막히는지 (참고용)
for url in "https://apis.data.go.kr" "https://apis.openapi.fr" "https://api.odcloud.kr"; do
  echo -n "$url: "
  curl -s -o /dev/null -w "%{http_code}\n" --max-time 5 "$url" 2>&1
done
```

## 다른 skill 영향

`kakaoLocalConfigured: true` 라고 proxy health가 표시하지만, **endpoint 경로가 노출 안 됨** (`/v1/kakao/local/search`, `/v1/local/search` 등 모두 Google GFE 400 응답). 단지 좌표는 행정동(법정동) GPS 클러스터 centroid로 fallback하고 네이버부동산/카카오맵 키워드 검색 링크로 사용자 보정.

→ SKILL.md의 "kakaoLocal at k-skill-proxy endpoint 미노출" pitfall 참조.
