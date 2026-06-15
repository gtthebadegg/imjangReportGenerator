#!/usr/bin/env python3
"""[결정론] Kakao Local API로 한국 아파트/장소 좌표 정밀 보정.

입력 session.json의 apartments[]를 Kakao Local keyword search로 재조회해
lat/lng/address/kakao_place_id/coord_source를 갱신한다.

사용법:
    uv run python3 scripts/geocode_kakao.py \
        --session /path/to/session.json \
        --audit /path/to/kakao_geocode_audit.json

환경변수:
    KAKAO_REST_API_KEY preferred.
    또는 ~/.config/k-skill/secrets.env / ~/.hermes/.env 에 저장.

원칙:
- API 키는 절대 출력하지 않는다.
- Kakao 좌표 convention: x=longitude, y=latitude.
- 단지명, 단지명+아파트, 안양+단지명, 안양+단지명+아파트 순으로 조회한다.
- '부동산 > 주거시설 > 아파트' 카테고리와 이름 exact/contains match를 우선한다.
- 검색 audit JSON을 남겨 자동화 품질을 검토할 수 있게 한다.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlencode


def load_dotenv() -> None:
    candidates = [
        Path.cwd() / ".env",
        Path(__file__).resolve().parents[3] / ".env",
        Path.home() / ".config/imjang-report/secrets.env",
        Path.home() / ".config/k-skill/secrets.env",
        Path.home() / ".hermes/.env",
    ]
    seen: set[Path] = set()
    for p in candidates:
        p = p.resolve()
        if p in seen:
            continue
        seen.add(p)
        if not p.exists():
            continue
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


def get_kakao_key() -> str:
    load_dotenv()
    key = (
        os.environ.get("KAKAO_REST_API_KEY")
        or os.environ.get("KAKAO_LOCAL_REST_API_KEY")
        or os.environ.get("KAKAO_API_KEY")
    )
    if not key:
        raise SystemExit("Kakao REST API key not configured. Set KAKAO_REST_API_KEY.")
    return key


def norm(s: str | None) -> str:
    return re.sub(r"[^0-9A-Za-z가-힣]", "", s or "").lower()


def kakao_keyword(key: str, query: str, size: int = 15) -> dict:
    url = "https://dapi.kakao.com/v2/local/search/keyword.json?" + urlencode(
        {"query": query, "size": size}
    )
    req = urllib.request.Request(url, headers={"Authorization": "KakaoAK " + key})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode("utf-8"))


def score_doc(name: str, d: dict, bbox: tuple[float, float, float, float] | None) -> int:
    n = norm(name)
    pn = norm(d.get("place_name"))
    addr = d.get("address_name") or ""
    cat = d.get("category_name") or ""
    try:
        lat = float(d.get("y"))
        lng = float(d.get("x"))
    except Exception:
        return -10**9

    if bbox:
        min_lat, max_lat, min_lng, max_lng = bbox
        if not (min_lat <= lat <= max_lat and min_lng <= lng <= max_lng):
            return -10**8

    s = 0
    if n and n in pn:
        s += 1000
    elif pn and pn in n:
        s += 700
    common = sum(1 for a, b in zip(n, pn) if a == b)
    s += min(common, 10) * 20

    if "부동산 > 주거시설 > 아파트" in cat:
        s += 600
    elif "아파트" in cat:
        s += 400
    if "입출구" in cat or "정문" in (d.get("place_name") or "") or "후문" in (d.get("place_name") or ""):
        s -= 200
    if "중개" in cat or "공인중개" in (d.get("place_name") or ""):
        s -= 300
    if "안양시" in addr:
        s += 100
    if "경기" in addr:
        s += 30
    if (d.get("place_name") or "").endswith("아파트"):
        s += 100
    return s


def best_kakao(key: str, name: str, region_hint: str, bbox: tuple[float, float, float, float] | None):
    queries: list[str] = []
    for q in [name, f"{name} 아파트", f"{region_hint} {name}", f"{region_hint} {name} 아파트"]:
        q = q.strip()
        if q and q not in queries:
            queries.append(q)

    candidates: list[dict] = []
    for q in queries:
        try:
            data = kakao_keyword(key, q, size=15)
            for d in data.get("documents", []):
                d = dict(d)
                d["_query"] = q
                d["_score"] = score_doc(name, d, bbox)
                candidates.append(d)
        except Exception as e:
            candidates.append({"_query": q, "_error": str(e), "_score": -10**9})
        time.sleep(0.12)

    seen = set()
    uniq: list[dict] = []
    for d in candidates:
        key2 = (d.get("id"), d.get("place_name"), d.get("address_name"))
        if key2 in seen:
            continue
        seen.add(key2)
        uniq.append(d)
    uniq.sort(key=lambda d: d.get("_score", -10**9), reverse=True)
    if uniq and uniq[0].get("_score", -10**9) > 0:
        return uniq[0], uniq[:5]
    return None, uniq[:5]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--session", required=True, help="session.json path")
    ap.add_argument("--audit", default=None, help="audit JSON output path")
    ap.add_argument("--region-hint", default="안양", help="query prefix for disambiguation")
    ap.add_argument("--bbox", default="37.36,37.43,126.89,127.02", help="min_lat,max_lat,min_lng,max_lng or empty")
    args = ap.parse_args()

    key = get_kakao_key()
    session_path = Path(args.session)
    session = json.loads(session_path.read_text(encoding="utf-8"))
    bbox = None
    if args.bbox:
        parts = [float(x) for x in args.bbox.split(",")]
        if len(parts) != 4:
            raise SystemExit("--bbox must be min_lat,max_lat,min_lng,max_lng")
        bbox = tuple(parts)  # type: ignore[assignment]

    results = []
    failures = []
    for a in session.get("apartments", []):
        best, top = best_kakao(key, a["name"], args.region_hint, bbox)
        if not best:
            failures.append({
                "name": a.get("name"),
                "top": [
                    {
                        "place_name": d.get("place_name"),
                        "category_name": d.get("category_name"),
                        "address_name": d.get("address_name"),
                        "score": d.get("_score"),
                        "error": d.get("_error"),
                    }
                    for d in top
                ],
            })
            continue

        old = {
            "lat": a.get("lat"),
            "lng": a.get("lng"),
            "coord_confidence": a.get("coord_confidence"),
            "coord_source": a.get("coord_source"),
        }
        a["lat"] = float(best["y"])
        a["lng"] = float(best["x"])
        a["coord_confidence"] = "high-kakao"
        a["coord_source"] = (
            "Kakao Local keyword exact/weighted match: "
            + (best.get("place_name") or "")
            + " / "
            + (best.get("address_name") or "")
        )
        a["kakao_place_id"] = best.get("id")
        a["kakao_place_name"] = best.get("place_name")
        a["address"] = best.get("address_name") or a.get("address", "")
        a["road_address"] = best.get("road_address_name") or a.get("road_address", "")
        a["kakao_map_link"] = (
            "https://place.map.kakao.com/" + str(best.get("id"))
            if best.get("id")
            else "https://map.kakao.com/?q=" + a["name"]
        )
        results.append({
            "name": a.get("name"),
            "matched_place": best.get("place_name"),
            "address": best.get("address_name"),
            "lat": a["lat"],
            "lng": a["lng"],
            "score": best.get("_score"),
            "query": best.get("_query"),
            "old": old,
        })

    session_path.write_text(json.dumps(session, ensure_ascii=False, indent=2), encoding="utf-8")
    audit = {"provider": "kakao-local", "count": len(results), "failures": failures, "results": results}
    if args.audit:
        Path(args.audit).write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Kakao geocoded: {len(results)}/{len(session.get('apartments', []))}")
    print(f"Failures: {len(failures)}")
    for r in results:
        print(f"  OK {r['name']} -> {r['matched_place']} ({r['lat']:.6f}, {r['lng']:.6f}) score={r['score']}")
    for f in failures:
        print(f"  FAIL {f['name']}")
    return 0 if not failures else 2


if __name__ == "__main__":
    raise SystemExit(main())
