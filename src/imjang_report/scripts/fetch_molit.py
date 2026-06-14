#!/usr/bin/env python3
"""[결정론] 국토교통부 아파트 실거래가/전월세 조회.

매매(trade)는 공식 data.go.kr 엔드포인트를 직접 호출한다.
  - 국토교통부_아파트 매매 실거래가 자료
  - Endpoint: https://apis.data.go.kr/1613000/RTMSDataSvcAptTrade/getRTMSDataSvcAptTrade

전월세(rent)는 아직 별도 공식 엔드포인트를 연결하지 않았으므로 기존 k-skill-proxy를 fallback으로 사용한다.

사용법:
    # 지역 코드 조회
    uv run python3 scripts/fetch_molit.py region-code --query "안양시 동안구"

    # 매매 직접 조회 후 JSON 저장
    uv run python3 scripts/fetch_molit.py fetch \
        --lawd-cd 41173 \
        --deal-ymd 202605 \
        --kind trade \
        --out trade_41173_202605.json

    # 전월세 조회(proxy fallback)
    uv run python3 scripts/fetch_molit.py fetch \
        --lawd-cd 41173 \
        --deal-ymd 202605 \
        --kind rent \
        --out rent_41173_202605.json

환경:
    MOLIT_SERVICE_KEY 또는 DATA_GO_KR_SERVICE_KEY 필요 (trade 직접 호출)
    ~/.config/k-skill/secrets.env 자동 로드
    KSKILL_PROXY_BASE_URL optional. 기본 https://k-skill-proxy.nomadamas.org

출력:
    {items: [...], raw_total_count, source, ...}
    items는 collect_apartments_near_route.py가 기대하는 공통 스키마로 normalize한다.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from urllib.error import HTTPError, URLError

DEFAULT_PROXY = "https://k-skill-proxy.nomadamas.org"
APT_TRADE_ENDPOINT = "https://apis.data.go.kr/1613000/RTMSDataSvcAptTrade/getRTMSDataSvcAptTrade"


def load_dotenv() -> None:
    for p in [Path.home() / ".config/k-skill/secrets.env", Path.home() / ".hermes/.env"]:
        if not p.exists():
            continue
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def service_key() -> str:
    load_dotenv()
    key = os.environ.get("MOLIT_SERVICE_KEY") or os.environ.get("DATA_GO_KR_SERVICE_KEY") or os.environ.get("MOLIT_API_KEY")
    if not key:
        raise SystemExit("MOLIT_SERVICE_KEY or DATA_GO_KR_SERVICE_KEY missing")
    return key


def proxy_base() -> str:
    return os.environ.get("KSKILL_PROXY_BASE_URL", DEFAULT_PROXY).rstrip("/")


def get_json_url(url: str, timeout: int = 40) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "Hermes real-estate-site-visit/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = r.read().decode("utf-8", errors="replace")
    try:
        return json.loads(body)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"JSON parse failed: {e}; prefix={body[:200]!r}") from e


def get_proxy_json(path: str, params: dict[str, str]) -> dict:
    url = proxy_base() + path + "?" + urllib.parse.urlencode(params)
    return get_json_url(url)


def clean_amount(v) -> int | None:
    if v is None:
        return None
    s = str(v).replace(",", "").strip()
    if not s:
        return None
    try:
        return int(float(s))
    except Exception:
        return None


def clean_float(v) -> float | None:
    if v is None:
        return None
    s = str(v).replace(",", "").strip()
    if not s:
        return None
    try:
        return float(s)
    except Exception:
        return None


def text(v) -> str:
    return "" if v is None else str(v).strip()


def normalize_apt_trade_item(raw: dict, lawd_cd: str, deal_ymd: str) -> dict:
    year = str(raw.get("dealYear") or deal_ymd[:4])
    month = str(raw.get("dealMonth") or deal_ymd[4:]).zfill(2)
    day = str(raw.get("dealDay") or "01").strip().zfill(2)
    return {
        "name": text(raw.get("aptNm") or raw.get("aptName")),
        "district": text(raw.get("umdNm")),
        "jibun": text(raw.get("jibun")),
        "sgg_cd": str(raw.get("sggCd") or lawd_cd),
        "lawd_cd": lawd_cd,
        "deal_date": f"{year}-{month}-{day}",
        "deal_year": int(year) if year.isdigit() else None,
        "deal_month": int(month) if month.isdigit() else None,
        "deal_day": int(day) if day.isdigit() else None,
        "price_10k": clean_amount(raw.get("dealAmount")),
        "area_m2": clean_float(raw.get("excluUseAr")),
        "floor": clean_amount(raw.get("floor")),
        "build_year": clean_amount(raw.get("buildYear")),
        "apt_dong": text(raw.get("aptDong")),
        "deal_type": text(raw.get("dealingGbn") or raw.get("dealType")),
        "buyer_gbn": text(raw.get("buyerGbn")),
        "seller_gbn": text(raw.get("slerGbn")),
        "estate_agent_sgg_nm": text(raw.get("estateAgentSggNm")),
        "raw": raw,
        "source": "data.go.kr RTMSDataSvcAptTrade",
    }


def extract_items(data: dict) -> tuple[list[dict], int | None, dict]:
    resp = data.get("response", {})
    header = resp.get("header", {})
    body = resp.get("body", {})
    code = header.get("resultCode")
    msg = header.get("resultMsg")
    if code not in ("000", "00", None):
        raise RuntimeError(f"data.go.kr resultCode={code} resultMsg={msg}")
    items_obj = body.get("items", {})
    item = items_obj.get("item") if isinstance(items_obj, dict) else []
    if item is None:
        item = []
    if isinstance(item, dict):
        item = [item]
    total = body.get("totalCount")
    try:
        total = int(total) if total is not None else None
    except Exception:
        total = None
    return item, total, {"header": header, "body_meta": {k: v for k, v in body.items() if k != "items"}}


def fetch_trade_direct(lawd_cd: str, deal_ymd: str, num_rows: int = 1000, sleep_s: float = 0.05) -> dict:
    key = service_key()
    page = 1
    all_raw: list[dict] = []
    total_count = None
    last_meta = {}
    while True:
        params = {
            "serviceKey": key,
            "LAWD_CD": lawd_cd,
            "DEAL_YMD": deal_ymd,
            "pageNo": str(page),
            "numOfRows": str(num_rows),
            "_type": "json",
        }
        url = APT_TRADE_ENDPOINT + "?" + urllib.parse.urlencode(params)
        data = get_json_url(url)
        raw_items, total_count, meta = extract_items(data)
        last_meta = meta
        all_raw.extend(raw_items)
        if total_count is None or len(all_raw) >= total_count or not raw_items:
            break
        page += 1
        time.sleep(sleep_s)
    items = [normalize_apt_trade_item(x, lawd_cd, deal_ymd) for x in all_raw]
    items = [x for x in items if x.get("name")]
    return {
        "source": "data.go.kr RTMSDataSvcAptTrade",
        "endpoint": APT_TRADE_ENDPOINT,
        "lawd_cd": lawd_cd,
        "deal_ymd": deal_ymd,
        "raw_total_count": total_count,
        "items": items,
        "meta": last_meta,
    }


def cmd_region_code(args: argparse.Namespace) -> int:
    data = get_proxy_json("/v1/real-estate/region-code", {"q": args.query})
    if args.out:
        Path(args.out).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(data, ensure_ascii=False, indent=2))
    return 0


def cmd_fetch(args: argparse.Namespace) -> int:
    if args.kind == "trade":
        if args.source == "proxy":
            data = get_proxy_json("/v1/real-estate/apartment/trade", {"lawd_cd": args.lawd_cd, "deal_ymd": args.deal_ymd})
            data.setdefault("source", "k-skill-proxy apartment trade")
        else:
            data = fetch_trade_direct(args.lawd_cd, args.deal_ymd, args.num_rows)
    elif args.kind == "rent":
        if args.source == "direct":
            raise SystemExit("rent direct endpoint is not wired yet; use --source proxy for rent")
        data = get_proxy_json("/v1/real-estate/apartment/rent", {"lawd_cd": args.lawd_cd, "deal_ymd": args.deal_ymd})
        data.setdefault("source", "k-skill-proxy apartment rent")
    else:
        raise SystemExit("--kind must be trade or rent")

    if args.out:
        Path(args.out).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"wrote {args.out} source={data.get('source')} items={len(data.get('items', []))} raw_total={data.get('raw_total_count')}")
    else:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("region-code", help="법정동/시군구 코드 조회")
    p.add_argument("--query", "-q", required=True)
    p.add_argument("--out")
    p.set_defaults(func=cmd_region_code)

    p = sub.add_parser("fetch", help="아파트 매매/전월세 조회")
    p.add_argument("--lawd-cd", required=True)
    p.add_argument("--deal-ymd", required=True, help="YYYYMM")
    p.add_argument("--kind", choices=["trade", "rent"], required=True)
    p.add_argument("--source", choices=["direct", "proxy"], default="direct", help="trade 기본 direct, rent는 proxy만 지원")
    p.add_argument("--num-rows", type=int, default=1000)
    p.add_argument("--out")
    p.set_defaults(func=cmd_fetch)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
