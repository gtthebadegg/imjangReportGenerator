#!/usr/bin/env python3
"""[결정론] 사진 폴더에서 GPS/EXIF 추출 → session.json photos[] 갱신.

사용법:
    uv run --with pillow --with piexif python3 scripts/extract_photo_gps.py \
        --photos /path/to/photos/ \
        --session /path/to/session.json

출력:
    session.json의 photos[] 배열에 lat/lng/timestamp 채워짐
    GPS 없는 사진은 제외됨 (스크린샷/카톡 이미지)

결정론 = AI 불필요. 매번 같은 결과. 이미지 메타데이터 파싱만.
"""
import argparse
import json
import sys
from pathlib import Path

def dms_to_dd(dms, ref):
    """EXIF GPS (degrees/minutes/seconds + reference) → decimal degrees"""
    d = float(dms[0])
    m = float(dms[1])
    s = float(dms[2])
    dd = d + m / 60.0 + s / 3600.0
    if ref in ('S', 'W'):
        dd = -dd
    return dd

def get_gps(photo_path):
    """JPEG/HEIC 사진에서 GPS (lat, lon) 추출. 없으면 None."""
    try:
        from PIL import Image
        from PIL.ExifTags import TAGS, GPSTAGS
        img = Image.open(photo_path)
        exif = img._getexif() if hasattr(img, '_getexif') else None
        if not exif:
            return None
        gps_info = None
        for tag_id, value in exif.items():
            tag = TAGS.get(tag_id, tag_id)
            if tag == 'GPSInfo':
                gps_info = value
                break
        if not gps_info:
            return None
        gps_data = {}
        for key, val in gps_info.items():
            tag = GPSTAGS.get(key, key)
            gps_data[tag] = val
        if 'GPSLatitude' not in gps_data or 'GPSLongitude' not in gps_data:
            return None
        lat = dms_to_dd(gps_data['GPSLatitude'], gps_data.get('GPSLatitudeRef', 'N'))
        lon = dms_to_dd(gps_data['GPSLongitude'], gps_data.get('GPSLongitudeRef', 'E'))
        return (lat, lon)
    except Exception as e:
        return None

def get_datetime(photo_path):
    """사진 촬영 시각. 없으면 파일 mtime."""
    try:
        from PIL import Image
        from PIL.ExifTags import TAGS
        img = Image.open(photo_path)
        exif = img._getexif() if hasattr(img, '_getexif') else None
        if exif:
            for tag_id, value in exif.items():
                tag = TAGS.get(tag_id, tag_id)
                if tag == 'DateTimeOriginal':
                    return value.replace(':', '-', 2).replace(' ', 'T')
                if tag == 'DateTime':
                    return value.replace(':', '-', 2).replace(' ', 'T')
    except Exception:
        pass
    import os
    from datetime import datetime
    mtime = os.path.getmtime(photo_path)
    return datetime.fromtimestamp(mtime).isoformat(timespec='seconds')

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--photos', required=True, help='사진 폴더 경로')
    parser.add_argument('--session', required=True, help='session.json 경로 (입출력)')
    parser.add_argument('--pattern', default='{*.jpg,*.jpeg,*.JPG,*.JPEG,*.heic,*.HEIC}', help='파일 glob 패턴 (brace 확장)')
    args = parser.parse_args()

    photo_dir = Path(args.photos)
    if not photo_dir.is_dir():
        print(f"ERROR: {photo_dir} 디렉토리 없음", file=sys.stderr)
        sys.exit(1)

    # 파일 수집
    files = []
    for pat in args.pattern.replace('{', '').replace('}', '').split(','):
        files.extend(photo_dir.glob(pat.strip()))
    files = sorted(set(files))
    print(f"발견: {len(files)}개 파일", file=sys.stderr)

    # GPS 추출
    photos = []
    no_gps = []
    for f in files:
        gps = get_gps(f)
        if not gps:
            no_gps.append(f.name)
            continue
        lat, lon = gps
        ts = get_datetime(f)
        photos.append({
            "id": f"photo_{f.stem}",
            "filename": f.name,
            "lat": round(lat, 6),
            "lng": round(lon, 6),
            "timestamp": ts,
        })

    print(f"GPS 있는 사진: {len(photos)}개 / GPS 없음 (제외): {len(no_gps)}개", file=sys.stderr)
    if no_gps:
        print(f"  제외: {no_gps[:5]}{'...' if len(no_gps) > 5 else ''}", file=sys.stderr)

    if photos:
        from collections import Counter
        times = [p['timestamp'][:10] for p in photos if p.get('timestamp')]
        if times:
            print(f"날짜 분포: {Counter(times).most_common(3)}", file=sys.stderr)
        lats = [p['lat'] for p in photos]
        lngs = [p['lng'] for p in photos]
        print(f"좌표 bbox: lat [{min(lats):.4f}, {max(lats):.4f}], lon [{min(lons):.4f}, {max(lons):.4f}]" if False else
              f"좌표 bbox: lat [{min(lats):.4f}, {max(lats):.4f}], lon [{min(lngs):.4f}, {max(lngs):.4f}]", file=sys.stderr)

    # session.json 갱신
    session_path = Path(args.session)
    if session_path.is_file():
        with open(session_path, 'r', encoding='utf-8') as f:
            session = json.load(f)
    else:
        from datetime import datetime
        session = {"session_id": f"imjang_{photo_dir.name}", "created_at": datetime.now().isoformat()}

    session['photos'] = photos
    session['photo_count'] = len(photos)

    with open(session_path, 'w', encoding='utf-8') as f:
        json.dump(session, f, ensure_ascii=False, indent=2)

    print(f"\n✓ {session_path} 갱신: photos={len(photos)}", file=sys.stderr)

if __name__ == '__main__':
    main()
