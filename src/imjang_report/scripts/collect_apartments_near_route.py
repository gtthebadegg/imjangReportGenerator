#!/usr/bin/env python3
"""[결정론] GPS 동선 주변(buffer 기본 300m)의 MOLIT 실거래 아파트 자동 수집.

입력:
  - session.json: photos[]에 lat/lng/timestamp가 있어야 함
  - MOLIT trade JSON 1개 이상: fetch_molit.py 결과
  - 선택 rent JSON 0개 이상

처리:
  1. GPS 사진을 timestamp 순으로 정렬해 route polyline 생성
  2. MOLIT trade items를 단지명 기준으로 집계
  3. Kakao Local REST API로 단지 좌표 정밀 조회
  4. 각 단지 좌표와 route polyline 최소거리 계산
  5. buffer-m 이내 단지만 session.apartments에 갱신

사용법:
  uv run python3 scripts/collect_apartments_near_route.py \
    --session /tmp/imjang/session.json \
    --trade-json /tmp/imjang/trade_41171_202605.json \
    --trade-json /tmp/imjang/trade_41173_202605.json \
    --rent-json /tmp/imjang/rent_41171_202605.json \
    --rent-json /tmp/imjang/rent_41173_202605.json \
    --buffer-m 300 \
    --region-hint 안양 \
    --audit /tmp/imjang/near_route_apartments_audit.json

환경:
  KAKAO_REST_API_KEY 필요. ~/.config/k-skill/secrets.env 자동 로드.

주의:
  - 사용자 보정은 하지 않는다. 자동 수집/자동 좌표/자동 거리 필터만 수행.
  - 좌표 실패 단지는 제외하고 audit에 남긴다.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import statistics
import time
import urllib.request
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode, quote

EARTH_R = 6371000.0


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


def kakao_key() -> str:
    load_dotenv()
    key = os.environ.get("KAKAO_REST_API_KEY") or os.environ.get("KAKAO_LOCAL_REST_API_KEY") or os.environ.get("KAKAO_API_KEY")
    if not key:
        raise SystemExit("KAKAO_REST_API_KEY missing")
    return key


def norm(s: str | None) -> str:
    return re.sub(r"[^0-9A-Za-z가-힣]", "", s or "").lower()


def kakao_keyword(key: str, query: str, size: int = 15, page: int = 1,
                  x: float | None = None, y: float | None = None, radius: int | None = None) -> dict:
    params = {"query": query, "size": size, "page": page}
    if x is not None and y is not None:
        params.update({"x": x, "y": y})
    if radius is not None:
        params["radius"] = radius
    url = "https://dapi.kakao.com/v2/local/search/keyword.json?" + urlencode(params)
    req = urllib.request.Request(url, headers={"Authorization": "KakaoAK " + key})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode("utf-8"))


def is_apartment_doc(d: dict) -> bool:
    cat = d.get("category_name") or ""
    name = d.get("place_name") or ""
    if "입출구" in cat or "정문" in name or "후문" in name:
        return False
    if "중개" in cat or "공인중개" in name:
        return False
    bad_name_tokens = [
        "상가", "관리사무소", "입주자대표", "재건축", "예정",
        "커뮤니티센터", "경로당", "어린이집", "유치원", "주차장",
    ]
    if any(bad in name for bad in bad_name_tokens):
        return False
    # Kakao may return individual buildings like "하이트타운아파트103동" or "대도 B동".
    # They are not complex-level apartment POIs, so exclude them from route apartment lists.
    if re.search(r"(?:아파트)?\s*\d{1,4}동$", name) or re.search(r"\s+[A-Z가-힣]?동$", name):
        return False
    return "부동산 > 주거시설 > 아파트" in cat or "아파트" in cat or name.endswith("아파트")


def score_doc(name: str, d: dict, bbox: tuple[float, float, float, float] | None = None) -> int:
    n = norm(name)
    pn = norm(d.get("place_name"))
    cat = d.get("category_name") or ""
    addr = d.get("address_name") or ""
    try:
        lat = float(d.get("y")); lng = float(d.get("x"))
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
    if "경기" in addr:
        s += 30
    if (d.get("place_name") or "").endswith("아파트"):
        s += 100
    return s


def best_kakao(key: str, name: str, region_hint: str, bbox: tuple[float, float, float, float] | None):
    queries = []
    for q in [name, f"{name} 아파트", f"{region_hint} {name}", f"{region_hint} {name} 아파트"]:
        q = q.strip()
        if q and q not in queries:
            queries.append(q)
    cands = []
    for q in queries:
        try:
            data = kakao_keyword(key, q, 15)
            for d in data.get("documents", []):
                d = dict(d)
                d["_query"] = q
                d["_score"] = score_doc(name, d, bbox)
                cands.append(d)
        except Exception as e:
            cands.append({"_query": q, "_error": str(e), "_score": -10**9})
        time.sleep(0.10)
    seen = set(); uniq = []
    for d in cands:
        k = (d.get("id"), d.get("place_name"), d.get("address_name"))
        if k in seen:
            continue
        seen.add(k); uniq.append(d)
    uniq.sort(key=lambda x: x.get("_score", -10**9), reverse=True)
    return (uniq[0] if uniq and uniq[0].get("_score", -10**9) > 0 else None), uniq[:5]


def parse_ts(p: dict):
    s = p.get("timestamp") or ""
    for fmt in ["%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y:%m:%d %H:%M:%S"]:
        try:
            return datetime.strptime(s[:19], fmt)
        except Exception:
            pass
    return datetime.min


def route_from_photos(session: dict) -> list[tuple[float, float]]:
    pts = []
    for p in sorted(session.get("photos", []), key=parse_ts):
        if p.get("lat") is None or p.get("lng") is None:
            continue
        pts.append((float(p["lat"]), float(p["lng"])))
    # remove consecutive duplicates/near duplicates (<3m)
    out = []
    for pt in pts:
        if not out or haversine(out[-1], pt) >= 3:
            out.append(pt)
    if len(out) < 2:
        raise SystemExit("Need at least 2 GPS photos for route")
    return out


def haversine(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)
    dlat = lat2 - lat1; dlon = lon2 - lon1
    h = math.sin(dlat/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(dlon/2)**2
    return 2 * EARTH_R * math.asin(math.sqrt(h))


def local_xy(lat: float, lng: float, lat0: float) -> tuple[float, float]:
    x = math.radians(lng) * EARTH_R * math.cos(math.radians(lat0))
    y = math.radians(lat) * EARTH_R
    return x, y


def point_segment_distance_m(p: tuple[float, float], a: tuple[float, float], b: tuple[float, float], lat0: float) -> float:
    px, py = local_xy(p[0], p[1], lat0)
    ax, ay = local_xy(a[0], a[1], lat0)
    bx, by = local_xy(b[0], b[1], lat0)
    vx, vy = bx - ax, by - ay
    wx, wy = px - ax, py - ay
    c2 = vx*vx + vy*vy
    if c2 <= 1e-9:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, (wx*vx + wy*vy) / c2))
    projx, projy = ax + t*vx, ay + t*vy
    return math.hypot(px - projx, py - projy)


def route_distance_m(p: tuple[float, float], route: list[tuple[float, float]]) -> float:
    lat0 = sum(lat for lat, _ in route) / len(route)
    return min(point_segment_distance_m(p, route[i], route[i+1], lat0) for i in range(len(route)-1))


def route_bbox(route: list[tuple[float, float]], pad_m: float) -> tuple[float, float, float, float]:
    lats = [p[0] for p in route]; lngs = [p[1] for p in route]
    lat_pad = pad_m / 111000.0
    lng_pad = pad_m / (111000.0 * math.cos(math.radians(sum(lats)/len(lats))))
    return min(lats)-lat_pad, max(lats)+lat_pad, min(lngs)-lng_pad, max(lngs)+lng_pad


def sample_route(route: list[tuple[float, float]], spacing_m: float) -> list[tuple[float, float]]:
    """Route points spaced roughly by spacing_m to limit Kakao radius-search calls."""
    out = [route[0]]
    last = route[0]
    for pt in route[1:]:
        if haversine(last, pt) >= spacing_m:
            out.append(pt)
            last = pt
    if haversine(out[-1], route[-1]) >= 30:
        out.append(route[-1])
    return out


def collect_kakao_poi_apartments(key: str, route: list[tuple[float, float]], buffer_m: float,
                                 spacing_m: float = 250.0, max_pages: int = 3) -> tuple[list[dict], list[dict]]:
    """Collect apartments directly from Kakao Local around sampled route points.

    These records may not have MOLIT trade data. They are still useful map markers.
    """
    docs_by_id: dict[str, dict] = {}
    errors = []
    for lat, lng in sample_route(route, spacing_m):
        for page in range(1, max_pages + 1):
            try:
                data = kakao_keyword(key, "아파트", size=15, page=page, x=lng, y=lat, radius=int(buffer_m))
            except Exception as e:
                errors.append({"lat": lat, "lng": lng, "page": page, "error": str(e)})
                break
            for d in data.get("documents", []):
                if not is_apartment_doc(d):
                    continue
                doc_id = str(d.get("id") or f"{d.get('place_name')}|{d.get('address_name')}")
                docs_by_id.setdefault(doc_id, d)
            if data.get("meta", {}).get("is_end"):
                break
            time.sleep(0.04)
        time.sleep(0.05)
    return list(docs_by_id.values()), errors


def load_items(paths: list[str]) -> list[dict]:
    items = []
    for path in paths:
        if not path:
            continue
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        items.extend(data.get("items", []))
    return items


def price_to_eok(v: int | float | None) -> str | None:
    if v is None:
        return None
    return f"{float(v)/10000:.1f}억"


def aggregate_trade(items: list[dict]) -> dict[str, dict]:
    by = defaultdict(list)
    for it in items:
        name = it.get("name")
        if name:
            by[name].append(it)
    out = {}
    for name, rows in by.items():
        prices = [int(r["price_10k"]) for r in rows if r.get("price_10k") is not None]
        latest = sorted(rows, key=lambda r: r.get("deal_date") or "", reverse=True)[0]
        out[name] = {
            "name": name,
            "district": latest.get("district"),
            "built_year": latest.get("build_year"),
            "trade_count": len(rows),
            "recent_trade_price": price_to_eok(latest.get("price_10k")),
            "latest_deal_date": latest.get("deal_date"),
            "latest_deal_type": latest.get("deal_type"),
            "median_price_10k": int(statistics.median(prices)) if prices else None,
            "min_price_10k": min(prices) if prices else None,
            "max_price_10k": max(prices) if prices else None,
            "areas": sorted({round(float(r.get("area_m2", 0)), 2) for r in rows if r.get("area_m2")}),
        }
    return out


def aggregate_rent(items: list[dict]) -> dict[str, dict]:
    by = defaultdict(list)
    for it in items:
        name = it.get("name")
        if name:
            by[name].append(it)
    out = {}
    for name, rows in by.items():
        latest = sorted(rows, key=lambda r: r.get("deal_date") or "", reverse=True)[0]
        dep = latest.get("deposit_10k") or latest.get("price_10k")
        out[name] = {
            "rent_count": len(rows),
            "jeonse_price": price_to_eok(dep) if dep else None,
            "latest_rent_date": latest.get("deal_date"),
        }
    return out


def apt_id(name: str) -> str:
    return "apt_" + re.sub(r"\s+", "", name)


def naver_link(name: str, lat: float | None = None, lng: float | None = None, zoom: int = 17) -> str:
    """Naver Real Estate search link for an apartment.

    `new.land.naver.com/search` uses the `ms=lat,lng,zoom` viewport hint.
    A fixed `ms` makes every popup open around the same neighborhood and can
    fail to focus the selected apartment, so prefer the apartment's own coords.
    """
    query = quote(name)
    if lat is not None and lng is not None:
        return f"https://new.land.naver.com/search?ms={lat:.6f},{lng:.6f},{zoom}&a=APT&b=A1&e=RETAIL&query={query}"
    return "https://new.land.naver.com/search?a=APT&b=A1&e=RETAIL&query=" + query


def google_link(name: str) -> str:
    return "https://www.google.com/maps/search/" + quote(name)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--session", required=True)
    ap.add_argument("--trade-json", action="append", default=[], help="MOLIT trade JSON path (repeatable)")
    ap.add_argument("--rent-json", action="append", default=[], help="MOLIT rent JSON path (repeatable)")
    ap.add_argument("--buffer-m", type=float, default=300.0)
    ap.add_argument("--region-hint", default="안양")
    ap.add_argument("--audit")
    ap.add_argument("--keep-existing", action="store_true", help="merge with existing apartments instead of replacing")
    args = ap.parse_args()

    session_path = Path(args.session)
    session = json.loads(session_path.read_text(encoding="utf-8"))
    route = route_from_photos(session)
    bbox = route_bbox(route, args.buffer_m + 800)  # search disambiguation bbox wider than filter
    key = kakao_key()

    trade = aggregate_trade(load_items(args.trade_json))
    rent = aggregate_rent(load_items(args.rent_json))

    included = []
    excluded = []
    failed = []
    for name, info in sorted(trade.items()):
        best, top = best_kakao(key, name, args.region_hint, bbox)
        if not best:
            failed.append({"name": name, "reason": "kakao_not_found", "top": top})
            continue
        lat, lng = float(best["y"]), float(best["x"])
        dist = route_distance_m((lat, lng), route)
        rec = {
            "id": apt_id(name),
            "name": name,
            "address": best.get("address_name") or "",
            "road_address": best.get("road_address_name") or "",
            "lat": lat,
            "lng": lng,
            "distance_to_route_m": round(dist, 1),
            "coord_confidence": "high-kakao",
            "coord_source": "Kakao Local route-buffer collection: " + (best.get("place_name") or "") + " / " + (best.get("address_name") or ""),
            "kakao_place_id": best.get("id"),
            "kakao_place_name": best.get("place_name"),
            "district": info.get("district"),
            "built_year": info.get("built_year"),
            "total_units": None,
            "asking_price_range": None,
            "recent_trade_price": info.get("recent_trade_price"),
            "jeonse_price": (rent.get(name) or {}).get("jeonse_price"),
            "trade_count": info.get("trade_count", 0),
            "rent_count": (rent.get(name) or {}).get("rent_count", 0),
            "is_daejang": False,
            "score": 0,
            "tags": [],
            "naver_link": naver_link(name, lat, lng),
            "kakao_map_link": "https://place.map.kakao.com/" + str(best.get("id")) if best.get("id") else "https://map.kakao.com/?q=" + quote(name),
            "google_maps_link": google_link(name),
            "review": None,
            "latest_deal_date": info.get("latest_deal_date"),
            "latest_deal_type": info.get("latest_deal_type"),
            "deal_info_source": "MOLIT/data.go.kr RTMSDataSvcAptTrade",
            "data_as_of": None,
        }
        if dist <= args.buffer_m:
            included.append(rec)
        else:
            excluded.append({"name": name, "distance_to_route_m": round(dist, 1), "matched_place": best.get("place_name")})

    # Add Kakao POI-only apartments around the route, even when no MOLIT trade exists.
    poi_docs, poi_errors = collect_kakao_poi_apartments(key, route, args.buffer_m)
    included_place_ids = {str(r.get("kakao_place_id")) for r in included if r.get("kakao_place_id")}
    included_norm_names = {norm(r.get("name")) for r in included if r.get("name")}
    poi_included = []
    poi_excluded = []
    for d in poi_docs:
        name = (d.get("place_name") or "").strip()
        if not name:
            continue
        pid = str(d.get("id") or "")
        nname = norm(name)
        if pid and pid in included_place_ids:
            continue
        if nname and nname in included_norm_names:
            continue
        try:
            lat, lng = float(d["y"]), float(d["x"])
        except Exception:
            continue
        dist = route_distance_m((lat, lng), route)
        if dist > args.buffer_m:
            poi_excluded.append({"name": name, "distance_to_route_m": round(dist, 1), "address": d.get("address_name")})
            continue
        rec = {
            "id": apt_id(name),
            "name": name,
            "address": d.get("address_name") or "",
            "road_address": d.get("road_address_name") or "",
            "lat": lat,
            "lng": lng,
            "distance_to_route_m": round(dist, 1),
            "coord_confidence": "high-kakao-poi",
            "coord_source": "Kakao Local route-radius POI search: " + name + " / " + (d.get("address_name") or ""),
            "kakao_place_id": pid,
            "kakao_place_name": name,
            "district": None,
            "built_year": None,
            "total_units": None,
            "asking_price_range": None,
            "recent_trade_price": None,
            "jeonse_price": None,
            "trade_count": 0,
            "rent_count": 0,
            "is_daejang": False,
            "score": 0,
            "tags": [],
            "naver_link": naver_link(name, lat, lng),
            "kakao_map_link": "https://place.map.kakao.com/" + pid if pid else "https://map.kakao.com/?q=" + quote(name),
            "google_maps_link": google_link(name),
            "review": None,
            "latest_deal_date": None,
            "latest_deal_type": None,
            "deal_info_source": "국토교통부 아파트매매 실거래가 API로 조회되지 않음",
            "data_as_of": None,
        }
        included.append(rec)
        poi_included.append(rec)
        if pid:
            included_place_ids.add(pid)
        if nname:
            included_norm_names.add(nname)

    # Preserve existing reviews/is_daejang tags where names match if requested, otherwise replace deterministic collection.
    existing = {a.get("name"): a for a in session.get("apartments", [])}
    for rec in included:
        old = existing.get(rec["name"])
        if old:
            rec["review"] = old.get("review")
            rec["tags"] = old.get("tags", [])
            rec["is_daejang"] = bool(old.get("is_daejang", False))
            if old.get("score") is not None:
                rec["score"] = old.get("score")
            if old.get("naver_complex_no"):
                rec["naver_complex_no"] = old.get("naver_complex_no")
            if old.get("naver_complex_name"):
                rec["naver_complex_name"] = old.get("naver_complex_name")
            if old.get("naver_complex_match_score") is not None:
                rec["naver_complex_match_score"] = old.get("naver_complex_match_score")
            if old.get("naver_complex_match_reasons"):
                rec["naver_complex_match_reasons"] = old.get("naver_complex_match_reasons")
    if args.keep_existing:
        merged = {a.get("name"): a for a in session.get("apartments", [])}
        for rec in included:
            merged[rec["name"]] = rec
        session["apartments"] = list(merged.values())
    else:
        session["apartments"] = included

    if not isinstance(session.get("data_source"), dict):
        session["data_source_note"] = session.get("data_source")
        session["data_source"] = {}
    session.setdefault("data_source", {})["apartment_collection"] = {
        "method": "route_buffer_molit_kakao_plus_kakao_poi",
        "buffer_m": args.buffer_m,
        "trade_json_count": len(args.trade_json),
        "rent_json_count": len(args.rent_json),
        "included": len(included),
        "kakao_poi_included": len(poi_included),
        "excluded": len(excluded),
        "failed_geocode": len(failed),
    }
    session_path.write_text(json.dumps(session, ensure_ascii=False, indent=2), encoding="utf-8")

    audit = {
        "method": "route_buffer_molit_kakao_plus_kakao_poi",
        "buffer_m": args.buffer_m,
        "route_points": len(route),
        "trade_complexes": len(trade),
        "included": included,
        "kakao_poi_included": poi_included,
        "kakao_poi_excluded": poi_excluded,
        "kakao_poi_errors": poi_errors,
        "excluded": excluded,
        "failed": failed,
    }
    if args.audit:
        Path(args.audit).write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"route points: {len(route)}")
    print(f"trade complexes: {len(trade)}")
    print(f"included within {args.buffer_m:.0f}m: {len(included)}")
    print(f"kakao poi-only included: {len(poi_included)}")
    print(f"excluded: {len(excluded)}")
    print(f"failed geocode: {len(failed)}")
    for rec in sorted(included, key=lambda x: x["distance_to_route_m"]):
        print(f"  IN {rec['distance_to_route_m']:6.1f}m | {rec['name']} | {rec.get('recent_trade_price') or '-'} | {rec.get('address')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
