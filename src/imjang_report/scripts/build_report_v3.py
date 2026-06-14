#!/usr/bin/env python3
"""Build v3 interactive HTML report (안양 임장) - v2 + v3 사용자 피드백 모두 반영.

v2 피드백 12개 + v3 피드백 4개 + 추가 피드백 1개 (진행률 0/3):
1. Streak inline edit (사진 옆에서 바로 후기)
2. 후기 갈무리 (동시 말풍선)
3. 후기 아이콘 초록색
4. MD 추출 (사진 포함, Notion 업로드 가능)
5. 거래가격 기준일자
6. 후기 작성 시 태그 (아파트 카드에 표시)
7. 드롭박스 기본닫힘, 동네총평은 열림
8. Streak/아파트 목록 태그 필터링
9. 진행률 0/3 형식 (후기 입력한 사진 수 / 전체)
"""
import argparse
import json
import os
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

def parse_args():
    parser = argparse.ArgumentParser(description='Build interactive imjang report HTML from session.json')
    parser.add_argument('--session', default=os.environ.get('IMJANG_SESSION', 'session.json'), help='Input session.json path')
    parser.add_argument('--out', default=os.environ.get('IMJANG_REPORT_OUT', 'report.html'), help='Output report.html path')
    return parser.parse_args()

args = parse_args()
session_path = Path(args.session).expanduser().resolve()
out_path = Path(args.out).expanduser().resolve()
if not session_path.is_file():
    raise SystemExit(f'session.json not found: {session_path}')
with session_path.open(encoding='utf-8') as f:
    session = json.load(f)

apartments = session.get('apartments', [])
facilities = session.get('facilities', [])
photos = session.get('photos', [])
news = session.get('news_items', [])
neighborhoods = session.get('neighborhoods', [])

session.setdefault('apartments', apartments)
session.setdefault('facilities', facilities)
session.setdefault('photos', photos)
session.setdefault('news_items', news)
session.setdefault('neighborhoods', neighborhoods)

# Normalize internal placeholders so they never leak into HTML/MD/Notion exports.
for apt in apartments:
    if isinstance(apt, dict):
        data_as_of = str(apt.get('data_as_of') or '').strip().lower()
        if data_as_of in {'', 'unknown', 'none', 'null'}:
            apt['data_as_of'] = None

report_title = session.get('title') or f"{session.get('region', '임장')} 임장 기록"
visit_date = session.get('visit_date') or session.get('date') or ''
region_label = session.get('region') or session.get('region_hint') or ''
data_source = session.get('data_source', {}) if isinstance(session.get('data_source'), dict) else {}
deal_ymd = data_source.get('molit_deal_ymd') or session.get('deal_ymd') or ''
meta_parts = []
if visit_date: meta_parts.append(str(visit_date))
if region_label: meta_parts.append(str(region_label))
meta_parts.append(f"사진 {len(photos)}장")
meta_parts.append(f"단지 {len(apartments)}개")
meta_parts.append(f"시설 {len(facilities)}개")
meta_parts.append(f"뉴스 {len(news)}건")
report_meta = ' | '.join(meta_parts)
md_intro = f"> {report_meta}"
price_basis = f"> 가격 기준: {deal_ymd} (국토교통부 아파트매매 실거래가 API / Kakao Local)" if deal_ymd else "> 가격 기준: 국토교통부 아파트매매 실거래가 API / Kakao Local"
storage_key = 'imjang_report_v3_data_' + ''.join(ch if ch.isalnum() else '_' for ch in (session.get('session_id') or region_label or 'default'))[:60]
session_json = json.dumps(session, ensure_ascii=False)

print(f"=== Report v3 Build ===")
print(f"  session: {session_path}")
print(f"  output:  {out_path}")
print(f"  photos: {len(photos)}, apts: {len(apartments)}, facs: {len(facilities)}, news: {len(news)}")

# === HTML ===
html_content = r'''<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>REPORT_TITLE</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
<style>
  * { box-sizing: border-box; }
  html, body { margin: 0; padding: 0; height: 100%; font-family: 'Apple SD Gothic Neo', 'Malgun Gothic', sans-serif; font-size: 13px; }
  body { display: flex; flex-direction: column; background: #f5f5f5; }
  #header {
    background: linear-gradient(135deg, #2c5f7e 0%, #1a3a4d 100%);
    color: white; padding: 10px 20px;
    display: flex; justify-content: space-between; align-items: center;
    z-index: 1000; flex-shrink: 0;
  }
  #header h1 { margin: 0; font-size: 16px; font-weight: 600; }
  #header .meta { font-size: 11px; opacity: 0.85; }
  #toolbar {
    background: white; padding: 6px 12px; border-bottom: 1px solid #ddd;
    display: flex; gap: 8px; align-items: center; flex-shrink: 0;
  }
  #toolbar button {
    padding: 4px 10px; border: 1px solid #ccc; border-radius: 3px;
    background: white; cursor: pointer; font-size: 12px;
  }
  #toolbar button:hover { background: #e8f4f8; border-color: #2c5f7e; }
  #toolbar button.active { background: #2c5f7e; color: white; border-color: #2c5f7e; }
  #layout-warning {
    display: none; background: #fff8e1; color: #5d4037;
    border-bottom: 1px solid #ffecb3; padding: 6px 12px;
    font-size: 12px; line-height: 1.4; flex-shrink: 0;
  }
  #capture-overlay {
    position: absolute; inset: 0; z-index: 650; pointer-events: none;
    display: none;
  }
  .capture-svg {
    position: absolute; inset: 0; pointer-events: none; overflow: visible;
  }
  .capture-line {
    stroke: #1b5e20; stroke-width: 2.5;  /* 실선 (가시성 ↑) */
    fill: none; opacity: 0.85;
  }
  .capture-arrow {
    fill: #1b5e20; opacity: 1;
  }
  /* 마커 anchor (시작점) - 큰 원 */
  .capture-marker-anchor {
    fill: #1b5e20; stroke: #ffffff; stroke-width: 2;
  }
  /* 말풍선 anchor (끝점) - 사각 + 작은 dot */
  .capture-label-anchor {
    fill: #ffffff; stroke: #1b5e20; stroke-width: 2.5;
  }
  .capture-label-dot {
    fill: #1b5e20;
  }
  .capture-label {
    position: absolute; width: 240px; min-height: 72px;
    background: rgba(240,248,240,0.97); border-left: 4px solid #2e7d32;
    border-radius: 8px; padding: 8px 10px;
    box-shadow: 0 4px 14px rgba(0,0,0,0.22);
    font-size: 11px; line-height: 1.42; color: #1b5e20;
    transition: box-shadow 0.2s, transform 0.1s;
  }
  .capture-label .type-tag {
    display: inline-block; font-size: 9px; padding: 1px 5px;
    border-radius: 3px; background: #2e7d32; color: white;
    margin-right: 4px; font-weight: 600;
  }
  .capture-label .type-tag.photo { background: #2e7d32; }
  .capture-label .type-tag.apt { background: #d35400; }
  .capture-label .type-tag.mark { background: #9c27b0; }
  }
  .capture-label .ts { font-size: 10px; color: #666; margin-bottom: 3px; font-weight: 600; }
  .capture-label .name { font-size: 10px; color: #2c5f7e; margin-bottom: 3px; font-weight: 700; }
  .capture-label .review { white-space: pre-wrap; }
  .capture-label .tags { margin-top: 4px; color: #555; font-size: 10px; }
  #main { flex: 1; display: flex; position: relative; min-height: 0; }
  #streak {
    width: 280px; background: white; border-right: 1px solid #ddd;
    overflow-y: auto; flex-shrink: 0;
  }
  #streak-header { padding: 10px 12px; background: #2c5f7e; color: white; font-size: 12px; font-weight: 600; position: sticky; top: 0; z-index: 10; display: flex; align-items: center; justify-content: space-between; gap: 8px; }
  #streak-close { display: none; background: rgba(255,255,255,0.18); color: white; border: 1px solid rgba(255,255,255,0.35); border-radius: 4px; padding: 2px 7px; font-size: 12px; cursor: pointer; }
  #streak-tag-filter { padding: 6px 8px; background: #f8f9fa; border-bottom: 1px solid #eee; }
  #streak-tag-filter select { width: 100%; padding: 3px 6px; font-size: 10px; border: 1px solid #ccc; border-radius: 3px; }
  #streak-list { padding: 8px; }
  .streak-item {
    background: #fafafa; border: 1px solid #e0e0e0; border-radius: 4px;
    margin-bottom: 6px; overflow: hidden;
  }
  .streak-item.has-review { border-color: #2e7d32; background: #f0f8f0; }
  .streak-item-header {
    display: flex; gap: 6px; padding: 6px;
  }
  .streak-item-header .photo-thumb {
    width: 60px; height: 60px; flex-shrink: 0; border-radius: 3px; overflow: hidden;
  }
  .streak-item-header .photo-thumb img {
    width: 100%; height: 100%; object-fit: cover;
  }
  .streak-item-header .info-area {
    flex: 1; min-width: 0; padding: 4px 6px; border-radius: 3px;
    cursor: pointer; transition: background 0.15s;
    border: 1px dashed transparent;
  }
  .streak-item-header .info-area:hover {
    background: #e8f4f8; border-color: #2c5f7e;
  }
  .streak-item-header .info-area .hint {
    font-size: 9px; color: #999; margin-top: 2px;
  }
  .streak-item-header .info-area:hover .hint {
    color: #2c5f7e; font-weight: 500;
  }
  .streak-item img {
    width: 60px; height: 60px; object-fit: cover; border-radius: 3px; flex-shrink: 0;
  }
  .streak-item .info { flex: 1; min-width: 0; }
  .streak-item .time { font-size: 10px; color: #666; font-weight: 500; }
  .streak-item .progress { font-size: 10px; color: #2e7d32; font-weight: 600; margin-top: 2px; }
  .streak-item .progress.zero { color: #999; font-weight: normal; }
  .streak-item .progress.full { color: #2e7d32; }
  .streak-item .inline-review {
    padding: 6px 8px; background: white; border-top: 1px solid #e0e0e0;
  }
  .streak-item .inline-review textarea {
    width: 100%; min-height: 50px; padding: 4px 6px; border: 1px solid #ccc;
    border-radius: 3px; font-family: inherit; font-size: 11px; resize: vertical;
  }
  .streak-item .inline-review .actions { display: flex; gap: 4px; margin-top: 4px; }
  .streak-item .inline-review button {
    padding: 3px 8px; border: none; border-radius: 3px; cursor: pointer; font-size: 10px;
  }
  .streak-item .inline-review .save { background: #2c5f7e; color: white; }
  .streak-item .inline-review .cancel { background: #ccc; }
  .streak-item .inline-review .delete { background: #d35400; color: white; }
  .streak-item .tags { padding: 4px 8px; background: #f8f9fa; font-size: 10px; }
  .streak-item .tags .tag { background: #e8f4f8; color: #2c5f7e; padding: 1px 5px; border-radius: 2px; margin-right: 3px; display: inline-block; }
  .streak-item .tag-input-row { display: flex; gap: 3px; margin-top: 3px; }
  .streak-item .tag-input-row input { flex: 1; padding: 2px 4px; font-size: 10px; border: 1px solid #ccc; border-radius: 2px; }
  .streak-item .tag-input-row button { padding: 2px 6px; font-size: 10px; background: #2c5f7e; color: white; border: none; border-radius: 2px; cursor: pointer; }
  #map-container { flex: 1; position: relative; }
  #map { width: 100%; height: 100%; background: #e8e8e8; }
  #panel-right {
    width: 360px; background: white; overflow-y: auto; flex-shrink: 0;
    border-left: 1px solid #ddd;
  }
  .panel-header {
    background: #1a3a4d; color: white; padding: 8px 12px;
    cursor: pointer; user-select: none; display: flex; justify-content: space-between;
    align-items: center; font-size: 13px; font-weight: 600;
  }
  .panel-header .arrow { transition: transform 0.2s; }
  .panel-header.collapsed .arrow { transform: rotate(-90deg); }
  .panel-body { padding: 8px 12px; max-height: 60vh; overflow-y: auto; }
  .panel-body.collapsed { display: none; }
  #apt-search-bar { padding: 6px 8px; background: #f8f9fa; border-bottom: 1px solid #eee; display: flex; flex-direction: column; gap: 5px; }
  #apt-search-bar .row { display: flex; gap: 4px; align-items: center; }
  #apt-search-bar input { flex: 1; min-width: 0; padding: 4px 6px; border: 1px solid #ccc; border-radius: 3px; font-size: 11px; }
  #apt-search-bar select { padding: 3px 4px; font-size: 10px; border: 1px solid #ccc; border-radius: 3px; min-width: 0; }
  #apt-search-bar #apt-tag-select { flex: 0 0 112px; }
  #apt-search-bar #apt-sort-select { flex: 1; }
  #apt-search-bar #apt-filter-select { flex: 0 0 102px; }
  .apt-card {
    background: #f8f9fa; border: 1px solid #e0e0e0; border-radius: 4px;
    padding: 8px 10px; margin-bottom: 6px; cursor: pointer; transition: all 0.15s;
    position: relative;
  }
  .apt-card:hover { background: #e8f4f8; border-color: #2c5f7e; }
  .apt-card.has-review { border-left: 3px solid #2e7d32; }
  .apt-card.favorite { border-left: 4px solid #f9a825; background: #fffdf3; box-shadow: 0 0 0 1px rgba(249,168,37,0.35); }
  .apt-card .name { font-weight: 600; font-size: 12px; color: #1a3a4d; }
  .apt-card .badge { background: #d35400; color: white; padding: 1px 5px; border-radius: 3px; font-size: 9px; margin-left: 4px; }
  .apt-card .badge.favorite-badge, .apt-card .tag.favorite-tag { background: #f9a825; color: #1a3a4d; font-weight: 700; }
  .apt-card .conf { position: absolute; top: 6px; right: 6px; font-size: 10px; }
  .apt-card .meta { font-size: 10px; color: #666; margin-top: 2px; }
  .apt-card .price { font-size: 11px; color: #2c5f7e; font-weight: 500; margin-top: 2px; }
  .apt-card .date-info { font-size: 9px; color: #999; margin-top: 1px; }
  .apt-card .tags { margin-top: 4px; }
  .apt-card .tag { background: #e8f4f8; color: #2c5f7e; padding: 1px 5px; border-radius: 2px; font-size: 9px; margin-right: 2px; display: inline-block; }
  .apt-card .review-snippet {
    margin-top: 4px; padding: 4px 6px; background: #f0f8f0;
    border-left: 2px solid #2e7d32; font-size: 10px; color: #1b5e20;
    border-radius: 2px;
  }
  .news-item {
    padding: 8px 0; border-bottom: 1px solid #eee; cursor: pointer; font-size: 11px;
  }
  .news-item:hover { background: #f8f9fa; }
  .news-item .title { color: #1a3a4d; font-weight: 500; line-height: 1.3; }
  .news-item .date { color: #999; font-size: 9px; margin-top: 2px; }
  .news-item .tag { background: #fff3e0; color: #d35400; padding: 1px 4px; border-radius: 2px; font-size: 9px; margin-right: 2px; display: inline-block; }
  .news-item.user { border-left: 2px solid #9c27b0; padding-left: 6px; }
  .news-item .delete-btn { float: right; color: #d35400; cursor: pointer; font-size: 10px; }
  .add-btn {
    width: 100%; padding: 6px; background: #f8f9fa; border: 1px dashed #2c5f7e;
    border-radius: 4px; cursor: pointer; color: #2c5f7e; font-size: 11px;
    margin-top: 6px;
  }
  .add-btn:hover { background: #e8f4f8; }
  #news-tag-filter { margin-bottom: 6px; }
  #news-tag-filter select { width: 100%; padding: 3px 6px; font-size: 10px; border: 1px solid #ccc; border-radius: 3px; }
  .photo-marker {
    background: #ff6b35; border: 2px solid white; border-radius: 50%;
    width: 14px; height: 14px; box-shadow: 0 0 0 1px #333;
  }
  .photo-cluster-marker {
    background: #ff6b35; color: white; border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    font-weight: bold; font-size: 11px; box-shadow: 0 0 0 2px white, 0 0 0 3px #333;
  }
  .photo-cluster-marker.zero { background: #ff6b35; }  /* 0/N: 주황 (기본) */
  .photo-cluster-marker.partial {
    background: #f9a825;  /* M/N (부분): 노란색 */
    color: white;
    font-size: 10px;
    box-shadow: 0 0 0 2px white, 0 0 0 3px #e65100;
  }
  .photo-cluster-marker.has-review.full,
  .photo-cluster-marker.full {
    background: #2e7d32;  /* N/N (전부): 초록 */
    color: white;
    box-shadow: 0 0 0 2px white, 0 0 0 3px #1b5e20;
  }
  /* v3: 후기 있는 사진 마커는 초록색 */
  .photo-marker.has-review { background: #2e7d32; border-color: #ffeb3b; }
  .photo-marker.has-review.full { background: #2e7d32; }
  .apt-marker {
    background: #2c5f7e; color: white; border: 2px solid white;
    border-radius: 4px; padding: 1px 5px; font-size: 10px; font-weight: 600;
    box-shadow: 0 2px 4px rgba(0,0,0,0.3); white-space: nowrap;
  }
  .apt-marker.daejang { background: #d35400; color:white; border-color:#fff; border-width:3px; font-size:13px; transform: scale(1.18); box-shadow: 0 0 0 2px #6d2c00, 0 0 12px rgba(211,84,0,0.9); z-index: 910 !important; }
  .apt-marker.favorite { background: #f9a825; color: #1a3a4d; border-color: #fff; border-width: 3px; font-size: 13px; transform: scale(1.18); box-shadow: 0 0 0 2px #1a3a4d, 0 0 12px rgba(249,168,37,0.9); z-index: 900 !important; }
  .apt-marker.favorite.daejang { background: linear-gradient(135deg, #f9a825 0%, #d35400 100%); color: white; }
  /* v3: 후기 있는 아파트 마커도 초록색 */
  .apt-marker.has-review { background: #2e7d32; border-color: #ffeb3b; border-width: 3px; }
  .apt-fav-btn { background:#fff7d6; color:#1a3a4d; padding:3px 6px; border-radius:3px; font-size:10px; border:1px solid #f9a825; cursor:pointer; font-weight:700; }
  .apt-fav-btn.active { background:#f9a825; color:#1a3a4d; }
  .apt-leader-btn { background:#fff0e2; color:#5d2600; padding:3px 6px; border-radius:3px; font-size:10px; border:1px solid #d35400; cursor:pointer; font-weight:700; }
  .apt-leader-btn.active { background:#d35400; color:white; }
  .fac-marker {
    background: white; border: 2px solid #2c5f7e; border-radius: 50%;
    width: 22px; height: 22px; display: flex; align-items: center; justify-content: center;
    font-size: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.2);
  }
  .user-mark {
    background: #9c27b0; color: white; border: 2px solid white;
    border-radius: 50%; width: 22px; height: 22px; display: flex;
    align-items: center; justify-content: center; font-size: 12px;
    box-shadow: 0 2px 4px rgba(0,0,0,0.3); cursor: pointer;
  }
  /* modals */
  .review-modal, .add-news-modal, .user-mark-modal, .photo-modal {
    display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%;
    background: rgba(0,0,0,0.6); z-index: 10000;
    justify-content: center; align-items: center;
  }
  .review-modal.show, .add-news-modal.show, .user-mark-modal.show, .photo-modal.show { display: flex; }
  .modal-content {
    background: white; padding: 20px; border-radius: 8px;
    width: 90%; max-width: 600px; max-height: 85vh; overflow-y: auto;
  }
  .modal-content h3 { margin: 0 0 12px 0; color: #1a3a4d; }
  .modal-content textarea, .modal-content input[type=text], .modal-content input[type=url] {
    width: 100%; min-height: 80px; padding: 8px; margin-bottom: 8px;
    border: 1px solid #ccc; border-radius: 4px; font-family: inherit; font-size: 13px;
  }
  .modal-content .actions { display: flex; gap: 8px; justify-content: flex-end; margin-top: 12px; }
  .modal-content button {
    padding: 6px 14px; border: none; border-radius: 4px; cursor: pointer; font-size: 13px;
  }
  .modal-content .save { background: #2c5f7e; color: white; }
  .modal-content .cancel { background: #ccc; color: #333; }
  .modal-content .delete { background: #d35400; color: white; }
  .photo-modal .modal-content { max-width: 900px; padding: 12px; }
  .photo-modal img { width: 100%; max-height: 70vh; object-fit: contain; border-radius: 4px; }
  .photo-modal .ts { color: #666; font-size: 12px; margin-top: 8px; text-align: center; }
  .photo-modal .review-area { margin-top: 12px; padding: 8px; background: #f8f9fa; border-radius: 4px; }
  .nb-review-section { padding: 8px 12px; }
  .nb-review-section h3 { margin: 0 0 8px 0; font-size: 12px; color: #1a3a4d; }
  .nb-review-section .field { margin-bottom: 8px; }
  .nb-review-section label { display: block; font-size: 10px; color: #666; margin-bottom: 2px; }
  .nb-review-section input, .nb-review-section textarea {
    width: 100%; padding: 4px 6px; border: 1px solid #ccc; border-radius: 3px; font-size: 11px;
    font-family: inherit;
  }
  .nb-review-section textarea { min-height: 50px; resize: vertical; }
  /* v3: 후기 갈무리 말풍선 (popup) 스타일 */
  .capture-balloon {
    min-width: 280px; max-width: 320px;
    background: #f0f8f0; border-left: 4px solid #2e7d32;
    padding: 8px 10px; border-radius: 4px;
  }
  .capture-balloon .ts { font-size: 10px; color: #666; margin-bottom: 4px; font-weight: 500; }
  .capture-balloon .review { font-size: 11px; color: #1b5e20; line-height: 1.4; white-space: pre-wrap; }
  .capture-balloon .apt-name { font-size: 10px; color: #2c5f7e; margin-bottom: 2px; font-weight: 500; }
  /* v3: 진행률 badge */
  .progress-badge {
    display: inline-block; padding: 1px 5px; border-radius: 8px;
    font-size: 9px; font-weight: 600; background: #e0e0e0; color: #666;
  }
  .progress-badge.zero { background: #f5f5f5; color: #999; }
  .progress-badge.partial { background: #fff3e0; color: #e65100; }
  .progress-badge.full { background: #c8e6c9; color: #1b5e20; }
  #save-status {
    position: fixed; bottom: 20px; right: 20px;
    background: rgba(0,0,0,0.85); color: white; padding: 8px 14px;
    border-radius: 4px; font-size: 12px; z-index: 9999;
    opacity: 0; transition: opacity 0.3s;
  }
  #save-status.show { opacity: 1; }
  .legend {
    position: absolute; bottom: 12px; left: 12px; background: white;
    padding: 6px 10px; border-radius: 4px; font-size: 10px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.2); z-index: 500; line-height: 1.6;
  }
  .legend-item { display: flex; align-items: center; gap: 4px; }
  .legend-marker { width: 12px; height: 12px; border-radius: 50%; }
  #btn-streak-drawer {
    display: none;
    background: #fffef7;
    color: #1f3b4d;
    border: 1px solid #2c5f7e;
    font-weight: 700;
  }
  #streak-backdrop { display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.28); z-index: 1190; }
  @media (max-width: 1100px) {
    #btn-streak-drawer { display: inline-block; background: #fffef7; color: #1f3b4d; }
    #streak {
      display: block; position: fixed; top: 0; bottom: 0; left: 0;
      width: min(88vw, 360px); max-width: 360px; z-index: 1200;
      box-shadow: 3px 0 12px rgba(0,0,0,0.28);
      transform: translateX(-105%); transition: transform 0.22s ease;
      border-right: none;
    }
    body.streak-drawer-open #streak { transform: translateX(0); }
    body.streak-drawer-open #streak-backdrop { display: block; }
    #streak-close { display: inline-block; }
    #layout-warning { display: block; }
  }
  @media (max-width: 768px) {
    #main { flex-direction: column; }
    #panel-right { width: 100%; border-left: none; border-top: 1px solid #ddd; }
  }
</style>
</head>
<body>
<div id="header">
  <div>
    <h1>🏠 REPORT_TITLE</h1>
    <div class="meta">REPORT_META</div>
  </div>
  <div class="meta">💾 자동 저장 (localStorage) | 📅 가격 기준: 2026-05-31</div>
</div>

<div id="toolbar">
  <button onclick="openStreakDrawer()" id="btn-streak-drawer">📷 Streak 열기</button>
  <button onclick="captureMode()" id="btn-capture">📸 후기 갈무리 (말풍선 동시)</button>
  <button onclick="toggleAddMark()" id="btn-add-mark">📍 마크 추가</button>
  <button onclick="exportSession()">💾 JSON 백업</button>
  <button onclick="exportMarkdown()">📝 MD 추출</button>
  <button onclick="openNotionExportModal()" id="btn-notion-export">📦 Notion ZIP 생성</button>
  <button onclick="resetMapView()">🗺️ 전체 보기</button>
  <span style="flex:1"></span>
  <span style="font-size: 11px; color: #666;">ⓘ 🟢=후기있음 ★=관심단지 👑=대장아파트</span>
</div>

<div id="layout-warning">ℹ️ 현재 창 너비에서는 Streak가 drawer 메뉴로 전환됩니다. 상단의 <b>📷 Streak 열기</b> 버튼을 누르면 시간순 사진/후기 패널을 볼 수 있습니다.</div>

<div id="streak-backdrop" onclick="closeStreakDrawer()"></div>

<div id="main">
  <div id="streak">
    <div id="streak-header"><span>📷 Streak — 시간순 사진</span><button id="streak-close" onclick="closeStreakDrawer()">닫기 ✕</button></div>
    <div id="streak-tag-filter"><select id="streak-tag-select" onchange="renderStreak()"><option value="all">전체 사진</option></select></div>
    <div id="streak-list"></div>
  </div>
  <div id="map-container">
    <div id="map"></div>
    <div id="capture-overlay"></div>
    <div class="legend">
      <div class="legend-item"><div class="legend-marker" style="background: #ff6b35;"></div>사진 (0/N)</div>
      <div class="legend-item"><div class="legend-marker" style="background: #2e7d32;"></div>후기 있는 사진 (M/N)</div>
      <div class="legend-item"><div class="legend-marker" style="background: #2c5f7e;"></div>아파트</div>
      <div class="legend-item"><div class="legend-marker" style="background: #d35400;"></div>대장아파트</div>
      <div class="legend-item"><div class="legend-marker" style="background: #2e7d32;"></div>후기 아파트</div>
      <div class="legend-item"><div class="legend-marker" style="background: #9c27b0;"></div>사용자 마크</div>
    </div>
  </div>
  <div id="panel-right">
    <div class="panel-header collapsed" onclick="togglePanel('apt')" id="apt-header">
      <span>🏢 아파트 목록 (APTS_COUNT개) <span id="apt-progress-summary" class="progress-badge zero">0/0</span></span>
      <span class="arrow">▼</span>
    </div>
    <div class="panel-body collapsed" id="apt-body">
      <div id="apt-search-bar">
        <div class="row">
          <input type="text" id="apt-search" placeholder="단지명 검색...">
          <select id="apt-filter-select" onchange="renderAptList()">
            <option value="all">전체</option>
            <option value="favorite">★ 관심단지</option>
            <option value="priced">가격 있음</option>
            <option value="unpriced">가격 없음</option>
            <option value="reviewed">후기 있음</option>
            <option value="leader">👑 대장아파트</option>
          </select>
        </div>
        <div class="row">
          <select id="apt-tag-select"><option value="all">전체 태그</option></select>
          <select id="apt-sort-select" onchange="renderAptList()">
            <option value="favorite-default">관심단지 우선 + 이름순</option>
            <option value="name-asc">이름 오름차순</option>
            <option value="name-desc">이름 내림차순</option>
            <option value="distance-asc">동선거리 가까운순</option>
            <option value="distance-desc">동선거리 먼순</option>
            <option value="price-desc">가격 높은순</option>
            <option value="price-asc">가격 낮은순</option>
            <option value="built-desc">준공 최신순</option>
            <option value="built-asc">준공 오래된순</option>
            <option value="trade-desc">거래량 많은순</option>
            <option value="trade-asc">거래량 적은순</option>
          </select>
        </div>
      </div>
      <div id="apt-list"></div>
    </div>
    <div class="panel-header collapsed" onclick="togglePanel('news')" id="news-header">
      <span>📰 호재/뉴스 (NEWS_COUNT건 + 사용자)</span>
      <span class="arrow">▼</span>
    </div>
    <div class="panel-body collapsed" id="news-body">
      <div id="news-tag-filter"></div>
      <div id="news-list"></div>
      <button class="add-btn" onclick="openAddNewsModal()">➕ 뉴스 추가</button>
    </div>
    <div class="panel-header" onclick="togglePanel('review')" id="review-header">
      <span>🏘️ 동네 총평 (한줄평) <span id="nb-review-status" class="progress-badge zero">미입력</span></span>
      <span class="arrow">▼</span>
    </div>
    <div class="panel-body" id="review-body">
      <div class="nb-review-section">
        <h3>전체 한줄평</h3>
        <div class="field"><textarea id="nb-overall" placeholder="동네 전체 인상 한줄로..."></textarea></div>
        <h3>세부 항목</h3>
        <div class="field"><label>분위기</label><input type="text" id="nb-atmosphere" placeholder="여유로움 / 분주함 / ..."></div>
        <div class="field"><label>상권</label><input type="text" id="nb-commerce" placeholder="상권 활발 / 음식점 다양 / ..."></div>
        <div class="field"><label>교통</label><input type="text" id="nb-transit" placeholder="지하철 접근성 / 버스 / ..."></div>
        <div class="field"><label>도보</label><input type="text" id="nb-walkability" placeholder="보도 상태 / 경사로 / ..."></div>
        <div class="field"><label>5년후 전망</label><input type="text" id="nb-future" placeholder="재개발/호재/지속가능 / ..."></div>
        <button class="save" style="background:#2c5f7e;color:white;width:100%;padding:8px;border:none;border-radius:4px;cursor:pointer;font-size:12px;" onclick="saveNeighborhoodReview()">💾 한줄평 저장</button>
      </div>
    </div>
  </div>
</div>

<div id="review-modal" class="review-modal">
  <div class="modal-content">
    <h3 id="review-title">후기 기록</h3>
    <textarea id="review-text" placeholder="임장 후기를 자유롭게 적어주세요..."></textarea>
    <div class="field">
      <label style="font-size:11px;color:#666;">태그 (Enter로 추가, 쉼표 구분)</label>
      <input type="text" id="review-tag-input" placeholder="예: 가족여행, 주차넓음, 학원가...">
    </div>
    <div id="review-tag-display" style="margin-bottom:8px;"></div>
    <div class="actions">
      <button class="delete" id="review-delete-btn" onclick="deleteReview()">🗑️ 삭제</button>
      <button class="cancel" onclick="closeReviewModal()">취소</button>
      <button class="save" onclick="saveReview()">💾 저장</button>
    </div>
  </div>
</div>

<div id="add-news-modal" class="add-news-modal">
  <div class="modal-content">
    <h3>뉴스/호재 추가</h3>
    <input type="text" id="news-title" placeholder="기사 제목">
    <input type="url" id="news-url" placeholder="https://...">
    <input type="text" id="news-summary" placeholder="요약 (선택)">
    <div class="actions">
      <button class="cancel" onclick="closeAddNewsModal()">취소</button>
      <button class="save" onclick="saveNewNews()">추가</button>
    </div>
  </div>
</div>

<div id="user-mark-modal" class="user-mark-modal">
  <div class="modal-content">
    <h3>사용자 마크 추가</h3>
    <p style="color:#666;font-size:11px;">툴바의 📍 마크 추가 후 지도 클릭, 또는 지도 우클릭/터치 길게 누르기로 위치를 지정하세요.</p>
    <input type="text" id="mark-name" placeholder="마크 이름 (예: GS25 평촌점)">
    <select id="mark-type" style="width:100%;padding:6px;margin-bottom:8px;border:1px solid #ccc;border-radius:4px;">
      <option value="📍">📍 일반</option>
      <option value="🏪">🏪 가게/상가</option>
      <option value="🍽️">🍽️ 맛집</option>
      <option value="🏫">🏫 학원/학교</option>
      <option value="🌳">🌳 공원</option>
      <option value="🚇">🚇 역/교통</option>
      <option value="🏢">🏢 단지/건물</option>
      <option value="⚠️">⚠️ 단점/주의</option>
    </select>
    <textarea id="mark-note" placeholder="메모 (선택)"></textarea>
    <div class="actions">
      <button class="cancel" onclick="closeUserMarkModal()">취소</button>
      <button class="save" onclick="saveUserMark()">마크 추가</button>
    </div>
  </div>
</div>

<div id="photo-modal" class="photo-modal">
  <div class="modal-content">
    <button style="float:right;background:none;border:none;font-size:18px;cursor:pointer;" onclick="closePhotoModal()">✕</button>
    <h3 id="photo-modal-title">사진</h3>
    <img id="photo-modal-img" src="" alt="">
    <div class="ts" id="photo-modal-ts"></div>
    <div class="review-area">
      <strong style="font-size:12px;">📝 후기</strong>
      <div id="photo-modal-review" style="margin-top:4px;font-size:12px;color:#1b5e20;"></div>
      <button style="margin-top:6px;padding:5px 10px;background:#2c5f7e;color:white;border:none;border-radius:3px;cursor:pointer;font-size:11px;" onclick="editCurrentPhotoReview()">📝 후기 작성/수정</button>
    </div>
  </div>
</div>

<!-- Notion ZIP Export Modal -->
<div id="notion-export-modal" class="add-news-modal">
  <div class="modal-content" style="max-width:560px;">
    <h3>📦 Notion Import용 ZIP 생성</h3>
    <p style="font-size:11px;color:#666;margin:0 0 8px 0;line-height:1.55;">
      Notion API/CORS를 우회하기 위해 <strong>imjang_report.md + images/</strong>를 ZIP으로 묶어 다운로드합니다.<br>
      Notion에서 <strong>Settings → Import → Text & Markdown</strong>으로 ZIP을 올리면 이미지가 Notion에 함께 임포트됩니다.<br>
      <strong style="color:#c0392b;">중요:</strong> 폴더 선택창은 ZIP을 저장할 위치를 고르는 창이 아닙니다. 브라우저가 사진을 읽기 위해 사용자 허락을 받는 단계입니다.
    </p>
    <div id="notion-photo-folder-hint" style="margin:8px 0;padding:8px;background:#fff7d6;border:1px solid #f9a825;border-radius:4px;font-size:11px;color:#1a3a4d;line-height:1.45;"></div>
    <label style="font-size:11px;color:#666;display:block;margin-bottom:6px;">
      <input type="checkbox" id="notion-zip-all-photos">
      전체 사진 포함 (기본: MD 추출과 동일하게 실제 후기 문구가 입력된 사진만 포함)
    </label>
    <div id="notion-progress" style="margin-top:8px;padding:6px;background:#f8f9fa;border-radius:3px;font-size:11px;display:none;"></div>
    <div class="actions">
      <button class="cancel" onclick="closeNotionExportModal()">취소</button>
      <button class="save" onclick="startNotionZipExport()">📁 사진 폴더 확인 후 ZIP 생성</button>
    </div>
  </div>
</div>

<div id="save-status"></div>

<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/jszip/3.10.1/jszip.min.js"></script>
<script>
const SESSION = SESSION_PLACEHOLDER;
</script>
<script>
const map = L.map('map').setView([37.394, 126.945], 13);
L.tileLayer('https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png', {
  attribution: '© OpenStreetMap, © CARTO',
  maxZoom: 19,
  subdomains: 'abcd',
}).addTo(map);

const STORAGE_KEY = 'STORAGE_KEY_PLACEHOLDER';
let storage = {
  reviews: {},         // targetId -> {text, tags[]}
  review_tags_map: {}, // tagName -> targetId[]
  favorite_apartments: [], // apartment id[] — 관심단지
  leader_apartments: [],   // apartment id[] — 사용자가 직접 체크한 대장아파트
  hidden_apartments: [],   // apartment id[] — 실제 지도와 맞지 않아 사용자가 지도에서 삭제한 단지
  user_news: [],
  user_marks: [],
  neighborhood_review: { overall: '', prompts: {} }
};
// v3: review data shape changed. Migration: convert old string reviews to {text: s, tags: []}
function migrateReviews(oldReviews) {
  const out = {};
  Object.keys(oldReviews).forEach(function(k) {
    const v = oldReviews[k];
    if (typeof v === 'string') {
      out[k] = { text: v, tags: [] };
    } else {
      out[k] = v;
    }
  });
  return out;
}
let currentReviewTarget = null;
let currentPhotoReviewTarget = null;
let addMarkMode = false;
let pendingMarkLatLng = null;

function loadStorage() {
  try {
    // 1) v3 키 먼저
    let data = localStorage.getItem(STORAGE_KEY);
    if (!data) {
      // 2) v2 키 마이그레이션 (한 번만)
      data = localStorage.getItem('anyang_imjang_v2_data');
      if (data) {
        const v2 = JSON.parse(data);
        // v2 reviews는 string, v3는 {text, tags}
        if (v2.reviews) v2.reviews = migrateReviews(v2.reviews);
        // user_news/marks/review 그대로 이전
        storage = Object.assign({}, storage, v2);
        // v3 키로 저장 + v2 키 삭제
        localStorage.setItem(STORAGE_KEY, JSON.stringify(storage));
        localStorage.removeItem('anyang_imjang_v2_data');
        console.log('✓ v2 → v3 마이그레이션 완료');
      } else {
        // 3) v1 키 마이그레이션 (anyang_imjang_data, v1 indexedDB 없음 = localStorage)
        data = localStorage.getItem('anyang_imjang_data');
        if (data) {
          const v1 = JSON.parse(data);
          if (v1.reviews) v1.reviews = migrateReviews(v1.reviews);
          storage = Object.assign({}, storage, v1);
          localStorage.setItem(STORAGE_KEY, JSON.stringify(storage));
          localStorage.removeItem('anyang_imjang_data');
          console.log('✓ v1 → v3 마이그레이션 완료');
        }
      }
    }
    if (data) {
      const parsed = JSON.parse(data);
      if (parsed.reviews) parsed.reviews = migrateReviews(parsed.reviews);
      storage = Object.assign(storage, parsed);
    }
  } catch (e) { console.error('loadStorage failed', e); }
}
function saveStorage() {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(storage));
    showSaveStatus('💾 자동 저장됨');
  } catch (e) { console.error('saveStorage failed', e); }
}
function showSaveStatus(msg) {
  const el = document.getElementById('save-status');
  el.textContent = msg;
  el.classList.add('show');
  setTimeout(function() { el.classList.remove('show'); }, 2000);
}
loadStorage();

// === Helpers ===
function escapeHtml(s) {
  if (!s) return '';
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}
function escapeJs(s) {
  if (!s) return '';
  return String(s).replace(/'/g, "\\'").replace(/"/g, '\\"');
}
function getReviewText(targetId) {
  const r = storage.reviews[targetId];
  if (!r) return null;
  const text = String(r.text || '').trim();
  return text ? text : null;
}
function getReviewTags(targetId) {
  const r = storage.reviews[targetId];
  if (!r) return [];
  return r.tags || [];
}
function photoMarkdownUrl(p) {
  const rel = 'assets/photos/' + encodeURIComponent(p.filename).replace(/%2F/g, '/');
  try { return new URL(rel, window.location.href).href; }
  catch (e) { return rel; }
}
function appendNeighborhoodReviewMarkdown(lines) {
  const nr = storage.neighborhood_review || {};
  const prompts = nr.prompts || {};
  const labels = { atmosphere: '분위기', commerce: '상권', transit: '교통', walkability: '도보', future: '5년후 전망' };
  lines.push('## 🏘️ 동네 총평');
  lines.push('');
  lines.push('### 한줄평');
  lines.push('> ' + (nr.overall || ''));
  lines.push('');
  lines.push('### 세부 항목');
  Object.keys(labels).forEach(function(k) {
    lines.push('- **' + labels[k] + '**: ' + (prompts[k] || ''));
  });
  lines.push('');
}
function getReviewBadge(targetId) {
  return getReviewText(targetId) ? ' <span style="background:#2e7d32;color:white;padding:1px 4px;border-radius:2px;font-size:9px;">📝</span>' : '';
}
function ensureFavoriteArray() {
  if (!Array.isArray(storage.favorite_apartments)) storage.favorite_apartments = [];
}
function isFavoriteApt(aptId) {
  ensureFavoriteArray();
  return storage.favorite_apartments.indexOf(aptId) >= 0;
}
function toggleFavoriteApt(aptId, ev) {
  if (ev) { ev.preventDefault(); ev.stopPropagation(); }
  ensureFavoriteArray();
  const idx = storage.favorite_apartments.indexOf(aptId);
  if (idx >= 0) {
    storage.favorite_apartments.splice(idx, 1);
    showSaveStatus('☆ 관심단지 해제');
  } else {
    storage.favorite_apartments.push(aptId);
    showSaveStatus('★ 관심단지 저장');
  }
  saveStorage();
  refreshAptMarkers();
  renderAptTagFilter();
  renderAptList();
  refreshOpenAptPopup(aptId);
}
function ensureLeaderArray() {
  if (!Array.isArray(storage.leader_apartments)) storage.leader_apartments = [];
}
function isLeaderApt(aptId) {
  ensureLeaderArray();
  return storage.leader_apartments.indexOf(aptId) >= 0;
}
function ensureHiddenAptArray() {
  if (!Array.isArray(storage.hidden_apartments)) storage.hidden_apartments = [];
}
function isHiddenApt(aptId) {
  ensureHiddenAptArray();
  return storage.hidden_apartments.indexOf(aptId) >= 0;
}
function hideMismatchedApt(aptId, aptName, ev) {
  if (ev) { ev.preventDefault(); ev.stopPropagation(); }
  const msg = '현재 사용하는 지도API(카카오 등) 상 잘못된 데이터가 입력된 것 같습니다.\n\n' +
    '기록의 정확함을 위해 해당 아이콘을 지도에서 삭제할 수도 있습니다.\n\n' +
    '삭제하시겠습니까?\n\n' +
    '(삭제한 경우 다시 임장기록 스크립트를 재실행하지 않는 한 다시 복구되지 않습니다.)';
  if (!confirm(msg)) return;
  ensureHiddenAptArray();
  if (storage.hidden_apartments.indexOf(aptId) < 0) storage.hidden_apartments.push(aptId);
  saveStorage();
  const marker = aptMarkers[aptId];
  if (marker) {
    if (marker.closePopup) marker.closePopup();
    map.removeLayer(marker);
    delete aptMarkers[aptId];
  }
  renderAptTagFilter();
  renderAptList();
  showSaveStatus('🗺️ 지도와 맞지 않는 단지를 삭제했습니다: ' + (aptName || aptId));
}
function toggleLeaderApt(aptId, ev) {
  if (ev) { ev.preventDefault(); ev.stopPropagation(); }
  ensureLeaderArray();
  const idx = storage.leader_apartments.indexOf(aptId);
  if (idx >= 0) {
    storage.leader_apartments.splice(idx, 1);
    showSaveStatus('👑 대장아파트 해제');
  } else {
    storage.leader_apartments.push(aptId);
    showSaveStatus('👑 대장아파트 저장');
  }
  saveStorage();
  refreshAptMarkers();
  renderAptTagFilter();
  renderAptList();
  refreshOpenAptPopup(aptId);
}

// === Markers ===
function photoIcon(reviewedCount, clusterSize) {
  // 3-state 아이콘: 0/N, M/N, N/N
  const total = clusterSize || 1;
  const reviewed = reviewedCount || 0;
  const ratio = reviewed / total;
  if (total > 1) {
    // 다중 사진 클러스터
    let cls = 'photo-cluster-marker';
    let html = '';
    if (reviewed === 0) {
      cls += ' zero';
      html = String(total);
    } else if (reviewed === total) {
      cls += ' has-review full';
      html = '✓' + total;
    } else {
      cls += ' partial';
      html = reviewed + '/' + total;
    }
    return L.divIcon({
      className: cls,
      html: html,
      iconSize: [32, 32]
    });
  }
  // 단일 사진
  if (reviewed === 0) {
    return L.divIcon({ className: 'photo-marker', iconSize: [14, 14] });
  } else {
    return L.divIcon({ className: 'photo-marker has-review full', iconSize: [14, 14] });
  }
}
function aptIcon(isDaejang, hasReview, reviewedCount, totalCount, isFavorite) {
  // 아파트도 동일하게 3-state (단, 다중 후기 항목이므로 보통 0/1, 1/1)
  let cls = 'apt-marker' + (isDaejang ? ' daejang' : '') + (hasReview ? ' has-review' : '') + (isFavorite ? ' favorite' : '');
  if (reviewedCount !== undefined && totalCount !== undefined && totalCount > 1) {
    if (reviewedCount === totalCount) cls += ' full';
    else if (reviewedCount > 0) cls += ' partial';
  }
  let html = isDaejang ? '👑' : (isFavorite ? '★' : '🏢');
  // 아파트는 1개라 M/N 표기 생략
  return L.divIcon({
    className: cls,
    html: html,
    iconSize: [28, 28],
    iconAnchor: [14, 14]
  });
}
function facIcon(type) {
  const icons = { subway: '🚇', mart: '🛒', department: '🏬', school: '🏫', hagwon: '📚', park: '🌳', hospital: '🏥' };
  return L.divIcon({
    className: 'fac-marker',
    html: icons[type] || '📍',
    iconSize: [22, 22],
    iconAnchor: [11, 11]
  });
}
function userMarkIcon(emoji) {
  return L.divIcon({
    className: 'user-mark',
    html: emoji || '📍',
    iconSize: [22, 22],
    iconAnchor: [11, 11]
  });
}

// === Apartment markers ===
const aptMarkers = {};
function naverLandLinkForApt(a) {
  const query = encodeURIComponent(a.name || '');
  const lat = Number(a.lat);
  const lng = Number(a.lng);
  if (Number.isFinite(lat) && Number.isFinite(lng)) {
    return 'https://new.land.naver.com/search?ms=' + lat.toFixed(6) + ',' + lng.toFixed(6) + ',17&a=APT&b=A1&e=RETAIL&query=' + query;
  }
  // Backward-compatible fallback for old session.json files without coordinates.
  if (a.naver_link && a.naver_link.indexOf('new.land.naver.com') >= 0 && a.naver_link.indexOf('37.394,126.956') < 0) return a.naver_link;
  return 'https://new.land.naver.com/search?a=APT&b=A1&e=RETAIL&query=' + query;
}
function cleanDataAsOf(value) {
  const v = String(value || '').trim();
  if (!v || v.toLowerCase() === 'unknown' || v.toLowerCase() === 'none' || v.toLowerCase() === 'null') return '';
  return v;
}
function formatDealDateInfo(a, label) {
  if (!a.latest_deal_date) return '';
  const dataAsOf = cleanDataAsOf(a.data_as_of);
  return label + ': ' + a.latest_deal_date + (dataAsOf ? ' (data: ' + dataAsOf + ')' : '');
}
function renderAptPopup(a) {
  const reviewBadge = getReviewBadge(a.id);
  const fav = isFavoriteApt(a.id);
  const leader = isLeaderApt(a.id);
  let tagsHtml = '';
  const aptTags = a.tags || [];
  const userTags = getReviewTags(a.id);
  const allTags = (fav ? ['관심단지'] : []).concat(leader ? ['대장아파트'] : []).concat(aptTags).concat(userTags);
  if (allTags.length) {
    tagsHtml = allTags.map(function(t) {
      return '<span class="tag' + (t === '관심단지' ? ' favorite-tag' : '') + '">#' + escapeHtml(t) + '</span>';
    }).join('');
  }
  return '<div style="min-width: 280px;">' +
    '<div style="display:flex;gap:6px;align-items:flex-start;justify-content:space-between;">' +
      '<div style="font-weight:600;font-size:13px;color:#1a3a4d;line-height:1.35;">' + escapeHtml(a.name) +
    (leader ? ' <span style="background:#d35400;color:white;padding:1px 5px;border-radius:3px;font-size:9px;">👑 대장</span>' : '') +
    (fav ? ' <span style="background:#f9a825;color:#1a3a4d;padding:1px 5px;border-radius:3px;font-size:9px;font-weight:700;">★ 관심</span>' : '') +
    reviewBadge + '</div>' +
      '<button onclick="hideMismatchedApt(\'' + a.id + '\', \'' + escapeJs(a.name) + '\', event)" title="실제 지도와 맞지 않는 단지를 지도에서 삭제" style="flex-shrink:0;background:#fff3e0;color:#c0392b;border:1px solid #e67e22;border-radius:3px;padding:2px 5px;font-size:9px;cursor:pointer;line-height:1.25;">실제 지도와<br>맞지 않습니다</button>' +
    '</div>' +
    '<div style="font-size:10px;color:#666;margin-top:2px;">' + escapeHtml(a.address) + '</div>' +
    (a.built_year ? '<div style="font-size:11px;margin-top:3px;">준공: ' + a.built_year + '년</div>' : '') +
    (a.recent_trade_price ? '<div style="font-size:11px;color:#2c5f7e;font-weight:500;">중위 매매: ' + escapeHtml(a.recent_trade_price) + '</div>' : '<div style="font-size:11px;color:#999;">국토교통부 아파트매매 실거래가 API로 조회되지 않음</div>') +
    (a.jeonse_price ? '<div style="font-size:11px;color:#666;">중위 전세: ' + escapeHtml(a.jeonse_price) + '</div>' : '') +
    (a.latest_deal_date ? '<div style="font-size:9px;color:#999;margin-top:2px;">📅 ' + escapeHtml(formatDealDateInfo(a, '기준일')) + '</div>' : '') +
    (tagsHtml ? '<div class="tags" style="margin-top:4px;">' + tagsHtml + '</div>' : '') +
    '<div style="margin-top:6px;display:flex;gap:3px;flex-wrap:wrap;">' +
      '<button class="apt-fav-btn' + (fav ? ' active' : '') + '" onclick="toggleFavoriteApt(\'' + a.id + '\', event)">★ 관심단지</button>' +
      '<button class="apt-leader-btn' + (leader ? ' active' : '') + '" onclick="toggleLeaderApt(\'' + a.id + '\', event)">👑 대장아파트</button>' +
      '<a href="' + escapeHtml(naverLandLinkForApt(a)) + '" target="_blank" rel="noopener" style="background:#03c75a;color:white;padding:3px 6px;border-radius:3px;font-size:10px;text-decoration:none;">네이버부동산</a>' +
      '<a href="' + escapeHtml(a.kakao_map_link) + '" target="_blank" style="background:#ffe600;color:#000;padding:3px 6px;border-radius:3px;font-size:10px;text-decoration:none;">카카오맵</a>' +
      '<a href="' + escapeHtml(a.google_maps_link || '#') + '" target="_blank" style="background:#4285f4;color:white;padding:3px 6px;border-radius:3px;font-size:10px;text-decoration:none;">구글맵</a>' +
      '<button onclick="openReviewModal(\'' + a.id + '\', \'apartment\', \'' + escapeJs(a.name) + '\')" style="background:#2c5f7e;color:white;padding:3px 6px;border-radius:3px;font-size:10px;border:none;cursor:pointer;">📝 후기</button>' +
    '</div>' +
  '</div>';
}
function refreshOpenAptPopup(aptId) {
  const marker = aptMarkers[aptId];
  if (!marker || !marker.isPopupOpen || !marker.isPopupOpen()) return;
  const apt = SESSION.apartments.find(function(x) { return x.id === aptId; });
  if (!apt) return;
  const content = renderAptPopup(apt);
  if (marker.getPopup && marker.getPopup()) marker.getPopup().setContent(content);
  else marker.bindPopup(content, { maxWidth: 380 });
}
function refreshAptMarkers() {
  SESSION.apartments.forEach(function(a) {
    const marker = aptMarkers[a.id];
    if (isHiddenApt(a.id)) {
      if (marker) {
        if (marker.closePopup) marker.closePopup();
        map.removeLayer(marker);
        delete aptMarkers[a.id];
      }
      return;
    }
    if (!marker) return;
    const hasReview = !!getReviewText(a.id);
    marker.setIcon(aptIcon(isLeaderApt(a.id), hasReview, undefined, undefined, isFavoriteApt(a.id)));
    const popupHtml = renderAptPopup(a);
    if (marker.isPopupOpen && marker.isPopupOpen() && marker.getPopup && marker.getPopup()) {
      marker.getPopup().setContent(popupHtml);
    } else {
      marker.bindPopup(popupHtml, { maxWidth: 380 });
    }
  });
}
SESSION.apartments.forEach(function(a) {
  if (a.lat && a.lng && !isHiddenApt(a.id)) {
    const hasReview = !!getReviewText(a.id);
    const marker = L.marker([a.lat, a.lng], { icon: aptIcon(isLeaderApt(a.id), hasReview, undefined, undefined, isFavoriteApt(a.id)) }).addTo(map);
    marker.bindPopup(renderAptPopup(a), { maxWidth: 380 });
    aptMarkers[a.id] = marker;
  }
});

// === Facility markers ===
SESSION.facilities.forEach(function(f) {
  const marker = L.marker([f.lat, f.lng], { icon: facIcon(f.type) }).addTo(map);
  marker.bindPopup(
    '<div style="min-width: 180px;">' +
      '<div style="font-weight:600;font-size:12px;">' + escapeHtml(f.name) + '</div>' +
      (f.line ? '<div style="font-size:10px;color:#666;">' + escapeHtml(f.line) + '</div>' : '') +
      '<div style="font-size:10px;color:#999;margin-top:2px;">분류: ' + escapeHtml(f.type) + '</div>' +
      '<div style="margin-top:4px;display:flex;gap:3px;">' +
        '<a href="' + escapeHtml(f.kakao_map_link) + '" target="_blank" style="background:#ffe600;color:#000;padding:2px 5px;border-radius:2px;font-size:10px;text-decoration:none;">카카오맵</a>' +
        '<a href="' + escapeHtml(f.naver_map_link) + '" target="_blank" style="background:#03c75a;color:white;padding:2px 5px;border-radius:2px;font-size:10px;text-decoration:none;">네이버</a>' +
      '</div>' +
    '</div>'
  );
});

// === Photo markers (per hour-cluster) ===
const photoMarkers = [];
const photoLatLngs = [];
const photoClusters = {};
SESSION.photos.forEach(function(p) {
  const cid = p.filename.substring(8, 14);
  if (!photoClusters[cid]) photoClusters[cid] = [];
  photoClusters[cid].push(p);
});

// === Photo markers (per hour-cluster) - 클릭 시 클러스터 전체 모달 ===
const clusterPhotosByCid = {};  // for cluster modal lookup
Object.keys(photoClusters).sort().forEach(function(cid) {
  clusterPhotosByCid[cid] = photoClusters[cid];
  const ps = photoClusters[cid];
  const lat = ps.reduce(function(s, p) { return s + p.lat; }, 0) / ps.length;
  const lng = ps.reduce(function(s, p) { return s + p.lng; }, 0) / ps.length;
  photoLatLngs.push([lat, lng]);
  const reviewed = ps.filter(function(p) { return getReviewText(p.id); });
  const reviewedCount = reviewed.length;
  const totalCount = ps.length;
  const hasReview = reviewedCount > 0;
  const icon = photoIcon(reviewedCount, totalCount);
  const marker = L.marker([lat, lng], { icon: icon }).addTo(map);
  // 작은 popup (preview만) + 클릭 시 큰 모달
  const previewHtml =
    '<div style="min-width: 200px;">' +
      '<div style="font-weight:600;font-size:12px;margin-bottom:4px;">📷 ' + ps.length + '장 (' + cid + ')</div>' +
      '<div style="font-size:10px;color:#666;margin-bottom:6px;">' +
        '후기: ' + reviewed.length + '/' + ps.length +
      '</div>' +
      '<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:2px;margin-bottom:6px;">' +
        ps.slice(0, 3).map(function(p) {
          return '<img src="assets/photos/' + escapeHtml(p.filename) + '" style="width:100%;height:50px;object-fit:cover;border-radius:2px;">';
        }).join('') +
      '</div>' +
      '<button onclick="openClusterModal(\'' + cid + '\')" style="width:100%;background:#2c5f7e;color:white;padding:6px;border:none;border-radius:3px;cursor:pointer;font-size:11px;">📷 사진 모두 보기 (' + ps.length + '장)</button>' +
    '</div>';
  marker.bindPopup(previewHtml, { maxWidth: 260, maxHeight: 250 });
  // 마커 자체를 클릭하면 큰 모달로 직접 열기
  marker.on('click', function() {
    // 약간의 지연 (popup과 겹치지 않게)
    setTimeout(function() { openClusterModal(cid); }, 100);
  });
  photoMarkers.push(marker);
});

// === Cluster Modal (지도 마커에서 직접) ===
function openClusterModal(cid) {
  const ps = clusterPhotosByCid[cid];
  if (!ps || ps.length === 0) return;
  const reviewed = ps.filter(function(p) { return getReviewText(p.id); });
  // 진행률 badge
  let progressHtml = '<div style="margin:8px 0;padding:6px 8px;background:#e8f4f8;border-radius:4px;font-size:11px;">' +
    '<strong>📝 후기 진행률:</strong> ' +
    '<span class="progress-badge ' + (reviewed.length === 0 ? 'zero' : reviewed.length === ps.length ? 'full' : 'partial') + '">' +
    reviewed.length + '/' + ps.length +
    '</span></div>';
  // 사진 그리드
  const gridHtml = ps.map(function(p, i) {
    const review = getReviewText(p.id);
    const tags = getReviewTags(p.id);
    const hasReview = !!review;
    const tagsStr = tags.length ? ' #' + tags.join(' #') : '';
    return '<div id="cluster-photo-' + p.id + '" style="margin-bottom:14px;border:1px solid ' + (hasReview ? '#2e7d32' : '#ddd') + ';border-radius:6px;overflow:hidden;background:white;">' +
      '<div style="position:relative;">' +
        '<img src="assets/photos/' + escapeHtml(p.filename) + '" style="width:100%;max-height:50vh;object-fit:contain;background:#222;">' +
        '<div style="position:absolute;top:6px;left:6px;background:rgba(0,0,0,0.7);color:white;padding:2px 8px;border-radius:10px;font-size:10px;">' +
          (i+1) + '/' + ps.length + ' · ' + escapeHtml(p.timestamp ? p.timestamp.substring(11) : '') +
        '</div>' +
        (hasReview ? '<div style="position:absolute;top:6px;right:6px;background:#2e7d32;color:white;padding:2px 8px;border-radius:10px;font-size:10px;">📝 후기완료</div>' : '<div style="position:absolute;top:6px;right:6px;background:rgba(255,107,53,0.85);color:white;padding:2px 8px;border-radius:10px;font-size:10px;">후기 미작성</div>') +
      '</div>' +
      '<div style="padding:10px;">' +
        '<textarea id="cluster-review-' + p.id + '" placeholder="이 사진에 대한 후기를 입력하세요..." ' +
        'style="width:100%;min-height:60px;padding:6px;border:1px solid #ccc;border-radius:4px;font-family:inherit;font-size:12px;resize:vertical;box-sizing:border-box;">' +
        escapeHtml(review || '') + '</textarea>' +
        '<div style="display:flex;gap:4px;margin-top:6px;align-items:center;">' +
          '<button onclick="saveClusterReview(\'' + p.id + '\')" style="flex:1;background:#2c5f7e;color:white;padding:5px 8px;border:none;border-radius:3px;cursor:pointer;font-size:11px;">💾 저장</button>' +
          (hasReview ? '<button onclick="deleteClusterReview(\'' + p.id + '\')" style="background:#d35400;color:white;padding:5px 8px;border:none;border-radius:3px;cursor:pointer;font-size:11px;">🗑️</button>' : '') +
          '<input type="text" id="cluster-tag-' + p.id + '" placeholder="태그 (Enter)" ' +
          'style="flex:1;min-width:80px;padding:4px 6px;font-size:10px;border:1px solid #ccc;border-radius:3px;" ' +
          'onkeydown="if(event.key===\'Enter\'){event.preventDefault();addClusterTag(\'' + p.id + '\')}">' +
          '<button onclick="addClusterTag(\'' + p.id + '\')" style="background:#9c27b0;color:white;padding:5px 8px;border:none;border-radius:3px;cursor:pointer;font-size:11px;">+#</button>' +
        '</div>' +
        (tagsStr ? '<div style="margin-top:6px;font-size:10px;">' + tags.map(function(t) { return '<span class="tag" style="background:#e8f4f8;color:#2c5f7e;padding:1px 5px;border-radius:2px;margin-right:3px;">#' + escapeHtml(t) + '</span>'; }).join('') + '</div>' : '') +
      '</div>' +
    '</div>';
  }).join('');
  // 모달 HTML
  const modal = document.getElementById('cluster-modal');
  if (!modal) {
    // 동적 생성
    const div = document.createElement('div');
    div.id = 'cluster-modal';
    div.className = 'photo-modal';
    div.innerHTML = '<div class="modal-content" style="max-width:900px;max-height:90vh;overflow-y:auto;padding:14px;">' +
      '<button onclick="closeClusterModal()" style="float:right;background:none;border:none;font-size:20px;cursor:pointer;line-height:1;">✕</button>' +
      '<h3 id="cluster-modal-title" style="margin:0 0 4px 0;color:#1a3a4d;"></h3>' +
      '<div id="cluster-modal-progress"></div>' +
      '<div id="cluster-modal-body"></div>' +
    '</div>';
    document.body.appendChild(div);
  }
  document.getElementById('cluster-modal-title').textContent = '📷 ' + cid + ' (' + ps.length + '장)';
  document.getElementById('cluster-modal-progress').innerHTML = progressHtml;
  document.getElementById('cluster-modal-body').innerHTML = gridHtml;
  document.getElementById('cluster-modal').classList.add('show');
}

function closeClusterModal() {
  const m = document.getElementById('cluster-modal');
  if (m) m.classList.remove('show');
}

function saveClusterReview(photoId) {
  const textarea = document.getElementById('cluster-review-' + photoId);
  if (!textarea) return;
  const text = textarea.value.trim();
  if (!text) {
    delete storage.reviews[photoId];
  } else {
    const existing = storage.reviews[photoId] || { text: '', tags: [] };
    storage.reviews[photoId] = { text: text, tags: existing.tags || [] };
  }
  saveStorage();
  showSaveStatus('💾 저장됨 (' + photoId + ')');
  refreshAll();
}

function deleteClusterReview(photoId) {
  if (!confirm('이 사진의 후기를 삭제하시겠습니까?')) return;
  delete storage.reviews[photoId];
  saveStorage();
  refreshAll();
}

function addClusterTag(photoId) {
  const input = document.getElementById('cluster-tag-' + photoId);
  if (!input) return;
  const tag = input.value.trim().replace(/^#/, '');
  if (!tag) return;
  if (!storage.reviews[photoId]) storage.reviews[photoId] = { text: '', tags: [] };
  if (!storage.reviews[photoId].tags) storage.reviews[photoId].tags = [];
  if (storage.reviews[photoId].tags.indexOf(tag) < 0) {
    storage.reviews[photoId].tags.push(tag);
  }
  input.value = '';
  saveStorage();
  // Re-render only this card (avoid full reload for smooth UX)
  const card = document.getElementById('cluster-photo-' + photoId);
  if (card) {
    // Update visual: border + badge
    card.style.border = '1px solid #2e7d32';
    const badges = card.querySelectorAll('.badge-after-review');
    // Just re-render
    refreshAll();
  }
}

// v1 호환: focusClusterPhotos (사용 안 함, openClusterModal 권장)
function focusClusterPhotos(photoIds) {
  const first = SESSION.photos.find(function(p) { return p.id === photoIds[0]; });
  if (first) {
    const cid = first.filename.substring(8, 14);
    openClusterModal(cid);
  }
}

// === Draw route polyline ===
if (photoLatLngs.length > 0) {
  L.polyline(photoLatLngs, {
    color: '#ff6b35', weight: 3, opacity: 0.6, dashArray: '8, 8'
  }).addTo(map);
}

if (photoLatLngs.length > 0) {
  const bounds = L.latLngBounds(photoLatLngs);
  SESSION.apartments.forEach(function(a) {
    if (isHiddenApt(a.id)) return;
    if (a.lat && a.lng) bounds.extend([a.lat, a.lng]);
  });
  map.fitBounds(bounds, { padding: [40, 40] });
}

// === User marks (loaded from storage) ===
function renderUserMarks() {
  storage.user_marks.forEach(function(m) {
    const marker = L.marker([m.lat, m.lng], { icon: userMarkIcon(m.type) }).addTo(map);
    const popup =
      '<div style="min-width: 200px;">' +
        '<div style="font-weight:600;font-size:13px;">' + escapeHtml(m.type) + ' ' + escapeHtml(m.name) + '</div>' +
        (m.note ? '<div style="font-size:11px;color:#666;margin-top:4px;">' + escapeHtml(m.note) + '</div>' : '') +
        '<div style="font-size:9px;color:#999;margin-top:4px;">' + (m.created_at || '') + '</div>' +
        '<div style="margin-top:6px;">' +
          '<button onclick="openReviewModal(\'' + m.id + '\', \'user_mark\', \'' + escapeJs(m.name) + '\')" style="background:#2c5f7e;color:white;padding:3px 6px;border-radius:3px;font-size:10px;border:none;cursor:pointer;">📝 후기</button>' +
          '<button onclick="deleteUserMark(\'' + m.id + '\')" style="background:#d35400;color:white;padding:3px 6px;border-radius:3px;font-size:10px;border:none;cursor:pointer;margin-left:4px;">🗑️ 삭제</button>' +
        '</div>' +
      '</div>';
    marker.bindPopup(popup);
  });
}
renderUserMarks();

// === Streak with inline edit + progress + tag filter ===
function renderStreak() {
  const tagFilterEl = document.getElementById('streak-tag-select');
  const tagFilter = tagFilterEl ? tagFilterEl.value : 'all';

  const sorted = SESSION.photos.slice().sort(function(a, b) {
    return (a.timestamp || '').localeCompare(b.timestamp || '');
  });

  // Filter by tag
  let filtered = sorted;
  if (tagFilter === 'unreviewed') {
    filtered = filtered.filter(function(p) { return !getReviewText(p.id); });
  } else if (tagFilter === 'reviewed') {
    filtered = filtered.filter(function(p) { return !!getReviewText(p.id); });
  } else if (tagFilter && tagFilter !== 'all') {
    filtered = filtered.filter(function(p) { return getReviewTags(p.id).indexOf(tagFilter) >= 0; });
  }

  const html = filtered.map(function(p) {
    const hasReview = !!getReviewText(p.id);
    const time = p.timestamp ? p.timestamp.substring(11) : '';
    const reviewText = getReviewText(p.id) || '';
    const tags = getReviewTags(p.id);
    const tagsHtml = tags.map(function(t) { return '<span class="tag">' + escapeHtml(t) + '</span>'; }).join('');
    return '<div class="streak-item' + (hasReview ? ' has-review' : '') + '" data-id="' + p.id + '">' +
      '<div class="streak-item-header">' +
        '<div class="photo-thumb" title="사진 더블클릭: 큰 모달">' +
          '<img src="assets/photos/' + escapeHtml(p.filename) + '" alt="" ondblclick="openPhotoModal(\'' + p.id + '\', \'' + escapeJs(p.filename) + '\', \'' + escapeJs(p.timestamp || '') + '\')">' +
        '</div>' +
        '<div class="info-area" onclick="toggleStreakEdit(\'' + p.id + '\')" title="클릭하여 후기 작성/수정">' +
          '<div class="time">' + escapeHtml(time) + '</div>' +
          '<div class="progress' + (hasReview ? '' : ' zero') + '">' +
            (hasReview ? '✓ ' + reviewText.substring(0, 30) + (reviewText.length > 30 ? '...' : '') : '클릭하여 후기 입력') +
          '</div>' +
          '<div class="hint">✏️ 여기를 눌러 후기 작성</div>' +
        '</div>' +
      '</div>' +
      '<div class="inline-review" id="streak-edit-' + p.id + '" style="display:none;">' +
        '<textarea placeholder="이 사진에 대한 후기를 입력하세요...">' + escapeHtml(reviewText) + '</textarea>' +
        '<div class="actions">' +
          '<button class="save" onclick="saveStreakReview(\'' + p.id + '\')">💾 저장</button>' +
          '<button class="cancel" onclick="cancelStreakEdit(\'' + p.id + '\')">취소</button>' +
          (hasReview ? '<button class="delete" onclick="deleteStreakReview(\'' + p.id + '\')">🗑️</button>' : '') +
        '</div>' +
        '<div class="tags">' +
          tagsHtml +
          '<div class="tag-input-row">' +
            '<input type="text" placeholder="태그 추가 (Enter)" id="streak-tag-' + p.id + '" onkeydown="if(event.key===\'Enter\'){event.preventDefault();addStreakTag(\'' + p.id + '\')}">' +
            '<button onclick="addStreakTag(\'' + p.id + '\')">+</button>' +
          '</div>' +
        '</div>' +
      '</div>' +
    '</div>';
  }).join('');
  document.getElementById('streak-list').innerHTML = html || '<div style="color:#999;font-size:11px;text-align:center;padding:8px;">해당 사진 없음</div>';

  // Update progress badge in header
  const total = SESSION.photos.length;
  const reviewed = SESSION.photos.filter(function(p) { return getReviewText(p.id); }).length;
  // (헤더에 진행률 추가하는 자리)
}

function toggleStreakEdit(photoId) {
  const el = document.getElementById('streak-edit-' + photoId);
  if (el) el.style.display = el.style.display === 'none' ? 'block' : 'none';
}
function cancelStreakEdit(photoId) {
  const el = document.getElementById('streak-edit-' + photoId);
  if (el) el.style.display = 'none';
}
function saveStreakReview(photoId) {
  const el = document.getElementById('streak-edit-' + photoId);
  if (!el) return;
  const textarea = el.querySelector('textarea');
  const text = textarea.value.trim();
  if (!text) {
    delete storage.reviews[photoId];
  } else {
    // preserve existing tags
    const existing = storage.reviews[photoId] || { text: '', tags: [] };
    storage.reviews[photoId] = { text: text, tags: existing.tags || [] };
  }
  saveStorage();
  refreshAll();
}
function deleteStreakReview(photoId) {
  if (!confirm('이 사진의 후기를 삭제하시겠습니까?')) return;
  delete storage.reviews[photoId];
  saveStorage();
  refreshAll();
}
function addStreakTag(photoId) {
  const input = document.getElementById('streak-tag-' + photoId);
  if (!input) return;
  const tag = input.value.trim().replace(/^#/, '');
  if (!tag) return;
  if (!storage.reviews[photoId]) storage.reviews[photoId] = { text: '', tags: [] };
  if (!storage.reviews[photoId].tags) storage.reviews[photoId].tags = [];
  if (storage.reviews[photoId].tags.indexOf(tag) < 0) {
    storage.reviews[photoId].tags.push(tag);
  }
  input.value = '';
  saveStorage();
  // Re-render only this item
  cancelStreakEdit(photoId);
  toggleStreakEdit(photoId);
  renderStreakTagFilter();
}

// Update tag filter options for streak
function renderStreakTagFilter() {
  const allTags = new Set();
  Object.values(storage.reviews).forEach(function(r) {
    if (r.tags) r.tags.forEach(function(t) { allTags.add(t); });
  });
  const opts = '<option value="all">전체 사진</option>' +
    '<option value="reviewed">✓ 후기 있는 사진</option>' +
    '<option value="unreviewed">○ 후기 없는 사진</option>' +
    Array.from(allTags).sort().map(function(t) {
      return '<option value="' + escapeHtml(t) + '">#' + escapeHtml(t) + '</option>';
    }).join('');
  document.getElementById('streak-tag-select').innerHTML = opts;
}
renderStreakTagFilter();
renderStreak();

// === Apartment list with tag filter ===
function getAllAptTags() {
  const tags = new Set();
  SESSION.apartments.forEach(function(a) {
    if (isHiddenApt(a.id)) return;
    if (isFavoriteApt(a.id)) tags.add('관심단지');
    if (isLeaderApt(a.id)) tags.add('대장아파트');
    (a.tags || []).forEach(function(t) { tags.add(t); });
    getReviewTags(a.id).forEach(function(t) { tags.add(t); });
  });
  return Array.from(tags).sort();
}

function renderAptTagFilter() {
  const tags = getAllAptTags();
  const sel = document.getElementById('apt-tag-select');
  if (!sel) return;
  sel.innerHTML = '<option value="all">전체 태그</option>' +
    tags.map(function(t) { return '<option value="' + escapeHtml(t) + '">#' + escapeHtml(t) + '</option>'; }).join('');
}

function parseAptPrice(a) {
  if (!a.recent_trade_price) return null;
  const s = String(a.recent_trade_price).replace(/,/g, '');
  const m = s.match(/([0-9]+(?:\.[0-9]+)?)\s*억/);
  if (m) return parseFloat(m[1]);
  const n = s.match(/([0-9]+(?:\.[0-9]+)?)/);
  return n ? parseFloat(n[1]) : null;
}
function getAptDistance(a) {
  const v = a.distance_to_route_m ?? a.route_distance_m ?? a.min_route_distance_m;
  return Number.isFinite(Number(v)) ? Number(v) : 999999;
}
function getAptTradeCount(a) {
  return Number(a.trade_count || a.sample_count || 0);
}

function compareAptsBySort(a, b, sortMode) {
  const favDiff = (isFavoriteApt(b.id) ? 1 : 0) - (isFavoriteApt(a.id) ? 1 : 0);
  if (favDiff !== 0) return favDiff;
  const leaderDiff = (isLeaderApt(b.id) ? 1 : 0) - (isLeaderApt(a.id) ? 1 : 0);
  if (leaderDiff !== 0) return leaderDiff;
  if (sortMode === 'name-desc') return b.name.localeCompare(a.name);
  if (sortMode === 'distance-asc') return getAptDistance(a) - getAptDistance(b) || a.name.localeCompare(b.name);
  if (sortMode === 'distance-desc') return getAptDistance(b) - getAptDistance(a) || a.name.localeCompare(b.name);
  if (sortMode === 'price-desc') return ((parseAptPrice(b) ?? -1) - (parseAptPrice(a) ?? -1)) || a.name.localeCompare(b.name);
  if (sortMode === 'price-asc') return ((parseAptPrice(a) ?? 999999) - (parseAptPrice(b) ?? 999999)) || a.name.localeCompare(b.name);
  if (sortMode === 'built-desc') return Number(b.built_year || 0) - Number(a.built_year || 0) || a.name.localeCompare(b.name);
  if (sortMode === 'built-asc') return Number(a.built_year || 9999) - Number(b.built_year || 9999) || a.name.localeCompare(b.name);
  if (sortMode === 'trade-desc') return getAptTradeCount(b) - getAptTradeCount(a) || a.name.localeCompare(b.name);
  if (sortMode === 'trade-asc') return getAptTradeCount(a) - getAptTradeCount(b) || a.name.localeCompare(b.name);
  return a.name.localeCompare(b.name);
}

function renderAptList() {
  const filter = document.getElementById('apt-search').value.toLowerCase();
  const tagFilter = document.getElementById('apt-tag-select').value;
  const typeFilterEl = document.getElementById('apt-filter-select');
  const typeFilter = typeFilterEl ? typeFilterEl.value : 'all';
  const sortEl = document.getElementById('apt-sort-select');
  const sortMode = sortEl ? sortEl.value : 'favorite-default';
  const filtered = SESSION.apartments.filter(function(a) {
    if (isHiddenApt(a.id)) return false;
    if (!a.name.toLowerCase().includes(filter)) return false;
    if (typeFilter === 'favorite' && !isFavoriteApt(a.id)) return false;
    if (typeFilter === 'priced' && !a.recent_trade_price) return false;
    if (typeFilter === 'unpriced' && a.recent_trade_price) return false;
    if (typeFilter === 'reviewed' && !getReviewText(a.id)) return false;
    if (typeFilter === 'leader' && !isLeaderApt(a.id)) return false;
    if (tagFilter !== 'all') {
      const aptTags = (isFavoriteApt(a.id) ? ['관심단지'] : []).concat(isLeaderApt(a.id) ? ['대장아파트'] : []).concat(a.tags || []).concat(getReviewTags(a.id));
      if (aptTags.indexOf(tagFilter) < 0) return false;
    }
    return true;
  });
  filtered.sort(function(a, b) { return compareAptsBySort(a, b, sortMode); });
  const html = filtered.map(function(a) {
    const reviewBadge = getReviewBadge(a.id);
    const hasReview = !!getReviewText(a.id);
    const fav = isFavoriteApt(a.id);
    const leader = isLeaderApt(a.id);
    const aptTags = a.tags || [];
    const userTags = getReviewTags(a.id);
    const allTags = (fav ? ['관심단지'] : []).concat(leader ? ['대장아파트'] : []).concat(aptTags).concat(userTags);
    const tagsHtml = allTags.length ? '<div class="tags">' + allTags.map(function(t) { return '<span class="tag' + (t === '관심단지' ? ' favorite-tag' : '') + '">#' + escapeHtml(t) + '</span>'; }).join('') + '</div>' : '';
    return '<div class="apt-card' + (hasReview ? ' has-review' : '') + (fav ? ' favorite' : '') + (leader ? ' daejang' : '') + '" onclick="focusApt(\'' + a.id + '\')" data-id="' + a.id + '">' +
      '<div class="name">' + escapeHtml(a.name) +
      (fav ? '<span class="badge favorite-badge">★ 관심</span>' : '') +
      (leader ? '<span class="badge">👑 대장</span>' : '') + reviewBadge + '</div>' +
      '<div class="meta">' + escapeHtml(a.address) + '</div>' +
      '<div class="meta">동선거리 ' + Math.round(getAptDistance(a)) + 'm' + (getAptTradeCount(a) ? ' · 거래 ' + getAptTradeCount(a) + '건' : '') + '</div>' +
      (a.built_year ? '<div class="meta">' + a.built_year + '년 준공</div>' : '') +
      ((a.recent_trade_price || a.jeonse_price) ? '<div class="price">' + (a.recent_trade_price || '-') + (a.jeonse_price ? ' / ' + a.jeonse_price : '') + '</div>' : '<div class="meta">국토교통부 아파트매매 실거래가 API로 조회되지 않음</div>') +
      (a.latest_deal_date ? '<div class="date-info">📅 ' + escapeHtml(formatDealDateInfo(a, '기준')) + '</div>' : '') +
      tagsHtml +
      (hasReview ? '<div class="review-snippet">📝 ' + escapeHtml(getReviewText(a.id)) + '</div>' : '') +
    '</div>';
  }).join('');
  document.getElementById('apt-list').innerHTML = html || '<div style="color:#999;font-size:11px;text-align:center;padding:8px;">검색 결과 없음</div>';
}
renderAptTagFilter();
renderAptList();

// === News list ===
function renderNewsList() {
  const allNews = SESSION.news_items.concat(storage.user_news);
  const tagFilterEl = document.getElementById('news-tag-select');
  const tagFilter = tagFilterEl ? tagFilterEl.value : 'all';
  let filtered = allNews;
  if (tagFilter !== 'all') {
    filtered = filtered.filter(function(n) { return n.tags && n.tags.indexOf(tagFilter) >= 0; });
  }
  filtered.sort(function(a, b) { return new Date(b.published_at || 0) - new Date(a.published_at || 0); });
  const html = filtered.map(function(n) {
    const isUser = storage.user_news.indexOf(n) >= 0;
    const reviewBadge = '';
    const dateStr = n.published_at ? new Date(n.published_at).toLocaleDateString('ko-KR') : '';
    let tagsHtml = '';
    if (n.tags && n.tags.length) {
      tagsHtml = '<div style="margin-top:2px;">' + n.tags.map(function(t) { return '<span class="tag">' + escapeHtml(t) + '</span>'; }).join('') + '</div>';
    }
    return '<div class="news-item' + (isUser ? ' user' : '') + '" onclick="' + (n.url ? 'window.open(\'' + escapeJs(n.url) + '\', \'_blank\')' : '') + '">' +
      (isUser ? '<span class="delete-btn" onclick="deleteUserNews(event, ' + (storage.user_news.indexOf(n)) + ')">✕</span>' : '') +
      '<div class="title">' + escapeHtml(n.title) + reviewBadge + '</div>' +
      '<div class="date">' + dateStr + (n.search_query ? ' | ' + escapeHtml(n.search_query) : (isUser ? ' | 사용자 추가' : '')) + '</div>' +
      tagsHtml +
    '</div>';
  }).join('');
  document.getElementById('news-list').innerHTML = html || '<div style="color:#999;font-size:11px;text-align:center;padding:8px;">뉴스 없음</div>';

  const allTags = [];
  allNews.forEach(function(n) {
    if (n.tags) n.tags.forEach(function(t) { if (allTags.indexOf(t) < 0) allTags.push(t); });
  });
  const filterOptions = '<select id="news-tag-select" onchange="renderNewsList()" style="padding:3px 6px;font-size:10px;border-radius:3px;border:1px solid #ccc;width:100%;">' +
    '<option value="all">전체 (' + allNews.length + ')</option>' +
    allTags.map(function(t) {
      const cnt = allNews.filter(function(n) { return n.tags && n.tags.indexOf(t) >= 0; }).length;
      return '<option value="' + escapeHtml(t) + '">' + escapeHtml(t) + ' (' + cnt + ')</option>';
    }).join('') +
    '</select>';
  document.getElementById('news-tag-filter').innerHTML = filterOptions;
}
renderNewsList();

// === Neighborhood review ===
function loadNeighborhoodReview() {
  const nr = storage.neighborhood_review || { overall: '', prompts: {} };
  document.getElementById('nb-overall').value = nr.overall || '';
  const p = nr.prompts || {};
  document.getElementById('nb-atmosphere').value = p.atmosphere || '';
  document.getElementById('nb-commerce').value = p.commerce || '';
  document.getElementById('nb-transit').value = p.transit || '';
  document.getElementById('nb-walkability').value = p.walkability || '';
  document.getElementById('nb-future').value = p.future || '';
}
function saveNeighborhoodReview() {
  storage.neighborhood_review = {
    overall: document.getElementById('nb-overall').value.trim(),
    prompts: {
      atmosphere: document.getElementById('nb-atmosphere').value.trim(),
      commerce: document.getElementById('nb-commerce').value.trim(),
      transit: document.getElementById('nb-transit').value.trim(),
      walkability: document.getElementById('nb-walkability').value.trim(),
      future: document.getElementById('nb-future').value.trim()
    },
    updated_at: new Date().toISOString()
  };
  saveStorage();
  showSaveStatus('💾 한줄평 저장됨');
  updateNbReviewStatus();
}
function updateNbReviewStatus() {
  const nr = storage.neighborhood_review || {};
  const filled = (nr.overall ? 1 : 0) + Object.values(nr.prompts || {}).filter(function(v){return v;}).length;
  const total = 6;
  const badge = document.getElementById('nb-review-status');
  if (!badge) return;
  badge.textContent = filled + '/' + total;
  badge.className = 'progress-badge ' + (filled === 0 ? 'zero' : filled === total ? 'full' : 'partial');
}
loadNeighborhoodReview();
updateNbReviewStatus();

// === Review modal ===
function openReviewModal(targetId, targetType, targetName) {
  currentReviewTarget = { id: targetId, type: targetType, name: targetName };
  document.getElementById('review-title').textContent = '후기 기록 — ' + targetName;
  const existing = storage.reviews[targetId];
  document.getElementById('review-text').value = (existing && existing.text) || '';
  const tags = (existing && existing.tags) || [];
  document.getElementById('review-tag-input').value = tags.join(', ');
  document.getElementById('review-delete-btn').style.display = existing ? 'inline-block' : 'none';
  document.getElementById('review-modal').classList.add('show');
}
function closeReviewModal() {
  document.getElementById('review-modal').classList.remove('show');
  currentReviewTarget = null;
}
function saveReview() {
  if (!currentReviewTarget) return;
  const text = document.getElementById('review-text').value.trim();
  const tagInput = document.getElementById('review-tag-input').value;
  const tags = tagInput.split(',').map(function(t) { return t.trim().replace(/^#/, ''); }).filter(function(t) { return t; });
  if (!text && tags.length === 0) {
    delete storage.reviews[currentReviewTarget.id];
  } else {
    storage.reviews[currentReviewTarget.id] = { text: text, tags: tags };
  }
  saveStorage();
  closeReviewModal();
  refreshAll();
}
function deleteReview() {
  if (!currentReviewTarget) return;
  if (!confirm('이 후기를 삭제하시겠습니까?')) return;
  delete storage.reviews[currentReviewTarget.id];
  saveStorage();
  closeReviewModal();
  refreshAll();
}

// === Photo modal ===
function openPhotoModal(photoId, filename, timestamp) {
  currentPhotoReviewTarget = { id: photoId, filename: filename, timestamp: timestamp };
  document.getElementById('photo-modal-img').src = 'assets/photos/' + filename;
  document.getElementById('photo-modal-img').alt = filename;
  document.getElementById('photo-modal-title').textContent = filename;
  document.getElementById('photo-modal-ts').textContent = (timestamp || '') + '  |  클릭하여 후기 작성/수정';
  const review = getReviewText(photoId);
  const tags = getReviewTags(photoId);
  const tagsHtml = tags.length ? '<div style="margin-top:4px;">' + tags.map(function(t){return '<span class="tag">#' + escapeHtml(t) + '</span>';}).join('') + '</div>' : '';
  document.getElementById('photo-modal-review').innerHTML = (review ? escapeHtml(review) : '<span style="color:#999;">(후기 없음 — 작성해주세요)</span>') + tagsHtml;
  document.getElementById('photo-modal').classList.add('show');
}
function closePhotoModal() {
  document.getElementById('photo-modal').classList.remove('show');
  currentPhotoReviewTarget = null;
}
function editCurrentPhotoReview() {
  if (!currentPhotoReviewTarget) return;
  closePhotoModal();
  openReviewModal(currentPhotoReviewTarget.id, 'photo', currentPhotoReviewTarget.filename);
}

// === Add news modal ===
function openAddNewsModal() {
  document.getElementById('news-title').value = '';
  document.getElementById('news-url').value = '';
  document.getElementById('news-summary').value = '';
  document.getElementById('add-news-modal').classList.add('show');
}
function closeAddNewsModal() {
  document.getElementById('add-news-modal').classList.remove('show');
}
function saveNewNews() {
  const title = document.getElementById('news-title').value.trim();
  const url = document.getElementById('news-url').value.trim();
  const summary = document.getElementById('news-summary').value.trim();
  if (!title) { alert('제목 필수'); return; }
  storage.user_news.push({
    id: 'user_news_' + Date.now(),
    title: title,
    url: url || '',
    summary: summary,
    published_at: new Date().toISOString(),
    tags: ['#사용자추가'],
    source: 'manual'
  });
  saveStorage();
  closeAddNewsModal();
  renderNewsList();
}
function deleteUserNews(e, idx) {
  e.stopPropagation();
  if (!confirm('이 뉴스를 삭제하시겠습니까?')) return;
  storage.user_news.splice(idx, 1);
  saveStorage();
  renderNewsList();
}

// === User mark ===
function openUserMarkAtLatLng(latlng, source) {
  pendingMarkLatLng = latlng;
  document.getElementById('user-mark-modal').classList.add('show');
  addMarkMode = false;
  document.getElementById('btn-add-mark').classList.remove('active');
  if (source) showSaveStatus('📍 ' + source + ' 위치에 마크를 추가합니다');
}
function toggleAddMark() {
  addMarkMode = !addMarkMode;
  document.getElementById('btn-add-mark').classList.toggle('active', addMarkMode);
  if (addMarkMode) {
    showSaveStatus('📍 지도를 클릭해서 위치를 지정하세요 (우클릭/길게 누르기도 가능)');
  }
}
map.on('click', function(e) {
  if (!addMarkMode) return;
  openUserMarkAtLatLng(e.latlng, '클릭한');
});
// 데스크톱: 지도 우클릭으로 바로 마크 추가
map.on('contextmenu', function(e) {
  if (e.originalEvent) {
    L.DomEvent.preventDefault(e.originalEvent);
    L.DomEvent.stopPropagation(e.originalEvent);
  }
  openUserMarkAtLatLng(e.latlng, '우클릭한');
});
// 모바일/터치: 지도 길게 누르기(650ms)로 마크 추가
let longPressTimer = null;
let longPressStartLatLng = null;
function clearLongPressTimer() {
  if (longPressTimer) clearTimeout(longPressTimer);
  longPressTimer = null;
  longPressStartLatLng = null;
}
map.on('touchstart mousedown', function(e) {
  if (!e.latlng) return;
  longPressStartLatLng = e.latlng;
  clearLongPressTimer();
  longPressStartLatLng = e.latlng;
  longPressTimer = setTimeout(function() {
    openUserMarkAtLatLng(longPressStartLatLng, '길게 누른');
    clearLongPressTimer();
  }, 650);
});
map.on('touchmove mousemove dragstart zoomstart popupopen', clearLongPressTimer);
map.on('touchend mouseup touchcancel mouseout', clearLongPressTimer);
function closeUserMarkModal() {
  document.getElementById('user-mark-modal').classList.remove('show');
  pendingMarkLatLng = null;
}
function saveUserMark() {
  if (!pendingMarkLatLng) return;
  const name = document.getElementById('mark-name').value.trim();
  const type = document.getElementById('mark-type').value;
  const note = document.getElementById('mark-note').value.trim();
  if (!name) { alert('이름 필수'); return; }
  const id = 'user_mark_' + Date.now();
  storage.user_marks.push({
    id: id,
    lat: pendingMarkLatLng.lat,
    lng: pendingMarkLatLng.lng,
    name: name,
    type: type,
    note: note,
    created_at: new Date().toISOString()
  });
  saveStorage();
  closeUserMarkModal();
  location.reload();
}
function deleteUserMark(id) {
  if (!confirm('이 마크를 삭제하시겠습니까?')) return;
  storage.user_marks = storage.user_marks.filter(function(m) { return m.id !== id; });
  saveStorage();
  location.reload();
}

// === Capture mode (후기 갈무리 - 전체 동선 오버레이) ===
function clearCaptureOverlay() {
  const overlay = document.getElementById('capture-overlay');
  if (overlay) {
    overlay.innerHTML = '';
    overlay.style.display = 'none';
  }
}
function captureEntryHtml(e) {
  const tagHtml = e.tags && e.tags.length ? '<div class="tags">#' + e.tags.map(escapeHtml).join(' #') + '</div>' : '';
  const typeCls = e.type === 'apartment' ? 'apt' : e.type === 'mark' ? 'mark' : 'photo';
  const typeLabel = e.typeLabel || '후기';
  return '<div class="ts"><span class="type-tag ' + typeCls + '">' + escapeHtml(typeLabel) + '</span>' + escapeHtml(e.time || '') + '</div>' +
    '<div class="name">' + escapeHtml(e.name || '') + '</div>' +
    '<div class="review">' + escapeHtml(e.review || '') + '</div>' + tagHtml;
}
function buildCaptureEntries() {
  const entries = [];
  SESSION.photos.forEach(function(p) {
    const review = getReviewText(p.id);
    const tags = getReviewTags(p.id);
    if (!review) return;
    if (p.lat == null || p.lng == null) return;
    entries.push({
      type: 'photo', typeLabel: '사진 후기', lat: p.lat, lng: p.lng,
      time: p.timestamp ? p.timestamp.substring(0, 16) : p.filename,
      name: p.filename, review: review, tags: tags
    });
  });
  SESSION.apartments.forEach(function(a) {
    if (isHiddenApt(a.id)) return;
    const review = getReviewText(a.id);
    const tags = getReviewTags(a.id);
    if (!review) return;
    if (a.lat == null || a.lng == null) return;
    entries.push({
      type: 'apartment', typeLabel: '단지 후기', lat: a.lat, lng: a.lng,
      time: '단지 후기', name: a.name, review: review, tags: tags
    });
  });
  storage.user_marks.forEach(function(m) {
    if (!m.note) return;
    entries.push({
      type: 'mark', typeLabel: '사용자 마크', lat: m.lat, lng: m.lng,
      time: '사용자 마크', name: (m.type || '📍') + ' ' + m.name, review: m.note, tags: []
    });
  });
  return entries.sort(function(a, b) { return String(a.time || '').localeCompare(String(b.time || '')); });
}
function rectOverlap(a, b) {
  const x = Math.max(0, Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x));
  const y = Math.max(0, Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y));
  return x * y;
}
function renderCaptureOverlay() {
  const overlay = document.getElementById('capture-overlay');
  if (!overlay || overlay.style.display === 'none') return;
  try {
    _renderCaptureOverlayInner();
  } catch (e) {
    console.error('renderCaptureOverlay error:', e);
    overlay.innerHTML = '<div class="capture-label" style="left:12px;top:12px;color:#d35400;">⚠️ 갈무리 오류: ' + (e.message || String(e)) + '<br>콘솔(F12) 확인</div>';
  }
}
function _renderCaptureOverlayInner() {
  const overlay = document.getElementById('capture-overlay');
  const entries = buildCaptureEntries();
  overlay.innerHTML = '';
  if (entries.length === 0) {
    overlay.innerHTML = '<div class="capture-label" style="left:12px;top:12px;">작성된 후기/마크 메모가 없습니다.</div>';
    return;
  }
  const w = overlay.clientWidth || 800;
  const h = overlay.clientHeight || 600;
  const labelW = 240;
  const labelH = 92;
  const margin = 8;

  // SVG layer (화살표 라인)
  const svgNS = 'http://www.w3.org/2000/svg';
  const svg = document.createElementNS(svgNS, 'svg');
  svg.setAttribute('class', 'capture-svg');
  svg.setAttribute('width', w);
  svg.setAttribute('height', h);
  overlay.appendChild(svg);

  // 8방위 직각 후보 (대각선 X, 모두 축 정렬) - 각 entry마다 pt 기반 생성
  const labelMargin = 12;  // 마커와 라벨 사이 최소 간격

  const placed = [];
  entries.forEach(function(e, idx) {
    const pt = map.latLngToContainerPoint([e.lat, e.lng]);
    // pt가 화면 밖이면 마커 안 보이므로 라벨도 표시 안 함
    if (pt.x < -100 || pt.x > w + 100 || pt.y < -100 || pt.y > h + 100) return;

    // 8방위 후보 (이 entry의 pt 기준)
    const candidates = [
      // top-right: 라벨이 마커 우상단, anchor = 라벨 좌하단 모서리
      { name: 'TR', anchorSide: 'left-bottom', labelX: pt.x + labelMargin + 28, labelY: pt.y - labelH - labelMargin, anchorX: pt.x + labelMargin + 28, anchorY: pt.y - labelMargin, route: 'L' },
      // top-left: 라벨이 마커 좌상단, anchor = 라벨 우하단 모서리
      { name: 'TL', anchorSide: 'right-bottom', labelX: pt.x - labelW - labelMargin - 28, labelY: pt.y - labelH - labelMargin, anchorX: pt.x - labelMargin - 28, anchorY: pt.y - labelMargin, route: 'L' },
      // bottom-right: anchor = 라벨 좌상단 모서리
      { name: 'BR', anchorSide: 'left-top', labelX: pt.x + labelMargin + 28, labelY: pt.y + labelMargin, anchorX: pt.x + labelMargin + 28, anchorY: pt.y + labelMargin, route: 'L' },
      // bottom-left: anchor = 라벨 우상단 모서리
      { name: 'BL', anchorSide: 'right-top', labelX: pt.x - labelW - labelMargin - 28, labelY: pt.y + labelMargin, anchorX: pt.x - labelMargin - 28, anchorY: pt.y + labelMargin, route: 'L' },
      // right: 라벨이 마커 우측, anchor = 라벨 좌변 중앙
      { name: 'R', anchorSide: 'left-mid', labelX: pt.x + labelMargin + 28, labelY: pt.y - labelH/2, anchorX: pt.x + labelMargin + 28, anchorY: pt.y, route: 'H' },
      // left: 라벨이 마커 좌측, anchor = 라벨 우변 중앙
      { name: 'L', anchorSide: 'right-mid', labelX: pt.x - labelW - labelMargin - 28, labelY: pt.y - labelH/2, anchorX: pt.x - labelMargin - 28, anchorY: pt.y, route: 'H' },
      // top: 라벨이 마커 위, anchor = 라벨 하변 중앙
      { name: 'T', anchorSide: 'bottom-mid', labelX: pt.x - labelW/2, labelY: pt.y - labelH - labelMargin - 28, anchorX: pt.x, anchorY: pt.y - labelMargin - 28, route: 'V' },
      // bottom: 라벨이 마커 아래, anchor = 라벨 상변 중앙
      { name: 'B', anchorSide: 'top-mid', labelX: pt.x - labelW/2, labelY: pt.y + labelMargin + 28, anchorX: pt.x, anchorY: pt.y + labelMargin + 28, route: 'V' },
    ];

    let best = null;
    candidates.forEach(function(c) {
      const x = Math.min(Math.max(c.labelX, margin), Math.max(margin, w - labelW - margin));
      const y = Math.min(Math.max(c.labelY, margin), Math.max(margin, h - labelH - margin));
      const rect = {x: x, y: y, w: labelW, h: labelH};
      const overlap = placed.reduce(function(s, r) { return s + rectOverlap(rect, r); }, 0);
      // 라벨이 마커와 가까운 정도 (수평+수직 거리 합)
      const dist = Math.abs(x - pt.x) + Math.abs(y - pt.y);
      const score = overlap * 100000 + dist + idx;
      if (!best || score < best.score) best = Object.assign({x: x, y: y, score: score, rect: rect}, c);
    });
    placed.push(best.rect);

    // anchor 위치 계산 (라벨 모서리/중심)
    let anchorX, anchorY;
    if (best.anchorSide === 'left-bottom') { anchorX = best.x; anchorY = best.y + labelH; }
    else if (best.anchorSide === 'right-bottom') { anchorX = best.x + labelW; anchorY = best.y + labelH; }
    else if (best.anchorSide === 'left-top') { anchorX = best.x; anchorY = best.y; }
    else if (best.anchorSide === 'right-top') { anchorX = best.x + labelW; anchorY = best.y; }
    else if (best.anchorSide === 'left-mid') { anchorX = best.x; anchorY = best.y + labelH/2; }
    else if (best.anchorSide === 'right-mid') { anchorX = best.x + labelW; anchorY = best.y + labelH/2; }
    else if (best.anchorSide === 'bottom-mid') { anchorX = best.x + labelW/2; anchorY = best.y + labelH; }
    else if (best.anchorSide === 'top-mid') { anchorX = best.x + labelW/2; anchorY = best.y; }

    // === L자 path (직각, 수평/수직만) ===
    // 마커(pt)에서 라벨 anchor까지의 경로:
    // 1) 마커에서 가장 먼 축으로 먼저 이동
    // 2) 그 다음 가까운 축으로 이동
    // 3) anchor 도달
    let pathD;
    if (best.route === 'H') {
      // 마커 → 수평 이동 → anchor (라벨 좌/우변)
      // 마커 y가 anchor y와 다르면 한 번 꺾임
      if (Math.abs(pt.y - anchorY) > 0.5) {
        const midX = (pt.x + anchorX) / 2;
        pathD = `M ${pt.x} ${pt.y} L ${midX} ${pt.y} L ${midX} ${anchorY} L ${anchorX} ${anchorY}`;
      } else {
        pathD = `M ${pt.x} ${pt.y} L ${anchorX} ${anchorY}`;
      }
    } else if (best.route === 'V') {
      // 마커 → 수직 이동 → anchor (라벨 상/하변)
      if (Math.abs(pt.x - anchorX) > 0.5) {
        const midY = (pt.y + anchorY) / 2;
        pathD = `M ${pt.x} ${pt.y} L ${pt.x} ${midY} L ${anchorX} ${midY} L ${anchorX} ${anchorY}`;
      } else {
        pathD = `M ${pt.x} ${pt.y} L ${anchorX} ${anchorY}`;
      }
    } else {
      // L자 (대각선 → 수평/수직): 마커에서 라벨의 anchor 모서리까지
      // 첫 이동: 마커와 anchor의 x 차이 vs y 차이 중 큰 축으로
      const dx = Math.abs(pt.x - anchorX);
      const dy = Math.abs(pt.y - anchorY);
      if (dx > dy) {
        // x축 먼저: pt.x → anchorX (수평), 그 다음 → anchorY (수직)
        pathD = `M ${pt.x} ${pt.y} L ${anchorX} ${pt.y} L ${anchorX} ${anchorY}`;
      } else {
        // y축 먼저
        pathD = `M ${pt.x} ${pt.y} L ${pt.x} ${anchorY} L ${anchorX} ${anchorY}`;
      }
    }
    const path = document.createElementNS(svgNS, 'path');
    path.setAttribute('d', pathD);
    path.setAttribute('class', 'capture-line');
    path.setAttribute('fill', 'none');
    path.setAttribute('stroke-linejoin', 'miter');
    path.setAttribute('stroke-linecap', 'square');
    svg.appendChild(path);

    // === 시작점: 마커 anchor (큰 원) ===
    const markerAnchor = document.createElementNS(svgNS, 'circle');
    markerAnchor.setAttribute('cx', pt.x);
    markerAnchor.setAttribute('cy', pt.y);
    markerAnchor.setAttribute('r', 6);
    markerAnchor.setAttribute('class', 'capture-marker-anchor');
    svg.appendChild(markerAnchor);
    // 마커 anchor 내부 dot (흰색)
    const markerInner = document.createElementNS(svgNS, 'circle');
    markerInner.setAttribute('cx', pt.x);
    markerInner.setAttribute('cy', pt.y);
    markerInner.setAttribute('r', 2);
    markerInner.setAttribute('fill', '#ffffff');
    svg.appendChild(markerInner);

    // === 끝점: 라벨 anchor (사각형) + dot ===
    const labelAnchorSize = 5;
    const labelRect = document.createElementNS(svgNS, 'rect');
    labelRect.setAttribute('x', anchorX - labelAnchorSize/2);
    labelRect.setAttribute('y', anchorY - labelAnchorSize/2);
    labelRect.setAttribute('width', labelAnchorSize);
    labelRect.setAttribute('height', labelAnchorSize);
    labelRect.setAttribute('class', 'capture-label-anchor');
    svg.appendChild(labelRect);
    const labelDot = document.createElementNS(svgNS, 'circle');
    labelDot.setAttribute('cx', anchorX);
    labelDot.setAttribute('cy', anchorY);
    labelDot.setAttribute('r', 1.5);
    labelDot.setAttribute('class', 'capture-label-dot');
    svg.appendChild(labelDot);

    // 라벨 div
    const el = document.createElement('div');
    el.className = 'capture-label';
    el.style.left = best.x + 'px';
    el.style.top = best.y + 'px';
    el.innerHTML = captureEntryHtml(e);
    overlay.appendChild(el);
  });
}

function updateCaptureOverlayOnMove() {
  // overlay가 활성화돼 있을 때만 (throttled)
  const overlay = document.getElementById('capture-overlay');
  if (!overlay || overlay.style.display === 'none') return;
  if (window._captureRAF) return;  // rAF 중복 방지
  window._captureRAF = requestAnimationFrame(function() {
    window._captureRAF = null;
    renderCaptureOverlay();
  });
}

function captureMode() {
  if (photoLatLngs.length === 0) return;
  const btn = document.getElementById('btn-capture');
  btn.classList.toggle('active');
  const isActive = btn.classList.contains('active');
  const overlay = document.getElementById('capture-overlay');
  if (isActive) {
    const bounds = L.latLngBounds(photoLatLngs);
    SESSION.apartments.forEach(function(a) {
      if (a.lat && a.lng) bounds.extend([a.lat, a.lng]);
    });
    storage.user_marks.forEach(function(m) {
      if (m.lat && m.lng) bounds.extend([m.lat, m.lng]);
    });
    overlay.style.display = 'block';
    map.fitBounds(bounds, { padding: [90, 90], animate: false });
    requestAnimationFrame(renderCaptureOverlay);
    enableCaptureTracking();
    showSaveStatus('📸 갈무리: 후기 ' + buildCaptureEntries().length + '건 동시 표시 (지도 이동 따라감)');
  } else {
    overlay.style.display = 'none';
    overlay.innerHTML = '';
    map.closePopup();
    disableCaptureTracking();
  }
}

// === 갈무리 모드 중 지도 이동/줌 따라가기 ===
let _captureMoveHandler = null;
let _captureZoomHandler = null;
let _captureActive = false;

function enableCaptureTracking() {
  if (_captureActive) return;
  _captureActive = true;
  _captureMoveHandler = updateCaptureOverlayOnMove;
  _captureZoomHandler = updateCaptureOverlayOnMove;
  map.on('move', _captureMoveHandler);
  map.on('zoom', _captureZoomHandler);
  // 윈도우 리사이즈도 처리
  window.addEventListener('resize', _captureMoveHandler);
}
function disableCaptureTracking() {
  if (!_captureActive) return;
  _captureActive = false;
  if (_captureMoveHandler) {
    map.off('move', _captureMoveHandler);
    map.off('zoom', _captureZoomHandler);
    window.removeEventListener('resize', _captureMoveHandler);
  }
}

// captureMode를 갈무리 on/off 시 tracking도 함께 켜고 끄기
// (기존 captureMode의 on/off 로직에서 enable/disable 호출하도록 patch)

// === Reset view ===
function resetMapView() {
  if (photoLatLngs.length === 0) return;
  const bounds = L.latLngBounds(photoLatLngs);
  SESSION.apartments.forEach(function(a) {
    if (isHiddenApt(a.id)) return;
    if (a.lat && a.lng) bounds.extend([a.lat, a.lng]);
  });
  map.fitBounds(bounds, { padding: [40, 40] });
}

// === Focus apartment ===
function focusApt(aptId) {
  const apt = SESSION.apartments.find(function(a) { return a.id === aptId; });
  if (!apt) { console.error('apt not found:', aptId); return; }
  if (isHiddenApt(aptId)) {
    showSaveStatus('이 단지는 지도와 맞지 않아 삭제된 상태입니다');
    renderAptList();
    return;
  }
  if (!apt.lat || !apt.lng) {
    alert('이 단지는 좌표가 없습니다. kakao_map_link로 확인하세요.');
    return;
  }
  const marker = aptMarkers[aptId];
  if (marker) {
    map.setView(marker.getLatLng(), 17, { animate: true });
    marker.openPopup();
  } else {
    map.setView([apt.lat, apt.lng], 17);
  }
}

// === Panel toggle ===
function togglePanel(name) {
  const header = document.getElementById(name + '-header');
  const body = document.getElementById(name + '-body');
  header.classList.toggle('collapsed');
  body.classList.toggle('collapsed');
}

// === Search ===
document.getElementById('apt-search').addEventListener('input', renderAptList);
document.getElementById('apt-tag-select').addEventListener('change', renderAptList);

// === Export JSON ===
function exportSession() {
  const data = {
    session_metadata: {
      exported_at: new Date().toISOString(),
      session_id: SESSION.session_id,
      photo_count: SESSION.photos.length,
      apartment_count: SESSION.apartments.length,
      news_count: SESSION.news_items.length + storage.user_news.length,
      user_marks_count: storage.user_marks.length,
      review_count: Object.keys(storage.reviews).length
    },
    reviews: storage.reviews,
    favorite_apartments: storage.favorite_apartments || [],
    leader_apartments: storage.leader_apartments || [],
    hidden_apartments: storage.hidden_apartments || [],
    user_news: storage.user_news,
    user_marks: storage.user_marks,
    neighborhood_review: storage.neighborhood_review
  };
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'imjang_user_data_' + new Date().toISOString().slice(0,10) + '.json';
  a.click();
  URL.revokeObjectURL(url);
  showSaveStatus('💾 JSON 다운로드 완료');
}

// === v3: MD Export (Notion 참고용) ===
function exportMarkdown() {
  const md = generateMarkdown();
  // 기존 단일 MD 추출. Notion 이미지 임포트는 📦 ZIP 생성을 권장.
  showSaveStatus('📝 MD 생성 중 (사진 포함)...');
  embedPhotosAndDownload(md);
}

function generateMarkdown() {
  const lines = [];
  const dt = new Date().toISOString().slice(0, 10);

  lines.push('# 🏠 ' + REPORT_TITLE_JS);
  lines.push('');
  lines.push(MD_INTRO_JS);
  lines.push(PRICE_BASIS_JS);
  lines.push('');

  // 첫 섹션: 동네 총평. 사용자가 아직 적지 않아도 공란 템플릿을 유지한다.
  appendNeighborhoodReviewMarkdown(lines);

  // 사진 헤더 → 사진 → 후기 순차
  lines.push('## 📷 임장 사진 + 후기');
  lines.push('');

  const sortedPhotos = SESSION.photos.slice().sort(function(a, b) {
    return (a.timestamp || '').localeCompare(b.timestamp || '');
  });

  sortedPhotos.forEach(function(p, i) {
    const review = getReviewText(p.id);
    const tags = getReviewTags(p.id);
    if (!review) return;  // 실제 후기 문구가 없는 사진은 스킵 (태그만으로는 추출 대상 아님)
    const time = p.timestamp ? p.timestamp.substring(0, 16).replace('T', ' ') : '';
    lines.push('### ' + (i+1) + '. ' + time);
    lines.push('');
    lines.push('![사진](' + photoMarkdownUrl(p) + ')');
    lines.push('');
    if (review) {
      lines.push('**📝 후기:**');
      lines.push('');
      lines.push('> ' + review.replace(/\n/g, '\n> '));
      lines.push('');
    }
    if (tags.length) {
      lines.push('**태그:** ' + tags.map(function(t) { return '`' + t + '`'; }).join(', '));
      lines.push('');
    }
  });

  // 아파트 헤더 → 단지 → 후기
  lines.push('## 🏢 아파트 단지 후기');
  lines.push('');

  const reviewedApts = SESSION.apartments.filter(function(a) {
    return !isHiddenApt(a.id) && !!getReviewText(a.id);
  });

  if (reviewedApts.length === 0) {
    lines.push('_(아파트 후기 없음)_');
    lines.push('');
  } else {
    reviewedApts.forEach(function(a, i) {
      const review = getReviewText(a.id);
      const tags = getReviewTags(a.id);
      const aptTags = a.tags || [];
      const allTags = (isFavoriteApt(a.id) ? ['관심단지'] : []).concat(isLeaderApt(a.id) ? ['대장아파트'] : []).concat(aptTags).concat(tags);
      lines.push('### ' + (i+1) + '. ' + a.name + (isLeaderApt(a.id) ? ' 👑대장' : '') + (isFavoriteApt(a.id) ? ' ★관심' : ''));
      lines.push('');
      lines.push('- **주소**: ' + a.address);
      if (a.built_year) lines.push('- **준공**: ' + a.built_year + '년');
      if (a.recent_trade_price) lines.push('- **중위 매매**: ' + a.recent_trade_price);
      else lines.push('- **중위 매매**: 국토교통부 아파트매매 실거래가 API로 조회되지 않음');
      if (a.jeonse_price) lines.push('- **중위 전세**: ' + a.jeonse_price);
      if (a.latest_deal_date) lines.push('- **기준일**: ' + formatDealDateInfo(a, '기준일').replace(/^기준일: /, ''));
      if (a.kakao_map_link) lines.push('- **카카오맵**: [' + a.name + '](' + a.kakao_map_link + ')');
      if (a.naver_link) lines.push('- **네이버부동산**: [' + a.name + '](' + a.naver_link + ')');
      if (allTags.length) lines.push('- **태그**: ' + allTags.map(function(t) { return '`' + t + '`'; }).join(', '));
      lines.push('');
      if (review) {
        lines.push('**📝 후기:**');
        lines.push('');
        lines.push('> ' + review.replace(/\n/g, '\n> '));
        lines.push('');
      }
    });
  }

  // 사용자 마크
  if (storage.user_marks.length > 0) {
    lines.push('## 📍 사용자 마크 (' + storage.user_marks.length + '개)');
    lines.push('');
    storage.user_marks.forEach(function(m, i) {
      lines.push('### ' + (i+1) + '. ' + (m.type || '📍') + ' ' + m.name);
      if (m.note) lines.push('> ' + m.note);
      lines.push('위도: ' + m.lat.toFixed(6) + ', 경도: ' + m.lng.toFixed(6));
      lines.push('[카카오맵에서 보기](https://map.kakao.com/?q=' + encodeURIComponent(m.name) + ')');
      lines.push('');
    });
  }

  // 호재 뉴스
  if (SESSION.news_items.length > 0) {
    lines.push('## 📰 호재/뉴스 (' + SESSION.news_items.length + '건)');
    lines.push('');
    SESSION.news_items.slice(0, 15).forEach(function(n) {
      lines.push('- [' + n.title + '](' + (n.url || '#') + ') - ' + (n.published_at || '').substring(0, 10) +
        (n.tags && n.tags.length ? ' ' + n.tags.map(function(t) { return '`' + t + '`'; }).join(' ') : ''));
    });
    lines.push('');
  }

  // 사용자 뉴스
  if (storage.user_news.length > 0) {
    lines.push('## 📰 사용자 추가 뉴스 (' + storage.user_news.length + '건)');
    lines.push('');
    storage.user_news.forEach(function(n) {
      lines.push('- [' + n.title + '](' + (n.url || '#') + ')');
    });
    lines.push('');
  }

  lines.push('---');
  lines.push('');
  lines.push('*생성: ' + dt + ' | 임장 리포트 v3*');
  lines.push('');

  return lines.join('\n');
}

async function embedPhotosAndDownload(md) {
  // 사진을 base64로 임베드 (Notion에 drag&drop 가능)
  const sortedPhotos = SESSION.photos.filter(function(p) {
    return !!getReviewText(p.id);
  }).sort(function(a, b) {
    return (a.timestamp || '').localeCompare(b.timestamp || '');
  });

  const lines = md.split('\n');
  const newLines = [];
  let i = 0;
  let photoIdx = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (line.startsWith('### ') && i + 2 < lines.length && lines[i+2].startsWith('![사진](')) {
      // 사진 헤더 + 빈줄 + 사진 마크다운 → base64 임베드
      newLines.push(line);
      newLines.push('');
      // Fetch and convert to base64
      if (photoIdx < sortedPhotos.length) {
        const p = sortedPhotos[photoIdx];
        try {
          const photoUrl = photoMarkdownUrl(p);
          const img = await fetch(photoUrl).then(function(r) { if (!r.ok) throw new Error('image fetch failed'); return r.blob(); });
          const reader = new FileReader();
          const dataUrl = await new Promise(function(resolve) {
            reader.onloadend = function() { resolve(reader.result); };
            reader.readAsDataURL(img);
          });
          newLines.push('![사진](' + dataUrl + ')');
        } catch (e) {
          newLines.push('![사진](' + photoMarkdownUrl(p) + ')');
        }
        photoIdx++;
      } else {
        newLines.push(lines[i+2]);
      }
      i += 3;  // skip the ![](...) line
      continue;
    }
    newLines.push(line);
    i++;
  }

  const finalMd = newLines.join('\n');
  const blob = new Blob([finalMd], { type: 'text/markdown' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'imjang_review_' + new Date().toISOString().slice(0,10) + '.md';
  a.click();
  URL.revokeObjectURL(url);
  showSaveStatus('📝 MD 다운로드 완료 (' + photoIdx + '장 임베드)');
}

// === v4: Notion ZIP Export (Markdown + images/) ===
// Notion API/CORS 대신 Markdown Import가 인식하는 ZIP 구조를 브라우저에서 생성한다.

function openNotionExportModal() {
  const sourceFolder = SESSION.photo_folder || (SESSION.photos && SESSION.photos[0] && SESSION.photos[0].abs_path ? SESSION.photos[0].abs_path.replace(/[\\/][^\\/]+$/, '') : 'assets/photos');
  const reviewedCount = photosForNotionZip(false).length;
  const hint = document.getElementById('notion-photo-folder-hint');
  if (hint) {
    hint.innerHTML = '<strong>선택창이 뜨면 이렇게 고르세요.</strong><br>' +
      '1차 선택창: <strong>원본 임장 사진 폴더</strong><br>' +
      '<code>' + escapeHtml(sourceFolder) + '</code><br>' +
      '<span style="color:#666;">처음 촬영 사진이 들어 있던 폴더입니다.</span><br><br>' +
      '2차 선택창: <strong>추출할 대상 위치</strong><br>' +
      '<span style="color:#666;">브라우저가 한 번 더 물어보면, 위와 같은 원본 사진 폴더를 다시 선택하면 됩니다. HTML 파일 기준의 상대경로를 직접 계산해서 고를 필요는 없습니다.</span><br><br>' +
      '<span style="color:#666;">기본 추출 대상: 실제 후기 문구가 입력된 사진 ' + reviewedCount + '장</span>';
  }
  document.getElementById('notion-export-modal').classList.add('show');
  document.getElementById('notion-progress').style.display = 'none';
}
function closeNotionExportModal() {
  document.getElementById('notion-export-modal').classList.remove('show');
}
function notionProgress(msg, pct) {
  const el = document.getElementById('notion-progress');
  el.style.display = 'block';
  el.innerHTML = '<strong>' + (pct !== undefined ? '[' + pct + '%] ' : '') + '</strong>' + escapeHtml(msg);
}

function notionZipSlug(s) {
  return String(s || 'image')
    .replace(/[\\/:*?"<>|\s]+/g, '_')
    .replace(/_+/g, '_')
    .replace(/^[_\.]+|[_\.]+$/g, '')
    .slice(0, 70) || 'image';
}

function photoExtFromFilename(filename, contentType) {
  const lower = String(filename || '').toLowerCase();
  const m = lower.match(/\.(jpe?g|png|gif|webp|heic|heif)$/);
  if (m) return m[1] === 'jpeg' ? 'jpg' : m[1];
  if (contentType && contentType.includes('png')) return 'png';
  if (contentType && contentType.includes('gif')) return 'gif';
  if (contentType && contentType.includes('webp')) return 'webp';
  return 'jpg';
}

function photosForNotionZip(includeAll) {
  return SESSION.photos.slice().sort(function(a, b) {
    return (a.timestamp || '').localeCompare(b.timestamp || '') || (a.filename || '').localeCompare(b.filename || '');
  }).filter(function(p) {
    return includeAll || !!getReviewText(p.id);
  });
}

function generateMarkdownForNotionZip(imageMap) {
  const lines = [];
  const dt = new Date().toISOString().slice(0, 10);
  lines.push('# 🏠 ' + REPORT_TITLE_JS);
  lines.push('');
  lines.push(MD_INTRO_JS.replace('사진 ' + SESSION.photos.length + '장', '사진 ' + Object.keys(imageMap).length + '장'));
  lines.push(PRICE_BASIS_JS);
  lines.push('');

  // 첫 섹션: 동네 총평. 사용자가 아직 적지 않아도 공란 템플릿을 유지한다.
  appendNeighborhoodReviewMarkdown(lines);

  lines.push('## 📷 임장 사진 + 후기');
  lines.push('');
  photosForNotionZip(document.getElementById('notion-zip-all-photos').checked).forEach(function(p, i) {
    const review = getReviewText(p.id);
    const tags = getReviewTags(p.id);
    const time = p.timestamp ? p.timestamp.substring(0, 16).replace('T', ' ') : (p.filename || '사진');
    lines.push('### ' + (i+1) + '. ' + time);
    lines.push('');
    if (imageMap[p.id]) {
      lines.push('![사진](' + imageMap[p.id] + ')');
      lines.push('');
    }
    if (review) {
      lines.push('**📝 후기:**');
      lines.push('');
      lines.push('> ' + review.replace(/\n/g, '\n> '));
      lines.push('');
    }
    if (tags.length) {
      lines.push('**태그:** ' + tags.map(function(t) { return '`' + t + '`'; }).join(', '));
      lines.push('');
    }
  });

  lines.push('## 🏢 아파트 단지 후기');
  lines.push('');
  const reviewedApts = SESSION.apartments.filter(function(a) {
    return !isHiddenApt(a.id) && !!getReviewText(a.id);
  });
  if (reviewedApts.length === 0) {
    lines.push('_(아파트 후기 없음)_');
    lines.push('');
  } else {
    reviewedApts.forEach(function(a, i) {
      const review = getReviewText(a.id);
      const tags = getReviewTags(a.id);
      const allTags = (isFavoriteApt(a.id) ? ['관심단지'] : []).concat(isLeaderApt(a.id) ? ['대장아파트'] : []).concat(a.tags || []).concat(tags);
      lines.push('### ' + (i+1) + '. ' + a.name + (isLeaderApt(a.id) ? ' 👑대장' : '') + (isFavoriteApt(a.id) ? ' ★관심' : ''));
      lines.push('');
      if (a.address) lines.push('- **주소**: ' + a.address);
      if (a.distance_to_route_m !== undefined) lines.push('- **동선 거리**: ' + Math.round(a.distance_to_route_m) + 'm');
      if (a.built_year) lines.push('- **준공**: ' + a.built_year + '년');
      if (a.recent_trade_price) lines.push('- **중위 매매**: ' + a.recent_trade_price);
      else lines.push('- **중위 매매**: 국토교통부 아파트매매 실거래가 API로 조회되지 않음');
      if (a.jeonse_price) lines.push('- **중위 전세**: ' + a.jeonse_price);
      if (a.latest_deal_date) lines.push('- **기준일**: ' + formatDealDateInfo(a, '기준일').replace(/^기준일: /, ''));
      if (a.kakao_map_link) lines.push('- **카카오맵**: [' + a.name + '](' + a.kakao_map_link + ')');
      if (a.naver_link) lines.push('- **네이버부동산**: [' + a.name + '](' + a.naver_link + ')');
      if (allTags.length) lines.push('- **태그**: ' + allTags.map(function(t) { return '`' + t + '`'; }).join(', '));
      lines.push('');
      if (review) {
        lines.push('**📝 후기:**');
        lines.push('');
        lines.push('> ' + review.replace(/\n/g, '\n> '));
        lines.push('');
      }
    });
  }

  if (storage.user_marks.length > 0) {
    lines.push('## 📍 사용자 마크 (' + storage.user_marks.length + '개)');
    lines.push('');
    storage.user_marks.forEach(function(m, i) {
      lines.push('### ' + (i+1) + '. ' + (m.type || '📍') + ' ' + m.name);
      if (m.note) lines.push('> ' + m.note);
      lines.push('위도: ' + m.lat.toFixed(6) + ', 경도: ' + m.lng.toFixed(6));
      lines.push('');
    });
  }

  if (SESSION.news_items.length > 0) {
    lines.push('## 📰 호재/뉴스 (' + SESSION.news_items.length + '건)');
    lines.push('');
    SESSION.news_items.slice(0, 15).forEach(function(n) {
      lines.push('- [' + n.title + '](' + (n.url || '#') + ') - ' + (n.published_at || '').substring(0, 10) +
        (n.tags && n.tags.length ? ' ' + n.tags.map(function(t) { return '`' + t + '`'; }).join(' ') : ''));
    });
    lines.push('');
  }

  if (storage.user_news.length > 0) {
    lines.push('## 📰 사용자 추가 뉴스 (' + storage.user_news.length + '건)');
    lines.push('');
    storage.user_news.forEach(function(n) {
      lines.push('- [' + n.title + '](' + (n.url || '#') + ')');
    });
    lines.push('');
  }

  lines.push('---');
  lines.push('*생성: ' + dt + ' | 임장 리포트 v3 | Notion Markdown ZIP*');
  lines.push('');
  return lines.join('\n');
}

async function readPhotoBlobForZip(photo, state) {
  const url = 'assets/photos/' + encodeURIComponent(photo.filename).replace(/%2F/g, '/');
  try {
    const resp = await fetch(url);
    if (!resp.ok) throw new Error('HTTP ' + resp.status);
    return await resp.blob();
  } catch (fetchErr) {
    if (!window.showDirectoryPicker) {
      throw new Error('로컬 이미지 fetch 실패: ' + (fetchErr.message || fetchErr) + '. 현재 브라우저가 폴더 선택 API도 지원하지 않습니다.');
    }
    if (!state.dirHandle) {
      notionProgress('브라우저가 로컬 사진 자동 읽기를 막았습니다. 지금 뜨는 선택창에서 ZIP 저장 위치가 아니라 원본 임장 사진 폴더를 선택하세요. 한 번 더 물어보면 같은 원본 사진 폴더를 다시 선택하면 됩니다.', 5);
      state.dirHandle = await window.showDirectoryPicker({ id: 'imjang-photos', mode: 'read' });
    }
    const handle = await state.dirHandle.getFileHandle(photo.filename);
    return await handle.getFile();
  }
}

async function startNotionZipExport() {
  if (typeof JSZip === 'undefined') {
    alert('JSZip 라이브러리를 불러오지 못했습니다. 인터넷 연결을 확인하거나 Hermes 로컬 스크립트 export_notion_md_zip.py를 사용하세요.');
    return;
  }
  const includeAll = document.getElementById('notion-zip-all-photos').checked;
  const photos = photosForNotionZip(includeAll);
  if (photos.length === 0) {
    alert('ZIP에 넣을 사진이 없습니다. 후기 없는 사진도 포함 옵션을 켜거나 사진 후기를 먼저 작성하세요.');
    return;
  }
  const zip = new JSZip();
  const images = zip.folder('images');
  const imageMap = {};
  const failures = [];
  const readState = { dirHandle: null };
  notionProgress('ZIP 준비 중...', 1);

  for (let i = 0; i < photos.length; i++) {
    const p = photos[i];
    const pct = 5 + Math.floor((i / photos.length) * 70);
    notionProgress('사진 추가 중... (' + (i+1) + '/' + photos.length + ')', pct);
    try {
      const blob = await readPhotoBlobForZip(p, readState);
      const ext = photoExtFromFilename(p.filename, blob.type);
      const name = String(i+1).padStart(3, '0') + '_' + notionZipSlug((p.filename || 'photo').replace(/\.[^.]+$/, '')) + '.' + ext;
      images.file(name, blob);
      imageMap[p.id] = 'images/' + name;
    } catch (e) {
      console.error('ZIP 사진 추가 실패:', p.filename, e);
      failures.push((p.filename || p.id) + ': ' + (e.message || e));
    }
  }

  notionProgress('Markdown 생성 중...', 80);
  zip.file('imjang_report.md', generateMarkdownForNotionZip(imageMap));
  zip.file('README_NOTION_IMPORT.txt', [
    'Notion Import 방법',
    '1. Notion → Settings → Import → Text & Markdown',
    '2. 이 ZIP 파일을 그대로 업로드',
    '3. imjang_report.md와 images/ 상대경로가 함께 임포트됩니다.',
    '',
    '사진 포함: ' + Object.keys(imageMap).length + '장',
    '사진 실패: ' + failures.length + '장',
  ].concat(failures.slice(0, 100)).join('\n'));

  notionProgress('ZIP 압축 중... 브라우저가 잠시 멈출 수 있습니다.', 90);
  const blob = await zip.generateAsync({type: 'blob', compression: 'DEFLATE', compressionOptions: {level: 6}}, function(meta) {
    notionProgress('ZIP 압축 중... ' + Math.round(meta.percent) + '%', 90 + Math.floor(meta.percent / 10));
  });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'imjang_notion_import_' + new Date().toISOString().slice(0,10) + '.zip';
  a.click();
  URL.revokeObjectURL(url);
  notionProgress('✅ ZIP 다운로드 완료 — Notion Settings → Import → Text & Markdown에서 업로드하세요. 사진 ' + Object.keys(imageMap).length + '장 포함' + (failures.length ? ', 실패 ' + failures.length + '장' : ''), 100);
  showSaveStatus('📦 Notion ZIP 다운로드 완료 (' + Object.keys(imageMap).length + '장)');
}

// === Refresh all UI after review change ===
function refreshAll() {
  renderStreakTagFilter();
  renderStreak();
  renderAptTagFilter();
  renderAptList();
  renderNewsList();
  updateNbReviewStatus();
  // 마커 아이콘 갱신 (저장/삭제 후 M/N 변경 반영)
  refreshMarkerIcons();
  // location.reload();  // 마커는 수동 갱신으로 변경
}

function refreshMarkerIcons() {
  // 사진 마커 아이콘 갱신
  photoMarkers.forEach(function(m) {
    const ll = m.getLatLng();
    // 이 마커에 해당하는 클러스터 찾기
    let ps = null;
    Object.keys(clusterPhotosByCid).forEach(function(cid) {
      if (!ps) {
        const cps = clusterPhotosByCid[cid];
        const cLat = cps.reduce(function(s, p) { return s + p.lat; }, 0) / cps.length;
        const cLng = cps.reduce(function(s, p) { return s + p.lng; }, 0) / cps.length;
        if (Math.abs(cLat - ll.lat) < 0.0001 && Math.abs(cLng - ll.lng) < 0.0001) {
          ps = cps;
        }
      }
    });
    if (ps) {
      const reviewedCount = ps.filter(function(p) { return getReviewText(p.id); }).length;
      m.setIcon(photoIcon(reviewedCount, ps.length));
    }
  });
  // 아파트 마커 아이콘/팝업 갱신
  refreshAptMarkers();
}

// === Small-screen Streak drawer ===
function openStreakDrawer() {
  document.body.classList.add('streak-drawer-open');
}
function closeStreakDrawer() {
  document.body.classList.remove('streak-drawer-open');
}
window.addEventListener('keydown', function(e) {
  if (e.key === 'Escape') closeStreakDrawer();
});
window.addEventListener('resize', function() {
  if (window.innerWidth > 1100) closeStreakDrawer();
});

console.log('Anyang imjang v3 loaded.');
console.log('Photos:', SESSION.photos.length, '| Apartments:', SESSION.apartments.length, '| News:', SESSION.news_items.length, '| Reviews:', Object.keys(storage.reviews).length);
</script>
</body>
</html>'''

# Replace placeholders
html_content = html_content.replace('PHOTOS_COUNT', str(len(photos)))
html_content = html_content.replace('APTS_COUNT', str(len(apartments)))

html_content = html_content.replace('FACS_COUNT', str(len(facilities)))
html_content = html_content.replace('NEWS_COUNT', str(len(news)))
html_content = html_content.replace('SESSION_PLACEHOLDER', session_json)
html_content = html_content.replace('REPORT_TITLE', report_title)
html_content = html_content.replace('REPORT_META', report_meta)
html_content = html_content.replace('STORAGE_KEY_PLACEHOLDER', storage_key)
html_content = html_content.replace('REPORT_TITLE_JS', json.dumps(report_title, ensure_ascii=False))
html_content = html_content.replace('MD_INTRO_JS', json.dumps(md_intro, ensure_ascii=False))
html_content = html_content.replace('PRICE_BASIS_JS', json.dumps(price_basis, ensure_ascii=False))

out_path.parent.mkdir(parents=True, exist_ok=True)
with out_path.open('w', encoding='utf-8') as f:
    f.write(html_content)

print(f"=== Generated: {out_path} ===")
print(f"  size: {os.path.getsize(out_path)} bytes ({os.path.getsize(out_path)/1024:.1f}KB)")
