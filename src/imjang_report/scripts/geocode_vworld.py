#!/usr/bin/env python3
"""[결정론] VWorld 검색 API로 아파트 단지 정밀 좌표 조회.

VWorld(공간정보 오픈플랫폼, 행정안전부 운영)는 한국 아파트 단지명 매칭 정확도 최상.
Nominatim(OSM)은 한국 신축 아파트 단지명이 DB에 없어서 매칭 실패가 많은데,
VWorld는 "시설구역경계 > 아파트단지" 카테고리 + "건물 > 주거용공동주택" 동별 entry가 모두 잡힘.

사용법:
    # 키 발급: https://www.data.go.kr/data/15000273/openapi.do (1~2시간 자동 승인)
    export VWORLD_KEY=<YOUR_VWORLD_KEY>
    uv run python3 scripts/geocode_vworld.py \
        --session /path/to/session.json

출력:
    session.json의 apartments[]에 lat/lng/coord_confidence/coord_source 갱신
    - conf=high: 시설구역경계 > 아파트단지 (가장 정확)
    - conf=high: 건물 > 주거용공동주택 (동별 평균, 정확)
    - conf=medium: 기타 카테고리
    - conf=failed: 매칭 실패 (기존 좌표 유지)

결정론 = 단지명으로 API 1회 호출, 좌표 + 카테고리 추출만. AI 불필요.

WSL 주의:
  apis.data.go.kr는 WSL outbound에서 차단되지만, api.vworld.kr은 정상 동작 확인됨.
  Python urllib + 한글 query는 ASCII codec 오류 발생 → quote(query, safe='')로
  직접 percent-encoding 후 raw URL로 호출 (urllib.parse.quote 사용 OK, 단 ascii 모드
  stdout이 아니라 URL에 직접 넣을 때만).
"""
import argparse
import json
import os
import sys
import time
import urllib.request
from pathlib import Path
from urllib.parse import quote


def vworld_search(query, key):
    """VWorld 검색 v2 API. request=search 필수 (v1은 request 파라미터 없음)."""
    base = "https://api.vworld.kr/req/search"
    q = quote(query, safe='')  # 한글 percent-encoding (ASCII codec 오류 회피)
    url = f"{base}?request=search&key={key}&query={q}&type=place&format=json&page=1&size=30"
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'HermesAgent/1.0 (real-estate-imjang)'})
        with urllib.request.urlopen(req, timeout=8) as resp:
            return json.loads(resp.read().decode('utf-8'))
    except Exception as e:
        return {"error": str(e)}


def extract_apt_coords(query, key):
    """아파트 단지 정밀 좌표 추출.

    우선순위:
    1) 시설구역경계 > 아파트단지 (정확한 단지 polygon)
    2) 건물 > 주거용공동주택 / 제1종근린생활시설 (동별, 단지 내부 건물)
    3) 기타 카테고리 (fallback)
    """
    r = vworld_search(query, key)
    if 'error' in r:
        return None, "API error: " + r['error'][:50]
    res = r.get("response", {})
    status = res.get("status", "?")
    if status != "OK":
        return None, f"status={status}"
    items = res.get("result", {}).get("items", [])

    boundary_points = []
    building_points = []
    other_points = []

    for it in items:
        title = it.get("title", "")
        cat = it.get("category", "")
        point = it.get("point", {})
        if not point.get("x") or not point.get("y"):
            continue
        # 단지명 정확히 포함된 entry만 (관련 없는 결과 제외)
        if query.replace(" ", "") not in title.replace(" ", ""):
            continue
        lng, lat = float(point["x"]), float(point["y"])
        # 시/도 bbox 필터 (안양시: 37.37~37.42, 126.90~126.98 — 다른 지역은 수정)
        if not (37.37 <= lat <= 37.42 and 126.90 <= lng <= 126.98):
            continue
        if "시설구역경계" in cat and "아파트단지" in cat:
            boundary_points.append((lat, lng, title, cat))
        elif "주거용공동주택" in cat or "제1종근린생활시설" in cat:
            building_points.append((lat, lng, title, cat))
        else:
            other_points.append((lat, lng, title, cat))

    if boundary_points:
        lats = [p[0] for p in boundary_points]
        lngs = [p[1] for p in boundary_points]
        return (sum(lats)/len(lats), sum(lngs)/len(lngs),
                f"VWorld 시설구역경계 {len(boundary_points)}개 평균"), "high"
    if building_points:
        lats = [p[0] for p in building_points]
        lngs = [p[1] for p in building_points]
        return (sum(lats)/len(lats), sum(lngs)/len(lngs),
                f"VWorld 건물 {len(building_points)}개 평균"), "high"
    if other_points:
        lats = [p[0] for p in other_points]
        lngs = [p[1] for p in other_points]
        return (sum(lats)/len(lats), sum(lngs)/len(lngs),
                f"VWorld 기타 {len(other_points)}개 평균"), "medium"
    return None, "VWorld NOT_FOUND"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--session', required=True)
    parser.add_argument('--key', default=os.environ.get('VWORLD_KEY'),
                        help='VWorld API 키 (또는 env VWORLD_KEY)')
    parser.add_argument('--min-conf', default='failed',
                        choices=['high', 'medium', 'low', 'fallback', 'failed'],
                        help='이 conf 이하만 갱신 (기본: failed=전체)')
    parser.add_argument('--bbox', default='37.37,37.42,126.90,126.98',
                        help='검색 영역 bbox (lat_min,lat_max,lng_min,lng_max)')
    args = parser.parse_args()

    if not args.key:
        print("ERROR: --key 또는 env VWORLD_KEY 필요", file=sys.stderr)
        print("  발급: https://www.data.go.kr/data/15000273/openapi.do", file=sys.stderr)
        sys.exit(1)

    bbox = [float(x) for x in args.bbox.split(',')]
    lat_min, lat_max, lng_min, lng_max = bbox

    session_path = Path(args.session)
    with open(session_path, 'r', encoding='utf-8') as f:
        session = json.load(f)
    apartments = session.get('apartments', [])
    print(f"입력 아파트: {len(apartments)}개", file=sys.stderr)

    # 정확도 순서 (failed가 가장 낮음)
    conf_order = {'high': 4, 'medium': 3, 'low': 2, 'fallback': 1, 'failed': 0}
    min_order = conf_order[args.min_conf]
    to_update = [a for a in apartments
                 if a.get('name') and conf_order.get(a.get('coord_confidence', 'failed'), 0) <= min_order]
    print(f"VWorld 재조회 대상: {len(to_update)}개 (현재 conf<={args.min_conf})", file=sys.stderr)
    print(f"bbox: lat [{lat_min}, {lat_max}], lng [{lng_min}, {lng_max}]", file=sys.stderr)

    n_h = n_m = n_f = 0
    for apt in to_update:
        name = apt['name']
        r, status = extract_apt_coords(name, args.key)
        if r:
            lat, lng, src = r
            apt['lat'] = round(lat, 6)
            apt['lng'] = round(lng, 6)
            apt['coord_confidence'] = status
            apt['coord_source'] = src
            if status == 'high':
                n_h += 1
            else:
                n_m += 1
        else:
            n_f += 1
        time.sleep(0.3)  # rate limit 여유
        marker = {'high': '📍', 'medium': '🗺️', 'failed': '❓'}.get(status, '?')
        coord = f"({apt.get('lat', '?'):.5f}, {apt.get('lng', '?'):.5f})" if apt.get('lat') else '(없음)'
        print(f"  {marker} {name:30s} → {status:8s} | {coord}", file=sys.stderr)

    with open(session_path, 'w', encoding='utf-8') as f:
        json.dump(session, f, ensure_ascii=False, indent=2)

    print(f"\n=== 결과: high={n_h}, medium={n_m}, failed={n_f} / {len(to_update)} ===", file=sys.stderr)
    print(f"✓ {session_path} 갱신", file=sys.stderr)


if __name__ == '__main__':
    main()
