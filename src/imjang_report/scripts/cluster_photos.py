#!/usr/bin/env python3
"""[결정론] GPS 사진들을 거리 기반 클러스터링 + Nominatim 역지오코딩.

사용법:
    uv run python3 scripts/cluster_photos.py \
        --session /path/to/session.json \
        --radius 0.3  # 300m (단위: km)

출력:
    session.json neighborhoods[]: 클러스터별 centroid/시간/사진수
    session.json raw_clusters[]: 클러스터별 사진 목록

결정론 = 좌표 거리 계산 + 시간 정렬만. AI 불필요.
"""
import argparse
import json
import sys
import math
import time
import urllib.request
from pathlib import Path
from collections import defaultdict

def haversine(lat1, lon1, lat2, lon2):
    """두 좌표 사이 거리 (km)"""
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    return 2 * R * math.asin(math.sqrt(a))

def cluster_centroid(photos):
    n = len(photos)
    return (sum(p['lat'] for p in photos) / n, sum(p['lng'] for p in photos) / n)

def cluster_by_radius(photos, radius_km):
    """시간순 정렬 후, 이전 클러스터 중심에서 radius_km 이내면 같은 클러스터."""
    sorted_photos = sorted(photos, key=lambda p: p.get('timestamp', ''))
    clusters = []
    for p in sorted_photos:
        added = False
        for c in clusters:
            dist = haversine(c['centroid'][0], c['centroid'][1], p['lat'], p['lng'])
            if dist <= radius_km:
                c['photos'].append(p)
                c['centroid'] = cluster_centroid(c['photos'])
                added = True
                break
        if not added:
            clusters.append({'photos': [p], 'centroid': (p['lat'], p['lng'])})
    return clusters

def reverse_geocode(lat, lon):
    """Nominatim OpenStreetMap. rate limit 1 req/sec 필수."""
    try:
        url = f"https://nominatim.openstreetmap.org/reverse?lat={lat}&lon={lon}&format=json&accept-language=ko"
        req = urllib.request.Request(url, headers={'User-Agent': 'HermesAgent/1.0 (real-estate-imjang)'})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read())
        display = data.get('display_name', '')
        addr = data.get('address', {})
        legal_dong = (addr.get('neighbourhood') or addr.get('suburb')
                      or addr.get('city_district') or '?')
        return display, legal_dong
    except Exception as e:
        return '', '?'

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--session', required=True, help='session.json 경로 (입출력)')
    parser.add_argument('--radius', type=float, default=0.3, help='클러스터 반경 (km, 기본 0.3 = 300m)')
    parser.add_argument('--no-geocode', action='store_true', help='역지오코딩 스킵 (rate limit 회피)')
    args = parser.parse_args()

    session_path = Path(args.session)
    with open(session_path, 'r', encoding='utf-8') as f:
        session = json.load(f)
    photos = session.get('photos', [])
    print(f"입력 사진: {len(photos)}개", file=sys.stderr)

    if not photos:
        print("ERROR: photos 없음. extract_photo_gps.py 먼저 실행", file=sys.stderr)
        sys.exit(1)

    # 클러스터링
    clusters = cluster_by_radius(photos, args.radius)
    print(f"클러스터: {len(clusters)}개 (반경 {args.radius}km)", file=sys.stderr)

    for i, c in enumerate(clusters):
        c['cluster_id'] = i
        ts = sorted([p.get('timestamp', '') for p in c['photos']])
        c['first_time'] = ts[0] if ts else ''
        c['last_time'] = ts[-1] if ts else ''
        c['photo_count'] = len(c['photos'])

    # 역지오코딩
    if not args.no_geocode:
        for c in clusters:
            display, legal_dong = reverse_geocode(c['centroid'][0], c['centroid'][1])
            c['display_name'] = display
            c['legal_dong'] = legal_dong
            time.sleep(1.1)  # Nominatim rate limit
            print(f"  [{c['cluster_id']:2d}] {c['photo_count']:2d}장 | "
                  f"{c['first_time'][11:16] if c['first_time'] else '--:--'} | {legal_dong}",
                  file=sys.stderr)

    # session.json 갱신
    session['neighborhoods'] = [
        {
            'cluster_id': c['cluster_id'],
            'cluster_name': c.get('legal_dong', f"지점 {c['cluster_id']+1}"),
            'lat': round(c['centroid'][0], 6),
            'lng': round(c['centroid'][1], 6),
            'first_time': c.get('first_time', ''),
            'last_time': c.get('last_time', ''),
            'photo_count': c['photo_count'],
            'display_name': c.get('display_name', ''),
        }
        for c in clusters
    ]
    session['raw_clusters'] = [
        {
            'cluster_id': c['cluster_id'],
            'centroid': list(c['centroid']),
            'photos': c['photos'],
        }
        for c in clusters
    ]

    with open(session_path, 'w', encoding='utf-8') as f:
        json.dump(session, f, ensure_ascii=False, indent=2)

    print(f"\n✓ {session_path} 갱신: neighborhoods={len(clusters)}", file=sys.stderr)

if __name__ == '__main__':
    main()
